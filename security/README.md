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
| **`analyze_live.py`** | Calcula `ρ` por pool sobre `data/pools_live.csv`, simula el ataque real (`n × joinswapExternAmountIn` + `exitPool`/`exitswapPoolAmountIn`) con contabilidad en enteros exactos y emite el ranking. `--md` genera las tablas del informe. |
| `data/pools_live.csv` | Los 100 pools activos con pesos, balances, precios, `usd_per_token` y supply (datos aportados por el usuario). Es la fuente de verdad del cálculo de `ρ`. |
| **`TRIAGE-POOLS-ES.md`** | **Triaje del inventario de pools**: qué se descarta, en qué orden revisar el resto y por qué el TVL / el flash loan no son buenos criterios. |
| `triage.py` | `inventory` (clasifica el CSV del escáner) y `screen` (veredicto real por pool a partir de balance/decimals/denorm/precio por token). |
| `screen.py` | Curva de rentabilidad `rho → P&L` y umbrales `rho*` por peso (aritmética exacta). |
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
