from __future__ import annotations


def apply_runtime_network_fix(engine) -> None:
    """Make libtorrent networking robust on Windows hosts with reserved ports.

    The default libtorrent listen port is 6881. Windows/Hyper-V/WSL/VPN stacks
    can reserve that port and cause every listen socket to fail. libtorrent also
    uses the listen UDP socket for DHT, UDP trackers and uTP, so a failed listener
    can leave peer discovery at zero.

    Port 0 asks the OS to select a currently available ephemeral port. Since this
    client never seeds, keeping a stable incoming port across launches is not
    important; reliable outbound discovery is more useful.
    """

    engine.session.apply_settings(
        {
            "listen_interfaces": "0.0.0.0:0,[::]:0",
            "listen_system_port_fallback": True,
        }
    )
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
