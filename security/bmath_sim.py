"""
Exact integer replica of Balancer V1 contracts/BNum.sol + contracts/BMath.sol
plus a faithful model of the state-changing entrypoints of contracts/BPool.sol.

Goal: reproduce the real Solidity arithmetic (including the half-up rounding of
bmul/bdiv and the 1e8 precision floor of bpowApprox) so that numerical claims in
the security report are reproducible, not hand-waved.

Every function mirrors the Solidity require()s so a "revert" is observable.
"""

BONE = 10**18
MIN_BPOW_BASE = 1
MAX_BPOW_BASE = 2 * BONE - 1
BPOW_PRECISION = BONE // 10**10
UINT_MAX = 2**256 - 1

# BConst
MIN_FEE = BONE // 10**6
MAX_FEE = BONE // 10
MIN_WEIGHT = BONE
MAX_WEIGHT = BONE * 50
MAX_TOTAL_WEIGHT = BONE * 50
MIN_BALANCE = BONE // 10**12
INIT_POOL_SUPPLY = BONE * 100
MAX_IN_RATIO = BONE // 2
MAX_OUT_RATIO = (BONE // 3) + 1


class Revert(Exception):
    pass


def _u(x):
    if x < 0 or x > UINT_MAX:
        raise Revert("uint256 overflow")
    return x


def btoi(a):
    return a // BONE


def bfloor(a):
    return btoi(a) * BONE


def badd(a, b):
    return _u(a + b)


def bsub(a, b):
    if a < b:
        raise Revert("ERR_SUB_UNDERFLOW")
    return a - b


def bmul(a, b):
    c0 = _u(a * b)
    if not (a == 0 or c0 // a == b):
        raise Revert("ERR_MUL_OVERFLOW")
    c1 = _u(c0 + BONE // 2)
    return c1 // BONE


def bdiv(a, b):
    if b == 0:
        raise Revert("ERR_DIV_ZERO")
    c0 = _u(a * BONE)
    if not (a == 0 or c0 // a == BONE):
        raise Revert("ERR_DIV_INTERNAL")
    c1 = _u(c0 + b // 2)
    return c1 // b


def bpowi(a, n):
    z = a if n % 2 != 0 else BONE
    n //= 2
    while n != 0:
        a = bmul(a, a)
        if n % 2 != 0:
            z = bmul(z, a)
        n //= 2
    return z


def bpowApprox(base, exp, precision):
    a = exp
    x, xneg = bsubSign(base, BONE)
    term = BONE
    s = term
    negative = False
    i = 1
    while term >= precision:
        bigK = _u(i * BONE)
        c, cneg = bsubSign(a, bsub(bigK, BONE))
        term = bmul(term, bmul(c, x))
        term = bdiv(term, bigK)
        if term == 0:
            break
        if xneg:
            negative = not negative
        if cneg:
            negative = not negative
        if negative:
            s = bsub(s, term)
        else:
            s = badd(s, term)
        i += 1
        if i > 512:  # safety: never hit in practice
            raise Revert("bpowApprox divergence")
    return s


def bsubSign(a, b):
    if a >= b:
        return (a - b, False)
    return (b - a, True)


def bpow(base, exp):
    if base < MIN_BPOW_BASE:
        raise Revert("ERR_BPOW_BASE_TOO_LOW")
    if base > MAX_BPOW_BASE:
        raise Revert("ERR_BPOW_BASE_TOO_HIGH")
    whole = bfloor(exp)
    remain = bsub(exp, whole)
    wholePow = bpowi(base, btoi(whole))
    if remain == 0:
        return wholePow
    partial = bpowApprox(base, remain, BPOW_PRECISION)
    return bmul(wholePow, partial)


# ----------------------------- BMath -----------------------------

def calcSpotPrice(bI, wI, bO, wO, sF):
    numer = bdiv(bI, wI)
    denom = bdiv(bO, wO)
    ratio = bdiv(numer, denom)
    scale = bdiv(BONE, bsub(BONE, sF))
    return bmul(ratio, scale)


def calcOutGivenIn(bI, wI, bO, wO, aI, sF):
    weightRatio = bdiv(wI, wO)
    adjustedIn = bmul(aI, bsub(BONE, sF))
    y = bdiv(bI, badd(bI, adjustedIn))
    foo = bpow(y, weightRatio)
    bar = bsub(BONE, foo)
    return bmul(bO, bar)


def calcInGivenOut(bI, wI, bO, wO, aO, sF):
    weightRatio = bdiv(wO, wI)
    diff = bsub(bO, aO)
    y = bdiv(bO, diff)
    foo = bpow(y, weightRatio)
    foo = bsub(foo, BONE)
    fee = bsub(BONE, sF)
    return bdiv(bmul(bI, foo), fee)


def calcPoolOutGivenSingleIn(bI, wI, pS, tW, aI, sF):
    norm = bdiv(wI, tW)
    zaz = bmul(bsub(BONE, norm), sF)
    aI_after = bmul(aI, bsub(BONE, zaz))
    newBal = badd(bI, aI_after)
    ratio = bdiv(newBal, bI)
    poolRatio = bpow(ratio, norm)
    newSupply = bmul(poolRatio, pS)
    return bsub(newSupply, pS)


def calcSingleInGivenPoolOut(bI, wI, pS, tW, pAo, sF):
    norm = bdiv(wI, tW)
    newSupply = badd(pS, pAo)
    poolRatio = bdiv(newSupply, pS)
    boo = bdiv(BONE, norm)
    tokenInRatio = bpow(poolRatio, boo)
    newBalIn = bmul(tokenInRatio, bI)
    aI_after = bsub(newBalIn, bI)
    zar = bmul(bsub(BONE, norm), sF)
    return bdiv(aI_after, bsub(BONE, zar))


def calcSingleOutGivenPoolIn(bO, wO, pS, tW, pAi, sF):
    norm = bdiv(wO, tW)
    pAi_after = bmul(pAi, bsub(BONE, 0))  # EXIT_FEE == 0
    newSupply = bsub(pS, pAi_after)
    ratio = bdiv(newSupply, pS)
    tokenOutRatio = bpow(ratio, bdiv(BONE, norm))
    newBalOut = bmul(tokenOutRatio, bO)
    beforeFee = bsub(bO, newBalOut)
    zaz = bmul(bsub(BONE, norm), sF)
    return bmul(beforeFee, bsub(BONE, zaz))


def calcPoolInGivenSingleOut(bO, wO, pS, tW, aO, sF):
    norm = bdiv(wO, tW)
    zoo = bsub(BONE, norm)
    zar = bmul(zoo, sF)
    aO_before = bdiv(aO, bsub(BONE, zar))
    newBalOut = bsub(bO, aO_before)
    ratio = bdiv(newBalOut, bO)
    poolRatio = bpow(ratio, norm)
    newSupply = bmul(poolRatio, pS)
    pAi_after = bsub(pS, newSupply)
    return bdiv(pAi_after, bsub(BONE, 0))


# ----------------------------- BPool -----------------------------

class Pool:
    """Faithful model of BPool for the paths that matter (2..n tokens)."""

    def __init__(self, tokens, fee=3 * 10**14):
        # tokens: list of dicts {sym, dec, bal (1e18 units), denorm}
        self.t = {}
        self.order = []
        for tok in tokens:
            self.t[tok["sym"]] = {
                "bal": tok["bal"],
                "denorm": tok["denorm"],
                "dec": tok["dec"],
            }
            self.order.append(tok["sym"])
        self.tW = sum(x["denorm"] for x in self.t.values())
        self.fee = fee
        self.pS = INIT_POOL_SUPPLY
        self.finalized = True
        self.publicSwap = True

    # ----- helpers -----
    def _rec(self, s):
        if s not in self.t:
            raise Revert("ERR_NOT_BOUND")
        return self.t[s]

    def units(self, sym, amount_1e18):
        """convert a 1e18-scaled amount into whole token units (human)"""
        return amount_1e18 / 10**18

    def smallest_unit(self, sym):
        """value of 1 on-chain unit in 1e18-scaled terms"""
        return 10 ** (18 - self.t[sym]["dec"])

    def snapshot(self):
        return (
            {k: dict(v) for k, v in self.t.items()},
            self.pS,
        )

    # ----- entrypoints -----
    def joinPool(self, pAo, maxAmountsIn):
        if not self.finalized:
            raise Revert("ERR_NOT_FINALIZED")
        ratio = bdiv(pAo, self.pS)
        if ratio == 0:
            raise Revert("ERR_MATH_APPROX")
        for s in self.order:
            bal = self.t[s]["bal"]
            aI = bmul(ratio, bal)
            if aI == 0:
                raise Revert("ERR_MATH_APPROX")
            if aI > maxAmountsIn.get(s, 0):
                raise Revert("ERR_LIMIT_IN")
            self.t[s]["bal"] = badd(bal, aI)
        self.pS = badd(self.pS, pAo)

    def exitPool(self, pAi, minAmountsOut):
        ratio = bdiv(pAi, self.pS)
        if ratio == 0:
            raise Revert("ERR_MATH_APPROX")
        self.pS = bsub(self.pS, pAi)
        for s in self.order:
            bal = self.t[s]["bal"]
            aO = bmul(ratio, bal)
            if aO == 0:
                raise Revert("ERR_MATH_APPROX")
            if aO < minAmountsOut.get(s, 0):
                raise Revert("ERR_LIMIT_OUT")
            self.t[s]["bal"] = bsub(bal, aO)

    def swapExactAmountIn(self, tin, aI, tout, minAmountOut, maxPrice):
        r_in, r_out = self._rec(tin), self._rec(tout)
        if aI > bmul(r_in["bal"], MAX_IN_RATIO):
            raise Revert("ERR_MAX_IN_RATIO")
        spBefore = calcSpotPrice(r_in["bal"], r_in["denorm"],
                                 r_out["bal"], r_out["denorm"], self.fee)
        if spBefore > maxPrice:
            raise Revert("ERR_BAD_LIMIT_PRICE")
        aO = calcOutGivenIn(r_in["bal"], r_in["denorm"],
                            r_out["bal"], r_out["denorm"], aI, self.fee)
        if aO < minAmountOut:
            raise Revert("ERR_LIMIT_OUT")
        r_in["bal"] = badd(r_in["bal"], aI)
        r_out["bal"] = bsub(r_out["bal"], aO)
        spAfter = calcSpotPrice(r_in["bal"], r_in["denorm"],
                                r_out["bal"], r_out["denorm"], self.fee)
        if spAfter < spBefore:
            raise Revert("ERR_MATH_APPROX")
        if spAfter > maxPrice:
            raise Revert("ERR_LIMIT_PRICE")
        if spBefore > bdiv(aI, aO):
            raise Revert("ERR_MATH_APPROX")
        return aO

    def swapExactAmountOut(self, tin, maxAmountIn, tout, aO, maxPrice):
        r_in, r_out = self._rec(tin), self._rec(tout)
        if aO > bmul(r_out["bal"], MAX_OUT_RATIO):
            raise Revert("ERR_MAX_OUT_RATIO")
        spBefore = calcSpotPrice(r_in["bal"], r_in["denorm"],
                                 r_out["bal"], r_out["denorm"], self.fee)
        if spBefore > maxPrice:
            raise Revert("ERR_BAD_LIMIT_PRICE")
        aI = calcInGivenOut(r_in["bal"], r_in["denorm"],
                            r_out["bal"], r_out["denorm"], aO, self.fee)
        if aI > maxAmountIn:
            raise Revert("ERR_LIMIT_IN")
        r_in["bal"] = badd(r_in["bal"], aI)
        r_out["bal"] = bsub(r_out["bal"], aO)
        spAfter = calcSpotPrice(r_in["bal"], r_in["denorm"],
                                r_out["bal"], r_out["denorm"], self.fee)
        if spAfter < spBefore:
            raise Revert("ERR_MATH_APPROX")
        if spAfter > maxPrice:
            raise Revert("ERR_LIMIT_PRICE")
        if spBefore > bdiv(aI, aO):
            raise Revert("ERR_MATH_APPROX")
        return aI

    def joinswapExternAmountIn(self, tin, aI, minPoolAmountOut):
        if not self.finalized:
            raise Revert("ERR_NOT_FINALIZED")
        r = self._rec(tin)
        if aI > bmul(r["bal"], MAX_IN_RATIO):
            raise Revert("ERR_MAX_IN_RATIO")
        pAo = calcPoolOutGivenSingleIn(r["bal"], r["denorm"], self.pS,
                                       self.tW, aI, self.fee)
        if pAo < minPoolAmountOut:
            raise Revert("ERR_LIMIT_OUT")
        r["bal"] = badd(r["bal"], aI)
        self.pS = badd(self.pS, pAo)
        return pAo

    def joinswapPoolAmountOut(self, tin, pAo, maxAmountIn):
        if not self.finalized:
            raise Revert("ERR_NOT_FINALIZED")
        r = self._rec(tin)
        aI = calcSingleInGivenPoolOut(r["bal"], r["denorm"], self.pS,
                                     self.tW, pAo, self.fee)
        if aI == 0:
            raise Revert("ERR_MATH_APPROX")
        if aI > maxAmountIn:
            raise Revert("ERR_LIMIT_IN")
        if aI > bmul(r["bal"], MAX_IN_RATIO):
            raise Revert("ERR_MAX_IN_RATIO")
        r["bal"] = badd(r["bal"], aI)
        self.pS = badd(self.pS, pAo)
        return aI

    def exitswapPoolAmountIn(self, tout, pAi, minAmountOut):
        r = self._rec(tout)
        aO = calcSingleOutGivenPoolIn(r["bal"], r["denorm"], self.pS,
                                     self.tW, pAi, self.fee)
        if aO < minAmountOut:
            raise Revert("ERR_LIMIT_OUT")
        if aO > bmul(r["bal"], MAX_OUT_RATIO):
            raise Revert("ERR_MAX_OUT_RATIO")
        r["bal"] = bsub(r["bal"], aO)
        self.pS = bsub(self.pS, pAi)
        return aO

    def exitswapExternAmountOut(self, tout, aO, maxPoolAmountIn):
        r = self._rec(tout)
        if aO > bmul(r["bal"], MAX_OUT_RATIO):
            raise Revert("ERR_MAX_OUT_RATIO")
        pAi = calcPoolInGivenSingleOut(r["bal"], r["denorm"], self.pS,
                                       self.tW, aO, self.fee)
        if pAi == 0:
            raise Revert("ERR_MATH_APPROX")
        if pAi > maxPoolAmountIn:
            raise Revert("ERR_LIMIT_IN")
        r["bal"] = bsub(r["bal"], aO)
        self.pS = bsub(self.pS, pAi)
        return pAi

    def gulp(self, sym, real_balance):
        r = self._rec(sym)
        r["bal"] = real_balance
