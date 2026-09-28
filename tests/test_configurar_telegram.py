from rastreador import configurar_telegram
from rastreador.configurar_telegram import main

TOKEN = "00000:TOKEN_FALSO_de_prueba_no_es_un_token_real"


class TelegramFalso:
    enviados: list[tuple[str, str, str]] = []

    def __init__(self, token, chat_id):
        self.token, self.chat_id = token, chat_id

    def buscar_chats(self):
        return [("42", "Ana")]

    def enviar(self, texto):
        TelegramFalso.enviados.append((self.token, self.chat_id, texto))


def test_chat_id_muestra_los_chats_sin_el_token(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(configurar_telegram, "RAIZ", tmp_path)
    assert main(["chat-id"], entorno={"TELEGRAM_TOKEN": TOKEN}, fabrica=TelegramFalso) == 0
    salida = capsys.readouterr().out
    assert "42  Ana" in salida
    assert TOKEN not in salida


def test_chat_id_sin_token_explica_que_falta(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(configurar_telegram, "RAIZ", tmp_path)
    assert main(["chat-id"], entorno={}, fabrica=TelegramFalso) == 2
    assert "TELEGRAM_TOKEN" in capsys.readouterr().err


def test_probar_envia_con_los_secretos_del_env(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(configurar_telegram, "RAIZ", tmp_path)
    (tmp_path / ".env").write_text(f"TELEGRAM_TOKEN={TOKEN}\nTELEGRAM_CHAT_ID=42\n", encoding="utf-8")
    TelegramFalso.enviados.clear()
    assert main(["probar"], entorno={}, fabrica=TelegramFalso) == 0
    assert TelegramFalso.enviados[0][:2] == (TOKEN, "42")
    assert TOKEN not in capsys.readouterr().out
