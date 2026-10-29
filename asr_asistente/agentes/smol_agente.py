"""Configuración 2: smolagents ``ToolCallingAgent`` con las MISMAS herramientas que las otras configuraciones.

Por qué ``ToolCallingAgent`` y no ``CodeAgent`` (decisión completa y alternativa analizada en la memoria):

* Las dos herramientas son consultas cortas con argumentos simples y salida JSON; no hay bucles,
  agregaciones ni composición de herramientas que justifiquen generar código.
* El agente de herramientas emite llamadas estructuradas (nombre + argumentos con tipos) que el programa
  valida y registra antes de ejecutar; el modelo no ejecuta nada propio. Con ``CodeAgent`` el modelo escribiría
  Python que habría que ejecutar y eso exige un entorno aislado (Docker/E2B/WASM) y limitar los imports.
* El coste es menos flexibilidad: si hiciera falta comparar muchos sistemas o idiomas en una sola acción,
  un ``CodeAgent`` podría hacerlo en un paso con un bucle (ver memoria, apartado de la alternativa).

La respuesta final se valida con ``final_answer_checks`` contra el mismo esquema (unión discriminada) que
usa Pydantic AI; así la paridad estructural es explícita. La coherencia con la evidencia la comprueba el
mismo ``verificador`` que en las demás configuraciones (puerta final de la aplicación).
"""
from __future__ import annotations

import concurrent.futures
import json
import time
from typing import Any

from pydantic import ValidationError
from smolagents import Tool, ToolCallingAgent

from ..contratos import ADAPTADOR_SALIDA, validar_salida
from ..herramientas import DESCRIPCIONES, PARAMETROS, ServicioResultados
from ..verificador import verificar_coherencia
from .comun import DepsAsistente, NO_DISPONIBLE, ResultadoEjecucion, a_json, instrucciones, registro
from .errores import clasificar_excepcion

ESQUEMA_SALIDA = json.dumps(ADAPTADOR_SALIDA.json_schema(), ensure_ascii=False, separators=(",", ":"))


def crear_herramientas(servicio: ServicioResultados) -> list[Tool]:
    class ListarSistemas(Tool):
        name = "listar_sistemas"
        description = DESCRIPCIONES["listar_sistemas"]
        inputs = {
            "corpus": {"type": "string", "description": PARAMETROS["corpus"]},
            "idioma": {"type": "string", "description": PARAMETROS["idioma"]},
        }
        output_type = "string"

        def forward(self, corpus: str, idioma: str) -> str:
            return servicio.listar_sistemas(corpus, idioma).model_dump_json()

    class ObtenerResultados(Tool):
        name = "obtener_resultados"
        description = DESCRIPCIONES["obtener_resultados"]
        inputs = {
            "corpus": {"type": "string", "description": PARAMETROS["corpus"]},
            "idioma": {"type": "string", "description": PARAMETROS["idioma"]},
            "sistema": {"type": "string", "description": PARAMETROS["sistema"]},
        }
        output_type = "string"

        def forward(self, corpus: str, idioma: str, sistema: str) -> str:
            return servicio.obtener_resultados(corpus, idioma, sistema).model_dump_json()

    class RespuestaFinal(Tool):
        name = "final_answer"
        description = ("Entrega la respuesta final. `answer` debe ser UN objeto JSON que cumpla este esquema "
                       "(unión discriminada por `estado`: 'comparacion' o 'datos_insuficientes'): " + ESQUEMA_SALIDA)
        inputs = {"answer": {"type": "object", "description": "Objeto JSON con la salida estructurada."}}
        output_type = "any"

        def forward(self, answer: Any) -> Any:
            return answer

    return [ListarSistemas(), ObtenerResultados(), RespuestaFinal()]


def comprobar_esquema(respuesta: Any, memoria=None, agent=None) -> bool:
    """``final_answer_checks``: si la estructura no cumple el contrato, el agente recibe el error y reintenta."""
    try:
        validar_salida(respuesta)
    except ValidationError as exc:
        raise ValueError("La respuesta no cumple el esquema: " +
                         "; ".join(f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors()[:6]))
    return True


def _comprobar_coherencia(deps: DepsAsistente):
    """Variante «verificada»: el verificador de la aplicación se ejecuta DENTRO del bucle (como ``final_answer_check``)
    y, si falla, el agente recibe el motivo y puede corregirse dentro del límite de pasos."""
    def comprobar_coherencia(respuesta: Any, memoria=None, agent=None) -> bool:
        ver = verificar_coherencia(validar_salida(respuesta), deps.repo, deps.permisos)
        if not ver.ok:
            raise ValueError("La respuesta no coincide con la evidencia de las herramientas: " + ver.texto() +
                             ". Corrígela usando solo los datos devueltos por las herramientas.")
        return True
    return comprobar_coherencia


def construir_agente(model: Any, deps: DepsAsistente, variante: str = "base") -> ToolCallingAgent:
    assert variante in ("base", "verificada")
    checks = [comprobar_esquema] + ([_comprobar_coherencia(deps)] if variante == "verificada" else [])
    return ToolCallingAgent(
        tools=crear_herramientas(deps.servicio), model=model, max_steps=deps.limites.pasos_smolagents,
        instructions=instrucciones(deps), final_answer_checks=checks, verbosity_level=0)


def _pasos_a_traza(pasos) -> tuple[list[dict], int, int, int]:
    """(traza, solicitudes_modelo, llamadas_herramienta, reintentos)."""
    from smolagents.memory import ActionStep

    traza: list[dict] = []
    solicitudes = llamadas = reintentos = 0
    for p in pasos:
        if not isinstance(p, ActionStep):
            continue
        solicitudes += 1
        for tc in (p.tool_calls or []):
            es_final = tc.name == "final_answer"
            if not es_final:
                llamadas += 1
            traza.append({"tipo": "llamada", "destino": "salida_final" if es_final else "herramienta",
                          "nombre": tc.name, "argumentos": tc.arguments})
        if p.error is not None:
            reintentos += 1
            traza.append({"tipo": "reintento", "contenido": str(p.error)[:800]})
        elif p.observations:
            traza.append({"tipo": "observacion", "contenido": str(p.observations)[:2500]})
    return traza, solicitudes, llamadas, reintentos


def ejecutar_smolagents(model: Any, pregunta: str, deps: DepsAsistente, config: str, caso: str,
                        real: bool = True, variante: str = "base") -> ResultadoEjecucion:
    res = ResultadoEjecucion(config=config, caso=caso, pregunta=pregunta)
    agente = construir_agente(model, deps, variante)
    t0 = time.perf_counter()
    resultado = None
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        futuro = pool.submit(lambda: agente.run(pregunta, return_full_result=True, max_steps=deps.limites.pasos_smolagents))
        try:
            resultado = futuro.result(timeout=deps.limites.plazo_total_s)
        except concurrent.futures.TimeoutError:
            res.terminacion, res.error = "plazo_excedido", f"más de {deps.limites.plazo_total_s}s"
        except Exception as exc:  # noqa: BLE001
            res.terminacion, res.error = clasificar_excepcion(exc)
            registro.error("fallo no esperado (%s): %s", res.terminacion, exc)
    res.tiempo_s = round(time.perf_counter() - t0, 4)

    pasos = list(agente.memory.steps)
    res.traza, res.solicitudes_modelo, res.llamadas_herramienta, res.reintentos = _pasos_a_traza(pasos)
    # smolagents hace una solicitud extra cuando agota los pasos (respuesta final forzada)
    if resultado is not None:
        if real and resultado.token_usage is not None:
            res.tokens_entrada, res.tokens_salida = resultado.token_usage.input_tokens, resultado.token_usage.output_tokens
        if resultado.state == "max_steps_error":
            res.terminacion, res.error = "limite_excedido", f"se agotaron los {deps.limites.pasos_smolagents} pasos"
        else:
            try:
                res.salida = validar_salida(resultado.output)
                res.texto_salida = res.salida.model_dump_json()
                res.terminacion = "salida_final"
            except (ValidationError, ValueError) as exc:
                res.terminacion, res.error = "salida_invalida", str(exc)[:500]
                res.texto_salida = a_json(resultado.output, 1500)
    if res.salida is not None:
        ver = verificar_coherencia(res.salida, deps.repo, deps.permisos)
        res.detalle_verificador = ver.codigos()
        if not ver.ok:
            res.terminacion, res.error = "rechazada_verificador", ver.texto()
            res.extra["salida_descartada"] = res.salida.model_dump(mode="json")
            res.salida = None
    return res
