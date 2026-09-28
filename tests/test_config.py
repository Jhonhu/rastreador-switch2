from pathlib import Path

import pytest
import yaml

from rastreador.config import ErrorConfiguracion, cargar_configuracion, interpretar_configuracion
from rastreador.modelos import Version

RAIZ = Path(__file__).parent.parent

AJUSTES = """
ajustes:
  lecturas_minimas: 3
  precio_min_valido: 5000
  precio_max_valido: 25000
  precio_objetivo: 9500
"""


def config_con(producto_yaml: str, ajustes: str = AJUSTES) -> str:
    return ajustes + "productos:\n" + producto_yaml


PRODUCTO_VALIDO = """
  - id: sears-mk
    tienda: sears
    version: nacional
    descripcion: Switch 2 + MK
    url: https://www.sears.com.mx/producto/3522625/consola-nintendo-switch-2-mario-kart-world
    valor_extra: 1500.50
"""


def errores_de(texto: str) -> list[str]:
    with pytest.raises(ErrorConfiguracion) as info:
        interpretar_configuracion(texto)
    return info.value.errores


def test_el_productos_yaml_del_repo_es_valido():
    config = cargar_configuracion(RAIZ / "productos.yaml")
    assert len(config.productos) >= 4
    assert {p.tienda for p in config.productos} == {"liverpool", "walmart", "gameplanet", "sears"}


def test_convierte_pesos_a_centavos_y_aplica_valores_por_omision():
    config = interpretar_configuracion(config_con(PRODUCTO_VALIDO))
    assert config.ajustes.precio_min_valido == 500_000
    assert config.ajustes.precio_objetivo == 950_000
    assert config.ajustes.baja_minima_alerta == 0  # por omisión: cualquier baja
    producto = config.productos[0]
    assert producto.valor_extra == 150_050
    assert producto.version is Version.NACIONAL
    assert producto.permitir_terceros is False
    assert producto.precio_objetivo is None
    assert producto.precio_efectivo(1_524_900) == 1_374_850


@pytest.mark.parametrize(
    ("url", "fragmento_error"),
    [
        ("http://www.sears.com.mx/producto/3522625/x", "https"),
        ("https://www.liverpool.com.mx/tienda/pdp/x/1177646322", "no es de sears"),
        ("https://sears.com.mx.evil.com/producto/3522625/x", "no es de sears"),
        ("https://evil.com/producto/3522625/x?www.sears.com.mx", "no es de sears"),
        ("https://www.sears.com.mx@evil.com/producto/3522625/x", "usuario"),
        ("https://www.sears.com.mx:8443/producto/3522625/x", "puerto"),
        ("https://www.sears.com.mx/resultados/switch", "no parece una página de producto"),
        ("https://www.sears.com.mx/producto/3522625/x y", "espacios"),
    ],
)
def test_rechaza_urls_que_no_son_de_la_tienda(url, fragmento_error):
    producto = PRODUCTO_VALIDO.replace(
        "https://www.sears.com.mx/producto/3522625/consola-nintendo-switch-2-mario-kart-world", url
    )
    errores = errores_de(config_con(producto))
    assert any(fragmento_error in e for e in errores), errores


def test_junta_todos_los_errores_de_una_vez():
    producto_malo = """
  - id: Con Mayúsculas
    tienda: coppel
    version: pirata
    descripcion: ""
    url: https://www.coppel.com/pdp/x
    valor_extra: -1
    permitir_terceros: "sí"
    precio_obejtivo: 9000
"""
    errores = errores_de(config_con(producto_malo))
    textos = "\n".join(errores)
    for esperado in ["id debe", "tienda desconocida 'coppel'", "version debe", "descripcion", "negativo",
                     "permitir_terceros", "clave desconocida 'precio_obejtivo'"]:
        assert esperado in textos


def test_rechaza_ids_y_urls_repetidos():
    errores = errores_de(config_con(PRODUCTO_VALIDO + PRODUCTO_VALIDO))
    assert any("id repetido" in e for e in errores)
    assert any("url repetido" in e for e in errores)


@pytest.mark.parametrize(
    ("ajustes", "fragmento_error"),
    [
        (AJUSTES.replace("precio_min_valido: 5000", "precio_min_valido: 30000"), "menor que"),
        (AJUSTES.replace("lecturas_minimas: 3", "lecturas_minimas: -1"), "lecturas_minimas"),
        (AJUSTES.replace("lecturas_minimas: 3", "lecturas_minimas: true"), "lecturas_minimas"),
        (AJUSTES.replace("precio_objetivo: 9500", "precio_objetivo: yes"), "número en pesos"),
        (AJUSTES.replace("  precio_max_valido: 25000\n", ""), "falta ajustes.precio_max_valido"),
        ("", "falta la sección 'ajustes'"),
        (AJUSTES + "  baja_minima_alerta: -5\n", "negativo"),
    ],
)
def test_valida_los_ajustes(ajustes, fragmento_error):
    errores = errores_de(config_con(PRODUCTO_VALIDO, ajustes))
    assert any(fragmento_error in e for e in errores), errores


def test_usa_safe_load_y_no_construye_objetos_python():
    """Con yaml.load (inseguro) esta etiqueta ejecutaría os.system al cargar."""
    malicioso = config_con(PRODUCTO_VALIDO) + '\nextra: !!python/object/apply:os.system ["echo pwned"]\n'
    errores = errores_de(malicioso)
    assert any("YAML inválido" in e for e in errores)


def test_yaml_que_no_es_un_mapa():
    assert errores_de("- solo\n- una lista\n") == ["el archivo debe ser un mapa con 'ajustes' y 'productos'"]


def test_safe_load_realmente_rechaza_la_etiqueta():
    # Sanidad de la prueba anterior: el error viene de safe_load, no de otra cosa.
    with pytest.raises(yaml.constructor.ConstructorError):
        yaml.safe_load('!!python/object/apply:os.system ["echo"]')


VIGILANCIA_VALIDA = """
vigilancias:
  - id: liverpool-bundle-pokemon
    tienda: liverpool
    busqueda: consola nintendo switch 2
    requiere: [consola, pokemon, "256"]
"""


def test_vigilancia_valida():
    config = interpretar_configuracion(config_con(PRODUCTO_VALIDO) + VIGILANCIA_VALIDA)
    (v,) = config.vigilancias
    assert (v.id, v.tienda, v.busqueda, v.requiere) == (
        "liverpool-bundle-pokemon", "liverpool", "consola nintendo switch 2", ("consola", "pokemon", "256"))


def test_sin_vigilancias_es_valido():
    assert interpretar_configuracion(config_con(PRODUCTO_VALIDO)).vigilancias == ()


@pytest.mark.parametrize(("cambio", "fragmento"), [
    (("tienda: liverpool", "tienda: walmart"), "no admite vigilancias"),
    (('requiere: [consola, pokemon, "256"]', "requiere: []"), "requiere"),
    (('requiere: [consola, pokemon, "256"]', "requiere: consola"), "requiere"),
    (("busqueda: consola nintendo switch 2", "busqueda: ''"), "busqueda"),
    (("    busqueda:", "    buscar: x\n    busqueda:"), "clave desconocida 'buscar'"),
])
def test_valida_las_vigilancias(cambio, fragmento):
    errores = errores_de(config_con(PRODUCTO_VALIDO) + VIGILANCIA_VALIDA.replace(*cambio))
    assert any(fragmento in e for e in errores), errores
