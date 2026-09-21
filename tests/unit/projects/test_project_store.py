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
