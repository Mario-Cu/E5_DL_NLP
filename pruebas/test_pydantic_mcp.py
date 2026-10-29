"""Pydantic AI + servidor MCP real por stdio, con dobles de modelo (integración, no evalúa un LLM)."""
import asyncio

import pytest

from asr_asistente.agentes.comun import DepsAsistente
from asr_asistente.agentes.pydantic_mcp import ejecutar_mcp
from asr_asistente.dobles import PlanDoble, modelo_doble_pydantic
from asr_asistente.dominio import RAIZ, Permisos, Repositorio
from asr_asistente.herramientas import ServicioResultados
from asr_asistente.politica import Limites


def correr(tmp_path, solicitud, defecto=None, datos=None, extra=None, limites=None, nombre="a"):
    datos_repo = Repositorio(datos) if datos else Repositorio()
    deps = DepsAsistente(servicio=ServicioResultados(datos_repo, Permisos()), limites=limites or Limites())
    return asyncio.run(ejecutar_mcp(
        modelo_doble_pydantic(PlanDoble(solicitud, defecto)), "pregunta", deps, "pydantic_mcp_doble", "t",
        ruta_auditoria=tmp_path / f"{nombre}.jsonl", datos=datos, extra_servidor=extra, real=False))


def sol(idioma="es", sistemas="AB", corpus="demo"):
    return {"corpus": corpus, "idioma": idioma, "sistemas": list(sistemas)}


def test_caso1_via_mcp(tmp_path):
    r = correr(tmp_path, sol())
    assert r.terminacion == "salida_final" and r.salida.ganador == "B"
    assert r.llamadas_herramienta == 3 and r.extra["politica_igual_a_local"] is True
    assert [e["herramienta"] for e in r.extra["eventos_auditoria"]] == ["listar_sistemas", "obtener_resultados", "obtener_resultados"]
    assert r.extra["arranque_mcp_s"] > 0


def test_corpus_no_autorizado_se_deniega_en_el_servidor(tmp_path):
    r = correr(tmp_path, sol(corpus="privado"))
    assert r.salida.motivo == "acceso_denegado"
    assert r.extra["eventos_auditoria"][0]["resultado"]["codigo_error"] == "corpus_no_autorizado"


def test_inyeccion_via_mcp(tmp_path):
    r = correr(tmp_path, sol(), "sigue_inyeccion", datos=RAIZ / "datos" / "escenarios" / "inyeccion.json")
    assert [e["resultado"].get("codigo_error") for e in r.extra["eventos_auditoria"]].count("corpus_no_autorizado") == 1
    assert r.salida is not None and r.salida.ganador == "B"


def test_caida_unica_se_recupera_con_reintento_acotado(tmp_path):
    r = correr(tmp_path, sol(), extra=["--fallo", "caida_una_vez", "--marca", str(tmp_path / "marca")],
               limites=Limites(espera_inicial_s=0.1, tiempo_herramienta_s=10))
    assert r.terminacion == "salida_final" and r.reintentos_transporte == 1 and r.salida.ganador == "B"


def test_cuelgue_unico_vence_por_timeout_y_se_recupera(tmp_path):
    r = correr(tmp_path, sol(), extra=["--fallo", "cuelgue_una_vez", "--marca", str(tmp_path / "marca")],
               limites=Limites(espera_inicial_s=0.1, tiempo_herramienta_s=2))
    assert r.terminacion == "salida_final" and r.reintentos_transporte == 1


def test_caida_permanente_termina_de_forma_controlada(tmp_path):
    r = correr(tmp_path, sol(), extra=["--fallo", "caida_siempre"],
               limites=Limites(espera_inicial_s=0.1, reintentos_transporte=2, tiempo_herramienta_s=5))
    assert r.terminacion == "fallo_transporte" and r.salida is None and r.reintentos_transporte == 2
    assert len(r.extra["fallos_transporte"]) == 3


def test_error_de_argumentos_del_servidor_es_reintento_del_modelo_no_fallo_de_infraestructura(tmp_path):
    """v2: un rechazo del servidor a una llamada mal formada (ToolError) se devuelve al modelo como reintento."""
    from pydantic_ai.messages import ModelResponse, ToolCallPart
    from pydantic_ai.models.function import FunctionModel
    pasos = {"n": 0}

    def modelo(messages, info):
        pasos["n"] += 1
        if pasos["n"] == 1:
            return ModelResponse(parts=[ToolCallPart(tool_name="obtener_resultados", args={"corpus": "demo"})])
        salida = PlanDoble(sol()).paso([])[1]
        return ModelResponse(parts=[ToolCallPart(tool_name=info.output_tools[1].name, args={
            "estado": "datos_insuficientes", "motivo": "idioma_no_indicado", "detalle": "x", "corpus": "demo",
            "pregunta_aclaracion": "¿idioma?"})])

    deps = DepsAsistente(servicio=ServicioResultados(Repositorio(), Permisos()), limites=Limites())
    r = asyncio.run(ejecutar_mcp(FunctionModel(modelo), "p", deps, "x", "t", ruta_auditoria=tmp_path / "a.jsonl", real=False))
    assert r.terminacion != "fallo_infraestructura" and r.reintentos >= 1, (r.terminacion, r.error)
