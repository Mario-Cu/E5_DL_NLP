"""Construcción del modelo real (Ollama) para cada framework. El mismo modelo y parámetros en las tres."""
from __future__ import annotations

from ..politica import CONFIG_MODELO, ConfigModelo


def modelo_pydantic(cfg: ConfigModelo = CONFIG_MODELO):
    from pydantic_ai.models.openai import OpenAIChatModel
    from pydantic_ai.providers.ollama import OllamaProvider

    return OpenAIChatModel(cfg.modelo, provider=OllamaProvider(base_url=cfg.url_base.rstrip("/") + "/v1"))


def ajustes_pydantic(cfg: ConfigModelo = CONFIG_MODELO):
    from pydantic_ai.settings import ModelSettings

    return ModelSettings(temperature=cfg.temperatura, seed=cfg.semilla)


def modelo_smolagents(cfg: ConfigModelo = CONFIG_MODELO):
    from smolagents import LiteLLMModel

    return LiteLLMModel(model_id=f"ollama_chat/{cfg.modelo}", api_base=cfg.url_base, api_key="ollama",
                        num_ctx=cfg.num_ctx, temperature=cfg.temperatura, seed=cfg.semilla)
