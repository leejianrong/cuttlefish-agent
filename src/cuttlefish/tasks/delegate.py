"""The kopicode delegation, wrapped as a satay task (ADR-0001, ADR-0003).

``side_effect=True``: invoking kopicode genuinely has real-world effects (it can
edit files, and run shell commands once a policy allows it, ADR-0002's addendum),
and satay's own execution guarantees exist precisely to make a retried
side-effecting call safe rather than repeated — see
``cuttlefish.episodic.store``'s module docstring for the one race this doesn't
close.

Every call writes and passes kopicode's declared-allowlist policy file (KAN-987,
``cuttlefish.delegate.policy``) rather than running unconfigured. ``allow`` is
the operator-declared, per-task policy (KAN-1011, docs/SLICES.md V2 step 3) —
``None`` falls back to ``write_policy_file``'s own default, V1's original
hardcoded, no-shell-commands-at-all allowlist.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import satay

from cuttlefish import runtime
from cuttlefish.delegate.kopicode import DelegationOutcome, run_kopicode
from cuttlefish.delegate.policy import write_policy_file


@satay.task(side_effect=True)
async def delegate_to_kopicode(
    task_text: str, root: str, allow: list[list[str]] | None = None
) -> DelegationOutcome:
    fd, policy_path_str = tempfile.mkstemp(prefix="cuttlefish-policy-", suffix=".toml")
    os.close(fd)
    policy_path = Path(policy_path_str)
    try:
        write_policy_file(policy_path, root=root, allow=allow)
        return await run_kopicode(
            binary=runtime.current().kopicode_binary,
            task_text=task_text,
            root=root,
            policy_file=str(policy_path),
        )
    finally:
        policy_path.unlink(missing_ok=True)
