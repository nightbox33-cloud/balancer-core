# `security/` — Auditoría Balancer V1 (balancer-core)

Artefactos del análisis de seguridad del commit `f4ed5d6` (master).

| Archivo | Qué es |
|---|---|
| **`REPORTE-BALANCER-V1-ES.md`** | **Informe principal.** Empieza por la tabla de hallazgos (§0). |
| `bmath_sim.py` | Réplica exacta en Python de `BNum.sol` + `BMath.sol` (mismo redondeo *half-up*, misma precisión `1e8` en `bpowApprox`, mismos `require`) y modelo de `BPool` para las rutas relevantes. |
| `experiments.py` | E1-E7: reproducción del bug principal, la variante `joinswapExternAmountIn`, el caso de 18 decimales, la economía end-to-end, los DoS (`exitPool`, `gulp→0`) y el blow-up de `bpow`. |
| `rounding_search.py` | S1-S4: búsqueda exhaustiva de ciclos rentables por redondeo (join/exit, swap ida-vuelta, join-swap/exit-swap) a escala normal y con reservas en polvo. |
| `economics.py` | Capital / botín / ROI del ataque completo sobre pools balanceados a precio de mercado, en función del factor de compresión. |
| `patches/balancer-v1-hardening.patch` | Parche propuesto (P1 contención / P2 causa raíz / P3 robustez). Se aplica limpio con `git apply`. **No compilado en este entorno** (sin `node_modules`): validar con `solc 0.5.12` + `truffle test` antes de desplegar. |

## Reproducir

No requiere dependencias (sólo Python 3):

```bash
python3 security/experiments.py
python3 security/rounding_search.py
python3 security/economics.py
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
