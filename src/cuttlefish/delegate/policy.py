"""The declared-allowlist policy file cuttlefish writes for each delegation.

kopicode board KAN-987 landed the policy gate ADR-0003 was written to depend on
(kopicode ADR-0011). Slice 1 uses it with one hardcoded, narrow policy rather than
a general, operator-declared mechanism (docs/PLAN.md Scope, QUESTIONS.md Q2):
confine writes to the delegation's own root, and permit no shell command at all.
Generalising this into a per-task policy is V2 scope (docs/SLICES.md).

This is also the exact capability ADR-0002's addendum names: a policy-gated
delegation can now cause a real shell command or file write to happen unattended,
which it could not before KAN-987 landed (kopicode's unconfigured `denyHeadless`
refused everything). Slice 1 proceeds without the sandbox that ADR-0011 asks the
orchestrator to provide, as a deliberate, named exception — see that addendum.
"""

from __future__ import annotations

import json
from pathlib import Path

#: Slice 1's one hardcoded shell allowlist: no shell command may run at all. Real
#: containment (V2's sandbox, ADR-0002) is what would make a wider allowlist safe
#: to offer; until then, writes confined to the delegation's own root are the
#: narrowest capability that still lets kopicode land a real edit.
DEFAULT_SHELL_ALLOWLIST: list[list[str]] = []


def write_policy_file(path: Path, *, root: str, allow: list[list[str]] | None = None) -> None:
    """Write a kopicode declared-allowlist policy file at `path`.

    Grammar is kopicode's own (``internal/permission/allowlist_file.go``): two
    flat top-level keys, `root` (a quoted absolute path) and `allow` (a list of
    argv lists) — hand-written rather than templated through a library, the same
    reasoning kopicode's own file gives for not pulling in a TOML dependency for
    two keys. `json.dumps` happens to render a list of string lists in exactly
    this grammar's array syntax, so it's reused for `allow` rather than
    hand-formatting it.
    """
    resolved_allow = DEFAULT_SHELL_ALLOWLIST if allow is None else allow
    allow_literal = json.dumps(resolved_allow)
    path.write_text(f'root = "{root}"\nallow = {allow_literal}\n')
