# Descartados: cuatro falsos positivos de la lista original

Los cuatro pools que figuraban como vulnerables en la primera versión de `README-VULNERABLES-7.md` (que
entonces eran siete) y que **no lo son**. Se conservan aquí como evidencia: si vuelven a aparecer como
candidatos, es que se está midiendo con precio de marca.

| # orig. | pool | por qué se cae | prueba |
|---|---|---|---|
| 2 | `0xf0f8b1ce` | PAR/MIMO 50/50 (v1). El ρ=0,285 es **artefacto de marca**: MIMO no vale su spot | con MIMO a **spot/6**, ρ_PAR = **0,999** |
| 3 | `0x5b1c06c4` | PAR/MIMO 75/25 (v2), mismo caso | con MIMO a **spot/6**, ρ_PAR = **1,000** |
| 6 | `0xa5533a44` | PAR/MIMO 20/80 (v2), mismo caso | con MIMO a **spot/6**, ρ_PAR = **1,000** |
| 4 | `0x30cb8593` | UNI-V2/WETH. Se valoraba el LP de Uni-V2 **a libro** | el LP es black-hole: `burn` revierte; techo real = $83 de WETH |

## El caso de los tres PAR/MIMO

El pool valora PAR a **$6,695** cuando el mercado dice **$1,114**: un **6,01×**. Eso no es un bug del
pool: es la misma cifra que el *haircut* de liquidación de MIMO medido en fork (MIMO se realiza a ~1/6
de su spot). Y el factor que hace desaparecer el desequilibrio es exactamente ése:

```
MIMO a spot/1:  rho_PAR = 0,285   rho_MIMO = 1,715
MIMO a spot/2:  rho_PAR = 0,500   rho_MIMO = 1,500
MIMO a spot/4:  rho_PAR = 0,799   rho_MIMO = 1,201
MIMO a spot/6:  rho_PAR = 0,999   rho_MIMO = 1,001   <-- el haircut medido
```

No es casualidad: **ρ = 1 es, por definición, «el precio marginal del pool coincide con la marca»**. El
pool no estaba desequilibrado; estaba diciendo la verdad sobre MIMO y la marca era la que mentía. Un
pool que cotiza al precio ejecutable **no tiene arbitraje**, por muy «desequilibrado» que lo vea un
scanner que usa spot.

Los tres eran el mismo artefacto con los pesos barajados (50/50, 75/25, 20/80), y el único token del par
que se podía vender era PAR — justo la pata por la que se entra. La «causa» *par desarbitrado* que
figuraba en el documento no era una causa: era una marca mala.

## El caso `0x30cb8593`

El botín de $2.720 venía de valorar 3.799,90 $ de UNI-V2 **a valor contable** y suponer que se podía
vender. El `burn` del LP revierte en fork: no hay salida. El pool entero tiene **$83,55 de WETH** y eso
es todo lo que se puede sacar, con un fee del 3,75 %. El «desequilibrio puro» era real; la
**cobrabilidad** no.

## Regla que sale de aquí

Para que un pool entre en la lista hace falta que **la pata premio se pueda vender**. El escalón que
falta en el escáner:

1. para cada pata, precio al que se puede vender *el importe que habría que vender* contra su mejor par
   (curva de venta, no spot);
2. recalcular `ρ_i = v_i/(w_i·TVL)` con esas marcas;
3. exigir que el precio marginal del pool difiera del realizable **después** de slippage.
