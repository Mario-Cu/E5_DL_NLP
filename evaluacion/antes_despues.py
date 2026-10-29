"""Tabla antes/después de la modificación v3 sobre los casos afectados y los de no regresión.

Uso:  python evaluacion/antes_despues.py resultados/v2_verificada resultados/v3_verificada [salida.md]
"""
import csv
import sys
from pathlib import Path

AFECTADOS = ["C04", "C07", "C07b"]
NO_REGRESION = ["C01", "C03", "C05", "C08", "C09"]
CONFIGS = ["smolagents", "pydantic_local", "pydantic_mcp"]


def leer(d):
    return list(csv.DictReader((Path(d) / "medidas.csv").open(encoding="utf-8")))


def celda(filas, cfg, caso):
    fs = [f for f in filas if f["config"] == cfg and f["caso"] == caso]
    if not fs:
        return "—"
    ok = sum(f["exito_tarea"] == "True" for f in fs)
    term = ",".join(sorted({f["terminacion"] for f in fs if f["exito_tarea"] != "True"}))
    return f"{ok}/{len(fs)}" + (f" ({term})" if term else "")


if __name__ == "__main__":
    antes, despues = leer(sys.argv[1]), leer(sys.argv[2])
    salida = Path(sys.argv[3]) if len(sys.argv) > 3 else None
    out = [f"# Antes ({Path(sys.argv[1]).name}) y después ({Path(sys.argv[2]).name}) de la modificación v3\n"]
    for titulo, casos in (("Casos afectados por el fallo", AFECTADOS), ("Casos de no regresión (acertaban antes)", NO_REGRESION)):
        out.append(f"\n## {titulo}\n\n| caso | " + " | ".join(f"{c} antes | {c} después" for c in CONFIGS) + " |\n|---|" + "---|---|" * len(CONFIGS))
        for caso in casos:
            out.append(f"| {caso} | " + " | ".join(f"{celda(antes, c, caso)} | {celda(despues, c, caso)}" for c in CONFIGS) + " |")
    texto = "\n".join(out) + "\n"
    print(texto)
    if salida:
        salida.write_text(texto, encoding="utf-8")
