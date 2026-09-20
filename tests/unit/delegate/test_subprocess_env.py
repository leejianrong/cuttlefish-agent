"""Unit: merge_env's inheritance-preserving behaviour (ADR-0006)."""

from __future__ import annotations

import pytest

from cuttlefish.delegate.subprocess_env import merge_env


def test_none_stays_none() -> None:
    """`env=None` to `create_subprocess_exec` means full inheritance -- a call
    that declares nothing must keep meaning exactly that."""
    assert merge_env(None) is None


def test_an_empty_mapping_also_stays_none() -> None:
    """An *empty* dict as `env=` would give the child no environment at all
    (no PATH, nothing) rather than inheriting the parent's -- must not happen."""
    assert merge_env({}) is None


def test_a_nonempty_mapping_merges_over_a_copy_of_os_environ(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SOME_AMBIENT_VAR", "ambient-value")

    merged = merge_env({"HUGGINGFACE_TOKEN": "hf_value"})

    assert merged is not None
    assert merged["SOME_AMBIENT_VAR"] == "ambient-value"
    assert merged["HUGGINGFACE_TOKEN"] == "hf_value"


def test_a_declared_value_overrides_the_same_name_already_in_os_environ(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "from-env")

    merged = merge_env({"ANTHROPIC_API_KEY": "from-secret"})

    assert merged is not None
    assert merged["ANTHROPIC_API_KEY"] == "from-secret"
