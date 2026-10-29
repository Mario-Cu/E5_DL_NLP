"""Utilidades de cliente MCP compartidas por las pruebas sin LLM y por el agente Pydantic AI + MCP."""
from __future__ import annotations

import sys
from pathlib import Path

from fastmcp.client.transports import StdioTransport

RAIZ = Path(__file__).resolve().parent.parent


def transporte_stdio(auditoria: str | Path | None = None, datos: str | Path | None = None,
                     corpus_autorizados: str = "demo", extra: list[str] | None = None) -> StdioTransport:
    """Lanza el servidor como subproceso (stdio) con el mismo intérprete y la raíz del proyecto como cwd."""
    args = ["-m", "asr_asistente.servidor_mcp", "--corpus-autorizados", corpus_autorizados]
    if datos:
        args += ["--datos", str(datos)]
    if auditoria:
        args += ["--auditoria", str(auditoria)]
    args += extra or []
    return StdioTransport(command=sys.executable, args=args, cwd=str(RAIZ))
