# Auditoría de seguridad — `balancer-core` (Balancer V1)

**Repositorio:** `nightbox33-cloud/balancer-core` @ `f4ed5d6` (master)
**Fecha:** 2026-11-09
**Alcance:** `contracts/BPool.sol`, `BMath.sol`, `BNum.sol`, `BConst.sol`, `BToken.sol`, `BFactory.sol`, `BColor.sol`
**Método:** revisión manual línea por línea + **simulador exacto de la aritmética entera** de `BNum`/`BMath` (réplica de `bmul`, `bdiv`, `bpowi`, `bpow`, `bpowApprox` con redondeo *half-up* y precisión `1e8`) para reproducir numéricamente cada afirmación. Artefactos ejecutables en `security/`.

---

## 0. Resumen ejecutivo

**Tu premisa es correcta, pero está descrita de forma incompleta en un punto que cambia la remediación:**

1. El fallo **existe** en este código y lo he reproducido: `joinswapPoolAmountOut` (`BPool.sol:584-618`) permite acuñar una fracción arbitraria del suministro pagando cantidades **de polvo**, cuando la reserva del token de entrada está en polvo. Reproducción: con una reserva de **3 unidades raw** (3e-8 WBTC) se acuñan **62,4 BPT de 100** en **una sola llamada**; con 1 wei se acuñan **38,3 %** del suministro.

2. **La causa raíz NO es "truncamiento hacia abajo"**. El redondeo (`bdiv`/`bmul` con `+B/2`) es casi siempre favorable al *pool*, y la fuga por redondeo en estado normal está acotada a ~`bO/(w·1e18)` por operación (≈2e-15 ETH en un pool de 1 ETH), es decir **no explotable a escala normal**. La causa raíz real es otra: **el BPT se acuña según el cambio *relativo* de una única reserva, no según el *valor* aportado, y no existe ninguna cota que ligue lo acuñado al valor, ni un suelo que impida que una reserva llegue a polvo**. A reserva polvo, "+50 % de la reserva" es a la vez "~0 de valor" y "el 38 % del suministro".
   - Consecuencia práctica: **"menos de 18 decimales" no es la condición real**. Lo verifiqué con un token de 18 decimales: idéntico resultado (§3.3). Los decimales solo abaratan *llegar* al polvo. La condición real es **"existe una reserva en polvo"**, y el polvo es alcanzable en *cualquier* pool (no hay invariante; el `MIN_BALANCE` de `BConst.sol:34` = `1e-12` solo se comprueba en `rebind`, y ToR lo marcó **FAILED / WONT FIX**, issue #210).

3. **Sí hay un bug que empeora esto y es, en la práctica, el más grave de la lista: la misma primitiva existe en `joinswapExternAmountIn` (`BPool.sol:549-582`)**, función que *no* se menciona en el reporte público y que **no queda cubierta si se parchea solo `joinswapPoolAmountOut`**. Verificado: depositar **1 wei** de la reserva polvorienta acuña el **38,3 %** del suministro; 28 llamadas desde 2 wei llevan al atacante al **99,99 %** del BPT depositando 0,002 WBTC. Cualquier mitigación centrada en `joinswapPoolAmountOut` es **bypasseable en una línea de código**.

4. **No existe botón de emergencia para la ruta vulnerable.** `_publicSwap` solo se comprueba en `swapExactAmountIn/Out` (`:438`, `:500`) — **no** en `joinswapExternAmountIn`, `joinswapPoolAmountOut`, `joinPool` ni `exitPool`. Y `setPublicSwap` (`:214`) exige `! _finalized`, por lo que **tras `finalize()` el controlador no puede pausar nada**. En un incidente, esta versión no se puede congelar.

5. **Matiz económico importante (verificado, §3.4):** en un pool V1 *balanceado a precios de mercado*, "comprimir la reserva hasta polvo por mi cuenta" es **económicamente autodestructivo**: el slippage del invariante ponderado hace que el coste de comprimir 1:10⁴ sea ~6.300× la reserva de entrada, mientras el botín es ~0,5·TVL (tabla §3.4; ROI ≈ 0,01 %). Esto explica por qué el CVE de nov-2025 se materializó en *stable pools* V2 (invariante lineal ⇒ comprimir cuesta ~1:1 y es recuperable). **En V1 la exposición realista es: (a) pools que YA tienen una reserva en polvo** (token muerto, long-tail drenado, o pool creado así), **(b) el vector "honeypot del creador"** (§3.5), que no requiere capital ni compresión, y **(c) los DoS de §4.3/§4.4**, que sí son gratuitos.

**Tabla de hallazgos**

| ID | Severidad | Título | Estado |
|----|-----------|--------|--------|
| **C-1** | 🔴 Crítico | `joinswapPoolAmountOut`: acuñación de BPT por polvo | confirmado, reproducido |
| **C-2** | 🔴 Crítico | `joinswapExternAmountIn`: **misma primitiva**, bypassea el parche de C-1 | confirmado, reproducido |
| **H-1** | 🟠 Alto | `MIN_BALANCE` no es invariante: las reservas llegan a 0/polvo (enabler) | confirmado (#210 WONT FIX) |
| **H-2** | 🟠 Alto | `gulp()` sin permisos = primitivo "set balance"; + `_pullUnderlying` no verifica lo recibido ⇒ desincronización registro/real | confirmado |
| **H-3** | 🟠 Alto | Sin pausa de emergencia; `setPublicSwap` bloqueado tras `finalize` | confirmado (diseño) |
| **M-1** | 🟡 Medio | DoS de `exitPool`/`joinPool` por polvo (`require(x != 0)`), griefing ≈ coste = sólo comisiones | confirmado |
| **M-2** | 🟡 Medio | `bpow` con base→`MAX_BPOW_BASE` ⇒ ~136.000 iteraciones (~100 M gas) ⇒ OOG | confirmado |
| **M-3** | 🟡 Medio | Redondeo *half-up* sistemático en `bmul`/`bdiv` (a favor del usuario en varias rutas) | confirmado, fuga acotada |
| **L-1…L-8** | 🔵 Bajo/Info | `setController(0)`, `bind` del propio BPT/0x0, transfer a 0x0, `bind` sin `_lock_`, sin deadline, USDT-style, `LOG_CALL` con calldata, decimales no normalizados | varios #WONT FIX |
| — | ✅ | Reentrancy, control de acceso, overflow, `transferFrom` | **sin hallazgos** (§6) |

---

## 1. Cómo se ha verificado

Todo lo cuantitativo de este informe proviene de un **modelo entero exacto** de los contratos, no de aritmética de coma flotante:

- `security/bmath_sim.py` — réplica de `BNum` (`btoi`, `bfloor`, `badd`, `bsub`, `badd` con chequeo de overflow uint256, `bmul` con `+BONE/2`, `bdiv` con `+b/2`, `bpowi`, `bpow` con `MIN/MAX_BPOW_BASE`, `bpowApprox` con `BPOW_PRECISION = 1e8`) y de `BMath`, **más** un modelo de `BPool` que reproduce todos los `require` de las rutas de interés (incluidos `MAX_IN_RATIO`, `MAX_OUT_RATIO`, base de `bpow` < 2, `poolAmountIn/Out != 0`).
- `security/experiments.py` — E1…E7.
- `security/rounding_search.py` — búsqueda de ciclos rentables (join/exit, swap ida-vuelta, join-swap/exit-swap).
- `security/economics.py` — economía del ataque completo sobre pools balanceados.

Los `.js` de `test/` **no se han ejecutado** (no hay `node_modules` y el registro npm no es accesible desde este entorno); por eso el PoC es el simulador exacto, no un test de Truffle. Los números son reproducibles con `python3 security/experiments.py`.

---

## 2. C-1 — `joinswapPoolAmountOut` (la vulnerabilidad reportada)

```solidity
// BPool.sol:584
function joinswapPoolAmountOut(address tokenIn, uint poolAmountOut, uint maxAmountIn)
    external _logs_ _lock_ returns (uint tokenAmountIn)
{
    require(_finalized, "ERR_NOT_FINALIZED");
    require(_records[tokenIn].bound, "ERR_NOT_BOUND");

    Record storage inRecord = _records[tokenIn];

    tokenAmountIn = calcSingleInGivenPoolOut(
                        inRecord.balance, inRecord.denorm,
                        _totalSupply, _totalWeight,
                        poolAmountOut, _swapFee);

    require(tokenAmountIn != 0, "ERR_MATH_APPROX");          // :604  ← única cota inferior
    require(tokenAmountIn <= maxAmountIn, "ERR_LIMIT_IN");   // :605  ← la fija el atacante
    require(tokenAmountIn <= bmul(_records[tokenIn].balance, MAX_IN_RATIO), "ERR_MAX_IN_RATIO"); // :607
    ...
}
```

### 2.1 La fórmula y por qué el polvo lo rompe

`calcSingleInGivenPoolOut` (`BMath.sol:156-182`) implementa

```
tokenAmountIn ≈ bI · [ (1 + pAo/pS)^(1/w) − 1 ] / (1 − (1−w)·sF)
```

donde `bI` es la reserva actual del token de entrada y `w` su peso normalizado. **El coste es lineal en `bI`.** No hay ninguna referencia a cuánto vale `bI`, ni al valor del pool, ni al valor de `pAo`.

Cuando `bI → 0`, el coste de acuñar una fracción arbitraria del suministro `→ 0`. La cota `MAX_IN_RATIO` (`:607`) **no lo evita**, sólo limita la llamada a `tokenAmountIn ≤ 0,5·bI`: como el coste también es proporcional a `bI`, la cota es invariante de escala y siempre deja pasar la operación. La única cota real del `pAo` por llamada es:

```
pAo_max = (1,5^w − 1) · pS          (porque tokenAmountIn ≤ 0,5·bI  ⇒  (1+pAo/pS)^(1/w) ≤ 1,5)
```

que para `w = 0,8` es el **38,3 % del suministro por llamada**, y es **repetible/compuesto**.

El invariante `bpow` (base < `MAX_BPOW_BASE = 2·BONE − 1`) actúa como segunda cota (impide `pAo ≥ pS` en una llamada) pero no cambia nada: el ataque se compone.

### 2.2 Reproducción numérica (E1)

Pool 80/20 WBTC(8 dec)/WETH, suministro 100 BPT, `swapFee` 0,03 %, reserva WBTC comprimida:

| reserva WBTC (raw) | pago exigido | BPT acuñado | % del suministro |
|---|---|---|---|
| 3 (3e-8 WBTC) | **2 raw (2e-8 WBTC)** | **62,40** | **62,40 %** |
| 10 | 5 raw | 42,00 | 41,99 % |
| 1.000 | 500 raw | 38,44 | 38,35 % |
| 1.000.000 | 500.000 raw | 38,31 | 38,31 % |

Obsérvese que la amplificación **no depende de los decimales**: con `w = 0,8` y `bI = 1e6` (que es exactamente `MIN_BALANCE`, el mínimo permitido en `rebind`) se sigue acuñando el **38,3 % del suministro por 0,005 BTC**.

Con `w = 0,5` el máximo por llamada es 22,5 %; con `w = 0,2`, 8,4 %; con `w = 0,1`, 4,1 %. Como el coste crece geométricamente (`bI ×1,5` por llamada), **el total depositado hasta quedarse con ~100 % del BPT es `≈ bI_inicial · 2^(1/w)`** — constante e irrisoria si `bI_inicial` es polvo. Ejemplo verificado (E2): desde una reserva de **2 wei**, **28 llamadas**, **0,00207 WBTC depositados en total** ⇒ **99,9903 % del suministro**, con derecho a retirar la totalidad de las 3.000 WETH del pool.

### 2.3 Sobre "1 satoshi → 4.408,8 BPT"

Compatible: 4.408,8 BPT con `w=0,8` exige `pAo/pS = 0,624` en una llamada, es decir un suministro previo de ~7.065 BPT y un pago de `pAo/pS`-relativo a la reserva polvorienta (≈ 0,6 satoshis). Mi reproducción da la misma forma funcional (§2.2).

---

## 3. C-2 — El mismo fallo en `joinswapExternAmountIn` (**lo que empeora el bug**)

```solidity
// BPool.sol:549
function joinswapExternAmountIn(address tokenIn, uint tokenAmountIn, uint minPoolAmountOut)
    external _logs_ _lock_ returns (uint poolAmountOut)
{
    require(_finalized, "ERR_NOT_FINALIZED");
    require(_records[tokenIn].bound, "ERR_NOT_BOUND");
    require(tokenAmountIn <= bmul(_records[tokenIn].balance, MAX_IN_RATIO), "ERR_MAX_IN_RATIO");

    poolAmountOut = calcPoolOutGivenSingleIn(inRecord.balance, inRecord.denorm,
                                             _totalSupply, _totalWeight,
                                             tokenAmountIn, _swapFee);
    require(poolAmountOut >= minPoolAmountOut, "ERR_LIMIT_OUT");   // ← sólo cota del usuario
    ...
}
```

`calcPoolOutGivenSingleIn` (`BMath.sol:117-144`) es **el espejo exacto**:

```
poolAmountOut ≈ pS · [ (1 + aI'/bI)^w − 1 ]
```

idéntica dependencia lineal en `bI` y la misma ausencia de referencia de valor. Verificado (E2):

| `w` del token polvoriento | depósito | BPT acuñado | % del suministro previo |
|---|---|---|---|
| 0,80 | **1 wei** | 38,3162 | **38,32 %** |
| 0,50 | 1 wei | 22,4745 | 22,47 % |
| 0,20 | 1 wei | 8,4472 | 8,45 % |
| 0,10 | 1 wei | 4,1380 | 4,14 % |

**Por qué esto es peor que C-1:**

1. **No aparece en el reporte público** ⇒ el threat model publicado es incompleto.
2. **Es más fácil de ejecutar**: no hay que resolver `pAo` (que está acotado por la base de `bpow < 2` y puede provocar OOG, §M-2) ni preocuparse por `ERR_MATH_APPROX`; basta con mandar `1 wei`.
3. **Bypassea el parche obvio.** Un `require` añadido en `joinswapPoolAmountOut` no toca esta función. Cualquier parche que no cubra **ambas** rutas es cosmético.
4. **También bypassa el "fix de redondeo"**: aunque se redondeara el input hacia arriba, `bmul(tokenInRatio, bI)` con `bI = 1` sigue dando `bI` y `tokenAmountIn = 0`... pero con `bI = 2` da 1 y el ataque sigue. El redondeo no es la raíz.

> **Conclusión de mitigación:** la superficie vulnerable es **toda la familia de join unilateral** (`joinPool` es proporcional y está a salvo; `joinswapExternAmountIn` y `joinswapPoolAmountOut` no). El parche debe ser un invariante, no un `require` puntual.

### 3.4 ¿Es rentable "fabricar" el polvo uno mismo? (verificado, y es un matiz importante)

Simulé el ataque completo (comprimir → diluir → `exitPool`) con la aritmética exacta sobre pools **balanceados a precio de mercado**, TVL 1 M USD (`security/economics.py`):

| Pool | compresión | capital necesario | botín | ROI/bloque |
|---|---|---|---|---|
| 50/50 WBTC(8d)/WETH | 1:10⁴ | **$6.297 M** | $499.955 | 0,01 % |
| 20/80 WBTC(8d)/WETH | 1:10⁸ | **$2,9e17** | $799.923 | ~0 % |
| 50/50 WETH(18d)/USDC | 1:10⁴ | **$6.297 M** | $499.955 | 0,01 % |
| 50/50 USDC(6d)/WETH | 1:10⁴ | **$6.297 M** | $499.955 | 0,01 % |

**El ROI es invariante respecto al tamaño del pool** (capital y botín escalan ambos linealmente con el TVL), así que no se arregla apuntando a pools más grandes. El motivo: en un pool ponderado el precio marginal del token se dispara al agotarse (`coste ∝ r^α`, `α = ln(1+c)/ln 1,5`), y **ese sobrecoste no se recupera** — sólo se recupera la fracción del pool que uno acaba poseyendo.

**Interpretación honesta:** en *este* código (ponderado V1) el vector "comprimo yo mismo desde un pool sano" **no es rentable**; en un *stable pool* V2 (invariante lineal, comprimir cuesta ~1:1 y es recuperable) sí lo es, que es exactamente donde se materializó el CVE de nov-2025 y de donde salen las cifras de "1 satoshi → 4.408,8 BPT". Esto **no reduce** la severidad de C-1/C-2, porque:

- **(a) Pools que ya están en polvo**: token muerto/long-tail drenado por arbitraje, o reserva residual. Ahí el coste de compresión es **cero** y el ataque es gratis. Es el caso realista en V1 (2020-2021 hubo muchísimos pools con tokens long-tail).
- **(b) Honeypot del creador** (§3.5): capital cero, sin compresión.
- **(c) Los DoS asociados** (§M-1, §M-2) no necesitan ninguna condición económica.

### 3.5 Vector "honeypot del creador" (capital cero, sin compresión)

`BFactory.newBPool()` es **permissionless** y `rebind` sólo exige `balance ≥ MIN_BALANCE = 1e6 raw` (`:274`). Para un token de **18 decimales**, `1e6 raw = 1e-12` tokens ⇒ **un pool puede finalizarse legítimamente con una reserva literalmente de polvo**. El creador:

1. `bind(tokenX_18dec, 1e6, 80 %)` + `bind(tokenReal_18dec, 200.000e18, 20 %)` y `finalize()` (recibe 100 BPT).
2. Un LP hace `joinPool` (proporcional, "justo") depositando valor real.
3. El creador ejecuta `joinswapExternAmountIn(tokenX, 1 wei)` unas decenas de veces ⇒ ~100 % del BPT.
4. `exitPool` ⇒ se lleva el valor real del LP.

El paso 2 requiere que un LP entre en un pool cuya composición visible es absurda (80 % de un token con 1e-12 de reserva), así que es un vector de **phishing/honeypot**, no un ataque silencioso. Pero es gratis y no necesita flash loans: merece seguimiento porque el `MIN_BALANCE` de `1e-12` no protege nada.

---

## 4. Bugs adicionales (los que empeoran C-1/C-2 o son independientes)

### H-1 🟠 `MIN_BALANCE` no es un invariante — el *enabler* estructural

`BConst.sol:34`: `MIN_BALANCE = BONE / 1e12` (= `1e-12` tokens). Se comprueba **sólo** en `rebind` (`BPool.sol:274`), es decir **sólo en la génesis**. Después:

- `swapExactAmountOut` / `exitswapExternAmountOut` sólo exigen `aO ≤ bO·MAX_OUT_RATIO` (`:505`, `:666`) ⇒ **cualquiera puede llevar una reserva a 1-2 wei en pasos geométricos**, a precio "justo" (o mejor, si el pool está desarbitrado).
- `gulp` (§H-2) permite fijarla a **0**.

La propiedad de ToB `min_token_balance` está en `Audit.md` como **FAILED — WONT FIX (issue #210)**. Es exactamente la condición habilitante de C-1/C-2 y sigue abierta en este commit. **Es el hallazgo que hay que cerrar para arreglar de verdad C-1/C-2.**

### H-2 🟠 `gulp()` — primitivo "set balance" sin permisos, y `_pullUnderlying` no verifica lo recibido

```solidity
// BPool.sol:334
function gulp(address token) external _logs_ _lock_ {
    require(_records[token].bound, "ERR_NOT_BOUND");
    _records[token].balance = IERC20(token).balanceOf(address(this));   // ← sobreescribe sin condiciones
}
```

Dos problemas encadenados:

1. `gulp` es **público** y **sobrescribe** el registro con el saldo real, **hacia arriba o hacia abajo**. El registro es la única fuente de verdad para toda la matemática.
2. `_pullUnderlying` (`:701-706`) sólo hace `transferFrom` y comprueba el `bool`; **nunca verifica que el pool recibió `amount`**. Con cualquier token fee-on-transfer, deflacionario o con rebase negativo, `registro > real` de forma permanente. Un tercero llama `gulp` y **hunde el registro**, incluso a 0.

Verificado (E6) con `record = 0`:

```
swapExactAmountIn      REVERT ERR_MAX_IN_RATIO   (bmul(0, 0.5e18) = 0)
joinPool               REVERT ERR_MATH_APPROX    (tokenAmountIn = 0)
exitPool               REVERT ERR_MATH_APPROX    (tokenAmountOut = 0)  ← todos los LPs
exitswapPoolAmountIn   OK                        (única vía de salida que queda)
```

Es decir: **una reserva a 0 deja `joinPool` y `exitPool` muertos para siempre** (no hay forma de repararlo: `rebind` exige `! _finalized`). Los fondos siguen siendo recuperables token a token vía `exitswapPoolAmountIn`/`exitswapExternAmountOut` a base de comisiones, pero el pool queda inutilizable. La propiedad de ToB `pool_record_balance` aparece como **PASSED** en `Audit.md`; mi lectura es que esa propiedad no modela `gulp` ni tokens no estándar.

### H-3 🟠 Sin pausa de emergencia; el interruptor existente se autobloquea

- `_publicSwap` sólo se consulta en `swapExactAmountIn` (`:438`) y `swapExactAmountOut` (`:500`). **`joinPool`, `exitPool`, `joinswapExternAmountIn`, `joinswapPoolAmountOut`, `exitswap*` NO lo consultan.**
- `setPublicSwap` (`:214-222`) exige `require(! _finalized)`. `finalize()` (`:233-234`) pone `_finalized = true` y `_publicSwap = true`.

⇒ **Tras `finalize()` la ruta vulnerable es irrevocable y no existe ningún mecanismo de pausa.** Para un incidente como el de nov-2025 esto es determinante: no se puede mitigar en caliente, sólo con una migración. (Ver el parche propuesto en §7: `pause()` + gate de los `joinswap*`.)

### M-1 🟡 DoS de `exitPool`/`joinPool` con reservas en polvo

```solidity
// exitPool :409-418
uint tokenAmountOut = bmul(ratio, bal);
require(tokenAmountOut != 0, "ERR_MATH_APPROX");   // ← cualquier token en polvo mata la salida proporcional
```

Con `bmul` *half-up*, `bmul(ratio, bal) == 0` ⇔ `ratio·bal < 0,5e18`. Verificado (E5):

| reserva (raw) | retirada proporcional mínima | efecto |
|---|---|---|
| 1 wei | `pAi/pS ≥ 50 %` | **nadie con < 50 % del BPT puede salir** |
| 2 wei | `≥ 25 %` | idem, < 25 % |
| 100 | `≥ 0,5 %` | LPs pequeños bloqueados |
| 1e6 (`MIN_BALANCE`) | `≥ 5e-7` | irrelevante |

El **griefing es prácticamente gratis**: el atacante compra el token en pasos de `MAX_OUT_RATIO` (≤ 1/3 por llamada) y **se queda con lo comprado** (sólo paga comisiones ≈ 0,03 %), dejando la reserva en 1-2 wei. No roba, pero degrada la única salida "limpia" y deja a los LPs pequeños con la ruta de salida de un solo activo (más comisiones y más llamadas). Combinado con H-1, es el mismo primitivo que C-1: **el polvo no es sólo un estado explotable, es un estado que cualquiera puede imponer**.

### M-2 🟡 `bpow` puede consumir gas no acotado ⇒ OOG

`bpowApprox` (`BNum.sol:128-163`) itera `for (uint i = 1; term >= precision; i++)` sin cota. La serie binomial `Σ C(e,k)·x^k` converge **geométricamente** mientras `x = base − BONE ≪ BONE`, pero converge como `k^-1,5` cuando `x → BONE`. Medido (E7, `exp = 0,8`):

| base | iteraciones | gas aprox. |
|---|---|---|
| 1,0 | 1 | ~750 |
| 1,5 | 24 | ~18.000 |
| 1,9 | 122 | ~91.500 |
| **2,0 − 1 wei** | **136.146** | **~100.000.000** ⇒ OOG (> límite de bloque) |

Alcanzable desde `joinswapPoolAmountOut` cuando `pAo → pS` (`poolRatio → 2`). Impacto: (i) la llamada revierte siempre (robustez/UX, y hace que la cota real sea `base ≲ 1,9` en la práctica), y (ii) **un integrador que confíe en `joinswapPoolAmountOut` puede ser forzado a OOG** si su `pAo` cae en la zona. Severidad media (no es robo). Fix: cota de iteraciones (`require(i <= MAX_ITER)`) o `require(base <= 1.5e18)` en las rutas de join.

### M-3 🟡 Redondeo *half-up* sistemático (`bmul`, `bdiv`)

`bmul` suma `BONE/2` antes de dividir y `bdiv` suma `b/2` (`BNum.sol:63-86`). No es el "redondeo hacia abajo" del reporte: es **redondeo al más cercano**, que a veces favorece al usuario. Busqué ciclos rentables (S1-S4) y el resultado es:

- `joinPool`+`exitPool`, `swap` ida-vuelta, `join-swap`+`exit-swap` en estado normal: **sin ganancia** (la comisión se come cualquier desvío).
- Con reserva en polvo aparece una ganancia acotada: en un ciclo `joinswapExternAmountIn`/`exitswapPoolAmountIn` se observó `+1.000 wei` con `bO = 1e21` (es decir `+1e-18·bO·(1/w)`). **Fuga acotada ≈ `bO/(w·1e18)` por operación**, no escalable (al subir el importe, la comisión domina). Es exactamente el mismo mecanismo que se vuelve catastrófico cuando la propia reserva es polvo, pero **en estado sano es económicamente irrelevante**.
- ToB ya documentó estos casos como **#203/#204/#205 "Mitigated"** (no *fixed*), y `math_extreme_weights.js` cubre los extremos de peso.

Recomendación: introducir `bdivUp`/`bmulDown` y usarlos con dirección **siempre favorable al pool** en las rutas de join/exit (§7). No arregla C-1/C-2 (no es la raíz) pero elimina la variante de granularidad.

### L-1…L-8 🔵 Bajo / informativo

| ID | Hallazgo | Referencia |
|---|---|---|
| L-1 | `setController(address(0))` permitido ⇒ pool irrecuperable (no se puede `finalize`/`unbind` ni pagar exit fees) | `:205`, ToB #198 **WONT FIX** |
| L-2 | `bind`/`rebind` no rechazan `token == address(this)` (el propio BPT) ni `address(0)`; bindear el BPT propio crea estructuras recursivas en `_records` y rompe `joinPool`/`exitPool` | `:241`, `:262` |
| L-3 | `BToken._move` permite `transfer`/`transferFrom` a `address(0)` ⇒ BPT atrapado | `BToken.sol:57`, ToB #197 **WONT FIX** |
| L-4 | `bind` no lleva `_lock_` (por diseño delega en `rebind`, pero deja la escritura de `_records`/`_tokens` sin mutex; sólo explotable si el *controller* es malicioso) | `:241-260` |
| L-5 | Ninguna función acepta `deadline`; todo es vulnerable a MEV/sandwich por diseño (AMM sin oráculo) | todas |
| L-6 | `IERC20` asume `bool` de retorno: **USDT y similares no funcionan** (revert por decodificación) | `BToken.sol:20-33` |
| L-7 | `LOG_CALL` emite `msg.data` completo de toda llamada (incluidos parámetros que el usuario quizá no quiere publicar) | `:48-57` |
| L-8 | **Raíz arquitectónica:** V1 no normaliza decimales en ningún punto; todas las reservas se tratan como si fueran `1e18`. Esto es lo que hace que el "mínimo representable" de un token de 8/6 decimales sea comparable al `MIN_BALANCE`, y por lo que el mismo bug reaparece una y otra vez | `BConst.sol:25-38` |

---

## 5. ¿Hay "otro crítico" que no sea de la familia join?

**No he encontrado un segundo robo independiente.** Lo que sí hay es (i) la **duplicación de la primitiva** en C-2 (crítico, y lo más importante del informe), (ii) el **enabler** H-1, y (iii) dos DoS gratuitos (M-1, M-2) más el "brick" de H-2. Esto es coherente con lo que dice `Audit.md`: todas las propiedades de "no se pueden generar BPT gratis / no se pueden sacar activos gratis" que fallaron (#203, #204, #205) son la **misma** familia de redondeo/polvo, y sólo se marcaron "Mitigated", nunca "Fixed".

---

## 6. Lo que se descartó (y por qué)

| Clase | Veredicto |
|---|---|
| **Reentrancy** | ✅ Sólido. Todas las funciones externas que mutan estado llevan `_lock_` (`swap*`, `joinPool`, `exitPool`, `joinswap*`, `exitswap*`, `bind→rebind`, `gulp`, `set*`, `finalize`, `unbind`); las vistas llevan `_viewlock_`. Los `_pull/_pushUnderlying` se ejecutan **después** de actualizar `_records` y `_totalSupply`. Los `transfer/approve` de BPT no están bloqueados pero no hacen llamadas externas ⇒ no abren camino de reentrada a estado de pool. |
| **Control de acceso** | ✅ `setSwapFee`/`setController`/`setPublicSwap`/`finalize`/`bind`/`rebind`/`unbind` exigen `_controller`. `BFactory.collect` exige `_blabs`. `newBPool()` toma el control correctamente (`setController(msg.sender)` desde la factory). |
| **Overflow/underflow** | ✅ `badd`/`bsub`/`bmul`/`bdiv` con chequeos; `uint256` en Solidity 0.5.12 sin SafeMath no es problema aquí porque las primitivas están envueltas. `i * BONE` en `bpowApprox` acotado por el gas. |
| **`BToken.transferFrom` / allowance** | ✅ `msg.sender == src || amt <= allowance`, decremento con `bsub`, soporte `uint(-1)`. Sin hallazgos. |
| **Orden de actualización en `joinPool`/`exitPool`** | ✅ `_mint`/`_push` y `_pull`/`_burn` en orden correcto; `_burn` exige `_balance[this] >= amt`. |
| **`unbind` swap-and-pop** | ✅ Correcto incluso cuando el índice es el último. |

---

## 7. Remediación propuesta

El parche completo está en **`security/patches/balancer-v1-hardening.patch`** (diff unificado contra `contracts/`, **no compilado en este entorno** — revisar con `solc 0.5.12` antes de desplegar). Resumen por prioridad:

### P1 — Contención inmediata (aunque el pool ya esté desplegado no se puede aplicar; sirve para forks/redeploys)

```solidity
// BPool.sol
bool private _paused;

function setPaused(bool p) external _logs_ _lock_ {
    require(msg.sender == _controller, "ERR_NOT_CONTROLLER");
    _paused = p;                       // permitido SIEMPRE, también tras finalize()
}

// añadir a joinPool / exitPool / swapExactAmountIn / swapExactAmountOut
// / joinswapExternAmountIn / joinswapPoolAmountOut / exitswapPoolAmountIn
// / exitswapExternAmountOut:
require(!_paused, "ERR_PAUSED");
```

Y permitir desactivar swaps después de `finalize` (una sola dirección, para que el controlador no pueda cambiar las reglas de negocio a mitad de vida):

```solidity
function setPublicSwap(bool public_) external _logs_ _lock_ {
    require(msg.sender == _controller, "ERR_NOT_CONTROLLER");
    require(!_finalized || !public_, "ERR_CANNOT_REENABLE");   // una vez finalizado, sólo se puede apagar
    _publicSwap = public_;
}
```

Además, **gatear los `joinswap*` con `_publicSwap`** (hoy no lo están):

```solidity
function joinswapExternAmountIn(...) external ... {
    require(_publicSwap, "ERR_SWAP_NOT_PUBLIC");
```

### P2 — Cerrar la causa raíz (obligatorio; P1 sólo mitiga)

1. **Suelo de reserva como invariante**, no como chequeo de génesis. Requiere un mínimo **por token** (los decimales no se normalizan):

```solidity
mapping(address => uint) private _minBalance;   // fijado en bind/rebind según decimals

function _checkFloor(address t) internal view {
    require(_records[t].balance >= _minBalance[t], "ERR_MIN_BALANCE");
}
```
   y llamar `_checkFloor(t)` en **toda** ruta que decremente `_records[t].balance` (`swapExactAmount*`, `exitswap*`, `exitPool`) y tras todo join. Con un `_minBalance` económicamente significativo (p. ej. `1e15` para 18 dec, `1e4` para 8 dec) **la reserva no puede llegar a polvo** y C-1/C-2 desaparecen. Ojo: `MIN_BALANCE = 1e-12` actual **no** sirve para esto.

2. **Rechazar joins unilaterales sobre reservas no significativas** (defensa en profundidad; no requiere configuración):

```solidity
// en joinswapExternAmountIn y joinswapPoolAmountOut
require(_records[tokenIn].balance >= _minBalance[tokenIn], "ERR_RESERVE_TOO_SMALL");
```

3. **Redondeo siempre a favor del pool** (elimina la variante de granularidad):

```solidity
function bdivUp(uint a, uint b) internal pure returns (uint) {   // BNum.sol
    require(b != 0, "ERR_DIV_ZERO");
    uint c0 = a * BONE;
    require(a == 0 || c0 / a == BONE, "ERR_DIV_INTERNAL");
    return c0 == 0 ? 0 : (c0 - 1) / b + 1;
}
```
   - `calcSingleInGivenPoolOut`: `newTokenBalanceIn` con `bmulDown`, división final con `bdivUp` ⇒ el input se redondea **hacia arriba**.
   - `calcPoolOutGivenSingleIn`: `newPoolSupply` con `bmulDown` ⇒ el BPT se redondea **hacia abajo**.
   - `calcInGivenOut`: `bdivUp` en el resultado final.

4. **`gulp` monótono** (sólo permite subir el registro) o eliminarlo:

```solidity
function gulp(address token) external _logs_ _lock_ {
    require(_records[token].bound, "ERR_NOT_BOUND");
    uint real = IERC20(token).balanceOf(address(this));
    require(real > _records[token].balance, "ERR_GULP_DOWN");   // nunca hacia abajo
    _records[token].balance = real;
}
```

5. **`_pullUnderlying` verifica lo recibido** (rechaza fee-on-transfer/deflacionarios en vez de corromper el registro):

```solidity
function _pullUnderlying(address erc20, address from, uint amount) internal {
    uint before = IERC20(erc20).balanceOf(address(this));
    bool xfer = IERC20(erc20).transferFrom(from, address(this), amount);
    require(xfer, "ERR_ERC20_FALSE");
    require(bsub(IERC20(erc20).balanceOf(address(this)), before) == amount, "ERR_UNSUPPORTED_TOKEN");
}
```

### P3 — Robustez

- `bpowApprox`: `require(i <= 256, "ERR_BPOW_ITER")`, o `require(base <= (3 * BONE) / 2)` en las rutas de join (evita el OOG de M-2).
- `setController`: `require(manager != address(0), "ERR_ZERO_ADDRESS")`.
- `bind`/`rebind`: `require(token != address(0) && token != address(this), "ERR_BAD_TOKEN")`.
- `BToken._move`: `require(dst != address(0), "ERR_ZERO_ADDRESS")`.
- Añadir `deadline` a todas las funciones de usuario (L-5) y soportar tokens sin valor de retorno (L-6) si se van a listar.

### P4 — Nota sobre lo que **no** funciona

- ❌ **Capar el BPT acuñado por llamada** (`pAo ≤ k·pS`) **no arregla nada**: el depósito total hasta quedarse con X % del suministro es `bI · X^(1/w)`, **independiente de `k`**. Sólo añade llamadas.
- ❌ **Endurecer sólo `joinswapPoolAmountOut`**: C-2 sigue abierto.
- ❌ **Subir `MIN_BALANCE` a un valor global**: rompe tokens de 8/6 decimales (no se normalizan decimales). Tiene que ser por token.
- ❌ **Confiar en `_publicSwap`**: hoy no cubre las rutas de join y no se puede tocar tras `finalize`.

---

## 8. Sobre el pool explotado en nov-2025 (contexto)

La descripción pública (compresión de reservas + depósito de 1 satoshi + retirada desproporcionada) **encaja con la aritmética de este código** en la parte de acuñación: lo he reproducido (§2.2, §3). Donde discrepo es en:

1. **El mecanismo no es "truncamiento hacia abajo que favorece al atacante"**, es **precio marginal del invariante a reserva polvo** (con redondeo *half-up*, no *down*). Esto importa porque un parche de redondeo **no** lo arregla.
2. **La condición no es "tokens con < 18 decimales"** sino **"reserva en polvo"**; los decimales sólo determinan el coste de llegar ahí. Verificado con un token de 18 dec (§3.3).
3. **La condición "`joinswapPoolAmountOut` invocable públicamente" es tautológica** en V1 (todos los `joinswap*` son públicos tras `finalize`), y además **hay una segunda función vulnerable** (`joinswapExternAmountIn`) que el reporte no menciona.
4. **Los pools V1 ponderados son mucho menos rentables de atacar "desde cero"** que los stable pools V2 (tabla §3.4): el sobrecoste de compresión no se recupera. La exposición real en V1 son pools **ya** en polvo, honeypots de creador y los DoS M-1/M-2.

---

## 9. Apéndice — resultados reproducibles

```
$ python3 security/experiments.py     # E1..E7
$ python3 security/rounding_search.py # S1..S4
$ python3 security/economics.py       # tabla de capital/botín/ROI
```

Salidas clave ya citadas en §2.2 (E1), §3 (E2), §3.4 (economics), §4 H-2 (E6), §M-1 (E5), §M-2 (E7), §M-3 (S1-S4).

| Archivo | Contenido |
|---|---|
| `security/bmath_sim.py` | réplica exacta de `BNum`/`BMath` + modelo de `BPool` |
| `security/experiments.py` | E1-E7 |
| `security/rounding_search.py` | S1-S4 (búsqueda de ciclos rentables) |
| `security/economics.py` | capital/botín/ROI por factor de compresión |
| `security/patches/balancer-v1-hardening.patch` | parche propuesto (P1-P3) |
