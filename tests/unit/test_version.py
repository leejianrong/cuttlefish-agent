from __future__ import annotations

import cuttlefish


def test_version_is_a_string() -> None:
    assert isinstance(cuttlefish.__version__, str)
    assert cuttlefish.__version__
