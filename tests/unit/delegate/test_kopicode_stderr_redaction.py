"""Unit: classify_kopicode_output threads a failed session's stderr into
DelegationOutcome.reason, redacted first (Q54's sibling live finding -- an
OpenRouter 401 that was only ever visible on stderr, discarded entirely once
kopicode emitted a real session_ended event).
"""

from __future__ import annotations

from cuttlefish.delegate.kopicode import classify_kopicode_output

_SESSION_ENDED = '{"kind": "session_ended", "exit_code": 3, "reason": "error"}\n'


def test_a_failed_sessions_stderr_detail_reaches_the_outcome_reason() -> None:
    outcome = classify_kopicode_output(
        _SESSION_ENDED,
        "401 Unauthorized: API key expired",
        returncode=3,
    )
    assert outcome.kind == "failed"
    assert outcome.reason is not None
    assert "401 Unauthorized: API key expired" in outcome.reason
    assert "exit_code=3 reason=error" in outcome.reason


def test_a_secret_in_env_is_redacted_out_of_the_stderr_tail() -> None:
    # Deliberately not shaped like a real provider key (no "sk-"-style prefix) --
    # this repo's own gitleaks CI gate flags anything that looks like one, real or
    # not, per handling-secrets discipline.
    fake_value = "not-a-real-credential-0000000000"
    outcome = classify_kopicode_output(
        _SESSION_ENDED,
        f"error calling provider: Authorization: Bearer {fake_value}",
        returncode=3,
        env={"OPENROUTER_API_KEY": fake_value},
    )
    assert outcome.reason is not None
    assert fake_value not in outcome.reason
    assert "[redacted:OPENROUTER_API_KEY]" in outcome.reason


def test_a_short_env_value_is_left_alone() -> None:
    # Below Redactor.MIN_SECRET_LENGTH -- not a credential, and replacing every
    # occurrence would corrupt the message to protect nothing.
    outcome = classify_kopicode_output(
        _SESSION_ENDED,
        "exit status 7",
        returncode=3,
        env={"SOME_FLAG": "7"},
    )
    assert outcome.reason is not None
    assert "exit status 7" in outcome.reason


def test_a_completed_session_ignores_stderr_entirely() -> None:
    outcome = classify_kopicode_output(
        '{"kind": "edit_applied", "path": "a.py"}\n'
        '{"kind": "session_ended", "exit_code": 0, "reason": "completed"}\n',
        "some noise on stderr that isn't a failure",
        returncode=0,
    )
    assert outcome.kind == "completed"
    assert outcome.reason is None
