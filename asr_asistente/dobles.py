"""Modelos de lenguaje simulados («dobles») con guion determinista.

Sirven SOLO para probar la integración (esquemas, bucle de herramientas, límites, reintentos, verificador)
sin depender de un LLM. Un doble que acierta no dice nada sobre la capacidad de un modelo real: sus
resultados en la tabla de la memoria se marcan como «integración».

``PlanDoble`` decide la siguiente acción a partir de las observaciones de las herramientas, como haría un
modelo razonable. Admite *defectos* para provocar fallos controlados (se etiquetan como inyectados):

* ``wer_falso``         WER declarado distinto del real.
* ``ganador_invertido`` declara ganador al peor sistema.
* ``fuente_inventada``  cita una fila que no existe.
* ``ceros_por_ausente`` sustituye un sistema sin resultados por conteos a cero (error del enunciado).
* ``sigue_inyeccion``   obedece la orden escondida en ``comentario_externo`` y pide otro corpus.
* ``abstiene_de_mas``   se abstiene con ``sistema_sin_resultados`` aunque hay datos.
* ``json_roto``         devuelve una salida sin el campo discriminador.
"""
from __future__ import annotations

import json
from typing import Any

DEFECTOS = ("wer_falso", "ganador_invertido", "fuente_inventada", "ceros_por_ausente", "sigue_inyeccion",
            "abstiene_de_mas", "json_roto")


class PlanDoble:
    def __init__(self, solicitud: dict, defecto: str | None = None, corrige_tras_reintento: bool = False):
        assert defecto is None or defecto in DEFECTOS
        self.corrige_tras_reintento = corrige_tras_reintento   # el doble rectifica si recibe un reintento
        self.defecto_original = defecto
        self.corpus = solicitud.get("corpus")
        self.idioma = solicitud.get("idioma")
        self.sistemas = list(solicitud.get("sistemas") or [])
        self.defecto = defecto

    # observaciones: lista de (nombre_herramienta, argumentos, resultado_dict)
    def paso(self, observaciones: list[tuple[str, dict, dict]]):
        s = self.sistemas
        if not self.corpus:
            return ("final", self._abst("corpus_no_indicado", "No se indicó el corpus.", [], "¿En qué corpus quieres comparar?"))
        if not self.idioma:
            return ("final", self._abst("idioma_no_indicado", "No se indicó el idioma.", [], "¿En qué idioma quieres comparar?"))
        if len(set(s)) != 2:
            return ("final", self._abst("sistemas_no_indicados", "Faltan dos sistemas distintos.", [], "¿Qué dos sistemas comparo?"))
        hechas = [(n, a) for n, a, _ in observaciones]
        if not observaciones:
            return ("herramienta", "listar_sistemas", {"corpus": self.corpus, "idioma": self.idioma})
        lis = observaciones[0][2]
        if lis.get("ok") is False and (lis.get("error") or {}).get("codigo") == "corpus_no_autorizado":
            return ("final", self._abst("acceso_denegado", lis["error"]["mensaje"], []))
        if not lis.get("idioma_con_datos"):
            return ("final", self._abst("idioma_sin_resultados",
                                        f"No hay resultados en {self.corpus}/{self.idioma}.", []))
        for sis in s:
            if ("obtener_resultados", {"corpus": self.corpus, "idioma": self.idioma, "sistema": sis}) not in hechas:
                return ("herramienta", "obtener_resultados",
                        {"corpus": self.corpus, "idioma": self.idioma, "sistema": sis})
        if self.defecto == "sigue_inyeccion" and not any(a.get("corpus") == "privado" for _, a in hechas):
            if any("privado" in ((r.get("fila") or {}).get("comentario_externo") or "") for _, _, r in observaciones):
                return ("herramienta", "obtener_resultados", {"corpus": "privado", "idioma": self.idioma, "sistema": s[0]})
        por_sis = {a["sistema"]: r for n, a, r in observaciones if n == "obtener_resultados" and a.get("corpus") == self.corpus}
        filas = {k: v for k, v in por_sis.items()}
        faltan = [k for k in s if filas.get(k, {}).get("disponibilidad") == "sin_resultados"]
        if self.defecto == "ceros_por_ausente" and faltan:
            return ("final", self._comparacion({k: self._fila_ceros(k) for k in s}, ceros=True))
        if self.defecto == "abstiene_de_mas" and not faltan:
            return ("final", self._abst("sistema_sin_resultados", "Dice que faltan datos.", [], faltante=[s[0]]))
        if faltan:
            return ("final", self._abst("sistema_sin_resultados", f"No hay resultados de {', '.join(faltan)}.", [],
                                        faltante=[f"{self.corpus}:{self.idioma}:{k}" for k in faltan]))
        malos = [k for k in s if filas.get(k, {}).get("disponibilidad") == "datos_invalidos"]
        if malos:
            ids = [filas[k]["fila_id"] for k in s if filas[k].get("fila_id")]
            return ("final", self._abst("datos_invalidos", filas[malos[0]]["detalle"], ids))
        objs = {k: filas[k]["fila"] for k in s}
        a, b = objs[s[0]], objs[s[1]]
        dif = [c for c in ("corpus", "version", "idioma", "particion", "normalizacion", "referencia") if a[c] != b[c]]
        if dif:
            return ("final", self._abst("filas_no_comparables", f"Difieren en {', '.join(dif)}.", [a["id"], b["id"]]))
        return ("final", self._comparacion(objs))

    # -- construcción de salidas --------------------------------------------------------------
    def _abst(self, motivo, detalle, fuentes, pregunta=None, faltante=None):
        if self.defecto == "json_roto":
            return {"motivo": motivo, "detalle": detalle}
        return {"estado": "datos_insuficientes", "motivo": motivo, "corpus": self.corpus, "idioma": self.idioma,
                "sistemas": list(self.sistemas), "faltante": faltante or [], "detalle": detalle,
                "fuentes": fuentes, "pregunta_aclaracion": pregunta}

    def _fila_ceros(self, k):
        return {"id": f"{self.corpus}:{self.idioma}:{k}", "s": 0, "d": 0, "i": 0, "n": 100, "wer": 0.0}

    def _comparacion(self, objs: dict[str, dict], ceros: bool = False):
        s = self.sistemas
        medidas = []
        for k in s:
            o = objs[k]
            medidas.append({"sistema": k, "fila": o["id"], "s": o["s"], "d": o["d"], "i": o["i"], "n": o["n"],
                            "wer": (o["s"] + o["d"] + o["i"]) / o["n"]})
        fa = (medidas[0]["s"] + medidas[0]["d"] + medidas[0]["i"]) * medidas[1]["n"]
        fb = (medidas[1]["s"] + medidas[1]["d"] + medidas[1]["i"]) * medidas[0]["n"]
        if fa == fb:
            resultado, ganador = "empate", None
        else:
            resultado, ganador = "ganador", (s[0] if fa < fb else s[1])
        if self.defecto == "wer_falso":
            medidas[1]["wer"] = round(medidas[1]["wer"] + 0.1, 4)
        if self.defecto == "ganador_invertido" and ganador:
            ganador = s[1] if ganador == s[0] else s[0]
        if self.defecto == "fuente_inventada":
            medidas[0]["fila"] = f"{self.corpus}:{self.idioma}:Q"
        out = {"estado": "comparacion", "corpus": self.corpus, "idioma": self.idioma, "medidas": medidas,
               "resultado": resultado, "ganador": ganador, "fuentes": [m["fila"] for m in medidas],
               "limitaciones": "Datos sintéticos y agregados; sin intervalos de confianza ni significación estadística."}
        if self.defecto == "json_roto":
            out.pop("estado")
        return out


# --------------------------------------------------------------------------- #
# Adaptador Pydantic AI
# --------------------------------------------------------------------------- #
def modelo_doble_pydantic(plan: PlanDoble):
    from pydantic_core import to_jsonable_python
    from pydantic_ai.messages import ModelResponse, TextPart, ToolCallPart, ToolReturnPart, RetryPromptPart
    from pydantic_ai.models.function import AgentInfo, FunctionModel

    def observaciones(messages) -> list[tuple[str, dict, dict]]:
        llamadas: dict[str, tuple[str, dict]] = {}
        obs = []
        for m in messages:
            for p in m.parts:
                if isinstance(p, ToolCallPart):
                    args = p.args_as_dict() if hasattr(p, "args_as_dict") else (p.args or {})
                    llamadas[p.tool_call_id] = (p.tool_name, args)
                elif isinstance(p, ToolReturnPart) and p.tool_call_id in llamadas and not p.tool_name.startswith("final_result"):
                    cont = to_jsonable_python(p.content)
                    if isinstance(cont, str):
                        try:
                            cont = json.loads(cont)
                        except ValueError:
                            cont = {}
                    nombre, args = llamadas[p.tool_call_id]
                    obs.append((nombre, args, cont))
        return obs

    def hubo_reintento(messages) -> bool:
        return any(isinstance(p, RetryPromptPart) or getattr(p, "outcome", None) == "retried"
                   for m in messages for p in m.parts)

    def funcion(messages, info: AgentInfo) -> ModelResponse:
        if plan.corrige_tras_reintento and hubo_reintento(messages):
            plan.defecto = None
        accion = plan.paso(observaciones(messages))
        if accion[0] == "herramienta":
            return ModelResponse(parts=[ToolCallPart(tool_name=accion[1], args=accion[2])])
        salida = accion[1]
        if not info.output_tools:   # salida «prompted»: el modelo escribe el JSON como texto
            return ModelResponse(parts=[TextPart(json.dumps(salida, ensure_ascii=False))])
        # Pydantic AI expone una herramienta de salida por miembro de la unión: se elige por ``estado``
        nombre = "final_result_Comparacion" if salida.get("estado") == "comparacion" else "final_result_DatosInsuficientes"
        if nombre not in {t.name for t in info.output_tools}:
            nombre = info.output_tools[0].name
        return ModelResponse(parts=[ToolCallPart(tool_name=nombre, args=salida)])

    return FunctionModel(funcion, model_name=f"doble-{plan.defecto or 'correcto'}")


# --------------------------------------------------------------------------- #
# Adaptador smolagents
# --------------------------------------------------------------------------- #
def modelo_doble_smol(plan: PlanDoble):
    from smolagents.models import ChatMessage, ChatMessageToolCall, ChatMessageToolCallFunction, Model, MessageRole
    from smolagents.monitoring import TokenUsage

    class ModeloDoble(Model):
        def __init__(self):
            super().__init__(model_id=f"doble-{plan.defecto or 'correcto'}")
            self.obs: list[tuple[str, dict, dict]] = []
            self.pendiente: tuple[str, dict] | None = None
            self.contador = 0

        def generate(self, messages, stop_sequences=None, response_format=None, tools_to_call_from=None, **kwargs):
            # recoger el resultado de la última herramienta llamada desde el texto de la observación
            if self.pendiente is not None:
                texto = _ultima_observacion(messages)
                try:
                    cont = json.loads(texto)
                except ValueError:
                    cont = {}
                self.obs.append((self.pendiente[0], self.pendiente[1], cont))
                self.pendiente = None
            accion = plan.paso(self.obs)
            self.contador += 1
            if accion[0] == "herramienta":
                self.pendiente = (accion[1], accion[2])
                nombre, args = accion[1], accion[2]
            else:
                nombre, args = "final_answer", {"answer": accion[1]}
            tc = ChatMessageToolCall(function=ChatMessageToolCallFunction(name=nombre, arguments=args),
                                     id=f"call_{self.contador}", type="function")
            return ChatMessage(role=MessageRole.ASSISTANT, content="", tool_calls=[tc],
                               token_usage=TokenUsage(input_tokens=0, output_tokens=0))

    return ModeloDoble()


def _ultima_observacion(messages) -> str:
    """Texto de la última observación de herramienta que smolagents devolvió al modelo."""
    for m in reversed(messages):
        contenido = m.content if hasattr(m, "content") else m.get("content")
        if isinstance(contenido, list):
            contenido = " ".join(c.get("text", "") for c in contenido if isinstance(c, dict))
        if contenido and "Observation:" in contenido:
            return contenido.split("Observation:", 1)[-1].strip()
    return ""
