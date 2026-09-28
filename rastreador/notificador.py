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
        self._llamar("sendMessage", {"chat_id": self._chat_id, "text": texto, "disable_web_page_preview": True})

    def buscar_chats(self) -> list[tuple[str, str]]:
        """(chat_id, nombre) de quienes escribieron al bot recientemente (getUpdates).

        Sirve para configurar TELEGRAM_CHAT_ID sin pegar la URL con el token en el navegador.
        """
        chats: dict[str, str] = {}
        for actualizacion in self._llamar("getUpdates", {"timeout": 0}) or []:
            mensaje = actualizacion.get("message") or actualizacion.get("channel_post") or {}
            chat = mensaje.get("chat") or {}
            if "id" in chat:
                nombre = chat.get("title") or " ".join(filter(None, [chat.get("first_name"), chat.get("last_name")]))
                chats[str(chat["id"])] = nombre or chat.get("username") or "(sin nombre)"
        return list(chats.items())

    def _llamar(self, metodo: str, datos: dict):
        """Llama a la API y devuelve `result`. Si falla, ErrorNotificacion sin token ni cadena."""
        resultado, fallo = self._intentar(metodo, datos)
        if fallo is not None:
            raise ErrorNotificacion(self._ocultar(fallo))  # fuera del except: sin cadena
        return resultado

    def _intentar(self, metodo: str, datos: dict) -> tuple[object, str | None]:
        """(result, None) si Telegram respondió ok; si no, (None, descripción del fallo)."""
        try:
            resp = self._sesion.post(f"{API}/bot{self._token}/{metodo}", json=datos, timeout=TIMEOUT)
        except requests.RequestException as exc:
            return None, f"Telegram: fallo de red ({type(exc).__name__})"
        try:
            cuerpo = resp.json()
        except ValueError:
            cuerpo = {}
        if not isinstance(cuerpo, dict):  # un proxy o una página de error: no es la API
            cuerpo = {}
        if resp.status_code == 200 and cuerpo.get("ok") is True:
            return cuerpo.get("result"), None
        descripcion = str(cuerpo.get("description", "sin descripción"))[:200]
        return None, f"Telegram respondió HTTP {resp.status_code}: {descripcion}"

    def _ocultar(self, texto: str) -> str:
        return texto.replace(self._token, "***") if self._token else texto


class NotificadorConsola:
    """Para --sin-notificar: muestra el mensaje en vez de enviarlo."""

    def enviar(self, texto: str) -> None:
        print("----- mensaje que se habría enviado -----")
        print(texto)
        print("-----------------------------------------")
