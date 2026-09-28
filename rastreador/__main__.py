r"""Punto de entrada: python -m rastreador [--sin-notificar]

Códigos de salida (GitHub Actions marca en rojo todo lo distinto de 0):
  0  terminó (aunque algunas tiendas hayan fallado)
  1  TODAS las lecturas fallaron
  2  configuración, secretos o historial inválidos (no se tocó la red)
  3  las lecturas se guardaron, pero falló el envío a Telegram
"""

import argparse
import logging
import os
import sys
import time
from collections.abc import Callable, MutableMapping
from datetime import UTC, datetime
from functools import partial
from pathlib import Path

from . import dashboard
from .config import ErrorConfiguracion, cargar_configuracion
from .descarga import Respuesta, crear_sesion, descargar
from .dinero import formatear_pesos
from .historial import ErrorHistorial, leer_lecturas
from .modelos import Configuracion
from .notificador import Notificador, NotificadorConsola, NotificadorTelegram
from .orquestador import Dependencias, Resumen, ejecutar
from .secretos import ErrorSecretos, cargar_env, leer_secretos

RAIZ = Path(__file__).resolve().parent.parent


def main(
    argv: list[str] | None = None,
    entorno: MutableMapping[str, str] | None = None,
    descargador: Callable[[str], Respuesta] | None = None,
) -> int:
    args = _argumentos(argv)
    entorno = os.environ if entorno is None else entorno
    # urllib3 registra las URLs en nivel DEBUG, y la de Telegram lleva el token.
    logging.getLogger("urllib3").setLevel(logging.WARNING)

    try:
        config = cargar_configuracion(args.config)
        notificador = _crear_notificador(args, entorno)
        deps = Dependencias(
            descargar=descargador or partial(descargar, crear_sesion()),
            reloj=lambda: datetime.now(UTC),
            pausa=time.sleep,
            notificador=notificador,
        )
        resumen = ejecutar(config, args.historial, deps)
        # Siempre, aunque todo haya fallado: el dashboard debe mostrar los fallos.
        datos = dashboard.construir(config, leer_lecturas(args.historial), deps.reloj())
        dashboard.escribir(args.dashboard, datos)
    except (ErrorConfiguracion, ErrorSecretos, ErrorHistorial) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    _imprimir(resumen, config)
    if resumen.todas_fallaron:
        print("ERROR: todas las lecturas fallaron", file=sys.stderr)
        return 1
    if resumen.fallo_notificacion:
        print(f"ERROR: lecturas guardadas, pero no se pudo notificar: {resumen.fallo_notificacion}", file=sys.stderr)
        return 3
    return 0


def _argumentos(argv: list[str] | None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(prog="python -m rastreador", description="Rastreador de precios de Switch 2")
    ap.add_argument("--sin-notificar", action="store_true", help="muestra las alertas en consola en vez de enviarlas")
    ap.add_argument("--config", type=Path, default=RAIZ / "productos.yaml")
    ap.add_argument("--historial", type=Path, default=RAIZ / "data" / "lecturas.csv")
    ap.add_argument("--dashboard", type=Path, default=RAIZ / "docs" / "datos.json")
    return ap.parse_args(argv)


def _crear_notificador(args: argparse.Namespace, entorno: MutableMapping[str, str]) -> Notificador:
    if args.sin_notificar:
        return NotificadorConsola()
    cargar_env(RAIZ / ".env", entorno)
    secretos = leer_secretos(entorno)
    return NotificadorTelegram(secretos.token, secretos.chat_id)


def _imprimir(resumen: Resumen, config: Configuracion) -> None:
    productos = {p.id: p for p in config.productos}
    for l in resumen.lecturas:
        if l.precio is None:
            detalle = l.motivo
        else:
            efectivo = productos[l.producto_id].precio_efectivo(l.precio)
            detalle = f"{formatear_pesos(l.precio)} (efectivo {formatear_pesos(efectivo)}) {l.motivo}".strip()
        print(f"{l.estado.value:13} {l.producto_id:26} {detalle}")
    print(f"{len(resumen.alertas)} alerta(s)")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")  # la consola de Windows usa cp1252
    sys.stderr.reconfigure(encoding="utf-8")
    sys.exit(main())
