r"""Convierte una página real descargada en un fixture mínimo para las pruebas.

Conserva solo la ruta real hasta el dato (misma estructura, mismas claves) y
descarta todo lo demás. Úsalo cuando una tienda cambie su HTML:

    .venv\Scripts\python.exe investigacion\sondeo.py C:\temp\html
    .venv\Scripts\python.exe investigacion\recortar_fixtures.py liverpool ^
        C:\temp\html\liverpool_xxxx.html tests\fixtures\liverpool_estandar.html ^
        --url https://www.liverpool.com.mx/tienda/pdp/.../1177646322 --id 1177646322
"""

import argparse
import datetime
import json
import sys
from pathlib import Path

from bs4 import BeautifulSoup

PREFIJO_RSC = "self.__next_f.push("


def elegir(d: dict, claves: list[str]) -> dict:
    return {k: d[k] for k in claves if k in d}


def solo_escalares(d: dict, conservar: tuple[str, ...] = ("priceInfo",)) -> dict:
    return {k: v for k, v in d.items() if not isinstance(v, (dict, list)) or k in conservar}


def script_ld(obj) -> str:
    return f'<script type="application/ld+json">{json.dumps(obj, ensure_ascii=False)}</script>\n'


def script_next(obj) -> str:
    return f'<script id="__NEXT_DATA__" type="application/json">{json.dumps(obj, ensure_ascii=False)}</script>\n'


def ld_producto(sopa: BeautifulSoup) -> dict:
    for t in sopa.find_all("script", type="application/ld+json"):
        try:
            d = json.loads(t.string)
        except (TypeError, ValueError):
            continue
        for it in (d.get("@graph", [d]) if isinstance(d, dict) else d):
            if isinstance(it, dict) and it.get("@type") == "Product":
                return it
    raise SystemExit("sin JSON-LD Product")


def ld_minimo(p: dict) -> dict:
    oferta = p["offers"][0] if isinstance(p["offers"], list) else p["offers"]
    return {
        "@context": "https://schema.org/",
        "@type": "Product",
        "name": p.get("name"),
        "offers": [elegir(oferta, ["@type", "price", "priceCurrency", "availability", "url", "seller"])],
    }


# ---------------------------------------------------------------- por tienda
def recortar_walmart(sopa: BeautifulSoup, _id: str | None) -> str:
    nd = json.loads(sopa.find("script", id="__NEXT_DATA__").string)
    prod = nd["props"]["pageProps"]["initialData"]["data"]["product"]
    pi = prod["priceInfo"]
    producto = {
        **elegir(prod, ["usItemId", "name", "availabilityStatus", "sellerId", "sellerName", "sellerDisplayName", "sellerType"]),
        "priceInfo": {
            "currentPrice": elegir(pi["currentPrice"], ["price", "priceString", "currencyUnit"]),
            "wasPrice": elegir(pi["wasPrice"], ["price", "priceString"]) if pi.get("wasPrice") else None,
        },
    }
    mini = {"props": {"pageProps": {"initialData": {"data": {"product": producto}}}}}
    return "<html><head>\n" + script_ld(ld_minimo(ld_producto(sopa))) + script_next(mini) + "</head><body></body></html>\n"


def recortar_gameplanet(sopa: BeautifulSoup, _id: str | None) -> str:
    grafo = {"@context": "https://schema.org/", "@graph": [
        {"@type": "BreadcrumbList", "itemListElement": []},
        ld_minimo(ld_producto(sopa)),
    ]}
    return "<html><head>\n" + script_ld(grafo) + "</head><body></body></html>\n"


def recortar_sears(sopa: BeautifulSoup, _id: str | None) -> str:
    nd = json.loads(sopa.find("script", id="__NEXT_DATA__").string)
    data = nd["props"]["pageProps"]["response"]["data"]
    mini = {
        "props": {"pageProps": {"response": {"data": {
            **elegir(data, ["id", "title", "sku", "ean", "sale_price", "price", "stock", "status"]),
            "store": elegir(data["store"], ["id", "name"]),
        }}}},
        "page": "/producto/[[...producto]]",
    }
    return "<html><head>\n" + script_next(mini) + "</head><body></body></html>\n"


# ---------------------------------------------------------------- Liverpool (RSC)
def flujo_rsc(sopa: BeautifulSoup) -> str:
    partes = []
    for t in sopa.find_all("script"):
        c = (t.string or "").strip()
        if c.startswith(PREFIJO_RSC):
            arr = json.loads(c[len(PREFIJO_RSC):].rstrip(";").rstrip(")"))
            if arr[0] == 1:
                partes.append(arr[1])
    return "".join(partes)


def podar_hasta(o, es_objetivo):
    """Copia de `o` que conserva solo las ramas que llevan a nodos objetivo."""
    if isinstance(o, dict):
        if es_objetivo(o):
            return o
        hijos = {k: podar_hasta(v, es_objetivo) for k, v in o.items()}
        hijos = {k: v for k, v in hijos.items() if v is not None}
        return hijos or None
    if isinstance(o, list):
        hijos = [x for x in (podar_hasta(v, es_objetivo) for v in o) if x is not None]
        return hijos or None
    return None


def limpiar_objetivo(d):
    """Nodo `product`: productInfo con escalares + priceInfo + variants; y offersListVariants."""
    if isinstance(d, dict):
        if isinstance(d.get("productInfo"), dict):
            pi = d["productInfo"]
            info = {k: v for k, v in solo_escalares(pi).items() if k != "description"}
            info["variants"] = [solo_escalares(x) for x in pi.get("variants", [])]
            return {"productInfo": info, **elegir(d, ["offersListVariants"])}
        return {k: limpiar_objetivo(v) for k, v in d.items()}
    if isinstance(d, list):
        return [limpiar_objetivo(v) for v in d]
    return d


def limpiar_senuelo(d):
    """Un solo producto señuelo: en cada lista queda solo el primer elemento."""
    if isinstance(d, dict):
        if "priceInfo" in d and "productId" in d:
            return solo_escalares(d)
        return {k: limpiar_senuelo(v) for k, v in d.items()}
    if isinstance(d, list):
        return [limpiar_senuelo(d[0])] if d else []
    return d


def recortar_liverpool(sopa: BeautifulSoup, sku: str | None) -> str:
    if not sku:
        raise SystemExit("Liverpool requiere --id")

    def es_objetivo(d):
        return isinstance(d.get("productInfo"), dict) and d["productInfo"].get("productId") == sku

    def es_senuelo(d):
        nombre = str(d.get("name") or d.get("title") or "").lower()
        return d.get("productId") not in (None, sku) and isinstance(d.get("priceInfo"), dict) and "switch" in nombre

    objetivo = senuelo = None
    for linea in flujo_rsc(sopa).split("\n"):
        i = linea.find(":")
        cuerpo = linea[i + 1:]
        if i <= 0 or cuerpo[:1] not in "[{":
            continue
        try:
            o = json.loads(cuerpo)
        except ValueError:
            continue
        if objetivo is None and (podado := podar_hasta(o, es_objetivo)):
            objetivo = (linea[:i], limpiar_objetivo(podado))
        if senuelo is None and (cand := podar_hasta(o, es_senuelo)):
            senuelo = (linea[:i], limpiar_senuelo(cand))
    if objetivo is None:
        raise SystemExit(f"no encontré productInfo con productId {sku}")
    lineas = []
    if senuelo:
        if senuelo[0] == objetivo[0]:  # misma línea RSC de origen: ids únicos como en el stream real
            senuelo = (senuelo[0] + "0", senuelo[1])
        lineas.append(f"{senuelo[0]}:{json.dumps(senuelo[1], ensure_ascii=False, separators=(',', ':'))}")
    lineas.append(f"{objetivo[0]}:{json.dumps(objetivo[1], ensure_ascii=False, separators=(',', ':'))}")
    texto = "\n".join(lineas) + "\n"
    corte = len(texto) // 2  # el stream real parte las líneas entre varios push
    scripts = "<script>(self.__next_f=self.__next_f||[]).push([0]);self.__next_f.push([2,null])</script>\n"
    for parte in (texto[:corte], texto[corte:]):
        scripts += f"<script>self.__next_f.push({json.dumps([1, parte], ensure_ascii=False)})</script>\n"
    return "<html><head></head><body>\n" + scripts + "</body></html>\n"


def recortar_liverpool_busqueda(sopa: BeautifulSoup, _id: str | None) -> str:
    """Página /tienda?s=...: consolas + hasta 4 tarjetas más (ruido realista), solo title/productId/priceInfo."""
    def es_tarjeta(d):
        return isinstance(d.get("productId"), str) and isinstance(d.get("title"), str) and isinstance(d.get("priceInfo"), dict)

    lineas_json = []
    for linea in flujo_rsc(sopa).split("\n"):
        i = linea.find(":")
        if i > 0 and linea[i + 1:i + 2] in "[{":
            try:
                lineas_json.append((linea[:i], json.loads(linea[i + 1:])))
            except ValueError:
                pass
    elegidas: set[str] = set()
    ruido = 0
    for _, o in lineas_json:
        pendientes = [o]
        while pendientes:
            n = pendientes.pop()
            if isinstance(n, dict):
                if es_tarjeta(n) and n["productId"] not in elegidas:
                    titulo = n["title"].lower()
                    if titulo.startswith("consola") and "256" in titulo:  # consolas Switch 2
                        elegidas.add(n["productId"])
                    elif ruido < 4:
                        elegidas.add(n["productId"])
                        ruido += 1
                pendientes.extend(n.values())
            elif isinstance(n, list):
                pendientes.extend(n)

    def es_elegida(d):
        return es_tarjeta(d) and d["productId"] in elegidas

    def limpiar(d):
        if isinstance(d, dict):
            if es_elegida(d):
                return elegir(d, ["productId", "title", "priceInfo"])
            return {k: limpiar(v) for k, v in d.items()}
        if isinstance(d, list):
            return [limpiar(v) for v in d]
        return d

    lineas = []
    for lid, o in lineas_json:
        if (podado := podar_hasta(o, es_elegida)):
            lineas.append(f"{lid}:{json.dumps(limpiar(podado), ensure_ascii=False, separators=(',', ':'))}")
    if not lineas:
        raise SystemExit("no encontré tarjetas de producto")
    texto = "\n".join(lineas) + "\n"
    scripts = "".join(f"<script>self.__next_f.push({json.dumps([1, texto], ensure_ascii=False)})</script>\n")
    return "<html><head></head><body>\n" + scripts + "</body></html>\n"


RECORTADORES = {
    "liverpool": recortar_liverpool,
    "liverpool-busqueda": recortar_liverpool_busqueda,
    "walmart": recortar_walmart,
    "gameplanet": recortar_gameplanet,
    "sears": recortar_sears,
}


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("tienda", choices=sorted(RECORTADORES))
    ap.add_argument("entrada", type=Path)
    ap.add_argument("salida", type=Path)
    ap.add_argument("--url", required=True, help="URL de origen (queda documentada en el fixture)")
    ap.add_argument("--id", help="id del producto (Liverpool: número al final de la URL)")
    args = ap.parse_args()
    sopa = BeautifulSoup(args.entrada.read_text(encoding="utf-8"), "html.parser")
    cuerpo = RECORTADORES[args.tienda](sopa, args.id)
    hoy = datetime.date.today().isoformat()
    encabezado = f"<!-- Fixture recortado de {args.url}\n     Descargado {hoy} con User-Agent honesto (investigacion/recortar_fixtures.py). -->\n"
    args.salida.write_text(encabezado + cuerpo, encoding="utf-8")
    print(f"{args.salida}: {len(encabezado + cuerpo):,} bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
