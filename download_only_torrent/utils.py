from __future__ import annotations


def format_bytes(value: float | int) -> str:
    value = float(max(0, value))
    units = ["B", "KiB", "MiB", "GiB", "TiB"]
    for unit in units:
        if value < 1024.0 or unit == units[-1]:
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} B"
        value /= 1024.0
    return f"{value:.1f} TiB"


def format_rate(value: float | int) -> str:
    return f"{format_bytes(value)}/s"
