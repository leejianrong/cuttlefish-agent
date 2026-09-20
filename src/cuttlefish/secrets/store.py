"""An encrypted-at-rest, project-scoped secrets store (ADR-0006).

``.cuttlefish/secrets.db`` — its own SQLite file, never a table inside
``episodic.db`` or satay's own ``.satay/`` store, the same discipline
ADR-0004 already holds for episodic memory (docs/QUESTIONS.md Q7), extended
here rather than special-cased for a second kind of durable state.

Every value is encrypted with Fernet (symmetric, authenticated) under
``CUTTLEFISH_SECRETS_KEY`` — a key the operator generates once
(:func:`generate_key`) and holds themselves; this store never derives it from,
or makes it depend on, any secret it itself protects. A row's ``scope`` is
either a project's own name or :data:`SHARED_SCOPE`; :meth:`SecretsStore.resolve`
is the only lookup that ever crosses that boundary (a project's own value wins,
falling back to the shared one), so a caller never has to reimplement that
precedence itself.
"""

from __future__ import annotations

import os
import sqlite3
from collections.abc import Sequence
from pathlib import Path

from cryptography.fernet import Fernet

#: The scope every project can read from in addition to its own (Q34: "the
#: option of secrets shared across projects, like a personal OpenRouter key").
SHARED_SCOPE = "*"

#: What a task belongs to when the operator names no project of its own
#: (`cuttlefish.cli`'s `--project`, defaulting to `--root`'s own directory
#: name in practice) -- there is no formal `Project` entity yet (slice D's
#: job, docs/SLICES.md); this is a plain string bucket, nothing more
#: (docs/QUESTIONS.md Q38).
DEFAULT_PROJECT = "default"

SECRETS_KEY_ENV = "CUTTLEFISH_SECRETS_KEY"

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS secrets (
    scope TEXT NOT NULL,
    name TEXT NOT NULL,
    ciphertext BLOB NOT NULL,
    PRIMARY KEY (scope, name)
)
"""


class MissingSecretsKeyError(RuntimeError):
    """`CUTTLEFISH_SECRETS_KEY` isn't set (checked before the store is opened,
    not mid-task -- the same fail-closed posture Q17 already established for a
    missing binary)."""


class InvalidSecretsKeyError(RuntimeError):
    """`CUTTLEFISH_SECRETS_KEY` is set but isn't a valid Fernet key."""


def generate_key() -> str:
    """A fresh `CUTTLEFISH_SECRETS_KEY` value (`cuttlefish secrets generate-key`)."""
    return Fernet.generate_key().decode("ascii")


class SecretsStore:
    """An encrypted-at-rest key/value store, scoped per project with a shared fallback."""

    def __init__(self, connection: sqlite3.Connection, *, key: str | None = None) -> None:
        resolved_key = key if key is not None else os.environ.get(SECRETS_KEY_ENV)
        if not resolved_key:
            raise MissingSecretsKeyError(
                f"{SECRETS_KEY_ENV} is not set. Generate one with "
                "`cuttlefish secrets generate-key` and set it before using secrets."
            )
        try:
            self._fernet = Fernet(resolved_key.encode("ascii"))
        except (ValueError, TypeError) as exc:
            raise InvalidSecretsKeyError(f"{SECRETS_KEY_ENV} is not a valid Fernet key") from exc
        self._conn = connection
        self._conn.execute(_CREATE_TABLE)
        self._conn.commit()

    @classmethod
    def open(cls, path: Path, *, key: str | None = None) -> SecretsStore:
        """Open (creating if needed) the SQLite file at `path`."""
        path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(path)
        return cls(connection, key=key)

    def close(self) -> None:
        self._conn.close()

    def set(self, scope: str, name: str, value: str) -> None:
        """Encrypt and store `value` under `scope`/`name`, replacing any prior value."""
        ciphertext = self._fernet.encrypt(value.encode("utf-8"))
        self._conn.execute(
            "INSERT INTO secrets (scope, name, ciphertext) VALUES (?, ?, ?) "
            "ON CONFLICT (scope, name) DO UPDATE SET ciphertext = excluded.ciphertext",
            (scope, name, ciphertext),
        )
        self._conn.commit()

    def get(self, scope: str, name: str) -> str | None:
        """`scope`/`name`'s decrypted value, or `None` if it isn't set."""
        row = self._conn.execute(
            "SELECT ciphertext FROM secrets WHERE scope = ? AND name = ?", (scope, name)
        ).fetchone()
        if row is None:
            return None
        return self._fernet.decrypt(row[0]).decode("utf-8")

    def delete(self, scope: str, name: str) -> bool:
        """Remove `scope`/`name`. Returns whether anything was actually deleted."""
        cursor = self._conn.execute(
            "DELETE FROM secrets WHERE scope = ? AND name = ?", (scope, name)
        )
        self._conn.commit()
        return cursor.rowcount > 0

    def list_names(self, scope: str) -> list[str]:
        """Every name set in `scope` -- never values, for an operator inspecting
        what's there without needing to decrypt anything."""
        cursor = self._conn.execute(
            "SELECT name FROM secrets WHERE scope = ? ORDER BY name", (scope,)
        )
        return [row[0] for row in cursor]

    def resolve(self, project: str, names: Sequence[str]) -> dict[str, str]:
        """`name -> value` for every one of `names` found in `project`'s own scope
        or, failing that, :data:`SHARED_SCOPE` -- a name found in neither is simply
        absent from the result, not an error. Whether an absent *declared* name
        should fail a task closed is the caller's call (`cuttlefish.cli`), not this
        store's -- it only ever reports what it actually has.
        """
        resolved: dict[str, str] = {}
        for name in names:
            value = self.get(project, name)
            if value is None and project != SHARED_SCOPE:
                value = self.get(SHARED_SCOPE, name)
            if value is not None:
                resolved[name] = value
        return resolved
