# Los 7 pools vulnerables: qué son, por qué lo son y cómo se explota cada uno

Este documento explica, uno por uno, los 7 pools de la lista que **hoy son rentables de atacar** con
aritmética exacta (`verify_triage.py`: P&L > $100). Total: **$42.044 de botín** con **$17.468 de
capital** comprometido.

Reproducir: `python3 security/dossier7.py` (datos en `security/data/dossier7.csv`).

---

## 0. Resumen

| # | pool | versión | tipo | tokens (pesos) | fee | TVL | pata en polvo (ρ) | capital | botín | ROI | causa |
|---|---|---|---|---|---:|---:|---|---:|---:|---:|---|
| 1 | `0x1373e57f` | v1 | BPool 8 tokens | 0x0ba45a8b + 7 patas iguales (12,5 %) | 1,00 % | $29.298 | USDC (ρ≈0) | **$9** | **$29.026** | 3.225× | patas muertas |
| 2 | `0xf0f8b1ce` | v1 | BPool | MIMO / PAR (50/50) | 0,15 % | $17.435 | PAR (ρ=0,285) | $10.108 | $5.188 | 0,51× | par desarbitrado |
| 3 | `0x5b1c06c4` | v2 | WeightedPool v1 | PAR / MIMO (75/25) | 0,15 % | $9.059 | PAR (ρ=0,445) | $1.894 | $2.732 | 1,44× | par desarbitrado |
| 4 | `0x30cb8593` | v1 | BPool | UNI-V2 / WETH (50/50) | 3,75 % | $3.883 | WETH (ρ=0,043) | $3.128 | $2.720 | 0,87× | desequilibrio puro |
| 5 | `0xc3516482` | v1 | BPool | WETH / REPv2 (20/80) | 0,30 % | $10.056 | WETH (ρ=0,313) | $1.497 | $993 | 0,66× | peso extremo |
| 6 | `0xa5533a44` | v2 | WeightedPool v1 | PAR / MIMO (20/80) | 0,15 % | $4.507 | PAR (ρ=0,200) | $573 | $727 | 1,27× | par desarbitrado |
| 7 | `0xcf8dfdb7` | v2 | WeightedPool v4 | st-yETH / GOLD (40/60) | 1,00 % | $1.235 | GOLD (ρ=0,160) | $259 | $657 | 2,54× | desequilibrio puro |
| | | | | | | **$75.474** | | **$17.468** | **$42.045** | | |

«ROI» = botín / capital. Para el #2 y el #4 el ROI es menor que 1: hace falta poner más de lo que se
saca, pero el capital **se recupera** (entra y vuelve a salir); lo que cuenta es el P&L neto.

---

## 1. El bug: qué tienen en común los 7

### 1.1 La operación que se explota

Los siete exponen la misma ruta: **entrar con un solo token pidiendo una cantidad exacta de BPT** y
**salir quemando BPT contra un solo token**. En v1 es `joinswapPoolAmountOut` → `calcSingleInGivenPoolOut`
(`contracts/BMath.sol:156`); en v2 es `JoinKind.TOKEN_IN_FOR_EXACT_BPT_OUT` → `WeightedMath.sol:274`.

El coste de esa entrada, en ambos:

```
poolRatio = (pS + pAo) / pS                     # v1, BMath.sol:173
nuevoBal = b_i · poolRatio^(1/w_i)              # w_i = peso normalizado de la pata i
amountIn = (nuevoBal − b_i) / (1 − (1−w_i)·fee)
```

y la salida mono-token (`BMath.sol:195`, `WeightedMath.sol:423`):

```
amountOut = b_j · (1 − (1 − pAi/pS)^(1/w_j)) · (1 − (1−w_j)·fee)
```

Idénticas salvo notación: v2 escribe `(S+bptOut)/S` donde v1 escribe `(pS+pAo)/pS`, y `1/w_i` en vez
de `tW/w_i`.

### 1.2 Por qué el coste no mira el valor

Fíjate en la fórmula: `amountIn` es **lineal en `b_i`**, el balance de la pata por la que entras. No
aparece en ningún sitio el precio ni el valor de lo que recibe el depositante. El contrato cobra «lo
que hace falta para reponer el equilibrio de la curva», no «lo que vale lo que te llevas».

Esa es toda la vulnerabilidad. En un pool **equilibrado** (todos los `b_i/w_i` iguales) ambas cosas
coinciden y no hay nada que rascar: es la igualdad de la media aritmético-geométrica. En cuanto hay
desequilibrio, el precio marginal que cobra el pool por la pata escasa **es menor** que el valor medio
por BPT, y el BPT acuñado es un derecho **pro-rata sobre el valor medio**. La diferencia se cobra en
la salida.

### 1.3 La métrica: ρ

```
ρ_i = v_i / (w_i · TVL)        v_i = valor de la pata i, w_i = su peso
```

- `ρ_i = 1` para todas las patas ⇔ pool en equilibrio ⇔ ataque con P&L 0 (empate AM-GM, verificado:
  da **−$1** exacto por fees).
- `ρ_i < 1` ⇒ la pata `i` está por debajo de su peso en valor ⇒ **es la pata por la que hay que
  entrar**. Cuanto menor, más caro le sale al pool reponerla y más barato te vende el BPT.
- `ρ_i > 1` ⇒ es la pata por la que hay que **salir**.

En los 7, la pata en polvo tiene ρ ≤ 0,445. En el #4, ρ = 0,043.

### 1.4 La secuencia, en tres pasos

1. **Entrar por la pata en polvo**, troceando: en v1 el tope por llamada es `MAX_IN_RATIO = 50 %` del
   balance de esa pata (`BConst.sol:39`), así que se repite `b ← 1,5·b` hasta reunir el BPT que se
   quiera; en v2 el tope es `_MAX_INVARIANT_RATIO = 3` (acuñar hasta 2× el supply por llamada).
2. **Salir por la pata con ρ alto**: `exitPool` (pro-rata) o `exitswapPoolAmountIn` (mono-token).
   En v1 el tope es `MAX_OUT_RATIO = 33,3 %`; en v2, `_MIN_INVARIANT_RATIO = 0,7` (quemar ≤30 % por llamada).
3. **Cobrar**: el BPT vale el valor medio del pool; lo pagaste al precio marginal de la pata escasa.

### 1.5 v1 y v2 fallan igual, pero no por el mismo motivo del código

| | v1 (BPool) | v2 (WeightedPool) |
|---|---|---|
| Ruta | `joinswapPoolAmountOut` (BPool.sol:584) | `JoinKind.TOKEN_IN_FOR_EXACT_BPT_OUT` (2) |
| Tope de entrada | `MAX_IN_RATIO = 50 %` del **balance** de la pata | `_MAX_INVARIANT_RATIO = 3` sobre el **supply** |
| Tope de salida | `MAX_OUT_RATIO = 33,3 %` del balance | `_MIN_INVARIANT_RATIO = 0,7` del supply |
| Redondeo | half-up en todo | up en entrada, down en salida |
| ¿Frena el ataque? | No: sólo obliga a iterar | **Menos aún**: el tope es sobre una magnitud que el atacante controla pagando |

En v2 el único control añadido respecto a v1 es el ratio de invariante, y ese limita *cuánto BPT se
acuña por llamada*, no *cuánto desequilibrio se crea*. El atacante usa fracciones pequeñas (20 %, 10 %)
y repite. Por eso v2 no tiene umbral ρ\*: **todo pool con ρ < 1 es rentable**, y el corte práctico lo
pone el gas.

---

## 2. Los 7, uno por uno

### 2.1 `0x1373e57f764a7944bdd7a4bd5ca3007d496934da` — siete patas muertas

**Qué es.** BPool de **8 tokens con pesos iguales (12,5 %)**, fee 1 %, TVL $29.298,13, supply
104.336,94 BPT. Código de la factoría original (`codesize` 22.537), finalizado, no pausado y no
pausable. Los tokens: `0x0ba45a8b`, DAI, USDC, WETH, MKR, UMA, LINK, SNX.

**Por qué es vulnerable.** Siete de las ocho patas están vaciadas. Valores:

| pata | valor | peso | ρ |
|---|---:|---:|---:|
| `0x0ba45a8b` | $29.297,98 | 12,5 % | **8,00** |
| MKR | $0,03 | 12,5 % | 0,0000 |
| UMA / SNX | $0,03 | 12,5 % | 0,0000 |
| DAI | $0,02 | 12,5 % | 0,0000 |
| LINK | $0,02 | 12,5 % | 0,0000 |
| WETH | $0,01 | 12,5 % | 0,0000 |
| USDC | $0,00 | 12,5 % | 0,0000 |

Una sola pata concentra el 99,99994 % del valor con el 12,5 % del peso (ρ = 8) y las otras siete están
en ρ ≈ 0: por cualquiera de ellas se entra prácticamente gratis.

**Cómo se explota.** 21 llamadas a `joinswapPoolAmountOut` metiendo USDC, empezando por
**0,000903 USDC** (sí, un décimo de céntimo), que acuñan 5.384 BPT. Capital total: **$9**. Con el
65,24 % del supply se quema en `exitswapPoolAmountIn` contra la pata viva y se cobran
**$29.035,43**. P&L **+$29.026**.

**Por qué el contrato lo permite.** Con `w = 0,125` el exponente es `1/w = 8`. Acuñar el 65 % del
supply cuesta `b·(1,65^8 − 1) = b·54,3`, donde `b` es el balance de la pata de entrada: **$0,0018 de
USDC**. El pool te cobra por «reponer el USDC que falta», no por el `0x0ba45a8b` que te llevas.
`MIN_BALANCE = 1e6` wei no protege: el balance no es cero, es pequeño **en valor**.

---

### 2.2 `0xf0f8b1ce9d95dfbe82f8310d48dcae71d79f9519` — el pool del PoC (PAR/MIMO)

**Qué es.** BPool de **2 tokens al 50 %, MIMO/PAR**, fee 0,15 %, TVL $17.435,36, supply 25.102,79 BPT.
Es exactamente el pool del PoC original. MIMO es el token de incentivos (mStable) y PAR el token de
precio objetivo.

**Por qué es vulnerable.**

| pata | balance | precio | valor | ρ |
|---|---:|---:|---:|---:|
| MIMO | 5.350.088,4 | $0,0027938 | $14.947,24 | **1,715** |
| PAR | 2.232,595 | $1,11445 | $2.488,12 | **0,285** |

PAR pesa la mitad del pool y aporta el **14,3 %** del valor. Nadie lo arbitró: para cerrar el hueco
habría que vender MIMO contra el pool, y el MIMO farmeado no tiene demanda.

**Cómo se explota.** 4 joins de 50 % del balance de PAR: 1.116 + 1.674 + 2.512 + 3.768 =
**9.070 PAR ($10.108)**. Con el 55,53 % del supply, `exitPool` (pro-rata) devuelve
6.263 PAR ($6.994) + ~2,97 M MIMO ($8.298). El PAR vuelve a medias; **el MIMO es gratis**.
P&L **+$5.188**.

**Por qué el contrato lo permite.** El join cobra PAR al precio marginal de la curva cuando PAR está
escaso (caro reponerlo… pero el que paga eres tú con PAR, que el pool valora por encima de su precio
de mercado al ponderarlo al 50 %). El BPT acuñado se redime al valor **medio**, donde el MIMO pesa
mucho más. La diferencia entre esas dos valoraciones es el botín.

---

### 2.3 `0x5b1c06c4923dbba4b27cfa270ffb2e60aa286159` — el mismo par, pesos invertidos (v2)

**Qué es.** **WeightedPool v2** (factoría v1, `codesize` 19.384), **PAR 75 % / MIMO 25 %**, fee 0,15 %,
TVL $9.059,40, supply 26.980,52 BPT.

**Por qué es vulnerable.**

| pata | valor | peso | ρ |
|---|---:|---:|---:|
| MIMO | $6.035,31 | 25 % | **2,665** |
| PAR | $3.024,10 | 75 % | **0,445** |

La pata en polvo es **PAR a pesar de tener el 75 % del peso**: MIMO vale el doble con la cuarta parte
del peso. Es el mismo desequilibrio del #2 con los pesos cambiados, y sigue siendo explotable porque
lo que manda es `v_i` contra `w_i`, no el peso solo.

**Cómo se explota.** 2 joins de fracción **0,2** del supply (muy por debajo del tope de 2) + 2 exits
de ≤30 %. Capital $1.894,22 → cobrado $4.626,64. P&L **+$2.732**.

**Por qué el contrato lo permite.** Aquí se ve por qué el hardening de v2 no sirve: `_MAX_INVARIANT_RATIO
= 3e18` permite acuñar hasta el 200 % del supply por llamada y el atacante usa el **20 %**. El tope
está holgadísimo y, sobre todo, mide la magnitud equivocada (supply, no desequilibrio).

---

### 2.4 `0x30cb859317e171832b064c97cc03ccb081954d1b` — desequilibrio puro

**Qué es.** BPool **UNI-V2/WETH 50/50**, fee **3,75 %** (alta), TVL $3.883,45, supply **0,03733535 BPT**.

**Por qué es vulnerable.**

| pata | valor | peso | ρ |
|---|---:|---:|---:|
| UNI-V2 | $3.799,90 | 50 % | **1,957** |
| WETH | $83,55 | 50 % | **0,043** |

WETH aporta el **2,15 %** del valor con el **50 %** del peso. El ρ más bajo de los siete.

**Cómo se explota.** 9 joins metiendo WETH (el primero, 0,0197 WETH), f = 83,41 %, capital $3.128,36 →
$5.848,57. P&L **+$2.720**. Hacen falta 9 llamadas (no 2) por el fee del 3,75 %, que encarece cada paso.

**Un detalle que engaña.** El supply de 0,037 BPT parece la causa y no lo es: el ataque es
**invariante al supply** (comprobado: multiplicarlo por 1, 10, 100 o 1.000 da el mismo P&L al dólar).
Lo que importa es `b_polvo/b_grande`, `w` y la fee. El supply minúsculo es un **síntoma** de que el
pool estuvo vaciado, no el mecanismo.

---

### 2.5 `0xc351648240e9fc9213e8b6016e566f95c5fa7909` — peso extremo 20/80

**Qué es.** BPool **WETH 20 % / REPv2 80 %**, fee 0,30 %, TVL $10.055,75, supply 100 BPT.

**Por qué es vulnerable.**

| pata | valor | peso | ρ |
|---|---:|---:|---:|
| REPv2 | $9.425,45 | 80 % | 1,172 |
| WETH | $630,30 | 20 % | **0,313** |

El 20 % de peso de WETH aporta sólo el **6,3 %** del valor.

**Cómo se explota.** 3 joins de WETH (0,148 + 0,223 + 0,334 = 0,705 WETH = $1.497), f = 21,56 %,
salida pro-rata: $2.490,43. P&L **+$993**.

**Por qué el contrato lo permite.** Con `w = 0,2` el exponente es 5: el BPT sale barato en cuanto el
peso es bajo. Cuanto más extremo el peso, menos hay que mover el precio para desequilibrar el pool —
y este pool ya venía desequilibrado.

> Este es el pool que el PoC usaba como **control negativo**. No lo es: ρ = 0,313 y da +$993.

---

### 2.6 `0xa5533a44d06800eaf2daad5aad3f9aa9e1dc3614` — PAR/MIMO 20/80 (v2)

**Qué es.** **WeightedPool v2** (factoría v1, `codesize` 18.286), **PAR 20 % / MIMO 80 %**, fee 0,15 %,
TVL $4.507,03, supply 486.769,84 BPT.

**Por qué es vulnerable.**

| pata | valor | peso | ρ |
|---|---:|---:|---:|
| MIMO | $4.327,01 | 80 % | 1,200 |
| PAR | $180,02 | 20 % | **0,200** |

**Cómo se explota.** 3 joins de fracción 0,1 + 1 exit. Capital $573 → cobrado $1.299,95.
P&L **+$727**, ROI 1,27×.

**Por qué el contrato lo permite.** Igual que #3. Y el patrón se repite: **tres de los siete pools son
el par PAR/MIMO** (#2, #3, #6), en v1 y en v2, con pesos 50/50, 75/25 y 20/80. Es el mismo fallo de
arbitraje que nadie cerró en ninguno de los tres.

---

### 2.7 `0xcf8dfdb73e7434b05903b5599fb96174555f4353` — el más rentable por dólar

**Qué es.** **WeightedPool v2** (factoría v4, `codesize` 24.252), **st-yETH 40 % / GOLD 60 %**,
fee 1 %, TVL $1.235,45, supply 114,93 BPT.

**Por qué es vulnerable.**

| pata | valor | peso | ρ |
|---|---:|---:|---:|
| st-yETH | $1.116,95 | 40 % | **2,260** |
| GOLD | $118,50 | 60 % | **0,160** |

GOLD tiene el 60 % del peso y aporta el **9,6 %** del valor.

**Cómo se explota.** Un solo join de fracción 1 (acuñar el 100 % del supply, dentro del tope de 2) y
2 exits: capital **$258,76** → cobrado **$916,22**. P&L **+$657**, ROI **2,54×**. Es el mejor ROI de
los siete después del #1.

**Por qué es especialmente peligroso.** A diferencia de los tokens muertos, **GOLD se puede comprar**
($1,0037, con precio de mercado). El atacante no necesita tener el token de antemano: compra $259 de
GOLD, entra, sale con st-yETH y vende. Es un ataque sin inventario.

---

## 3. Cuatro causas, no siete bugs

Los siete son el **mismo bug** en cuatro estados distintos del pool:

| causa | pools | qué lo produce |
|---|---|---|
| **Patas muertas** | #1 | El pool sobrevivió a sus tokens: siete patas a ~0 y una que concentra todo. ρ ≈ 0 ⇒ entrar cuesta céntimos. |
| **Par desarbitrado** | #2, #3, #6 | Un token con precio administrado (PAR) y otro de incentivos (MIMO). El valor relativo se movió 6:1 y nadie vendió MIMO contra el pool. |
| **Desequilibrio puro** | #4, #7 | Un token se apreció (o el otro se hundió) y el pool quedó con una pata al 2–10 % de su peso en valor. |
| **Peso extremo** | #5 | Con w = 0,2 basta un desequilibrio moderado para que el BPT salga barato. |

Los cuatro son la misma condición aritmética: **`min_i ρ_i < ρ*`**. En v1, `ρ*` ∈ [0,845; 0,979] según
el peso (lo imponía `MAX_IN_RATIO`). En v2, `ρ* = 1`.

## 4. Cómo se detecta

```bash
python3 security/dossier7.py      # rho por pata + traza del ataque, pool a pool
python3 security/verify_triage.py # veredicto de las 226 filas del escáner
```

El criterio, sin simulador: **`ρ_i = v_i/(w_i·TVL)`**. Si alguna pata baja de su umbral, el pool es
atacable. La simulación sólo hace falta para cuantificar el botín y el número de llamadas.

## 5. Cómo se cierra

1. **Mínimo de balance por token en valor** (no en wei): rechazar el join/exit no proporcional si deja
   una pata por debajo de `ε·TVL`. Es lo que v1 rechazó en `Audit.md` #210 (`min_token_balance`,
   WONT FIX) y lo que aplica `security/patches/balancer-v1-hardening.patch` (P1). Con eso, #1, #4, #7
   quedan cerrados y #2/#3/#6 necesitan un ε más agresivo.
2. **Acotar ρ, no el supply.** En v2, sustituir `_MAX_INVARIANT_RATIO` por un límite sobre el
   desequilibrio resultante.
3. **Oráculo para operaciones no proporcionales.** Es lo único que ataca la causa raíz: comparar el
   valor que entra con el que sale. Sin referencia de precio, cualquier curva AM-GM sigue siendo
   explotable en cuanto se desequilibra.

## 6. Límites

- Cálculo estático + simulación determinista; nada ejecutado contra un nodo.
- Los precios son los de la lista del escáner (`usd_per_token`). La **fracción** drenada no depende del
  precio; el importe en dólares, sí.
- El botín asume que el atacante puede adquirir la pata en polvo. En #1–#6 son tokens con mercado o
  ya en cartera; el #7 lo demuestra con un token comprable. Si la pata en polvo no se pudiera
  comprar, el ataque requeriría ser tenedor previo.
- El ROI de #2, #4 y #5 es < 1: hace falta capital (que se recupera) y el beneficio es el P&L neto.
