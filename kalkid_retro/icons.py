"""Icônes vectorielles dessinées par code (aucune police ni image requise)."""

from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen


def _path_people() -> list[QPainterPath]:
    a = QPainterPath()
    a.addEllipse(QPointF(9, 8), 3.4, 3.4)
    b = QPainterPath()
    b.moveTo(3, 19.5)
    b.cubicTo(3, 15.8, 5.8, 14, 9, 14)
    b.cubicTo(12.2, 14, 15, 15.8, 15, 19.5)
    c = QPainterPath()
    c.addEllipse(QPointF(17, 9), 2.5, 2.5)
    d = QPainterPath()
    d.moveTo(17, 13.6)
    d.cubicTo(19.7, 13.8, 21.5, 15.4, 21.5, 18.6)
    return [a, b, c, d]


def _path_bell() -> list[QPainterPath]:
    a = QPainterPath()
    a.moveTo(6.5, 17)
    a.lineTo(6.5, 11)
    a.arcTo(QRectF(6.5, 5, 11, 11), 180, -180)
    a.lineTo(17.5, 17)
    a.closeSubpath()
    b = QPainterPath()
    b.moveTo(4.5, 17)
    b.lineTo(19.5, 17)
    c = QPainterPath()
    c.moveTo(10.2, 20)
    c.lineTo(13.8, 20)
    return [a, b, c]


def _path_shield() -> list[QPainterPath]:
    a = QPainterPath()
    a.moveTo(12, 3)
    a.lineTo(19, 6)
    a.lineTo(19, 11.5)
    a.cubicTo(19, 16, 16, 19.5, 12, 21)
    a.cubicTo(8, 19.5, 5, 16, 5, 11.5)
    a.lineTo(5, 6)
    a.closeSubpath()
    b = QPainterPath()
    b.moveTo(8.8, 12)
    b.lineTo(11, 14.3)
    b.lineTo(15.3, 9.7)
    return [a, b]


def _path_keyboard() -> list[QPainterPath]:
    a = QPainterPath()
    a.addRoundedRect(QRectF(2.5, 6, 19, 12, ), 3, 3)
    keys = QPainterPath()
    for x in (6.5, 10, 13.5, 17.5):
        keys.moveTo(x, 10)
        keys.lineTo(x + 0.01, 10)
    for x in (6.5, 17.5):
        keys.moveTo(x, 13.5)
        keys.lineTo(x + 0.01, 13.5)
    bar = QPainterPath()
    bar.moveTo(9.5, 14)
    bar.lineTo(14.5, 14)
    return [a, keys, bar]


def _path_sliders() -> list[QPainterPath]:
    out = []
    for y, knob in ((7, 9), (12, 15.5), (17, 8)):
        line = QPainterPath()
        line.moveTo(4, y)
        line.lineTo(knob - 2.6, y)
        line.moveTo(knob + 2.6, y)
        line.lineTo(20, y)
        circle = QPainterPath()
        circle.addEllipse(QPointF(knob, y), 2.1, 2.1)
        out += [line, circle]
    return out


def _path_gear() -> list[QPainterPath]:
    a = QPainterPath()
    a.addEllipse(QPointF(12, 12), 3, 3)
    b = QPainterPath()
    b.addEllipse(QPointF(12, 12), 6.4, 6.4)
    teeth = QPainterPath()
    for i in range(8):
        ang = math.radians(i * 45)
        teeth.moveTo(12 + 6.4 * math.cos(ang), 12 + 6.4 * math.sin(ang))
        teeth.lineTo(12 + 9 * math.cos(ang), 12 + 9 * math.sin(ang))
    return [a, b, teeth]


def _path_check() -> list[QPainterPath]:
    a = QPainterPath()
    a.moveTo(5, 12.5)
    a.lineTo(10, 17.5)
    a.lineTo(19, 7)
    return [a]


def _path_info() -> list[QPainterPath]:
    a = QPainterPath()
    a.addEllipse(QPointF(12, 12), 8.5, 8.5)
    b = QPainterPath()
    b.moveTo(12, 11)
    b.lineTo(12, 16.5)
    c = QPainterPath()
    c.moveTo(12, 7.8)
    c.lineTo(12.01, 7.8)
    return [a, b, c]


_BUILDERS = {
    "people": _path_people, "bell": _path_bell, "shield": _path_shield, "keyboard": _path_keyboard,
    "sliders": _path_sliders, "gear": _path_gear, "check": _path_check, "info": _path_info,
}


def draw_icon(painter: QPainter, name: str, rect: QRectF, color: QColor, stroke: float = 1.9) -> None:
    """Dessine l'icône `name` dans `rect` (repère 24×24 mis à l'échelle)."""
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.translate(rect.topLeft())
    painter.scale(rect.width() / 24.0, rect.height() / 24.0)
    pen = QPen(color, stroke)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    for path in _BUILDERS[name]():
        painter.drawPath(path)
    painter.restore()
