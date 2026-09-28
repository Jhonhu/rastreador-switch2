"""Secretos de Telegram desde variables de entorno (GitHub Secrets) o un .env local.

El .env es para tu PC: está en .gitignore. Evita poner el token con
`$env:TELEGRAM_TOKEN = "..."` en PowerShell, porque queda en el historial
de comandos (PSReadLine lo guarda en disco).
"""

import re
from collections.abc import Mapping, MutableMapping
from dataclasses import dataclass, field
from pathlib import Path

PATRON_TOKEN = re.compile(r"\d{5,}:[A-Za-z0-9_-]{30,}")
PATRON_CHAT_ID = re.compile(r"-?\d{1,20}")


class ErrorSecretos(Exception):
    """Falta un secreto o tiene mal formato. El mensaje nunca incluye el valor."""


@dataclass(frozen=True, slots=True)
class SecretosTelegram:
    token: str = field(repr=False)
    chat_id: str = field(repr=False)


def leer_secretos(entorno: Mapping[str, str]) -> SecretosTelegram:
    token = entorno.get("TELEGRAM_TOKEN", "").strip()
    chat_id = entorno.get("TELEGRAM_CHAT_ID", "").strip()
    faltan = [n for n, v in (("TELEGRAM_TOKEN", token), ("TELEGRAM_CHAT_ID", chat_id)) if not v]
    if faltan:
        raise ErrorSecretos(f"faltan variables de entorno: {', '.join(faltan)} (o usa --sin-notificar)")
    if not PATRON_TOKEN.fullmatch(token):
        raise ErrorSecretos("TELEGRAM_TOKEN no tiene el formato <número>:<clave> que entrega @BotFather")
    if not PATRON_CHAT_ID.fullmatch(chat_id):
        raise ErrorSecretos("TELEGRAM_CHAT_ID debe ser un número (negativo si es un grupo)")
    return SecretosTelegram(token=token, chat_id=chat_id)


def cargar_env(ruta: Path, entorno: MutableMapping[str, str]) -> None:
    """Lee líneas CLAVE=valor. No pisa variables ya definidas (los Secrets de Actions ganan)."""
    if not ruta.exists():
        return
    for linea in ruta.read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        if not linea or linea.startswith("#") or "=" not in linea:
            continue
        clave, _, valor = linea.partition("=")
        clave, valor = clave.strip(), valor.strip().strip("\"'")
        if clave and clave not in entorno:
            entorno[clave] = valor
