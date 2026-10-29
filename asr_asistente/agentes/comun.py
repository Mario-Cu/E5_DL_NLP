"""Piezas comunes a las tres configuraciones: resultado de ejecución, dependencias, contadores y trazas."""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any

from ..contratos import Comparacion, DatosInsuficientes
from ..herramientas import ServicioResultados
from ..politica import LIMITES, SECRETO_CANARIO, Limites, instrucciones_completas

registro = logging.getLogger("asr_asistente")

NO_DISPONIBLE = "no disponible"

#: valores posibles de ``terminacion`` (motivo de fin de la ejecución)
TERMINACIONES = (
    "salida_final",              # el agente entregó una salida válida
    "rechazada_verificador",     # salida válida en forma pero falsa: la aplicación la descartó
    "salida_invalida",           # agotó reintentos sin producir una salida con el esquema
    "limite_excedido",           # superó solicitudes/pasos/llamadas permitidos
    "fallo_transporte",          # MCP: caída o timeout tras agotar los reintentos acotados
    "fallo_infraestructura",     # datos/servidor no disponibles (error de infraestructura)
    "plazo_excedido",            # superó el plazo total de la ejecución
)


@dataclass
class DepsAsistente:
    """Dependencias inyectadas por la aplicación (Pydantic AI ``deps_type``).

    Al modelo solo llega lo que se decide enviar: instrucciones, política y resultados de herramientas.
    Se queda en el programa: el repositorio, la lista de corpus autorizados, el secreto canario, los
    límites y la auditoría.
    """

    servicio: ServicioResultados
    limites: Limites = LIMITES
    secreto: str = SECRETO_CANARIO
    politica: str | None = None

    @property
    def permisos(self):
        return self.servicio.permisos

    @property
    def repo(self):
        return self.servicio.repo


@dataclass
class ResultadoEjecucion:
    config: str
    caso: str
    pregunta: str
    salida: Comparacion | DatosInsuficientes | None = None
    texto_salida: str = ""
    terminacion: str = "salida_final"
    error: str | None = None
    tiempo_s: float = 0.0
    solicitudes_modelo: int = 0
    llamadas_herramienta: int = 0
    reintentos: int = 0
    reintentos_transporte: int = 0
    tokens_entrada: Any = NO_DISPONIBLE
    tokens_salida: Any = NO_DISPONIBLE
    coste: Any = NO_DISPONIBLE
    traza: list[dict] = field(default_factory=list)
    detalle_verificador: list[str] = field(default_factory=list)
    extra: dict = field(default_factory=dict)

    def a_dict(self) -> dict:
        d = {k: getattr(self, k) for k in (
            "config", "caso", "pregunta", "terminacion", "error", "tiempo_s", "solicitudes_modelo",
            "llamadas_herramienta", "reintentos", "reintentos_transporte", "tokens_entrada", "tokens_salida",
            "coste", "detalle_verificador", "extra")}
        d["salida"] = self.salida.model_dump(mode="json") if self.salida is not None else None
        d["texto_salida"] = self.texto_salida
        d["traza"] = self.traza
        return d


class Cronometro:
    def __enter__(self):
        self.t0 = time.perf_counter()
        return self

    def __exit__(self, *a):
        self.segundos = time.perf_counter() - self.t0


def a_json(x: Any, limite: int = 4000) -> str:
    try:
        s = json.dumps(x, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        s = str(x)
    return s if len(s) <= limite else s[:limite] + "…"


def instrucciones(deps: DepsAsistente) -> str:
    return instrucciones_completas(deps.politica)
