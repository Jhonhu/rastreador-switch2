"""Una ejecución diaria: leer cada producto, guardar el historial y alertar.

Red, reloj, pausa y notificador se inyectan: las pruebas simulan días enteros
sin red y sin esperar.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .alertas import Alerta, evaluar, redactar_mensaje
from .clasificacion import clasificar
from .descarga import ErrorDescarga, Respuesta
from .historial import agregar_lecturas, leer_lecturas
from .modelos import Configuracion, Estado, Lectura
from .notificador import ErrorNotificacion, Notificador

ESTADOS_FALLIDOS = {Estado.ERROR, Estado.BLOQUEADO, Estado.NO_ENCONTRADO}
PAUSA_ENTRE_DESCARGAS = 2.0  # segundos: cortesía con las tiendas


@dataclass(frozen=True, slots=True)
class Dependencias:
    descargar: Callable[[str], Respuesta]  # puede lanzar ErrorDescarga
    reloj: Callable[[], datetime]  # devuelve UTC
    pausa: Callable[[float], None]
    notificador: Notificador


@dataclass(frozen=True, slots=True)
class Resumen:
    lecturas: tuple[Lectura, ...]
    alertas: tuple[Alerta, ...]
    fallo_notificacion: str | None = None  # el dato quedó guardado, pero el aviso no salió

    @property
    def todas_fallaron(self) -> bool:
        """Ninguna tienda respondió con datos: GitHub Actions debe marcarlo en rojo."""
        return bool(self.lecturas) and all(l.estado in ESTADOS_FALLIDOS for l in self.lecturas)


def ejecutar(config: Configuracion, ruta_historial: Path, deps: Dependencias) -> Resumen:
    previas = leer_lecturas(ruta_historial)  # antes de tocar la red: un CSV roto aborta todo
    nuevas = _leer_productos(config, deps)
    agregar_lecturas(ruta_historial, nuevas)  # se guarda ANTES de notificar: si Telegram falla, el dato queda

    productos = {p.id: p for p in config.productos}
    alertas = tuple(a for l in nuevas for a in evaluar(productos[l.producto_id], config.ajustes, previas, l))
    fallo = None
    if alertas:
        try:
            deps.notificador.enviar(redactar_mensaje(alertas))
        except ErrorNotificacion as exc:
            fallo = str(exc)  # ya viene sin token (ver notificador.py)
    return Resumen(lecturas=tuple(nuevas), alertas=alertas, fallo_notificacion=fallo)


def _leer_productos(config: Configuracion, deps: Dependencias) -> list[Lectura]:
    lecturas = []
    for i, producto in enumerate(config.productos):
        if i:
            deps.pausa(PAUSA_ENTRE_DESCARGAS)
        try:
            resultado: Respuesta | ErrorDescarga = deps.descargar(producto.url)
        except ErrorDescarga as exc:
            resultado = exc
        lecturas.append(clasificar(producto, config.ajustes, resultado, deps.reloj()))
    return lecturas
