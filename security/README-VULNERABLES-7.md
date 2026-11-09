# Los 3 pools vulnerables

Tres pools donde el bug de Balancer v1/v2 es **cobrable hoy**: **$30.676 de botín** con **$1.765 de
capital** sobre **$40.589 de TVL**.

| # | pool | ver. | tipo | fee | TVL | pata en polvo (ρ) | capital | botín | ROI | causa |
|---|---|---|---:|---:|---|---:|---:|---:|---:|---|
| 1 | `0x1373e57f` | v1 | BPool 8 tokens (12,5 % c/u) | 1,00 % | $29.298 | USDC (ρ≈0) | **$9** | **$29.026** | 3.225× | patas muertas |
| 2 | `0xc3516482` | v1 | WETH / REPv2 (20/80) | 0,30 % | $10.056 | WETH (ρ=0,313) | $1.497 | $993 | 0,66× | peso extremo |
| 3 | `0xcf8dfdb7` | v2 | st-yETH / GOLD (40/60) | 1,00 % | $1.235 | GOLD (ρ=0,160) | $259 | $657 | 2,54× | desequilibrio puro |

«ROI» = botín / capital. En el #2 es menor que 1 porque el capital (que se recupera) supera al
beneficio; lo que cuenta es el P&L neto.

Reproducir: `python3 security/dossier7.py` (datos en `security/data/dossier7.csv`).

---

## 1. El bug

### 1.1 La operación

Entrar con **un solo token** pidiendo una cantidad exacta de BPT, y salir quemando BPT contra **un solo
token**. En v1: `joinswapPoolAmountOut` → `calcSingleInGivenPoolOut` (`contracts/BMath.sol:156`); en v2:
`JoinKind.TOKEN_IN_FOR_EXACT_BPT_OUT` → `WeightedMath.sol:274`.

```
# entrada, v1 BMath.sol:173
poolRatio = (pS + pAo) / pS
nuevoBal  = b_i · poolRatio^(1/w_i)
amountIn  = (nuevoBal − b_i) / (1 − (1−w_i)·fee)

# salida mono-token, BMath.sol:195
amountOut = b_j · (1 − (1 − pAi/pS)^(1/w_j)) · (1 − (1−w_j)·fee)
```

### 1.2 Por qué no mira el valor

`amountIn` es **lineal en `b_i`**, el balance de la pata por la que entras. No aparece en ningún sitio
el precio ni el valor de lo que se lleva el depositante: el contrato cobra «lo que hace falta para
reponer el equilibrio de la curva», no «lo que vale lo que te llevas».

En un pool equilibrado (todos los `b_i/w_i` iguales) las dos cosas coinciden — es la igualdad de la
media aritmético-geométrica — y no hay nada que rascar. En cuanto hay desequilibrio, el precio marginal
de la pata escasa es **menor** que el valor medio por BPT, y el BPT acuñado es un derecho **pro-rata
sobre el valor medio**. La diferencia se cobra en la salida.

### 1.3 La métrica

```
ρ_i = v_i / (w_i · TVL)        v_i = valor de la pata i, w_i = su peso
```

- `ρ_i < 1` ⇒ la pata está por debajo de su peso en valor ⇒ **es la pata por la que se entra**.
- `ρ_i > 1` ⇒ es la pata por la que se **sale**.
- `ρ_i = 1` en todas ⇔ pool equilibrado ⇔ P&L 0 (verificado: **−$1** exacto por fees).

### 1.4 La secuencia

1. **Entrar** por la pata en polvo, troceando: v1 limita a `MAX_IN_RATIO = 50 %` del balance de esa
   pata (`BConst.sol:39`), así que se repite `b ← 1,5·b` hasta reunir el BPT que se quiera; v2 limita a
   `_MAX_INVARIANT_RATIO = 3` sobre el supply (acuñar hasta 2× por llamada).
2. **Salir** por la pata con ρ alto: `exitswapPoolAmountIn` (mono, tope `MAX_OUT_RATIO = 33,3 %` del
   balance, `BPool.sol:642`) o `exitPool` (pro-rata). En v2, quemar ≤30 % por llamada.
3. **Cobrar**: el BPT vale el valor medio; lo pagaste al precio marginal de la pata escasa.

**No hay «doble cap» en v1**: la única condición de `exitswapPoolAmountIn` es `MAX_OUT_RATIO` sobre el
balance. El «BPT/supply ≤ 1/3» es de v2 (`_MAX_INVARIANT_RATIO`) y allí actúa sobre el *supply*, no
sobre el desequilibrio — por eso v2 no tiene umbral ρ\*: **todo pool con ρ < 1 es rentable** y el corte
práctico lo pone el gas.

---

## 2. Los tres, uno por uno

### 2.1 `0x1373e57f764a7944bdd7a4bd5ca3007d496934da` — siete patas muertas

**Qué es.** BPool de 8 tokens con pesos iguales (12,5 %), fee 1 %, TVL $29.298,13, supply 104.336,94
BPT. Factoría original (`codesize` 22.537), finalizado, sin pausa. Tokens: `0x0ba45a8b`, DAI, USDC,
WETH, MKR, UMA, LINK, SNX.

**Por qué es vulnerable.** Siete patas vaciadas, una con todo:

| pata | valor | peso | ρ |
|---|---:|---:|---:|
| `0x0ba45a8b` | $29.297,98 | 12,5 % | **8,00** |
| MKR / UMA / SNX | $0,03 c/u | 12,5 % | ≈ 0 |
| DAI / LINK | $0,02 c/u | 12,5 % | ≈ 0 |
| WETH | $0,01 | 12,5 % | ≈ 0 |
| USDC | $0,00 | 12,5 % | ≈ 0 |

Una sola pata concentra el **99,99994 %** del valor con el 12,5 % del peso. Por cualquiera de las otras
siete se entra prácticamente gratis.

**Cómo se explota.** 21 `joinswapPoolAmountOut` metiendo USDC, empezando por **0,000903 USDC**, que
acuñan 5.384 BPT. Capital total: **$9**. Con el 65,24 % del supply se sale en **mono** contra la pata
viva: **$29.035,43**. P&L **+$29.026**.

**Por qué la salida es mono y no pro-rata.** Con `w = 0,125` el exponente es `1/w = 8`, y
`1 − (1 − 0,6524)^8 = 0,99979`: quemando el 65 % del supply te llevas el **99,98 % de la pata**. Ése es
todo el ataque. `exitPool` daría sólo el 65 % de cada pata y además revierte con `ERR_MATH_APPROX` en
cuanto una pata da cero (`BPool.sol:413`).

**Por qué el contrato lo permite.** Acuñar el 65 % del supply cuesta `b·(1,65^8 − 1) = b·54,3`, con `b`
el balance de USDC: **$0,0018**. El pool te cobra por reponer el USDC que falta, no por el `0x0ba45a8b`
que te llevas. `MIN_BALANCE = 1e6` wei no protege: el balance no es cero, es pequeño **en valor**.

> **Pendiente:** el 100 % del TVL es `0x0ba45a8b` a $55,134. El mecanismo no depende del precio (la
> fracción drenada es exacta); el importe sí. Falta medir la salida de 531 unidades.

---

### 2.2 `0xc351648240e9fc9213e8b6016e566f95c5fa7909` — peso extremo 20/80

**Qué es.** BPool WETH 20 % / REPv2 80 %, fee 0,30 %, TVL $10.055,75, supply 100 BPT.

**Por qué es vulnerable.**

| pata | valor | peso | ρ |
|---|---:|---:|---:|
| REPv2 | $9.425,45 | 80 % | 1,172 |
| WETH | $630,30 | 20 % | **0,313** |

El 20 % de peso de WETH aporta sólo el **6,3 %** del valor.

**Cómo se explota.** 3 joins de WETH (0,148 + 0,223 + 0,334 = 0,705 WETH = $1.497), f = 21,56 %, salida
pro-rata: $2.490,43. P&L **+$993**.

**Por qué el contrato lo permite.** Con `w = 0,2` el exponente es 5: el BPT sale barato en cuanto el
peso es bajo. Cuanto más extremo el peso, menos hay que mover el precio para desequilibrar el pool — y
éste ya venía desequilibrado.

> **Pendiente:** probar la salida por **REPv2** o pro-rata. Entrar y salir por WETH es un wash por
> construcción (`2 × fee × 0,28 = 0,00168`) y no dice nada del pool.

---

### 2.3 `0xcf8dfdb73e7434b05903b5599fb96174555f4353` — el mejor ROI y sin inventario

**Qué es.** WeightedPool v2 (factoría v4, `codesize` 24.252), st-yETH 40 % / GOLD 60 %, fee 1 %,
TVL $1.235,45, supply 114,93 BPT.

**Por qué es vulnerable.**

| pata | valor | peso | ρ |
|---|---:|---:|---:|
| st-yETH | $1.116,95 | 40 % | **2,260** |
| GOLD | $118,50 | 60 % | **0,160** |

GOLD tiene el 60 % del peso y aporta el **9,6 %** del valor.

**Cómo se explota.** Un join de fracción 1 (acuñar el 100 % del supply, dentro del tope de 2) y 2 exits:
capital **$258,76** → cobrado **$916,22**. P&L **+$657**, ROI **2,54×**.

**Por qué es el más limpio.** Las dos patas tienen salida y **GOLD se puede comprar** a $1,0037: el
atacante no necesita inventario. Compra $259 de GOLD, entra, sale con st-yETH y vende.

> **Pendiente:** los dos precios. Si st-yETH vale como ETH (~$2.123) en vez de $55,42, la pata pasa a
> ~$42.780 y ρ_GOLD cae a **0,005**: el pool sería mucho más vulnerable y el botín mayor.

---

## 3. Cómo se cierra

1. **Mínimo de balance por token en valor** (no en wei): rechazar el join/exit no proporcional si deja
   una pata por debajo de `ε·TVL`. Es lo que v1 rechazó en `Audit.md` #210 (`min_token_balance`,
   WONT FIX) y lo que aplica `security/patches/balancer-v1-hardening.patch` (P1). Cierra #1 y #3.
2. **Acotar ρ, no el supply.** En v2, sustituir `_MAX_INVARIANT_RATIO` por un límite sobre el
   desequilibrio resultante.
3. **Oráculo para operaciones no proporcionales.** Comparar el valor que entra con el que sale: sin
   referencia de precio, cualquier curva AM-GM sigue siendo explotable en cuanto se desequilibra.

**Límites.** Cálculo estático + simulación determinista, nada ejecutado contra un nodo. Los precios son
los de `usd_per_token` del escáner: la **fracción** drenada no depende del precio, el **importe** sí —
tratar la columna de botín como cota superior a precio de marca.

**Descartados.** Cuatro pools de la lista original eran falsos positivos de valoración; la prueba está
en `security/data/DESCARTADOS-ES.md`.
