"""Vigilancias: una búsqueda fija por tienda para enterarse de productos NUEVOS.

Caso de uso: un bundle que la tienda despublicó (404) puede volver con otro
SKU. No es un buscador abierto: la consulta está fija en productos.yaml y solo
avisa UNA vez por SKU (los ya avisados se guardan en data/vigilancias.json).
"""

import json
import os
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit

from .descarga import ErrorDescarga, Respuesta
from .dinero import formatear_pesos
from .lectores import ErrorExtraccion
from .modelos import ResultadoBusqueda, Vigilancia
from .tiendas import TIENDAS


@dataclass(frozen=True, slots=True)
class Hallazgo:
    vigilancia: Vigilancia
    resultado: ResultadoBusqueda
    url: str | None


@dataclass(frozen=True, slots=True)
class Revision:
    hallazgos: tuple[Hallazgo, ...] = ()
    fallo: str | None = None  # la búsqueda no se pudo leer: no se marca nada como visto


# ------------------------------------------------------------------ reglas
def normalizar(texto: str) -> str:
    """Minúsculas y sin acentos: "Pokémon" y "POKEMON" coinciden."""
    return unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode().lower()


def coincide(nombre: str, requiere: tuple[str, ...]) -> bool:
    nombre = normalizar(nombre)
    return all(normalizar(palabra) in nombre for palabra in requiere)


def revisar(vigilancia: Vigilancia, resultado: Respuesta | ErrorDescarga, vistos: set[str]) -> Revision:
    """Qué SKU que cumplen la vigilancia no se habían visto. Función pura."""
    tienda = TIENDAS[vigilancia.tienda]
    if isinstance(resultado, ErrorDescarga):
        return Revision(fallo=str(resultado))
    if resultado.status != 200:
        return Revision(fallo=f"HTTP {resultado.status}")
    destino = urlsplit(resultado.url_final)
    esperado = urlsplit(tienda.url_busqueda(vigilancia.busqueda))
    if destino.hostname not in tienda.dominios or destino.path != esperado.path:
        return Revision(fallo=f"redirigido fuera de la búsqueda ({destino.path[:60]})")
    try:
        resultados = tienda.extraer_resultados(resultado.texto)
    except ErrorExtraccion as exc:
        return Revision(fallo=f"extracción: {exc}")
    nuevos = [r for r in resultados if coincide(r.nombre, vigilancia.requiere) and r.id not in vistos]
    return Revision(hallazgos=tuple(Hallazgo(vigilancia, r, tienda.url_producto(r) if tienda.url_producto else None)
                                    for r in nuevos))


# ------------------------------------------------------------------ estado (data/vigilancias.json)
def cargar_vistos(ruta: Path) -> dict[str, dict[str, str]]:
    """{vigilancia_id: {sku: fecha_utc_en_que_se_avisó}}."""
    if not ruta.exists():
        return {}
    datos = json.loads(ruta.read_text(encoding="utf-8"))
    if not isinstance(datos, dict) or not all(isinstance(v, dict) for v in datos.values()):
        raise ValueError(f"{ruta}: formato inesperado")
    return datos


def guardar_vistos(ruta: Path, vistos: dict[str, dict[str, str]]) -> None:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    temporal = ruta.with_suffix(ruta.suffix + ".tmp")
    texto = json.dumps(vistos, ensure_ascii=False, indent=1, sort_keys=True) + "\n"
    temporal.write_text(texto, encoding="utf-8", newline="\n")
    os.replace(temporal, ruta)


def marcar_vistos(vistos: dict[str, dict[str, str]], hallazgos: tuple[Hallazgo, ...], fecha: datetime) -> None:
    for h in hallazgos:
        vistos.setdefault(h.vigilancia.id, {})[h.resultado.id] = fecha.strftime("%Y-%m-%dT%H:%M:%SZ")


# ------------------------------------------------------------------ mensaje
def redactar_hallazgos(hallazgos: tuple[Hallazgo, ...]) -> str:
    bloques = []
    for h in hallazgos:
        precio = f" · {formatear_pesos(h.resultado.precio)}" if h.resultado.precio is not None else ""
        lineas = [f"Apareció en {h.vigilancia.tienda.capitalize()} (búsqueda \"{h.vigilancia.busqueda}\")",
                  f"{h.resultado.nombre} · SKU {h.resultado.id}{precio}"]
        if h.url:
            lineas.append(h.url)
        bloques.append("\n".join(lineas))
    return "\n\n".join(bloques)
