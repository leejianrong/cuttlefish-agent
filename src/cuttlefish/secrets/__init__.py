"""Project-scoped, encrypted-at-rest secrets (ADR-0006, docs/QUESTIONS.md Q34).

`SecretsStore` is the whole public surface: an encrypted key/value store,
scoped per project with a shared fallback, that `cuttlefish.agents.kopicode`/
`cuttlefish.agents.claude_code` resolve against instead of reading
`os.environ` directly. See `cuttlefish.secrets.store`'s own module docstring
for the store itself, and ADR-0006 for why injection, not a broker, is this
slice's answer.
"""

from __future__ import annotations

from cuttlefish.secrets.store import (
    DEFAULT_PROJECT,
    SECRETS_KEY_ENV,
    SHARED_SCOPE,
    InvalidSecretsKeyError,
    MissingSecretsKeyError,
    SecretsStore,
    generate_key,
)

__all__ = [
    "DEFAULT_PROJECT",
    "SECRETS_KEY_ENV",
    "SHARED_SCOPE",
    "InvalidSecretsKeyError",
    "MissingSecretsKeyError",
    "SecretsStore",
    "generate_key",
]
