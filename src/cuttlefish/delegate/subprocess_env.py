"""The one env-merging helper both delegation backends share (ADR-0006).

Not a wire-format concern ADR-0003/ADR-0005's "no shared protocol between
backends" discipline is about — kopicode's and Claude Code's own subprocess
invocations still speak their own native CLI language. Building the `env=`
kwarg `asyncio.create_subprocess_exec` takes is identical logic either way,
so it lives once here rather than twice.
"""

from __future__ import annotations

import os
from collections.abc import Mapping


def merge_env(env: Mapping[str, str] | None) -> dict[str, str] | None:
    """The `env=` kwarg to hand `asyncio.create_subprocess_exec`.

    `None` for an empty/absent `env`: passing an *empty* dict as `env=` would
    give the child process no environment at all (no `PATH`, nothing) rather
    than inheriting the parent's, so this only ever widens what `env=None`'s
    default inheritance already provides, never replaces it — a call that
    declares nothing behaves exactly as it always has.
    """
    if not env:
        return None
    return {**os.environ, **env}
