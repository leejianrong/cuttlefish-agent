from __future__ import annotations

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
