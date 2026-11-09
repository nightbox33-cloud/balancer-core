#!/usr/bin/env python3
"""Dossier de los 7 pools vulnerables: rho, traza del ataque paso a paso.

Uso: python3 dossier7.py
"""
import csv
from collections import OrderedDict

from bmath_sim import Pool, Revert, BONE, MAX_IN_RATIO, bmul, bdiv
import v2_weighted as V2
from decimal import Decimal

ONE = 10**18


def load(path="data/dossier7.csv"):
    pools = OrderedDict()
    for r in csv.DictReader(open(path), delimiter="|"):
        p = pools.setdefault(r["pool"], dict(ver=r["ver"], fee=float(r["fee"]),
                                             supply=float(r["supply"]), toks=[]))
        p["toks"].append(dict(sym=r["sym"], w=float(r["w"]) / 100.0,
                              bal=float(r["bal"]), px=float(r["px"])))
    return pools


def rho_table(p):
    tvl = sum(t["bal"] * t["px"] for t in p["toks"])
    for t in p["toks"]:
        t["usd"] = t["bal"] * t["px"]
        t["rho"] = t["usd"] / (t["w"] * tvl) if t["w"] > 0 else 0
    return tvl


def v1_trace(p, step_frac=0.5, max_steps=400):
    """join con cap = step_frac * balance (MAX_IN_RATIO=0.5), exit optimo."""
    toks = p["toks"]
    tvl = sum(t["usd"] for t in toks)
    dust = min(toks, key=lambda t: t["rho"])
    prize = max(toks, key=lambda t: t["rho"])
    # balances en DOLARES (b_i*px). El ataque es homogeneo de grado 1 en b_i,
    # asi que el P&L y la fraccion f son identicos a usar unidades de token.
    pool = Pool([{"sym": t["sym"], "dec": 18, "bal": max(int(t["usd"] * ONE), 4),
                  "denorm": max(int(t["w"] * BONE), 1)} for t in toks],
                fee=int(p["fee"] * BONE))
    pool.pS = max(int(p["supply"] * ONE), 2)
    s0 = pool.pS
    fee = int(p["fee"] * BONE)
    steps, best = [], None
    for n in range(1, max_steps + 1):
        cap = bmul(pool.t[dust["sym"]]["bal"], int(step_frac * BONE))
        if cap < 1:
            break
        try:
            bpt = pool.joinswapExternAmountIn(dust["sym"], cap, 0)
        except Revert:
            break
        steps.append(dict(n=n, amount_in=cap, bpt_out=pool.pS - (steps[-1]["pS"] if steps else s0)
                          if False else bpt, pS=pool.pS))
        mine = pool.pS - s0
        if mine <= 0:
            continue
        # salidas posibles
        pro = sum(pool.t[t["sym"]]["bal"] * mine // pool.pS for t in toks)
        mono, which = 0, None
        from bmath_sim import calcSingleOutGivenPoolIn
        for t in toks:
            try:
                o = calcSingleOutGivenPoolIn(pool.t[t["sym"]]["bal"],
                                             pool.t[t["sym"]]["denorm"], pool.pS,
                                             pool.tW, mine, fee)
            except Revert:
                o = 0
            if o > mono:
                mono, which = o, t["sym"]
        got_raw, mode = (pro, "pro-rata") if pro >= mono else (mono, f"mono:{which}")
        pnl = (got_raw - sum(s["amount_in"] for s in steps)) / ONE
        if best is None or pnl > best["pnl"]:
            best = dict(n=n, pnl=pnl, got=got_raw / ONE, mode=mode,
                        paid=sum(s["amount_in"] for s in steps) / ONE,
                        frac=mine / pool.pS, dust=dust["sym"], prize=prize["sym"])
        if mine >= pool.pS - 1:
            break
    return best, steps


def v2_trace(p):
    toks = p["toks"]
    tvl = sum(t["usd"] for t in toks)
    dust = min(toks, key=lambda t: t["rho"])
    prize = max(toks, key=lambda t: t["rho"])
    best = None
    for frac in ("0.001", "0.005", "0.02", "0.05", "0.1", "0.2", "0.5", "1", "2"):
        fr = Decimal(frac)
        for n in range(1, 7):
            q = V2.V2Weighted(Decimal(str(dust["usd"])), Decimal(str(prize["usd"])),
                              Decimal(str(dust["w"])), Decimal(str(p["fee"])),
                              supply=Decimal(str(p["supply"])) * V2.ONE)
            mine, spent, steps = 0, Decimal(0), []
            ok = True
            for _ in range(n):
                bpt = int(fr * q.supply)
                if bpt < 1:
                    ok = False
                    break
                amt = q.join_single(0, bpt)
                spent += amt
                mine += bpt
                steps.append((amt, bpt))
            if not ok:
                break
            got, exits = Decimal(0), 0
            while mine > 0 and exits < 200:
                chunk = min(mine, int(Decimal("0.3") * q.supply))
                if chunk < 1:
                    break
                try:
                    got += q.exit_single(1, chunk)
                except ValueError:
                    break
                mine -= chunk
                exits += 1
            r = dict(pnl=float((got - spent) / V2.ONE), paid=float(spent / V2.ONE),
                     got=float(got / V2.ONE), n=n, exits=exits, frac=frac,
                     dust=dust["sym"], prize=prize["sym"])
            if best is None or r["pnl"] > best["pnl"]:
                best = r
    return best


def main():
    for addr, p in load().items():
        tvl = rho_table(p)
        print("=" * 78)
        print(f"{addr}  ({p['ver']}, fee {p['fee']*100:.2f}%, supply {p['supply']:,.2f} BPT)")
        print(f"TVL ${tvl:,.2f}")
        print(f"  {'token':<12}{'peso':>7}{'balance':>16}{'precio':>12}{'valor $':>13}{'rho':>8}")
        for t in p["toks"]:
            print(f"  {t['sym']:<12}{t['w']*100:>6.2f}%{t['bal']:>16,.6f}{t['px']:>12,.4f}"
                  f"{t['usd']:>13,.2f}{t['rho']:>8.3f}")
        if p["ver"] == "v1":
            b, steps = v1_trace(p)
            dpx = next(t["px"] for t in p["toks"] if t["sym"] == b["dust"])
            print(f"\n  ATAQUE v1: {b['n']} joins ({b['dust']} -> pool), salida {b['mode']}")
            for s in steps[:min(b["n"], 6)]:
                print(f"    join {s['n']}: ${s['amount_in']/ONE:,.6f}"
                      f" = {s['amount_in']/ONE/dpx:,.6f} {b['dust']}"
                      f"  ->  +{s['bpt_out']/ONE:,.2f} BPT")
            if b["n"] > 6:
                print(f"    ... hasta {b['n']} joins")
            print(f"  pagado ${b['paid']:,.2f} -> cobrado ${b['got']:,.2f}"
                  f"  =  P&L ${b['pnl']:,.2f}  (f={b['frac']*100:.2f}%)")
        else:
            b = v2_trace(p)
            print(f"\n  ATAQUE v2: {b['n']} joins de frac={b['frac']} + {b['exits']} exits"
                  f" ({b['dust']} -> {b['prize']})")
            print(f"  pagado ${b['paid']:,.2f} -> cobrado ${b['got']:,.2f}"
                  f"  =  P&L ${b['pnl']:,.2f}")


if __name__ == "__main__":
    main()
