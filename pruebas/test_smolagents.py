"""Integración smolagents ToolCallingAgent con dobles (no evalúa un LLM real)."""
import pytest

from asr_asistente.agentes.comun import DepsAsistente
from asr_asistente.agentes.smol_agente import ejecutar_smolagents
from asr_asistente.dobles import PlanDoble, modelo_doble_smol
from asr_asistente.herramientas import Auditoria, ServicioResultados
from asr_asistente.politica import Limites
from pruebas.ayudas import escenario


def correr(repo, permisos, solicitud, defecto=None, limites=None):
    servicio = ServicioResultados(repo, permisos, Auditoria())
    deps = DepsAsistente(servicio=servicio, limites=limites or Limites())
    return ejecutar_smolagents(modelo_doble_smol(PlanDoble(solicitud, defecto)), "pregunta", deps, "smol_doble", "t", real=False), servicio


def sol(idioma="es", sistemas="AB", corpus="demo"):
    return {"corpus": corpus, "idioma": idioma, "sistemas": list(sistemas)}


def test_caso1(repo, permisos):
    r, srv = correr(repo, permisos, sol())
    assert r.terminacion == "salida_final", r.error
    assert r.salida.ganador == "B" and r.llamadas_herramienta == 3
    assert [e["herramienta"] for e in srv.auditoria.eventos] == ["listar_sistemas", "obtener_resultados", "obtener_resultados"]


def test_abstencion_y_aclaracion(repo, permisos):
    assert correr(repo, permisos, sol(sistemas="AD"))[0].salida.motivo == "sistema_sin_resultados"
    r, srv = correr(repo, permisos, sol(idioma=None))
    assert r.salida.motivo == "idioma_no_indicado" and not srv.auditoria.eventos


def test_falsa_pero_valida_es_rechazada(repo, permisos):
    r, _ = correr(repo, permisos, sol(), "wer_falso")
    assert r.terminacion == "rechazada_verificador" and r.salida is None


def test_json_roto_reintenta_y_agota(repo, permisos):
    r, _ = correr(repo, permisos, sol(), "json_roto", Limites(pasos_smolagents=4))
    assert r.terminacion in ("limite_excedido", "salida_invalida") and r.reintentos >= 1


def test_inyeccion_denegada(permisos):
    r, srv = correr(escenario("inyeccion"), permisos, sol(), "sigue_inyeccion")
    assert any(e["resultado"].get("codigo_error") == "corpus_no_autorizado" for e in srv.auditoria.eventos)
    assert r.salida is not None and r.salida.ganador == "B"


def test_variante_verificada_rechaza_dentro_del_bucle(repo, permisos):
    """Con la variante verificada la salida falsa se rechaza EN el paso (reintento), no solo al final."""
    servicio = ServicioResultados(repo, permisos, Auditoria())
    deps = DepsAsistente(servicio=servicio, limites=Limites(pasos_smolagents=5))
    r = ejecutar_smolagents(modelo_doble_smol(PlanDoble(sol(), "wer_falso")), "p", deps, "smol", "t", real=False,
                            variante="verificada")
    assert r.reintentos >= 1 and r.terminacion in ("limite_excedido", "salida_invalida")   # el doble no se corrige
    assert any("no coincide con la evidencia" in str(e.get("contenido", "")) for e in r.traza if e["tipo"] == "reintento")
