"""Códigos de salida del CLI (lo que ve GitHub Actions). Sin red: descargador falso."""

from pathlib import Path

from rastreador.__main__ import main
from rastreador.descarga import ErrorDescarga, Respuesta

from .conftest import URLS, leer_fixture

RAIZ = Path(__file__).parent.parent
TOKEN = "00000:TOKEN_FALSO_de_prueba_no_es_un_token_real"

CONFIG = """
ajustes:
  lecturas_minimas: 3
  precio_min_valido: 5000
  precio_max_valido: 25000
  precio_objetivo: 11000
productos:
  - id: walmart-estandar
    tienda: walmart
    version: nacional
    descripcion: Switch 2
    url: {url}
"""


def preparar(tmp_path) -> list[str]:
    config = tmp_path / "productos.yaml"
    config.write_text(CONFIG.format(url=URLS["walmart_vende_walmart"]), encoding="utf-8")
    return ["--config", str(config), "--historial", str(tmp_path / "lecturas.csv"),
            "--dashboard", str(tmp_path / "docs" / "datos.json")]


def pagina_real(url: str) -> Respuesta:
    return Respuesta(200, url, leer_fixture("walmart_vende_walmart"))


def red_caida(url: str) -> Respuesta:
    raise ErrorDescarga("red: ConnectionError")


def test_sin_notificar_muestra_la_alerta_y_termina_bien(tmp_path, capsys):
    codigo = main(preparar(tmp_path) + ["--sin-notificar"], entorno={}, descargador=pagina_real)
    salida = capsys.readouterr().out
    assert codigo == 0
    assert "ok            walmart-estandar           $10,790.00 (efectivo $10,790.00)" in salida
    assert "Bajó del objetivo de $11,000.00" in salida  # impreso, no enviado
    assert "1 alerta(s)" in salida


def test_todas_fallan_sale_con_1_pero_guarda_el_registro(tmp_path, capsys):
    args = preparar(tmp_path)
    assert main(args + ["--sin-notificar"], entorno={}, descargador=red_caida) == 1
    assert "todas las lecturas fallaron" in capsys.readouterr().err
    assert "red: ConnectionError" in (tmp_path / "lecturas.csv").read_text(encoding="utf-8")
    assert '"estado": "error"' in (tmp_path / "docs" / "datos.json").read_text(encoding="utf-8")


def test_sin_secretos_y_sin_bandera_falla_antes_de_tocar_la_red(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr("rastreador.__main__.RAIZ", tmp_path)  # sin .env local
    llamadas = []
    codigo = main(preparar(tmp_path), entorno={}, descargador=lambda url: llamadas.append(url))
    assert codigo == 2
    assert llamadas == []
    assert "TELEGRAM_TOKEN" in capsys.readouterr().err


def test_configuracion_invalida_sale_con_2(tmp_path, capsys):
    config = tmp_path / "productos.yaml"
    config.write_text("ajustes: {}\nproductos: []\n", encoding="utf-8")
    assert main(["--config", str(config), "--sin-notificar"], entorno={}) == 2
    assert "configuración inválida" in capsys.readouterr().err


def test_fallo_de_telegram_sale_con_3_sin_mostrar_el_token(tmp_path, capsys, monkeypatch):
    class TelegramCaido:
        def __init__(self, token, chat_id):
            self.token = token

        def enviar(self, texto):
            from rastreador.notificador import ErrorNotificacion
            raise ErrorNotificacion("Telegram: fallo de red (ConnectTimeout)")

    monkeypatch.setattr("rastreador.__main__.NotificadorTelegram", TelegramCaido)
    monkeypatch.setattr("rastreador.__main__.RAIZ", tmp_path)
    entorno = {"TELEGRAM_TOKEN": TOKEN, "TELEGRAM_CHAT_ID": "42"}
    assert main(preparar(tmp_path), entorno=entorno, descargador=pagina_real) == 3
    salida = capsys.readouterr()
    assert TOKEN not in salida.out + salida.err
    assert (tmp_path / "lecturas.csv").exists()
    assert (tmp_path / "docs" / "datos.json").exists()


def test_el_env_local_se_usa_si_no_hay_variables(tmp_path, monkeypatch):
    enviados = []

    class TelegramEspia:
        def __init__(self, token, chat_id):
            enviados.append((token, chat_id))

        def enviar(self, texto):
            pass

    monkeypatch.setattr("rastreador.__main__.NotificadorTelegram", TelegramEspia)
    monkeypatch.setattr("rastreador.__main__.RAIZ", tmp_path)
    (tmp_path / ".env").write_text(f"TELEGRAM_TOKEN={TOKEN}\nTELEGRAM_CHAT_ID=42\n", encoding="utf-8")
    assert main(preparar(tmp_path), entorno={}, descargador=pagina_real) == 0
    assert enviados == [(TOKEN, "42")]
