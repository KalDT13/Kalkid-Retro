"""Composants graphiques sur mesure : interrupteur animé, bouton de navigation circulaire, avatar."""

from __future__ import annotations

from PySide6.QtCore import Property, QPropertyAnimation, QEasingCurve, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPen
from PySide6.QtWidgets import QAbstractButton, QWidget

from . import theme
from .icons import draw_icon


class Switch(QAbstractButton):
    """Interrupteur arrondi animé (remplace les boutons ON/OFF)."""

    def __init__(self, checked: bool = False, parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setChecked(checked)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(50, 28)
        self._pos = 1.0 if checked else 0.0
        self._anim = QPropertyAnimation(self, b"position", self)
        self._anim.setDuration(140)
        self._anim.setEasingCurve(QEasingCurve.Type.InOutQuad)
        self.toggled.connect(self._animate)

    def _animate(self, state: bool):
        self._anim.stop()
        self._anim.setEndValue(1.0 if state else 0.0)
        self._anim.start()

    def get_position(self) -> float:
        return self._pos

    def set_position(self, value: float):
        self._pos = value
        self.update()

    position = Property(float, get_position, set_position)

    def set_checked_silently(self, state: bool):
        self.blockSignals(True)
        self.setChecked(state)
        self.blockSignals(False)
        self._pos = 1.0 if state else 0.0
        self.update()

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        track = QRectF(0, 0, self.width(), self.height())
        grad = QLinearGradient(0, 0, self.width(), 0)
        if self.isEnabled():
            off, on1, on2 = QColor("#3A3A41"), QColor(theme.ACCENT2), QColor(theme.ACCENT)
        else:
            off, on1, on2 = QColor("#2A2A2E"), QColor("#6A4A40"), QColor("#6A4A40")
        mix = self._pos
        grad.setColorAt(0, QColor(int(off.red() + (on1.red() - off.red()) * mix),
                                  int(off.green() + (on1.green() - off.green()) * mix),
                                  int(off.blue() + (on1.blue() - off.blue()) * mix)))
        grad.setColorAt(1, QColor(int(off.red() + (on2.red() - off.red()) * mix),
                                  int(off.green() + (on2.green() - off.green()) * mix),
                                  int(off.blue() + (on2.blue() - off.blue()) * mix)))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(grad)
        p.drawRoundedRect(track, self.height() / 2, self.height() / 2)
        d = self.height() - 8
        x = 4 + (self.width() - d - 8) * self._pos
        p.setBrush(QColor("white"))
        p.drawEllipse(QRectF(x, 4, d, d))


class NavButton(QAbstractButton):
    """Bouton de navigation circulaire (icône vectorielle + libellé)."""

    def __init__(self, icon: str, text: str, parent=None):
        super().__init__(parent)
        self._icon = icon
        self.setText(text)
        self.setCheckable(True)
        self.setAutoExclusive(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(text)
        self._badge = False

    def sizeHint(self) -> QSize:
        return QSize(78, 78)

    def set_badge(self, on: bool):
        self._badge = on
        self.update()

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        d = 46
        cx = self.width() / 2
        circle = QRectF(cx - d / 2, 4, d, d)
        if self.isChecked():
            grad = QLinearGradient(circle.topLeft(), circle.bottomRight())
            grad.setColorAt(0, QColor(theme.ACCENT2))
            grad.setColorAt(1, QColor(theme.ACCENT))
            p.setBrush(grad)
            icon_color = QColor("white")
        else:
            p.setBrush(QColor("#2A2A2F" if self.underMouse() else "#222226"))
            icon_color = QColor("#C9C9D1")
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(circle)
        draw_icon(p, self._icon, QRectF(circle.center().x() - 11, circle.center().y() - 11, 22, 22), icon_color)
        if self._badge:
            p.setBrush(QColor(theme.ERR))
            p.setPen(QPen(QColor("#131316"), 2))
            p.drawEllipse(QRectF(circle.right() - 10, circle.top() - 1, 12, 12))
        font = QFont(self.font())
        font.setPointSizeF(8)
        font.setWeight(QFont.Weight.DemiBold)
        p.setFont(font)
        p.setPen(QColor(theme.ACCENT2 if self.isChecked() else theme.MUTED))
        p.drawText(QRectF(0, d + 6, self.width(), 18), Qt.AlignmentFlag.AlignCenter, self.text())

    def enterEvent(self, event):
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.update()
        super().leaveEvent(event)


_AVATAR_COLORS = [("#FF9A62", "#FF5A36"), ("#7C8CFF", "#4B5BFF"), ("#3DDC84", "#1FA463"),
                  ("#FFD15C", "#FF9F1C"), ("#E06BFF", "#A93BD6"), ("#5CD6FF", "#2B9BD8")]


class Avatar(QWidget):
    """Pastille ronde avec l'initiale du personnage et un voyant de connexion."""

    def __init__(self, name: str, online: bool, size: int = 46, parent=None):
        super().__init__(parent)
        self.name, self.online = name, online
        self.setFixedSize(size, size)

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        d = min(self.width(), self.height()) - 4
        circle = QRectF(2, 2, d, d)
        c1, c2 = _AVATAR_COLORS[sum(map(ord, self.name)) % len(_AVATAR_COLORS)]
        grad = QLinearGradient(circle.topLeft(), circle.bottomRight())
        grad.setColorAt(0, QColor(c1 if self.online else "#4A4A52"))
        grad.setColorAt(1, QColor(c2 if self.online else "#33333A"))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(grad)
        p.drawEllipse(circle)
        font = QFont(self.font())
        font.setPointSizeF(13)
        font.setWeight(QFont.Weight.ExtraBold)
        p.setFont(font)
        p.setPen(QColor("white" if self.online else "#9A9AA3"))
        p.drawText(circle, Qt.AlignmentFlag.AlignCenter, (self.name[:1] or "?").upper())
        dot = QRectF(self.width() - 13, self.height() - 13, 11, 11)
        p.setPen(QPen(QColor(theme.CARD), 2))
        p.setBrush(QColor(theme.OK if self.online else "#5A5A62"))
        p.drawEllipse(dot)
