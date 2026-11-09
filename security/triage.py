"""
Triage of the Balancer V1 pool inventory.

MODE 1 (inventory): applies the eliminations that ARE decidable from the scanner
        columns (finalized / totalSupply / n_tokens) and ranks the rest by payoff.
MODE 2 (screen):    the real verdict. Needs, per pool, the funded tokens with
        (balance_raw, decimals, denorm, price_usd); computes

            rho_i = value_i / (w_i * TVL)          w_i = denorm_i / totalWeight

        and flags the pool when some rho_i < rho*(w_i), i.e. when a single-sided
        join + exitPool on that token is profitable.  Thresholds below come from
        screen.py (exact contract arithmetic, 0.03% fee).

usage:
    python3 triage.py inventory data/pools.tsv
    python3 triage.py screen data/tokens.csv
        tokens.csv: pool,token,symbol,balance_raw,decimals,denorm,price_usd
"""
import sys
import csv
from bmath_sim import BONE, Pool, Revert, bmul, MAX_IN_RATIO, INIT_POOL_SUPPLY

# rho* per target weight, computed by screen.py (break-even of
# joinswapExternAmountIn(50% of reserve) -> exitPool)
RHO_STAR = {0.05: 0.8190, 0.10: 0.8274, 0.20: 0.8445, 0.30: 0.8622, 0.40: 0.8803,
            0.50: 0.8989, 0.60: 0.9180, 0.70: 0.9376, 0.80: 0.9578, 0.90: 0.9786,
            0.95: 0.9892}


def rho_star(w):
    ks = sorted(RHO_STAR)
    if w <= ks[0]:
        return RHO_STAR[ks[0]]
    if w >= ks[-1]:
        return RHO_STAR[ks[-1]]
    for a, b in zip(ks, ks[1:]):
        if a <= w <= b:
            return RHO_STAR[a] + (RHO_STAR[b] - RHO_STAR[a]) * (w - a) / (b - a)


# --------------------------------------------------------------- inventory
def inventory(path):
    rows = []
    with open(path) as f:
        for line in f:
            c = line.rstrip("\n").split("\t")
            if len(c) < 11:
                continue
            rows.append(dict(risk=c[0], tvl=float(c[1]), code=int(c[2]),
                             joinswap=c[3] == "True", fin=c[4] == "True",
                             pub=c[5] == "True", supply=int(c[6]),
                             ntok=int(c[8]), pool=c[9], tag=c[10]))

    def cat(r):
        if not r["fin"]:
            return "A_eliminado_no_finalizado"
        if r["supply"] == 0:
            return "B_eliminado_supply_cero"
        if r["ntok"] < 2:
            return "C_eliminado_un_solo_token"
        return "D_candidato"

    for r in rows:
        r["cat"] = cat(r)
    by = {}
    for r in rows:
        by.setdefault(r["cat"], []).append(r)

    print(f"filas: {len(rows)}   codesize distinto: {sorted({r['code'] for r in rows})}\n")
    for k in sorted(by):
        v = by[k]
        print(f"{k:<32} {len(v):>3} pools   ${sum(x['tvl'] for x in v):>14,.0f} TVL")
    print()

    elim = by.get("A_eliminado_no_finalizado", []) + by.get("B_eliminado_supply_cero", []) \
        + by.get("C_eliminado_un_solo_token", [])
    print("ELIMINADOS (no explotables hoy, por el propio codigo de BPool):")
    for r in elim:
        why = {"A_eliminado_no_finalizado": "joinswap exige _finalized (:556/:590)",
               "B_eliminado_supply_cero": "bdiv(x,0) revierte: join/exit muertos",
               "C_eliminado_un_solo_token": "finalize exige >=2 tokens; sin 2a reserva no hay botin"}[r["cat"]]
        print(f"  {r['pool']}  ${r['tvl']:>10,.0f}  ntok={r['ntok']}  supply={r['supply']}  <- {why}")

    cand = sorted(by.get("D_candidato", []), key=lambda x: -x["tvl"])
    solo = [r for r in cand if r["supply"] <= INIT_POOL_SUPPLY]
    multi = [r for r in cand if r["supply"] > INIT_POOL_SUPPLY]
    print(f"\n   de los {len(cand)} candidatos:")
    print(f"     supply <= 100e18 (un solo LP: el creador; no hay fondos de terceros) : {len(solo):>3} pools, ${sum(r['tvl'] for r in solo):>12,.0f}")
    print(f"     supply >  100e18 (hay LPs reales a los que diluir)                   : {len(multi):>3} pools, ${sum(r['tvl'] for r in multi):>12,.0f}")
    print(f"\nCANDIDATOS CON LPs DE TERCEROS ({len(multi)}), por botin potencial:")
    print(f"  {'#':>3} {'pool':<44} {'TVL':>12} {'ntok':>5} {'supply(BPT)':>20} {'nota'}")
    for i, r in enumerate(multi[:25], 1):
        note = ""
        if r["supply"] < 10**16:
            note = "supply < 0.01 BPT: estado anomalo (casi totalmente salido)"
        if r["ntok"] >= 3:
            note = (note + "; " if note else "") + f"{r['ntok']} tokens: mas superficie de token muerto"
        print(f"  {i:>3} {r['pool']:<44} {r['tvl']:>12,.0f} {r['ntok']:>5} "
              f"{r['supply']/1e18:>20,.8f} {note}")
    return rows


# --------------------------------------------------------------- screen
def screen(path):
    pools = {}
    with open(path) as f:
        for r in csv.DictReader(f):
            pools.setdefault(r["pool"], []).append(dict(
                token=r["token"], sym=r.get("symbol", "?"),
                bal=int(r["balance_raw"]), dec=int(r["decimals"]),
                denorm=int(float(r["denorm"]) * BONE) if float(r["denorm"]) <= 50
                else int(float(r["denorm"])),
                px=float(r["price_usd"])))
    print(f"{'pool':<44} {'min rho':>8} {'token':>10} {'botin est.':>12} {'veredicto'}")
    for pool, toks in pools.items():
        tW = sum(t["denorm"] for t in toks)
        tvl = sum(t["bal"] / 10**t["dec"] * t["px"] for t in toks)
        if tvl <= 0 or tW == 0:
            print(f"{pool:<44} {'n/a':>8} {'':>10} {'':>12} sin precio / sin reservas")
            continue
        worst = None
        for t in toks:
            if t["bal"] == 0:
                continue
            w = t["denorm"] / tW
            val = t["bal"] / 10**t["dec"] * t["px"]
            rho = val / (w * tvl)
            if worst is None or rho < worst[0]:
                worst = (rho, t, w)
        rho, t, w = worst
        rs = rho_star(w)
        # profit estimate: single-sided join of 50% of the reserve, then exit
        try:
            p = Pool([{"sym": "T", "dec": t["dec"], "bal": t["bal"], "denorm": int(w * BONE)},
                      {"sym": "O", "dec": 18,
                       "bal": max(int((tvl - t["bal"] / 10**t["dec"] * t["px"]) * BONE), 10**6),
                       "denorm": int((1 - w) * BONE)}], fee=3 * 10**14)
            pAo = p.joinswapExternAmountIn("T", max(bmul(t["bal"], MAX_IN_RATIO), 1), 0)
            share = pAo / p.pS
            prof = share * (tvl + (t["bal"] / 10**t["dec"] * t["px"]) * 0.5) \
                - 0.5 * (t["bal"] / 10**t["dec"] * t["px"])
        except Revert:
            prof = 0.0
        verdict = "VULNERABLE" if rho < rs else "ok"
        print(f"{pool:<44} {rho:>8.4f} {t['sym']:>10} {prof:>12,.0f} {verdict}  (rho*={rs:.3f})")


if __name__ == "__main__":
    if sys.argv[1] == "inventory":
        inventory(sys.argv[2])
    else:
        screen(sys.argv[2])
