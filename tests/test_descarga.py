"""Descarga sin red: una sesión falsa que imita lo mínimo de requests."""

import pytest
import requests

from rastreador import descarga
from rastreador.descarga import USER_AGENT, ErrorDescarga, crear_sesion, descargar


class RespuestaFalsa:
    def __init__(self, cuerpo: bytes, status=200, url="https://www.sears.com.mx/producto/1/x",
                 headers=None, encoding=None):
        self.cuerpo, self.status_code, self.url = cuerpo, status, url
        self.headers = headers if headers is not None else {"Content-Type": "text/html; charset=utf-8"}
        self.encoding = encoding or "utf-8"

    def iter_content(self, tamano):
        for i in range(0, len(self.cuerpo), tamano):
            yield self.cuerpo[i:i + tamano]

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


class SesionFalsa:
    def __init__(self, respuesta=None, error=None):
        self.respuesta, self.error, self.llamadas = respuesta, error, []

    def get(self, url, **kwargs):
        self.llamadas.append((url, kwargs))
        if self.error:
            raise self.error
        return self.respuesta


def test_descarga_con_timeout_stream_y_redirecciones():
    sesion = SesionFalsa(RespuestaFalsa("<html>ñ</html>".encode()))
    r = descargar(sesion, "https://www.sears.com.mx/producto/1/x")
    assert (r.status, r.texto) == (200, "<html>ñ</html>")
    _, kwargs = sesion.llamadas[0]
    assert kwargs["timeout"] == descarga.TIMEOUT
    assert kwargs["stream"] is True


def test_rechaza_content_length_excesivo_sin_leer_el_cuerpo():
    grande = str(descarga.LIMITE_BYTES + 1)
    sesion = SesionFalsa(RespuestaFalsa(b"x", headers={"Content-Length": grande}))
    with pytest.raises(ErrorDescarga, match="excede"):
        descargar(sesion, "https://x.test/")


def test_corta_la_lectura_si_el_cuerpo_crece_de_mas(monkeypatch):
    monkeypatch.setattr(descarga, "LIMITE_BYTES", 100)
    sesion = SesionFalsa(RespuestaFalsa(b"x" * 101, headers={}))  # sin Content-Length
    with pytest.raises(ErrorDescarga, match="excede"):
        descargar(sesion, "https://x.test/")


def test_sin_charset_decodifica_utf8_y_no_latin1():
    cuerpo = "Pokémon".encode()
    sesion = SesionFalsa(RespuestaFalsa(cuerpo, headers={"Content-Type": "text/html"}, encoding="ISO-8859-1"))
    assert descargar(sesion, "https://x.test/").texto == "Pokémon"


@pytest.mark.parametrize("error", [requests.ConnectTimeout(), requests.ConnectionError("detalle largo con https://x.test/")])
def test_errores_de_red_se_resumen_al_tipo(error):
    with pytest.raises(ErrorDescarga) as info:
        descargar(SesionFalsa(error=error), "https://x.test/")
    assert str(info.value) == f"red: {type(error).__name__}"
    assert info.value.__cause__ is None  # cadena cortada: sin detalles ni URL


def test_sesion_con_user_agent_honesto():
    sesion = crear_sesion()
    assert sesion.headers["User-Agent"] == USER_AGENT
    assert "rastreador-switch2" in USER_AGENT and "Mozilla" not in USER_AGENT
    assert sesion.max_redirects == descarga.MAX_REDIRECCIONES
