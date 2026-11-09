# Verificación del escaneo nuevo

**Entrada:** las 268 filas que has pasado (25 columnas, con `pause_window_end`).
**Método:** aritmética exacta del contrato, no la etiqueta `risk`. `python3 security/verify_scan.py`.
**Ficheros:** `data/scan_new.tsv` (227 en alcance), `data/scan_new_verdict.csv` (veredicto por pool),
`data/scan_new_oos.txt` (41 fuera de alcance).

---

## 0. Qué es este escaneo

Lo primero, y cambia la lectura de todo: **ninguna de las 268 filas llega a $1.000 de TVL.** La primera
es `0xe044bc87` con $993,59 y la última `0x988f2b03` con $50,75. Esto no es el inventario: es **la cola**
del inventario. Cualquier botín posible aquí está acotado por $1.000, y en la práctica por la pata viva.

| bloque | filas | TVL |
|---|---:|---:|
| v1 `BPool` | 130 | $33.813 |
| v2 `WEIGHTED` | 97 | $20.895 |
| **en alcance** | **227** | **$54.708** |
| v2 otros tipos (`GYROE`, `ELEMENT`, `COMPOSABLE_STABLE`, `LIQUIDITY_BOOTSTRAPPING`, `STABLE`, `FX`, `META_STABLE`, `INVESTMENT`) | 41 | $15.975 |

Los 41 de tipos no ponderados quedan fuera de alcance por la misma razón que en el triaje anterior: el
bug explotado vive en `calcSingleInGivenPoolOut` / `_calcTokenInGivenExactBptOut`; en Stable/GyroE/Linear
la ruta no existe o no es rentable.

**Integridad: 227/227 filas cuadran** (suma de las patas valoradas == `tvl_live_usd`). Los datos están
bien transcritos y el escáner es consistente consigo mismo.

---

## 1. Veredicto

| veredicto | pools | TVL | qué significa |
|---|---:|---:|---|
| **VULNERABLE** (P&L > $100) | **0** | — | ninguno |
| MARGINAL ($0 < P&L ≤ $100) | 2 | $587 | rentables en teoría, **por debajo del gas** |
| SEGURO (P&L < 0) | 96 | $25.991 | equilibrados: atacar cuesta dinero |
| REVISAR (una pata sin precio) | 91 | $17.629 | 84 condicionales + 7 indecidibles |
| **INERTE** | **38** | $10.500 | **no se puede ni entrar** (§2) |

**Cero vulnerables de 227.** Y no por poco: el mejor P&L bruto de todo el escaneo son **$28**.

---

## 2. Los tres que parecían cobrables y no lo son

La aritmética sin filtrar daba tres ganadores:

| pool | P&L bruto | por qué es falso positivo |
|---|---:|---|
| `0x40ef36dd` | +$123,36 | `NOT-FINALIZED`, supply **0** |
| `0x85bc2533` | +$104,79 | `NOT-FINALIZED`, supply **0** |
| `0xb06f073c` | +$102,15 | `NOT-FINALIZED`, supply **0** |

Los tres tienen patas en polvo reales (son pools de 8 tokens donde una pata vale céntimos) y la cuenta
sale positiva — pero **el pool no está finalizado y su supply es cero**, y entonces:

1. `joinswapPoolAmountOut` empieza con `require(_finalized, "ERR_NOT_FINALIZED")` (`BPool.sol:589`).
2. Aunque estuviera finalizado, `calcSingleInGivenPoolOut` hace `poolRatio = bdiv(newPoolSupply, poolSupply)`
   (`BMath.sol:169`) → **división por cero** con supply = 0.

Es decir: **revierte dos veces, por dos motivos independientes.** Un pool con supply 0 y fondos dentro
está permanentemente muerto para todos salvo para su controller, que no puede hacer nada útil tampoco.

**38 de las 130 filas v1 de este escaneo están en ese estado** (36 `NOT-FINALIZED` + 2 `ZERO-SUPPLY`). Eso es el 29 % del bloque v1 y $10.500 de TVL que no se puede tocar. En el triaje
anterior este filtro no estaba explícito y es el que más falsos positivos genera en las colas bajas:
la aritmética te dice «rentable» y el contrato te dice «ni entres».

---

## 3. Los dos que quedan: el gas se los come

| pool | ver | TVL | P&L bruto | por qué no |
|---|---|---:|---:|---|
| `0x6b0d50a9` | v2 | $318 | +$27,98 | 4 patas; `j+exit` ≈ 450k gas ≈ **$19** a 20 gwei ⇒ neto **+$9**, y es el modelo **aproximado** (pata-polvo contra el resto agregado) |
| `0x2fa1a2fd` | v1 | $269 | +$8,04 | 2 patas, 1 join + exit ≈ 230k gas ≈ **$10** ⇒ neto **−$2** |

Ninguno pasa el umbral de $100 que use en el resto del trabajo, y el primero es además el tipo de número
que la crítica de §1 de `REVISION-ANEXO-ES.md` desmonta: está medido a precio de marca.

**El mejor resultado realista de las 227 filas es ~$9.**

---

## 4. Los 84 condicionales: $16.105, y casi todos son tokens muertos

Son los `REVISAR` con exactamente una pata sin precio. Umbral (`u < w_u·ρ*·V/(1−w_u·ρ*)`) y botín si esa
pata está muerta. Los 11 donde puedo contrastar el umbral **por unidad** con un precio plausible:

| pool | token sin precio | umbral | ⇔ precio unitario | plausible | ¿cae? |
|---|---|---:|---:|---|---|
| `0x7699aa38` | COVER_RAI claim | $2.355 | **$0,0233/u** | muerto (Cover, 2021) | **sí, $717** |
| `0x12d165dc` | PIPT | $2.105 | **$0,2703/u** | muerto | **sí, $641** |
| `0xa36c6f85` | COVER_CREAM claim | $18.733 | **$0,6285/u** | muerto | **sí, $591** |
| `0x533f1164` | COVER_BARNBRIDGE claim | $1.844 | **$0,0323/u** | muerto | **sí, $561** |
| `0x790bae3e` | COVER_INVERSE claim | $8.047 | **$0,7315/u** | muerto | **sí, $254** |
| `0xa33a4574` | RPL | $1.287 | **$1,2369/u** | RPL cotiza $2–5 | **no** |
| `0x8eb6c82c` | graviAURA | $148 | **$0,0240/u** | no hay dato fiable | ¿? |
| `0x58ef3aba` | yUSD-SEP20 | $363 | **$6,5618/u** | yUSD ≈ $1,2 | **no** |
| `0xed3d99d8` | sUSD | $659 | **$0,2027/u** | sUSD ≈ $1 | **no** (está 5× por encima) |
| `0xb4297eac` | DED | $685 | **$15,572/u** | meme sin valor | **sí, $468** |
| `0x7b065a77` | VALUE | $122 | **$0,0012/u** | muerto | **sí, $487** |

**Y aquí está el problema práctico, que la aritmética no ve:** para entrar por la pata en polvo hay que
**tener ese token**. Los cinco `COVER_*` y los `yUSD-*`/`PIPT` no cotizan en ningún sitio desde 2021 —
si no los tienes de una airdrop o de un depósito antiguo, no puedes comprarlos. El ataque queda al
alcance de quien ya los tenga, no del primero que pase. Eso convierte «$717 cobrables» en «$717 cobrables
si tienes 101.306 tokens de una claim muerta».

Los `0xea209798`, `0xf86b3afc`, `0xde5921f0`, `0xca151702`, `0x47a06d04`, `0x382dc5b2` y `0x0578292c`
son **indecidibles**: tienen 2 o más patas sin precio y no se cierran con una fórmula.

---

## 5. Conclusión

1. **Ninguna de las 268 filas es cobrable hoy.** 0 vulnerables, y los dos marginales netos son +$9 y −$2.
2. **El 29 % del bloque v1 ni siquiera admite la entrada**: supply 0 / no finalizado. Es el filtro que
   hay que meter en el escáner antes que cualquier otro, porque la aritmética los marca como rentables.
3. Lo único con volumen real es la cola condicional de tokens muertos (~$3.700 en los que he podido
   contrastar), y está gated por **posesión** del token, no por precio.
4. **Este escaneo no cambia el mapa.** Son las colas; el dinero, si queda, está en los pools de TVL
   alto — y allí el problema no es la aritmética sino el precio realizable de la pata premio
   (`REVISION-ANEXO-ES.md` §1).

*Nota de método:* los valores vienen en dólares del propio escáner y están redondeados a 2 decimales en
`scan_new.tsv`; la comprobación 227/227 los valida contra `tvl_live_usd`. Los precios son **precios de
marca**, así que las columnas de P&L son cotas superiores.
