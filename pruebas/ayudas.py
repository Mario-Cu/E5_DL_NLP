from pathlib import Path

from asr_asistente.dominio import Repositorio

RAIZ = Path(__file__).resolve().parent.parent


def escenario(nombre):
    return Repositorio(RAIZ / "datos" / "escenarios" / f"{nombre}.json")
