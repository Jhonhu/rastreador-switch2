# Hallazgos de la Fase 1 (2026-09-28)

Sondeo con User-Agent honesto desde IP residencial (`investigacion/sondeo.py`).
**Desde GitHub Actions (2026-09-28, `sondeo.yml`):** Liverpool, Gameplanet y Sears responden igual que desde casa. **Walmart bloquea** las IPs de Actions (PerimeterX: 302 a `/blocked?url=...` con HTTP 200). Coppel sigue bloqueada.

| Tienda | Fuente del precio | Ruta exacta | Disponibilidad | Vendedor |
|---|---|---|---|---|
| Liverpool | Stream RSC de Next.js App Router (`self.__next_f.push`). **No hay JSON-LD.** | nodo con `productInfo.productId` == id final de la URL → `productInfo.priceInfo.promoPrice.price` (lo que se paga; respaldo `salePrice`); lista: `listPrice.price` | `productInfo.inventoryStatus` (bool) | Propio si `offersListVariants` es `"$undefined"`; si trae algo, marketplace (no verificado con un caso real) |
| Walmart | JSON-LD Product | `offers[0].price` | `offers[0].availability` | `__NEXT_DATA__` → `props.pageProps.initialData.data.product.sellerType` (`INTERNAL` = Walmart), `sellerDisplayName`; "antes": `priceInfo.wasPrice.price` |
| Gameplanet | JSON-LD en `@graph` (WooCommerce) | `offers[0].price` (texto `"10999.99"`) | `offers[0].availability` | `offers[0].seller.name` |
| Sears | `__NEXT_DATA__` (su JSON-LD es inválido o engañoso) | `props.pageProps.response.data.sale_price`; lista `price` | `stock` (int) > 0 y `status` true | `store.name` == `"SEARS"` |
| Coppel | — | — | — | **Descartada:** `/pdp/` responde 302 a la portada con cookies de Akamai Bot Manager (`_abck`, `bm_sz`). No se evade. |

Notas:
- Liverpool: la URL del bundle 1177646331 da 404 (caducó). Las páginas incluyen productos recomendados con precio: anclar siempre al id.
- Walmart y Sears son marketplaces: la misma URL puede mostrar el precio de un tercero.
- EAN 045496885816 aparece en Walmart (00004549688581) y Sears (3522519): misma consola nacional.
- `robots.txt` de las cinco tiendas permite las rutas de producto.
- No verificado: Liverpool agotado (todo tenía stock), 404 de Walmart.

Regenerar fixtures: ver el docstring de `investigacion/recortar_fixtures.py`.
