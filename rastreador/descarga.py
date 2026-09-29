"""Descarga HTTP con User-Agent honesto, timeouts y límite de tamaño.

Única pieza que toca la red. La sesión se inyecta para poder probar sin red.
"""

from dataclasses import dataclass

import requests

USER_AGENT = (
    "rastreador-switch2/0.1 (uso personal; historial de precios; "
    "4 lecturas diarias por producto)"
)
TIMEOUT = (10, 30)  # segundos: (conectar, esperar cada lectura)
LIMITE_BYTES = 8 * 1024 * 1024  # las páginas reales pesan < 1 MB
MAX_REDIRECCIONES = 5
TAMANO_TROZO = 64 * 1024


@dataclass(frozen=True, slots=True)
class Respuesta:
    status: int
    url_final: str  # tras seguir redirecciones
    texto: str


class ErrorDescarga(Exception):
    """Fallo de red o respuesta inaceptable. El mensaje es corto y apto para el historial."""


def crear_sesion() -> requests.Session:
    sesion = requests.Session()
    sesion.headers.update({"User-Agent": USER_AGENT, "Accept-Language": "es-MX,es;q=0.9"})
    sesion.max_redirects = MAX_REDIRECCIONES
    return sesion


def descargar(sesion: requests.Session, url: str) -> Respuesta:
    try:
        with sesion.get(url, timeout=TIMEOUT, stream=True, allow_redirects=True) as resp:
            cuerpo = _leer_con_limite(resp)
            return Respuesta(status=resp.status_code, url_final=resp.url, texto=_decodificar(resp, cuerpo))
    except requests.RequestException as exc:
        # Solo el tipo de error: los mensajes de requests son largos y repiten la URL.
        raise ErrorDescarga(f"red: {type(exc).__name__}") from None


def _leer_con_limite(resp: requests.Response) -> bytes:
    declarado = resp.headers.get("Content-Length", "")
    if declarado.isdigit() and int(declarado) > LIMITE_BYTES:
        raise ErrorDescarga(f"respuesta de {int(declarado):,} bytes excede el límite")
    partes: list[bytes] = []
    total = 0
    for trozo in resp.iter_content(TAMANO_TROZO):
        total += len(trozo)
        if total > LIMITE_BYTES:  # el servidor puede mentir o no declarar el tamaño
            raise ErrorDescarga(f"respuesta excede el límite de {LIMITE_BYTES:,} bytes")
        partes.append(trozo)
    return b"".join(partes)


def _decodificar(resp: requests.Response, cuerpo: bytes) -> str:
    # requests supone ISO-8859-1 si text/html no declara charset; en ese caso, UTF-8.
    declara_charset = "charset=" in resp.headers.get("Content-Type", "").lower()
    codificacion = resp.encoding if declara_charset and resp.encoding else "utf-8"
    try:
        return cuerpo.decode(codificacion, errors="replace")
    except LookupError:  # charset inventado por el servidor
        return cuerpo.decode("utf-8", errors="replace")
