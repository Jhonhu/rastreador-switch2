"""Genera docs/datos.json: todo lo que el dashboard estático necesita, ya calculado.

Datos y presentación separados: la página solo formatea y dibuja. Importes en
centavos y fechas en UTC (ISO 8601); el navegador los muestra en hora de CDMX.
"""

import json
import os
from collections import defaultdict
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .modelos import Configuracion, Estado, Lectura, Producto

VERSION_FORMATO = 1
ESTADOS_CON_PRECIO_VIGENTE = {Estado.OK, Estado.AGOTADO, Estado.TERCERO}
ESTADOS_FALLIDOS = {Estado.ERROR, Estado.BLOQUEADO, Estado.NO_ENCONTRADO}


def construir(config: Configuracion, lecturas: Iterable[Lectura], generado: datetime) -> dict[str, Any]:
    por_producto: dict[str, list[Lectura]] = defaultdict(list)
    for lectura in sorted(lecturas, key=lambda l: l.fecha):
        por_producto[lectura.producto_id].append(lectura)

    productos = [_resumen_producto(p, config, por_producto[p.id]) for p in config.productos]
    return {
        "version_formato": VERSION_FORMATO,
        "generado_utc": _iso(generado),
        "precio_objetivo": config.ajustes.precio_objetivo,
        "mejor": _mejor_actual(productos),
        "productos": productos,
    }


def escribir(ruta: Path, datos: dict[str, Any]) -> None:
    """Escritura atómica: la página nunca ve un JSON a medio escribir."""
    ruta.parent.mkdir(parents=True, exist_ok=True)
    temporal = ruta.with_suffix(ruta.suffix + ".tmp")
    temporal.write_text(json.dumps(datos, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
    os.replace(temporal, ruta)


# ------------------------------------------------------------------ por producto
def _resumen_producto(producto: Producto, config: Configuracion, lecturas: list[Lectura]) -> dict[str, Any]:
    ultima = lecturas[-1] if lecturas else None
    validas = [l for l in lecturas if l.estado is Estado.OK and l.precio is not None]
    serie = [(l.fecha, producto.precio_efectivo(l.precio)) for l in validas]
    vigente = ultima is not None and ultima.estado in ESTADOS_CON_PRECIO_VIGENTE and ultima.precio is not None

    return {
        "id": producto.id,
        "tienda": producto.tienda,
        "descripcion": producto.descripcion,
        "version": producto.version.value,
        "url": producto.url,
        "valor_extra": producto.valor_extra,
        "precio_objetivo": producto.precio_objetivo or config.ajustes.precio_objetivo,
        "estado": ultima.estado.value if ultima else "sin_datos",
        "motivo": ultima.motivo if ultima else "",
        "vendedor": ultima.vendedor if ultima else None,
        "ultima_lectura_utc": _iso(ultima.fecha) if ultima else None,
        "precio_actual": ultima.precio if vigente else None,
        "precio_lista_actual": ultima.precio_lista if vigente else None,
        "efectivo_actual": producto.precio_efectivo(ultima.precio) if vigente else None,
        "minimo": _extremo(serie, min),
        "maximo": _extremo(serie, max),
        "lecturas_ok": len(validas),
        "racha_fallos": _racha_fallos(lecturas),
        "serie": [[_iso(fecha), efectivo] for fecha, efectivo in serie],
    }


def _extremo(serie: list[tuple[datetime, int]], funcion) -> dict[str, Any] | None:
    if not serie:
        return None
    fecha, efectivo = funcion(serie, key=lambda punto: (punto[1], punto[0]))
    return {"efectivo": efectivo, "fecha_utc": _iso(fecha)}


def _racha_fallos(lecturas: list[Lectura]) -> int:
    """Cuántas lecturas seguidas (las más recientes) fallaron: "lleva 5 días fallando"."""
    racha = 0
    for lectura in reversed(lecturas):
        if lectura.estado not in ESTADOS_FALLIDOS:
            break
        racha += 1
    return racha


def _mejor_actual(productos: list[dict[str, Any]]) -> dict[str, Any] | None:
    """El precio efectivo más bajo entre los productos cuya última lectura es OK."""
    candidatos = [p for p in productos if p["estado"] == Estado.OK.value and p["efectivo_actual"] is not None]
    if not candidatos:
        return None
    mejor = min(candidatos, key=lambda p: p["efectivo_actual"])
    return {"producto_id": mejor["id"], "efectivo": mejor["efectivo_actual"]}


def _iso(fecha: datetime) -> str:
    return fecha.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
