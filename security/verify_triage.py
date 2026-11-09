#!/usr/bin/env python3
"""Verifica, pool por pool, la etiqueta `risk` del escaner con aritmetica exacta.

Idea: tanto `joinswapPoolAmountOut` (v1) como `_calcTokenInGivenExactBptOut` (v2)
son LINEALES en el balance de la pata en polvo, y `exitPool`/`exitswap` tambien.
Por eso el ataque completo se puede calcular en DOLARES (usd_per_token = v_i)
sin necesitar las unidades: usar balance = v_i con precio 1 da exactamente el
mismo P&L (homogeneidad de grado 1).

Uso: python3 verify_triage.py
"""
import csv
from decimal import Decimal

import analyze_live as A
import v2_weighted as V2
from bmath_sim import MAX_IN_RATIO

GAS_USD = 80.0        # ~7 llamadas en v2 / ~2-20 en v1
MIN_PNL = 100.0       # por debajo de esto no merece la pena ni el gas

SCOPE = {"BPool", "WEIGHTED"}


def load(path):
    rows = []
    for r in csv.DictReader(open(path), delimiter="|"):
        toks = []
        for part in r["wv"].split(";"):
            w, v = part.split(":")
            toks.append((float(w), None if v == "NA" else float(v)))
        rows.append(dict(pool=r["pool"], ver=r["ver"], type=r["type"],
                         fee=float(r["fee"]), supply=float(r["supply"]),
                         tvl=float(r["tvl"]), risk=r["risk"], toks=toks))
    return rows


def rho_of(toks, tvl):
    return [v / (w / 100.0 * tvl) if v is not None else None for w, v in toks]


def v1_attack(toks, fee):
    fee = int(fee * 10**18)          # bmath_sim trabaja en BONE (1e18)
    """Reutiliza el modelo entero exacto de analyze_live (BPool/BMath)."""
    tokens = [dict(name=f"T{i}", w=w / 100.0, px=1e-18,
                   raw=max(int(round(v * 1e18)), 4)) for i, (w, v) in enumerate(toks)]
    return A.attack(tokens, fee)        # px=1e-18 => pnl ya en dolares


def v2_attack(dust_v, big_v, w_dust, fee):
    r = V2.attack(Decimal(str(max(dust_v, 1e-9))), Decimal(str(big_v)),
                  Decimal(str(w_dust)), Decimal(str(fee)))
    return r


def judge(r, toks, ver, fee):
    """Devuelve (veredicto, pnl, detalle)."""
    priced = [(i, w, v) for i, (w, v) in enumerate(toks) if v is not None]
    if not priced:
        return "SIN-DATOS", 0.0, ""
    tvl = sum(v for _, _, v in priced)
    rho = rho_of(toks, tvl)
    if ver == "v1":
        if len(priced) == len(toks):
            b = v1_attack(toks, fee)
            if b:
                tv = sum(v for _, v in toks)
                if b["pnl"] > tv:
                    return "ARTEFACTO", b["pnl"], "P&L > TVL"
                return ("VULNERABLE" if b["pnl"] > MIN_PNL else
                        "MARGINAL" if b["pnl"] > 0 else "SEGURO",
                        b["pnl"], f"n={b['n']} salida={b['exit_mode']} "
                                  f"f={b['frac']*100:.1f}%")
        return "REVISAR", 0.0, "pata sin precio"
    # v2
    if len(toks) == 2:
        (w0, v0), (w1, v1_) = toks
        if v0 is None or v1_ is None:
            return "REVISAR", 0.0, "pata sin precio"
        if rho[0] <= rho[1]:
            r = v2_attack(v0, v1_, w0 / 100.0, fee)
        else:
            r = v2_attack(v1_, v0, w1 / 100.0, fee)
        return ("VULNERABLE" if r["pnl"] > MIN_PNL else
                "MARGINAL" if r["pnl"] > 0 else "SEGURO",
                r["pnl"], f"{r['joins']}j+{r['exits']}s f={r['f']*100:.1f}%")
    return "REVISAR", 0.0, f"n={len(toks)}: sin modelo exacto"


def unpriced_scan(row):
    """Una pata sin precio. Solo es valido el ataque que ENTRA por ella (polvo)
    y SALE por una pata con precio (vendible). El umbral sale en forma cerrada:

        rho_u < rho*  <=>  u < w_u*rho*V/(1 - w_u*rho*)

    con u = valor de la pata sin precio y V = valor de las patas con precio.
    Para v1 rho* depende del peso (lo imponia MAX_IN_RATIO); para v2 rho* = 1.
    """
    idx = [i for i, (_, v) in enumerate(row["toks"]) if v is None]
    if len(idx) != 1:
        return None
    i = idx[0]
    w_u = row["toks"][i][0] / 100.0
    V = sum(v for j, (_, v) in enumerate(row["toks"]) if v is not None)
    rs = 1.0 if row["ver"] == "v2" else A.rho_star(w_u)
    den = 1 - w_u * rs
    if den <= 0 or V <= 0:
        return None
    w_p = 1 - w_u
    if w_p <= 0:
        return None
    u_star = min(w_u * rs * V / den, w_u * V / w_p)   # nunca mas alla del cruce
    toks = [(w, u_star / 1e4 if j == i else v)
            for j, (w, v) in enumerate(row["toks"])]
    dead = judge(row, toks, row["ver"], row["fee"])[1]
    return (u_star, dead)


def main():
    rows = load("data/triage_v1.csv") + load("data/triage_v2.csv")
    print(f"{len(rows)} pools con datos\n")
    bad = 0
    for r in rows:
        if all(v is not None for _, v in r["toks"]):
            s = sum(v for _, v in r["toks"])
            if r["tvl"] > 0 and abs(s - r["tvl"]) / r["tvl"] > 0.01:
                print(f"  !! {r['pool'][:10]} suma v={s:,.2f} != tvl={r['tvl']:,.2f}")
                bad += 1
    print(f"chequeo de integridad: {len(rows)-bad}/{len(rows)} filas cuadran (suma usd_per_token == tvl_live)\n")

    res = []
    for r in rows:
        v, pnl, det = judge(r, r["toks"], r["ver"], r["fee"])
        res.append((r, v, pnl, det))

    from collections import Counter
    print("== distribucion de veredictos vs etiqueta del escaner ==")
    c = Counter((r["risk"], v) for r, v, _, _ in res)
    for (risk, v), k in sorted(c.items()):
        print(f"  {risk:<32} -> {v:<12} {k}")
    print()

    print("== VULNERABLES (P&L > $100) ==")
    vul = sorted([x for x in res if x[1] == "VULNERABLE"], key=lambda x: -x[2])
    for r, v, pnl, det in vul:
        print(f"  {r['pool']} {r['ver']:<3} {r['tvl']:>12,.0f}  +${pnl:>10,.0f}  {det}")
    print(f"  total {len(vul)} pools, botin ${sum(x[2] for x in vul):,.0f}\n")

    print("== MARGINALES (0 < P&L <= $100) ==")
    for r, v, pnl, det in sorted([x for x in res if x[1] == "MARGINAL"],
                                 key=lambda x: -x[2]):
        print(f"  {r['pool']} {r['ver']:<3} {r['tvl']:>12,.0f}  +${pnl:>8,.2f}  {det}")

    print("\n== UNA PATA SIN PRECIO: umbral de valor ==")
    cond = []
    for r, v, pnl, det in res:
        if v != "REVISAR":
            continue
        sc = unpriced_scan(r)
        if sc is None:
            print(f"  {r['pool']} {r['ver']:<3} {r['tvl']:>10,.0f}  varias patas sin precio")
            continue
        umax, dead = sc
        cond.append((r, umax, dead))
    cond.sort(key=lambda x: -x[2])
    for r, umax, dead in cond:
        live = r["tvl"]
        tag = "DRENA" if umax > 0 else "seguro"
        print(f"  {r['pool']} {r['ver']:<3} pata_viva ${live:>10,.0f}  "
              f"{tag:<6} si la otra < ${umax:>12,.0f}   botin ${dead:>10,.0f}")
    cc = [x for x in cond if x[1] > 0]
    print(f"  {len(cc)} pools condicionalmente vulnerables: pata viva ${sum(x[0]['tvl'] for x in cc):,.0f}, "
          f"botin maximo ${sum(x[2] for x in cc):,.0f}")

    print("\n== etiquetados EXPOSED pero SEGUROS (P&L < 0) ==")
    seg = [x for x in res if x[1] == "SEGURO" and "EXPOSED" in x[0]["risk"]]
    print(f"  {len(seg)} de {sum(1 for x in res if 'EXPOSED' in x[0]['risk'])}")
    for r, v, pnl, det in sorted(seg, key=lambda x: x[2])[:8]:
        print(f"  {r['pool']} {r['ver']:<3} {r['tvl']:>12,.0f}  {pnl:>12,.0f}  {det}")


if __name__ == "__main__":
    main()
