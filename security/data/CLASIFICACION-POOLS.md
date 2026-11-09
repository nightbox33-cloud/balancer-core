# Clasificación de los 100 pools por severidad real

**Datos:** `data/pools_live.csv` (100 pools activos, `finalized=true`, con pesos, balances, precios y supply aportados por el usuario).
**Cálculo:** `analyze_live.py` — aritmética del contrato (`BMath`/`BNum`) en enteros exactos, sin estimaciones.
**Criterio:** `ρ` (grado de desequilibrio) + ataque simulado con la secuencia real de llamadas.

---

## Veredicto

| | pools | TVL | botín realizable |
|---|---:|---:|---:|
| **A · VULNERABLE** (ρ por debajo del umbral, con precios reales) | **14** | $377.133 | **$261.204** |
| **B · REVISAR** (hay un token sin precio: ρ no es calculable) | 40 | $1.142.294 | $0 – $1.142.294 |
| **C · SIN RIESGO hoy** (ρ por encima del umbral) | 46 | $2.025.291 | $0 |
| total | 100 | $3.544.719 | ≤ $1.403.498 |

**El TVL no ordena el riesgo.** El pool más grande del conjunto —`0x1eff8af5`, $761.097— es **inmune**. El tercero por botín —`0x1373e57f`, $29.298— **se compra por 9 dólares**. Lo que ordena el riesgo es una sola cosa: cuánto vale la reserva más barata comparada con la cuota que su peso le asigna.

---

## 1. El criterio

Para cada token `i` de un pool:

```
ρ_i = valor de la reserva i  /  ( w_i × TVL )        (cuota justa por peso)
```

`ρ = 1` significa equilibrio perfecto. `ρ → 0` significa que la reserva está vacía. El umbral de vulnerabilidad depende del peso (calculado en `screen.py` con la aritmética exacta, es el punto donde el P&L del ataque se anula):

| w | 5% | 10% | 20% | 30% | 50% | 70% | 80% | 90% |
|---|---|---|---|---|---|---|---|---|
| **ρ\*** | 0,819 | 0,827 | 0,845 | 0,862 | 0,899 | 0,938 | 0,958 | 0,979 |

**Vulnerable ⟺ existe un token con `ρ_i < ρ*(w_i)`.** El motivo está en `calcSingleInGivenPoolOut`: el coste de acuñar BPT contra una reserva **no tiene referencia de valor**, es lineal en el balance de esa reserva. Si la reserva está desequilibrada hacia abajo, acuñas participación en el pool entero pagando por la parte barata.

Segunda etapa (la que da los importes): simulación de la secuencia real
`n × joinswapExternAmountIn(token_barato, 50% de su reserva)` → `exitPool`, con la aritmética del contrato y **contabilidad exacta en enteros** (el P&L se calcula como diferencia de enteros y sólo al final se convierte a dólares; restar floats del orden del capital produce artefactos de 10²² $, ya detectados y descartados en el barrido anterior). Se barre `n` y se queda el óptimo: la curva sube y **baja**, porque el depósito no recuperable `(1−f)·D` crece con `n`.

---

## 2. Tabla A — los 14 pools vulnerables

Ordenados por botín. `ρ` es el del token que se deposita; `capital` es el total que hay que mover en la misma transacción; `f` es la fracción del pool que acaba en manos del atacante.

| pool | TVL hoy | ρ | reserva que se deposita | botín | capital | f | llamadas | salida |
|---|---|---|---:|---|---:|---:|---:|---:|---|
| `0x9a16bddf0e89541d6abea035b706968465241e4f` | $135.358 | 0,001 | USDC, w=20% | $97.639 | $36.303 | 78% | 19 | pro-rata |
| `0x3c71fad2a1fc9ea1c5f7b87491daae7f1669d21a` | $98.149 | 0,167 | WETH, w=50% | $43.682 | $85.402 | 70% | 6 | pro-rata |
| `0x1373e57f764a7944bdd7a4bd5ca3007d496934da` | $29.298 | 0,000 | USDC, w=12% | $29.026 | $9 | 65% | 21 | mono:0x0ba45a8b |
| `0xe9a2c7a19e47bac855fad9c3147ffe95aea8c4c4` | $27.459 | 0,000 | BAL, w=50% | $27.376 | $26.815 | 100% | 32 | pro-rata |
| `0x0e3e2781ee4ed14758c04eca5b4cc4a7aee459cd` | $17.761 | 0,002 | WBTC, w=12% | $17.761 | $8.570 | 100% | 121 | pro-rata |
| `0xf1f3d252be946ee079f02cf577372bdada307457` | $17.392 | 0,000 | WBTC, w=8% | $17.307 | $1 | 38% | 16 | mono:OCEAN |
| `0xaaa117d04aaf533701c9e40cd52113706d95d420` | $13.003 | 0,000 | REN, w=50% | $12.958 | $11.038 | 100% | 31 | pro-rata |
| `0xa1ec308f05bca8acc84eaf76bc9c92a52ac25415` | $6.423 | 0,264 | LINK, w=60% | $6.354 | $752 | 99% | 115 | pro-rata |
| `0xf0f8b1ce9d95dfbe82f8310d48dcae71d79f9519` | $17.435 | 0,285 | PAR, w=50% | $5.188 | $10.108 | 56% | 4 | pro-rata |
| `0x30cb859317e171832b064c97cc03ccb081954d1b` | $3.883 | 0,043 | WETH, w=50% | $2.720 | $3.128 | 83% | 9 | pro-rata |
| `0xc351648240e9fc9213e8b6016e566f95c5fa7909` | $10.056 | 0,313 | WETH, w=20% | $993 | $1.497 | 22% | 3 | pro-rata |
| `0xba46868f49182b521b71bf9894d24da7e969e286` | $916 | 0,372 | DAI, w=50% | $200 | $693 | 55% | 4 | pro-rata |
| `0x36a57f5ea6cceb75523639aba3224036e5f8231d` | $0 | 0,731 | renBTC, w=50% | $0 | $0 | 18% | 1 | pro-rata |
| `0xaf59044157ed99f3630c4c67f8870e09a5d1a6e2` | $0 | 0,774 | MTLX, w=33% | $0 | $0 | 13% | 1 | pro-rata |

Los dos últimos (`0x36a57f5e`, `0xaf59044`) están por debajo del umbral pero su TVL es **cero**: vulnerables de forma, sin nada que robar.

---

## 3. Los casos que importan

### 3.1 `0x9a16bddf` — OCEAN/USDC 80/20, $135.358

La reserva de USDC es **16,38 USDC ($16,38)** en un pool que vale $135.358. Su cuota justa por el peso del 20% sería $27.072. `ρ = 0,0006`.

Balance completo, verificado a mano contra el modelo:

| | valor |
|---|---:|
| reservas iniciales | OCEAN $135.341,49 + USDC $16,38 |
| 19 depósitos de USDC (50% de la reserva cada uno) | $36.303,18 |
| reservas finales | OCEAN $135.341,49 + USDC $36.319,56 = **$171.661,06** ✓ (≡ inicial + depositado) |
| BPT en manos del atacante | 78,03% |
| salida pro-rata de ese 78,03% | $133.941,73 |
| **P&L** | **+$97.638,55** |

No es un ataque de redondeo ni de polvo fabricado: es comprar el 78% de un pool de $135k pagando $36k por el lado que el pool tiene vacío. La salida mono-token (quemar todo el BPT y sacar un solo activo) da menos aquí ($114.406), y el modelo elige la mejor de las dos vías en cada caso.

### 3.2 `0x1373e57f` — ocho tokens al 12,5%, siete reservas a cero

| token | reserva |
|---|---:|
| `0x0ba45a8b` | $29.297,98 |
| UMA / SNX / MKR / LINK / DAI / WETH / USDC | $0,032 / $0,031 / $0,027 / $0,023 / $0,022 / $0,014 / $0,002 |

Siete de las ocho patas están literalmente vacías. Con **$9** de capital se acuña el 65% del pool y se sale por la única pata que tiene dinero: **+$29.026**. Es el pool más rentable por dólar invertido de todo el conjunto.

### 3.3 `0xe9a2c7a1` y `0xf1f3d252` — un solo activo real

- `0xe9a2c7a1` (BAL/OCEAN 50/50): BAL $0,06, OCEAN $27.458,72. 32 llamadas, $26.815 → **+$27.376** (f = 99,8%).
- `0xf1f3d252` (LOCK 75% / WBTC 7,5% / WETH 7,5% / LINK 5% / OCEAN 5%): todo el valor está en OCEAN ($17.391,61); WBTC tiene 2e-08 unidades ($0,0015). Con **$1** de capital, f = 38% y salida mono-token: **+$17.307**.

### 3.4 `0x3c71fad2` — el único desequilibrio «de verdad»

WETH/OCEAN 50/50, pero WETH está en $8.219 (8,4% del pool) cuando su cuota justa es $49.075. `ρ = 0,167`. Es el caso menos extremo de la lista y aun así: 6 llamadas, $85.402 de capital, f = 70,3%, **+$43.682**. La curva de P&L (`n` = 1..12) sube hasta n=6 y cae: en n=12 el depósito no recuperable ya supera el botín (−$3.672). El óptimo es finito y el modelo lo encuentra.

### 3.5 El patrón, resumido

En **9 de los 14** la reserva que se deposita vale **menos de $100**; en 7 es literalmente céntimos. Esto no es una colección de pools «desequilibrados»: es una colección de pools **con una sola pata financiada**. El ataque no necesita condiciones de mercado ni una posición previa: la entrada vale céntimos y el depósito se recupera en la misma transacción.

---

## 4. ¿Cuánto tiene que comprar exactamente?

Dos preguntas distintas que la columna «capital» de la tabla A mezclaba. Aquí van separadas.

### 4.1 El mínimo: una sola llamada, sin flash loan

| pool | token a comprar | unidades (1 llamada) | coste | BPT obtenido | botín |
|---|---|---:|---:|---:|---:|
| `0x9a16bddf0e89541d6abea035b706968465241e4f` | USDC | 8,19 | $8,19 | 7,7% | $12.770 |
| `0x3c71fad2a1fc9ea1c5f7b87491daae7f1669d21a` | WETH | 1,94 | $4.109,57 | 18,3% | $25.792 |
| `0x1373e57f764a7944bdd7a4bd5ca3007d496934da` | USDC | 0,000903 | $0,00 | 4,9% | $9.624 |
| `0xe9a2c7a19e47bac855fad9c3147ffe95aea8c4c4` | BAL | 0,267 | $0,03 | 18,3% | $9.141 |
| `0xf1f3d252be946ee079f02cf577372bdada307457` | WBTC | 1e-08 | $0,00 | 3,0% | $7.865 |
| `0xaaa117d04aaf533701c9e40cd52113706d95d420` | REN | 9,02 | $0,02 | 18,3% | $4.329 |
| `0xf0f8b1ce9d95dfbe82f8310d48dcae71d79f9519` | PAR | 1,12e+03 | $1.244,06 | 18,3% | $3.732 |
| `0x30cb859317e171832b064c97cc03ccb081954d1b` | WETH | 0,0197 | $41,77 | 18,1% | $1.185 |
| `0xc351648240e9fc9213e8b6016e566f95c5fa7909` | WETH | 0,148 | $315,15 | 7,8% | $591 |
| `0xba46868f49182b521b71bf9894d24da7e969e286` | DAI | 85,3 | $85,27 | 18,3% | $162 |

Con **8,19 USDC** (ocho dólares) se obtiene el 7,7% de `0x9a16bddf` y se sale con **$12.770**. Una transacción, sin capital prestado, sin bucle. En `0xe9a2c7a1` basta **0,27 BAL** (tres céntimos) para sacar $9.141. Este es el suelo: lo que cuesta entrar por primera vez es exactamente **la mitad de la reserva que hay en el pool hoy** (`MAX_IN_RATIO` = 0,5), y esas reservas son de céntimos.

La salida de esta tabla es mono-token en los pools desequilibrados: quemar el BPT y sacar **un solo** activo da más que el pro-rata, porque el pool te lo vende al precio interno torcido.

### 4.2 El óptimo: bucle de compresión

| pool | token a comprar | unidades totales | valor | 1er depósito | reserva en el pool hoy | n | botín |
|---|---|---:|---:|---:|---:|---:|---:|
| `0x9a16bddf0e89541d6abea035b706968465241e4f` | USDC | 3,631e+04 | $36.303 | $8,19 | 16,4 | 19 | $97.639 |
| `0x3c71fad2a1fc9ea1c5f7b87491daae7f1669d21a` | WETH | 40,22 | $85.402 | $4.109,57 | 3,87 | 6 | $43.682 |
| `0x1373e57f764a7944bdd7a4bd5ca3007d496934da` | USDC | 9,006 | $9 | $0,00 | 0,00181 | 21 | $29.026 |
| `0xe9a2c7a19e47bac855fad9c3147ffe95aea8c4c4` | BAL | 2,301e+05 | $26.815 | $0,03 | 0,533 | 32 | $27.376 |
| `0xf1f3d252be946ee079f02cf577372bdada307457` | WBTC | 1,312e-05 | $1 | $0,00 | 2e-08 | 16 | $17.307 |
| `0xaaa117d04aaf533701c9e40cd52113706d95d420` | REN | 5,188e+06 | $11.038 | $0,02 | 18 | 31 | $12.958 |
| `0xf0f8b1ce9d95dfbe82f8310d48dcae71d79f9519` | PAR | 9070 | $10.108 | $1.244,06 | 2,23e+03 | 4 | $5.188 |
| `0x30cb859317e171832b064c97cc03ccb081954d1b` | WETH | 1,473 | $3.128 | $41,77 | 0,0394 | 9 | $2.720 |
| `0xc351648240e9fc9213e8b6016e566f95c5fa7909` | WETH | 0,7051 | $1.497 | $315,15 | 0,297 | 3 | $993 |
| `0xba46868f49182b521b71bf9894d24da7e969e286` | DAI | 692,8 | $693 | $85,27 | 171 | 4 | $200 |

### 4.3 Cómo se lee

- **`unidades` y `valor`**: lo que hay que tener en la mano —o pedir en un flash loan— durante esa transacción. Se multiplica por **1,5 en cada llamada** (cada depósito es el 50% de la reserva, y la reserva pasa a ser 1,5× la anterior), y por eso el total es `reserva × (1,5ⁿ − 1)`: en `0x3c71fad2` son 3,87 WETH en el pool hoy y 40,22 WETH acumulados en 6 llamadas.
- **No se pierde.** Al salir te llevas el 78% (o el 70%, o el 99%) de *todo*, incluido ese mismo porcentaje de tu propio depósito. Lo que no vuelve es `(1−f)×depósito`, y de ahí sale el P&L. Por eso el «valor» de la columna no es un coste: es un **requisito de caja instantáneo**, que es justo lo que un flash loan resuelve por un 0,05%.
- **El coste real** es la suma de: fee del flash loan ($18 en el caso de USDC, $43 en el de WETH) + gas (~120.000 por llamada, ~2,5 M para 19 llamadas ≈ $115). Frente a $97.639 y $43.682 de botín.
- **`n`** sale del óptimo: sube mientras la fracción capturada gana a la parte no recuperable del depósito, y baja cuando el depósito crece más rápido que lo que se lleva.

### 4.4 La letra pequeña que este modelo no puede verificar

El modelo asume que las unidades se compran al precio de la tabla **sin slippage**. En `0xaaa117d0` eso son **5,19 millones de REN**: si no hay esas unidades disponibles, el ataque no falla, simplemente se hace con menos `n` — y el botín baja hacia el de la tabla 4.1, que ya es rentable con 9 REN. **El suelo es 4.1, el techo es 4.2; en medio no hay ningún escenario donde el ataque deje de ser rentable.** La única comprobación que falta es una consulta de liquidez por token.

Además, los tokens con pocos decimales (WBTC 8, USDC 6) tienen un suelo de granularidad: cuando la reserva son 2 unidades mínimas, `bmul(bal, 0,5)` devuelve 1 y el bucle se corta antes de lo que dice el modelo. Afecta a las últimas llamadas, no al resultado.

---

---

## 5. Tabla B — los 40 pools con tokens sin precio

Aquí `ρ` no se puede calcular, así que el escáner valora esos tokens a cero. En vez de adivinar, calculo el **precio de equilibrio `p*`**: el precio del token sin precio por debajo del cual el pool cae por debajo del umbral y pasa a ser vulnerable.

> Úsese así: se pide el precio del token en cualquier DEX/agregador. Si está **por debajo** de `p*`, el pool está abierto por el importe de su TVL. Si está por encima, es seguro a ese precio.

| pool | TVL | token sin precio | p* (por debajo ⇒ vulnerable) | unidades a conseguir |
|---|---|---:|---:|---:|
| `0xe00770cbe21933e8040ce1b2d0e2c96fd7e4b63f` | $715.351 | ULU | $510,3 | 4,3e+22 |
| `0x33812e984d49ed5b44d75a008c12060e5076238c` | $141.652 | xAAVEa | $1,607 | 1,5e+23 |
| `0x48c1d1d43f2a2267dacdd06bd6c63f3696073ed4` | $75.171 | COVER_CDS | $0,814 | 6,5e+22 |
| `0xeb85b2e12320a123d447ca0da26b49e666b799db` | $50.637 | PCT | $0,2052 | 4,3e+22 |
| `0xc1b10e536cd611acff7a7c32a9e29ce6a02ef6ef` | $35.283 | MPL | $0,2967 | 2,9e+22 |
| `0xa795600590a7da0057469049ab8f1284baed977e` | $24.152 | DEFI+L | $0,8859 | 2,9e+22 |
| `0xc786ab4704e6b79c6bfedfefd0e0d7f0b0abfa73` | $22.356 | COVER_RULER | $0,814 | 1,9e+22 |
| `0xae95d3198d602acfb18f9188d733d710e14a27dd` | $14.872 | BHSc$ | $1 | 1,3e+22 |
| `0x6b74fb4e4b3b177b8e95ba9fa4c3a3121d22fbfb` | $10.356 | yTrump,nTrump | $0,5517 | 3,8e+21 |
| `0xd9346ab5a2ed5e32f5fc69a5cccf45211307ffc5` | $7.300 | xAAVEb | $1,275 | 8,6e+21 |
| `0x2dd7255b487a62d738110bd10f8bc4b4ea989778` | $5.036 | uUSDrBTC-DEC | $2,474 | 5,7e+21 |
| `0x79c44cd4291a72aa26a2f04a3559daf67e3ff761` | $4.397 | MCX | $9,722e-05 | 2,2e+20 |
| `0xf658132f2a5edd07da1fde126558aabedf11398c` | $3.183 | WFIL | $2,48 | 3,8e+21 |
| `0xf22c9bd7c03d7f06290d331a8ea1477ddab80e85` | $2.845 | WZEC | $108,9 | 2,5e+21 |
| `0x0d88b55317516b84e78fbba7cde3f910d5686901` | $2.714 | ALBT | $3,969e-05 | 2,5e+21 |
| `0x8ca1b17c69fe04bf31036219d75ad1bab29f88f3` | $2.652 | VTT | $0,003501 | 2,5e+21 |
| `0x5277a42ef95eca7637ffa9e69b65a12a089fe12b` | $2.501 | FRY | $8,39e-05 | 2,5e+21 |
| `0x1e63fd8f5c2b7d4498f72f09016c0893e382e1f8` | $2.162 | IND | $0,0007953 | 3,8e+21 |
| `0x96248f6305d04c4842df1abba3714036226bf3fb` | $2.123 | COVER_ORIGIN | $0,7184 | 6,7e+16 |
| `0x53e6728366d8518e69867ee15fa990708c0d8cd6` | $1.992 | COVER_RAI | $0,6503 | 1,5e+17 |
| `0xe3f9cf7d44488715361581dd8b3a15379953eb4c` | $1.872 | xSNXa | $2,891e-06 | 1,7e+21 |
| `0xfff2a5f81d14729408201341df42af29f3b30458` | $1.670 | COVER_BADGERDAO | $0,814 | 1,7e+21 |
| `0x1f187fa8d99803a0c1d7bb66ba619aa92a3ec34a` | $1.516 | ULU | $0,02929 | 6,6e+19 |
| `0x4e2579468f414f3b2c683e8562d4c67056d5cb4b` | $1.442 | O-OCEAN-MAR22 | $1,27 | 1,7e+21 |
| `0xfab9446167bd8c375a2a64fe85bd71488cf14edd` | $1.410 | XAUt | $574,2 | 7,5e+20 |
| `0x554659b6e28251918defd45a34bae6a30753ac` | $1.398 | FRY | $9,773e-05 | 1,1e+21 |
| `0xde7e006a9583a4cdcbdd0e233155d88d80962b31` | $1.312 | MCX | $9,676e-05 | 1,1e+21 |
| `0x0ffc0ac3139a7cde29e6858c369b32cbbaf41cf4` | $1.121 | YFL | $2,389 | 1,1e+21 |
| `0xf8cc687f4744f47781b5742a6c029fccfbdbeffc` | $1.110 | YD-BTC-SEPT | $1,007 | 1,1e+21 |
| `0xcca17fe7e292d75994d0ab97fd78416edcf64a76` | $1.106 | YD-ETH-SEPT | $39,26 | 6,7e+16 |
| `0x5dcb5baa17a5af85aaec5d2b422cab13c0141bce` | $972 | LINKUSD | $25,67 | 1,5e+17 |
| `0xf11da347012b9752931202a40ed1328982551f5c` | $580 | LEND | $0,05079 | 2,2e+20 |
| `0xe8620e0f1867a657b0e32b9e123873d5e84f4ec5` | $41 | ETHMNY | $1,585e-08 | 2,6e+18 |
| `0x55353cbadda8fd525f0e6f307b3527d518416700` | $3 | WSTA | $8,61e-05 | 2,6e+18 |
| `0x33bc3abfabde8fceb0ced58e16184fb4cfc163ef` | $2 | COVER_REN | n/d | 1,0e+17 |
| `0x1b8874baceaafba9ea194a625d12e8b270d77016` | $2 | BHSc$ | $1,185 | 1,1e+18 |
| `0x3b260cf977df1ff8d87960064daee2ce491a1b91` | $1 | UNI-V2 | $1,12 | 7,6e+17 |
| `0xee4148ff794cf1d0976d2063a32a8f562abe6d75` | $1 | RPL | $1,162 | 1,0e+17 |
| `0xcd461b73d5fc8ea1d69a600f44618bdfac98364d` | $0 | UNI-V2,WBTC | $1,444 | 6,7e+16 |
| `0x5b2dc8c02728e8fb6aea03a622c3849875a48801` | $0 | STR,PIXEL,IMPACT,GIFT,NFTS,LIFT,YFU | $0,0009441 | 2,3e+14 |

`0xe00770cb` es el más importante: $715.351 de TVL con ULU al 5%. ULU sólo tiene que valer **menos de $510** para que el pool sea drenable entero. Las unidades a conseguir (`4,3e22`) parecen absurdas, pero son unidades de un token que, si vale menos de $510 y tiene supply de mil millones, se compran por muy poco o directamente no existen con liquidez — en cuyo caso el ataque es aún más fácil, no más difícil. Por eso esta categoría no es «probablemente segura»: es **«hay que medirla y no está medida»**.

---

## 6. Los 46 «seguros» no son seguros: son seguros *hoy*

Los 46 pools con `ρ ≥ ρ*` suman **$2.025.291** y hoy no son atacables. Pero `ρ` se mueve con el **precio relativo** entre los tokens del pool (un movimiento de ambos a la vez se cancela; lo que rompe el equilibrio es que uno se mueva más que el otro). Umbral de ruptura:

| pool | TVL | token limitante | ρ hoy | ρ\* | movimiento relativo que lo abre |
|---|---|---:|---:|---:|---:|
| `0x1eff8af5` | $761.097 | WETH (50%) | 0,9996 | 0,899 | **−22,4%** vs WBTC |
| `0x9866772a` | $615.156 | WETH (40%) | 0,9970 | 0,880 | **−22,0%** vs MKR |
| `0x74a5d106` | $127.237 | WETH (30%) | 0,9421 | 0,862 | **−12,9%** vs `0x0ba45a8b` |
| `0x5a0d8516` | $88.562 | WETH (50%) | 0,9983 | 0,899 | −22,1% |
| `0xbed340a3` | $55.009 | UNI (50%) | 0,9973 | 0,899 | −21,8% |

Un par como MKR/WETH se mueve un 20% relativo en cuestión de semanas. **Estos pools no son inmunes: están a un movimiento de precio de ser el `0x9a16bddf` de mañana**, y nadie los va a parchear. Los 8 pools «no finalizados» del triaje anterior (`finalize()` los activa) son el mismo tipo de riesgo latente.

---

## 7. Flash loans: lo que cambian y lo que no

**No son el vector.** Ya está demostrado en `flashloan_grid.py`: desde un pool *equilibrado* el ataque exige ~10⁶ veces las reservas para un botín del 0,1%, porque la pérdida `(1−f)·D` crece igual que la ganancia. El flash loan **no fabrica** el desequilibrio.

**Sí son el financiador.** Con el desequilibrio ya presente, el capital necesario es pequeño y **se recupera dentro de la misma transacción**:

| pool | capital a mover | fee de flash loan (0,05%) | botín |
|---|---:|---:|---:|
| `0x3c71fad2` | $85.402 | **$43** | $43.682 |
| `0x9a16bddf` | $36.303 | **$18** | $97.639 |
| `0x0e3e2781` | $8.570 | $4 | $17.761 |
| `0x1373e57f` | $9 | — | $29.026 |

Consecuencias concretas:

1. **El capital no es una barrera.** Un solo flash loan cubre el pool más caro de la lista con $43 de coste.
2. **En 4 de los 14 el capital total movido es inferior a $100** (y en 9, la reserva que se compra para empezar vale menos de $100; el capital crece 1,5× por llamada y se recupera al salir).
3. **No deja posición que liquidar**: no hay colateral, no hay exposición mantenida, no hay riesgo de liquidación. Todo ocurre en un bloque, y por eso nadie tiene tiempo de reaccionar.
4. **Lo que el flash loan no resuelve es conseguir las unidades del token barato.** Si tiene mercado fino, el propio slippage de comprarlo es el coste real; si es basura sin liquidez, se compra por nada. En ambos casos el ataque sigue siendo viable — el flash loan sólo traslada el problema de *dinero* a *inventario*, y el inventario de estos tokens vale céntimos.

**El coste que sí domina es el gas.** El tope `MAX_IN_RATIO` obliga a `n` llamadas separadas (~120k gas cada una) más la salida: ~20 llamadas ≈ 2,5M gas ≈ **$115** a 20 gwei y ETH $2.123. Por eso, en la práctica, **nada por debajo de ~$1.000 de botín interesa**, lo que reduce la lista de 14 a **8 pools con beneficio neto claro**. Los 6 restantes son vulnerables y explotables, pero el gas se come el botín.

### 7.1 ¿Y para *abrir* un pool que hoy está por encima del umbral?

La pregunta obvia: si el flash loan no ayuda desde un pool equilibrado, ¿ayuda para **crear** el desequilibrio? Lo he modelado (`open_balanced.py`) con las tres maniobras posibles, todas financiables y reversibles en la misma transacción, sobre pools de 200.000 $ de referencia:

- **swap**: vender B contra el pool para dejar A famélico, y depositar el A que se ha sacado.
- **donate + gulp**: transferir B directamente al pool (invisible para el AMM) y llamar `gulp()` — público, sin permisos — para que el AMM lo contabilice.
- **nada**: control.

Barrido de 8 tamaños de empuje × 10 valores de `n` × 5 tipos de pool (w = 20/30/50/80 %, ρ=1 y ρ al borde del umbral). **El mejor resultado de las 800 combinaciones es una pérdida**, y su tamaño es exactamente el fee del viaje de ida y vuelta:

| escenario | maniobra | mejor neto |
|---|---|---:|
| 50/50 equilibrado | swap 2 % / 10 % / 35 % | −12 / −56 / −169 |
| 50/50 equilibrado | donate 2 % / 35 % | −2.125 / −32.760 |
| `0x74a5d106` (ρ=0,9421, umbral 0,862) | swap 2 % / 10 % / 35 % | −17 / −78 / −233 |
| `0x74a5d106` | donate 2 % / 35 % | −2.968 / −46.636 |
| `0x5a0d8516` (ρ=0,9983, umbral 0,899) | swap 2 % / 10 % / 35 % | −12 / −56 / −169 |

El óptimo es siempre `n = 1` y una pérdida igual a ~2 fees. La razón:

1. **`ρ*` es el punto de beneficio cero por construcción.** Cualquier maniobra que cueste algo para llevar ρ desde arriba del umbral hasta justo debajo arranca exactamente en cero y **resta** su coste. Para ganar hay que pasarse, y pasarse cuesta de forma convexa (slippage) mientras la ganancia crece lineal.
2. **Depositar *repara* el desequilibrio**: `ρ' = 1,5ρ/(1 + 0,5ρ) ≥ ρ`. Desde un pool equilibrado, el bucle se acuña a precio justo o peor — no se puede arrancar.
3. **La donación es pérdida pura**: solo recuperas `f` de ella, y `f → 1` exige precisamente el desequilibrio que intentabas crear.
4. **El mecanismo no lee ningún precio.** `calcSingleInGivenPoolOut` usa balances, pesos y supply: **ρ es una valoración del pool, no una entrada del contrato**. Los precios manipulables cambian lo que *vale* el botín, nunca lo que el contrato te cobra. Y manipular el precio del token que depositas es autocancelable: para comprarlo barato hay que haberlo vendido antes.

Corolario: los 46 «seguros» **no se pueden abrir**. Lo que sí los abre es un movimiento de precio **real** del 13–22 % relativo (§6) — pero eso no es una técnica del atacante, es el mercado, y se resuelve con monitorización, no con un parche.

---

## 8. Qué haría, en este orden

1. **Hoy:** los 8 pools de la tabla A con botín > $1.000 (`setPublicSwap(false)` desde el `controller`, o retirar la liquidez). Son $260.000 y no requieren más análisis.
2. **Esta semana:** medir el precio de los 5 tokens de la tabla B con más TVL (ULU, xAAVEa, COVER_CDS, PCT, MPL) y compararlo con su `p*`. Son $1,02M en juego y es una consulta por token.
3. **Monitorización permanente:** alerta cuando el ratio de precios de los 46 «seguros» se mueva un 10% relativo. Un pool que hoy es inmune es mañana el botín. Esto incluye los 8 no finalizados.
4. **Estructural:** el parche de `security/patches/balancer-v1-hardening.patch`. Mientras `joinswapExternAmountIn` no tenga referencia de valor (oráculo o `MIN_BALANCE` real por token, el `#210` que el equipo dejó en WONT FIX), cada depósito de polvo es una compra de participación a precio regalado.

---

## 9. Límites de este análisis

- `ρ` usa los precios de un instante; no incorpora profundidad de mercado ni slippage de la venta del botín.
- El modelo es homogéneo en dólares (invariante a decimales), lo que es exacto para el efecto `ρ` y aproximado para el redondeo de unidades mínimas.
- El botín de la tabla A es un **techo** (un atacante, sin competencia, con la salida óptima); el de la tabla B es el techo del escenario «token muerto».
- Los balances y precios son los aportados por el usuario; no se han releído on-chain.
- No se modela el gas por pool individualmente, sólo el umbral de ~$115 por 20 llamadas.

---

## 10. Reproducir

```bash
cd security
python3 analyze_live.py          # tabla completa ordenada por botín
python3 analyze_live.py --md     # tablas markdown de este informe
```

La clasificación completa (100 filas) está en la salida del primer comando; este documento reproduce las tablas A y B generadas por `--md`.
