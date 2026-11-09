# Los 61 pools condicionalmente vulnerables

No son vulnerables con los datos de hoy: les falta el precio de **una** pata. Lo serán si esa pata vale menos que el **umbral**, porque entonces entra a precio de polvo y se drena la pata viva.

Umbral en forma cerrada (`unpriced_scan`), con `u` = valor de la pata sin precio, `V` = valor de las patas con precio, `w_u` su peso y `ρ*` el umbral por peso:

```
ρ_u = u/(w_u·(V+u)) < ρ*   <=>   u < w_u·ρ*·V / (1 − w_u·ρ*)
```

**61 pools · pata viva $1,460,055 · botín máximo $974,855**

| # | pool | ver | pata viva | umbral (la otra debe valer menos de) | ⇔ precio unitario | botín si muere |
|---|---|---|---:|---:|---:|---:|
| 1 | `0xe00770cb` | v1 | $715,351 | $30,544 | ULU < **$510.3468** | $244,643 |
| 2 | `0x33812e98` | v1 | $141,652 | $115,640 | xAAVEa < **$1.6074** | $139,086 |
| 3 | `0x1bccaac0` | v2 | $108,568 | $108,568 | — | $106,354 |
| 4 | `0x39eb5581` | v2 | $96,040 | $384,162 | — | $95,770 |
| 5 | `0x48c1d1d4` | v1 | $75,171 | $61,367 | COVER_CDS < **$0.8140** | $73,812 |
| 6 | `0x9232a548` | v2 | $58,406 | $233,625 | — | $58,238 |
| 7 | `0xeb85b2e1` | v1 | $50,637 | $41,339 | PCT < **$0.2052** | $49,724 |
| 8 | `0xc1b10e53` | v1 | $35,283 | $28,804 | MPL < **$0.2967** | $34,644 |
| 9 | `0xa7956005` | v1 | $24,152 | $46,123 | DEFI+L < **$0.8859** | $24,045 |
| 10 | `0xc786ab47` | v1 | $22,356 | $18,251 | COVER_RULER < **$0.8140** | $21,952 |
| 11 | `0xae95d319` | v1 | $14,872 | $12,141 | BHSc$ < **$1.0004** | $14,599 |
| 12 | `0x5122e01d` | v2 | $14,250 | $56,999 | — | $14,209 |
| 13 | `0x100a6a95` | v2 | $7,899 | $7,899 | — | $7,738 |
| 14 | `0xd9346ab5` | v1 | $7,300 | $5,959 | xAAVEb < **$1.2751** | $7,167 |
| 15 | `0x8e9690e1` | v2 | $6,689 | $6,689 | — | $6,551 |
| 16 | `0x7c9cf12d` | v2 | $6,431 | $6,431 | — | $6,299 |
| 17 | `0xa1ec308f` | v1 | $6,423 | $579 | AXIAv3 < **$0.0006** | $5,008 |
| 18 | `0x2dd7255b` | v1 | $5,036 | $4,111 | uUSDrBTC-DEC < **$2.4742** | $4,946 |
| 19 | `0x79c44cd4` | v1 | $4,397 | $14,412 | MCX < **$0.0001** | $4,386 |
| 20 | `0x9e030b67` | v2 | $4,278 | $4,278 | — | $4,190 |
| 21 | `0xf658132f` | v1 | $3,183 | $2,598 | WFIL < **$2.4799** | $3,125 |
| 22 | `0xf22c9bd7` | v1 | $2,845 | $2,323 | WZEC < **$108.8743** | $2,794 |
| 23 | `0x9f2b223d` | v2 | $2,826 | $2,826 | — | $2,767 |
| 24 | `0x0d88b553` | v1 | $2,714 | $2,215 | ALBT < **$0.0000** | $2,664 |
| 25 | `0x8ca1b17c` | v1 | $2,652 | $2,165 | VTT < **$0.0035** | $2,604 |
| 26 | `0x5277a42e` | v1 | $2,501 | $2,042 | FRY < **$0.0001** | $2,447 |
| 27 | `0x60b4601c` | v2 | $2,220 | $2,220 | — | $2,174 |
| 28 | `0x1e63fd8f` | v1 | $2,162 | $2,651 | IND < **$0.0008** | $2,143 |
| 29 | `0x96248f63` | v1 | $2,123 | $67,306 | COVER_ORIGIN < **$0.7184** | $2,122 |
| 30 | `0x53e67283` | v1 | $1,992 | $63,128 | COVER_RAI < **$0.6503** | $1,990 |
| 31 | `0xe3f9cf7d` | v1 | $1,872 | $1,528 | xSNXa < **$0.0000** | $1,838 |
| 32 | `0xb70c25d9` | v2 | $1,716 | $1,716 | — | $1,681 |
| 33 | `0xfff2a5f8` | v1 | $1,670 | $1,363 | COVER_BADGERDAO < **$0.8140** | $1,640 |
| 34 | `0x0aaba3d6` | v2 | $1,662 | $1,662 | — | $1,627 |
| 35 | `0x4e257946` | v1 | $1,442 | $1,178 | O-OCEAN-MAR22 < **$1.2701** | $1,416 |
| 36 | `0x554659b6` | v1 | $1,398 | $1,141 | — | $1,367 |
| 37 | `0x7173b184` | v2 | $1,391 | $1,391 | — | $1,362 |
| 38 | `0x7ae275fa` | v1 | $1,374 | $1,121 | — | $1,349 |
| 39 | `0xfab94461` | v1 | $1,410 | $574 | XAUt < **$574.1344** | $1,317 |
| 40 | `0xde7e006a` | v1 | $1,312 | $1,071 | MCX < **$0.0001** | $1,288 |
| 41 | `0xfb46bc8f` | v2 | $1,203 | $4,812 | — | $1,200 |
| 42 | `0x62e57e37` | v2 | $1,202 | $1,202 | — | $1,178 |
| 43 | `0x0ffc0ac3` | v1 | $1,121 | $915 | YFL < **$2.3889** | $1,100 |
| 44 | `0x08775ccb` | v2 | $1,115 | $1,115 | — | $1,092 |
| 45 | `0xf8cc687f` | v1 | $1,110 | $907 | YD-BTC-SEPT < **$1.0068** | $1,090 |
| 46 | `0xcca17fe7` | v1 | $1,106 | $902 | YD-ETH-SEPT < **$0.9979** | $1,086 |
| 47 | `0x2d6e3515` | v2 | $621 | $621 | — | $608 |
| 48 | `0x759fabc5` | v2 | $602 | $2,409 | — | $601 |
| 49 | `0x87165b65` | v2 | $549 | $2,195 | — | $547 |
| 50 | `0x1f187fa8` | v1 | $1,516 | $65 | ULU < **$0.0293** | $518 |
| 51 | `0xea395819` | v2 | $454 | $1,362 | — | $452 |
| 52 | `0x702605f4` | v2 | $409 | $1,638 | — | $408 |
| 53 | `0x2d344a84` | v2 | $380 | $1,518 | — | $379 |
| 54 | `0xd8721e92` | v2 | $344 | $1,376 | — | $343 |
| 55 | `0x82b8c7c6` | v2 | $340 | $1,359 | — | $339 |
| 56 | `0x844ba71d` | v2 | $306 | $2,753 | — | $305 |
| 57 | `0xf3a605da` | v2 | $252 | $2,271 | — | $252 |
| 58 | `0x27c9f71c` | v2 | $214 | $855 | — | $213 |
| 59 | `0x80a8ea2f` | v2 | $43 | $2,091 | — | $43 |
| 60 | `0xb986fd52` | v2 | $22 | $89 | — | $22 |
| 61 | `0x20faceca` | v2 | $1,493 | $213 | — | $0 |

## Indecidibles: más de una pata sin precio

No se pueden cerrar ni con la fórmula: hacen falta dos precios a la vez.

| pool | ver | pata viva |
|---|---|---:|
| `0x6b74fb4e4b3b177b8e95ba9fa4c3a3121d22fbfb` | v1 | $10,356 |
| `0x61d5dc44849c9c87b0856a2a311536205c96c7fd` | v2 | $11,202 |
| `0x4e1325ff075a387e3d337f5f12638d6d72b12780` | v2 | $9,230 |
| `0xc45d42f801105e861e86658648e3678ad7aa70f9` | v2 | $7,879 |

## Cómo se leen los umbrales

- Umbral **alto** = el pool es vulnerable salvo que el token valga mucho: cuanto más alto, más probable que el ataque funcione.
- Umbral igual al **100 % de la pata viva** ⇒ el pool está en el cruce: atacable con casi cualquier precio del token sin precio.
- Umbral **bajo** ⇒ sólo cae si el token está realmente muerto.
- `—` en la columna de símbolo = esa fila no está en `pools_live.csv` (la lista del escáner sólo
  guarda 100 pools con metadatos); el umbral en dólares sí es exacto en todas.
