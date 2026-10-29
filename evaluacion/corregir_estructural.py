"""Corrige la métrica de validez estructural/coherencia de las ejecuciones ``rechazada_verificador``.

Error de MEDIDA (no del sistema): cuando la aplicación descartaba una salida válida en forma pero falsa, el ejecutor
evaluaba ``salida=None`` y registraba ``validez_estructural=False`` y ``coherencia_evidencia=False``. Pero esa salida SÍ
cumplía el contrato (por eso llegó al verificador): era estructuralmente válida e incoherente con los datos, que es justo
la distinción que se quiere medir. El ejecutor ya está corregido; este script rehace la evaluación de las tandas anteriores
a partir de ``extra.salida_descartada`` guardada en cada traza.

Uso (desde la raíz del proyecto):  python evaluacion/corregir_estructural.py resultados/base resultados/v2_base ...
Deja ``medidas_sin_corregir_estructural.csv`` y sincroniza ``medidas.csv``, ``medidas.json`` y la fila embebida en las trazas
(también el campo ``reintentos`` ya corregido por ``corregir_reintentos.py``).
"""
import csv
import json
import re
import shutil
import sys
from pathlib import Path

CAMPOS = ("reintentos", "validez_estructural", "coherencia_evidencia", "hallazgos_verificador")


def corregir(carpeta: Path) -> int:
    ruta_csv = carpeta / "medidas.csv"
    filas = list(csv.DictReader(ruta_csv.open(encoding="utf-8")))
    copia = carpeta / "medidas_sin_corregir_estructural.csv"
    cambios = 0
    for f in filas:
        if f["terminacion"] != "rechazada_verificador":
            continue
        traza = carpeta / "trazas" / f"{f['config']}_{f['caso']}_{f['repeticion']}.json"
        descartada = json.loads(traza.read_text(encoding="utf-8")).get("extra", {}).get("salida_descartada")
        if descartada is None:
            continue
        # Por construcción: la salida pasó el contrato VIGENTE EN SU TANDA (si no, habría sido ``salida_invalida``) y el
        # verificador la rechazó. No se revalida con el contrato actual (más estricto desde v2: las salidas de la tanda
        # base no lo cumplirían). Los códigos de hallazgo salen del texto del rechazo guardado en la columna ``error``.
        f["validez_estructural"], f["coherencia_evidencia"] = "True", "False"
        f["hallazgos_verificador"] = ";".join(re.findall(r"\[(\w+)\]", f["error"]))
        cambios += 1
    if cambios and not copia.exists():
        shutil.copy(ruta_csv, copia)
    with ruta_csv.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(filas[0].keys()))
        w.writeheader(); w.writerows(filas)
    _sincronizar(carpeta, filas)
    return cambios


def _sincronizar(carpeta: Path, filas: list[dict]) -> None:
    por_clave = {(f["config"], f["caso"], str(f["repeticion"])): f for f in filas}
    ruta_json = carpeta / "medidas.json"
    if ruta_json.exists():
        datos = json.loads(ruta_json.read_text(encoding="utf-8"))
        for d in datos:
            f = por_clave.get((d["config"], d["caso"], str(d["repeticion"])))
            if f:
                d["reintentos"] = int(float(f["reintentos"] or 0))
                d["validez_estructural"] = None if f["validez_estructural"] in ("None", "") else f["validez_estructural"] == "True"
                d["coherencia_evidencia"] = None if f["coherencia_evidencia"] in ("None", "") else f["coherencia_evidencia"] == "True"
                d["hallazgos_verificador"] = f["hallazgos_verificador"]
        ruta_json.write_text(json.dumps(datos, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    for (cfg, caso, rep), f in por_clave.items():
        ruta = carpeta / "trazas" / f"{cfg}_{caso}_{rep}.json"
        if not ruta.exists():
            continue
        t = json.loads(ruta.read_text(encoding="utf-8"))
        cambiado = False
        for campo in CAMPOS:
            v = f[campo]
            if campo == "reintentos":
                v = int(float(v or 0))
            elif campo in ("validez_estructural", "coherencia_evidencia"):
                v = None if v in ("None", "") else v == "True"
            if t["fila"].get(campo) != v:
                t["fila"][campo] = v; cambiado = True
        if cambiado:
            ruta.write_text(json.dumps(t, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


if __name__ == "__main__":
    for d in sys.argv[1:]:
        print(f"{d}: {corregir(Path(d))} ejecuciones rechazadas reevaluadas")
