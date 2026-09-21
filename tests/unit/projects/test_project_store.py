"""Unit: `ProjectStore` (ADR-0009)."""

from __future__ import annotations

from pathlib import Path

from cuttlefish.projects.store import Project, ProjectNotFoundError, ProjectStore, RoleDefinition


def _store(tmp_path: Path) -> ProjectStore:
    return ProjectStore.open(tmp_path / "projects.db")


def test_register_defaults_secrets_scope_to_name(tmp_path: Path) -> None:
    store = _store(tmp_path)
    project = store.register(name="demo", root=str(tmp_path / "demo"))
    assert project.secrets_scope == "demo"
    assert project.roles == ()
    assert project.last_team_id is None
    assert project.allow == ()
    store.close()


def test_register_get_round_trips_allow(tmp_path: Path) -> None:
    store = _store(tmp_path)
    allow = (("uv", "run", "pytest"), ("go", "test"))
    project = store.register(name="demo", root=str(tmp_path / "demo"), allow=allow)
    assert store.get(project.id).allow == allow
    store.close()


def test_update_allow_replaces_the_whole_set(tmp_path: Path) -> None:
    store = _store(tmp_path)
    project = store.register(name="demo", root=str(tmp_path / "demo"), allow=(("go", "test"),))
    updated = store.update_allow(project.id, (("uv", "run", "pytest"),))
    assert updated.allow == (("uv", "run", "pytest"),)
    store.close()


def test_a_projects_db_predating_the_allow_column_is_migrated_in_place(tmp_path: Path) -> None:
    """`allow_json` was added after slice D1 shipped -- an operator's existing,
    on-disk `projects.db` predates it (D1D2 live-usage findings). Simulate that by
    creating the pre-migration schema directly, then opening it through
    `ProjectStore.open` as a real operator restart would."""
    import sqlite3

    db_path = tmp_path / "projects.db"
    legacy = sqlite3.connect(db_path)
    legacy.execute(
        "CREATE TABLE projects (id TEXT PRIMARY KEY, name TEXT NOT NULL, root TEXT NOT NULL, "
        "secrets_scope TEXT NOT NULL, roles_json TEXT NOT NULL, last_team_id TEXT)"
    )
    legacy.execute(
        "INSERT INTO projects (id, name, root, secrets_scope, roles_json, last_team_id) "
        "VALUES ('p1', 'demo', '/tmp/demo', 'demo', '[]', NULL)"
    )
    legacy.commit()
    legacy.close()

    store = ProjectStore.open(db_path)
    project = store.get("p1")
    assert project.allow == ()
    store.close()


def test_register_get_round_trips_roles_with_personas(tmp_path: Path) -> None:
    store = _store(tmp_path)
    roles = (
        RoleDefinition(name="builder", persona="ships fast, terse commits"),
        RoleDefinition(name="reviewer", persona="skeptical, flags risk"),
    )
    project = store.register(name="demo", root=str(tmp_path / "demo"), roles=roles)
    fetched = store.get(project.id)
    assert fetched == Project(
        id=project.id,
        name="demo",
        root=str(tmp_path / "demo"),
        secrets_scope="demo",
        roles=roles,
    )
    store.close()


def test_get_unknown_id_raises(tmp_path: Path) -> None:
    store = _store(tmp_path)
    try:
        store.get("no-such-id")
        raise AssertionError("expected ProjectNotFoundError")
    except ProjectNotFoundError:
        pass
    store.close()


def test_list_orders_by_name(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.register(name="zebra", root=str(tmp_path / "z"))
    store.register(name="alpha", root=str(tmp_path / "a"))
    names = [p.name for p in store.list()]
    assert names == ["alpha", "zebra"]
    store.close()


def test_update_roles_replaces_the_whole_set(tmp_path: Path) -> None:
    store = _store(tmp_path)
    project = store.register(
        name="demo", root=str(tmp_path / "demo"), roles=(RoleDefinition(name="builder"),)
    )
    updated = store.update_roles(project.id, (RoleDefinition(name="reviewer", persona="terse"),))
    assert updated.roles == (RoleDefinition(name="reviewer", persona="terse"),)
    store.close()


def test_record_team_started_sets_last_team_id(tmp_path: Path) -> None:
    store = _store(tmp_path)
    project = store.register(name="demo", root=str(tmp_path / "demo"))
    store.record_team_started(project.id, "team-123")
    assert store.get(project.id).last_team_id == "team-123"
    store.close()


def test_deregister_returns_whether_anything_was_removed_and_never_touches_root(
    tmp_path: Path,
) -> None:
    store = _store(tmp_path)
    root = tmp_path / "demo"
    root.mkdir()
    (root / "marker.txt").write_text("still here")
    project = store.register(name="demo", root=str(root))

    assert store.deregister(project.id) is True
    assert store.deregister(project.id) is False  # already gone -- idempotent, not an error
    assert (root / "marker.txt").exists()
    store.close()
