from __future__ import annotations


def apply_listen_port(engine, port: int) -> None:
    """Apply the saved listen port (and current local address) to libtorrent."""

    engine.apply_listen_settings()


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
