"""The kopicode delegation, wrapped as a satay task (ADR-0001, ADR-0003).

``side_effect=True``: invoking kopicode genuinely has real-world effects (it can
edit files, and run shell commands once a policy allows it, ADR-0002's addendum),
and satay's own execution guarantees exist precisely to make a retried
side-effecting call safe rather than repeated — see
``cuttlefish.episodic.store``'s module docstring for the one race this doesn't
close.
"""

from __future__ import annotations

import satay

from cuttlefish import runtime
from cuttlefish.delegate.kopicode import DelegationOutcome, run_kopicode


@satay.task(side_effect=True)
async def delegate_to_kopicode(task_text: str, root: str) -> DelegationOutcome:
    return await run_kopicode(
        binary=runtime.current().kopicode_binary,
        task_text=task_text,
        root=root,
    )
