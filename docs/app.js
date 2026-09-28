// Dashboard del rastreador. Lee datos.json (generado por rastreador/dashboard.py) y
// construye todo con createElement/textContent: los textos vienen de las tiendas y
// NUNCA se insertan como HTML (nada de innerHTML).
"use strict";

const ZONA = "America/Mexico_City";
const SVG = "http://www.w3.org/2000/svg";
const MAX_SERIES_CON_COLOR = 8; // la paleta categórica tiene 8 tonos; no se inventan más

const pesos = new Intl.NumberFormat("es-MX", { style: "currency", currency: "MXN" });
const pesosCortos = new Intl.NumberFormat("es-MX", { style: "currency", currency: "MXN", maximumFractionDigits: 0 });
const fechaHora = new Intl.DateTimeFormat("es-MX", { timeZone: ZONA, dateStyle: "medium", timeStyle: "short" });
const fechaCorta = new Intl.DateTimeFormat("es-MX", { timeZone: ZONA, day: "numeric", month: "short" });
const fechaLarga = new Intl.DateTimeFormat("es-MX", { timeZone: ZONA, weekday: "short", day: "numeric", month: "short", year: "numeric" });

const ESTADOS = {
  ok:            { texto: "En venta",       icono: "✓", clase: "estado-bien" },
  agotado:       { texto: "Agotado",        icono: "–", clase: "estado-aviso" },
  tercero:       { texto: "Vende un tercero", icono: "!", clase: "estado-serio" },
  no_encontrado: { texto: "URL caducada",   icono: "?", clase: "estado-critico" },
  bloqueado:     { texto: "Bloqueado",      icono: "✕", clase: "estado-critico" },
  error:         { texto: "Error",          icono: "✕", clase: "estado-critico" },
  sin_datos:     { texto: "Sin datos",      icono: "…", clase: "estado-sin" },
};

// ------------------------------------------------------------------ utilidades DOM
function el(etiqueta, props = {}, ...hijos) {
  const nodo = document.createElement(etiqueta);
  for (const [clave, valor] of Object.entries(props)) {
    if (clave === "clase") nodo.className = valor;
    else if (clave === "texto") nodo.textContent = valor;
    else nodo.setAttribute(clave, valor);
  }
  for (const hijo of hijos) if (hijo != null) nodo.append(hijo);
  return nodo;
}

function svg(etiqueta, atributos = {}) {
  const nodo = document.createElementNS(SVG, etiqueta);
  for (const [clave, valor] of Object.entries(atributos)) nodo.setAttribute(clave, String(valor));
  return nodo;
}

/** Solo enlaces https:// ; cualquier otra cosa (javascript:, data:, http:) se muestra como texto. */
function urlSegura(texto) {
  try {
    const url = new URL(texto);
    return url.protocol === "https:" ? url.href : null;
  } catch {
    return null;
  }
}

const dinero = (centavos) => (centavos == null ? "—" : pesos.format(centavos / 100));
const claseSerie = (i) => (i < MAX_SERIES_CON_COLOR ? `serie-${i + 1}` : "serie-otra");
const nombreTienda = (t) => t.charAt(0).toUpperCase() + t.slice(1);
const nombreProducto = (p) => `${nombreTienda(p.tienda)} · ${p.descripcion}`;

// ------------------------------------------------------------------ arranque
async function iniciar() {
  let datos;
  try {
    const respuesta = await fetch("datos.json", { cache: "no-store" });
    if (!respuesta.ok) throw new Error(`HTTP ${respuesta.status}`);
    datos = await respuesta.json();
  } catch (error) {
    const aviso = document.getElementById("error-carga");
    aviso.textContent = `No se pudieron cargar los datos (${error.message}).`;
    aviso.hidden = false;
    return;
  }
  const productos = datos.productos.map((p, i) => ({ ...p, clase: claseSerie(i) }));
  document.getElementById("actualizado").textContent = `Actualizado: ${fechaHora.format(new Date(datos.generado_utc))}`;
  pintarDestacado(datos, productos);
  pintarTablaProductos(productos);
  pintarLeyenda(productos);
  pintarTablaHistorial(productos);
  const grafica = new Grafica(document.getElementById("grafica"), productos, datos.precio_objetivo);
  new ResizeObserver(() => grafica.dibujar()).observe(document.getElementById("grafica"));
}

// ------------------------------------------------------------------ cifra destacada
function pintarDestacado(datos, productos) {
  const valor = document.getElementById("mejor-valor");
  const detalle = document.getElementById("mejor-detalle");
  if (!datos.mejor) {
    valor.textContent = "—";
    detalle.textContent = productos.every((p) => p.estado === "sin_datos")
      ? "Aún no hay lecturas: aparecerán después de la primera ejecución diaria."
      : "Ningún producto está en venta por la propia tienda en la última lectura.";
    return;
  }
  const producto = productos.find((p) => p.id === datos.mejor.producto_id);
  valor.textContent = dinero(datos.mejor.efectivo);
  detalle.replaceChildren(enlaceProducto(producto, nombreProducto(producto)));
  if (datos.precio_objetivo != null) {
    const diferencia = datos.mejor.efectivo - datos.precio_objetivo;
    const frase = diferencia <= 0
      ? ` · ${dinero(-diferencia)} por debajo del objetivo (${dinero(datos.precio_objetivo)})`
      : ` · ${dinero(diferencia)} arriba del objetivo (${dinero(datos.precio_objetivo)})`;
    detalle.append(frase);
  }
}

function enlaceProducto(producto, texto) {
  const url = urlSegura(producto.url);
  if (!url) return document.createTextNode(texto);
  return el("a", { href: url, target: "_blank", rel: "noopener noreferrer" }, texto);
}

// ------------------------------------------------------------------ tabla de productos
function pintarTablaProductos(productos) {
  const cuerpo = document.querySelector("#tabla-productos tbody");
  cuerpo.replaceChildren(...productos.map(filaProducto));
}

function filaProducto(p) {
  const nombre = el("div", { clase: "producto-nombre" },
    el("span", { clase: `clave ${p.clase}`, "aria-hidden": "true" }),
    enlaceProducto(p, p.descripcion));
  const extra = p.valor_extra ? ` · juego valorado en ${dinero(p.valor_extra)}` : "";
  const celdaProducto = el("td", {}, nombre,
    el("span", { clase: "secundario", texto: `${nombreTienda(p.tienda)} · versión ${p.version.replace("_", " ")}${extra}` }));

  const actual = el("td", { clase: "num" }, dinero(p.efectivo_actual));
  if (p.precio_actual != null && p.valor_extra) {
    actual.append(el("span", { clase: "secundario", texto: `cobra ${dinero(p.precio_actual)}` }));
  }
  if (p.precio_lista_actual != null && p.precio_lista_actual > p.precio_actual) {
    actual.append(el("span", { clase: "secundario", texto: `"antes" ${dinero(p.precio_lista_actual)}` }));
  }

  return el("tr", {},
    celdaProducto,
    el("td", {}, chipEstado(p), detalleEstado(p)),
    actual,
    celdaExtremo(p.minimo),
    celdaExtremo(p.maximo),
    el("td", { texto: p.ultima_lectura_utc ? fechaHora.format(new Date(p.ultima_lectura_utc)) : "—" }));
}

function chipEstado(p) {
  const estado = ESTADOS[p.estado] ?? ESTADOS.error;
  return el("span", { clase: `estado ${estado.clase}` },
    el("span", { clase: "estado-icono", "aria-hidden": "true", texto: estado.icono }),
    estado.texto);
}

function detalleEstado(p) {
  const partes = [];
  if (p.motivo) partes.push(p.motivo);
  if (p.racha_fallos > 1) partes.push(`falla desde hace ${p.racha_fallos} lecturas`);
  return partes.length ? el("span", { clase: "secundario", texto: partes.join(" · ") }) : null;
}

function celdaExtremo(extremo) {
  if (!extremo) return el("td", { clase: "num", texto: "—" });
  return el("td", { clase: "num" }, dinero(extremo.efectivo),
    el("span", { clase: "secundario", texto: fechaCorta.format(new Date(extremo.fecha_utc)) }));
}

// ------------------------------------------------------------------ leyenda y tabla de historial
function pintarLeyenda(productos) {
  const conDatos = productos.filter((p) => p.serie.length);
  document.getElementById("leyenda").replaceChildren(...conDatos.map((p) =>
    el("li", {}, el("span", { clase: `clave ${p.clase}`, "aria-hidden": "true" }), nombreProducto(p))));
}

/** Vista en tabla del historial: todo valor de la gráfica es legible sin pasar el mouse. */
function pintarTablaHistorial(productos) {
  const conDatos = productos.filter((p) => p.serie.length);
  const dias = diasOrdenados(conDatos);
  const tabla = document.getElementById("tabla-historial");
  tabla.tHead.replaceChildren(el("tr", {}, el("th", { scope: "col", texto: "Fecha" }),
    ...conDatos.map((p) => el("th", { scope: "col", clase: "num", texto: nombreProducto(p) }))));
  const valores = conDatos.map((p) => new Map(p.serie.map(([f, v]) => [diaLocal(f), v])));
  tabla.tBodies[0].replaceChildren(...[...dias].reverse().map((dia) =>
    el("tr", {}, el("th", { scope: "row", texto: fechaLarga.format(new Date(dia.fecha)) }),
      ...valores.map((mapa) => el("td", { clase: "num", texto: dinero(mapa.get(dia.clave)) })))));
}

/** Clave de día en hora de CDMX: una lectura diaria por producto se alinea por día. */
function diaLocal(fechaIso) {
  return new Intl.DateTimeFormat("en-CA", { timeZone: ZONA }).format(new Date(fechaIso));
}

function diasOrdenados(productos) {
  const porClave = new Map();
  for (const p of productos) {
    for (const [fecha] of p.serie) {
      const clave = diaLocal(fecha);
      if (!porClave.has(clave) || fecha < porClave.get(clave).fecha) porClave.set(clave, { clave, fecha });
    }
  }
  return [...porClave.values()].sort((a, b) => a.fecha.localeCompare(b.fecha));
}

// ------------------------------------------------------------------ gráfica de líneas (SVG propio)
class Grafica {
  constructor(contenedor, productos, objetivo) {
    this.contenedor = contenedor;
    this.productos = productos.filter((p) => p.serie.length);
    this.objetivo = objetivo;
    this.dias = diasOrdenados(this.productos);
    this.porDia = this.productos.map((p) => new Map(p.serie.map(([f, v]) => [diaLocal(f), v])));
    this.indice = null;
  }

  dibujar() {
    const vacio = document.getElementById("grafica-vacia");
    this.contenedor.querySelectorAll("svg, .tooltip").forEach((n) => n.remove());
    if (!this.productos.length) { vacio.hidden = false; return; }
    vacio.hidden = true;

    const ancho = Math.max(this.contenedor.clientWidth - 16, 280);
    const alto = Math.round(Math.min(360, Math.max(220, ancho * 0.45)));
    const m = { arriba: 16, derecha: 16, abajo: 32, izquierda: 72 };
    this.geo = { ancho, alto, m, x: this.escalaX(ancho, m), y: this.escalaY(alto, m) };

    const lienzo = svg("svg", { viewBox: `0 0 ${ancho} ${alto}`, role: "img", tabindex: "0",
      "aria-label": "Historial del precio efectivo por producto; los valores están en la tabla de abajo. Usa las flechas para recorrer los días." });
    this.dibujarEjes(lienzo);
    this.dibujarObjetivo(lienzo);
    this.productos.forEach((p, i) => this.dibujarSerie(lienzo, p, i));
    this.prepararCursor(lienzo);
    this.contenedor.append(lienzo);
  }

  escalaX(ancho, m) {
    const tiempos = this.dias.map((d) => Date.parse(d.fecha));
    let [min, max] = [Math.min(...tiempos), Math.max(...tiempos)];
    if (min === max) { min -= 86_400_000; max += 86_400_000; } // un solo día: centrarlo
    return (fecha) => m.izquierda + ((Date.parse(fecha) - min) / (max - min)) * (ancho - m.izquierda - m.derecha);
  }

  escalaY(alto, m) {
    const valores = this.productos.flatMap((p) => p.serie.map(([, v]) => v));
    if (this.objetivo != null) valores.push(this.objetivo);
    const paso = pasoRedondo((Math.max(...valores) - Math.min(...valores)) / 4 || 50_000);
    const min = Math.floor(Math.min(...valores) / paso) * paso;
    const max = Math.ceil(Math.max(...valores) / paso) * paso || min + paso;
    const tope = max === min ? min + paso : max;
    const escala = (v) => alto - m.abajo - ((v - min) / (tope - min)) * (alto - m.arriba - m.abajo);
    escala.marcas = [];
    for (let v = min; v <= tope; v += paso) escala.marcas.push(v);
    return escala;
  }

  dibujarEjes(lienzo) {
    const { ancho, alto, m, x, y } = this.geo;
    for (const v of y.marcas) {
      lienzo.append(svg("line", { class: "reticula", x1: m.izquierda, x2: ancho - m.derecha, y1: y(v), y2: y(v) }));
      const texto = svg("text", { class: "texto-eje", x: m.izquierda - 8, y: y(v) + 4, "text-anchor": "end" });
      texto.textContent = pesosCortos.format(v / 100);
      lienzo.append(texto);
    }
    lienzo.append(svg("line", { class: "eje", x1: m.izquierda, x2: ancho - m.derecha, y1: alto - m.abajo, y2: alto - m.abajo }));
    const cada = Math.max(1, Math.ceil(this.dias.length / Math.floor((ancho - m.izquierda) / 70)));
    this.dias.forEach((dia, i) => {
      if (i % cada) return;
      const texto = svg("text", { class: "texto-eje", x: x(dia.fecha), y: alto - m.abajo + 18, "text-anchor": "middle" });
      texto.textContent = fechaCorta.format(new Date(dia.fecha));
      lienzo.append(texto);
    });
  }

  dibujarObjetivo(lienzo) {
    if (this.objetivo == null) return;
    const { ancho, m, y } = this.geo;
    lienzo.append(svg("line", { class: "objetivo", x1: m.izquierda, x2: ancho - m.derecha, y1: y(this.objetivo), y2: y(this.objetivo) }));
    const texto = svg("text", { class: "texto-objetivo", x: ancho - m.derecha, y: y(this.objetivo) - 6, "text-anchor": "end" });
    texto.textContent = `Objetivo ${pesosCortos.format(this.objetivo / 100)}`;
    lienzo.append(texto);
  }

  /** Línea por tramos: un hueco de más de 36 h (días agotado o con error) corta la línea. */
  dibujarSerie(lienzo, producto, i) {
    const { x, y } = this.geo;
    const grupo = svg("g", { class: producto.clase });
    const tramos = [];
    let previo = null;
    for (const [fecha, valor] of producto.serie) {
      if (!previo || Date.parse(fecha) - Date.parse(previo) > 36 * 3_600_000) tramos.push([]);
      tramos.at(-1).push([x(fecha), y(valor)]);
      previo = fecha;
    }
    for (const tramo of tramos) {
      if (tramo.length > 1) {
        grupo.append(svg("path", { class: "linea", d: "M" + tramo.map(([a, b]) => `${a.toFixed(1)},${b.toFixed(1)}`).join("L") }));
      } else {
        grupo.append(svg("circle", { class: "punto", cx: tramo[0][0], cy: tramo[0][1], r: 4 }));
      }
    }
    const [ultX, ultY] = tramos.at(-1).at(-1);
    grupo.append(svg("circle", { class: "punto", cx: ultX, cy: ultY, r: 4 })); // punto final
    lienzo.append(grupo);
  }

  // ---- cursor + tooltip: una lectura por día con todos los productos
  prepararCursor(lienzo) {
    const { ancho, alto, m, x } = this.geo;
    const cursor = svg("line", { class: "cursor", y1: m.arriba, y2: alto - m.abajo, visibility: "hidden" });
    const zona = svg("rect", { class: "zona-sensible", x: m.izquierda, y: 0, width: ancho - m.izquierda - m.derecha, height: alto });
    lienzo.append(cursor, zona);
    const tooltip = el("div", { clase: "tooltip", role: "status" });
    tooltip.hidden = true;
    this.contenedor.append(tooltip);

    const mostrar = (indice) => {
      this.indice = indice;
      const dia = this.dias[indice];
      const cx = x(dia.fecha);
      cursor.setAttribute("x1", cx); cursor.setAttribute("x2", cx); cursor.setAttribute("visibility", "visible");
      this.llenarTooltip(tooltip, dia);
      tooltip.hidden = false;
      const escalaPantalla = lienzo.getBoundingClientRect().width / ancho;
      const izquierda = cx * escalaPantalla + 8 + 16;
      const cabe = izquierda + tooltip.offsetWidth < this.contenedor.clientWidth;
      tooltip.style.left = `${cabe ? izquierda : Math.max(8, cx * escalaPantalla - tooltip.offsetWidth - 8)}px`;
      tooltip.style.top = "12px";
    };
    const ocultar = () => { cursor.setAttribute("visibility", "hidden"); tooltip.hidden = true; };

    zona.addEventListener("pointermove", (evento) => {
      const caja = lienzo.getBoundingClientRect();
      const px = ((evento.clientX - caja.left) / caja.width) * ancho;
      let mejor = 0;
      this.dias.forEach((d, i) => { if (Math.abs(x(d.fecha) - px) < Math.abs(x(this.dias[mejor].fecha) - px)) mejor = i; });
      mostrar(mejor);
    });
    zona.addEventListener("pointerleave", ocultar);
    lienzo.addEventListener("blur", ocultar);
    lienzo.addEventListener("focus", () => mostrar(this.indice ?? this.dias.length - 1));
    lienzo.addEventListener("keydown", (evento) => {
      if (evento.key !== "ArrowLeft" && evento.key !== "ArrowRight") return;
      evento.preventDefault();
      const paso = evento.key === "ArrowLeft" ? -1 : 1;
      mostrar(Math.min(this.dias.length - 1, Math.max(0, (this.indice ?? this.dias.length - 1) + paso)));
    });
  }

  llenarTooltip(tooltip, dia) {
    const filas = this.productos
      .map((p, i) => ({ p, valor: this.porDia[i].get(dia.clave) }))
      .filter((f) => f.valor != null)
      .sort((a, b) => a.valor - b.valor)
      .map(({ p, valor }) => el("div", { clase: "tooltip-fila" },
        el("span", { clase: `clave ${p.clase}`, "aria-hidden": "true" }),
        el("span", { clase: "tooltip-valor", texto: dinero(valor) }),
        el("span", { clase: "tooltip-nombre", texto: nombreProducto(p) })));
    tooltip.replaceChildren(el("div", { clase: "tooltip-fecha", texto: fechaLarga.format(new Date(dia.fecha)) }),
      ...(filas.length ? filas : [el("div", { texto: "Sin lecturas válidas ese día" })]));
  }
}

/** Paso "bonito" para las marcas del eje: 1, 2 o 5 × 10^n (en centavos). */
function pasoRedondo(bruto) {
  const potencia = 10 ** Math.floor(Math.log10(bruto));
  const fraccion = bruto / potencia;
  return (fraccion <= 1 ? 1 : fraccion <= 2 ? 2 : fraccion <= 5 ? 5 : 10) * potencia;
}

iniciar();
