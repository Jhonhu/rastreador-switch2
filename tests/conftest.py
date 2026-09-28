from datetime import UTC, datetime
from pathlib import Path

import pytest

from rastreador.modelos import Ajustes, Producto, Version

FIXTURES = Path(__file__).parent / "fixtures"
FECHA = datetime(2026, 9, 28, 14, 17, 3, tzinfo=UTC)

# URL de origen de cada fixture (también anotada en el comentario del HTML).
URLS = {
    "liverpool_estandar": "https://www.liverpool.com.mx/tienda/pdp/consola-nintendo-switch-2-de-256-gb-edicion-estandar/1177646322",
    "liverpool_bundle_sports": "https://www.liverpool.com.mx/tienda/pdp/consola-fija-portatil-switch-2-de-256-gb-edicion-bundle-sports-resort/1209428225",
    "walmart_vende_walmart": "https://www.walmart.com.mx/ip/consola-nintendo-switch-2-256-gb/00004549688581",
    "walmart_tercero_agotado": "https://www.walmart.com.mx/ip/consola-nintendo-switch-2-256gb-joy-con-2-lcd-7-9-internacional/00070452118393",
    "gameplanet_en_stock": "https://gameplanet.com/producto/consola-nintendo-switch-2-con-adaptador-nsw2/",
    "gameplanet_agotado": "https://gameplanet.com/producto/consola-nintendo-switch-2-elige-tu-paquete-de-juego-nsw2/",
    "sears_vende_sears": "https://www.sears.com.mx/producto/3522519/consola-nintendo-switch-2",
    "sears_tercero_sin_stock": "https://www.sears.com.mx/producto/3578083/consola-nintendo-switch-2-256gb",
}


def leer_fixture(nombre: str) -> str:
    return (FIXTURES / f"{nombre}.html").read_text(encoding="utf-8")


def hacer_producto(fixture: str = "walmart_vende_walmart", **cambios) -> Producto:
    datos = {
        "id": "prueba",
        "tienda": fixture.split("_")[0],
        "url": URLS[fixture],
        "version": Version.NACIONAL,
        "descripcion": "producto de prueba",
    } | cambios
    return Producto(**datos)


@pytest.fixture
def ajustes() -> Ajustes:
    return Ajustes(lecturas_minimas=3, precio_min_valido=500_000, precio_max_valido=2_500_000, precio_objetivo=950_000)
