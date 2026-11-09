"""
Profitability screen: for a 2-token pool, how unbalanced must the target token
be (in MARKET VALUE terms, relative to its fair weight share) for
    joinswapExternAmountIn(max)  ->  exitPool(all BPT)
to be profitable?  Exact contract arithmetic, 0.03% fee.

rho = (market value of target reserve) / (fair value implied by its weight)
  rho = 1.0  -> arb-balanced pool (nothing to take)
  rho -> 0   -> target reserve is dust (attack is free)

Output: profit as a fraction of TVL, and the implied USD threshold.
"""
from bmath_sim import *

fee = 3 * 10**14
TVL = 1_000_000.0


def roundtrip(w, rho):
    """returns profit in USD for a pool of $1M TVL where the target token holds
    rho * w * TVL of value."""
    v_t = rho * w * TVL          # value of target reserve
    v_o = TVL - v_t              # value of the other reserve
    if v_t <= 0 or v_o <= 0:
        return None
    px = 1.0                     # target priced at $1/unit, 18 decimals
    bT = int(v_t / px * BONE)
    bO = int(v_o / px * BONE)
    if bT < 4 or bO < 4:
        return None
    p = Pool([{"sym": "T", "dec": 18, "bal": bT, "denorm": int(w * BONE)},
              {"sym": "O", "dec": 18, "bal": bO, "denorm": int((1 - w) * BONE)}],
             fee=fee)
    pS0 = p.pS
    cap = bmul(bT, MAX_IN_RATIO)
    if cap == 0:
        return None
    try:
        pAo = p.joinswapExternAmountIn("T", cap, 0)
    except Revert:
        return None
    if pAo == 0:
        return None
    share = pAo / p.pS
    paid = cap / BONE * px
    poolval = (p.t["T"]["bal"] + p.t["O"]["bal"]) / BONE * px
    got = share * poolval
    return got - paid, share, poolval


print("profit of joinswapExternAmountIn(50% of reserve) + exitPool, as % of TVL")
print("(negative = the AMM's concavity protects the pool)\n")
header = "  rho   " + "".join(f"  w={w:.1f}  " for w in [0.1, 0.2, 0.3, 0.5, 0.8, 0.9])
print(header)
print("  " + "-" * (len(header) - 2))
for rho in [1.0, 0.9, 0.5, 0.2, 0.1, 0.05, 0.02, 0.01, 0.005, 0.001, 1e-4, 1e-5, 1e-6]:
    row = f"  {rho:<7.3g}"
    for w in [0.1, 0.2, 0.3, 0.5, 0.8, 0.9]:
        r = roundtrip(w, rho)
        row += f"{100*r[0]/TVL:>+8.2f}" if r else "     n/a"
    print(row)

print("\nbreak-even rho (below it, the round trip is profitable):")
for w in [0.05, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 0.95]:
    lo, hi = 1e-9, 1.0
    for _ in range(80):
        mid = (lo * hi) ** 0.5
        r = roundtrip(w, mid)
        if r and r[0] > 0:
            lo = mid
        else:
            hi = mid
    print(f"  w={w:<5} rho* = {lo:.4f}   => attackable if target reserve holds less "
          f"than {100*lo:.2f}% of its fair value share")
