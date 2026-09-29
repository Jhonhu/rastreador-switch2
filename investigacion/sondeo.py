r"""Sondeo de tiendas: descarga cada URL UNA vez, como lo haría el rastreador,
y reporta qué hay en la respuesta. No extrae precios: solo diagnostica dónde
podrían vivir y si la tienda sirve una página de bloqueo.

Uso:
    .venv\Scripts\python.exe investigacion\sondeo.py [directorio_para_html]

Si se pasa un directorio, guarda ahí el HTML crudo para analizarlo a mano.
NUNCA dentro del repo: son páginas completas (usa una carpeta temporal).
"""

import hashlib
import json
import re
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

import requests

USER_AGENT = (
    "rastreador-switch2/0.1 (uso personal; historial de precios; "
    "2 lecturas diarias por producto)"
)
TIMEOUT = (10, 30)  # (conexión, lectura) en segundos
LIMITE_BYTES = 8 * 1024 * 1024
PAUSA_SEGUNDOS = 3

URLS: dict[str, list[str]] = {
    "liverpool": [
        "https://www.liverpool.com.mx/tienda/pdp/consola-nintendo-switch-2-de-256-gb-edicion-estandar/1177646322",
        "https://www.liverpool.com.mx/tienda/pdp/consola-nintendo-switch-2-de-256-gb-edici%C3%B3n-bundle-pok%C3%A9mon/1186172911",
        "https://www.liverpool.com.mx/tienda/pdp/consola-fija-portatil-switch-2-de-256-gb-edicion-bundle-sports-resort/1209428225",
    ],
    "walmart": [
        "https://www.walmart.com.mx/ip/consola-nintendo-switch-2-256-gb/00004549688581",
        "https://www.walmart.com.mx/ip/consola-nintendo-switch-2-256gb-bundle-mario-kart-world-juego-fisico/00490237055345",
    ],
    "coppel": [
        "https://www.coppel.com/pdp/nintendo-switch-2-256gb-mkp-75321163",
    ],
    "gameplanet": [
        "https://gameplanet.com/producto/consola-nintendo-switch-2-con-adaptador-nsw2/",
        "https://gameplanet.com/producto/consola-nintendo-switch-2-con-mario-kart-world-fisico-y-adaptador-de-corriente-nsw2/",
    ],
    "sears": [
        "https://www.sears.com.mx/producto/3522519/consola-nintendo-switch-2",
        "https://www.sears.com.mx/producto/3522625/consola-nintendo-switch-2-mario-kart-world",
    ],
    "bodega-aurrera": [
        "https://www.bodegaaurrera.com.mx/ip/nintendo/consola-nintendo-switch-2-256-gb/00004549688581",
    ],
}

# Señales de dónde podría vivir el precio.
MARCADORES_DATOS = {
    "json_ld": re.compile(r"<script[^>]+application/ld\+json", re.I),
    "next_data": re.compile(r"id=[\"']__NEXT_DATA__[\"']", re.I),
    "rsc_next_f": re.compile(r"self\.__next_f\.push", re.I),
    "meta_precio": re.compile(r"<meta[^>]+(product:price|og:price)", re.I),
    "itemprop_price": re.compile(r"itemprop=[\"']price[\"']", re.I),
    "woocommerce": re.compile(r"woocommerce", re.I),
}
# Señales de página anti-bot o de desafío.
MARCADORES_BLOQUEO = {
    "akamai": re.compile(r"Access Denied|errors\.edgesuite\.net", re.I),
    "perimeterx": re.compile(r"px-captcha|_pxAppId", re.I),
    "cloudflare": re.compile(r"cf-chl|Just a moment\.\.\.|challenge-platform", re.I),
    "sgcaptcha": re.compile(r"sgcaptcha|One moment, please", re.I),
    "robot": re.compile(r"are you a (human|robot)|verify you are human|Pardon Our Interruption", re.I),
}


@dataclass
class Resultado:
    tienda: str
    url: str
    status: int | None = None
    url_final: str | None = None
    redirecciones: list[str] = field(default_factory=list)
    content_type: str | None = None
    bytes: int = 0
    titulo: str | None = None
    datos: list[str] = field(default_factory=list)
    bloqueo: list[str] = field(default_factory=list)
    cookies_bot_manager: bool = False
    error: str | None = None
    segundos: float = 0.0


def descargar(sesion: requests.Session, url: str) -> tuple[requests.Response, bytes]:
    """GET en stream que aborta si la respuesta excede LIMITE_BYTES."""
    with sesion.get(url, timeout=TIMEOUT, stream=True, allow_redirects=True) as resp:
        partes: list[bytes] = []
        total = 0
        for trozo in resp.iter_content(64 * 1024):
            total += len(trozo)
            if total > LIMITE_BYTES:
                raise ValueError(f"respuesta excede {LIMITE_BYTES} bytes")
            partes.append(trozo)
        return resp, b"".join(partes)


def diagnosticar(tienda: str, url: str, sesion: requests.Session, destino: Path | None) -> Resultado:
    res = Resultado(tienda=tienda, url=url)
    inicio = time.monotonic()
    try:
        resp, cuerpo = descargar(sesion, url)
    except (requests.RequestException, ValueError) as exc:
        res.error = f"{type(exc).__name__}: {exc}"[:300]
        res.segundos = round(time.monotonic() - inicio, 1)
        return res
    res.segundos = round(time.monotonic() - inicio, 1)
    res.status = resp.status_code
    res.url_final = resp.url
    res.redirecciones = [f"{r.status_code} {r.headers.get('location', '')}" for r in resp.history]
    res.content_type = resp.headers.get("content-type")
    res.bytes = len(cuerpo)
    # Akamai Bot Manager marca a los clientes con estas cookies.
    nombres_cookies = {c.name for r in [*resp.history, resp] for c in r.cookies}
    res.cookies_bot_manager = bool(nombres_cookies & {"_abck", "bm_sz"})
    texto = cuerpo.decode(resp.encoding or "utf-8", errors="replace")
    titulo = re.search(r"<title[^>]*>(.*?)</title>", texto, re.I | re.S)
    res.titulo = titulo.group(1).strip()[:120] if titulo else None
    res.datos = [n for n, rx in MARCADORES_DATOS.items() if rx.search(texto)]
    res.bloqueo = [n for n, rx in MARCADORES_BLOQUEO.items() if rx.search(texto)]
    if destino is not None:
        nombre = f"{tienda}_{hashlib.sha1(url.encode()).hexdigest()[:8]}.html"
        (destino / nombre).write_text(texto, encoding="utf-8")
        (destino / (nombre + ".url")).write_text(url, encoding="utf-8")
    return res


def revisar_robots(sesion: requests.Session, url: str) -> str:
    partes = urlsplit(url)
    try:
        resp, cuerpo = descargar(sesion, f"{partes.scheme}://{partes.netloc}/robots.txt")
        return f"{resp.status_code} ({len(cuerpo)} bytes)"
    except (requests.RequestException, ValueError) as exc:
        return f"error: {type(exc).__name__}"


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")  # la consola de Windows usa cp1252
    destino = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    if destino is not None:
        destino.mkdir(parents=True, exist_ok=True)
    sesion = requests.Session()
    sesion.headers.update({"User-Agent": USER_AGENT, "Accept-Language": "es-MX,es;q=0.9"})
    for tienda, urls in URLS.items():
        print(f"# {tienda}: robots.txt {revisar_robots(sesion, urls[0])}", flush=True)
        for url in urls:
            time.sleep(PAUSA_SEGUNDOS)
            res = diagnosticar(tienda, url, sesion, destino)
            print(json.dumps(asdict(res), ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
