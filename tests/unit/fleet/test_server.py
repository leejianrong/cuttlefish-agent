"""Unit: `cuttlefish.fleet.server.find_free_port` (slice D2 dev-playbook fix) --
`cuttlefish serve` must never just fail when its default port is taken.
"""

from __future__ import annotations

import socket

from cuttlefish.fleet.server import find_free_port


def test_returns_the_preferred_port_when_it_is_free() -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        free_port = probe.getsockname()[1]
    assert find_free_port("127.0.0.1", free_port) == free_port


def test_skips_a_port_that_is_actually_taken() -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as occupied:
        occupied.bind(("127.0.0.1", 0))
        occupied.listen(1)
        taken_port = occupied.getsockname()[1]

        found = find_free_port("127.0.0.1", taken_port)

        assert found != taken_port
        assert found > taken_port


def test_raises_when_no_port_is_free_in_the_attempted_range() -> None:
    sockets = []
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.bind(("127.0.0.1", 0))
            start_port = probe.getsockname()[1]

        for offset in range(3):
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.bind(("127.0.0.1", start_port + offset))
            s.listen(1)
            sockets.append(s)

        try:
            find_free_port("127.0.0.1", start_port, attempts=3)
        except RuntimeError as exc:
            assert "no free port" in str(exc)
        else:
            raise AssertionError("expected RuntimeError")
    finally:
        for s in sockets:
            s.close()
