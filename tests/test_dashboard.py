import json
from datetime import timedelta

from rastreador.dashboard import construir, escribir
from rastreador.modelos import Ajustes, Configuracion, Estado, Lectura

from .conftest import FECHA, hacer_producto

ESTANDAR = hacer_producto("walmart_vende_walmart", id="walmart-estandar")
BUNDLE = hacer_producto("sears_vende_sears", id="sears-bundle", valor_extra=180_000, precio_objetivo=900_000)
NUEVO = hacer_producto("gameplanet_en_stock", id="gameplanet-estandar")
CONFIG = Configuracion(
    ajustes=Ajustes(lecturas_minimas=3, precio_min_valido=500_000, precio_max_valido=2_500_000, precio_objetivo=950_000),
    productos=(ESTANDAR, BUNDLE, NUEVO),
)


def lectura(producto, dia, estado=Estado.OK, pesos=None, motivo=""):
    return Lectura(fecha=FECHA + timedelta(days=dia), producto_id=producto.id, tienda=producto.tienda,
                   estado=estado, precio=None if pesos is None else pesos * 100, motivo=motivo)


HISTORIAL = [
    lectura(ESTANDAR, 0, pesos=10_790),
    lectura(ESTANDAR, 1, pesos=10_500),
    lectura(ESTANDAR, 2, pesos=10_990),
    lectura(ESTANDAR, 3, Estado.AGOTADO, pesos=10_400),  # agotado: precio visible, no cuenta para mín/máx
    lectura(BUNDLE, 0, pesos=15_249),
    lectura(BUNDLE, 1, pesos=12_000),
    lectura(BUNDLE, 2, Estado.ERROR, motivo="red: ReadTimeout"),
    lectura(BUNDLE, 3, Estado.NO_ENCONTRADO, motivo="HTTP 404: el producto necesita URL nueva"),
    lectura(hacer_producto(id="retirado"), 0, pesos=1),  # ya no está en la configuración: se ignora
]


def por_id(datos):
    return {p["id"]: p for p in datos["productos"]}


def test_resumen_por_producto():
    datos = construir(CONFIG, HISTORIAL, FECHA + timedelta(days=3, hours=1))
    estandar, bundle, nuevo = (por_id(datos)[i] for i in ("walmart-estandar", "sears-bundle", "gameplanet-estandar"))

    assert estandar["estado"] == "agotado"
    assert (estandar["precio_actual"], estandar["efectivo_actual"]) == (1_040_000, 1_040_000)
    assert estandar["minimo"] == {"efectivo": 1_050_000, "fecha_utc": "2026-09-29T14:17:03Z"}
    assert estandar["maximo"] == {"efectivo": 1_099_000, "fecha_utc": "2026-09-30T14:17:03Z"}
    assert estandar["lecturas_ok"] == 3
    assert estandar["serie"] == [["2026-09-28T14:17:03Z", 1_079_000], ["2026-09-29T14:17:03Z", 1_050_000],
                                 ["2026-09-30T14:17:03Z", 1_099_000]]
    assert estandar["precio_objetivo"] == 950_000  # el global

    assert bundle["estado"] == "no_encontrado"
    assert bundle["motivo"] == "HTTP 404: el producto necesita URL nueva"
    assert bundle["racha_fallos"] == 2  # "lleva 2 días fallando"
    assert bundle["efectivo_actual"] is None
    assert bundle["minimo"]["efectivo"] == 1_020_000  # 12,000 − extra 1,800
    assert bundle["precio_objetivo"] == 900_000  # el propio
    assert bundle["valor_extra"] == 180_000

    assert nuevo["estado"] == "sin_datos"
    assert nuevo["serie"] == [] and nuevo["minimo"] is None
    assert "retirado" not in por_id(datos)


def test_mejor_precio_solo_entre_lecturas_ok_vigentes():
    datos = construir(CONFIG, HISTORIAL, FECHA)
    assert datos["mejor"] is None  # el más barato está agotado y el otro no se encontró

    con_ok = HISTORIAL + [lectura(NUEVO, 3, pesos=10_999)]
    assert construir(CONFIG, con_ok, FECHA)["mejor"] == {"producto_id": "gameplanet-estandar", "efectivo": 1_099_900}


def test_metadatos_y_escritura_atomica(tmp_path):
    datos = construir(CONFIG, HISTORIAL, FECHA)
    assert datos["version_formato"] == 1
    assert datos["generado_utc"] == "2026-09-28T14:17:03Z"
    assert datos["precio_objetivo"] == 950_000

    ruta = tmp_path / "docs" / "datos.json"
    escribir(ruta, datos)
    assert json.loads(ruta.read_text(encoding="utf-8")) == datos
    assert list(ruta.parent.iterdir()) == [ruta]  # no queda el .tmp
    assert b"\r\n" not in ruta.read_bytes()
