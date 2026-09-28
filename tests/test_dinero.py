from decimal import Decimal

import pytest

from rastreador.dinero import a_centavos, formatear_pesos


@pytest.mark.parametrize(
    ("pesos", "centavos"),
    [
        (13999, 1_399_900),
        (Decimal("12879.08"), 1_287_908),
        ("10999.99", 1_099_999),
        (" 9500 ", 950_000),
        (999.5, 99_950),  # YAML entrega floats; se convierten por su texto, sin error binario
        (0.1, 10),
        (Decimal("0.005"), 1),  # redondeo comercial (mitad hacia arriba), no "del banquero"
        (Decimal("1.004"), 100),
        (0, 0),
    ],
)
def test_convierte_pesos_a_centavos_exactos(pesos, centavos):
    assert a_centavos(pesos) == centavos


@pytest.mark.parametrize("malo", [True, None, [1], {"a": 1}])
def test_rechaza_tipos_que_no_son_importes(malo):
    with pytest.raises(TypeError):
        a_centavos(malo)


@pytest.mark.parametrize("malo", ["abc", "", "-1", Decimal("NaN"), Decimal("Infinity"), -5])
def test_rechaza_valores_invalidos(malo):
    with pytest.raises(ValueError):
        a_centavos(malo)


@pytest.mark.parametrize(
    ("centavos", "texto"),
    [(1_287_908, "$12,879.08"), (5, "$0.05"), (0, "$0.00"), (-150_000, "-$1,500.00")],
)
def test_formatea_pesos_mexicanos(centavos, texto):
    assert formatear_pesos(centavos) == texto
