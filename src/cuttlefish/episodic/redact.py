"""Write-time secret redaction for the episodic journal (ADR-0004, QUESTIONS.md Q22).

satay's own write-time redaction (satay-runtime ADR-0029) protects satay's own
journal schema; it does nothing for this second, cuttlefish-owned store, because it
was never meant to. This closes that gap the same way kopicode's own redactor does
(``internal/journal/redact.go``), on purpose rather than by rediscovery: redaction is
not a scan for credential-shaped strings — a denylist of shapes misses the next
provider's format — it removes specific, known values read from named environment
variables, because cuttlefish already knows the actual secret from having read it to
make the call. It runs over the encoded JSON line, so it also catches a secret that
reached an opaque field no payload schema could have kept it out of — a delegated
`env` call's output landing in a kopicode tool result, say.
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable, Sequence

#: Environment variables whose values must never reach the episodic journal:
#: cuttlefish's own LLM provider credential, plus the coding-provider keys a
#: delegated kopicode invocation's tool output might otherwise echo verbatim.
DEFAULT_SECRET_ENV_VARS: tuple[str, ...] = (
    "ANTHROPIC_API_KEY",
    "OPENAI_API_KEY",
    "OPENROUTER_API_KEY",
)

#: The shortest value worth redacting (matches kopicode's own ``minSecretLen``). A
#: one- or two-character environment value is not a credential, and replacing every
#: occurrence of a short string would corrupt the journal to protect nothing.
MIN_SECRET_LENGTH = 12


class Redactor:
    """Removes known secret values from an encoded journal line before it is written."""

    def __init__(
        self,
        names: Sequence[str] = DEFAULT_SECRET_ENV_VARS,
        *,
        lookup: Callable[[str], str | None] | None = None,
    ) -> None:
        get = lookup if lookup is not None else os.environ.get
        pairs: list[tuple[str, str]] = []
        for name in names:
            value = get(name)
            if not value or len(value) < MIN_SECRET_LENGTH:
                continue
            replacement = f"[redacted:{name}]"
            pairs.append((value, replacement))
            # The line is JSON, so a value containing a quote or backslash lands on
            # disk in escaped form and the literal wouldn't match it — look for both
            # spellings of the same secret.
            escaped = _json_string_body(value)
            if escaped != value:
                pairs.append((escaped, replacement))
        # Longest needle first: if one secret's value contains another's, replacing
        # the shorter one first would leave the longer one's remaining bytes on disk.
        pairs.sort(key=lambda pair: len(pair[0]), reverse=True)
        self._pairs = pairs

    def scrub(self, line: str) -> tuple[str, bool]:
        """`line` with every known secret replaced, and whether anything changed."""
        if not self._pairs:
            return line, False
        out = line
        changed = False
        for needle, replacement in self._pairs:
            if needle in out:
                out = out.replace(needle, replacement)
                changed = True
        return out, changed


def _json_string_body(value: str) -> str:
    """`value` as it appears inside a JSON string, without the surrounding quotes."""
    encoded = json.dumps(value)
    return encoded[1:-1]
