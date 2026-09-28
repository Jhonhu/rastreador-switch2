"""Carga y validación de productos.yaml.

Reglas: yaml.safe_load siempre; claves desconocidas = error (atrapa typos);
solo https y solo los dominios de la tienda declarada. Se juntan TODOS los
errores antes de fallar, para corregir el archivo de una sola vez.
"""

import re
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import yaml

from .dinero import a_centavos
from .modelos import Ajustes, Configuracion, Producto, Version, Vigilancia
from .tiendas import TIENDAS

PATRON_ID = re.compile(r"[a-z0-9][a-z0-9-]{0,49}")
CLAVES_RAIZ = {"ajustes", "productos", "vigilancias"}
CLAVES_VIGILANCIA = {"id", "tienda", "busqueda", "requiere"}
CLAVES_AJUSTES = {"lecturas_minimas", "precio_min_valido", "precio_max_valido", "precio_objetivo", "baja_minima_alerta"}
CLAVES_PRODUCTO = {
    "id", "tienda", "url", "version", "descripcion",
    "valor_extra", "precio_objetivo", "permitir_terceros",
}


class ErrorConfiguracion(Exception):
    def __init__(self, errores: list[str]):
        self.errores = errores
        super().__init__("configuración inválida:\n- " + "\n- ".join(errores))


def cargar_configuracion(ruta: Path) -> Configuracion:
    return interpretar_configuracion(ruta.read_text(encoding="utf-8"))


def interpretar_configuracion(texto: str) -> Configuracion:
    try:
        crudo = yaml.safe_load(texto)  # NUNCA yaml.load: puede construir objetos Python
    except yaml.YAMLError as exc:
        raise ErrorConfiguracion([f"YAML inválido: {exc}"]) from None

    errores: list[str] = []
    if not isinstance(crudo, dict):
        raise ErrorConfiguracion(["el archivo debe ser un mapa con 'ajustes' y 'productos'"])
    _claves_desconocidas(crudo, CLAVES_RAIZ, "raíz", errores)

    ajustes = _validar_ajustes(crudo.get("ajustes"), errores)
    productos = _validar_productos(crudo.get("productos"), errores)
    vigilancias = _validar_vigilancias(crudo.get("vigilancias", []), errores)
    if errores:
        raise ErrorConfiguracion(errores)
    return Configuracion(ajustes=ajustes, productos=tuple(productos), vigilancias=tuple(vigilancias))


# ------------------------------------------------------------------ ajustes
def _validar_ajustes(crudo: Any, errores: list[str]) -> Ajustes | None:
    if not isinstance(crudo, dict):
        errores.append("falta la sección 'ajustes'")
        return None
    _claves_desconocidas(crudo, CLAVES_AJUSTES, "ajustes", errores)
    lecturas = crudo.get("lecturas_minimas")
    if not _es_entero(lecturas) or lecturas < 0:
        errores.append("ajustes.lecturas_minimas debe ser un entero >= 0")
    minimo = _pesos(crudo.get("precio_min_valido"), "ajustes.precio_min_valido", errores, obligatorio=True)
    maximo = _pesos(crudo.get("precio_max_valido"), "ajustes.precio_max_valido", errores, obligatorio=True)
    objetivo = _pesos(crudo.get("precio_objetivo"), "ajustes.precio_objetivo", errores)
    baja = _pesos(crudo.get("baja_minima_alerta", 0), "ajustes.baja_minima_alerta", errores, obligatorio=True)
    if minimo is not None and maximo is not None and minimo >= maximo:
        errores.append("ajustes.precio_min_valido debe ser menor que precio_max_valido")
    if None in (minimo, maximo, baja) or not _es_entero(lecturas):
        return None
    return Ajustes(
        lecturas_minimas=lecturas, precio_min_valido=minimo, precio_max_valido=maximo,
        precio_objetivo=objetivo, baja_minima_alerta=baja,
    )


# ------------------------------------------------------------------ productos
def _validar_productos(crudo: Any, errores: list[str]) -> list[Producto]:
    if not isinstance(crudo, list) or not crudo:
        errores.append("'productos' debe ser una lista con al menos un producto")
        return []
    productos = [p for i, item in enumerate(crudo) if (p := _validar_producto(item, i, errores))]
    _sin_repetidos([p.id for p in productos], "id", errores)
    _sin_repetidos([p.url for p in productos], "url", errores)
    return productos


def _validar_producto(crudo: Any, indice: int, errores: list[str]) -> Producto | None:
    donde = f"productos[{indice}]"
    if not isinstance(crudo, dict):
        errores.append(f"{donde} debe ser un mapa")
        return None
    donde = f"{donde} ({crudo.get('id', 'sin id')})"
    antes = len(errores)
    _claves_desconocidas(crudo, CLAVES_PRODUCTO, donde, errores)

    id_ = crudo.get("id")
    if not isinstance(id_, str) or not PATRON_ID.fullmatch(id_):
        errores.append(f"{donde}: id debe ser minúsculas, dígitos y guiones (máx. 50)")
    tienda = crudo.get("tienda")
    if tienda not in TIENDAS:
        errores.append(f"{donde}: tienda desconocida {tienda!r}; soportadas: {', '.join(sorted(TIENDAS))}")
    url = crudo.get("url")
    if not isinstance(url, str):
        errores.append(f"{donde}: falta url")
    elif tienda in TIENDAS:
        errores.extend(f"{donde}: {e}" for e in errores_de_url(url, tienda))
    version = crudo.get("version")
    if version not in {v.value for v in Version}:
        errores.append(f"{donde}: version debe ser una de {', '.join(v.value for v in Version)}")
    descripcion = crudo.get("descripcion")
    if not isinstance(descripcion, str) or not descripcion.strip() or len(descripcion) > 200:
        errores.append(f"{donde}: descripcion es obligatoria (máx. 200 caracteres)")
    valor_extra = _pesos(crudo.get("valor_extra", 0), f"{donde}.valor_extra", errores, obligatorio=True)
    objetivo = _pesos(crudo.get("precio_objetivo"), f"{donde}.precio_objetivo", errores)
    terceros = crudo.get("permitir_terceros", False)
    if not isinstance(terceros, bool):
        errores.append(f"{donde}: permitir_terceros debe ser true o false")

    if len(errores) > antes:
        return None
    return Producto(
        id=id_, tienda=tienda, url=url, version=Version(version), descripcion=descripcion.strip(),
        valor_extra=valor_extra, precio_objetivo=objetivo, permitir_terceros=terceros,
    )


# ------------------------------------------------------------------ vigilancias
def _validar_vigilancias(crudo: Any, errores: list[str]) -> list[Vigilancia]:
    if not isinstance(crudo, list):
        errores.append("'vigilancias' debe ser una lista")
        return []
    vigilancias = [v for i, item in enumerate(crudo) if (v := _validar_vigilancia(item, i, errores))]
    _sin_repetidos([v.id for v in vigilancias], "id de vigilancia", errores)
    return vigilancias


def _validar_vigilancia(crudo: Any, indice: int, errores: list[str]) -> Vigilancia | None:
    donde = f"vigilancias[{indice}]"
    if not isinstance(crudo, dict):
        errores.append(f"{donde} debe ser un mapa")
        return None
    donde = f"{donde} ({crudo.get('id', 'sin id')})"
    antes = len(errores)
    _claves_desconocidas(crudo, CLAVES_VIGILANCIA, donde, errores)
    id_ = crudo.get("id")
    if not isinstance(id_, str) or not PATRON_ID.fullmatch(id_):
        errores.append(f"{donde}: id debe ser minúsculas, dígitos y guiones (máx. 50)")
    tienda = crudo.get("tienda")
    if tienda not in TIENDAS or TIENDAS[tienda].url_busqueda is None:
        con_buscador = sorted(n for n, t in TIENDAS.items() if t.url_busqueda)
        errores.append(f"{donde}: la tienda {tienda!r} no admite vigilancias; admiten: {', '.join(con_buscador)}")
    busqueda = crudo.get("busqueda")
    if not isinstance(busqueda, str) or not busqueda.strip() or len(busqueda) > 100:
        errores.append(f"{donde}: busqueda es obligatoria (máx. 100 caracteres)")
    requiere = crudo.get("requiere")
    if (not isinstance(requiere, list) or not requiere
            or not all(isinstance(p, str) and p.strip() for p in requiere)):
        errores.append(f"{donde}: requiere debe ser una lista de palabras que el nombre debe contener")
    if len(errores) > antes:
        return None
    return Vigilancia(id=id_, tienda=tienda, busqueda=busqueda.strip(), requiere=tuple(p.strip() for p in requiere))


def errores_de_url(url: str, tienda: str) -> list[str]:
    """Lista blanca: https, host exacto de la tienda, sin credenciales ni puerto, ruta de producto."""
    if any(c.isspace() or ord(c) < 32 for c in url):
        return ["la url contiene espacios o caracteres de control"]
    partes = urlsplit(url)
    errores = []
    if partes.scheme != "https":
        errores.append("la url debe usar https")
    if partes.username is not None or partes.password is not None:
        errores.append("la url no debe llevar usuario ni contraseña")
    try:
        if partes.port is not None:
            errores.append("la url no debe llevar puerto")
    except ValueError:
        errores.append("la url tiene un puerto inválido")
    dominios = TIENDAS[tienda].dominios
    if partes.hostname not in dominios:
        errores.append(f"el dominio {partes.hostname!r} no es de {tienda} ({', '.join(sorted(dominios))})")
    elif not TIENDAS[tienda].patron_ruta.fullmatch(partes.path):
        errores.append(f"la ruta {partes.path!r} no parece una página de producto de {tienda}")
    return errores


# ------------------------------------------------------------------ auxiliares
def _es_entero(valor: Any) -> bool:
    return isinstance(valor, int) and not isinstance(valor, bool)


def _pesos(valor: Any, campo: str, errores: list[str], obligatorio: bool = False) -> int | None:
    """Importe en pesos (YAML) -> centavos. None si falta y no es obligatorio."""
    if valor is None:
        if obligatorio:
            errores.append(f"falta {campo}")
        return None
    if isinstance(valor, bool) or not isinstance(valor, (int, float)):
        errores.append(f"{campo} debe ser un número en pesos, no {valor!r}")
        return None
    try:
        return a_centavos(valor)
    except ValueError as exc:
        errores.append(f"{campo}: {exc}")
        return None


def _claves_desconocidas(crudo: dict, permitidas: set[str], donde: str, errores: list[str]) -> None:
    for clave in sorted(set(crudo) - permitidas, key=str):
        errores.append(f"{donde}: clave desconocida {clave!r}")


def _sin_repetidos(valores: list[str], campo: str, errores: list[str]) -> None:
    vistos: set[str] = set()
    for valor in valores:
        if valor in vistos:
            errores.append(f"{campo} repetido: {valor}")
        vistos.add(valor)
