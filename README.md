# Rastreador de precios de Nintendo Switch 2 (México)

Te dice **cuándo** una Switch 2 está a un precio realmente bueno, según el
**historial real** de precios y no según el "% de descuento" que anuncian las
tiendas (que suelen inflar el precio "anterior").

Dos veces al día (08:23 y 20:23, hora de CDMX), GitHub Actions lee cada producto de `productos.yaml` y:

1. agrega la lectura al historial `data/lecturas.csv` (también las fallidas, con su motivo);
2. regenera el dashboard estático en GitHub Pages (`docs/`);
3. te avisa por Telegram **solo** si hay un nuevo mínimo histórico o si el precio cruza tu objetivo.

Costo: $0 (GitHub Actions + GitHub Pages + un bot de Telegram).

**Tiendas soportadas:** Liverpool, Walmart, Gameplanet y Sears. Coppel quedó
fuera porque bloquea a clientes que no son navegador (Akamai Bot Manager), y
aquí no se evaden bloqueos. Los detalles están en
[`investigacion/HALLAZGOS.md`](investigacion/HALLAZGOS.md).

---

## Conceptos

- **Precio efectivo** = precio de la tienda − `valor_extra`, donde `valor_extra`
  es lo que vale **para ti** lo que trae el bundle (p. ej. el juego). Todas las
  comparaciones y alertas usan este precio.
- **Estados de una lectura:**

  | Estado | Significa | ¿Cuenta para mínimos y alertas? |
  |---|---|---|
  | `ok` | En venta por la propia tienda | Sí |
  | `agotado` | Hay precio, pero no se puede comprar | No |
  | `tercero` | Lo vende otro vendedor del marketplace (Walmart, Sears, Liverpool) | No, salvo `permitir_terceros: true` |
  | `no_encontrado` | HTTP 404/410: **la URL caducó**, hay que poner una nueva | No |
  | `bloqueado` | HTTP 401/403/429 o redirección a la portada: la tienda nos bloqueó | No |
  | `error` | Red, formato inesperado o precio fuera del rango de cordura | No |

- **Alertas:**
  - *Nuevo mínimo histórico:* se necesitan al menos `lecturas_minimas` lecturas
    `ok` previas, y la baja respecto del mínimo anterior debe ser de al menos
    `baja_minima_alerta`.
  - *Cruce del objetivo:* el precio efectivo llega a `precio_objetivo` o baja de
    él viniendo de arriba. Si al día siguiente sigue abajo, no se repite. Un día
    agotado o con error no cuenta como "haber subido".

- **Vigilancias** (sección `vigilancias` de `productos.yaml`): una búsqueda
  **fija** en la tienda que corre en cada ejecución diaria y avisa **una sola vez
  por SKU** cuando aparece un producto cuyo nombre tiene todas las palabras de
  `requiere` (sin distinguir acentos ni mayúsculas). Sirve para enterarse de que
  un bundle despublicado volvió, quizá con otro SKU. Los SKU ya avisados quedan
  en `data/vigilancias.json`: bórralos de ahí si quieres que se avise de nuevo.
  Hoy solo Liverpool admite vigilancias. Una búsqueda fallida se reporta en la
  salida, pero no cuenta para "todas las lecturas fallaron".

---

## 1. Entorno local (Windows)

Necesitas Python 3.13 y Git.

```bash
py -3.13 -m venv .venv
```
```bash
.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
```
```bash
.venv\Scripts\python.exe -m pytest
```

Siempre ejecuta Python con la ruta del intérprete del entorno
(`.venv\Scripts\python.exe`) y nunca instales paquetes en el Python global.

Para una prueba real sin Telegram, que solo muestra en consola las alertas que habría enviado:

```bash
.venv\Scripts\python.exe -m rastreador --sin-notificar
```

Esto **sí agrega** una lectura real a `data/lecturas.csv` y regenera
`docs/datos.json`. Para no tocarlos, usa
`--historial C:\temp\prueba.csv --dashboard C:\temp\datos.json`.

## 2. Bot de Telegram

1. En Telegram, abre **@BotFather** y envía `/newbot`. Elige un nombre y un
   usuario (debe terminar en `bot`). BotFather te da un **token** con la forma
   `123456789:AA...`. **Es una contraseña:** quien lo tenga controla tu bot.
2. Crea en la raíz del proyecto un archivo `.env` (está en `.gitignore`) con estas dos líneas y pega el token:
   ```
   TELEGRAM_TOKEN=
   TELEGRAM_CHAT_ID=
   ```
   *Evita* hacer `$env:TELEGRAM_TOKEN="..."` en PowerShell: queda guardado en el
   historial de comandos.
3. Abre tu bot en Telegram (búscalo por su usuario) y escríbele cualquier cosa, por ejemplo "hola".
4. Obtén tu `chat_id` sin exponer el token:
   ```bash
   .venv\Scripts\python.exe -m rastreador.configurar_telegram chat-id
   ```
   Pega el número en `TELEGRAM_CHAT_ID=` dentro de `.env`.
   (No uses la receta de abrir `https://api.telegram.org/bot<TOKEN>/getUpdates`
   en el navegador: el token queda en el historial del navegador.)
5. Comprueba que el bot te escribe:
   ```bash
   .venv\Scripts\python.exe -m rastreador.configurar_telegram probar
   ```

## 3. Repositorio en GitHub

GitHub Pages gratis requiere un repositorio **público**. El historial de precios
no es sensible, pero **los commits muestran el nombre y el email del autor**
(ver [Privacidad](#privacidad)).

1. Crea un repositorio público **vacío** (sin README ni licencia) en
   <https://github.com/new>.
2. Conéctalo y sube el código:
   ```bash
   git remote add origin https://github.com/<tu-usuario>/<tu-repo>.git
   ```
   ```bash
   git push -u origin main
   ```

## 4. Secrets

En el repositorio ve a **Settings → Secrets and variables → Actions → New repository secret** y crea:

| Nombre | Valor |
|---|---|
| `TELEGRAM_TOKEN` | el token de @BotFather |
| `TELEGRAM_CHAT_ID` | el número que obtuviste en el paso 2.4 |

GitHub enmascara los secretos en los logs. El workflow solo los expone en el
paso que corre el rastreador.

## 5. GitHub Pages (dashboard)

**Settings → Pages → Build and deployment → Source: Deploy from a branch →
Branch: `main`, carpeta `/docs` → Save.**

En uno o dos minutos el dashboard queda en
`https://<tu-usuario>.github.io/<tu-repo>/`.

## 6. Primera ejecución

1. **Diagnóstico primero.** En **Actions → "Sondeo de tiendas (diagnóstico
   manual)" → Run workflow**, abre el log y revisa cada línea JSON: `status` 200,
   `datos` con `json_ld`/`next_data`/`rsc_next_f` y `bloqueo` vacío. Así sabes si
   las tiendas aceptan las IPs de GitHub (distintas a las de tu casa).
2. **Rastreo.** En **Actions → "Rastreo diario" → Run workflow**. Al terminar
   debe haber un commit `datos: lecturas del AAAA-MM-DD` del bot, y el dashboard
   se actualiza.
3. Desde ahí corre solo **dos veces al día: 08:23 y 20:23 (hora de CDMX)**.

Los workflows piden permisos explícitos: solo "Rastreo diario" puede escribir
(`contents: write`) para commitear los datos. No hace falta cambiar los permisos
por omisión del repositorio.

**Códigos de salida** (lo que marca el workflow en verde o rojo): `0` terminó (aunque
alguna tienda fallara), `1` **todas** las lecturas fallaron, `2` configuración o
secretos inválidos, `3` las lecturas se guardaron pero Telegram falló.

## 7. Operación

| Ves en el dashboard | Qué hacer |
|---|---|
| `URL caducada` | Busca el producto en la tienda y reemplaza su `url` en `productos.yaml` |
| `error` con "extracción: ..." por varios días | La tienda cambió su HTML: repite el sondeo, regenera los fixtures con `investigacion/recortar_fixtures.py` y ajusta el extractor |
| `bloqueado` | La tienda nos está rechazando. **No se evade**: decide si quitarla |
| `tercero` | Lo vende otro vendedor. Si quieres contarlo, pon `permitir_terceros: true` en ese producto |

**Agregar un producto** de una tienda soportada: copia un bloque en
`productos.yaml` (`id`, `tienda`, `version`, `descripcion`, `url` y opcionalmente
`valor_extra`, `precio_objetivo` o `permitir_terceros`). La configuración se valida
al arrancar: dominio exacto de la tienda, solo `https`, ruta de página de producto
y sin claves desconocidas.

**Agregar una tienda:** investiga primero (`investigacion/sondeo.py`), escribe su
extractor con fixtures recortados y regístrala en `rastreador/tiendas.py`.

## Estructura

```
productos.yaml            qué rastrear y los ajustes de alertas
rastreador/
  __main__.py             CLI: python -m rastreador [--sin-notificar]
  orquestador.py          una ejecución: leer, guardar, alertar
  descarga.py             la única pieza que toca la red de las tiendas
  lectores.py             formatos: JSON-LD, __NEXT_DATA__, stream RSC de Next.js
  extractores.py          un extractor por tienda (sin red; probado con fixtures)
  tiendas.py              dominios permitidos, forma de URL y extractor por tienda
  clasificacion.py        reglas de estado (404, bloqueo, cordura, tercero, agotado)
  alertas.py              reglas anti-spam y texto del mensaje
  notificador.py          Telegram sin filtrar el token
  historial.py            CSV de solo-agregar
  dashboard.py            genera docs/datos.json
  config.py, secretos.py  validación de configuración y secretos
docs/                     dashboard estático (GitHub Pages)
data/lecturas.csv         historial (lo escribe el bot)
investigacion/            sondeo de tiendas, recorte de fixtures, hallazgos
tests/                    pytest; fixtures reales recortados en tests/fixtures
```

## Límites honestos

- **Walmart bloquea a GitHub Actions** (PerimeterX, comprobado con el sondeo del
  2026-09-28): desde Actions sus lecturas quedan como `bloqueado`. Liverpool,
  Gameplanet y Sears sí responden. Una tienda puede empezar a bloquear en
  cualquier momento; el sondeo manual sirve para revisarlo.
- **Dos lecturas al día (08:23 y 20:23).** Una oferta relámpago de pocas horas puede pasar sin
  que la veas.
- **El cron de GitHub no es puntual:** puede retrasarse desde minutos hasta
  horas, o saltarse una ejecución en horas de carga.
- **GitHub desactiva los workflows programados** de un repositorio público tras
  60 días sin actividad (avisa por email antes). No verifiqué si los commits del
  bot cuentan como actividad. Si se desactiva, se reactiva con un botón en Actions.
- **Precios que no ve:** promociones bancarias, cupones, meses sin intereses,
  precio con tarjeta departamental, envío. Tampoco Amazon (uso Keepa aparte), Coppel
  ni Mercado Libre (su API exige OAuth con tokens que rotan y su web tiene verificación
  anti-bot; ver `investigacion/HALLAZGOS.md`).
- **Liverpool:** se toma el precio promocional que la página muestra como
  principal. No verifiqué si alguna promoción exige una condición (p. ej. su
  tarjeta). Tampoco pude ver cómo luce un producto agotado ni uno de
  marketplace: la regla de "tercero" se basa en un campo (`offersListVariants`)
  sin un caso real que la confirme.
- **Marketplaces:** en Walmart y Sears la misma URL puede mostrar mañana el
  precio de otro vendedor. Esas lecturas se marcan `tercero` y no cuentan, pero
  pueden dejar huecos en el historial.
- **Gameplanet no declara** si sus consolas son versión nacional o importada.
- **Las tiendas cambian su HTML sin avisar.** Cuando pasa, el estado será `error`
  (nunca un precio inventado), y hay que ajustar el extractor.
- **Si Telegram falla ese día, la alerta se pierde:** al día siguiente el cruce
  ya no es "nuevo". El workflow queda en rojo (código 3) y el dato sí está en el CSV.
- **Baja lenta:** un precio que baje menos de `baja_minima_alerta` cada día nunca
  dispara "nuevo mínimo" (cada lectura compara contra el mínimo anterior). La alerta
  de cruce del objetivo sí lo detecta.
- **`valor_extra` es subjetivo** y se aplica a todo el historial con tu valoración
  actual: si lo cambias, cambian también los mínimos pasados.

## Privacidad

- El repositorio es público: el historial y la configuración los puede ver cualquiera.
- **Cada commit publica el nombre y el email del autor.** Si no quieres exponer
  tu email, antes del primer push configura el email privado que te da GitHub
  (**Settings → Emails → "Keep my email addresses private"**) con
  `git config user.email "<id>+<usuario>@users.noreply.github.com"` y corrige
  los commits existentes con `git commit --amend --reset-author`.
- Nunca subas `.env`. Si un token llega a filtrarse, revócalo en @BotFather con
  `/revoke` y actualiza el secret.
