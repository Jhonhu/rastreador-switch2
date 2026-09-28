"""Convierte el resultado de una descarga en una Lectura con su Estado.

Aquí viven las reglas: 404 = URL caducada, 403/429 = bloqueo, cordura del
precio, vendedor tercero y disponibilidad. Función pura: sin red ni reloj.
"""

from datetime import datetime
from urllib.parse import urlsplit

from .descarga import ErrorDescarga, Respuesta
from .dinero import formatear_pesos
from .lectores import ErrorExtraccion
from .modelos import Ajustes, Estado, Lectura, Producto
from .tiendas import TIENDAS

STATUS_NO_ENCONTRADO = {404, 410}
STATUS_BLOQUEO = {401, 403, 429}


def clasificar(
    producto: Producto,
    ajustes: Ajustes,
    resultado: Respuesta | ErrorDescarga,
    fecha: datetime,
) -> Lectura:
    def lectura(estado: Estado, motivo: str = "", **datos) -> Lectura:
        return Lectura(fecha=fecha, producto_id=producto.id, tienda=producto.tienda, estado=estado, motivo=motivo, **datos)

    if isinstance(resultado, ErrorDescarga):
        return lectura(Estado.ERROR, str(resultado))
    if resultado.status in STATUS_NO_ENCONTRADO:
        return lectura(Estado.NO_ENCONTRADO, f"HTTP {resultado.status}: el producto necesita URL nueva")
    if resultado.status in STATUS_BLOQUEO:
        return lectura(Estado.BLOQUEADO, f"HTTP {resultado.status}")
    if resultado.status != 200:
        return lectura(Estado.ERROR, f"HTTP {resultado.status}")

    tienda = TIENDAS[producto.tienda]
    destino = urlsplit(resultado.url_final)
    if destino.hostname not in tienda.dominios:
        return lectura(Estado.ERROR, f"redirigido fuera de la tienda ({destino.hostname})")
    if destino.path in ("", "/"):  # así bloquea Coppel: 302 a la portada
        return lectura(Estado.BLOQUEADO, "redirigido a la portada")
    if not tienda.patron_ruta.fullmatch(destino.path):  # así bloquea Walmart: 302 a /blocked?...
        return lectura(Estado.BLOQUEADO, f"redirigido fuera de la página de producto ({destino.path[:60]})")

    try:
        extraccion = tienda.extraer(resultado.texto, producto.url)
    except ErrorExtraccion as exc:
        return lectura(Estado.ERROR, f"extracción: {exc}")

    datos = {"precio": extraccion.precio, "precio_lista": extraccion.precio_lista, "vendedor": extraccion.vendedor}
    if not ajustes.precio_min_valido <= extraccion.precio <= ajustes.precio_max_valido:
        rango = f"{formatear_pesos(ajustes.precio_min_valido)}–{formatear_pesos(ajustes.precio_max_valido)}"
        return lectura(Estado.ERROR, f"precio {formatear_pesos(extraccion.precio)} fuera de rango {rango}", **datos)
    if not extraccion.vendedor_oficial and not producto.permitir_terceros:
        return lectura(Estado.TERCERO, f"vendido por {extraccion.vendedor or 'vendedor desconocido'}", **datos)
    if not extraccion.disponible:
        return lectura(Estado.AGOTADO, **datos)
    return lectura(Estado.OK, **datos)
