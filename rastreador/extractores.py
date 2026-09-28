"""Un extractor por tienda: (html, url) -> Extraccion. No tocan la red.

De dónde sale cada dato está documentado en investigacion/HALLAZGOS.md.
Si algo no está donde se espera, lanzan ErrorExtraccion con el motivo.
"""

from decimal import Decimal
from typing import Any
from urllib.parse import urlsplit

from .dinero import a_centavos
from .lectores import (
    ErrorExtraccion,
    analizar_html,
    buscar_dicts,
    flujo_rsc,
    json_ld_productos,
    next_data,
    ruta,
)
from .modelos import Extraccion, ResultadoBusqueda

# Valores de schema.org/availability que significan "se puede comprar".
DISPONIBLE_SCHEMA = {"InStock", "LimitedAvailability", "OnlineOnly", "PreOrder", "PreSale"}

# En el stream RSC, "$undefined" es el `undefined` de JavaScript.
RSC_INDEFINIDO = "$undefined"


# ------------------------------------------------------------------ auxiliares
def _segmentos(url: str) -> list[str]:
    return [s for s in urlsplit(url).path.split("/") if s]


def _importe(valor: Any, campo: str) -> int:
    if not isinstance(valor, (int, str, Decimal)) or isinstance(valor, bool):
        raise ErrorExtraccion(f"{campo} no es un importe: {valor!r}")
    try:
        return a_centavos(valor)
    except ValueError as exc:
        raise ErrorExtraccion(f"{campo}: {exc}") from None


def _importe_opcional(valor: Any, campo: str) -> int | None:
    return None if valor is None else _importe(valor, campo)


def _primero(*valores: Any) -> Any:
    return next((v for v in valores if v is not None), None)


def _oferta_ld(producto: dict) -> dict:
    ofertas = producto.get("offers")
    oferta = ofertas[0] if isinstance(ofertas, list) and ofertas else ofertas
    if not isinstance(oferta, dict):
        raise ErrorExtraccion("JSON-LD Product sin offers")
    return oferta


def _disponible_schema(valor: Any) -> bool:
    if not isinstance(valor, str):
        raise ErrorExtraccion("JSON-LD sin availability")
    return valor.rstrip("/").rsplit("/", 1)[-1] in DISPONIBLE_SCHEMA


def _unico_producto_ld(html_analizado) -> dict:
    productos = json_ld_productos(html_analizado)
    if not productos:
        raise ErrorExtraccion("sin JSON-LD Product")
    return productos[0]


# ------------------------------------------------------------------ Liverpool
def extraer_liverpool(html: str, url: str) -> Extraccion:
    """Next.js App Router: stream RSC -> product.productInfo cuyo productId es el de la URL.

    La página también trae productos recomendados con precio: por eso se ancla
    al id y nunca se toma "el primer precio que aparezca".
    """
    sku = _segmentos(url)[-1]

    def es_el_producto(nodo: dict) -> bool:
        info = nodo.get("productInfo")
        return isinstance(info, dict) and info.get("productId") == sku

    producto = next((p for valor in flujo_rsc(analizar_html(html)) for p in buscar_dicts(valor, es_el_producto)), None)
    if producto is None:
        raise ErrorExtraccion(f"sin productInfo del producto {sku}")

    info = producto["productInfo"]
    precios = ruta(info, "priceInfo")
    promo = precios.get("promoPrice") if isinstance(precios.get("promoPrice"), dict) else {}
    lista = precios.get("listPrice") if isinstance(precios.get("listPrice"), dict) else {}
    precio = _primero(promo.get("price"), precios.get("salePrice"))
    if precio is None:
        raise ErrorExtraccion("falta priceInfo.promoPrice.price y priceInfo.salePrice")

    disponible = info.get("inventoryStatus")
    if not isinstance(disponible, bool):
        raise ErrorExtraccion("falta productInfo.inventoryStatus")

    # Productos propios traen offersListVariants = "$undefined". Si trae algo
    # (una lista o una referencia "$xx"), hay ofertas de marketplace: no es Liverpool.
    marketplace = producto.get("offersListVariants") not in (None, RSC_INDEFINIDO)
    return Extraccion(
        precio=_importe(precio, "precio"),
        precio_lista=_importe_opcional(_primero(lista.get("price"), precios.get("salePrice")), "precio de lista"),
        disponible=disponible,
        vendedor=None if marketplace else "Liverpool",
        vendedor_oficial=not marketplace,
    )


def extraer_resultados_liverpool(html: str) -> list[ResultadoBusqueda]:
    """Tarjetas de la página de búsqueda (/tienda?s=...): mismo stream RSC, sin duplicados."""
    def es_tarjeta(nodo: dict) -> bool:
        return isinstance(nodo.get("productId"), str) and isinstance(nodo.get("title"), str) and isinstance(nodo.get("priceInfo"), dict)

    resultados: dict[str, ResultadoBusqueda] = {}
    for valor in flujo_rsc(analizar_html(html)):
        for tarjeta in buscar_dicts(valor, es_tarjeta):
            if tarjeta["productId"] in resultados:
                continue
            precios = tarjeta["priceInfo"]
            promo = precios.get("promoPrice")
            bruto = _primero(promo.get("price") if isinstance(promo, dict) else promo, precios.get("salePrice"))
            try:
                precio = _importe_opcional(bruto, "precio")
            except ErrorExtraccion:
                precio = None  # un precio raro en una tarjeta no invalida la búsqueda
            resultados[tarjeta["productId"]] = ResultadoBusqueda(tarjeta["productId"], tarjeta["title"], precio)
    return list(resultados.values())


# ------------------------------------------------------------------ Walmart
def extraer_walmart(html: str, url: str) -> Extraccion:
    """Precio y disponibilidad del JSON-LD; vendedor de __NEXT_DATA__ (es marketplace)."""
    sopa = analizar_html(html)
    oferta = _oferta_ld(_unico_producto_ld(sopa))
    producto = ruta(next_data(sopa), "props", "pageProps", "initialData", "data", "product")

    id_url = _segmentos(url)[-1]
    if producto.get("usItemId") not in (None, id_url):
        raise ErrorExtraccion(f"la página es del artículo {producto.get('usItemId')}, no {id_url}")

    precio_anterior = (producto.get("priceInfo") or {}).get("wasPrice") or {}
    return Extraccion(
        precio=_importe(oferta.get("price"), "precio"),
        precio_lista=_importe_opcional(precio_anterior.get("price"), "precio anterior"),
        disponible=_disponible_schema(oferta.get("availability")),
        vendedor=_primero(producto.get("sellerDisplayName"), producto.get("sellerName")),
        vendedor_oficial=producto.get("sellerType") == "INTERNAL",
    )


# ------------------------------------------------------------------ Gameplanet
def extraer_gameplanet(html: str, url: str) -> Extraccion:
    """WooCommerce: JSON-LD en @graph. Tienda de un solo vendedor."""
    oferta = _oferta_ld(_unico_producto_ld(analizar_html(html)))
    vendedor = (oferta.get("seller") or {}).get("name") or "Gameplanet"
    return Extraccion(
        precio=_importe(oferta.get("price"), "precio"),
        precio_lista=None,
        disponible=_disponible_schema(oferta.get("availability")),
        vendedor=vendedor,
        vendedor_oficial=vendedor == "Gameplanet",
    )


# ------------------------------------------------------------------ Sears
def extraer_sears(html: str, url: str) -> Extraccion:
    """__NEXT_DATA__ -> props.pageProps.response.data.

    Su JSON-LD NO se usa: a veces no parsea, dice InStock con stock 0 y
    declara el producto como usado.
    """
    datos = ruta(next_data(analizar_html(html)), "props", "pageProps", "response", "data")

    id_url = _segmentos(url)[1]  # /producto/<id>/<slug>
    if str(datos.get("id")) != id_url:
        raise ErrorExtraccion(f"la página es del producto {datos.get('id')}, no {id_url}")

    stock = ruta(datos, "stock")
    if not isinstance(stock, int) or isinstance(stock, bool):
        raise ErrorExtraccion(f"stock no es entero: {stock!r}")
    tienda = ruta(datos, "store", "name")
    return Extraccion(
        precio=_importe(ruta(datos, "sale_price"), "precio"),
        precio_lista=_importe_opcional(datos.get("price"), "precio de lista"),
        disponible=stock > 0 and datos.get("status") is True,
        vendedor=tienda,
        vendedor_oficial=isinstance(tienda, str) and tienda.strip().upper() == "SEARS",
    )
