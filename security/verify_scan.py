#!/usr/bin/env python3
"""Verifica el escaneo nuevo (data/scan_new.tsv) con la aritmetica exacta del contrato.

Formato de scan_new.tsv:  pool|ver|fee|tvl|w1,w2,..|v1,v2,..
  - w en % (los del escaner, sin normalizar)
  - v en dolares, NA si el escaner no tiene precio

Uso: python3 verify_scan.py     (cwd = security/)
"""
import csv

import analyze_live as A
import v2_weighted as V2
from verify_triage import judge, rho_of

GAS_V1 = 80.0      # 2-20 llamadas + exit
GAS_V2 = 45.0      # join + exit (2-7 llamadas)
MIN_PNL = 100.0


def load(path="data/scan_new.tsv"):
    rows = []
    for line in open(path):
        line = line.strip()
        if not line:
            continue
        pool, ver, fee, tvl, ws, vs = line.split("|")
        w = [float(x) for x in ws.split(",")]
        v = [None if x == "NA" else float(x) for x in vs.split(",")]
        assert len(w) == len(v), pool
        rows.append(dict(pool=pool, ver=ver, fee=float(fee), tvl=float(tvl),
                         toks=list(zip(w, v))))
    return rows


INERT = {l.strip() for l in open("data/scan_new_inert.txt") if l.strip()}


def judge2(r):
    """judge() + modelo para v2 con mas de 2 patas."""
    v = judge(r, r["toks"], r["ver"], r["fee"])
    if v[0] != "REVISAR" or r["ver"] != "v2" or len(r["toks"]) <= 2:
        return v
    priced = [(w, x) for w, x in r["toks"] if x is not None]
    if len(priced) != len(r["toks"]):
        return v
    tvl = sum(x for _, x in priced)
    rho = rho_of(r["toks"], tvl)
    i_min = min(range(len(rho)), key=lambda i: rho[i])
    v_dust = r["toks"][i_min][1]
    v_big = tvl - v_dust
    w_dust = r["toks"][i_min][0] / 100.0
    res = V2.attack(v_dust, v_big, w_dust, r["fee"])
    pnl = res["pnl"]
    return ("VULNERABLE" if pnl > MIN_PNL else
            "MARGINAL" if pnl > 0 else "SEGURO",
            pnl, f"~{res['joins']}j+{res['exits']}s f={res['f']*100:.1f}% (n={len(r['toks'])}, aprox)")


def cond_scan(r):
    """Umbral en forma cerrada + botin si la pata muere (con red de seguridad)."""
    toks = r["toks"]
    idx = [i for i, (_, v) in enumerate(toks) if v is None]
    if len(idx) != 1:
        return None
    i = idx[0]
    w_u = toks[i][0] / 100.0
    V = sum(v for _, v in toks if v is not None)
    if V <= 0 or w_u >= 1:
        return None
    rs = 1.0 if r["ver"] == "v2" else A.rho_star(w_u)
    den = 1 - w_u * rs
    if den <= 0:
        return None
    u_star = min(w_u * rs * V / den, w_u * V / (1 - w_u))
    toks2 = [(w, u_star / 1e4 if j == i else v) for j, (w, v) in enumerate(toks)]
    try:
        dead = judge2(dict(r, toks=toks2))[1]
    except Exception:
        dead = 0.0
    return (u_star, dead)


def main():
    rows = load()
    bad = []
    for r in rows:
        s = sum(x for _, x in r["toks"] if x is not None)
        if abs(s - r["tvl"]) > max(0.5, 0.005 * r["tvl"]):
            bad.append((r["pool"], s, r["tvl"]))
    print(f"{len(rows)} pools · integridad: {len(rows)-len(bad)}/{len(rows)} "
          f"cuadran (suma de patas == tvl_live)")
    for p, s, t in bad:
        print(f"   !! {p} suma {s:,.2f} != tvl {t:,.2f}")

    res = []
    for r in rows:
        v, pnl, det = judge2(r)
        if r["pool"][:10] in INERT:          # supply 0 o no finalizado: el join revierte
            v, det = "INERTE", "ERR_NOT_FINALIZED / supply=0"
        if v == "MARGINAL" and pnl <= 1.0:      # ruido de redondeo, no rentabilidad
            v = "SEGURO"
        res.append((r, v, pnl, det))

    from collections import Counter
    c = Counter(v for _, v, _, _ in res)
    print("\n== veredicto ==")
    for k, n in c.most_common():
        tot = sum(r["tvl"] for r, v, _, _ in res if v == k)
        print(f"  {k:<12} {n:>3} pools  TVL ${tot:>9,.0f}")

    vul = sorted([x for x in res if x[1] in ("VULNERABLE", "MARGINAL")],
                 key=lambda x: -x[2])
    print("\n== con P&L > 0 (aritmetica a precio de marca) ==")
    for r, v, pnl, det in vul:
        net = pnl - (GAS_V1 if r["ver"] == "v1" else GAS_V2)
        print(f"  {r['pool']} {r['ver']} TVL ${r['tvl']:>7,.0f}  +${pnl:>7,.2f}  "
              f"neto tras gas ${net:>7,.2f}  {det}")
    if vul:
        print(f"  total P&L ${sum(x[2] for x in vul):,.2f}")
    print()

    cond = []
    for r, v, pnl, det in res:
        if v != "REVISAR":
            continue
        sc = cond_scan(r)
        if sc is None:
            continue
        umax, dead = sc
        cond.append((r, umax, dead))
    cond.sort(key=lambda x: -x[2])
    print("== condicionales (pata sin precio) ==")
    for r, umax, dead in cond[:25]:
        print(f"  {r['pool']} {r['ver']} viva ${r['tvl']:>7,.0f}  "
              f"cae si la otra < ${umax:>8,.0f}   botin ${dead:>7,.0f}")
    print(f"  ... {len(cond)} en total, botin maximo ${sum(x[2] for x in cond):,.0f}")

    indec = [r for r, v, _, _ in res if v == "REVISAR" and cond_scan(r) is None]
    print(f"\n== indecidibles (2+ patas sin precio): {len(indec)} ==")
    for r in indec:
        print(f"  {r['pool']} {r['ver']} TVL ${r['tvl']:,.2f}")

    # volcado para el informe
    with open("data/scan_new_verdict.csv", "w") as f:
        f.write("pool|ver|tvl|veredicto|pnl|detalle\n")
        for r, v, pnl, det in sorted(res, key=lambda x: -x[0]["tvl"]):
            f.write(f"{r['pool']}|{r['ver']}|{r['tvl']}|{v}|{pnl:.2f}|{det}\n")


if __name__ == "__main__":
    main()
