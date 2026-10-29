"""Corrige la métrica «reintentos» de las ejecuciones Pydantic AI en modo de salida «prompted».

Motivo (error de MEDIDA, no del sistema): en ese modo Pydantic AI reintenta con un ``RetryFeedbackPart`` y el
contador original solo miraba ``RetryPromptPart`` y los ``ToolReturnPart`` reintentados, por lo que los reintentos
de la salida en texto se registraban como 0. El código ya cuenta bien (``agentes/pydantic_local.py``), pero las
tandas v2_prompted, v2_verificada y v3_verificada se lanzaron antes de la corrección. Como cada intento de salida
en texto queda en la traza como ``texto_modelo``, los reintentos se reconstruyen como (nº de textos − 1).

Uso:  python evaluacion/corregir_reintentos.py resultados/v2_prompted resultados/v2_verificada resultados/v3_verificada
Deja la copia original en ``medidas_sin_corregir.csv`` y anota la corrección en ``config_ejecucion.json``.
"""
import csv
import json
import shutil
import sys
from pathlib import Path


def corregir(carpeta: Path) -> int:
    csv_path = carpeta / "medidas.csv"
    if (carpeta / "medidas_sin_corregir.csv").exists():
        print(f"{carpeta}: ya corregida"); return 0
    filas = list(csv.DictReader(csv_path.open(encoding="utf-8")))
    cambios = 0
    for f in filas:
        if not f["config"].startswith("pydantic") or f.get("modo_salida") != "prompted":
            continue
        traza = json.loads((carpeta / "trazas" / f"{f['config']}_{f['caso']}_{f['repeticion']}.json").read_text(encoding="utf-8"))["traza"]
        textos = sum(1 for e in traza if e["tipo"] == "texto_modelo")
        extra = max(textos - 1, 0)
        if extra:
            f["reintentos"] = str(int(float(f["reintentos"])) + extra)
            cambios += 1
    shutil.copy(csv_path, carpeta / "medidas_sin_corregir.csv")
    with csv_path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(filas[0].keys()))
        w.writeheader(); w.writerows(filas)
    cfg_path = carpeta / "config_ejecucion.json"
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    cfg["correccion_metrica"] = ("reintentos de Pydantic AI en modo prompted reconstruidos desde la traza "
                                 "(nº de textos del modelo − 1); original en medidas_sin_corregir.csv")
    cfg_path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{carpeta}: {cambios} filas corregidas")
    return cambios


def sincronizar_trazas(carpeta: Path) -> int:
    """Copia el valor corregido de ``reintentos`` a la fila embebida en cada traza (para que CSV y trazas coincidan)."""
    filas = csv.DictReader((carpeta / "medidas.csv").open(encoding="utf-8"))
    cambios = 0
    for f in filas:
        ruta = carpeta / "trazas" / f"{f['config']}_{f['caso']}_{f['repeticion']}.json"
        if not ruta.exists():
            continue
        t = json.loads(ruta.read_text(encoding="utf-8"))
        nuevo = int(float(f["reintentos"])) if f["reintentos"] not in ("", None) else 0
        if t["fila"].get("reintentos") != nuevo:
            t["fila"]["reintentos"] = nuevo
            ruta.write_text(json.dumps(t, ensure_ascii=False, indent=2), encoding="utf-8")
            cambios += 1
    return cambios


if __name__ == "__main__":
    for d in sys.argv[1:]:
        corregir(Path(d))
        print(f"{d}: {sincronizar_trazas(Path(d))} trazas sincronizadas")
