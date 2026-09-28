"""Historial en CSV de solo-agregar (data/lecturas.csv).

Legible en los diffs de git; el historial de git es el respaldo. Nunca se
reescribe: solo se agregan filas al final.
"""

import csv
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path

from .modelos import Estado, Lectura

COLUMNAS = (
    "fecha_utc", "producto_id", "tienda", "estado",
    "precio_centavos", "precio_lista_centavos", "vendedor", "motivo",
)
FORMATO_FECHA = "%Y-%m-%dT%H:%M:%SZ"
MAX_TEXTO = 300
# Si un texto empieza así, Excel/LibreOffice lo ejecutan como fórmula al abrir el CSV.
INICIO_DE_FORMULA = ("=", "+", "-", "@")


class ErrorHistorial(Exception):
    pass


def agregar_lecturas(ruta: Path, lecturas: Iterable[Lectura]) -> None:
    filas = [_a_fila(lectura) for lectura in lecturas]  # validar todo antes de tocar el archivo
    nuevo = not ruta.exists() or ruta.stat().st_size == 0
    if nuevo:
        ruta.parent.mkdir(parents=True, exist_ok=True)
    else:
        _verificar_encabezado(ruta)
        _asegurar_salto_final(ruta)
    with ruta.open("a", encoding="utf-8", newline="") as archivo:
        escritor = csv.writer(archivo, lineterminator="\n")
        if nuevo:
            escritor.writerow(COLUMNAS)
        escritor.writerows(filas)


def leer_lecturas(ruta: Path) -> list[Lectura]:
    if not ruta.exists():
        return []
    with ruta.open(encoding="utf-8", newline="") as archivo:
        lector = csv.reader(archivo)
        encabezado = next(lector, None)
        if encabezado is None:
            return []
        if tuple(encabezado) != COLUMNAS:
            raise ErrorHistorial(f"{ruta}: encabezado inesperado {encabezado}")
        lecturas = []
        for numero, fila in enumerate(lector, start=2):
            try:
                lecturas.append(_de_fila(fila))
            except (ValueError, TypeError) as exc:
                raise ErrorHistorial(f"{ruta}, línea {numero}: {exc}") from None
        return lecturas


# ------------------------------------------------------------------ filas
def _a_fila(lectura: Lectura) -> list[str]:
    return [
        lectura.fecha.astimezone(UTC).strftime(FORMATO_FECHA),
        lectura.producto_id,
        lectura.tienda,
        lectura.estado.value,
        _entero_a_texto(lectura.precio),
        _entero_a_texto(lectura.precio_lista),
        _texto_seguro(lectura.vendedor or ""),
        _texto_seguro(lectura.motivo),
    ]


def _de_fila(fila: list[str]) -> Lectura:
    if len(fila) != len(COLUMNAS):
        raise ValueError(f"se esperaban {len(COLUMNAS)} columnas y hay {len(fila)}")
    fecha, producto_id, tienda, estado, precio, precio_lista, vendedor, motivo = fila
    return Lectura(
        fecha=datetime.strptime(fecha, FORMATO_FECHA).replace(tzinfo=UTC),
        producto_id=producto_id,
        tienda=tienda,
        estado=Estado(estado),
        precio=_texto_a_entero(precio),
        precio_lista=_texto_a_entero(precio_lista),
        vendedor=vendedor or None,
        motivo=motivo,
    )


def _entero_a_texto(valor: int | None) -> str:
    return "" if valor is None else str(valor)


def _texto_a_entero(texto: str) -> int | None:
    return int(texto) if texto else None


def _texto_seguro(texto: str) -> str:
    """Una línea, longitud acotada y sin arrancar como fórmula de hoja de cálculo."""
    limpio = " ".join(texto.split())[:MAX_TEXTO]
    return "'" + limpio if limpio.startswith(INICIO_DE_FORMULA) else limpio


# ------------------------------------------------------------------ archivo
def _verificar_encabezado(ruta: Path) -> None:
    with ruta.open(encoding="utf-8", newline="") as archivo:
        encabezado = next(csv.reader(archivo), None)
    if encabezado is None or tuple(encabezado) != COLUMNAS:
        raise ErrorHistorial(f"{ruta}: encabezado inesperado {encabezado}; no agrego para no mezclar formatos")


def _asegurar_salto_final(ruta: Path) -> None:
    """Si alguien editó el archivo a mano y quitó el último salto, la fila nueva no se pega."""
    with ruta.open("rb") as archivo:
        archivo.seek(-1, 2)
        ultimo = archivo.read(1)
    if ultimo != b"\n":
        with ruta.open("a", encoding="utf-8", newline="") as archivo:
            archivo.write("\n")
