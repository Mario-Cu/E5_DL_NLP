"""Configuración 4: Pydantic AI como *host* + cliente MCP, con el servidor ``servidor_mcp`` por stdio.

Roles (se explican en la memoria):

* **host**: esta aplicación (el proceso que contiene el agente Pydantic AI y decide qué recursos y prompts usa);
* **cliente MCP**: ``MCPToolset`` (una sesión por servidor; traduce las tools MCP a herramientas del agente);
* **servidor MCP**: ``asr_asistente.servidor_mcp`` (subproceso); impone el control de acceso y audita.

El host lee el *resource* ``asr://politica-evaluacion`` por el cliente, comprueba por hash que es el mismo
texto que usan las otras configuraciones y lo añade a las instrucciones. El *prompt* ``comparar_por_idioma``
no se usa en las ejecuciones evaluadas (la pregunta del usuario es texto libre y debe ser idéntica en todas
las configuraciones); se ejercita en la prueba de descubrimiento sin LLM.

Fallos de transporte: si el servidor se cae o no responde (timeout), se reintenta como máximo
``reintentos_transporte`` veces con espera exponencial y dentro de un plazo total; si no se recupera, la
ejecución termina de forma controlada con ``fallo_transporte`` (nunca se inventa una respuesta).
"""
from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import Any

from pydantic_ai.mcp import MCPToolset
from fastmcp.exceptions import ToolError
from pydantic_ai import ModelRetry
from pydantic_ai.exceptions import UnexpectedModelBehavior, UsageLimitExceeded
from pydantic_ai.usage import RunUsage, UsageLimits

from ..cliente_mcp import transporte_stdio
from ..herramientas import Auditoria
from ..politica import POLITICA_EVALUACION, hash_politica, instrucciones_completas
from .comun import DepsAsistente, ResultadoEjecucion, registro
from .errores import clasificar_excepcion
from .pydantic_local import construir_agente, contar_reintentos, traza_desde_mensajes
from ..verificador import verificar_coherencia

URI_POLITICA = "asr://politica-evaluacion"


def _texto(recurso: Any) -> str:
    if isinstance(recurso, str):
        return recurso
    if isinstance(recurso, list):
        return "".join(x for x in recurso if isinstance(x, str))
    return str(recurso)


async def _rechazo_de_herramienta(ctx, llamar, nombre, argumentos):
    """Un rechazo del SERVIDOR a una llamada mal formada (p. ej. falta un argumento) es un error que el
    modelo puede corregir (→ ``ModelRetry``). Las caídas y los timeouts (``MCPError``) NO se tratan aquí:
    se propagan como fallo de transporte para no confundirlos con un error del modelo."""
    try:
        return await llamar(nombre, argumentos)
    except ToolError as exc:
        raise ModelRetry(f"La herramienta {nombre} rechazó la llamada: {exc}")


async def ejecutar_mcp(model: Any, pregunta: str, deps: DepsAsistente, config: str, caso: str,
                       variante: str = "base", salida: str = "tool", ruta_auditoria: str | Path | None = None,
                       datos: str | Path | None = None, extra_servidor: list[str] | None = None,
                       ajustes: Any = None, real: bool = True) -> ResultadoEjecucion:
    lim = deps.limites
    res = ResultadoEjecucion(config=config, caso=caso, pregunta=pregunta)
    uso = RunUsage()
    mensajes: list = []
    t_inicio = time.perf_counter()
    espera = lim.espera_inicial_s
    intento = 0
    ultimo_error = ""
    while True:
        intento += 1
        corrida: dict[str, Any] = {}
        try:
            restante = lim.plazo_total_s - (time.perf_counter() - t_inicio)
            if restante <= 0:
                res.terminacion, res.error = "plazo_excedido", f"más de {lim.plazo_total_s}s"
                break
            tr = transporte_stdio(auditoria=ruta_auditoria, datos=datos,
                                  corpus_autorizados=",".join(sorted(deps.permisos.corpus_autorizados)),
                                  extra=extra_servidor)
            toolset = MCPToolset(tr, init_timeout=lim.tiempo_herramienta_s, read_timeout=lim.tiempo_herramienta_s,
                                 tool_error_behavior="error", process_tool_call=_rechazo_de_herramienta)  # un fallo de transporte NO se disfraza de error corregible por el modelo

            async def _correr():
                t0 = time.perf_counter()
                async with toolset:
                    politica = _texto(await toolset.read_resource(URI_POLITICA))
                    res.extra["arranque_mcp_s"] = round(time.perf_counter() - t0, 4)
                    res.extra["politica_igual_a_local"] = hash_politica(politica) == hash_politica(POLITICA_EVALUACION)
                    res.extra["servidor"] = str(getattr(toolset, "server_info", ""))[:200]
                    agente = construir_agente(model, variante, deps, toolsets=[toolset], con_herramientas_locales=False,
                                              ajustes=ajustes, texto_instrucciones=instrucciones_completas(politica),
                                              salida=salida)
                    async with agente.iter(pregunta, deps=deps, usage=uso,
                                           usage_limits=UsageLimits(request_limit=lim.solicitudes_modelo,
                                                                    tool_calls_limit=lim.llamadas_herramienta)) as ejec:
                        corrida["ejec"] = ejec
                        async for _ in ejec:
                            pass
                        return ejec.result

            resultado = await asyncio.wait_for(_correr(), timeout=restante)
            res.salida = resultado.output
            res.texto_salida = res.salida.model_dump_json()
            mensajes = corrida["ejec"].all_messages()
            res.terminacion, res.error = "salida_final", None
            break
        except UsageLimitExceeded as exc:
            res.terminacion, res.error = "limite_excedido", str(exc)
            break
        except UnexpectedModelBehavior as exc:
            res.terminacion, res.error = "salida_invalida", str(exc)
            if corrida.get("ejec") is not None:
                mensajes = corrida["ejec"].all_messages()
            break
        except asyncio.TimeoutError:
            res.terminacion, res.error = "plazo_excedido", f"más de {lim.plazo_total_s}s"
            break
        except BaseException as exc:  # noqa: BLE001
            if isinstance(exc, (KeyboardInterrupt, SystemExit)):
                raise
            terminacion, msg = clasificar_excepcion(exc)
            if corrida.get("ejec") is not None:
                mensajes = corrida["ejec"].all_messages()
            if terminacion == "fallo_transporte" and intento <= lim.reintentos_transporte:
                registro.warning("fallo de transporte MCP (intento %s): %s; reintento en %.1fs", intento, msg, espera)
                res.reintentos_transporte += 1
                res.extra.setdefault("fallos_transporte", []).append(msg[:300])
                await asyncio.sleep(espera)
                espera *= 2
                continue
            res.terminacion, res.error = terminacion, msg
            if terminacion == "fallo_transporte":
                res.extra.setdefault("fallos_transporte", []).append(msg[:300])
                registro.error("fallo de transporte MCP sin recuperar tras %s intentos: %s", intento, msg)
            break

    res.tiempo_s = round(time.perf_counter() - t_inicio, 4)
    res.solicitudes_modelo = uso.requests
    res.llamadas_herramienta = uso.tool_calls
    if real:
        res.tokens_entrada, res.tokens_salida = uso.input_tokens, uso.output_tokens
    res.reintentos = contar_reintentos(mensajes)
    res.traza = traza_desde_mensajes(mensajes)
    if ruta_auditoria:
        res.extra["eventos_auditoria"] = Auditoria.leer(ruta_auditoria)

    if res.salida is not None:
        ver = verificar_coherencia(res.salida, deps.repo, deps.permisos)
        res.detalle_verificador = ver.codigos()
        if not ver.ok:
            res.terminacion, res.error = "rechazada_verificador", ver.texto()
            res.extra["salida_descartada"] = res.salida.model_dump(mode="json")
            res.salida = None
    return res
