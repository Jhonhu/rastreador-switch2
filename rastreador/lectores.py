"""Lectores de los formatos de datos que las tiendas embeben en su HTML.

No saben nada de tiendas concretas: solo de formatos (JSON-LD, __NEXT_DATA__,
stream RSC de Next.js). Todos los números con decimales se leen como Decimal.
"""

import json
from collections.abc import Callable, Iterator
from decimal import Decimal
from typing import Any

from bs4 import BeautifulSoup

PREFIJO_RSC = "self.__next_f.push("


class ErrorExtraccion(Exception):
    """El HTML no contiene el dato esperado (la tienda cambió o no es la página correcta)."""


def analizar_html(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "html.parser")


def cargar_json(texto: str) -> Any:
    """json.loads, pero con decimales exactos: 12879.08 -> Decimal('12879.08')."""
    return json.loads(texto, parse_float=Decimal)


# ------------------------------------------------------------------ JSON-LD
def json_ld_productos(sopa: BeautifulSoup) -> list[dict]:
    """Todos los nodos schema.org/Product de los <script type="application/ld+json">."""
    productos = []
    for script in sopa.find_all("script", type="application/ld+json"):
        try:
            dato = cargar_json(script.string or "")
        except ValueError:
            continue  # Sears publica JSON-LD inválido; un bloque roto no invalida los demás
        productos.extend(n for n in _nodos_ld(dato) if _es_tipo(n, "Product"))
    return productos


def _nodos_ld(dato: Any) -> list[dict]:
    if isinstance(dato, list):
        return [n for n in dato if isinstance(n, dict)]
    if isinstance(dato, dict) and isinstance(dato.get("@graph"), list):
        return [n for n in dato["@graph"] if isinstance(n, dict)]
    return [dato] if isinstance(dato, dict) else []


def _es_tipo(nodo: dict, tipo: str) -> bool:
    valor = nodo.get("@type")
    return valor == tipo or (isinstance(valor, list) and tipo in valor)


# ------------------------------------------------------------------ __NEXT_DATA__
def next_data(sopa: BeautifulSoup) -> Any:
    """El JSON de <script id="__NEXT_DATA__"> (Next.js con Pages Router)."""
    script = sopa.find("script", id="__NEXT_DATA__")
    if script is None or not script.string:
        raise ErrorExtraccion("sin __NEXT_DATA__")
    try:
        return cargar_json(script.string)
    except ValueError:
        raise ErrorExtraccion("__NEXT_DATA__ no es JSON válido") from None


# ------------------------------------------------------------------ stream RSC
def flujo_rsc(sopa: BeautifulSoup) -> list[Any]:
    """Valores JSON del stream "React Server Components" (Next.js App Router).

    La página no trae un JSON único: trae muchos
    <script>self.__next_f.push([1, "trozo"])</script>. Concatenados forman
    líneas "id:valor"; un trozo puede cortar una línea a la mitad, por eso
    primero se unen y luego se parte por saltos de línea.
    """
    trozos = []
    for script in sopa.find_all("script"):
        codigo = (script.string or "").strip()
        if not codigo.startswith(PREFIJO_RSC):
            continue
        argumento = codigo.removeprefix(PREFIJO_RSC).rstrip(";").removesuffix(")")
        try:
            dato = json.loads(argumento)
        except ValueError:
            continue
        if isinstance(dato, list) and len(dato) == 2 and dato[0] == 1 and isinstance(dato[1], str):
            trozos.append(dato[1])
    if not trozos:
        raise ErrorExtraccion("sin datos RSC (self.__next_f)")

    valores = []
    for linea in "".join(trozos).split("\n"):
        _id, separador, cuerpo = linea.partition(":")
        if separador and cuerpo[:1] in ("{", "["):
            try:
                valores.append(cargar_json(cuerpo))
            except ValueError:
                continue  # trozos de texto u otros formatos del stream: no son datos
    return valores


# ------------------------------------------------------------------ navegación
def buscar_dicts(raiz: Any, predicado: Callable[[dict], bool]) -> Iterator[dict]:
    """Recorre (en orden de documento) todos los dict anidados que cumplen `predicado`."""
    pendientes = [raiz]
    while pendientes:
        nodo = pendientes.pop()
        if isinstance(nodo, dict):
            if predicado(nodo):
                yield nodo
            pendientes.extend(reversed(list(nodo.values())))
        elif isinstance(nodo, list):
            pendientes.extend(reversed(nodo))


def ruta(dato: Any, *claves: str | int) -> Any:
    """dato[c1][c2]... con un error legible que dice qué parte faltó."""
    actual = dato
    for i, clave in enumerate(claves):
        try:
            actual = actual[clave]
        except (KeyError, IndexError, TypeError):
            recorrido = ".".join(str(c) for c in claves[: i + 1])
            raise ErrorExtraccion(f"falta {recorrido}") from None
    return actual
