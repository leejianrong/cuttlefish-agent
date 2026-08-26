from __future__ import annotations

import json
from collections.abc import Callable

from cuttlefish.episodic.redact import DEFAULT_SECRET_ENV_VARS, Redactor


def _lookup(values: dict[str, str]) -> Callable[[str], str | None]:
    return values.get


def test_scrub_replaces_a_known_long_secret() -> None:
    secret = "sk-ant-1234567890abcdef"
    redactor = Redactor(["ANTHROPIC_API_KEY"], lookup=_lookup({"ANTHROPIC_API_KEY": secret}))

    line = json.dumps({"tool_result": f"here is the key: {secret}"})
    redacted, changed = redactor.scrub(line)

    assert changed
    assert secret not in redacted
    assert "[redacted:ANTHROPIC_API_KEY]" in redacted


def test_scrub_leaves_unrelated_text_untouched() -> None:
    secret = "sk-ant-1234567890abcdef"
    redactor = Redactor(["ANTHROPIC_API_KEY"], lookup=_lookup({"ANTHROPIC_API_KEY": secret}))

    line = json.dumps({"tool_result": "nothing sensitive here"})
    redacted, changed = redactor.scrub(line)

    assert not changed
    assert redacted == line


def test_scrub_ignores_a_value_shorter_than_the_minimum() -> None:
    redactor = Redactor(["SHORT_VAR"], lookup=_lookup({"SHORT_VAR": "abc"}))

    line = json.dumps({"tool_result": "abc appears here"})
    redacted, changed = redactor.scrub(line)

    assert not changed
    assert redacted == line


def test_scrub_ignores_an_unset_variable() -> None:
    redactor = Redactor(["MISSING_VAR"], lookup=_lookup({}))

    line = json.dumps({"tool_result": "hello"})
    redacted, changed = redactor.scrub(line)

    assert not changed
    assert redacted == line


def test_scrub_catches_the_json_escaped_spelling_too() -> None:
    # A secret containing a character JSON escapes (a backslash) lands on disk in
    # its escaped form; scrub must catch that spelling as well as the literal one.
    secret = "sk-ant-abc\\def-0123456789"
    redactor = Redactor(["ANTHROPIC_API_KEY"], lookup=_lookup({"ANTHROPIC_API_KEY": secret}))

    line = json.dumps({"tool_result": f"key: {secret}"})
    redacted, changed = redactor.scrub(line)

    assert changed
    assert "\\\\def" not in redacted
    assert "[redacted:ANTHROPIC_API_KEY]" in redacted


def test_default_secret_env_vars_covers_the_e2b_credential() -> None:
    # ADR-0002: the sandbox provider reads E2B_API_KEY, so it must be in the
    # default redaction list the same way every other provider credential is.
    assert "E2B_API_KEY" in DEFAULT_SECRET_ENV_VARS


def test_scrub_replaces_the_longer_secret_first_when_one_contains_another() -> None:
    short = "sk-short-0123456789"
    long_ = short + "-and-then-some-more"
    redactor = Redactor(
        ["SHORT_KEY", "LONG_KEY"],
        lookup=_lookup({"SHORT_KEY": short, "LONG_KEY": long_}),
    )

    line = json.dumps({"tool_result": f"here: {long_}"})
    redacted, changed = redactor.scrub(line)

    assert changed
    assert long_ not in redacted
    assert short not in redacted
    assert "[redacted:LONG_KEY]" in redacted
