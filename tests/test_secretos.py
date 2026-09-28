import pytest

from rastreador.secretos import ErrorSecretos, cargar_env, leer_secretos

TOKEN = "00000:TOKEN_FALSO_de_prueba_no_es_un_token_real"


def test_lee_secretos_validos():
    s = leer_secretos({"TELEGRAM_TOKEN": f" {TOKEN} ", "TELEGRAM_CHAT_ID": "-100123"})
    assert (s.token, s.chat_id) == (TOKEN, "-100123")
    assert TOKEN not in repr(s)


@pytest.mark.parametrize(
    ("entorno", "fragmento"),
    [
        ({}, "TELEGRAM_TOKEN, TELEGRAM_CHAT_ID"),
        ({"TELEGRAM_TOKEN": TOKEN}, "TELEGRAM_CHAT_ID"),
        ({"TELEGRAM_TOKEN": "no-es-un-token", "TELEGRAM_CHAT_ID": "1"}, "formato"),
        ({"TELEGRAM_TOKEN": TOKEN, "TELEGRAM_CHAT_ID": "@canal"}, "número"),
    ],
)
def test_errores_claros_sin_revelar_valores(entorno, fragmento):
    with pytest.raises(ErrorSecretos, match=fragmento) as info:
        leer_secretos(entorno)
    assert TOKEN not in str(info.value)
    assert "no-es-un-token" not in str(info.value)


def test_env_local_no_pisa_variables_existentes(tmp_path):
    env = tmp_path / ".env"
    env.write_text('# comentario\nTELEGRAM_TOKEN="desde-archivo"\nTELEGRAM_CHAT_ID=42\nlinea rara\n', encoding="utf-8")
    entorno = {"TELEGRAM_TOKEN": "desde-actions"}
    cargar_env(env, entorno)
    assert entorno == {"TELEGRAM_TOKEN": "desde-actions", "TELEGRAM_CHAT_ID": "42"}


def test_env_inexistente_no_hace_nada(tmp_path):
    entorno: dict[str, str] = {}
    cargar_env(tmp_path / ".env", entorno)
    assert entorno == {}
