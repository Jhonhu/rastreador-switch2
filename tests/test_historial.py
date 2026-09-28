from datetime import UTC, datetime, timedelta, timezone

import pytest

from rastreador.historial import COLUMNAS, ErrorHistorial, agregar_lecturas, leer_lecturas
from rastreador.modelos import Estado, Lectura

from .conftest import FECHA


def lectura(**cambios) -> Lectura:
    datos = {"fecha": FECHA, "producto_id": "sears-estandar", "tienda": "sears", "estado": Estado.OK,
             "precio": 1_399_900, "precio_lista": 1_399_900, "vendedor": "SEARS"} | cambios
    return Lectura(**datos)


def test_ida_y_vuelta_conserva_todo(tmp_path):
    ruta = tmp_path / "data" / "lecturas.csv"
    originales = [
        lectura(),
        lectura(fecha=FECHA + timedelta(days=1), estado=Estado.AGOTADO, precio_lista=None),
        lectura(estado=Estado.ERROR, precio=None, precio_lista=None, vendedor=None, motivo="red: ReadTimeout"),
    ]
    agregar_lecturas(ruta, originales)
    assert leer_lecturas(ruta) == originales


def test_solo_agrega_y_escribe_el_encabezado_una_vez(tmp_path):
    ruta = tmp_path / "lecturas.csv"
    agregar_lecturas(ruta, [lectura()])
    agregar_lecturas(ruta, [lectura(producto_id="otro")])
    lineas = ruta.read_text(encoding="utf-8").splitlines()
    assert lineas[0] == ",".join(COLUMNAS)
    assert len(lineas) == 3
    assert [l.producto_id for l in leer_lecturas(ruta)] == ["sears-estandar", "otro"]


def test_formato_legible_con_fechas_utc_y_finales_lf(tmp_path):
    ruta = tmp_path / "lecturas.csv"
    agregar_lecturas(ruta, [lectura()])
    contenido = ruta.read_bytes()
    assert b"\r\n" not in contenido  # diffs limpios en git aunque se corra en Windows
    assert contenido.decode().splitlines()[1] == "2026-09-28T14:17:03Z,sears-estandar,sears,ok,1399900,1399900,SEARS,"


def test_fecha_con_otra_zona_se_rechaza_en_el_modelo():
    with pytest.raises(ValueError, match="UTC"):
        lectura(fecha=datetime(2026, 9, 28, 8, 17, tzinfo=timezone(timedelta(hours=-6))))
    with pytest.raises(ValueError, match="UTC"):
        lectura(fecha=datetime(2026, 9, 28, 8, 17))  # sin zona


def test_textos_se_aplanan_y_no_arrancan_como_formula(tmp_path):
    ruta = tmp_path / "lecturas.csv"
    agregar_lecturas(ruta, [lectura(vendedor="=HYPERLINK(\"x\")", motivo="línea 1\nlínea 2,\"con comillas\"")])
    leida = leer_lecturas(ruta)[0]
    assert leida.vendedor == "'=HYPERLINK(\"x\")"
    assert leida.motivo == 'línea 1 línea 2,"con comillas"'
    assert len(ruta.read_text(encoding="utf-8").splitlines()) == 2


def test_repara_archivo_sin_salto_final_antes_de_agregar(tmp_path):
    ruta = tmp_path / "lecturas.csv"
    agregar_lecturas(ruta, [lectura()])
    ruta.write_bytes(ruta.read_bytes().rstrip(b"\n"))  # alguien lo editó a mano
    agregar_lecturas(ruta, [lectura(producto_id="otro")])
    assert [l.producto_id for l in leer_lecturas(ruta)] == ["sears-estandar", "otro"]


def test_no_agrega_a_un_archivo_con_otro_formato(tmp_path):
    ruta = tmp_path / "lecturas.csv"
    ruta.write_text("fecha,precio\n2026-01-01,100\n", encoding="utf-8")
    with pytest.raises(ErrorHistorial, match="encabezado"):
        agregar_lecturas(ruta, [lectura()])
    assert ruta.read_text(encoding="utf-8") == "fecha,precio\n2026-01-01,100\n"


def test_fila_corrupta_indica_la_linea(tmp_path):
    ruta = tmp_path / "lecturas.csv"
    agregar_lecturas(ruta, [lectura()])
    with ruta.open("a", encoding="utf-8") as f:
        f.write("2026-09-29T14:17:03Z,x,sears,inventado,1,,,\n")
    with pytest.raises(ErrorHistorial, match="línea 3"):
        leer_lecturas(ruta)


def test_archivo_inexistente_es_historial_vacio(tmp_path):
    assert leer_lecturas(tmp_path / "no-existe.csv") == []


def test_las_fechas_leidas_son_utc(tmp_path):
    ruta = tmp_path / "lecturas.csv"
    agregar_lecturas(ruta, [lectura()])
    assert leer_lecturas(ruta)[0].fecha.tzinfo is UTC
