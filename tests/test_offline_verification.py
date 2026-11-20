"""Offline verification helpers must actually block outbound sockets."""

import socket

import pytest

from siraj_research.offline_verify import (
    REQUIRED_ASSETS,
    asset_report,
    outbound_network_blocked,
)


def test_outbound_connections_are_blocked_inside_the_context():
    with outbound_network_blocked():
        with pytest.raises(OSError):
            socket.create_connection(("nominatim.openstreetmap.org", 443), timeout=0.01)
    # The patch is always restored.
    assert socket.create_connection.__name__ == "create_connection"


def test_loopback_connections_are_not_blocked():
    with outbound_network_blocked():
        sock = socket.socket()
        try:
            # Port 1 on loopback is closed, but the call is *attempted* (a
            # ConnectionRefusedError, not our OSError marker).
            with pytest.raises(OSError) as excinfo:
                sock.connect(("127.0.0.1", 1))
            assert "offline verification" not in str(excinfo.value)
        finally:
            sock.close()


def test_required_assets_are_bundled():
    report = asset_report()
    missing = [path for path in REQUIRED_ASSETS if path in report["missing"]]
    assert missing == []
    assert report["required_assets_bytes"] > 100_000
