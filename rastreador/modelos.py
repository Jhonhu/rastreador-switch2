"""Tipos de datos del rastreador. Solo datos: sin red, sin disco, sin reloj.

Todos los importes son enteros en CENTAVOS (int), nunca float.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum


class Estado(StrEnum):
    """Resultado de una lectura. Solo OK cuenta para mínimos y alertas."""

    OK = "ok"
    AGOTADO = "agotado"
    TERCERO = "tercero"  # lo vende alguien distinto de la tienda (marketplace)
    NO_ENCONTRADO = "no_encontrado"  # 404/410: el producto necesita URL nueva
    BLOQUEADO = "bloqueado"  # 401/403/429 o redirección a la portada (anti-bot)
    ERROR = "error"  # red, formato inesperado, precio fuera de rango


class Version(StrEnum):
    NACIONAL = "nacional"
    INTERNACIONAL = "internacional"
    SIN_DECLARAR = "sin_declarar"  # la tienda no lo dice (p. ej. Gameplanet)


@dataclass(frozen=True, slots=True)
class Producto:
    id: str
    tienda: str
    url: str
    version: Version
    descripcion: str
    valor_extra: int = 0  # centavos: lo que vale para ti lo que incluye el bundle
    precio_objetivo: int | None = None  # centavos; None = usa el de los ajustes
    permitir_terceros: bool = False

    def precio_efectivo(self, precio: int) -> int:
        """Precio − valor_extra. Todas las comparaciones usan este valor."""
        return precio - self.valor_extra


@dataclass(frozen=True, slots=True)
class Ajustes:
    lecturas_minimas: int  # lecturas OK previas antes de alertar "mínimo histórico"
    precio_min_valido: int  # centavos; fuera del rango = error (p. ej. mensualidad MSI)
    precio_max_valido: int
    precio_objetivo: int | None = None  # centavos
    baja_minima_alerta: int = 0  # centavos: cuánto debe bajar un mínimo para avisar (0 = cualquier baja)


@dataclass(frozen=True, slots=True)
class Configuracion:
    ajustes: Ajustes
    productos: tuple[Producto, ...]


@dataclass(frozen=True, slots=True)
class Extraccion:
    """Lo que un extractor encontró en el HTML, antes de aplicar reglas."""

    precio: int  # centavos: lo que se paga hoy
    precio_lista: int | None  # el "antes" que anuncia la tienda (informativo)
    disponible: bool
    vendedor: str | None
    vendedor_oficial: bool


@dataclass(frozen=True, slots=True)
class Lectura:
    """Una fila del historial: qué pasó al leer un producto en un momento."""

    fecha: datetime  # siempre UTC con zona horaria
    producto_id: str
    tienda: str
    estado: Estado
    precio: int | None = None
    precio_lista: int | None = None
    vendedor: str | None = None
    motivo: str = ""

    def __post_init__(self) -> None:
        if self.fecha.utcoffset() != timedelta(0):
            raise ValueError("la fecha de una lectura debe ser UTC con zona horaria")
