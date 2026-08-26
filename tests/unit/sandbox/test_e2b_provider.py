from __future__ import annotations

import pytest

from cuttlefish.sandbox.e2b import E2bSandboxProvider, MissingApiKeyError


def test_raises_when_api_key_is_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("E2B_API_KEY", raising=False)
    with pytest.raises(MissingApiKeyError):
        E2bSandboxProvider()


def test_constructs_with_api_key_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("E2B_API_KEY", "e2b-test-key")
    E2bSandboxProvider()


def test_constructs_with_explicit_api_key_overriding_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("E2B_API_KEY", raising=False)
    E2bSandboxProvider(api_key="e2b-explicit-key")
