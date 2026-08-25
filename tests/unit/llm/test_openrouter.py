from __future__ import annotations

import pytest

from cuttlefish.llm.openrouter import MissingApiKeyError, OpenRouterLlmProvider


def test_raises_when_api_key_is_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    with pytest.raises(MissingApiKeyError):
        OpenRouterLlmProvider()


def test_constructs_with_api_key_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test-key")
    OpenRouterLlmProvider()
