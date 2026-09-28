# CLAUDE.md

Contexto y reglas del proyecto para futuras sesiones. El README explica el uso;
aquí van las reglas de trabajo y los porqués.

## Qué es
Rastreador de **historial** de precios de Nintendo Switch 2 en tiendas de México.
Cada día, GitHub Actions hace una lectura por producto (`productos.yaml`), la
agrega a `data/lecturas.csv`, regenera `docs/datos.json` (dashboard en GitHub
Pages) y avisa por Telegram solo si hay un nuevo mínimo o se cruza el objetivo.
Costo $0. Repositorio público.

## Cómo trabajar con el usuario
- Retoma Python viniendo de C++/JS/web: **explica decisiones y trade-offs**, no solo el código.
- **Sé crítico**: si algo del pedido parece mala idea, dilo con argumentos antes de implementarlo.
- Trabajo por fases: detente al terminar cada una y espera confirmación.
- **Nunca hagas commit ni push sin preguntar.**
- Código en español (nombres y mensajes), funciones pequeñas, tipado, responsabilidades separadas.

## Comandos (Windows; siempre con el intérprete del venv, nunca el Python global)
```bash
.venv\Scripts\python.exe -m pytest
.venv\Scripts\python.exe -m rastreador --sin-notificar          # lectura real; escribe data/ y docs/datos.json
.venv\Scripts\python.exe -m rastreador --sin-notificar --historial C:\temp\p.csv --dashboard C:\temp\d.json
.venv\Scripts\python.exe -m rastreador.configurar_telegram chat-id|probar
.venv\Scripts\python.exe investigacion\sondeo.py C:\temp\html   # diagnóstico de tiendas
```
Vista previa del dashboard: la entrada `rastreador-dashboard` de `../.claude/launch.json` (sirve `docs/` en 127.0.0.1:8765).

## Arquitectura
Flujo: `descarga` (única pieza con red) → `clasificacion` (estado) usando
`tiendas` → `extractores` → `lectores` → `historial` (CSV) → `alertas` →
`notificador`; `dashboard` genera el JSON. `orquestador` recibe inyectados
red, reloj, pausa y notificador, y las pruebas simulan días sin red.
Detalle por tienda (dónde vive cada dato): `investigacion/HALLAZGOS.md`.

## Decisiones (no cambiarlas sin hablarlo)
- Importes en **centavos (int)**; `Decimal` solo al leer JSON/YAML (`parse_float=Decimal`). Nunca float.
- Fechas en **UTC**; hora de CDMX solo al mostrar (el navegador con `Intl`).
- Historial = **CSV de solo-agregar** con LF (`.gitattributes`). El precio efectivo **no se guarda**: se calcula con el `valor_extra` actual.
- Solo el estado `ok` cuenta para mínimos y alertas. `tercero` (marketplace) no cuenta salvo `permitir_terceros`.
- Los extractores se **anclan al id de la URL** (Liverpool mezcla productos recomendados con precio) y lanzan `ErrorExtraccion` en vez de adivinar.
- `version` admite `sin_declarar` (Gameplanet no lo dice): desviación consciente del pedido original.
- Dashboard con **SVG propio**, sin librerías: la CSP puede ser `script-src 'self'` sin SRI.

## Seguridad (obligatorio)
- Secretos solo en variables de entorno / GitHub Secrets / `.env` local (ignorado). Nada de secretos en el repo, los logs ni los mensajes de error.
- **La URL de Telegram contiene el token.** `notificador.py` traduce toda excepción de `requests` a `ErrorNotificacion` lanzada **fuera** del `except` (sin `__cause__` ni `__context__`), nunca usa `raise_for_status()` ni `resp.url`, y oculta el token de cualquier texto. `test_notificador.py` lo verifica con requests real y un adaptador falso. No lo debilites.
- `yaml.safe_load`, nunca `yaml.load`. Claves desconocidas en la configuración = error.
- URLs: solo `https`, host **exacto** de la tienda, sin usuario ni puerto, ruta de página de producto.
- Descargas con timeout, límite de 8 MB y máximo 5 redirecciones.
- Workflows: `permissions` explícitos y mínimos, Actions **fijadas por SHA**, secretos solo en el paso que los usa. `test_seguridad_estatica.py` lo vigila.
- Dashboard: sin `innerHTML` (solo `createElement`/`textContent`), enlaces solo `https://`, CSP estricta en `<meta>`.
- CSV: textos en una sola línea y protegidos contra inyección de fórmulas (`=`, `+`, `-`, `@`).
- **No evadir protecciones anti-bot**: User-Agent honesto, nada de disfrazarse de navegador, proxies, captchas ni navegadores headless. Si una tienda bloquea, se reporta y decide el usuario. (Por eso Coppel está fuera.)
- Dependencias fijadas con `==` en todo el árbol (incluidas las transitivas) + Dependabot.

## Lecciones aprendidas
- **No asumas el formato de una tienda: investígala primero.** Liverpool no tiene JSON-LD (usa el stream RSC `self.__next_f.push`), y el JSON-LD de Sears es inválido o engañoso.
- Las URLs de producto caducan (Liverpool 1177646331 → 404): es un estado explícito (`no_encontrado`), no un error genérico.
- Fixtures: siempre **reales y recortados** con `investigacion/recortar_fixtures.py`, nunca páginas completas en el repo.
- En este entorno, un heredoc de Bash puede alterar `\\` y `\r\n` dentro del código: para archivos con barras invertidas usa la herramienta Write.

## Pendientes conocidos
- Correr `sondeo.yml` en Actions para saber si las tiendas bloquean IPs de datacenter.
- Verificar un caso real de Liverpool agotado y de Liverpool marketplace.
- Fuera de alcance por ahora: promociones bancarias, Amazon (se usa Keepa), Google Shopping.
