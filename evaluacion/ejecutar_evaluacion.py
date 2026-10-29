"""Ejecuta la evaluación de las configuraciones sobre los casos congelados y guarda CSV/JSON/trazas.

Configuraciones (mismo modelo, datos, preguntas, criterios y límites en todas):
  referencia      función determinista, sin LLM ni framework de agentes
  smolagents      ToolCallingAgent
  pydantic_local  Pydantic AI con herramientas Python locales
  pydantic_mcp    Pydantic AI como host/cliente del servidor MCP por stdio

Modos:
  real   usa el LLM local (Ollama). Es la ÚNICA evaluación que cuenta como resultado del sistema.
  doble  usa modelos simulados con guion: solo prueba la integración y los resultados se etiquetan «integración».

Ejemplos:
  python evaluacion/ejecutar_evaluacion.py --modo real --etiqueta base
  python evaluacion/ejecutar_evaluacion.py --modo real --variante verificada --casos C01 C06 --etiqueta mejora
  python evaluacion/ejecutar_evaluacion.py --modo doble --etiqueta integracion
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import hashlib
import json
import platform
import sys
import tempfile
import time
import urllib.request
from dataclasses import asdict
from datetime import datetime
from importlib import metadata
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from asr_asistente.agentes.comun import DepsAsistente, NO_DISPONIBLE, ResultadoEjecucion, a_json  # noqa: E402
from asr_asistente.dominio import Permisos, Repositorio, Solicitud  # noqa: E402
from asr_asistente.herramientas import Auditoria, ServicioResultados  # noqa: E402
from asr_asistente.politica import (CONFIG_MODELO, LIMITES, POLITICA_EVALUACION, SECRETO_CANARIO,  # noqa: E402
                                    ConfigModelo, hash_politica)
from asr_asistente.referencia import ejecutar_referencia  # noqa: E402
from asr_asistente.verificador import evaluar_aceptacion  # noqa: E402

CONFIGS = ("referencia", "smolagents", "pydantic_local", "pydantic_mcp")
COLUMNAS = ["etiqueta", "modo", "config", "variante", "modo_salida", "caso", "tipo", "repeticion", "terminacion",
            "exito_tarea", "validez_estructural", "coherencia_evidencia", "cumplimiento_permisos",
            "intentos_acceso_denegado", "fuga_secreto", "estado_salida", "motivo_o_ganador", "tiempo_total_s",
            "solicitudes_modelo", "llamadas_herramienta", "reintentos", "reintentos_transporte",
            "tokens_entrada", "tokens_salida", "coste", "arranque_mcp_s", "hallazgos_verificador", "error"]


# --------------------------------------------------------------------------- #
def cargar_casos(ruta: Path) -> list[dict]:
    texto = ruta.read_text(encoding="utf-8")
    esperado = (ruta.parent / "casos.sha256").read_text(encoding="utf-8").split()[0]
    real = hashlib.sha256(texto.encode("utf-8")).hexdigest()
    if real != esperado:
        raise SystemExit(f"casos.json no coincide con casos.sha256 ({real[:12]} != {esperado[:12]}). "
                         "Los casos están congelados: no se cambian después de observar salidas.")
    return json.loads(texto)["casos"], real


def versiones() -> dict:
    out = {}
    for p in ("smolagents", "pydantic-ai-slim", "pydantic-ai", "mcp", "fastmcp-slim", "fastmcp", "litellm", "pydantic", "pytest"):
        try:
            out[p] = metadata.version(p)
        except metadata.PackageNotFoundError:
            pass
    return out


def revision_protocolo_mcp() -> str:
    """Revisión del protocolo MCP realmente negociada entre cliente y servidor (no la versión del paquete)."""
    from fastmcp.client import Client
    from asr_asistente.cliente_mcp import transporte_stdio

    async def _q():
        async with Client(transporte_stdio()) as c:
            return str(c.protocol_version)
    try:
        return asyncio.run(_q())
    except Exception as exc:  # noqa: BLE001
        return f"no disponible ({type(exc).__name__})"


def comprobar_ollama(cfg: ConfigModelo) -> None:
    try:
        with urllib.request.urlopen(cfg.url_base.rstrip("/") + "/api/tags", timeout=5) as r:
            etiquetas = [m["name"] for m in json.loads(r.read())["models"]]
    except Exception as exc:  # noqa: BLE001
        raise SystemExit(f"No se puede contactar con Ollama en {cfg.url_base} ({exc}). ¿Está en marcha 'ollama serve'?")
    if not any(e == cfg.modelo or e.startswith(cfg.modelo + ":") or e.split(":")[0] == cfg.modelo for e in etiquetas):
        raise SystemExit(f"El modelo {cfg.modelo} no existe en Ollama. Ejecuta scripts/preparar_windows.ps1 (hace ollama pull {cfg.modelo_base} y ollama create {cfg.modelo} -f ollama/Modelfile). Modelos presentes: {etiquetas}")


# --------------------------------------------------------------------------- #
def ejecutar_una(config: str, caso: dict, rep: int, args, cfg: ConfigModelo) -> tuple[ResultadoEjecucion, list[dict], Repositorio]:
    repo = Repositorio(RAIZ / caso["datos"])
    permisos = Permisos()
    sol = caso["solicitud"]
    pregunta = caso["pregunta"]
    real = args.modo == "real"

    if config == "referencia":
        with_t = time.perf_counter()
        salida = ejecutar_referencia(repo, permisos, Solicitud(sol["corpus"], sol["idioma"], tuple(sol["sistemas"])))
        res = ResultadoEjecucion(config=config, caso=caso["id"], pregunta=pregunta, salida=salida,
                                 texto_salida=salida.model_dump_json(), tiempo_s=round(time.perf_counter() - with_t, 6))
        return res, [], repo

    from asr_asistente.agentes.comun import DepsAsistente
    servicio = ServicioResultados(repo, permisos, Auditoria(origen=config))
    deps = DepsAsistente(servicio=servicio, limites=LIMITES)

    if config == "smolagents":
        from asr_asistente.agentes.smol_agente import ejecutar_smolagents
        if real:
            from asr_asistente.agentes.modelos import modelo_smolagents
            modelo = modelo_smolagents(cfg)
        else:
            from asr_asistente.dobles import PlanDoble, modelo_doble_smol
            modelo = modelo_doble_smol(PlanDoble(sol, args.defecto))
        res = ejecutar_smolagents(modelo, pregunta, deps, config, caso["id"], real=real, variante=args.variante)
        return res, servicio.auditoria.eventos, repo

    if config == "pydantic_local":
        from asr_asistente.agentes.pydantic_local import construir_agente, ejecutar_agente
        if real:
            from asr_asistente.agentes.modelos import ajustes_pydantic, modelo_pydantic
            modelo, ajustes = modelo_pydantic(cfg), ajustes_pydantic(cfg)
        else:
            from asr_asistente.dobles import PlanDoble, modelo_doble_pydantic
            modelo, ajustes = modelo_doble_pydantic(PlanDoble(sol, args.defecto, args.corrige)), None
        agente = construir_agente(modelo, args.variante, deps, ajustes=ajustes, salida=args.salida)
        res = asyncio.run(ejecutar_agente(agente, pregunta, deps, config, caso["id"], args.variante, real=real))
        return res, servicio.auditoria.eventos, repo

    if config == "pydantic_mcp":
        from asr_asistente.agentes.pydantic_mcp import ejecutar_mcp
        if real:
            from asr_asistente.agentes.modelos import ajustes_pydantic, modelo_pydantic
            modelo, ajustes = modelo_pydantic(cfg), ajustes_pydantic(cfg)
        else:
            from asr_asistente.dobles import PlanDoble, modelo_doble_pydantic
            modelo, ajustes = modelo_doble_pydantic(PlanDoble(sol, args.defecto, args.corrige)), None
        with tempfile.TemporaryDirectory() as tmp:
            extra = None
            if caso.get("fallo_servidor"):
                extra = ["--fallo", caso["fallo_servidor"], "--marca", str(Path(tmp) / "marca")]
            res = asyncio.run(ejecutar_mcp(modelo, pregunta, deps, config, caso["id"], args.variante, salida=args.salida,
                                           ruta_auditoria=Path(tmp) / "auditoria.jsonl", datos=RAIZ / caso["datos"],
                                           extra_servidor=extra, ajustes=ajustes, real=real))
        return res, res.extra.get("eventos_auditoria", []), repo
    raise ValueError(config)


def fila_csv(args, config: str, caso: dict, rep: int, res: ResultadoEjecucion, ev: dict) -> dict:
    s = res.salida
    estado = s.estado if s is not None else "sin_salida"
    detalle = "" if s is None else (s.ganador or "empate" if s.estado == "comparacion" else s.motivo)
    return {
        "etiqueta": args.etiqueta, "modo": args.modo, "config": config,
        "variante": args.variante if config != "referencia" else "n/a",
        "modo_salida": args.salida if config.startswith("pydantic") else "n/a",
        "caso": caso["id"], "tipo": caso["tipo"], "repeticion": rep, "terminacion": res.terminacion,
        "exito_tarea": ev["exito_tarea"], "validez_estructural": ev["validez_estructural"],
        "coherencia_evidencia": ev["coherencia_evidencia"], "cumplimiento_permisos": ev["cumplimiento_permisos"],
        "intentos_acceso_denegado": ev["intentos_acceso_denegado"], "fuga_secreto": ev["fuga_secreto"],
        "estado_salida": estado, "motivo_o_ganador": detalle, "tiempo_total_s": res.tiempo_s,
        "solicitudes_modelo": res.solicitudes_modelo, "llamadas_herramienta": res.llamadas_herramienta,
        "reintentos": res.reintentos, "reintentos_transporte": res.reintentos_transporte,
        "tokens_entrada": res.tokens_entrada, "tokens_salida": res.tokens_salida, "coste": res.coste,
        "arranque_mcp_s": res.extra.get("arranque_mcp_s", ""),
        "hallazgos_verificador": ";".join(ev["hallazgos"]), "error": (res.error or "")[:300],
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--modo", choices=["real", "doble"], default="doble")
    ap.add_argument("--etiqueta", default=None, help="nombre de la carpeta de resultados (por defecto, modo_fecha)")
    ap.add_argument("--configs", nargs="+", default=list(CONFIGS), choices=CONFIGS)
    ap.add_argument("--variante", choices=["base", "verificada"], default="base",
                    help="verificación solo posterior (base) o también dentro del bucle del agente (verificada); smolagents y Pydantic AI")
    ap.add_argument("--salida", choices=["tool", "prompted"], default="tool",
                    help="solo Pydantic AI: salida estructurada por herramienta de salida (tool) o JSON en texto validado (prompted)")
    ap.add_argument("--casos", nargs="*", help="ids de casos a ejecutar (por defecto, todos)")
    ap.add_argument("--repeticiones", type=int, default=None, help="fuerza el nº de repeticiones de todos los casos")
    ap.add_argument("--modelo", default=CONFIG_MODELO.modelo)
    ap.add_argument("--url", default=CONFIG_MODELO.url_base)
    ap.add_argument("--defecto", default=None, help="(modo doble) defecto inyectado en el doble")
    ap.add_argument("--corrige", action="store_true", help="(modo doble) el doble rectifica tras un reintento")
    ap.add_argument("--sin-calentamiento", action="store_true")
    args = ap.parse_args()
    cfg = ConfigModelo(modelo=args.modelo, url_base=args.url)
    args.etiqueta = args.etiqueta or f"{args.modo}_{datetime.now():%Y%m%d_%H%M%S}"

    casos, hash_casos = cargar_casos(RAIZ / "evaluacion" / "casos.json")
    if args.casos:
        casos = [c for c in casos if c["id"] in args.casos]
    carpeta = RAIZ / "resultados" / args.etiqueta
    (carpeta / "trazas").mkdir(parents=True, exist_ok=True)

    if args.modo == "real":
        comprobar_ollama(cfg)
        if not args.sin_calentamiento and any(c != "referencia" for c in args.configs):
            print("Calentamiento (no se registra)…")
            from asr_asistente.agentes.modelos import modelo_pydantic
            from pydantic_ai import Agent
            Agent(modelo_pydantic(cfg)).run_sync("Responde solo: ok")

    config_ejec = {
        "etiqueta": args.etiqueta, "modo": args.modo, "variante": args.variante, "modo_salida": args.salida, "fecha": datetime.now().isoformat(timespec="seconds"),
        "python": sys.version, "sistema": platform.platform(), "versiones": versiones(),
        "modelo": cfg.a_dict() if args.modo == "real" else "doble de pruebas (sin LLM)",
        "limites": asdict(LIMITES), "casos_sha256": hash_casos, "politica_sha256": hash_politica(),
        "revision_protocolo_mcp_negociada": revision_protocolo_mcp(),
        "transporte_mcp": "stdio (subproceso)", "defecto_inyectado": args.defecto,
        "nota": "Las filas con modo=doble prueban integración; no son resultados de ningún LLM.",
    }
    (carpeta / "config_ejecucion.json").write_text(json.dumps(config_ejec, ensure_ascii=False, indent=2), encoding="utf-8")

    filas, completos, no_ejecutadas = [], [], []
    for config in args.configs:
        for caso in casos:
            if caso.get("solo_config") and config not in caso["solo_config"]:
                no_ejecutadas.append({"config": config, "caso": caso["id"],
                                      "motivo": f"no aplica: la prueba solo existe para {caso['solo_config']}"})
                continue
            if config == "referencia" and caso["tipo"] == "transporte":
                continue
            reps = args.repeticiones or caso["repeticiones"]
            for rep in range(1, reps + 1):
                t0 = time.perf_counter()
                res, eventos, repo = ejecutar_una(config, caso, rep, args, cfg)
                texto = res.texto_salida + a_json(res.extra.get("salida_descartada") or "")
                ev = evaluar_aceptacion(res.salida, caso, repo, Permisos(), eventos, texto, SECRETO_CANARIO, res.terminacion,
                                      res.extra.get("salida_descartada"))
                fila = fila_csv(args, config, caso, rep, res, ev)
                filas.append(fila)
                completos.append({**fila, "evaluacion": ev, "salida": res.a_dict()["salida"], "extra": res.extra})
                (carpeta / "trazas" / f"{config}_{caso['id']}_{rep}.json").write_text(
                    json.dumps({"fila": fila, "pregunta": res.pregunta, "traza": res.traza, "salida": res.a_dict()["salida"],
                                "eventos_auditoria": eventos, "extra": {k: v for k, v in res.extra.items() if k != "eventos_auditoria"}},
                               ensure_ascii=False, indent=2, default=str), encoding="utf-8")
                marca = "OK " if fila["exito_tarea"] else "FALLO"
                print(f"{marca} {config:15s} {caso['id']:4s} rep{rep}  {res.terminacion:22s} {res.tiempo_s:7.2f}s "
                      f"req={res.solicitudes_modelo} tools={res.llamadas_herramienta} reint={res.reintentos}")

    if args.modo == "doble":
        no_ejecutadas.append({"config": "LLM real (todas)", "caso": "todos", "motivo": "modo doble: solo integración"})
    no_ejecutadas.append({"config": "smolagents_codeagent", "caso": "todos",
                          "motivo": "no ejecutada: la alternativa CodeAgent se analiza en la memoria; ejecutar código generado "
                                    "por el modelo exigiría un entorno aislado (Docker/E2B) que no se ha desplegado"})
    with (carpeta / "medidas.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=COLUMNAS)
        w.writeheader(); w.writerows(filas)
    (carpeta / "medidas.json").write_text(json.dumps(completos, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    with (carpeta / "no_ejecutadas.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["config", "caso", "motivo"])
        w.writeheader(); w.writerows(no_ejecutadas)
    print(f"\nResultados en {carpeta}  ({len(filas)} ejecuciones)")


if __name__ == "__main__":
    main()
