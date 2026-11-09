# Verificación del triaje: qué pools de la lista son realmente vulnerables

**Entrada:** las 226 filas del escáner (`version,risk,pool,pool_type,...`).
**Método:** aritmética exacta del contrato, no la etiqueta `risk`.
**Script:** `verify_triage.py` → `python3 security/verify_triage.py`.

---

## Veredicto

De las 149 filas que se pueden decidir con datos (`triage_v1.csv` + `triage_v2.csv`: los 70 v1 con
TVL ≥ $1.000 y los 79 v2 `WEIGHTED`):

| veredicto | pools | dinero |
|---|---:|---:|
| **VULNERABLE hoy** (P&L > $100) | **7** | botín **$42.250** sobre TVL $75.473 |
| **Vulnerable si la pata sin precio está muerta** | **61** | botín hasta **$974.855** sobre $1,46 M de pata viva |
| Rentable pero no cubre el gas ($0 < P&L ≤ $100) | 23 | ≤ $3,13 cada uno |
| **SEGURO por aritmética** (P&L < 0) | **54** | 0 |
| Indecidible (2+ patas sin precio) | 4 | — |

**La etiqueta del escáner no distingue nada.** `STILL-EXPOSED` sólo significa «no pausado»: de las
127 filas así etiquetadas, **54 tienen P&L negativo** — el atacante pierde dinero. Los dos pools más
grandes de toda la lista (0x5c6ee304, $4,28 M; 0x3de27efa, $2,54 M) están en ese grupo: −$34 y −$12.

`has_joinswap=False` en las filas v2 es irrelevante: en v2 no existe `joinswapPoolAmountOut`, se entra
por `Vault.joinPool` con `JoinKind.TOKEN_IN_FOR_EXACT_BPT_OUT`.

## Validación del método

Para las patas sin precio el umbral sale en forma cerrada, `u < w_u·ρ*·V/(1 − w_u·ρ*)`. Aplicado a los
cuatro casos que ya había calculado por otra vía en `CLASIFICACION-POOLS.md` §5:

| pool | token sin precio | umbral aquí | `p*` del informe anterior |
|---|---|---:|---:|
| `0xe00770cb` | ULU | $510,4 | $510,3 |
| `0x33812e98` | xAAVEa | $1.607 | $1.607 |
| `0x48c1d1d4` | COVER_CDS | $0,814 | $0,814 |
| `0xc1b10e53` | MPL | $0,2967 | $0,2967 |

Cuatro de cuatro. El mismo número por dos caminos independientes.

---

## 1. Vulnerables hoy (aritmética completa, P&L > $100)

| pool | ver | TVL | P&L | ejecución |
|---|---|---:|---:|---|
| `0x1373e57f` | v1 | $29.298 | **+$29.216** | 119 joins, salida pro-rata, f = 99,8 % |
| `0xf0f8b1ce` | v1 | $17.435 | **+$5.188** | 4 joins, f = 55,5 % |
| `0x5b1c06c4` | v2 | $9.059 | **+$2.746** | 7 joins + 1 exit, f = 28,9 % |
| `0x30cb8593` | v1 | $3.883 | **+$2.720** | 9 joins, f = 83,4 % |
| `0xc3516482` | v1 | $10.056 | **+$993** | 3 joins, f = 21,6 % |
| `0xa5533a44` | v2 | $4.507 | **+$727** | 3 joins + 1 exit, f = 24,9 % |
| `0xcf8dfdb7` | v2 | $1.235 | **+$660** | 7 joins + 2 exits, f = 48,7 % |

Dos observaciones:

- **`0x1373e57f`** es un pool de 8 tokens donde 7 patas valen céntimos (DAI $0,02, USDC $0,00, WETH
  $0,01…) y la octava $29.297,98. No es «un pool desequilibrado»: es un pool con siete patas muertas.
  El atacante acuña el 99,8 % del BPT metiendo céntimos y se lleva la pata viva entera.
- **El par PAR/MIMO (mStable)** aparece en 3 de los 7 (`0xf0f8b1ce` v1, `0x5b1c06c4` y `0xa5533a44` v2).
  No es casualidad: son pools de incentivos con un token de precio administrado y otro que se movió,
  y nadie arbitró el desequilibrio. `0xf0f8b1ce` es justo el pool del PoC original.

Los otros tres coinciden con lo que ya había marcado al revisar el PoC: `0xf0f8b1ce` no estaba
equilibrado (ρ de la pata PAR = 0,29) y da +$5.188; `0x30cb8593` es justo el pool que el PoC
replicaba y sale **+$2.720** frente a los +$2.595 del PoC (4,6 % corto, por no haber contado bien el
número de iteraciones); y `0xc3516482`, que el PoC usaba como control negativo, tiene ρ = 0,313 y da
+$993.

## 2. La parte gorda: 61 pools con una pata sin precio

Aquí el escáner pone `NA` y `tvl_live_usd` **sólo cuenta la pata con precio**. Si esa pata sin precio
está muerta (típico: tokens de 2021 sin mercado), el ataque es drenar la pata viva depositando basura.
El umbral dice cuánto puede valer la pata sin precio antes de que el pool deje de ser rentable.

| pool | ver | pata viva | vulnerable si la otra vale < | botín |
|---|---|---:|---:|---:|
| `0xe00770cb` | v1 | $715.351 | $30.544 (⇔ ULU < **$510**) | **$244.643** |
| `0x33812e98` | v1 | $141.652 | $115.640 (⇔ xAAVEa < **$1,61**) | $139.086 |
| `0x1bccaac0` | v2 | $108.568 | $108.568 (⇔ XNS < $108.568 en total) | $106.354 |
| `0x39eb5581` | v2 | $96.040 | $384.162 | $95.770 |
| `0x48c1d1d4` | v1 | $75.171 | $61.367 (⇔ COVER < **$0,81**) | $73.812 |
| `0x9232a548` | v2 | $58.406 | $233.625 | $58.238 |
| `0xeb85b2e1` | v1 | $50.637 | $41.339 | $49.724 |
| `0xc1b10e53` | v1 | $35.283 | $28.804 (⇔ MPL < **$0,30**) | $34.644 |
| `0xa7956005` | v1 | $24.152 | $46.123 | $24.045 |
| `0xc786ab47` | v1 | $22.356 | $18.251 | $21.952 |
| … 51 más | | $133.439 | | $126.587 |
| **total** | | **$1.460.055** | | **$974.855** |

Sin el precio del token no puedo decir «es vulnerable»: digo exactamente cuánto tiene que valer para
que lo sea. Y hay un detalle que inclina la balanza hacia el riesgo: en varios de estos pools el umbral
es tan alto que **cualquier precio plausible lo cumple**. `0x1bccaac0` (XNS/WETH 50/50): el umbral es
el 100 % de la pata viva, es decir, es vulnerable salvo que XNS valga exactamente lo que equilibra el
pool. `0x9232a548`: LIT tendría que valer $233.625 **en total** (no por unidad) para estar a salvo.

## 3. Los 54 que el escáner marca como expuestos y son seguros

| pool | ver | TVL | P&L del ataque |
|---|---|---:|---:|
| `0x1eff8af5` | v1 | $761.097 | −$634 |
| `0x9866772a` | v1 | $615.156 | −$245 |
| `0x5c6ee304` | v2 | $4.278.165 | −$34 |
| `0x3de27efa` | v2 | $2.536.616 | −$12 |
| `0xa6f548df` | v2 | $1.656.162 | −$7 |
| `0x74a5d106` | v1 | $127.237 | −$251 |
| `0xa6cf0a73` | v1 | $49.116 | −$31 |
| `0xbed340a3` | v1 | $55.009 | −$29 |

No significa «para siempre»: significa que con estos precios y estos balances el atacante pierde. El
margen es el ρ frente a su umbral. `0x1eff8af5` está en ρ = 1,00 con umbral 0,899 (w = 0,5): le hace
falta un desequilibrio de ~10 % en la relación WETH/WBTC, igual que al resto de los 50/50 bien
arbitrados. Los que no tienen margen son los de ρ cerca del umbral (§ «marginales»).

## 4. Los 23 marginales

P&L entre $0,00 y $3,13. Son pools con ρ = 0,999: técnicamente rentables, en la práctica el gas
(~$80 por 2–8 llamadas) se come el beneficio. El mayor es `0x29d7a7e0` con **+$3,13**. Ninguno
justifica una transacción.

## 5. Fuera de alcance (y por qué)

| grupo | filas | motivo |
|---|---:|---|
| v2 `STABLE`, `COMPOSABLE_STABLE`, `META_STABLE`, `GYROE`, `ELEMENT`, `LIQUIDITY_BOOTSTRAPPING`, `INVESTMENT` | 42 | otra curva (`StableMath`/`GyroMath`, amplificación, BPT anidado). Mi hallazgo es de `WeightedMath`; no afirmo nada sobre estos sin modelo propio. |
| v1 con TVL < $1.000 | 23 | el botín máximo es el TVL; el gas mínimo del ataque (~$15–80) se lo come. |
| v1 `NOT-FINALIZED` (8), `ZERO-SUPPLY` (1), `1-SIDED/EMPTY` (3) | 12 | no hay BPT negociable o falta una pata. `0xd7123bd9` (ZERO-SUPPLY, $27.865) merece revisión aparte: con supply 0 la primera entrada fija el precio del BPT sin referencia. |

## 6. Errores de datos detectados en la propia lista

- **`0xe00770cb`, columna `tvl_scan_usd` = $858.768 > `tvl_live_usd` = $715.351.** La diferencia
  implica un precio de ULU de **$2.396**, imposible (ULU no vale eso). El escáner emparejó el símbolo
  con otro token. Uso `tvl_live_usd` en todo el cálculo.
- **`0x69d460e0`**: `tvl_live` $2,15 vs `tvl_scan` $488.429. Dato roto, descartado.
- **Los `COMPOSABLE_STABLE` muestran `supply` ≈ 2,596e15.** Es el BPT virtual (el pool se tiene a sí
  mismo), no una emisión real. Cualquier comparación de supply entre pools que no tenga esto en cuenta
  es basura.
- **`codesize`** (18286 / 19384 / 24252 / 24342) agrupa versiones de factoría, no niveles de riesgo.
  `0x5c6ee304` (18.286) y `0x96646936` (19.384) son igual de seguros y comparten código.

## 7. Método, en una línea

`ρ_i = v_i/(w_i·TVL)` con `v_i = usd_per_token` (verificado: Σv = `tvl_live_usd` en 149/149 filas).
El ataque completo se simula en dólares porque **todas** las operaciones del exploit son lineales en
el balance de la pata en polvo: usar `balance = v_i` con precio 1 da exactamente el mismo P&L
(homogeneidad de grado 1). v1 se ejecuta sobre `bmath_sim` (entero exacto, `BMath`/`BNum`); v2 sobre
`v2_weighted` (Decimal 60 dígitos, redondeo del contrato).
