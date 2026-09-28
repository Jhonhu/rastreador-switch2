from datetime import timedelta

import pytest

from rastreador.alertas import LIMITE_MENSAJE, TipoAlerta, evaluar, redactar_mensaje
from rastreador.modelos import Ajustes, Estado, Lectura

from .conftest import FECHA, hacer_producto

AJUSTES = Ajustes(lecturas_minimas=3, precio_min_valido=500_000, precio_max_valido=2_500_000, precio_objetivo=1_000_000)
PRODUCTO = hacer_producto("walmart_vende_walmart", id="walmart-estandar")


def pesos(*precios_en_pesos, estado=Estado.OK, desde=0, producto_id="walmart-estandar") -> list[Lectura]:
    """Una lectura diaria por precio (None = lectura sin precio)."""
    return [
        Lectura(fecha=FECHA + timedelta(days=desde + i), producto_id=producto_id, tienda="walmart",
                estado=estado, precio=None if p is None else p * 100)
        for i, p in enumerate(precios_en_pesos)
    ]


def nueva(precio_en_pesos: int, estado=Estado.OK) -> Lectura:
    return pesos(precio_en_pesos, estado=estado, desde=100)[0]


def tipos(alertas) -> list[TipoAlerta]:
    return [a.tipo for a in alertas]


# ------------------------------------------------------------------ mínimo histórico
def test_nuevo_minimo_con_suficientes_lecturas_previas():
    alertas = evaluar(PRODUCTO, AJUSTES, pesos(10_900, 10_800, 10_790), nueva(10_500))
    assert tipos(alertas) == [TipoAlerta.MINIMO_HISTORICO]
    assert alertas[0].referencia == 1_079_000
    assert alertas[0].precio_efectivo == 1_050_000


def test_sin_suficientes_lecturas_la_primera_no_alerta():
    assert evaluar(PRODUCTO, AJUSTES, pesos(10_900, 10_800), nueva(10_500)) == []


def test_empatar_el_minimo_no_es_nuevo_minimo():
    assert evaluar(PRODUCTO, AJUSTES, pesos(10_900, 10_800, 10_790), nueva(10_790)) == []


def test_solo_cuentan_lecturas_ok_del_mismo_producto():
    ruido = (
        pesos(9_000, 9_000, 9_000, estado=Estado.TERCERO)  # tercero más barato: no cuenta
        + pesos(8_000, estado=Estado.AGOTADO)
        + pesos(None, None, estado=Estado.ERROR)
        + pesos(7_000, 7_000, 7_000, producto_id="otro-producto")
    )
    assert evaluar(PRODUCTO, AJUSTES, ruido + pesos(10_900, 10_800), nueva(10_500)) == []  # solo 2 válidas
    assert tipos(evaluar(PRODUCTO, AJUSTES, ruido + pesos(10_900, 10_800, 10_790), nueva(10_500))) == [
        TipoAlerta.MINIMO_HISTORICO
    ]


def test_lecturas_minimas_cero_sigue_necesitando_algo_con_que_comparar():
    sin_minimo = Ajustes(lecturas_minimas=0, precio_min_valido=1, precio_max_valido=10**9)
    assert evaluar(PRODUCTO, sin_minimo, [], nueva(10_500)) == []
    assert tipos(evaluar(PRODUCTO, sin_minimo, pesos(10_900), nueva(10_500))) == [TipoAlerta.MINIMO_HISTORICO]


def test_lectura_que_no_es_ok_nunca_alerta():
    for estado in (Estado.AGOTADO, Estado.TERCERO, Estado.ERROR):
        assert evaluar(PRODUCTO, AJUSTES, pesos(10_900, 10_800, 10_790), nueva(5_000, estado)) == []


def test_el_minimo_usa_precio_efectivo_con_la_valoracion_actual():
    bundle = hacer_producto("walmart_vende_walmart", id="walmart-estandar", valor_extra=150_000)
    # Previos efectivos: 10,500 / 10,400 / 10,300. Nuevo: 11,700 − 1,500 = 10,200.
    alertas = evaluar(bundle, AJUSTES, pesos(12_000, 11_900, 11_800), nueva(11_700))
    assert tipos(alertas) == [TipoAlerta.MINIMO_HISTORICO]
    assert (alertas[0].precio, alertas[0].precio_efectivo, alertas[0].referencia) == (1_170_000, 1_020_000, 1_030_000)


# ------------------------------------------------------------------ cruce del objetivo
@pytest.mark.parametrize(
    ("historial", "precio", "alerta"),
    [
        ((10_500,), 9_900, True),  # venía de arriba y bajó
        ((10_500,), 10_000, True),  # alcanzar el objetivo exacto cuenta
        ((9_900,), 9_800, False),  # ya estaba abajo: no se repite
        ((9_900, 10_200), 9_950, True),  # subió y volvió a bajar: nuevo cruce
        ((), 9_900, True),  # primera lectura de la historia y ya está abajo
        ((10_500,), 10_001, False),  # sigue arriba
    ],
)
def test_cruce_hacia_abajo_del_objetivo(historial, precio, alerta):
    alertas = evaluar(PRODUCTO, AJUSTES, pesos(*historial), nueva(precio))
    assert (TipoAlerta.CRUCE_OBJETIVO in tipos(alertas)) is alerta


def test_un_dia_agotado_no_rompe_la_racha_bajo_el_objetivo():
    historial = pesos(9_900) + pesos(9_900, estado=Estado.AGOTADO, desde=1) + pesos(None, estado=Estado.ERROR, desde=2)
    assert evaluar(PRODUCTO, AJUSTES, historial, nueva(9_900)) == []


def test_objetivo_del_producto_tiene_prioridad_sobre_el_global():
    exigente = hacer_producto("walmart_vende_walmart", id="walmart-estandar", precio_objetivo=900_000)
    assert evaluar(exigente, AJUSTES, pesos(10_500), nueva(9_500)) == []
    assert tipos(evaluar(exigente, AJUSTES, pesos(10_500), nueva(8_900))) == [TipoAlerta.CRUCE_OBJETIVO]


def test_sin_objetivo_configurado_no_hay_alerta_de_cruce():
    sin_objetivo = Ajustes(lecturas_minimas=3, precio_min_valido=1, precio_max_valido=10**9)
    assert evaluar(PRODUCTO, sin_objetivo, pesos(10_500), nueva(1_000)) == []


def test_ambas_alertas_el_mismo_dia():
    alertas = evaluar(PRODUCTO, AJUSTES, pesos(10_900, 10_800, 10_790), nueva(9_900))
    assert tipos(alertas) == [TipoAlerta.MINIMO_HISTORICO, TipoAlerta.CRUCE_OBJETIVO]


# ------------------------------------------------------------------ mensaje
def test_mensaje_legible_con_extra_y_enlace():
    bundle = hacer_producto("walmart_vende_walmart", id="walmart-estandar", valor_extra=150_000, descripcion="Switch 2 + juego")
    alertas = evaluar(bundle, AJUSTES, pesos(12_000, 11_900, 11_800), nueva(11_400))
    texto = redactar_mensaje(alertas)
    assert "Nuevo mínimo histórico (antes $10,300.00)" in texto
    assert "Bajó del objetivo de $10,000.00" in texto
    assert "Walmart · Switch 2 + juego" in texto
    assert "Precio efectivo: $9,900.00 (cobra $11,400.00 − extra $1,500.00)" in texto
    assert bundle.url in texto


def test_mensaje_no_excede_el_limite_de_telegram():
    alertas = evaluar(PRODUCTO, AJUSTES, pesos(10_900, 10_800, 10_790), nueva(9_900)) * 200
    assert len(redactar_mensaje(alertas)) <= LIMITE_MENSAJE


# ------------------------------------------------------------------ baja mínima (anti-spam)
CON_UMBRAL = Ajustes(lecturas_minimas=3, precio_min_valido=500_000, precio_max_valido=2_500_000, baja_minima_alerta=20_000)


@pytest.mark.parametrize(("precio", "alerta"), [(10_590, True), (10_591, False), (10_789, False), (9_000, True)])
def test_nuevo_minimo_exige_la_baja_minima(precio, alerta):
    alertas = evaluar(PRODUCTO, CON_UMBRAL, pesos(10_900, 10_800, 10_790), nueva(precio))
    assert (TipoAlerta.MINIMO_HISTORICO in tipos(alertas)) is alerta


def test_la_baja_minima_no_afecta_el_cruce_del_objetivo():
    umbral_y_objetivo = Ajustes(lecturas_minimas=3, precio_min_valido=1, precio_max_valido=10**9,
                                precio_objetivo=1_000_000, baja_minima_alerta=20_000)
    alertas = evaluar(PRODUCTO, umbral_y_objetivo, pesos(10_100, 10_050, 10_020), nueva(9_990))
    assert tipos(alertas) == [TipoAlerta.CRUCE_OBJETIVO]
