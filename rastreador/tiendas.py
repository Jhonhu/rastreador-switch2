"""Registro de tiendas soportadas: dominios permitidos, forma de la URL y extractor.

Agregar una tienda = investigarla (investigacion/), escribir su extractor con
fixtures y registrarla aquí. Coppel quedó fuera: bloquea con Akamai Bot Manager.
"""

import re
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass
from urllib.parse import quote_plus

from .extractores import (
    extraer_gameplanet,
    extraer_liverpool,
    extraer_resultados_liverpool,
    extraer_sears,
    extraer_walmart,
)
from .modelos import Extraccion, ResultadoBusqueda


@dataclass(frozen=True, slots=True)
class Tienda:
    nombre: str
    dominios: frozenset[str]  # coincidencia EXACTA del host (nada de "termina en")
    patron_ruta: re.Pattern[str]  # la ruta de la URL debe ser una página de producto
    extraer: Callable[[str, str], Extraccion]
    # Opcional: solo las tiendas cuyo buscador se investigó admiten vigilancias.
    url_busqueda: Callable[[str], str] | None = None
    extraer_resultados: Callable[[str], list[ResultadoBusqueda]] | None = None
    url_producto: Callable[[ResultadoBusqueda], str] | None = None


def _slug(texto: str) -> str:
    sin_acentos = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", sin_acentos.lower()).strip("-") or "producto"


TIENDAS: dict[str, Tienda] = {
    t.nombre: t
    for t in (
        Tienda(
            nombre="liverpool",
            dominios=frozenset({"www.liverpool.com.mx"}),
            patron_ruta=re.compile(r"/tienda/pdp/[^/]+/\d+"),
            extraer=extraer_liverpool,
            url_busqueda=lambda consulta: f"https://www.liverpool.com.mx/tienda?s={quote_plus(consulta)}",
            extraer_resultados=extraer_resultados_liverpool,
            # Liverpool acepta cualquier slug: lo que identifica al producto es el id final.
            url_producto=lambda r: f"https://www.liverpool.com.mx/tienda/pdp/{_slug(r.nombre)}/{r.id}",
        ),
        Tienda(
            nombre="walmart",
            dominios=frozenset({"www.walmart.com.mx"}),
            patron_ruta=re.compile(r"/ip/[^/]+/\d+"),
            extraer=extraer_walmart,
        ),
        Tienda(
            nombre="gameplanet",
            dominios=frozenset({"gameplanet.com"}),
            patron_ruta=re.compile(r"/producto/[^/]+/?"),
            extraer=extraer_gameplanet,
        ),
        Tienda(
            nombre="sears",
            dominios=frozenset({"www.sears.com.mx"}),
            patron_ruta=re.compile(r"/producto/\d+(/[^/]+)?/?"),
            extraer=extraer_sears,
        ),
    )
}
