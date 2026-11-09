# Triaje de los pools Balancer V1 del inventario (113 filas)

**Pregunta:** ¿cuáles son vulnerables, teniendo en cuenta que se usa flash loan?

**Respuesta corta:** con las columnas que tienes **no se puede decidir** — falta justo la
variable que lo determina. De las 113 filas puedo **descartar 12 con certeza** y decirte
**en qué orden revisar las otras 101**, y sobre todo puedo corregir dos supuestos del
planteamiento que llevan a priorizar mal:

1. **El TVL no es un indicador de vulnerabilidad** (y ordenar por TVL te hace mirar los
   pools equivocados). La condición es geométrica/económica, no de tamaño.
2. **El flash loan no crea la condición explotable en un pool V1 ponderado.** Lo medí:
   la pata de compresión es **siempre** una pérdida neta (el mejor caso pierde ~$25 M
   sobre un pool de $1 M). El flash loan solo sirve cuando el pool **ya** está mal
   valorado; y en ese caso no hace falta, porque lo que se deposita es polvo.

---

## 1. Lo que sí se puede descartar hoy (12 pools, $1,33 M de TVL)

Aplicando sólo el código de `BPool.sol`, estas filas **no son explotables por
`joinswap*`**:

| Motivo | Código | Pools | TVL |
|---|---|---|---|
| `_finalized == false` | `joinswap*` exige `require(_finalized)` (`:556`, `:590`) | **8** | $1.295.044 |
| `totalSupply == 0` con `finalized == true` | `bdiv(pAo, 0)` revierte ⇒ `joinPool`/`exitPool`/`joinswap*`/`exitswapExternAmountOut` muertos | **1** | $35.530 |
| `n_tokens < 2` | `finalize()` exige `>= MIN_BOUND_TOKENS`; sin segunda reserva no hay botín | **3** | $7.349 |

```
no finalizados (8):  0xc697051d…(605k)  0x98918326…(307k)  0x25af1f2c…(270k)  0x249dda6b…(37k)
                     0x6469d9f9…(24k)   0x3029c376…(22k)   0x78c28109…(17k)   0x4d6c1725…(11k)
supply 0:            0xd7123bd9…(35k)   ← fondos no redimibles por los LPs
1 token:             0x0189c1f3…(5.8k) 0xd262e432…(1.5k)  0xa5da8cc7…(0)
```

> ⚠️ **Los 8 "NOT-FINALIZED" son una mina, no un alivio:** conservan `$1,3 M` de reservas
> y `_publicSwap=true` en 6 de ellos. El día que su controlador llame `finalize()`, el
> `totalSupply` salta a `100e18` **con las reservas que ya tienen** y quedan expuestos
> exactamente igual que los demás. No son un riesgo hoy; sí un riesgo latente que
> conviene vigilar (evento `LOG_CALL(finalize)`).

> ⚠️ **Tu columna `n_tokens` no puede ser el número de tokens enlazados**: `finalize()`
> exige `>= 2` y esas 3 filas están `finalized=True` con `n_tokens=1`. O el escáner está
> leyendo "tokens con saldo > 0", o hay un fallo de lectura. Si es lo primero, no cambia
> el veredicto (una sola reserva financiada no permite el drenaje), pero conviene
> arreglar la métrica antes de tomar decisiones con ella.

---

## 2. La variable que falta: `rho` (y por qué el TVL engaña)

El ataque es `joinswapExternAmountIn` (o `joinswapPoolAmountOut`) + `exitPool`. El BPT se
acuña según el cambio **relativo** de una reserva, no según el valor aportado. Con
`w = denorm/totalWeight` del token atacado, definiendo

```
rho = (valor de mercado de la reserva i) / (valor que le correspondería por su peso)
    = v_i / (w_i · TVL)
```

`rho = 1` ⇔ pool equilibrado (el arbitraje lo mantiene así); `rho → 0` ⇔ reserva en polvo.

**Umbral de rentabilidad exacto** (aritmética del contrato, fee 0,03 %, medido en
`screen.py` — join del 50 % de la reserva + `exitPool`):

| w del token | 0,1 | 0,2 | 0,3 | 0,4 | 0,5 | 0,6 | 0,7 | 0,8 | 0,9 |
|---|---|---|---|---|---|---|---|---|---|
| `rho*` (por debajo ⇒ rentable) | 0,827 | 0,845 | 0,862 | 0,880 | 0,899 | 0,918 | 0,938 | 0,958 | 0,979 |
| botín si `rho→0` (% del TVL) | 3,97 | 7,79 | 11,45 | 14,97 | 18,35 | 21,59 | 24,71 | 27,70 | 30,57 |

O sea: **cualquier reserva que valga menos de ~83-98 % de lo que le toca por peso ya es
explotable**, y el botín va del 4 % al 31 % del TVL según el peso. Un pool *sano* pierde
1-2 % (la concavidad del invariante protege), así que el ataque necesita
**desbalance persistente**, no tamaño.

**Consecuencias para tu inventario:**

- El botín es `3-31 % del TVL`, así que el TVL sí ordena el *botín*… pero **no** la
  probabilidad de estar en estado explotable. Un pool de $5 k con un token muerto es
  explotable; uno de $850 k perfectamente arbitrado no lo es.
- **Un token muerto/ilíquido ⇒ `rho ≈ 0` gratis**, sin que nadie tenga que comprimir nada.
  Ese es el disparador realista en V1 y es un dato de *token*, no de pool.
- **Cuidado con los 35 pools que tu escáner marca con TVL = 0** (`tag=scanmd`): "TVL 0"
  suele significar *"no pude poner precio a los tokens"*, que es precisamente la
  condición `rho ≈ 0`. **No son "sin valor", son "desconocidos"** y en el peor caso
  esconden valor real. No los descartes sin mirarlos.

---

## 3. El flash loan: no sirve para crear la condición en V1

Este es el punto que cambia la priorización. Simulé el ataque completo
comprimir → diluir → `exitPool` con la aritmética exacta, empezando desde un pool
**equilibrado** de $1 M y buscando el mejor punto de operación (`flashloan_grid.py`).
El resultado no es "caro", es **físicamente irrealizable**: para quedarte con ~99,9999 %
del BPT hay que inyectar cantidades absurdas por una de las dos patas:

| w | mejor `#` de swaps | depósito exigido | pago exigido | capital para un botín de $300 k |
|---|---|---|---|---|
| 0,3 | 29 | **9,6e14 ×** la reserva | 165 × la reserva | ~$9,6e20 |
| 0,5 | 31 | **4,6e6 ×** la reserva | 2,5e5 × la reserva | ~$4,6e12 |
| 0,8 | 8  | **1,5e6 ×** la reserva | 4,3e5 × la reserva | ~$1,5e12 |

Es decir: con un pool de $1 M, el **mejor** caso de todo el espacio de parámetros
necesita del orden de **$10¹² de capital** para un botín de $3·10⁵ (el fee flash del
0,05 % sería ya ~$7·10⁸). Verificado también con las cifras del P&L: **negativo en todas
las configuraciones** (w de 0,3 a 0,9; 8 y 18 decimales; 0 a 35 swaps; dilución hasta
×1e9). El motivo es estructural y elegante:

> Para quedarte con una fracción `f = 1 − ε` del suministro tienes que inflarlo ×`1/ε`,
> y eso obliga a depositar `D = b_T · ε^(−1/w)`. Como no puedes llegar a `f = 1`, la
> fracción `ε` **de todo lo que has metido en el pool** (compresión `C` + depósitos `D`)
> se la queda el LP original:
>
> **P&L = TVL − ε·(C + D)**
>
> Con `C ≈ 10²–10⁶ × TVL`, necesitas `ε < TVL/C ≈ 10⁻⁴…10⁻⁸`, y entonces
> `D = b_T·ε^(−1/w)` se vuelve astronómico. No hay ventana.

**Conclusión operativa:** el flash loan solo tiene sentido cuando `C ≈ 0`, es decir,
**cuando el pool ya está desbalanceado**. Y ahí el depósito es polvo: **no necesitas
flash loan en absoluto**. Por tanto:

- Si tu modelo de amenaza es *"flash loan ⇒ comprimir y drenar"*, eso es el CVE de
  **Balancer V2 stable pools** (invariante lineal: comprimir cuesta ~1:1 y se recupera,
  de ahí el "1 satoshi → 4.408,8 BPT"). En **V1 ponderado esa forma del ataque está
  muerta** por el término `ε·(C+D)`.
- El riesgo real de este inventario V1 es **estado preexistente**: token muerto,
  reserva residual, pool creado con polvo. No requiere capital ni flash loan.

---

## 4. Orden de revisión (lo único accionable con los datos que tienes)

`python3 triage.py inventory data/pools.tsv` reproduce esto. De los **101 candidatos**
($4,04 M): 48 tienen `supply ≤ 100 BPT` (un solo LP ⇒ el botín sale del creador) y
**53 tienen LPs de terceros** ($2,01 M) — empieza por estos últimos.

### 4.1 Prioridad 1 — estados anómalos (`supply` colapsada con TVL alto)

Una `supply` muy por debajo de los 100 BPT iniciales significa que **casi todos los LPs
ya salieron y el pool retiene valor**: es la firma de un pool que ya pasó por algo raro,
y donde cualquier desbalance es permanente.

| pool | TVL | supply (BPT) | n_tok |
|---|---|---|---|
| **0x1eff8af5d577060ba4ac8a29a13525bb0ee2a3d5** | $838.763 | **3,76** | 2 |
| **0x9866772a9bdb4dc9d2c5a4753e8658b8b0ca1fc3** | $690.014 | **5,68** | 2 |
| 0x9a16bddf0e89541d6abea035b706968465241e4f | $135.356 | 25,80 | 2 |
| 0xbed340a301b4f07fa7b61ab9e0767faa172f530d | $51.493 | **1,08** | 2 |
| 0x9762c600a39bda3359f50a1fb1f90945cead379d | $37.367 | 29,76 | 2 |
| 0x30cb859317e171832b064c97cc03ccb081954d1b | $5.026 | **0,037** | 2 |
| 0xe0e6b25b22173849668c85e06bc2ce1f69baff8c | $2.844 | **0,0036** | 2 |
| 0x7afe74ae3c19f070c109a38c286684256adc656c | $2.801 | **0,0097** | 2 |

### 4.2 Prioridad 2 — mayor botín potencial

| pool | TVL | n_tok | supply | nota |
|---|---|---|---|---|
| 0xe00770cbe21933e8040ce1b2d0e2c96fd7e4b63f | $858.768 | 2 | 14.095 BPT | mayor TVL de todo el inventario |
| 0x69d460e01070a7ba1bc363885bc8f4f0daa19bf5 | $488.429 | **4** | 100,0011 | 4 tokens y `supply≈100` ⇒ un solo LP con $488 k: o es un pool recién creado con mucho dinero, o el creador tiene todo |
| 0x33812e984d49ed5b44d75a008c12060e5076238c | $148.914 | 3 | 149.349 BPT | 3 tokens, LPs reales |
| 0x5a0d85166a20f9cd27be2cb293e4d10188f0c97d | $93.791 | 2 | 8.918 BPT | |
| 0xe867be952ee17d2d294f2de62b13b9f4af521e9a | $76.713 | 2 | 20.803 BPT | |
| 0x48c1d1d43f2a2267dacdd06bd6c63f3696073ed4 | $75.167 | 2 | 757.991 BPT | |
| 0xeb85b2e12320a123d447ca0da26b49e666b799db | $72.510 | 2 | 2,1e11 BPT | supply absurda (2,1e11 BPT para $72 k) ⇒ vale la pena mirar el histórico |
| 0x3c71fad2a1fc9ea1c5f7b87491daae7f1669d21a | $59.678 | 2 | 1.452 BPT | |

### 4.3 Prioridad 3 — mucha superficie de "token muerto"

Pools multi-token: cada token extra es una oportunidad de que uno sea ilíquido o haya
muerto. `0x1373e57f764a7944bdd7a4bd5ca3007d496934da` (**8 tokens**, $32.749) es el caso
más extremo del inventario; luego `0x5b2dc8c0…` (7 tokens), y varios de 5
(`0xf1f3d252…`, `0x0e3e2781…`, `0xe8620e0f…`, `0xa1ec308f…`, `0x55353cba…`, `0x3b260cf9…`).

### 4.4 Datos que hay que añadir (una pasada, ~10 min)

Por cada pool candidato, y por cada token enlazado (`getCurrentTokens()`):

```
balance_raw  = pool.getBalance(token)                 // BPool.getBalance
denorm       = pool.getDenormalizedWeight(token)      // 1e18
totalWeight  = pool.getTotalDenormalizedWeight()
decimals     = IERC20(token).decimals()
price_usd    = <tu oráculo>
```

Con eso:

```bash
python3 triage.py screen data/tokens.csv     # veredicto VULNERABLE / ok por pool
```

`triage.py screen` calcula `rho` por token, lo compara con `rho*(w)` y estima el botín.
**Ese** es el veredicto; lo de arriba es solo el orden de la cola.

Atajo para el caso más probable: si tu escáner **no consigue poner precio a un token**
(o lo pone a ~0), ese pool es sospechoso automáticamente: `rho ≈ 0` y el botín es todo
el resto del TVL. Empieza por ahí antes de pedir balances uno a uno.

---

## 5. Resumen ejecutivo

| | |
|---|---|
| Descartados con certeza | **12 pools** ($1,33 M) — 8 sin finalizar, 1 con supply 0, 3 de un solo token |
| Riesgo latente | los 8 sin finalizar ($1,3 M): al finalizarse heredan el problema |
| Candidatos | **101** ($4,04 M), de los cuales **53** con LPs de terceros ($2,01 M) |
| Veredicto por pool | **requiere `rho`** (balance + decimals + denorm + precio por token) — no está en tu tabla |
| Probabilidad de que el flash loan sea el vector | **baja en V1 ponderado** (la compresión es pérdida neta: `P&L = TVL − ε(C+D)`); alta en V2 stable |
| Botín si hay pool vulnerable | 4-31 % de su TVL (según el peso del token en polvo) |
| Lo que NO debes hacer | ordenar por TVL y asumir que "flash loan" crea el estado |

**Si sólo puedes mirar 5 pools:** `0x1eff8af5…`, `0x9866772a…` (supply colapsada a
3,7/5,7 BPT con $838 k/$690 k dentro), `0xe00770cb…` (mayor TVL), `0x69d460e0…` (4 tokens,
$488 k) y `0x1373e57f…` (8 tokens). En los cinco, el primer chequeo es el mismo: **¿hay
algún token cuyo valor en el pool sea menos del ~85 % de lo que le toca por su peso?**
