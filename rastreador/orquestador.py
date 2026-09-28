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
from .tiendas import TIENDAS
from .vigilancia import Hallazgo, cargar_vistos, guardar_vistos, marcar_vistos, redactar_hallazgos, revisar

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
    hallazgos: tuple[Hallazgo, ...] = ()  # productos nuevos encontrados por las vigilancias
    fallos_vigilancia: tuple[tuple[str, str], ...] = ()  # (vigilancia_id, motivo); no cuentan como lecturas

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
    hallazgos, fallos_vigilancia = _revisar_vigilancias(config, ruta_historial.parent / "vigilancias.json", deps)

    fallo = None
    partes = ([redactar_mensaje(alertas)] if alertas else []) + ([redactar_hallazgos(hallazgos)] if hallazgos else [])
    if partes:
        try:
            deps.notificador.enviar("\n\n".join(partes))
        except ErrorNotificacion as exc:
            fallo = str(exc)  # ya viene sin token (ver notificador.py)
    return Resumen(lecturas=tuple(nuevas), alertas=alertas, fallo_notificacion=fallo,
                   hallazgos=hallazgos, fallos_vigilancia=fallos_vigilancia)


def _revisar_vigilancias(config: Configuracion, ruta_vistos: Path, deps: Dependencias):
    """Corre cada búsqueda fija y guarda los SKU nuevos ANTES de avisar (igual que el historial)."""
    if not config.vigilancias:
        return (), ()
    vistos = cargar_vistos(ruta_vistos)
    hallazgos: list[Hallazgo] = []
    fallos: list[tuple[str, str]] = []
    for vigilancia in config.vigilancias:
        deps.pausa(PAUSA_ENTRE_DESCARGAS)
        url = TIENDAS[vigilancia.tienda].url_busqueda(vigilancia.busqueda)
        try:
            resultado: Respuesta | ErrorDescarga = deps.descargar(url)
        except ErrorDescarga as exc:
            resultado = exc
        revision = revisar(vigilancia, resultado, set(vistos.get(vigilancia.id, {})))
        if revision.fallo:
            fallos.append((vigilancia.id, revision.fallo))
        hallazgos.extend(revision.hallazgos)
        marcar_vistos(vistos, revision.hallazgos, deps.reloj())
    if hallazgos or not ruta_vistos.exists():
        guardar_vistos(ruta_vistos, vistos)
    return tuple(hallazgos), tuple(fallos)


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
