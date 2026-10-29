import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from asr_asistente.dominio import Permisos, Repositorio  # noqa: E402
from asr_asistente.herramientas import Auditoria, ServicioResultados  # noqa: E402


@pytest.fixture
def repo():
    return Repositorio()


@pytest.fixture
def permisos():
    return Permisos()


@pytest.fixture
def servicio(repo, permisos):
    return ServicioResultados(repo, permisos, Auditoria())
