"""Clasificación de excepciones de infraestructura y de transporte (no son resultados de negocio)."""
from __future__ import annotations


class FalloTransporte(Exception):
    """Caída o timeout del servidor MCP tras agotar los reintentos acotados."""


def clasificar_excepcion(exc: BaseException) -> tuple[str, str]:
    """Devuelve (terminacion, mensaje). Revisa también la causa encadenada (los frameworks envuelven errores)."""
    cadena = []
    e: BaseException | None = exc
    while e is not None and len(cadena) < 8:
        cadena.append(e)
        e = e.__cause__ or e.__context__
    nombres = " ".join(type(x).__name__ + " " + str(x) for x in cadena).lower()
    if any(isinstance(x, (TimeoutError, FalloTransporte, ConnectionError, BrokenPipeError, EOFError)) for x in cadena) \
            or any(k in nombres for k in ("timeout", "closedresource", "connection closed", "brokenpipe", "eof", "mcperror")):
        return "fallo_transporte", f"{type(exc).__name__}: {exc}"
    return "fallo_infraestructura", f"{type(exc).__name__}: {exc}"
