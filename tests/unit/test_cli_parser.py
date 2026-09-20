from __future__ import annotations

import pytest

from cuttlefish.cli import _parse_allow, build_parser


def test_parse_allow_defaults_to_empty() -> None:
    assert _parse_allow(None) == []


def test_parse_allow_splits_each_shell_quoted_value() -> None:
    assert _parse_allow(["go test", "npm test"]) == [["go", "test"], ["npm", "test"]]


def test_parse_allow_handles_a_single_quoted_argument() -> None:
    assert _parse_allow(["git commit -m 'fix bug'"]) == [["git", "commit", "-m", "fix bug"]]


def test_run_parser_accepts_repeated_allow_flags() -> None:
    args = build_parser().parse_args(
        ["run", "add a test", "--allow", "go test", "--allow", "npm test"]
    )
    assert args.allow == ["go test", "npm test"]


def test_run_parser_allow_defaults_to_none_when_omitted() -> None:
    args = build_parser().parse_args(["run", "add a test"])
    assert args.allow is None


def test_run_parser_accepts_repeated_secret_flags() -> None:
    args = build_parser().parse_args(
        ["run", "add a test", "--secret", "HUGGINGFACE_TOKEN", "--secret", "GITHUB_TOKEN"]
    )
    assert args.secret == ["HUGGINGFACE_TOKEN", "GITHUB_TOKEN"]


def test_run_parser_project_and_secret_default_to_none_when_omitted() -> None:
    args = build_parser().parse_args(["run", "add a test"])
    assert args.project is None
    assert args.secret is None


def test_secrets_set_requires_a_scope() -> None:
    with pytest.raises(SystemExit):
        build_parser().parse_args(["secrets", "set", "TOKEN"])


def test_secrets_set_rejects_both_project_and_shared_together() -> None:
    with pytest.raises(SystemExit):
        build_parser().parse_args(["secrets", "set", "--project", "demo", "--shared", "TOKEN"])


def test_secrets_set_accepts_a_project_scope() -> None:
    args = build_parser().parse_args(["secrets", "set", "--project", "demo", "TOKEN"])
    assert args.secrets_command == "set"
    assert args.project == "demo"
    assert args.name == "TOKEN"


def test_secrets_list_accepts_the_shared_scope() -> None:
    args = build_parser().parse_args(["secrets", "list", "--shared"])
    assert args.secrets_command == "list"
    assert args.shared is True


def test_secrets_generate_key_needs_no_scope() -> None:
    args = build_parser().parse_args(["secrets", "generate-key"])
    assert args.secrets_command == "generate-key"
