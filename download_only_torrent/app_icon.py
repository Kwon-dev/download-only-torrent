from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPixmap


def _draw_icon(size: int) -> QPixmap:
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

    margin = size * 0.08
    rect = QRectF(margin, margin, size - margin * 2, size - margin * 2)
    radius = size * 0.22

    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor("#1976d2"))
    painter.drawRoundedRect(rect, radius, radius)

    # Download arrow. Broad geometry keeps the icon readable at 16px.
    painter.setBrush(QColor("#ffffff"))
    cx = size * 0.5
    shaft_w = size * 0.17
    top = size * 0.22
    body_bottom = size * 0.53
    arrow_bottom = size * 0.75
    arrow_half = size * 0.24

    path = QPainterPath()
    path.moveTo(cx - shaft_w / 2, top)
    path.lineTo(cx + shaft_w / 2, top)
    path.lineTo(cx + shaft_w / 2, body_bottom)
    path.lineTo(cx + arrow_half, body_bottom)
    path.lineTo(cx, arrow_bottom)
    path.lineTo(cx - arrow_half, body_bottom)
    path.lineTo(cx - shaft_w / 2, body_bottom)
    path.closeSubpath()
    painter.drawPath(path)

    # Small tray-like baseline gives the mark a clear download meaning.
    baseline = QRectF(size * 0.28, size * 0.79, size * 0.44, size * 0.07)
    painter.drawRoundedRect(baseline, size * 0.025, size * 0.025)
    painter.end()
    return pixmap


def make_app_icon() -> QIcon:
    icon = QIcon()
    for size in (16, 20, 24, 32, 40, 48, 64, 128, 256):
        icon.addPixmap(_draw_icon(size))
    return icon
