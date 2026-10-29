"""Integración Pydantic AI (herramientas locales) con dobles: NO evalúa ningún LLM real."""
import asyncio

import pytest

from asr_asistente.agentes.comun import DepsAsistente
from asr_asistente.agentes.pydantic_local import construir_agente, ejecutar_agente
from asr_asistente.dobles import PlanDoble, modelo_doble_pydantic
from asr_asistente.herramientas import Auditoria, ServicioResultados
from asr_asistente.politica import Limites
from pruebas.ayudas import escenario


def correr(repo, permisos, solicitud, defecto=None, variante="base", limites=None):
    servicio = ServicioResultados(repo, permisos, Auditoria())
    deps = DepsAsistente(servicio=servicio, limites=limites or Limites())
    agente = construir_agente(modelo_doble_pydantic(PlanDoble(solicitud, defecto)), variante, deps)
    return asyncio.run(ejecutar_agente(agente, "pregunta", deps, "pydantic_local_doble", "t", variante, real=False)), servicio


def sol(idioma="es", sistemas="AB", corpus="demo"):
    return {"corpus": corpus, "idioma": idioma, "sistemas": list(sistemas)}


def test_caso1_correcto(repo, permisos):
    r, srv = correr(repo, permisos, sol())
    assert r.terminacion == "salida_final" and r.salida.ganador == "B"
    assert r.llamadas_herramienta == 3 and r.solicitudes_modelo == 4 and r.reintentos == 0
    assert [e["herramienta"] for e in srv.auditoria.eventos] == ["listar_sistemas", "obtener_resultados", "obtener_resultados"]


def test_abstencion_sistema_d(repo, permisos):
    r, _ = correr(repo, permisos, sol(sistemas="AD"))
    assert r.salida.estado == "datos_insuficientes" and r.salida.motivo == "sistema_sin_resultados"


def test_aclaracion_sin_llamar_herramientas(repo, permisos):
    r, srv = correr(repo, permisos, sol(idioma=None))
    assert r.salida.motivo == "idioma_no_indicado" and r.llamadas_herramienta == 0 and not srv.auditoria.eventos


def test_salida_valida_pero_falsa_es_rechazada_por_la_aplicacion(repo, permisos):
    for defecto in ("wer_falso", "ganador_invertido", "fuente_inventada", "ceros_por_ausente"):
        sistemas = "AD" if defecto == "ceros_por_ausente" else "AB"
        r, _ = correr(repo, permisos, sol(sistemas=sistemas), defecto)
        assert r.terminacion == "rechazada_verificador", defecto
        assert r.salida is None and r.extra["salida_descartada"]["estado"] == "comparacion"   # era válida en forma


def test_variante_verificada_reintenta_y_agota(repo, permisos):
    r, _ = correr(repo, permisos, sol(), "wer_falso", variante="verificada", limites=Limites(reintentos_salida=1))
    assert r.terminacion in ("salida_invalida", "rechazada_verificador")
    assert r.reintentos >= 1                  # el validador devolvió el motivo al modelo


def test_json_roto_agota_reintentos_de_estructura(repo, permisos):
    r, _ = correr(repo, permisos, sol(), "json_roto", limites=Limites(reintentos_salida=2))
    assert r.terminacion == "salida_invalida" and r.reintentos >= 2


def test_limite_de_solicitudes(repo, permisos):
    r, _ = correr(repo, permisos, sol(), limites=Limites(solicitudes_modelo=2))
    assert r.terminacion == "limite_excedido"


def test_sigue_inyeccion_la_herramienta_deniega_y_se_audita(permisos):
    r, srv = correr(escenario("inyeccion"), permisos, sol(), "sigue_inyeccion")
    denegados = [e for e in srv.auditoria.eventos if e["resultado"].get("codigo_error") == "corpus_no_autorizado"]
    assert denegados and denegados[0]["argumentos"]["corpus"] == "privado"
    assert r.terminacion == "salida_final" and r.salida.ganador == "B"      # la tarea no se desvió


def test_fallo_de_infraestructura_se_trata_y_registra(repo, permisos):
    class Roto(ServicioResultados):
        def obtener_resultados(self, *a, **k):
            from asr_asistente.dominio import ErrorInfraestructura
            raise ErrorInfraestructura("fichero de datos corrupto")
    deps = DepsAsistente(servicio=Roto(repo, permisos, Auditoria()), limites=Limites())
    agente = construir_agente(modelo_doble_pydantic(PlanDoble(sol())), "base", deps)
    r = asyncio.run(ejecutar_agente(agente, "p", deps, "x", "t", real=False))
    assert r.terminacion == "fallo_infraestructura" and "corrupto" in r.error and r.salida is None


def test_variante_verificada_corrige_un_fallo_inyectado(repo, permisos):
    """Fallo INYECTADO (doble que miente una vez): ``base`` lo descarta; ``verificada`` lo corrige con el motivo."""
    def ejecutar(variante):
        servicio = ServicioResultados(repo, permisos, Auditoria())
        deps = DepsAsistente(servicio=servicio, limites=Limites())
        agente = construir_agente(modelo_doble_pydantic(PlanDoble(sol(), "wer_falso", corrige_tras_reintento=True)),
                                  variante, deps)
        return asyncio.run(ejecutar_agente(agente, "p", deps, "x", "t", variante, real=False))
    base, verificada = ejecutar("base"), ejecutar("verificada")
    assert base.terminacion == "rechazada_verificador" and base.salida is None
    assert verificada.terminacion == "salida_final" and verificada.salida.ganador == "B" and verificada.reintentos == 1


def test_salida_prompted_valida_el_json_en_texto(repo, permisos):
    """v2: el modelo entrega el JSON como texto y Pydantic AI lo valida contra la MISMA unión discriminada."""
    servicio = ServicioResultados(repo, permisos, Auditoria())
    deps = DepsAsistente(servicio=servicio, limites=Limites())
    for solicitud, esperado in [(sol(), ("comparacion", "B")), (sol(sistemas="AD"), ("datos_insuficientes", None))]:
        agente = construir_agente(modelo_doble_pydantic(PlanDoble(solicitud)), "base", deps, salida="prompted")
        r = asyncio.run(ejecutar_agente(agente, "p", deps, "x", "t", real=False))
        assert r.terminacion == "salida_final" and r.salida.estado == esperado[0] and (esperado[1] is None or r.salida.ganador == "B")


def test_reintentos_de_la_salida_prompted_se_cuentan(repo, permisos):
    """Corrección de métrica: los reintentos del modo prompted no usan RetryPromptPart y se contaban como 0."""
    from pydantic_ai.messages import ModelResponse, TextPart
    from pydantic_ai.models.function import FunctionModel
    n = {"i": 0}

    def modelo(messages, info):
        n["i"] += 1
        if n["i"] == 1:
            return ModelResponse(parts=[TextPart("esto no es json")])
        return ModelResponse(parts=[TextPart('{"estado":"datos_insuficientes","motivo":"idioma_no_indicado","detalle":"x","pregunta_aclaracion":"¿idioma?"}')])
    deps = DepsAsistente(servicio=ServicioResultados(repo, permisos, Auditoria()), limites=Limites())
    agente = construir_agente(FunctionModel(modelo), "base", deps, salida="prompted")
    r = asyncio.run(ejecutar_agente(agente, "p", deps, "x", "t", real=False))
    assert r.terminacion == "salida_final" and r.reintentos == 1 and r.solicitudes_modelo == 2
    assert [e["tipo"] for e in r.traza].count("reintento") == 1
