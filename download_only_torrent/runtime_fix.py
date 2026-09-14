from __future__ import annotations

from .port_config import ensure_listen_port, listen_interfaces


def apply_listen_port(engine, port: int) -> None:
    """Apply one explicit TCP/UDP listen port to libtorrent."""

    engine.session.apply_settings(
        {
            "listen_interfaces": listen_interfaces(port),
            # A user-selected port should be honored rather than silently
            # falling back to another value. Diagnostics will expose bind errors.
            "listen_system_port_fallback": False,
        }
    )


def apply_runtime_network_fix(engine) -> None:
    """Apply the persisted listen port and remove active-torrent queue limits.

    On first launch an unused TCP+UDP port is chosen and stored in QSettings.
    Later launches reuse that port until the user changes it in Settings.

    This application explicitly disables auto-management on added torrents, but
    the active_* limits are also set to unlimited so there is no hidden session
    queue that can cap the number of simultaneous downloads.
    """

    port = ensure_listen_port()
    settings = {
        "listen_interfaces": listen_interfaces(port),
        "listen_system_port_fallback": False,
        "active_downloads": -1,
        "active_seeds": -1,
        "active_checking": -1,
        "active_dht_limit": -1,
        "active_tracker_limit": -1,
        "active_lsd_limit": -1,
        "active_limit": -1,
    }

    try:
        engine.session.apply_settings(settings)
    except Exception:
        apply_listen_port(engine, port)
        for key, value in settings.items():
            if not key.startswith("active_"):
                continue
            try:
                engine.session.apply_settings({key: value})
            except Exception:
                pass

    refresh_discovery(engine)


def refresh_discovery(engine) -> None:
    """Re-announce all known torrents after the listen socket is reconfigured."""

    handles = []
    for task in engine.tasks.values():
        handles.append(task.handle)
    for pending in engine.pending_magnets.values():
        handles.append(pending.handle)

    for handle in handles:
        try:
            handle.resume()
        except Exception:
            pass
        try:
            handle.force_reannounce()
        except Exception:
            pass
        if getattr(engine.config, "enable_dht", True):
            try:
                handle.force_dht_announce()
            except Exception:
                pass
