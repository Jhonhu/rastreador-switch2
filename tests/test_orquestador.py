"""Flujo de punta a punta simulado de varios días: fixtures reales, sin red ni esperas.

Un "día" = una llamada a ejecutar() con un reloj y un mundo (precios) distintos.
El historial CSV persiste entre días en tmp_path, como en el repo.
"""

from datetime import timedelta

import pytest

from rastreador.alertas import TipoAlerta
from rastreador.descarga import ErrorDescarga, Respuesta
from rastreador.historial import leer_lecturas
from rastreador.modelos import Ajustes, Configuracion, Estado
from rastreador.notificador import ErrorNotificacion
from rastreador.orquestador import PAUSA_ENTRE_DESCARGAS, Dependencias, ejecutar

from .conftest import FECHA, URLS, hacer_producto, leer_fixture

WALMART = hacer_producto("walmart_vende_walmart", id="walmart-estandar")
SEARS = hacer_producto("sears_vende_sears", id="sears-estandar")
LIVERPOOL = hacer_producto("liverpool_estandar", id="liverpool-estandar", valor_extra=100_000)
CONFIG = Configuracion(
    ajustes=Ajustes(lecturas_minimas=2, precio_min_valido=500_000, precio_max_valido=2_500_000, precio_objetivo=1_000_000),
    productos=(WALMART, SEARS, LIVERPOOL),
)


def pagina_walmart(pesos: int) -> Respuesta:
    html = leer_fixture("walmart_vende_walmart").replace('"price": 10790', f'"price": {pesos}')
    return Respuesta(200, URLS["walmart_vende_walmart"], html)


class NotificadorEspia:
    def __init__(self):
        self.mensajes: list[str] = []

    def enviar(self, texto: str) -> None:
        self.mensajes.append(texto)


class Simulacion:
    def __init__(self, ruta):
        self.ruta, self.dia, self.notificador, self.pausas = ruta, 0, NotificadorEspia(), []

    def correr(self, mundo: dict[str, Respuesta | ErrorDescarga]):
        """mundo: URL -> lo que responde la tienda ese día."""
        def descargar(url: str) -> Respuesta:
            resultado = mundo[url]
            if isinstance(resultado, ErrorDescarga):
                raise resultado
            return resultado

        fecha = FECHA + timedelta(days=self.dia)
        self.dia += 1
        deps = Dependencias(descargar=descargar, reloj=lambda: fecha, pausa=self.pausas.append, notificador=self.notificador)
        return ejecutar(CONFIG, self.ruta, deps)


def mundo(walmart: Respuesta | ErrorDescarga, sears=None, liverpool=None):
    return {
        WALMART.url: walmart,
        SEARS.url: sears or Respuesta(404, SEARS.url, "<html>No encontrado</html>"),
        LIVERPOOL.url: liverpool or Respuesta(200, LIVERPOOL.url, leer_fixture("liverpool_estandar")),
    }


def test_varios_dias_de_historial_y_alertas(tmp_path):
    sim = Simulacion(tmp_path / "data" / "lecturas.csv")
    alertas_por_dia = []
    for walmart in [
        pagina_walmart(10790),  # día 0: primera lectura, sin historial
        pagina_walmart(10790),  # día 1
        pagina_walmart(10500),  # día 2: nuevo mínimo (hay 2 previas)
        ErrorDescarga("red: ReadTimeout"),  # día 3: falla la red
        pagina_walmart(9900),  # día 4: nuevo mínimo + cruza el objetivo de $10,000
        pagina_walmart(9800),  # día 5: nuevo mínimo; sigue abajo -> el cruce NO se repite
        pagina_walmart(10200),  # día 6: sube
        pagina_walmart(9950),  # día 7: vuelve a cruzar; no es mínimo (9800 fue menor)
    ]:
        resumen = sim.correr(mundo(walmart))
        alertas_por_dia.append({(a.producto.id, a.tipo) for a in resumen.alertas})
        assert not resumen.todas_fallaron  # Sears 404 todos los días = fallo parcial

    minimo, cruce = TipoAlerta.MINIMO_HISTORICO, TipoAlerta.CRUCE_OBJETIVO
    assert alertas_por_dia == [
        set(), set(),
        {("walmart-estandar", minimo)},
        set(),
        {("walmart-estandar", minimo), ("walmart-estandar", cruce)},
        {("walmart-estandar", minimo)},
        set(),
        {("walmart-estandar", cruce)},
    ]
    # Liverpool: $12,879.08 − extra $1,000 = $11,879.08 estable, nunca alerta.
    assert len(sim.notificador.mensajes) == 4  # un mensaje por día con alertas, no uno por alerta

    historial = leer_lecturas(sim.ruta)
    assert len(historial) == 8 * 3
    walmart = [l for l in historial if l.producto_id == "walmart-estandar"]
    assert [l.estado for l in walmart].count(Estado.ERROR) == 1
    assert walmart[3].motivo == "red: ReadTimeout"
    sears = {l.estado for l in historial if l.producto_id == "sears-estandar"}
    assert sears == {Estado.NO_ENCONTRADO}
    # Pausa de cortesía entre descargas: 2 por día con 3 productos.
    assert sim.pausas == [PAUSA_ENTRE_DESCARGAS] * 2 * 8


def test_si_todas_fallan_el_resumen_lo_marca_y_el_historial_lo_registra(tmp_path):
    sim = Simulacion(tmp_path / "lecturas.csv")
    caida = ErrorDescarga("red: ConnectionError")
    resumen = sim.correr(mundo(caida, sears=caida, liverpool=Respuesta(403, LIVERPOOL.url, "Access Denied")))
    assert resumen.todas_fallaron
    assert [l.estado for l in leer_lecturas(sim.ruta)] == [Estado.ERROR, Estado.ERROR, Estado.BLOQUEADO]
    assert sim.notificador.mensajes == []


def test_si_telegram_falla_las_lecturas_ya_estan_guardadas(tmp_path):
    class NotificadorRoto:
        def enviar(self, texto):
            raise ErrorNotificacion("Telegram: fallo de red (ConnectTimeout)")

    ruta = tmp_path / "lecturas.csv"
    deps = Dependencias(
        descargar=lambda url: mundo(pagina_walmart(9000))[url],
        reloj=lambda: FECHA, pausa=lambda s: None, notificador=NotificadorRoto(),
    )
    resumen = ejecutar(CONFIG, ruta, deps)  # primera lectura bajo el objetivo -> intenta avisar
    assert resumen.fallo_notificacion == "Telegram: fallo de red (ConnectTimeout)"
    assert len(resumen.alertas) == 1
    assert len(leer_lecturas(ruta)) == 3


def test_un_error_inesperado_del_notificador_no_se_disfraza(tmp_path):
    class NotificadorConBug:
        def enviar(self, texto):
            raise RuntimeError("bug")

    deps = Dependencias(
        descargar=lambda url: mundo(pagina_walmart(9000))[url],
        reloj=lambda: FECHA, pausa=lambda s: None, notificador=NotificadorConBug(),
    )
    with pytest.raises(RuntimeError):
        ejecutar(CONFIG, tmp_path / "lecturas.csv", deps)
