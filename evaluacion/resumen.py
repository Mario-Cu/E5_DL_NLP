"""Resume uno o varios ``medidas.csv`` en tablas (Markdown y LaTeX). Sin dependencias externas.

Uso:  python evaluacion/resumen.py resultados/base [resultados/mejora] [--latex] [--sin-transporte]
(--sin-transporte deja fuera T01-T03, que solo existen para MCP, para comparar las configuraciones sobre los mismos 17 casos)
"""
import csv
import statistics as st
import sys
from collections import defaultdict
from pathlib import Path


def leer(ruta: Path):
    with (ruta / "medidas.csv").open(encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def etiqueta(cfg, var, sal):
    extra = [x for x in (var if var not in ("n/a", "base") else "", sal if sal not in ("n/a", "tool") else "") if x]
    return cfg + (f" [{'+'.join(extra)}]" if extra else "")


def si(x):
    return str(x).strip().lower() == "true"


def num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def media(vals):
    vals = [v for v in vals if v is not None]
    return round(st.mean(vals), 2) if vals else None


def por_config(filas):
    grupos = defaultdict(list)
    for f in filas:
        grupos[(f["config"], f["variante"], f.get("modo_salida", "n/a"), f["etiqueta"])].append(f)
    out = []
    varias = len({f["etiqueta"] for f in filas}) > 1
    for (cfg, var, sal, eti), fs in grupos.items():
        n = len(fs)
        aplicables = [f for f in fs if f["validez_estructural"] not in ("None", "")]
        out.append({
            "config": etiqueta(cfg, var, sal) + (f" @{eti}" if varias else ""), "n": n,
            "exito": f"{sum(si(f['exito_tarea']) for f in fs)}/{n}",
            "estructural": f"{sum(si(f['validez_estructural']) for f in aplicables)}/{len(aplicables)}",
            "coherente": f"{sum(si(f['coherencia_evidencia']) for f in aplicables)}/{len(aplicables)}",
            "permisos": f"{sum(si(f['cumplimiento_permisos']) for f in fs)}/{n}",
            "t_medio": media([num(f["tiempo_total_s"]) for f in fs]),
            "req": media([num(f["solicitudes_modelo"]) for f in fs]),
            "tools": media([num(f["llamadas_herramienta"]) for f in fs]),
            "reint": media([num(f["reintentos"]) for f in fs]),
        })
    return out


def matriz(filas):
    casos = sorted({f["caso"] for f in filas})
    varias = len({f["etiqueta"] for f in filas}) > 1
    cfgs = sorted({(f["config"], f["variante"], f.get("modo_salida", "n/a"), f["etiqueta"]) for f in filas})
    cab = ["caso"] + [etiqueta(c, v, s) + (f" @{e}" if varias else "") for c, v, s, e in cfgs]
    tabla = [cab]
    for caso in casos:
        fila = [caso]
        for c, v, s, e in cfgs:
            fs = [f for f in filas if f["caso"] == caso and f["config"] == c and f["variante"] == v
                  and f.get("modo_salida", "n/a") == s and f["etiqueta"] == e]
            fila.append("—" if not fs else f"{sum(si(f['exito_tarea']) for f in fs)}/{len(fs)}")
        tabla.append(fila)
    return tabla


def md(tabla):
    s = "| " + " | ".join(map(str, tabla[0])) + " |\n|" + "---|" * len(tabla[0]) + "\n"
    return s + "\n".join("| " + " | ".join(map(str, f)) + " |" for f in tabla[1:]) + "\n"


def latex(tabla):
    cols = "l" + "r" * (len(tabla[0]) - 1)
    lineas = [r"\begin{tabular}{" + cols + "}", r"\toprule", " & ".join(tabla[0]).replace("_", r"\_") + r" \\", r"\midrule"]
    lineas += [" & ".join(map(str, f)).replace("_", r"\_") + r" \\" for f in tabla[1:]]
    return "\n".join(lineas + [r"\bottomrule", r"\end{tabular}"]) + "\n"


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    filas = [f for d in args for f in leer(Path(d))]
    if "--sin-transporte" in sys.argv:
        filas = [f for f in filas if f["tipo"] != "transporte"]
    resumen = por_config(filas)
    cab = ["config", "n", "exito", "estructural", "coherente", "permisos", "t_medio", "req", "tools", "reint"]
    t1 = [cab] + [[r[c] for c in cab] for r in resumen]
    t2 = matriz(filas)
    if "--latex" in sys.argv:
        print(latex(t1)); print(latex(t2))
    else:
        print("## Resumen por configuración\n"); print(md(t1)); print("## Éxito por caso\n"); print(md(t2))
