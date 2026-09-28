"""Envío de alertas por Telegram sin filtrar el token.

La URL de la API lleva el token (https://api.telegram.org/bot<TOKEN>/sendMessage)
y requests lo repite en sus excepciones ("Max retries exceeded with url: ...").
Por eso aquí:
  - Ninguna excepción de requests sale de este módulo: se traduce a
    ErrorNotificacion con un mensaje propio, lanzada FUERA del bloque except
    para que no quede encadenada (ni __cause__ ni __context__).
  - Nunca se usa raise_for_status() ni resp.url (ambos incluyen la URL).
  - Cualquier texto de Telegram que se reporte pasa por _ocultar().
  - repr() del notificador no muestra el token.
"""

from typing import Protocol

import requests

TIMEOUT = (10, 20)
API = "https://api.telegram.org"


class ErrorNotificacion(Exception):
    """El envío falló. El mensaje nunca contiene el token."""


class Notificador(Protocol):
    def enviar(self, texto: str) -> None: ...


class NotificadorTelegram:
    def __init__(self, token: str, chat_id: str, sesion: requests.Session | None = None):
        self._token = token
        self._chat_id = chat_id
        self._sesion = sesion or requests.Session()

    def __repr__(self) -> str:
        return f"NotificadorTelegram(chat_id={self._chat_id!r}, token=***)"

    def enviar(self, texto: str) -> None:
        fallo = self._intentar_envio(texto)
        if fallo is not None:
            raise ErrorNotificacion(self._ocultar(fallo))  # fuera del except: sin cadena

    def _intentar_envio(self, texto: str) -> str | None:
        """None si Telegram confirmó el envío; si no, la descripción del fallo."""
        try:
            resp = self._sesion.post(
                f"{API}/bot{self._token}/sendMessage",
                json={"chat_id": self._chat_id, "text": texto, "disable_web_page_preview": True},
                timeout=TIMEOUT,
            )
        except requests.RequestException as exc:
            return f"Telegram: fallo de red ({type(exc).__name__})"
        try:
            cuerpo = resp.json()
        except ValueError:
            cuerpo = {}
        if not isinstance(cuerpo, dict):  # un proxy o una página de error: no es la API
            cuerpo = {}
        if resp.status_code == 200 and cuerpo.get("ok") is True:
            return None
        descripcion = str(cuerpo.get("description", "sin descripción"))[:200]
        return f"Telegram respondió HTTP {resp.status_code}: {descripcion}"

    def _ocultar(self, texto: str) -> str:
        return texto.replace(self._token, "***") if self._token else texto


class NotificadorConsola:
    """Para --sin-notificar: muestra el mensaje en vez de enviarlo."""

    def enviar(self, texto: str) -> None:
        print("----- mensaje que se habría enviado -----")
        print(texto)
        print("-----------------------------------------")
