"""El token de Telegram no debe aparecer en NINGUNA salida de un fallo.

Se usa requests de verdad (Session + adaptador HTTP falso), así que la URL con
el token se arma exactamente igual que en producción y el adaptador la mete en
el mensaje de error, como hace urllib3 ("Max retries exceeded with url: ...").
"""

import json
import logging
import traceback

import pytest
import requests
from requests.adapters import HTTPAdapter

from rastreador.notificador import ErrorNotificacion, NotificadorTelegram

TOKEN = "00000:TOKEN_FALSO_de_prueba_no_es_un_token_real"
CHAT_ID = "987654321"


class AdaptadorFalso(HTTPAdapter):
    def __init__(self, status=200, cuerpo=None, error: type[requests.RequestException] | None = None):
        super().__init__()
        self.status, self.cuerpo, self.error = status, cuerpo, error
        self.peticiones: list[requests.PreparedRequest] = []

    def send(self, request, **kwargs):
        self.peticiones.append(request)
        if self.error:
            raise self.error(f"HTTPSConnectionPool(host='api.telegram.org'): Max retries exceeded with url: {request.url}",
                             request=request)
        resp = requests.Response()
        resp.status_code, resp.url, resp.request = self.status, request.url, request
        resp._content = json.dumps(self.cuerpo if self.cuerpo is not None else {"ok": True}).encode()
        return resp


def notificador_con(adaptador: AdaptadorFalso) -> NotificadorTelegram:
    sesion = requests.Session()
    sesion.mount("https://", adaptador)
    return NotificadorTelegram(TOKEN, CHAT_ID, sesion)


def todo_lo_visible(exc: BaseException) -> str:
    """Lo que vería un humano o un log: str, repr, traceback completo y la cadena de causas."""
    partes = [str(exc), repr(exc), "".join(traceback.format_exception(exc))]
    for enlazada in (exc.__cause__, exc.__context__):
        if enlazada is not None:
            partes += [str(enlazada), repr(enlazada)]
    return "\n".join(partes)


def test_envia_texto_plano_al_chat_configurado():
    adaptador = AdaptadorFalso()
    notificador_con(adaptador).enviar("hola <b>no es html</b>")
    peticion = adaptador.peticiones[0]
    assert peticion.url == f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    cuerpo = json.loads(peticion.body)
    assert cuerpo == {"chat_id": CHAT_ID, "text": "hola <b>no es html</b>", "disable_web_page_preview": True}
    assert "parse_mode" not in cuerpo


@pytest.mark.parametrize("error", [requests.ConnectionError, requests.ConnectTimeout, requests.ReadTimeout, requests.exceptions.SSLError])
def test_fallo_de_red_no_filtra_el_token(error):
    adaptador = AdaptadorFalso(error=error)
    with pytest.raises(ErrorNotificacion) as info:
        notificador_con(adaptador).enviar("hola")
    assert TOKEN in adaptador.peticiones[0].url  # el token SÍ iba en la URL...
    visible = todo_lo_visible(info.value)
    assert TOKEN not in visible  # ...pero no aparece en nada de lo que sale
    assert "api.telegram.org" not in visible
    assert info.value.__cause__ is None and info.value.__context__ is None  # cadena cortada
    assert f"fallo de red ({error.__name__})" in str(info.value)


@pytest.mark.parametrize(
    ("status", "cuerpo"),
    [
        (401, {"ok": False, "error_code": 401, "description": "Unauthorized"}),
        (400, {"ok": False, "description": "Bad Request: chat not found"}),
        (200, {"ok": False, "description": "algo raro"}),
        (502, None),
    ],
)
def test_respuesta_de_error_no_filtra_el_token(status, cuerpo):
    adaptador = AdaptadorFalso(status=status, cuerpo=cuerpo if cuerpo is not None else "<html>Bad Gateway</html>")
    with pytest.raises(ErrorNotificacion) as info:
        notificador_con(adaptador).enviar("hola")
    visible = todo_lo_visible(info.value)
    assert TOKEN not in visible
    assert f"HTTP {status}" in str(info.value)


def test_si_telegram_repite_el_token_en_su_descripcion_se_oculta():
    adaptador = AdaptadorFalso(status=400, cuerpo={"ok": False, "description": f"token {TOKEN} inválido"})
    with pytest.raises(ErrorNotificacion) as info:
        notificador_con(adaptador).enviar("hola")
    assert TOKEN not in todo_lo_visible(info.value)
    assert "token *** inválido" in str(info.value)


def test_repr_del_notificador_no_muestra_el_token():
    notificador = NotificadorTelegram(TOKEN, CHAT_ID)
    assert TOKEN not in repr(notificador)
    assert TOKEN not in f"{notificador}"


def test_logs_de_urllib3_en_debug_no_se_escriben_tras_main(caplog):
    """__main__ sube urllib3 a WARNING; aquí se comprueba que eso basta."""
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    with caplog.at_level(logging.DEBUG):
        logging.getLogger("urllib3.connectionpool").debug("POST /bot%s/sendMessage", TOKEN)
    assert TOKEN not in caplog.text


def test_buscar_chats_lee_getupdates():
    actualizaciones = [
        {"update_id": 1, "message": {"chat": {"id": 42, "first_name": "Ana", "last_name": "P"}, "text": "hola"}},
        {"update_id": 2, "message": {"chat": {"id": -100777, "title": "Grupo precios"}, "text": "hola"}},
        {"update_id": 3, "message": {"chat": {"id": 42, "first_name": "Ana", "last_name": "P"}, "text": "otra vez"}},
    ]
    adaptador = AdaptadorFalso(cuerpo={"ok": True, "result": actualizaciones})
    assert notificador_con(adaptador).buscar_chats() == [("42", "Ana P"), ("-100777", "Grupo precios")]
    assert adaptador.peticiones[0].url.endswith("/getUpdates")


def test_buscar_chats_con_fallo_de_red_no_filtra_el_token():
    with pytest.raises(ErrorNotificacion) as info:
        notificador_con(AdaptadorFalso(error=requests.ConnectionError)).buscar_chats()
    assert TOKEN not in todo_lo_visible(info.value)
