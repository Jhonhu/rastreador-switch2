import json
from decimal import Decimal

import pytest

from rastreador.lectores import (
    ErrorExtraccion,
    analizar_html,
    buscar_dicts,
    flujo_rsc,
    json_ld_productos,
    next_data,
    ruta,
)


def _push(trozo: str) -> str:
    return f"<script>self.__next_f.push({json.dumps([1, trozo])})</script>"


def test_json_ld_encuentra_product_en_graph_y_listas():
    html = """
    <script type="application/ld+json">{"@graph": [{"@type": "BreadcrumbList"}, {"@type": "Product", "name": "A"}]}</script>
    <script type="application/ld+json">[{"@type": ["Product", "Thing"], "name": "B"}]</script>
    """
    assert [p["name"] for p in json_ld_productos(analizar_html(html))] == ["A", "B"]


def test_json_ld_invalido_se_ignora_sin_romper_los_demas():
    html = """
    <script type="application/ld+json">{"@type": "Product", "name": "roto\u0001}</script>
    <script type="application/ld+json">{"@type": "Product", "name": "bueno", "offers": {"price": 10.5}}</script>
    """
    productos = json_ld_productos(analizar_html(html))
    assert [p["name"] for p in productos] == ["bueno"]
    assert productos[0]["offers"]["price"] == Decimal("10.5")  # decimales exactos, nunca float


def test_next_data_ausente_es_error_de_extraccion():
    with pytest.raises(ErrorExtraccion, match="__NEXT_DATA__"):
        next_data(analizar_html("<html></html>"))


def test_flujo_rsc_une_trozos_que_cortan_una_linea_a_la_mitad():
    linea = 'a:{"producto": {"precio": 12879.08}}\n'
    html = (
        "<script>(self.__next_f=self.__next_f||[]).push([0])</script>"
        + _push("0:texto que no es json\n" + linea[:10])
        + _push(linea[10:] + "b:T12,texto plano\n")
    )
    assert flujo_rsc(analizar_html(html)) == [{"producto": {"precio": Decimal("12879.08")}}]


def test_flujo_rsc_ausente_es_error_de_extraccion():
    with pytest.raises(ErrorExtraccion, match="RSC"):
        flujo_rsc(analizar_html("<script>console.log(1)</script>"))


def test_buscar_dicts_recorre_en_orden_de_documento():
    datos = {"a": [{"id": 1, "hijo": {"id": 2}}, {"id": 3}], "b": {"id": 4}}
    assert [d["id"] for d in buscar_dicts(datos, lambda d: "id" in d)] == [1, 2, 3, 4]


def test_ruta_dice_que_parte_falta():
    with pytest.raises(ErrorExtraccion, match="falta props.pageProps"):
        ruta({"props": {}}, "props", "pageProps", "data")
