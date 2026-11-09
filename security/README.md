# `security/` — Auditoría Balancer V1 (balancer-core)

Artefactos del análisis de seguridad del commit `f4ed5d6` (master).

| Archivo | Qué es |
|---|---|
| **`REPORTE-BALANCER-V1-ES.md`** | **Informe principal.** Empieza por la tabla de hallazgos (§0). |
| `bmath_sim.py` | Réplica exacta en Python de `BNum.sol` + `BMath.sol` (mismo redondeo *half-up*, misma precisión `1e8` en `bpowApprox`, mismos `require`) y modelo de `BPool` para las rutas relevantes. |
| `experiments.py` | E1-E7: reproducción del bug principal, la variante `joinswapExternAmountIn`, el caso de 18 decimales, la economía end-to-end, los DoS (`exitPool`, `gulp→0`) y el blow-up de `bpow`. |
| `rounding_search.py` | S1-S4: búsqueda exhaustiva de ciclos rentables por redondeo (join/exit, swap ida-vuelta, join-swap/exit-swap) a escala normal y con reservas en polvo. |
| `economics.py` | Capital / botín / ROI del ataque completo sobre pools balanceados a precio de mercado, en función del factor de compresión. |
| **`data/CLASIFICACION-POOLS.md`** | **Veredicto de los 100 pools con datos reales**: 14 vulnerables ($261.204 de botín), 40 a revisar por token sin precio (con el precio de equilibrio `p*` de cada uno) y 46 seguros *hoy* con el margen de precio relativo que los abriría. |
| **`analyze_live.py`** | Calcula `ρ` por pool sobre `data/pools_live.csv`, simula el ataque real (`n × joinswapExternAmountIn` + `exitPool`/`exitswapPoolAmountIn`) con contabilidad en enteros exactos y emite el ranking. `--capital` / `--capital-md` dan lo que el atacante debe comprar, token y unidades, en el régimen mínimo (1 llamada) y en el óptimo. `--md` genera las tablas del informe. |
| `data/pools_live.csv` | Los 100 pools activos con pesos, balances, precios, `usd_per_token` y supply (datos aportados por el usuario). Es la fuente de verdad del cálculo de `ρ`. |
| **`TRIAGE-POOLS-ES.md`** | **Triaje del inventario de pools**: qué se descarta, en qué orden revisar el resto y por qué el TVL / el flash loan no son buenos criterios. |
| `triage.py` | `inventory` (clasifica el CSV del escáner) y `screen` (veredicto real por pool a partir de balance/decimals/denorm/precio por token). |
| `screen.py` | Curva de rentabilidad `rho → P&L` y umbrales `rho*` por peso (aritmética exacta). |
| **`README-VULNERABLES-7.md`** | **Los 3 pools vulnerables cobrables hoy**: mecanismo del bug, ρ por pata, traza del ataque (llamadas, capital, P&L) y cómo se cierra. $30.676 de botín sobre $1.765 de capital. |
| **`REVISION-ANEXO-ES.md`** | **Revisión crítica de la auditoría previa del propio autor** (anexo de 2 modos, fase PoC Foundry, fase hunt y `Executor.sol`): qué está bien, siete errores concretos con evidencia de código, la muralla `paused()` puesta en duda y la corrección de fondo (ρ con precio realizable ≠ ρ con spot) que invalida parte de nuestros propios números. |
| **`data/DESCARTADOS-ES.md`** | Los **4 falsos positivos** que salieron de la lista original, con la prueba de por qué no son vulnerables (3 PAR/MIMO por precio de marca, 1 LP sin salida). |
| `dossier7.py` | Genera el dossier: ρ por pata, traza del ataque (llamada a llamada, en unidades de token y en dólares) y P&L de los 7 originales (incluye los 4 descartados, que sirven de evidencia en `data/DESCARTADOS-ES.md`). Datos: `data/dossier7.csv`. |
| **`data/VERIFICACION-TRIAGE-ES.md`** | **Veredicto de las 226 filas del escáner**: 7 pools marcados como vulnerables ($42.250 de botín), **de los cuales 4 resultaron falsos positivos de valoración** (ver `data/DESCARTADOS-ES.md`) ⇒ quedan 3 candidatos, 61 condicionalmente vulnerables según el valor de la pata sin precio ($974.855) y **54 etiquetados `STILL-EXPOSED` que en realidad dan P&L negativo**. Reproduce exactamente el `p*` de la tabla B por un camino independiente. |
| `verify_triage.py` | Verifica la columna `risk` con aritmética exacta. Simula el ataque completo en dólares (todas las operaciones del exploit son lineales en el balance de la pata en polvo), con `bmath_sim` para v1 y `v2_weighted` para v2. Datos: `data/triage_v1.csv`, `data/triage_v2.csv`. |
| **`data/V2-HALLAZGO-ES.md`** | **¿Sobrevive el fallo en Balancer V2?** Sí, y con menos capital: `JoinKind.TOKEN_IN_FOR_EXACT_BPT_OUT` es el hermano de `joinswapPoolAmountOut`. Mismo estado ⇒ +$97.927 con $7.546 en 7 llamadas (V1: +$97.639 con $36.303 en 20). En V2 el umbral ρ\* desaparece (todo ρ<1 es rentable). |
| `v2_weighted.py` | Réplica de la aritmética de `WeightedMath._calcTokenInGivenExactBptOut` / `_calcTokenOutGivenExactBptIn` (V2) con los topes `3e18` / `0,7e18`, barrido fracción × nº de llamadas y control en ρ=1. |
| `open_balanced.py` | ¿Se puede **abrir** un pool que hoy está por encima del umbral? Barrido de 800 combinaciones (swap / donate+gulp / nada × empuje × n × pesos): todas negativas. ρ* es el punto de beneficio cero por construcción. |
| `flashloan_grid.py` | Busca si el ataque con flash loan (comprimir→diluir→exit) es viable desde un pool equilibrado. |
| `data/pools.tsv` | Inventario de 113 pools aportado por el usuario (anonimizado a los campos usados). |
| `patches/balancer-v1-hardening.patch` | Parche propuesto (P1 contención / P2 causa raíz / P3 robustez). Se aplica limpio con `git apply`. **No compilado en este entorno** (sin `node_modules`): validar con `solc 0.5.12` + `truffle test` antes de desplegar. |

## Reproducir

No requiere dependencias (sólo Python 3):

```bash
python3 security/experiments.py          # E1-E7
python3 security/rounding_search.py      # S1-S4
python3 security/economics.py            # capital/botin/ROI
python3 security/screen.py               # rho* y curva de profit
python3 security/flashloan_grid.py       # viabilidad del flash loan
python3 security/triage.py inventory security/data/pools.tsv
python3 security/analyze_live.py          # veredicto de los 100 pools con datos reales
python3 security/analyze_live.py --capital # cuanto tiene que comprar el atacante, por pool
python3 security/v2_weighted.py          # el mismo ataque sobre la aritmetica de Balancer V2
python3 security/verify_triage.py        # veredicto real de los pools del escaner
python3 security/dossier7.py             # traza del ataque de los 7 vulnerables
```

Aplicar el parche en una rama de trabajo:

```bash
git apply --check security/patches/balancer-v1-hardening.patch
git apply security/patches/balancer-v1-hardening.patch
```

## Aviso sobre el entorno

`yarn install` no pudo completarse (el registro npm no es accesible desde este sandbox),
por lo que la suite de Truffle (`test/*.js`) **no** se ha ejecutado. Todas las
afirmaciones numéricas del informe provienen del simulador entero exacto, no de un
nodo EVM.
