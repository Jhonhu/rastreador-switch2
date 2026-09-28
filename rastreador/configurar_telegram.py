r"""Ayudas para configurar Telegram sin exponer el token.

    .venv\Scripts\python.exe -m rastreador.configurar_telegram chat-id
        Muestra el chat_id de quien le escribió al bot (escríbele "hola" antes).
        Solo necesita TELEGRAM_TOKEN (en .env).

    .venv\Scripts\python.exe -m rastreador.configurar_telegram probar
        Manda un mensaje de prueba con TELEGRAM_TOKEN y TELEGRAM_CHAT_ID.

Ninguno imprime el token. Evita la receta de abrir
https://api.telegram.org/bot<TOKEN>/getUpdates en el navegador: deja el token
en el historial.
"""

import argparse
import os
import sys
from collections.abc import MutableMapping
from pathlib import Path

from .notificador import ErrorNotificacion, NotificadorTelegram
from .secretos import PATRON_TOKEN, ErrorSecretos, cargar_env, leer_secretos

RAIZ = Path(__file__).resolve().parent.parent


def main(argv: list[str] | None = None, entorno: MutableMapping[str, str] | None = None,
         fabrica=NotificadorTelegram) -> int:
    ap = argparse.ArgumentParser(prog="python -m rastreador.configurar_telegram")
    ap.add_argument("accion", choices=["chat-id", "probar"])
    args = ap.parse_args(argv)
    entorno = os.environ if entorno is None else entorno
    cargar_env(RAIZ / ".env", entorno)

    try:
        if args.accion == "chat-id":
            return _mostrar_chat_ids(entorno, fabrica)
        secretos = leer_secretos(entorno)
        fabrica(secretos.token, secretos.chat_id).enviar("Prueba del rastreador de Switch 2: el bot funciona.")
        print("Mensaje de prueba enviado. Revisa Telegram.")
        return 0
    except (ErrorSecretos, ErrorNotificacion) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


def _mostrar_chat_ids(entorno: MutableMapping[str, str], fabrica) -> int:
    token = entorno.get("TELEGRAM_TOKEN", "").strip()
    if not PATRON_TOKEN.fullmatch(token):
        raise ErrorSecretos("define TELEGRAM_TOKEN en .env (el que te dio @BotFather)")
    chats = fabrica(token, "").buscar_chats()
    if not chats:
        print("No hay mensajes recientes. Escríbele cualquier cosa a tu bot en Telegram y vuelve a correr esto.")
        return 1
    print("Chats que le escribieron al bot (usa el id como TELEGRAM_CHAT_ID):")
    for chat_id, nombre in chats:
        print(f"  {chat_id}  {nombre}")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    sys.exit(main())
