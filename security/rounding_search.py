"""
Search for rounding-driven, *state-independent* value leaks (no dust reserve
needed). If any of these finds a repeatable profit at ordinary balances, it is
an independent critical bug; if not, the dust reserve is confirmed as the
necessary amplifier.
"""
from bmath_sim import *

fee = 3 * 10**14


def profit_join_exit(balances, denorms, pS, lo, hi):
    """joinPool(x) then exitPool(x): can we come out with more of any token?"""
    worst = 0
    for x in range(lo, hi):
        p = Pool([{"sym": "A", "dec": 18, "bal": balances[0], "denorm": denorms[0]},
                  {"sym": "B", "dec": 18, "bal": balances[1], "denorm": denorms[1]}], fee=fee)
        p.pS = pS
        b0 = (p.t["A"]["bal"], p.t["B"]["bal"])
        try:
            p.joinPool(x, {"A": 2**200, "B": 2**200})
        except Revert:
            continue
        try:
            p.exitPool(x, {})
        except Revert:
            continue
        d = (p.t["A"]["bal"] - b0[0], p.t["B"]["bal"] - b0[1])
        worst = min(worst, d[0], d[1])
        if d[0] > 0 or d[1] > 0:
            return (x, d)
    return None


def report():
    print("=" * 78)
    print("S1  joinPool(x) -> exitPool(x) round trip at ordinary balances")
    print("=" * 78)
    cases = [
        ("1e21/1e21 50-50", (10**21, 10**21), (BONE, BONE)),
        ("1e9/3e21 80-20 wBTC-ish", (10**9, 3 * 10**21), (8 * BONE, 2 * BONE)),
        ("1e6/1e24 6dec/18dec", (10**6, 10**24), (BONE, BONE)),
        ("dust A=1000", (1000, 10**21), (BONE, BONE)),
    ]
    for name, bals, dens in cases:
        r = profit_join_exit(bals, dens, INIT_POOL_SUPPLY, 1, 3000)
        print(f"  {name:<28} -> {r if r else 'no profitable cycle for x in [1,3000)'}")

    print()
    print("=" * 78)
    print("S2  swap round trip A->B->A  (fee should make it a loss)")
    print("=" * 78)
    for name, bals, dens in cases:
        p = Pool([{"sym": "A", "dec": 18, "bal": bals[0], "denorm": dens[0]},
                  {"sym": "B", "dec": 18, "bal": bals[1], "denorm": dens[1]}], fee=fee)
        best = 0
        for aI in [10**k for k in range(0, 20)] + [10**9, 10**10]:
            if aI > bmul(p.t["A"]["bal"], MAX_IN_RATIO):
                continue
            try:
                out = p.swapExactAmountIn("A", aI, "B", 0, 2**200)
                back = p.swapExactAmountIn("B", out, "A", 0, 2**200)
            except Revert:
                p = Pool([{"sym": "A", "dec": 18, "bal": bals[0], "denorm": dens[0]},
                          {"sym": "B", "dec": 18, "bal": bals[1], "denorm": dens[1]}], fee=fee)
                continue
            best = max(best, back - aI)
            p = Pool([{"sym": "A", "dec": 18, "bal": bals[0], "denorm": dens[0]},
                      {"sym": "B", "dec": 18, "bal": bals[1], "denorm": dens[1]}], fee=fee)
        print(f"  {name:<28} -> best net = {best:+d} wei (negative = fee wins)")

    print()
    print("=" * 78)
    print("S3  joinswapExternAmountIn -> exitswapPoolAmountIn   /   inverse")
    print("=" * 78)
    for name, bals, dens in cases:
        p = Pool([{"sym": "A", "dec": 18, "bal": bals[0], "denorm": dens[0]},
                  {"sym": "B", "dec": 18, "bal": bals[1], "denorm": dens[1]}], fee=fee)
        best = 0
        for aI in [10**k for k in range(0, 18)]:
            if aI == 0 or aI > bmul(p.t["A"]["bal"], MAX_IN_RATIO):
                continue
            q = Pool([{"sym": "A", "dec": 18, "bal": bals[0], "denorm": dens[0]},
                      {"sym": "B", "dec": 18, "bal": bals[1], "denorm": dens[1]}], fee=fee)
            try:
                pAo = q.joinswapExternAmountIn("A", aI, 0)
                out = q.exitswapPoolAmountIn("A", pAo, 0)
            except Revert:
                continue
            best = max(best, out - aI)
        print(f"  {name:<28} -> best net = {best:+d} wei")

    # and the same starting from dust (where rounding can be relatively big)
    print()
    print("=" * 78)
    print("S4  same, starting from a dust reserve (relative rounding is large)")
    print("=" * 78)
    for dust in (2, 3, 10, 1000, 10**6):
        p = Pool([{"sym": "A", "dec": 18, "bal": dust, "denorm": BONE},
                  {"sym": "B", "dec": 18, "bal": 10**21, "denorm": BONE}], fee=fee)
        gained = []
        for aI in range(1, 200):
            if aI > bmul(dust, MAX_IN_RATIO):
                break
            q = Pool([{"sym": "A", "dec": 18, "bal": dust, "denorm": BONE},
                      {"sym": "B", "dec": 18, "bal": 10**21, "denorm": BONE}], fee=fee)
            try:
                pAo = q.joinswapExternAmountIn("A", aI, 0)
                out = q.exitswapPoolAmountIn("A", pAo, 0)
            except Revert:
                continue
            if out > aI:
                gained.append((aI, pAo / BONE, out))
        print(f"  dust={dust:>8}: {len(gained)} profitable in->out cycles; "
              f"examples {[(a, round(b,4), c) for a,b,c in gained[:3]]}")


if __name__ == "__main__":
    report()
