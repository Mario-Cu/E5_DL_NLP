"""Configuración 1: referencia determinista (sin LLM, sin framework de agentes)."""
from __future__ import annotations

from .contratos import Comparacion, DatosInsuficientes, desde_decision
from .dominio import Permisos, Repositorio, Solicitud, decidir


def ejecutar_referencia(repo: Repositorio, permisos: Permisos, solicitud: Solicitud) -> Comparacion | DatosInsuficientes:
    dec = decidir(repo, permisos, solicitud)
    filas = {f.id: (f.s, f.d, f.i, f.n) for f in repo.filas}
    return desde_decision(dec, filas)
