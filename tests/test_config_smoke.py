# tests/test_config_smoke.py
import importlib

import config


def test_llm_config_has_defaults(monkeypatch):
    monkeypatch.delenv("LLM_BASE_URL", raising=False)
    monkeypatch.delenv("LLM_MODEL", raising=False)
    importlib.reload(config)
    try:
        assert config.LLM_BASE_URL == "https://api.groq.com/openai/v1"
        assert config.LLM_MODEL == "llama-3.3-70b-versatile"
    finally:
        importlib.reload(config)  # restore real env for later tests
