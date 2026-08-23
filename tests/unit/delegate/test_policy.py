from __future__ import annotations

from pathlib import Path

from cuttlefish.delegate.policy import write_policy_file


def test_default_allowlist_is_empty(tmp_path: Path) -> None:
    path = tmp_path / "policy.toml"
    write_policy_file(path, root="/abs/scratch")

    content = path.read_text()
    assert content == 'root = "/abs/scratch"\nallow = []\n'


def test_a_declared_allowlist_is_rendered_as_argv_lists(tmp_path: Path) -> None:
    path = tmp_path / "policy.toml"
    write_policy_file(path, root="/abs/scratch", allow=[["go", "test"], ["npm", "test"]])

    content = path.read_text()
    assert content == 'root = "/abs/scratch"\nallow = [["go", "test"], ["npm", "test"]]\n'
