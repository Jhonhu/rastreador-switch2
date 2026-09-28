"""Reglas de alerta (anti-spam) y redacción del mensaje. Funciones puras.

Solo las lecturas OK cuentan. Todo se compara con el precio EFECTIVO
(precio − valor_extra), calculado con la valoración actual del producto.
"""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from enum import StrEnum

from .dinero import formatear_pesos
from .modelos import Ajustes, Estado, Lectura, Producto

LIMITE_MENSAJE = 4000  # Telegram corta en 4096 caracteres


class TipoAlerta(StrEnum):
    MINIMO_HISTORICO = "minimo_historico"
    CRUCE_OBJETIVO = "cruce_objetivo"


@dataclass(frozen=True, slots=True)
class Alerta:
    tipo: TipoAlerta
    producto: Producto
    precio: int  # centavos, lo que cobra la tienda
    precio_efectivo: int
    referencia: int  # mínimo anterior o precio objetivo, según el tipo


def evaluar(producto: Producto, ajustes: Ajustes, previas: Iterable[Lectura], nueva: Lectura) -> list[Alerta]:
    """Alertas que dispara `nueva` dado el historial `previas` (de cualquier producto)."""
    if nueva.estado is not Estado.OK or nueva.precio is None:
        return []
    efectivo = producto.precio_efectivo(nueva.precio)
    validas = [producto.precio_efectivo(l.precio) for l in _ok_del_producto(previas, producto.id)]

    alertas = []
    if _es_nuevo_minimo(efectivo, validas, ajustes.lecturas_minimas, ajustes.baja_minima_alerta):
        alertas.append(Alerta(TipoAlerta.MINIMO_HISTORICO, producto, nueva.precio, efectivo, min(validas)))
    objetivo = _primero_definido(producto.precio_objetivo, ajustes.precio_objetivo)
    if objetivo is not None and _cruza_hacia_abajo(efectivo, validas[-1] if validas else None, objetivo):
        alertas.append(Alerta(TipoAlerta.CRUCE_OBJETIVO, producto, nueva.precio, efectivo, objetivo))
    return alertas


def _ok_del_producto(lecturas: Iterable[Lectura], producto_id: str) -> list[Lectura]:
    """Lecturas válidas del producto en orden cronológico."""
    propias = [l for l in lecturas if l.producto_id == producto_id and l.estado is Estado.OK and l.precio is not None]
    return sorted(propias, key=lambda l: l.fecha)


def _es_nuevo_minimo(efectivo: int, previos: Sequence[int], lecturas_minimas: int, baja_minima: int) -> bool:
    """Baja del mínimo anterior al menos `baja_minima` centavos (y siempre estrictamente).

    Con poco historial, cualquier lectura "gana": no se alerta hasta tener N previas.
    """
    if len(previos) < max(lecturas_minimas, 1):
        return False
    anterior = min(previos)
    return efectivo < anterior and anterior - efectivo >= baja_minima


def _cruza_hacia_abajo(efectivo: int, anterior: int | None, objetivo: int) -> bool:
    """Alcanza el objetivo (<=) viniendo de arriba. Si ya estaba abajo, no se repite.

    `anterior` es la última lectura OK: un día agotado o con error no rompe la racha.
    Sin lecturas previas, estar abajo cuenta como cruce (es la primera noticia).
    """
    return efectivo <= objetivo and (anterior is None or anterior > objetivo)


def _primero_definido(*valores: int | None) -> int | None:
    return next((v for v in valores if v is not None), None)


# ------------------------------------------------------------------ mensaje
def redactar_mensaje(alertas: Sequence[Alerta]) -> str:
    """Texto plano (sin parse_mode): nada de lo que venga de la tienda se interpreta como HTML."""
    bloques = ["Switch 2: precio que vale la pena"]
    for alerta in alertas:
        bloques.append(_redactar_alerta(alerta))
    mensaje = "\n\n".join(bloques)
    return mensaje if len(mensaje) <= LIMITE_MENSAJE else mensaje[: LIMITE_MENSAJE - 1] + "…"


def _redactar_alerta(alerta: Alerta) -> str:
    p = alerta.producto
    if alerta.tipo is TipoAlerta.MINIMO_HISTORICO:
        titulo = f"Nuevo mínimo histórico (antes {formatear_pesos(alerta.referencia)})"
    else:
        titulo = f"Bajó del objetivo de {formatear_pesos(alerta.referencia)}"
    precio = f"Precio efectivo: {formatear_pesos(alerta.precio_efectivo)}"
    if p.valor_extra:
        precio += f" (cobra {formatear_pesos(alerta.precio)} − extra {formatear_pesos(p.valor_extra)})"
    return "\n".join([titulo, f"{p.tienda.capitalize()} · {p.descripcion}", precio, p.url])
