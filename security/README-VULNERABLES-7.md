# Candidatos vulnerables (los antiguos «7»)

> **Este documento se llamaba «los 7 pools vulnerables».** Tras la revisión crítica
> (`security/REVISION-ANEXO-ES.md`) **cuatro de los siete eran falsos positivos** y se han retirado: tres
> por estar valorados con **precio de marca (spot) en vez de precio realizable**, y uno por valorar a
> libro un LP que no tiene salida. Quedan **tres candidatos**, ninguno verificado en fork.
> Los descartados, con la prueba de por qué caen, están en **§0bis** (no se borran: se reclasifican).

De los tres, **$30.676 de botín** con **$1.765 de capital** sobre **$40.589 de TVL**, todos con aritmética
exacta (`verify_triage.py`: P&L > $100).

Reproducir: `python3 security/dossier7.py` (el script calcula los **siete originales**, incluidos los
cuatro descartados; datos en `security/data/dossier7.csv`).

---

## 0. Resumen

| # | pool | ver. | tipo | tokens (pesos) | fee | TVL | pata en polvo (ρ) | capital | botín | ROI | causa | estado |
|---|---|---|---|---:|---:|---|---:|---:|---:|---:|---|---|
| 1 | `0x1373e57f` | v1 | BPool 8 tokens | `0x0ba45a8b` + 7 patas muertas (12,5 % c/u) | 1,00 % | $29.298 | USDC (ρ≈0) | **$9** | **$29.026** | 3.225× | patas muertas | **pendiente**: salida de `0x0ba45a8b` |
| 2 | `0xc3516482` | v1 | BPool | WETH / REPv2 (20/80) | 0,30 % | $10.056 | WETH (ρ=0,313) | $1.497 | $993 | 0,66× | peso extremo | **condicional**: probar salida por REPv2 |
| 3 | `0xcf8dfdb7` | v2 | WeightedPool v4 | st-yETH / GOLD (40/60) | 1,00 % | $1.235 | GOLD (ρ=0,160) | $259 | $657 | 2,54× | desequilibrio puro | **condicional**: verificar ambos precios |
| | | | | | | **$40.589** | | **$1.765** | **$30.676** | | | |

**«Estado» no es una formalidad: es lo que falta por medir.** Ninguno de los tres está confirmado
ejecutando. El #1 es el que más cambia según lo que se mida (puede pasar de $29.026 a ~$0), y el #3 es
el más barato de verificar (token comprable, pool de $1,2k).

«ROI» = botín / capital. En el #2 es menor que 1: hace falta poner más de lo que se saca, pero el
capital **se recupera** (entra y vuelve a salir); lo que cuenta es el P&L neto.

---

## 0bis. Descartados: cuatro falsos positivos

| # orig. | pool | por qué se cae | prueba |
|---|---|---|---|
| 2 | `0xf0f8b1ce` | PAR/MIMO 50/50. El ρ=0,285 es **artefacto de marca**: MIMO no vale su spot | con MIMO a **spot/6**, ρ_PAR = **0,999** |
| 3 | `0x5b1c06c4` | PAR/MIMO 75/25 (v2), mismo caso | con MIMO a **spot/6**, ρ_PAR = **1,000** |
| 6 | `0xa5533a44` | PAR/MIMO 20/80 (v2), mismo caso | con MIMO a **spot/6**, ρ_PAR = **1,000** |
| 4 | `0x30cb8593` | UNI-V2/WETH. Se valoraba el LP de Uni-V2 **a libro** | el LP es black-hole: `burn` revierte; techo real = $83 de WETH |

### El caso de los tres PAR/MIMO

El pool valora PAR a **$6,695** cuando el mercado dice **$1,114**: un **6,01×**. Eso no es un bug del
pool. Es la misma cifra que el *haircut* de liquidación de MIMO que se midió en fork (MIMO se realiza a
~1/6 de su spot). Y el factor que hace desaparecer el desequilibrio es exactamente ése:

```
MIMO a spot/1:  rho_PAR = 0,285   rho_MIMO = 1,715
MIMO a spot/2:  rho_PAR = 0,500   rho_MIMO = 1,500
MIMO a spot/4:  rho_PAR = 0,799   rho_MIMO = 1,201
MIMO a spot/6:  rho_PAR = 0,999   rho_MIMO = 1,001   <-- el haircut medido
```

No es casualidad: **ρ = 1 es, por definición, «el precio marginal del pool coincide con la marca».** El
pool no estaba desequilibrado; estaba diciendo la verdad sobre MIMO y la marca era la que mentía. Un
pool que cotiza al precio ejecutable **no tiene arbitraje**, por muy «desequilibrado» que lo vea un
scanner que usa spot.

### El caso `0x30cb8593`

El botín de $2.720 venía de valorar 3.799,90 $ de UNI-V2 **a valor contable** y suponer que se podía
vender. El `burn` del LP revierte en fork: no hay salida. El pool entero tiene **$83,55 de WETH** y eso
es todo lo que se puede sacar, con un fee del 3,75 %. El «desequilibrio puro» era real; la **cobrabilidad
no**.

### Qué queda de la «familia PAR/MIMO»

Nada. Los tres pools del par eran el mismo artefacto con los pesos barajados (50/50, 75/25, 20/80) y el
único token del par que se podía vender era PAR, que es justo la pata por la que se entra. La «causa»
*par desarbitrado* desaparece del documento: no era una causa, era una marca mala.

---

## 1. El bug: qué tienen en común los tres

### 1.1 La operación que se explota

Los tres exponen la misma ruta: **entrar con un solo token pidiendo una cantidad exacta de BPT** y
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

### 1.3 La métrica: ρ, y la trampa de la marca

```
ρ_i = v_i / (w_i · TVL)        v_i = valor de la pata i, w_i = su peso
```

- `ρ_i = 1` para todas las patas ⇔ pool en equilibrio ⇔ ataque con P&L 0 (empate AM-GM, verificado:
  da **−$1** exacto por fees).
- `ρ_i < 1` ⇒ la pata `i` está por debajo de su peso en valor ⇒ **es la pata por la que hay que
  entrar**. Cuanto menor, más caro le sale al pool reponerla y más barato te vende el BPT.
- `ρ_i > 1` ⇒ es la pata por la que hay que **salir**.

**Pero ρ sólo vale lo que valga `v_i`.** Si se usan precios de marca, ρ mide la desviación del pool
respecto al spot — y eso **sólo es dinero si puedes ejecutar al spot**. Ése fue el error que metió los
cuatro falsos positivos de §0bis y el que hace que la tabla de §0 lleve columna de estado. El criterio
correcto está en §4.

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

**No hay «doble cap» en v1**: `exitswapPoolAmountIn` sólo aplica `MAX_OUT_RATIO` sobre el balance
(`BPool.sol:642`, `BConst.sol:40`). La condición «BPT/supply ≤ 1/3» **no existe en v1** — es de v2
(`_MAX_INVARIANT_RATIO`), y allí actúa sobre el *supply*, no sobre el desequilibrio. En v2, por tanto,
no hay umbral ρ\*: **todo pool con ρ < 1 es rentable**, y el corte práctico lo pone el gas.

---

## 2. Los tres, uno por uno

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
65,24 % del supply se quema en `exitswapPoolAmountIn` contra la pata viva y se cobran **$29.035,43**.
P&L **+$29.026**.

**La salida tiene que ser mono, no pro-rata.** Con `w = 0,125` el exponente es `1/w = 8`, y
`1 − (1 − 0,6524)^8 = 0,99979`: quemando el 65 % del supply te llevas **el 99,98 % de la pata**. Eso es
lo que hace el ataque tan desproporcionado. `exitPool` daría el 65 % de cada pata y además es frágil:
revierte con `ERR_MATH_APPROX` en cuanto cualquier pata da cero (`BPool.sol:413`).

**Por qué el contrato lo permite.** Acuñar el 65 % del supply cuesta `b·(1,65^8 − 1) = b·54,3`, donde
`b` es el balance de la pata de entrada: **$0,0018 de USDC**. El pool te cobra por «reponer el USDC que
falta», no por el `0x0ba45a8b` que te llevas. `MIN_BALANCE = 1e6` wei no protege: el balance no es
cero, es pequeño **en valor**.

> ⚠️ **Lo que falta por verificar (y es todo).** El 100 % del TVL es la pata `0x0ba45a8b` a $55,134 el
> token. Si ese token no tiene salida —o su precio realizable es una fracción de eso— el botín no es
> $29.026, es lo que se saque por 531 unidades. El **mecanismo** no depende del precio (la fracción
> drenada es exacta: 65,24 % del supply → 99,98 % de la pata); el **importe**, sí. Antes de contar este
> pool, mirar los pares de `0x0ba45a8b`, su profundidad y el slippage de venta de 531 tokens en una
> sola operación. Es el mismo test que tumbó los tres PAR/MIMO.

---

### 2.2 `0xc351648240e9fc9213e8b6016e566f95c5fa7909` — peso extremo 20/80

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

> ⚠️ **Lo que falta por verificar.** En el anexo de la auditoría previa este pool aparece como «control
> negativo» con −0,0017 WETH. Ese test **no vale**: entra y sale por la **misma** pata (WETH), y eso es
> un wash por construcción — `2 × fee × 0,28 WETH = 0,00168`, exactamente lo medido. La salida rentable
> es **REPv2** (ρ = 1,172) o **pro-rata**, que aquí sí funciona porque ninguna pata está muerta. Hay que
> probar esa dirección antes de dar el pool por bueno o por muerto.

---

### 2.3 `0xcf8dfdb73e7434b05903b5599fb96174555f4353` — el mejor ROI y sin inventario

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
los tres.

**Por qué es el único que no depende de una marca dudosa.** **GOLD se puede comprar** ($1,0037, con
precio de mercado) y st-yETH es un derivado de ETH con par profundo: las dos patas tienen salida, que
es justo lo que faltaba en los descartados. El atacante no necesita tener el token de antemano: compra
$259 de GOLD, entra, sale con st-yETH y vende.

> ⚠️ **Lo que falta por verificar.** Los dos precios. Si st-yETH vale como ETH (~$2.123) en vez de
> $55,42, la pata pasa de $1.117 a ~$42.780 y ρ_GOLD cae a **0,005**: el pool sería **mucho más**
> vulnerable y el botín mayor. Si el que está mal es GOLD, el pool se equilibra y el ataque muere. Es
> un pool de $1,2k: se comprueba en un fork en diez minutos, y es el orden correcto de trabajo.

---

## 3. Tres causas, no tres bugs

Los tres son el **mismo bug** en tres estados distintos del pool:

| causa | pools | qué lo produce |
|---|---|---|
| **Patas muertas** | #1 | El pool sobrevivió a sus tokens: siete patas a ~0 y una que concentra todo. ρ ≈ 0 ⇒ entrar cuesta céntimos. |
| **Peso extremo** | #2 | Con w = 0,2 basta un desequilibrio moderado para que el BPT salga barato. |
| **Desequilibrio puro** | #3 | Un token se hundió frente al otro y el pool quedó con una pata al 9,6 % de su peso en valor. |

Las tres son la misma condición aritmética: **`min_i ρ_i < ρ*`**, con ρ medido a **precio realizable**.
En v1, `ρ*` ∈ [0,845; 0,979] según el peso (lo imponía `MAX_IN_RATIO`). En v2, `ρ* = 1`.

La cuarta causa del documento anterior —*par desarbitrado* (#2, #3 y #6 de los antiguos)— **no era una
causa**: era MIMO marcado a spot (§0bis).

## 4. Cómo se detecta

```bash
python3 security/dossier7.py      # rho por pata + traza del ataque, pool a pool (los 7 originales)
python3 security/verify_triage.py # veredicto de las 226 filas del escáner
```

El criterio **no** es `ρ` con el precio del escáner. Es:

1. **marca realizable**: para cada pata, el precio al que se puede vender *el importe que habría que
   vender* contra su mejor par (curva de venta, no spot);
2. recalcular `ρ_i = v_i/(w_i·TVL)` con esas marcas;
3. exigir que el precio marginal del pool difiera del realizable **después** de slippage.

Un pool con ρ = 0,2 medido a spot puede estar perfectamente equilibrado a precio realizable — y
entonces no hay nada que cobrar, por muy «desequilibrado» que parezca. Es el filtro que falta en el
escáner y el que hay que meter antes de volver a listar candidatos.

La simulación sólo hace falta para cuantificar el botín y el número de llamadas.

## 5. Cómo se cierra

1. **Mínimo de balance por token en valor** (no en wei): rechazar el join/exit no proporcional si deja
   una pata por debajo de `ε·TVL`. Es lo que v1 rechazó en `Audit.md` #210 (`min_token_balance`,
   WONT FIX) y lo que aplica `security/patches/balancer-v1-hardening.patch` (P1). Con eso, #1 y #3
   quedan cerrados y #2 necesita un ε más agresivo.
2. **Acotar ρ, no el supply.** En v2, sustituir `_MAX_INVARIANT_RATIO` por un límite sobre el
   desequilibrio resultante.
3. **Oráculo para operaciones no proporcionales.** Es lo único que ataca la causa raíz: comparar el
   valor que entra con el que sale. Sin referencia de precio, cualquier curva AM-GM sigue siendo
   explotable en cuanto se desequilibra.

## 6. Límites

- Cálculo estático + simulación determinista; **nada de esto está confirmado ejecutando contra un nodo**.
- Los precios son los de la lista del escáner (`usd_per_token`). **La fracción drenada no depende del
  precio; el importe en dólares sí** — y es exactamente donde fallaron los cuatro descartados. Tratar
  la columna de botín como **cota superior a precio de marca**, no como botín.
- El botín asume que el atacante puede adquirir la pata en polvo **y vender la pata premio**. Lo
  segundo es lo que no está verificado en #1 y lo que hace que #3 sea el más sólido de los tres.
- El ROI de #2 es < 1: hace falta capital (que se recupera) y el beneficio es el P&L neto.
- El nombre del fichero («…-7») es histórico; se mantiene para no romper los enlaces del índice.
