from __future__ import annotations

import pytest
from PySide6.QtCore import QSettings

from download_only_torrent import peer_strategy
from download_only_torrent import port_config
from download_only_torrent.port_config import listen_interfaces

from conftest import close_engine, make_engine


def test_session_enforces_download_only_policy(tmp_path):
    engine = make_engine(tmp_path)
    settings = engine.session.get_settings()
    try:
        assert settings["unchoke_slots_limit"] == 0
        assert settings["allowed_fast_set_size"] == 0
        assert settings["active_checking"] == -1
        assert settings["active_downloads"] == -1
        assert settings["hashing_threads"] >= 2
        assert settings["checking_mem_usage"] == 1024
        assert settings["peer_fingerprint"].startswith("-DO")
        assert settings["user_agent"].startswith("DownloadOnlyTorrent/")
        assert settings["listen_system_port_fallback"] is False
        # Advanced defaults (libtorrent's own are 500 and 15 s).
        assert settings["max_out_request_queue"] == 1500
        assert settings["peer_connect_timeout"] == 7
    finally:
        close_engine(engine)


@pytest.mark.parametrize(
    "large_pool, prefer_seeders, expected_turnover, expected_limit",
    [
        (False, False, (4, 90, 300), 200),
        (True, False, (10, 80, 60), 1000),
        (False, True, (10, 80, 90), 200),
        (True, True, (15, 75, 45), 1000),
    ],
)
def test_peer_strategy_profiles(
    tmp_path, large_pool, prefer_seeders, expected_turnover, expected_limit
):
    engine = make_engine(tmp_path)
    try:
        settings = QSettings()
        settings.setValue(peer_strategy.LARGE_PEER_POOL_KEY, large_pool)
        settings.setValue(peer_strategy.SEEDER_PREFERENCE_KEY, prefer_seeders)
        engine.apply_config(engine.config)
        applied = engine.session.get_settings()
        assert (
            applied["peer_turnover"],
            applied["peer_turnover_cutoff"],
            applied["peer_turnover_interval"],
        ) == expected_turnover
        assert applied["connections_limit"] == expected_limit
    finally:
        close_engine(engine)


def test_listen_interfaces_follow_default_route():
    QSettings().setValue("network/bind_default_interface", True)
    assert listen_interfaces(4000, ("192.168.0.63", None)) == "192.168.0.63:4000"
    assert (
        listen_interfaces(4000, ("10.0.0.2", "2001:db8::5"))
        == "10.0.0.2:4000,[2001:db8::5]:4000"
    )
    # No usable route: fall back to every interface.
    assert listen_interfaces(4000, (None, None)) == "0.0.0.0:4000,[::]:4000"


def test_listen_interfaces_can_use_all_interfaces():
    QSettings().setValue("network/bind_default_interface", False)
    assert listen_interfaces(4000, ("192.168.0.63", None)) == "0.0.0.0:4000,[::]:4000"


def test_default_route_probe_survives_disabled_address_family(monkeypatch):
    real_socket = port_config.socket.socket

    def no_ipv6(family, *args, **kwargs):
        if family == port_config.socket.AF_INET6:
            raise OSError(97, "Address family not supported by protocol")
        return real_socket(family, *args, **kwargs)

    monkeypatch.setattr(port_config.socket, "socket", no_ipv6)
    ipv4, ipv6 = port_config.default_route_addresses()
    assert ipv6 is None


def test_advanced_network_values_are_applied(tmp_path):
    engine = make_engine(tmp_path, max_out_request_queue=3000, peer_connect_timeout=4)
    try:
        applied = engine.session.get_settings()
        assert applied["max_out_request_queue"] == 3000
        assert applied["peer_connect_timeout"] == 4
        engine.config.max_out_request_queue = 800
        engine.apply_config(engine.config)
        assert engine.session.get_settings()["max_out_request_queue"] == 800
    finally:
        close_engine(engine)
