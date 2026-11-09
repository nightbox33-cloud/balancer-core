# Balancer V2: el mismo fallo, y más expuesto

**Alcance:** `balancer/balancer-v2-monorepo` @ `e91a2b6` (clon `--depth 1`).
**Método:** lectura del fuente + réplica de la aritmética de `WeightedMath.sol` en `security/v2_weighted.py` (Decimal de 60 dígitos, redondeo en la dirección que marca el contrato).
**Reproducir:** `python3 security/v2_weighted.py`.

---

## Veredicto

El camino hermano de `joinswapPoolAmountOut` **existe en V2, se llama distinto y no está mitigado**:

> `JoinKind.TOKEN_IN_FOR_EXACT_BPT_OUT` → `WeightedMath._calcTokenInGivenExactBptOut()`

Sobre el **mismo estado** que usé para V1 (`0x9a16bddf`: 20 % USDC / 80 % OCEAN, fee 2,5 %), el ataque
en V2 **gana lo mismo con 4,8× menos capital y 6× menos llamadas**:

| | llamadas | BPT acuñado | depósito | salida | **P&L** |
|---|---:|---:|---:|---:|---:|
| V1 (`joinswapPoolAmountOut` ×19 + `exitPool`) | 20 | 78,03 % | $36.303 | $133.942 | **+$97.639** |
| **V2** (`TOKEN_IN_FOR_EXACT_BPT_OUT` ×3 + `EXACT_BPT_IN_FOR_ONE_TOKEN_OUT` ×4) | **7** | 70,37 % | **$7.546** | $105.475 | **+$97.927** |

Y no es un pool concreto: **en V2 todo pool con ρ < 1 es rentable** (ρ = 1 da −$1 exacto, la igualdad
AM-GM). En V1 el umbral era ρ\* ∈ [0,845; 0,958] **porque lo imponía el código** (`MAX_IN_RATIO`).
V2 sustituyó ese tope por uno sobre el *supply*, que el atacante satisface pagando más ⇒ **V2 amplía
el conjunto de pools atacables, no lo reduce**.

---

## 1. Dónde está el código

| Pieza | Ubicación |
|---|---|
| Kind de entrada (equivale a `joinswapPoolAmountOut`) | `pkg/interfaces/contracts/pool-weighted/WeightedPoolUserData.sol` — `JoinKind.TOKEN_IN_FOR_EXACT_BPT_OUT` = 2 |
| Kind de salida (equivale a `exitswapPoolAmountIn`) | ídem — `ExitKind.EXACT_BPT_IN_FOR_ONE_TOKEN_OUT` = 0 |
| Despacho | `pkg/pool-weighted/contracts/BaseWeightedPool.sol:256` (`_doJoin`) — **sin restricción** en `WeightedPool`; sólo `LiquidityBootstrappingPool` (l.229) y `ManagedPoolAmmLib` (l.75) lo capan |
| Entrada mono-token | `BaseWeightedPool.sol` (`_joinTokenInForExactBPTOut`) → `WeightedMath.sol:274` |
| Salida mono-token | `BaseWeightedPool.sol` (`_exitExactBPTInForOneTokenOut`) → `WeightedMath.sol:423` |

El propio fuente lo dice sin ambigüedad:

```solidity
// BaseWeightedPool._joinTokenInForExactBPTOut
// Note that there is no maximum amountIn parameter: this is handled by `IVault.joinPool`.
```

y lo que hace el Vault es:

```solidity
// pkg/vault/contracts/PoolBalances.sol:245
_require(amountIn <= change.limits[i], Errors.JOIN_ABOVE_MAX);
```

`change.limits` **lo elige el llamante**. No hay mínimo de balance por token, no hay comprobación de
que la composición resultante siga siendo razonable, no hay referencia de precio.

## 2. Los cuatro controles de V2, uno por uno

| Control | Qué acota realmente | ¿Cubre el fallo? |
|---|---|---|
| Redondeo hacia arriba en la entrada / hacia abajo en la salida | Fuga de 1 wei por operación | **No.** El exploit no es de redondeo: es el hueco de valor entre la curva y el precio. Cerrarlo no cambia nada (mi modelo lo aplica y el P&L sigue siendo positivo). |
| `_MAX_INVARIANT_RATIO = 3e18` (`WeightedMath.sol:42`, `require` en l.294) | `bptOut ≤ 2·supply` **por llamada** | **No.** Acota cuánto supply se acuña, no cuánto desequilibrio se crea. El atacante elige la fracción (mi barrido óptimo usa pasos de 0,02 a 0,5, no el tope) y repite. Su comentario — *"non-proportional joins cannot cause the invariant to increase by more than this ratio"* — describe exactamente la intención que no consigue. |
| `_MIN_INVARIANT_RATIO = 0.7e18` (`WeightedMath.sol:44`, l.444) | Quema ≤ 30 % del supply por llamada | **No.** Sólo obliga a trocear la salida en 4 llamadas. |
| `_MIN_WEIGHT = 0.01e18` | Peso mínimo 1 % | **No**, y en la dirección contraria: los pesos bajos son legales y **empeoran** el ataque (§6). |

Comparación con V1: allí el único freno era `MAX_IN_RATIO = BONE/2`, un tope **sobre el balance**, que
al menos obligaba a iterar. V2 lo reemplazó por un tope **sobre el supply**, que es una magnitud que el
atacante controla mintiendo BPT. La contención accidental desapareció.

## 3. Aritmética (por qué el coste sigue siendo lineal)

Con `R = (S + bptOut) / S` (ratio de invariante) y `w_i` el peso de la pata en polvo:

```
coste   = b_i · (R^(1/w_i) − 1) / (1 − fee_i)      fee_i = fee·(1 − w_i)     [WeightedMath:299-308]
salida  = b_j · (1 − R'^(1/w_j))                    R' = (S − bptIn)/S        [WeightedMath:440-452]
```

El coste es **lineal en `b_i`**: pagas proporcionalmente a lo que ya hay en la pata en polvo, sin ninguna
referencia al valor de lo que recibes. Es el mismo defecto de V1, con otra notación. La ganancia es la
diferencia entre el precio marginal de la curva y el precio medio que pagas — el hueco AM-GM: es
estrictamente positiva para todo ρ < 1 y se anula sólo en ρ = 1 (igualdad de la media aritmético-geométrica).
Eso es lo que se ve numéricamente en §4: la fila ρ = 1 da exactamente −$1 en los tres pesos.

## 4. Umbral ρ\*: V2 no tiene umbral

Pool de TVL $200.000, fee 0,3 %, ataque óptimo (barrido de fracción × nº de llamadas). P&L en % del TVL:

| ρ (pata en polvo) | w = 0,20 | w = 0,50 | w = 0,80 |
|---:|---:|---:|---:|
| 0,20 | +16,08 % | +39,89 % | +62,75 % |
| 0,40 | +6,80 % | +19,85 % | +38,40 % |
| 0,60 | +2,53 % | +8,24 % | +19,05 % |
| 0,80 | +0,54 % | +1,99 % | +5,78 % |
| 0,90 | +0,13 % | +0,49 % | +1,64 % |
| 0,95 | +0,03 % | +0,11 % | +0,44 % |
| **1,00** | **−$1** | **−$1** | **−$1** |
| **ρ\* V1 (por código)** | **0,845** | **0,899** | **0,958** |

Lectura: V1 **bloqueaba** los pools con ρ entre su ρ\* y 1. V2 no bloquea ninguno; sólo hace que el
beneficio tienda a cero al acercarse a ρ = 1. En términos prácticos el umbral de V2 lo fija el gas, no
el contrato: con TVL de $200k, ρ = 0,95 aún da $58–$884 y ρ = 0,90 da $251–$3.273. Todo pool con
ρ ≲ 0,9 es atacable con beneficio neto.

## 5. La ganancia no depende del supply

Variando `supply real / invariante` de 1 a 100 sobre `0x9a16bddf`, el resultado es **idéntico**
(depósito $7.546, P&L +$97.929 en los seis casos; la diferencia de $2 con la tabla de cabecera es el
redondeo del balance de entrada, $16,38 vs. su valor con más decimales). No es casualidad: el coste depende sólo de `R` y del
balance, y la fracción cobrada sólo de `R'`. La ganancia depende únicamente de
`(b_polvo / b_grande, w, fee)`; el tamaño del pool sólo fija el valor absoluto. Esto elimina la duda de
«supply colapsada» que sí condicionaba la lectura de V1.

## 6. Sensibilidad al peso (pata en polvo de $0,01, TVL $200k, fee 0,3 %)

| peso pata polvo | joins+exits | depósito | P&L | % de la pata grande drenado |
|---:|---:|---:|---:|---:|
| 0,05 | 7+2 | $6.344 | +$89.508 | 50,4 % |
| 0,10 | 7+4 | $3.545 | +$132.840 | 75,8 % |
| 0,20 | 6+7 | $1.942 | +$150.395 | 95,2 % |
| 0,50 | 6+12 | $41 | +$99.934 | 100,0 % |
| 0,80 | 4+8 | $0,31 | +$40.000 | 100,0 % |

## 7. Coste de ejecución

3 joins + 4 exits ≈ 7 llamadas × ~120k gas ≈ 840k gas. A 30 gwei y $3.000/ETH ≈ **$76** de gas, más
~0,05 % de flash loan sobre $7.546 ≈ **$4**. Total ≈ **$80** frente a un botín de **$97.927**
(ROI ≈ 1.200×). En V1 el mismo resultado exigía 20 llamadas.

## 8. Qué lo arregla

No es un fallo de redondeo ni de invariante: es que el invariante **no tiene referencia de precio**.
Las tres vías reales:

1. **Mínimo de balance por token** en joins/exits no proporcionales — exactamente lo que V1 rechazó en
   `Audit.md` #210 (*`min_token_balance`*, WONT FIX) y lo que aplica mi parche P1
   (`security/patches/balancer-v1-hardening.patch`). Con `b_i ≥ ε·TVL/w_i` el ataque deja de ser rentable.
2. **Acotar el desequilibrio (ρ), no el supply**, en `_doJoin`/`_doExit`: rechazar si la composición
   resultante se aleja más de X % del equilibrio.
3. **Oráculo de precios** para toda operación no proporcional (join/exit mono-token), comparando el
   valor que entra con el que sale; es lo único que cierra la causa raíz, porque el hueco AM-GM es
   explotable en cualquier estado ρ < 1.

## 9. Límites de este análisis

- Cubre `WeightedPool` de 2 tokens (`pkg/pool-weighted`), que es la forma mayoritaria en V2. **No**
  cubre `ComposableStablePool` ni `StableMath` (curva distinta; el mismo patrón de join/exit mono-token
  existe pero requiere un modelo aparte — no lo afirmo aquí).
- El estado de `0x9a16bddf` se reinyecta en la aritmética de V2 para comparar contra V1 con las mismas
  cifras. **No** afirmo que ese pool concreto exista en V2; lo que se demuestra es que *cualquier* pool
  V2 con ese estado (ρ = 0,0024) es explotable con esa aritmética.
- Los importes en dólares usan los mismos precios que la tabla V1 (`data/pools_live.csv`), para que la
  comparación sea homogénea. La magnitud **independiente de precio** es el 78 % de la pata grande
  drenado con el 70,37 % del supply.
- Nada de esto se ha ejecutado contra un nodo: es lectura de fuente + simulación determinista.
  No hay `node_modules` en el entorno, así que no se ha corrido la suite de Truffle/Hardhat de V2.
