"""Configuración 3: Pydantic AI con herramientas locales (funciones Python que llaman al dominio).

Qué hace Pydantic AI aquí: validar la salida contra la unión discriminada (``output_type``), reintentar
ante salidas inválidas, inyectar dependencias (``deps_type``) y limitar el uso (``UsageLimits``).
Qué NO hace: decidir si las cifras son ciertas. Eso lo hace ``verificador`` (código de la aplicación):

* variante ``base``: la verificación se aplica DESPUÉS de la ejecución; si falla, la aplicación
  descarta la salida (``rechazada_verificador``) en vez de entregarla.
* variante ``verificada``: la verificación está dentro del bucle (``output_validator`` → ``ModelRetry``)
  y le devuelve al modelo el motivo para que se corrija dentro del presupuesto de reintentos.
"""
from __future__ import annotations

import asyncio
import time
from typing import Annotated, Any

from pydantic import Field
from pydantic import ValidationError
from pydantic_ai import Agent, ModelRetry, RunContext, TextOutput
from pydantic_ai.exceptions import UnexpectedModelBehavior, UsageLimitExceeded
from pydantic_ai.messages import ModelResponse, RetryPromptPart, TextPart, ToolCallPart, ToolReturnPart, UserPromptPart
from pydantic_ai.usage import RunUsage, UsageLimits
from pydantic_core import to_jsonable_python

from ..contratos import Comparacion, DatosInsuficientes, SalidaAsistente, esquema_compacto, validar_salida
from ..dominio import ErrorInfraestructura
from ..herramientas import DESCRIPCIONES, PARAMETROS, ListadoSistemas, ResultadoConsulta
from ..verificador import verificar_coherencia
from .comun import (DepsAsistente, NO_DISPONIBLE, Cronometro, ResultadoEjecucion, a_json, instrucciones, registro)


def _parsear_texto(texto: str) -> Comparacion | DatosInsuficientes:
    """Salida «prompted»: el modelo escribe el JSON como texto; se valida contra la MISMA unión discriminada."""
    t = texto.strip()
    if t.startswith("```"):
        t = t.strip("`").removeprefix("json").strip()
    try:
        return validar_salida(t)
    except ValidationError as exc:
        errores = "; ".join(f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors()[:6])
        raise ModelRetry("Tu respuesta no cumple el esquema (" + errores + "). Responde SOLO con un objeto JSON válido.")


def _anade_formato(base, salida: str):
    if salida != "prompted":
        return base
    extra = ("\n\nFORMATO DE LA RESPUESTA FINAL: cuando termines de consultar, responde SOLO con un objeto JSON "
             "(sin texto antes o después, sin ```) que cumpla este esquema (unión discriminada por `estado`):\n"
             + esquema_compacto())
    return (lambda ctx: base(ctx) + extra) if callable(base) else base + extra


def construir_agente(model: Any, variante: str = "base", deps: DepsAsistente | None = None,
                     toolsets: list | None = None, con_herramientas_locales: bool = True,
                     ajustes: Any = None, texto_instrucciones: str | None = None, salida: str = "tool",
                     process_tool_call: Any = None) -> Agent:
    """``salida``: 'tool' = herramienta de salida por miembro de la unión (v1);
    'prompted' = el modelo escribe el JSON en texto y Pydantic AI lo valida contra la misma unión (v2)."""
    assert variante in ("base", "verificada") and salida in ("tool", "prompted")
    limites = (deps.limites if deps else None)
    from ..politica import LIMITES
    limites = limites or LIMITES
    agente: Agent = Agent(
        model, deps_type=DepsAsistente,
        output_type=SalidaAsistente if salida == "tool" else TextOutput(_parsear_texto),
        instructions=_anade_formato(
            texto_instrucciones if texto_instrucciones is not None else (lambda ctx: instrucciones(ctx.deps)), salida),
        retries=limites.reintentos_salida, toolsets=toolsets, model_settings=ajustes)

    if con_herramientas_locales:
        def listar_sistemas(ctx: RunContext[DepsAsistente],
                            corpus: Annotated[str, Field(description=PARAMETROS["corpus"])],
                            idioma: Annotated[str, Field(description=PARAMETROS["idioma"])]) -> ListadoSistemas:
            return ctx.deps.servicio.listar_sistemas(corpus, idioma)

        def obtener_resultados(ctx: RunContext[DepsAsistente],
                               corpus: Annotated[str, Field(description=PARAMETROS["corpus"])],
                               idioma: Annotated[str, Field(description=PARAMETROS["idioma"])],
                               sistema: Annotated[str, Field(description=PARAMETROS["sistema"])]) -> ResultadoConsulta:
            return ctx.deps.servicio.obtener_resultados(corpus, idioma, sistema)

        # Misma descripción y mismos argumentos descritos que en smolagents y MCP (comparación justa).
        agente.tool(listar_sistemas, description=DESCRIPCIONES["listar_sistemas"])
        agente.tool(obtener_resultados, description=DESCRIPCIONES["obtener_resultados"])

    if variante == "verificada":
        @agente.output_validator
        def _verificar(ctx: RunContext[DepsAsistente], salida: Comparacion | DatosInsuficientes):
            ver = verificar_coherencia(salida, ctx.deps.repo, ctx.deps.permisos)
            if not ver.ok:
                raise ModelRetry("La salida no coincide con la evidencia de las herramientas: " + ver.texto() +
                                 ". Corrígela usando solo los datos devueltos por las herramientas.")
            return salida

    return agente


# --------------------------------------------------------------------------- #
def traza_desde_mensajes(mensajes) -> list[dict]:
    traza: list[dict] = []
    for m in mensajes:
        for p in m.parts:
            if isinstance(p, ToolCallPart):
                destino = "salida_final" if p.tool_name.startswith("final_result") else "herramienta"
                traza.append({"tipo": "llamada", "destino": destino, "nombre": p.tool_name,
                              "argumentos": to_jsonable_python(p.args_as_dict() if hasattr(p, "args_as_dict") else p.args)})
            elif isinstance(p, ToolReturnPart):
                if getattr(p, "outcome", None) == "retried":
                    traza.append({"tipo": "reintento", "nombre": p.tool_name, "contenido": _acorta(p.content)})
                elif p.tool_name.startswith("final_result"):
                    traza.append({"tipo": "resultado", "nombre": p.tool_name, "contenido": _acorta(p.content)})
                else:
                    traza.append({"tipo": "observacion", "nombre": p.tool_name, "contenido": _acorta(p.content)})
            elif isinstance(p, RetryPromptPart):
                traza.append({"tipo": "reintento", "nombre": p.tool_name, "contenido": _acorta(p.content)})
            elif es_reintento_de_texto(p):
                traza.append({"tipo": "reintento", "nombre": "salida_texto", "contenido": _acorta(p.content)})
            elif isinstance(p, TextPart) and p.content.strip():
                traza.append({"tipo": "texto_modelo", "contenido": _acorta(p.content)})
    return traza


def _acorta(x) -> Any:
    j = to_jsonable_python(x)
    return j if len(a_json(j)) < 2500 else a_json(j, 2500)


def es_reintento_de_texto(p) -> bool:
    """Reintentos de la salida «prompted»: Pydantic AI los representa con ``RetryFeedbackPart`` (nuestro ``ModelRetry``)
    o con un mensaje de usuario automático («Your previous response failed…»), no con ``RetryPromptPart``."""
    if type(p).__name__ == "RetryFeedbackPart":
        return True
    return isinstance(p, UserPromptPart) and isinstance(p.content, str) and p.content.startswith("Your previous response failed")


def contar_reintentos(mensajes) -> int:
    return sum(isinstance(p, RetryPromptPart) or getattr(p, "outcome", None) == "retried" or es_reintento_de_texto(p)
               for m in mensajes for p in m.parts)


async def ejecutar_agente(agente: Agent, pregunta: str, deps: DepsAsistente, config: str, caso: str,
                          variante: str = "base", real: bool = True) -> ResultadoEjecucion:
    """Ejecuta una vez con límites, mide, y clasifica el final de la ejecución (sin excepciones sin tratar)."""
    lim = deps.limites
    res = ResultadoEjecucion(config=config, caso=caso, pregunta=pregunta)
    uso = RunUsage()
    mensajes: list = []
    t0 = time.perf_counter()
    corrida: dict[str, Any] = {}

    async def _correr():
        async with agente:
            async with agente.iter(pregunta, deps=deps, usage=uso,
                                   usage_limits=UsageLimits(request_limit=lim.solicitudes_modelo,
                                                            tool_calls_limit=lim.llamadas_herramienta)) as ejec:
                corrida["ejec"] = ejec            # se conserva para poder leer el historial aunque falle
                async for _ in ejec:
                    pass
                return ejec.result

    try:
        resultado = await asyncio.wait_for(_correr(), timeout=lim.plazo_total_s)
        res.salida = resultado.output
        res.texto_salida = res.salida.model_dump_json()
    except UsageLimitExceeded as exc:
        res.terminacion, res.error = "limite_excedido", str(exc)
    except UnexpectedModelBehavior as exc:
        res.terminacion, res.error = "salida_invalida", str(exc)
    except asyncio.TimeoutError:
        res.terminacion, res.error = "plazo_excedido", f"más de {lim.plazo_total_s}s"
    except ErrorInfraestructura as exc:
        res.terminacion, res.error = "fallo_infraestructura", str(exc)
        registro.error("fallo de infraestructura: %s", exc)
    except Exception as exc:  # noqa: BLE001 - se clasifica y se registra; no se oculta
        from .errores import clasificar_excepcion
        res.terminacion, res.error = clasificar_excepcion(exc)
        registro.error("fallo no esperado (%s): %s", res.terminacion, exc)
    res.tiempo_s = round(time.perf_counter() - t0, 4)
    if corrida.get("ejec") is not None:
        mensajes = corrida["ejec"].all_messages()
    res.solicitudes_modelo = uso.requests
    res.llamadas_herramienta = uso.tool_calls
    if real:
        res.tokens_entrada, res.tokens_salida = uso.input_tokens, uso.output_tokens
    res.reintentos = contar_reintentos(mensajes)
    res.traza = traza_desde_mensajes(mensajes)

    if res.salida is not None:   # puerta final de la aplicación (en ``verificada`` ya pasó dentro del bucle)
        ver = verificar_coherencia(res.salida, deps.repo, deps.permisos)
        res.detalle_verificador = ver.codigos()
        if not ver.ok:
            res.terminacion, res.error = "rechazada_verificador", ver.texto()
            res.extra["salida_descartada"] = res.salida.model_dump(mode="json")
            res.salida = None
    return res
