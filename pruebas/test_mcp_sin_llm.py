"""Descubrimiento y acceso al servidor MCP SIN modelo: protocolo + herramientas + permisos."""
import asyncio
import json

import pytest
from fastmcp.client import Client

from asr_asistente.cliente_mcp import transporte_stdio
from asr_asistente.herramientas import Auditoria
from asr_asistente.politica import POLITICA_EVALUACION, hash_politica


def ejecutar(coro):
    return asyncio.run(coro)


@pytest.fixture
def auditoria(tmp_path):
    return tmp_path / "auditoria.jsonl"


def test_descubrimiento_y_acceso(auditoria):
    async def main():
        async with Client(transporte_stdio(auditoria=auditoria)) as c:
            herramientas = {t.name: t for t in await c.list_tools()}
            recursos = [str(r.uri) for r in await c.list_resources()]
            prompts = {p.name: p for p in await c.list_prompts()}
            politica = await c.read_resource("asr://politica-evaluacion")
            prompt = await c.get_prompt("comparar_por_idioma",
                                        {"corpus": "demo", "idioma": "es", "sistema_a": "A", "sistema_b": "B"})
            ok = await c.call_tool("obtener_resultados", {"corpus": "demo", "idioma": "es", "sistema": "B"})
            ausente = await c.call_tool("obtener_resultados", {"corpus": "demo", "idioma": "es", "sistema": "D"})
            negado = await c.call_tool("obtener_resultados", {"corpus": "privado", "idioma": "es", "sistema": "A"})
            return herramientas, recursos, prompts, politica, prompt, ok, ausente, negado, c.protocol_version

    herramientas, recursos, prompts, politica, prompt, ok, ausente, negado, version = ejecutar(main())

    assert set(herramientas) == {"listar_sistemas", "obtener_resultados"}        # sin SQL, rutas ni exec genéricos
    for t in herramientas.values():
        assert t.annotations.read_only_hint is True and t.annotations.destructive_hint is False
        assert t.description
    assert set(herramientas["obtener_resultados"].input_schema["properties"]) == {"corpus", "idioma", "sistema"}
    assert recursos == ["asr://politica-evaluacion"]
    assert "comparar_por_idioma" in prompts
    texto = politica[0].text if hasattr(politica[0], "text") else str(politica[0])
    assert hash_politica(texto) == hash_politica(POLITICA_EVALUACION)          # mismo texto que las configs locales
    assert "idioma" in json.dumps([m.content.text for m in prompt.messages], ensure_ascii=False)

    assert ok.structured_content["disponibilidad"] == "disponible" and ok.structured_content["fila"]["wer"] == pytest.approx(0.09)
    assert ausente.structured_content["disponibilidad"] == "sin_resultados" and ausente.structured_content["fila"] is None
    assert negado.structured_content["ok"] is False and negado.structured_content["error"]["codigo"] == "corpus_no_autorizado"
    assert version  # revisión de protocolo negociada (se registra en la memoria)

    eventos = Auditoria.leer(auditoria)
    assert [e["resultado"].get("codigo_error") for e in eventos] == [None, None, "corpus_no_autorizado"]
    assert eventos[0]["origen"] == "servidor_mcp"


def test_argumentos_invalidos_error_controlado(auditoria):
    async def main():
        async with Client(transporte_stdio(auditoria=auditoria)) as c:
            r = await c.call_tool("obtener_resultados", {"corpus": "demo", "idioma": "español", "sistema": "A"})
            falta = await c.call_tool("obtener_resultados", {"corpus": "demo"}, raise_on_error=False)
            return r, falta
    r, falta = ejecutar(main())
    assert r.structured_content["error"]["codigo"] == "idioma_invalido" and r.structured_content["error"]["corregible"] is True
    assert falta.is_error          # argumento obligatorio ausente: lo rechaza el protocolo, no el dominio


def test_servidor_con_otros_datos_y_permisos(tmp_path):
    from asr_asistente.dominio import RAIZ
    datos = RAIZ / "datos" / "escenarios" / "inyeccion.json"

    async def main():
        async with Client(transporte_stdio(datos=datos)) as c:
            return await c.call_tool("obtener_resultados", {"corpus": "demo", "idioma": "es", "sistema": "B"})
    r = ejecutar(main())
    assert "ignora" in r.structured_content["fila"]["comentario_externo"].lower()   # llega como dato
