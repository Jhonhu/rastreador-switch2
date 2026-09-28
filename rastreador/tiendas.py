"""Registro de tiendas soportadas: dominios permitidos, forma de la URL y extractor.

Agregar una tienda = investigarla (investigacion/), escribir su extractor con
fixtures y registrarla aquí. Coppel quedó fuera: bloquea con Akamai Bot Manager.
"""

import re
from collections.abc import Callable
from dataclasses import dataclass

from .extractores import extraer_gameplanet, extraer_liverpool, extraer_sears, extraer_walmart
from .modelos import Extraccion


@dataclass(frozen=True, slots=True)
class Tienda:
    nombre: str
    dominios: frozenset[str]  # coincidencia EXACTA del host (nada de "termina en")
    patron_ruta: re.Pattern[str]  # la ruta de la URL debe ser una página de producto
    extraer: Callable[[str, str], Extraccion]


TIENDAS: dict[str, Tienda] = {
    t.nombre: t
    for t in (
        Tienda(
            nombre="liverpool",
            dominios=frozenset({"www.liverpool.com.mx"}),
            patron_ruta=re.compile(r"/tienda/pdp/[^/]+/\d+"),
            extraer=extraer_liverpool,
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
