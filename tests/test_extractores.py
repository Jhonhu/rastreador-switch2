"""Extractores contra fixtures REALES recortados (tests/fixtures, ver investigacion/)."""

import pytest

from rastreador.extractores import extraer_gameplanet, extraer_liverpool, extraer_sears, extraer_walmart
from rastreador.lectores import ErrorExtraccion
from rastreador.modelos import Extraccion

from .conftest import URLS, leer_fixture

CASOS = [
    ("liverpool_estandar", extraer_liverpool, Extraccion(1_287_908, 1_399_900, True, "Liverpool", True)),
    ("liverpool_bundle_sports", extraer_liverpool, Extraccion(1_352_308, 1_469_900, True, "Liverpool", True)),
    ("walmart_vende_walmart", extraer_walmart, Extraccion(1_079_000, 1_399_900, True, "Walmart", True)),
    ("walmart_tercero_agotado", extraer_walmart, Extraccion(1_389_900, None, False, "GRUPO DECME.", False)),
    ("gameplanet_en_stock", extraer_gameplanet, Extraccion(1_099_999, None, True, "Gameplanet", True)),
    ("gameplanet_agotado", extraer_gameplanet, Extraccion(999_999, None, False, "Gameplanet", True)),
    ("sears_vende_sears", extraer_sears, Extraccion(1_399_900, 1_399_900, True, "SEARS", True)),
    ("sears_tercero_sin_stock", extraer_sears, Extraccion(979_900, 1_349_900, False, "Celcom H", False)),
]


@pytest.mark.parametrize(("fixture", "extraer", "esperado"), CASOS, ids=[c[0] for c in CASOS])
def test_extrae_datos_reales(fixture, extraer, esperado):
    assert extraer(leer_fixture(fixture), URLS[fixture]) == esperado


def test_liverpool_se_ancla_al_id_y_no_al_producto_recomendado():
    html = leer_fixture("liverpool_estandar")
    # El fixture trae primero un producto recomendado real (1208187232, $15,249).
    assert "1208187232" in html
    assert extraer_liverpool(html, URLS["liverpool_estandar"]).precio == 1_287_908


def test_liverpool_con_id_que_no_esta_en_la_pagina_es_error():
    url_ajena = URLS["liverpool_estandar"].replace("1177646322", "1111111111")
    with pytest.raises(ErrorExtraccion, match="1111111111"):
        extraer_liverpool(leer_fixture("liverpool_estandar"), url_ajena)


def test_liverpool_con_ofertas_de_marketplace_no_es_vendedor_oficial():
    html = leer_fixture("liverpool_estandar").replace(
        '\\"offersListVariants\\":\\"$undefined\\"', '\\"offersListVariants\\":\\"$4f\\"'
    )
    resultado = extraer_liverpool(html, URLS["liverpool_estandar"])
    assert resultado.vendedor_oficial is False
    assert resultado.vendedor is None


def test_walmart_detecta_pagina_de_otro_articulo():
    url_ajena = URLS["walmart_vende_walmart"].replace("00004549688581", "00000000000001")
    with pytest.raises(ErrorExtraccion, match="00004549688581"):
        extraer_walmart(leer_fixture("walmart_vende_walmart"), url_ajena)


def test_sears_detecta_pagina_de_otro_producto():
    url_ajena = URLS["sears_vende_sears"].replace("3522519", "9999999")
    with pytest.raises(ErrorExtraccion, match="3522519"):
        extraer_sears(leer_fixture("sears_vende_sears"), url_ajena)


@pytest.mark.parametrize("extraer", [extraer_liverpool, extraer_walmart, extraer_gameplanet, extraer_sears])
def test_pagina_sin_datos_es_error_de_extraccion(extraer):
    """Una página de bloqueo o un rediseño debe dar ErrorExtraccion, nunca un precio inventado."""
    pagina_bloqueo = "<html><head><title>Access Denied</title></head><body>Reference #18</body></html>"
    with pytest.raises(ErrorExtraccion):
        extraer(pagina_bloqueo, "https://www.sears.com.mx/producto/1/x")
