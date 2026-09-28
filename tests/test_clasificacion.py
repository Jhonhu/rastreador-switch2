import pytest

from rastreador.clasificacion import clasificar
from rastreador.descarga import ErrorDescarga, Respuesta
from rastreador.modelos import Estado

from .conftest import FECHA, URLS, hacer_producto, leer_fixture


def respuesta(fixture: str, status: int = 200, url_final: str | None = None) -> Respuesta:
    return Respuesta(status=status, url_final=url_final or URLS[fixture], texto=leer_fixture(fixture))


def test_lectura_ok_guarda_precio_lista_y_vendedor(ajustes):
    lectura = clasificar(hacer_producto("walmart_vende_walmart"), ajustes, respuesta("walmart_vende_walmart"), FECHA)
    assert lectura.estado is Estado.OK
    assert (lectura.precio, lectura.precio_lista, lectura.vendedor) == (1_079_000, 1_399_900, "Walmart")
    assert (lectura.fecha, lectura.producto_id, lectura.tienda) == (FECHA, "prueba", "walmart")


def test_agotado_conserva_el_precio(ajustes):
    lectura = clasificar(hacer_producto("gameplanet_agotado"), ajustes, respuesta("gameplanet_agotado"), FECHA)
    assert lectura.estado is Estado.AGOTADO
    assert lectura.precio == 999_999


def test_vendedor_tercero_no_cuenta_como_ok(ajustes):
    lectura = clasificar(hacer_producto("sears_tercero_sin_stock"), ajustes, respuesta("sears_tercero_sin_stock"), FECHA)
    assert lectura.estado is Estado.TERCERO
    assert lectura.motivo == "vendido por Celcom H"
    assert lectura.precio == 979_900


def test_tercero_permitido_por_producto_sigue_las_demas_reglas(ajustes):
    producto = hacer_producto("sears_tercero_sin_stock", permitir_terceros=True)
    assert clasificar(producto, ajustes, respuesta("sears_tercero_sin_stock"), FECHA).estado is Estado.AGOTADO


@pytest.mark.parametrize(("status", "estado"), [(404, Estado.NO_ENCONTRADO), (410, Estado.NO_ENCONTRADO),
                                                (403, Estado.BLOQUEADO), (429, Estado.BLOQUEADO),
                                                (500, Estado.ERROR), (301, Estado.ERROR)])
def test_status_http(ajustes, status, estado):
    lectura = clasificar(hacer_producto(), ajustes, respuesta("walmart_vende_walmart", status=status), FECHA)
    assert lectura.estado is estado
    assert str(status) in lectura.motivo


def test_404_pide_url_nueva(ajustes):
    lectura = clasificar(hacer_producto(), ajustes, respuesta("walmart_vende_walmart", status=404), FECHA)
    assert "necesita URL nueva" in lectura.motivo


def test_redireccion_a_la_portada_es_bloqueo(ajustes):
    """Así respondía Coppel: 302 a "/" con cookies de Akamai Bot Manager."""
    r = respuesta("walmart_vende_walmart", url_final="https://www.walmart.com.mx/")
    lectura = clasificar(hacer_producto(), ajustes, r, FECHA)
    assert lectura.estado is Estado.BLOQUEADO
    assert lectura.motivo == "redirigido a la portada"


def test_redireccion_fuera_de_la_tienda_es_error(ajustes):
    r = respuesta("walmart_vende_walmart", url_final="https://captcha.ejemplo.com/reto")
    lectura = clasificar(hacer_producto(), ajustes, r, FECHA)
    assert lectura.estado is Estado.ERROR
    assert "fuera de la tienda" in lectura.motivo


def test_error_de_red(ajustes):
    lectura = clasificar(hacer_producto(), ajustes, ErrorDescarga("red: ReadTimeout"), FECHA)
    assert (lectura.estado, lectura.motivo, lectura.precio) == (Estado.ERROR, "red: ReadTimeout", None)


def test_pagina_irreconocible_es_error_de_extraccion(ajustes):
    r = Respuesta(200, URLS["walmart_vende_walmart"], "<html><title>Access Denied</title></html>")
    lectura = clasificar(hacer_producto(), ajustes, r, FECHA)
    assert lectura.estado is Estado.ERROR
    assert lectura.motivo.startswith("extracción:")


def test_precio_fuera_de_rango_es_error_y_se_guarda_para_diagnostico(ajustes):
    """Protege contra tomar la mensualidad MSI (~$1,000) por el precio."""
    angosto = type(ajustes)(lecturas_minimas=3, precio_min_valido=1_100_000, precio_max_valido=2_500_000)
    lectura = clasificar(hacer_producto(), angosto, respuesta("walmart_vende_walmart"), FECHA)
    assert lectura.estado is Estado.ERROR
    assert lectura.motivo == "precio $10,790.00 fuera de rango $11,000.00–$25,000.00"
    assert lectura.precio == 1_079_000
