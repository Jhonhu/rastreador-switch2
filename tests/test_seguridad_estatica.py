"""Reglas de seguridad que se revisan leyendo archivos: workflows y dashboard.

Si alguien (o Dependabot) cambia algo que rompa una regla, la prueba falla en el PR.
"""

import re
from pathlib import Path

import pytest
import yaml

RAIZ = Path(__file__).parent.parent
WORKFLOWS = sorted((RAIZ / ".github" / "workflows").glob("*.yml"))
DOCS = RAIZ / "docs"
SHA = re.compile(r"[^@\s]+@[0-9a-f]{40}")


def cargar(ruta: Path) -> dict:
    datos = yaml.safe_load(ruta.read_text(encoding="utf-8"))
    datos["on"] = datos.pop(True, datos.get("on"))  # YAML 1.1 lee la clave `on:` como True
    return datos


def test_hay_workflows():
    assert {w.name for w in WORKFLOWS} >= {"rastreo.yml", "pruebas.yml", "sondeo.yml"}


@pytest.mark.parametrize("ruta", WORKFLOWS, ids=lambda r: r.name)
def test_actions_fijadas_por_sha(ruta):
    for job in cargar(ruta)["jobs"].values():
        for paso in job["steps"]:
            if "uses" in paso:
                assert SHA.fullmatch(paso["uses"]), f"{ruta.name}: {paso['uses']} no está fijada por SHA"


@pytest.mark.parametrize("ruta", WORKFLOWS, ids=lambda r: r.name)
def test_permisos_explicitos_y_minimos(ruta):
    flujo = cargar(ruta)
    assert "permissions" in flujo, "sin 'permissions' el token hereda los permisos por omisión del repo"
    for nombre, job in flujo["jobs"].items():
        efectivos = job.get("permissions", flujo["permissions"]) or {}
        escrituras = {k for k, v in efectivos.items() if v == "write"}
        assert escrituras <= {"contents"}, f"{ruta.name}/{nombre} pide {escrituras}"
        if ruta.name != "rastreo.yml":
            assert not escrituras, f"{ruta.name} no necesita escribir"


@pytest.mark.parametrize("ruta", WORKFLOWS, ids=lambda r: r.name)
def test_secretos_solo_en_el_paso_que_los_usa(ruta):
    flujo = cargar(ruta)
    assert "secrets." not in yaml.safe_dump(flujo.get("env", {})), "secretos a nivel de workflow"
    for job in flujo["jobs"].values():
        assert "secrets." not in yaml.safe_dump(job.get("env", {})), "secretos a nivel de job"
        for paso in job["steps"]:
            assert "secrets." not in paso.get("run", ""), "un secreto interpolado en `run` puede acabar en el log"


def test_cron_dos_veces_al_dia_en_minuto_no_redondo():
    cron = cargar(RAIZ / ".github" / "workflows" / "rastreo.yml")["on"]["schedule"][0]["cron"]
    minuto, horas, *_ = cron.split()
    assert minuto not in {"0", "00", "15", "30", "45"}
    assert horas == "2,14"  # 02:xx y 14:xx UTC = 20:xx y 08:xx en CDMX (UTC-6)


# ------------------------------------------------------------------ dashboard
def test_csp_estricta_en_la_pagina():
    html = (DOCS / "index.html").read_text(encoding="utf-8")
    csp = re.search(r'http-equiv="Content-Security-Policy"\s+content="([^"]+)"', html).group(1)
    for directiva in ["default-src 'none'", "script-src 'self'", "style-src 'self'", "base-uri 'none'", "form-action 'none'"]:
        assert directiva in csp
    assert "unsafe-inline" not in csp and "unsafe-eval" not in csp


def test_la_pagina_no_carga_nada_externo_ni_inline():
    html = (DOCS / "index.html").read_text(encoding="utf-8")
    assert not re.search(r'<(script|link)[^>]+(src|href)="(https?:)?//', html), "recurso externo sin SRI"
    assert not re.search(r"<script(?![^>]*\bsrc=)[^>]*>", html), "script inline (lo bloquearía la CSP)"
    assert "<style" not in html and " style=" not in html
    assert not re.search(r"\son[a-z]+=", html), "manejador de eventos inline"


def test_app_js_no_inserta_html_con_datos():
    js = (DOCS / "app.js").read_text(encoding="utf-8")
    codigo = "\n".join(l for l in js.splitlines() if not l.lstrip().startswith("//"))
    for peligro in ["innerHTML", "outerHTML", "insertAdjacentHTML", "document.write", "eval(", "new Function"]:
        assert peligro not in codigo, peligro
    assert 'url.protocol === "https:"' in js  # los enlaces se filtran a https://
