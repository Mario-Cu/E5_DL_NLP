"""Servidor MCP del asistente ASR (transporte stdio).

Publica, reutilizando exactamente el mismo dominio y las mismas herramientas que las configuraciones
locales (``herramientas.ServicioResultados``):

* **tools** (solo lectura): ``listar_sistemas`` y ``obtener_resultados``;
* **resource**: ``asr://politica-evaluacion`` (política de evaluación, texto de ``politica.py``);
* **prompt**: ``comparar_por_idioma`` (plantilla parametrizada para el usuario/host).

Las restricciones de acceso las impone ESTE proceso (opción ``--corpus-autorizados``), no el modelo ni
el cliente: un cliente que pida el corpus ``privado`` recibe ``corpus_no_autorizado`` y queda en la
auditoría (``--auditoria``). Tampoco hay herramientas de SQL, rutas de fichero ni ejecución genérica.

Opciones de simulación de fallos de transporte (solo para la prueba de robustez; por defecto
no hacen nada): ``--fallo caida_una_vez|cuelgue_una_vez|caida_siempre`` y ``--marca RUTA`` (fichero que
recuerda que el fallo ya ocurrió, para que tras reiniciar el servidor funcione).

Uso:  python -m asr_asistente.servidor_mcp --datos datos/resultados_asr.json --corpus-autorizados demo
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations

from .dominio import Permisos, Repositorio
from typing import Annotated

from pydantic import Field

from .herramientas import (DESCRIPCIONES, PARAMETROS, Auditoria, ListadoSistemas, ResultadoConsulta,
                           ServicioResultados)
from .politica import POLITICA_EVALUACION

SOLO_LECTURA = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
URI_POLITICA = "asr://politica-evaluacion"
NOMBRE_PROMPT = "comparar_por_idioma"


class SimuladorFallos:
    """Provoca, de forma controlada, un fallo de transporte en la llamada a ``obtener_resultados``."""

    def __init__(self, modo: str = "ninguno", marca: str | None = None):
        self.modo, self.marca = modo, Path(marca) if marca else None

    def en_llamada(self) -> None:
        if self.modo == "ninguno":
            return
        if self.modo == "caida_siempre":
            os._exit(3)
        if self.marca is not None and self.marca.exists():
            return  # el fallo ya ocurrió una vez: ahora el servidor se comporta bien
        if self.marca is not None:
            self.marca.write_text("fallo provocado\n", encoding="utf-8")
        if self.modo == "caida_una_vez":
            os._exit(3)  # muerte abrupta del proceso, sin cerrar el protocolo
        if self.modo == "cuelgue_una_vez":
            time.sleep(3600)  # no responde: el cliente debe vencer por timeout


def crear_servidor(servicio: ServicioResultados, fallos: SimuladorFallos | None = None) -> MCPServer:
    fallos = fallos or SimuladorFallos()
    app = MCPServer(
        "asr-asistente",
        instructions=("Consulta de resultados ASR (solo lectura). Lee el recurso asr://politica-evaluacion "
                      "antes de comparar."))

    @app.tool(name="listar_sistemas", description=DESCRIPCIONES["listar_sistemas"], annotations=SOLO_LECTURA)
    def listar_sistemas(corpus: Annotated[str, Field(description=PARAMETROS["corpus"])],
                        idioma: Annotated[str, Field(description=PARAMETROS["idioma"])]) -> ListadoSistemas:
        return servicio.listar_sistemas(corpus, idioma)

    @app.tool(name="obtener_resultados", description=DESCRIPCIONES["obtener_resultados"], annotations=SOLO_LECTURA)
    def obtener_resultados(corpus: Annotated[str, Field(description=PARAMETROS["corpus"])],
                           idioma: Annotated[str, Field(description=PARAMETROS["idioma"])],
                           sistema: Annotated[str, Field(description=PARAMETROS["sistema"])]) -> ResultadoConsulta:
        fallos.en_llamada()
        return servicio.obtener_resultados(corpus, idioma, sistema)

    @app.resource(URI_POLITICA, name="politica-evaluacion", mime_type="text/markdown",
                  description="Política de evaluación: definición de WER, comparabilidad y cuándo abstenerse.")
    def politica() -> str:
        return POLITICA_EVALUACION

    @app.prompt(name=NOMBRE_PROMPT, description="Plantilla para comparar dos sistemas ASR en un idioma.")
    def comparar_por_idioma(corpus: str, idioma: str, sistema_a: str, sistema_b: str) -> str:
        return (f"Compara el WER de los sistemas {sistema_a} y {sistema_b} en el corpus {corpus} para el idioma "
                f"{idioma}. Consulta las herramientas, aplica la política de evaluación y, si falta evidencia, "
                "abstente explicando qué falta.")

    return app


def principal(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--datos", default=None, help="fichero JSON de datos (por defecto datos/resultados_asr.json)")
    ap.add_argument("--corpus-autorizados", default="demo", help="lista separada por comas")
    ap.add_argument("--auditoria", default=None, help="fichero JSONL donde registrar cada llamada")
    ap.add_argument("--fallo", default="ninguno", choices=["ninguno", "caida_una_vez", "cuelgue_una_vez", "caida_siempre"])
    ap.add_argument("--marca", default=None)
    a = ap.parse_args(argv)
    servicio = ServicioResultados(
        Repositorio(a.datos),
        Permisos(frozenset(c.strip() for c in a.corpus_autorizados.split(",") if c.strip())),
        Auditoria(a.auditoria, origen="servidor_mcp"))
    crear_servidor(servicio, SimuladorFallos(a.fallo, a.marca)).run(transport="stdio")


if __name__ == "__main__":
    principal(sys.argv[1:])
