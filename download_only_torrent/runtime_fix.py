from __future__ import annotations


def apply_runtime_network_fix(engine) -> None:
    """Apply Windows networking fixes and remove active-torrent queue limits.

    The default libtorrent listen port is 6881. Windows/Hyper-V/WSL/VPN stacks
    can reserve that port and cause every listen socket to fail. libtorrent also
    uses the listen UDP socket for DHT, UDP trackers and uTP, so a failed listener
    can leave peer discovery at zero.

    Port 0 asks the OS to select a currently available ephemeral port. Since this
    client never seeds, keeping a stable incoming port across launches is not
    important; reliable outbound discovery is more useful.

    This application explicitly disables auto-management on added torrents, but
    the active_* limits are also set to unlimited so there is no hidden session
    queue that can cap the number of simultaneous downloads.
    """

    settings = {
        "listen_interfaces": "0.0.0.0:0,[::]:0",
        "listen_system_port_fallback": True,
        "active_downloads": -1,
        "active_seeds": -1,
        "active_checking": -1,
        "active_dht_limit": -1,
        "active_tracker_limit": -1,
        "active_lsd_limit": -1,
        "active_limit": -1,
    }

    # Apply the network settings first because they are required for peer
    # discovery. Some older bindings may not expose every active_* key; in that
    # case retry them individually without sacrificing the listen-port fix.
    try:
        engine.session.apply_settings(settings)
    except Exception:
        engine.session.apply_settings(
            {
                "listen_interfaces": "0.0.0.0:0,[::]:0",
                "listen_system_port_fallback": True,
            }
        )
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
