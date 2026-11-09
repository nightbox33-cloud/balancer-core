#!/usr/bin/env python3
"""Lista completa de los pools CONDICIONALMENTE vulnerables: los que no son
vulnerables con los datos de hoy, pero lo serian si la pata sin precio valiera
menos que un umbral.

Uso: python3 condicionales.py        (cwd = security/)
Genera: data/CONDICIONALES-61.md
"""
import csv

from verify_triage import load, unpriced_scan, judge


def live_meta():
    """pool -> (simbolos, pesos, balances, precios) de la lista del escaner."""
    out = {}
    for r in csv.DictReader(open("data/pools_live.csv")):
        out[r["pool"]] = dict(tokens=r["tokens_csv"].split("|"),
                              w=r["weights_norm_pct"].split("|"),
                              bal=r["balances_amt"].split("|"),
                              px=r["prices_usd"].split("|"))
    return out


def unpriced_leg(meta):
    """Devuelve (simbolo, unidades) de la pata sin precio, si se conoce."""
    if not meta:
        return None, None
    for i, p in enumerate(meta["px"]):
        if p.endswith("=NA"):
            sym = p.split("=")[0]
            units = None
            for b in meta["bal"]:
                if b.startswith(sym + "="):
                    units = float(b.split("=")[1])
            return sym, units
    return None, None


def main():
    rows = load("data/triage_v1.csv") + load("data/triage_v2.csv")
    meta = live_meta()
    cond, indec = [], []
    for r in rows:
        if judge(r, r["toks"], r["ver"], r["fee"])[0] != "REVISAR":
            continue
        sc = unpriced_scan(r)
        if sc is None:
            indec.append(r)
            continue
        umax, dead = sc
        cond.append((r, umax, dead))
    cond.sort(key=lambda x: -x[2])

    L = []
    L.append("# Los 61 pools condicionalmente vulnerables\n")
    L.append("No son vulnerables con los datos de hoy: les falta el precio de **una** pata. "
             "Lo serán si esa pata vale menos que el **umbral**, porque entonces entra a precio "
             "de polvo y se drena la pata viva.\n")
    L.append("Umbral en forma cerrada (`unpriced_scan`), con `u` = valor de la pata sin precio, "
             "`V` = valor de las patas con precio, `w_u` su peso y `ρ*` el umbral por peso:\n")
    L.append("```\nρ_u = u/(w_u·(V+u)) < ρ*   <=>   u < w_u·ρ*·V / (1 − w_u·ρ*)\n```\n")
    L.append(f"**{len(cond)} pools · pata viva ${sum(x[0]['tvl'] for x in cond):,.0f} · "
             f"botín máximo ${sum(x[2] for x in cond):,.0f}**\n")
    L.append("| # | pool | ver | pata viva | umbral (la otra debe valer menos de) | ⇔ precio unitario | botín si muere |")
    L.append("|---|---|---|---:|---:|---:|---:|")
    for n, (r, umax, dead) in enumerate(cond, 1):
        sym, units = unpriced_leg(meta.get(r["pool"]))
        if sym and units:
            unit = f"{sym} < **${umax/units:,.4f}**"
        elif sym:
            unit = f"{sym} (total)"
        else:
            unit = "—"
        L.append(f"| {n} | `{r['pool'][:10]}` | {r['ver']} | ${r['tvl']:,.0f} | "
                 f"${umax:,.0f} | {unit} | ${dead:,.0f} |")
    L.append("")
    L.append("## Indecidibles: más de una pata sin precio\n")
    L.append("No se pueden cerrar ni con la fórmula: hacen falta dos precios a la vez.\n")
    L.append("| pool | ver | pata viva |\n|---|---|---:|")
    for r in indec:
        L.append(f"| `{r['pool']}` | {r['ver']} | ${r['tvl']:,.0f} |")
    L.append("")
    L.append("## Cómo se leen los umbrales\n")
    L.append("- Umbral **alto** = el pool es vulnerable salvo que el token valga mucho: "
             "cuanto más alto, más probable que el ataque funcione.\n"
             "- Umbral igual al **100 % de la pata viva** ⇒ el pool está en el cruce: "
             "atacable con casi cualquier precio del token sin precio.\n"
             "- Umbral **bajo** ⇒ sólo cae si el token está realmente muerto.\n")
    open("data/CONDICIONALES-61.md", "w").write("\n".join(L))
    print(f"{len(cond)} condicionales · pata viva ${sum(x[0]['tvl'] for x in cond):,.0f} · "
          f"botín ${sum(x[2] for x in cond):,.0f} · {len(indec)} indecidibles")
    print(f"umbral/100% de la pata viva: "
          f"{sum(1 for r, u, d in cond if abs(u - r['tvl']) < 1)} pools")


if __name__ == "__main__":
    main()
