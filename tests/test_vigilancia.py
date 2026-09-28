import pytest

from rastreador.descarga import ErrorDescarga, Respuesta
from rastreador.extractores import extraer_resultados_liverpool
from rastreador.modelos import Vigilancia
from rastreador.vigilancia import (
    cargar_vistos,
    coincide,
    guardar_vistos,
    marcar_vistos,
    redactar_hallazgos,
    revisar,
)

from .conftest import FECHA, leer_fixture

POKEMON = Vigilancia(id="liverpool-bundle-pokemon", tienda="liverpool",
                     busqueda="consola nintendo switch 2", requiere=("consola", "pokemon", "256"))
URL_BUSQUEDA = "https://www.liverpool.com.mx/tienda?s=consola+nintendo+switch+2"


def busqueda(html: str | None = None, status: int = 200, url_final: str = URL_BUSQUEDA) -> Respuesta:
    return Respuesta(status, url_final, leer_fixture("liverpool_busqueda") if html is None else html)


# ------------------------------------------------------------------ coincidencia
@pytest.mark.parametrize(("nombre", "esperado"), [
    ("Consola fija/portátil switch de 256 gb Nintendo pokémon", True),  # título real, sin "2"
    ("CONSOLA SWITCH 2 256GB POKEMON", True),
    ("Pokémon Legends: Z-A estándar para Nintendo Switch 2", False),  # juego suelto
    ("Consola Nintendo Switch 32 GB Pokémon Let's Go", False),  # Switch 1
    ("Funda para consola Nintendo Switch 2 de 256 gb Pokémon", True),  # límite conocido: accesorio con las 3 palabras
])
def test_coincide_sin_acentos_ni_mayusculas(nombre, esperado):
    assert coincide(nombre, POKEMON.requiere) is esperado


def test_resultados_reales_de_la_busqueda():
    resultados = extraer_resultados_liverpool(leer_fixture("liverpool_busqueda"))
    ids = [r.id for r in resultados]
    assert ids[:2] == ["1177646322", "1209428225"]
    assert len(ids) == len(set(ids))  # sin duplicados
    pokemon = next(r for r in resultados if r.id == "1186172911")
    assert pokemon.precio == 1_370_708


# ------------------------------------------------------------------ revisión
def test_encuentra_el_bundle_y_arma_su_enlace():
    revision = revisar(POKEMON, busqueda(), vistos=set())
    assert revision.fallo is None
    assert [h.resultado.id for h in revision.hallazgos] == ["1186172911"]
    assert revision.hallazgos[0].url == (
        "https://www.liverpool.com.mx/tienda/pdp/consola-fija-portatil-switch-de-256-gb-nintendo-pokemon/1186172911")


def test_un_sku_ya_avisado_no_se_repite():
    assert revisar(POKEMON, busqueda(), vistos={"1186172911"}).hallazgos == ()


def test_sin_coincidencias_no_hay_hallazgos_ni_fallo():
    sin_pokemon = leer_fixture("liverpool_busqueda").replace("pokémon", "genérica")
    revision = revisar(POKEMON, busqueda(sin_pokemon), vistos=set())
    assert (revision.hallazgos, revision.fallo) == ((), None)


@pytest.mark.parametrize(("resultado", "motivo"), [
    (ErrorDescarga("red: ReadTimeout"), "red: ReadTimeout"),
    (Respuesta(403, URL_BUSQUEDA, "Access Denied"), "HTTP 403"),
    (Respuesta(200, "https://www.liverpool.com.mx/blocked?x=1", ""), "redirigido fuera de la búsqueda (/blocked)"),
    (Respuesta(200, URL_BUSQUEDA, "<html>rediseño</html>"), "extracción: sin datos RSC (self.__next_f)"),
])
def test_una_busqueda_fallida_se_reporta(resultado, motivo):
    assert revisar(POKEMON, resultado, vistos=set()).fallo == motivo


# ------------------------------------------------------------------ estado y mensaje
def test_vistos_ida_y_vuelta(tmp_path):
    ruta = tmp_path / "data" / "vigilancias.json"
    assert cargar_vistos(ruta) == {}
    vistos: dict = {}
    marcar_vistos(vistos, revisar(POKEMON, busqueda(), set()).hallazgos, FECHA)
    guardar_vistos(ruta, vistos)
    assert cargar_vistos(ruta) == {"liverpool-bundle-pokemon": {"1186172911": "2026-09-28T14:17:03Z"}}
    assert b"\r\n" not in ruta.read_bytes()


def test_vistos_con_formato_roto_falla_en_voz_alta(tmp_path):
    ruta = tmp_path / "vigilancias.json"
    ruta.write_text('["no", "es", "un", "mapa"]', encoding="utf-8")
    with pytest.raises(ValueError, match="formato"):
        cargar_vistos(ruta)


def test_mensaje_del_hallazgo():
    texto = redactar_hallazgos(revisar(POKEMON, busqueda(), set()).hallazgos)
    assert 'Apareció en Liverpool (búsqueda "consola nintendo switch 2")' in texto
    assert "Consola fija/portátil switch de 256 gb Nintendo pokémon · SKU 1186172911 · $13,707.08" in texto
    assert "/tienda/pdp/consola-fija-portatil-switch-de-256-gb-nintendo-pokemon/1186172911" in texto
