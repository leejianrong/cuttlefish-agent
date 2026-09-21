"""A `Project`'s stable identity, outside any single project's own `.cuttlefish/` (ADR-0009).

``~/.cuttlefish/projects.db`` — deliberately *not* colocated with any project
directory's own state (`secrets.db`, `episodic.db`, satay's own `.satay/`, all still
rooted at that project's own `--root`/cwd, unchanged by this module): a fleet daemon
overseeing many projects needs one registry that outlives, and isn't rooted in, any
single one of them.

A role's own ``persona`` is durable here (docs/QUESTIONS.md Q31); its task text is not
— that stays as ephemeral as today's ``--role NAME:TASK_TEXT`` (ADR-0007), composed
fresh each time a team starts (`cuttlefish.fleet`).
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import dataclass, field
from pathlib import Path


def default_projects_db() -> Path:
    """``~/.cuttlefish/projects.db`` — hardcoded this slice, no env override yet
    (docs/QUESTIONS.md Q47): a concrete need for more than one registry per
    operator machine hasn't shown up, so this isn't built ahead of one.

    A function, not a module-level constant: `Path.home()` resolved once at import
    time would freeze whatever `HOME` happened to be when `cuttlefish` first
    imported this module, the same reason `cuttlefish.config.secrets_db_path`
    resolves its own default fresh on every call rather than once at import time.
    """
    return Path.home() / ".cuttlefish" / "projects.db"


_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS projects (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    root TEXT NOT NULL,
    secrets_scope TEXT NOT NULL,
    roles_json TEXT NOT NULL,
    last_team_id TEXT,
    allow_json TEXT NOT NULL DEFAULT '[]'
)
"""

#: `allow_json` was added after slice D1 shipped -- an operator's existing,
#: on-disk `projects.db` predates it. `CREATE TABLE IF NOT EXISTS` alone would
#: leave that column missing on every such file; `ProjectStore.__init__` runs
#: this once, guarded by `PRAGMA table_info`, so a fresh database (which already
#: has the column from `_CREATE_TABLE`) is a harmless no-op.
_ADD_ALLOW_COLUMN = "ALTER TABLE projects ADD COLUMN allow_json TEXT NOT NULL DEFAULT '[]'"


@dataclass(frozen=True, slots=True)
class RoleDefinition:
    """One role's durable identity: a name and a persona (voice/personality, Q31).

    Never task text — a role's task is supplied fresh each time a team starts.
    """

    name: str
    persona: str = ""


@dataclass(frozen=True, slots=True)
class Project:
    """A project's stable identity (Q38's own deferral target, resolved by ADR-0009).

    ``secrets_scope`` carries forward exactly the meaning `--project NAME` already had
    (docs/QUESTIONS.md Q38) — defaulting to ``name`` so a project registered against an
    existing checkout keeps reading whatever `SecretsStore` scope it already used.

    ``allow`` is durable here for the same reason ``persona`` is (Q31, Q53): a
    project's trusted shell-command set is reviewed once, not retyped per
    `FleetDaemon.start` call — a daemon-launched team has no CLI `--allow` flag
    of its own to carry it. Defaults to ``()``, the same "no shell command
    allowed" posture `policy.DEFAULT_SHELL_ALLOWLIST` already holds everywhere
    else nothing is declared.
    """

    id: str
    name: str
    root: str
    secrets_scope: str
    roles: tuple[RoleDefinition, ...] = field(default_factory=tuple)
    last_team_id: str | None = None
    allow: tuple[tuple[str, ...], ...] = field(default_factory=tuple)

    def role(self, name: str) -> RoleDefinition | None:
        """The registered role definition named `name`, or `None` if this project
        never declared one — a start request naming an unregistered role still runs,
        just with no persona prefix (a graceful default, not a rejected request)."""
        for candidate in self.roles:
            if candidate.name == name:
                return candidate
        return None


class ProjectNotFoundError(LookupError):
    """No project with the given id is registered."""


def _encode_roles(roles: tuple[RoleDefinition, ...]) -> str:
    return json.dumps([{"name": r.name, "persona": r.persona} for r in roles])


def _decode_roles(raw: str) -> tuple[RoleDefinition, ...]:
    return tuple(
        RoleDefinition(name=r["name"], persona=r.get("persona", "")) for r in json.loads(raw)
    )


def _encode_allow(allow: tuple[tuple[str, ...], ...]) -> str:
    return json.dumps([list(command) for command in allow])


def _decode_allow(raw: str) -> tuple[tuple[str, ...], ...]:
    return tuple(tuple(command) for command in json.loads(raw))


def _row_to_project(row: sqlite3.Row) -> Project:
    return Project(
        id=row["id"],
        name=row["name"],
        root=row["root"],
        secrets_scope=row["secrets_scope"],
        roles=_decode_roles(row["roles_json"]),
        last_team_id=row["last_team_id"],
        allow=_decode_allow(row["allow_json"]),
    )


class ProjectStore:
    """The `Project` registry — one row per registered project, id-addressed."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._conn = connection
        self._conn.row_factory = sqlite3.Row
        self._conn.execute(_CREATE_TABLE)
        columns = {row["name"] for row in self._conn.execute("PRAGMA table_info(projects)")}
        if "allow_json" not in columns:
            self._conn.execute(_ADD_ALLOW_COLUMN)
        self._conn.commit()

    @classmethod
    def open(cls, path: Path | None = None) -> ProjectStore:
        """Open (creating if needed) the SQLite file at `path` (default:
        :func:`default_projects_db`).

        ``check_same_thread=False``: the fleet daemon's FastAPI routes (ADR-0009)
        run this store's synchronous calls from whatever thread the ASGI server
        dispatches a request on -- a real production `cuttlefish serve` process is
        single-threaded (uvicorn's own asyncio loop), but its own `TestClient`
        (used in tests) dispatches through a background thread, and sqlite3's
        default same-thread check would reject that unconditionally. Every actual
        access still goes through this one connection sequentially -- sqlite3's own
        global lock, not Python's same-thread check, is what makes that safe.
        """
        resolved = path if path is not None else default_projects_db()
        resolved.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(resolved, check_same_thread=False)
        return cls(connection)

    def close(self) -> None:
        self._conn.close()

    def register(
        self,
        *,
        name: str,
        root: str,
        secrets_scope: str | None = None,
        roles: tuple[RoleDefinition, ...] = (),
        allow: tuple[tuple[str, ...], ...] = (),
    ) -> Project:
        """Register a new project. `secrets_scope` defaults to `name` (Q38)."""
        project = Project(
            id=uuid.uuid4().hex,
            name=name,
            root=root,
            secrets_scope=secrets_scope if secrets_scope is not None else name,
            roles=roles,
            allow=allow,
        )
        self._conn.execute(
            "INSERT INTO projects "
            "(id, name, root, secrets_scope, roles_json, last_team_id, allow_json) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                project.id,
                project.name,
                project.root,
                project.secrets_scope,
                _encode_roles(project.roles),
                project.last_team_id,
                _encode_allow(project.allow),
            ),
        )
        self._conn.commit()
        return project

    def get(self, project_id: str) -> Project:
        row = self._conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
        if row is None:
            raise ProjectNotFoundError(project_id)
        return _row_to_project(row)

    def list(self) -> list[Project]:
        cursor = self._conn.execute("SELECT * FROM projects ORDER BY name")
        return [_row_to_project(row) for row in cursor]

    def update_roles(self, project_id: str, roles: tuple[RoleDefinition, ...]) -> Project:
        self.get(project_id)  # raises ProjectNotFoundError if unknown
        self._conn.execute(
            "UPDATE projects SET roles_json = ? WHERE id = ?", (_encode_roles(roles), project_id)
        )
        self._conn.commit()
        return self.get(project_id)

    def update_allow(self, project_id: str, allow: tuple[tuple[str, ...], ...]) -> Project:
        self.get(project_id)  # raises ProjectNotFoundError if unknown
        self._conn.execute(
            "UPDATE projects SET allow_json = ? WHERE id = ?", (_encode_allow(allow), project_id)
        )
        self._conn.commit()
        return self.get(project_id)

    def record_team_started(self, project_id: str, team_id: str) -> None:
        self.get(project_id)  # raises ProjectNotFoundError if unknown
        self._conn.execute(
            "UPDATE projects SET last_team_id = ? WHERE id = ?", (team_id, project_id)
        )
        self._conn.commit()

    def deregister(self, project_id: str) -> bool:
        """Remove `project_id`'s registry row. Returns whether anything was actually
        deleted (mirroring `SecretsStore.delete`'s own return-what-happened shape).
        Never touches `root` or its own `.cuttlefish/` contents — the same
        non-destructive posture `cuttlefish secrets delete` already holds for one
        name, extended to a whole project entry."""
        cursor = self._conn.execute("DELETE FROM projects WHERE id = ?", (project_id,))
        self._conn.commit()
        return cursor.rowcount > 0
