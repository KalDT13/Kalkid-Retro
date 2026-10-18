"""Composants graphiques sur mesure : interrupteur animé, entrée de menu latéral, avatar."""

from __future__ import annotations

from PySide6.QtCore import Property, QEasingCurve, QPropertyAnimation, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QAbstractButton, QWidget

from . import theme
from .icons import draw_icon


def _mix(a: QColor, b: QColor, t: float) -> QColor:
    return QColor(int(a.red() + (b.red() - a.red()) * t), int(a.green() + (b.green() - a.green()) * t),
                  int(a.blue() + (b.blue() - a.blue()) * t))


class Switch(QAbstractButton):
    """Interrupteur arrondi animé (remplace les boutons ON/OFF)."""

    def __init__(self, checked: bool = False, parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setChecked(checked)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(44, 24)
        self._pos = 1.0 if checked else 0.0
        self._anim = QPropertyAnimation(self, b"position", self)
        self._anim.setDuration(130)
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
        if self.isEnabled():
            off, on1, on2 = QColor("#3A3A41"), QColor(theme.ACCENT2), QColor(theme.ACCENT)
        else:
            off, on1, on2 = QColor("#2A2A2E"), QColor("#6A4A40"), QColor("#6A4A40")
        grad = QLinearGradient(0, 0, self.width(), 0)
        grad.setColorAt(0, _mix(off, on1, self._pos))
        grad.setColorAt(1, _mix(off, on2, self._pos))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(grad)
        p.drawRoundedRect(QRectF(0, 0, self.width(), self.height()), self.height() / 2, self.height() / 2)
        d = self.height() - 8
        x = 4 + (self.width() - d - 8) * self._pos
        p.setBrush(QColor("white"))
        p.drawEllipse(QRectF(x, 4, d, d))


class SideNavItem(QAbstractButton):
    """Entrée du menu latéral : icône vectorielle + libellé, surlignée quand elle est active."""

    def __init__(self, icon: str, text: str, parent=None):
        super().__init__(parent)
        self._icon = icon
        self.setText(text)
        self.setCheckable(True)
        self.setAutoExclusive(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(44)
        self._badge = False

    def sizeHint(self) -> QSize:
        return QSize(200, 44)

    def set_badge(self, on: bool):
        self._badge = on
        self.update()

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(0, 0, self.width(), self.height())
        checked = self.isChecked()
        if checked:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(255, 90, 54, 40))
            p.drawRoundedRect(r, 12, 12)
            bar = QLinearGradient(0, 0, 0, self.height())
            bar.setColorAt(0, QColor(theme.ACCENT2))
            bar.setColorAt(1, QColor(theme.ACCENT))
            p.setBrush(bar)
            p.drawRoundedRect(QRectF(0, 10, 4, self.height() - 20), 2, 2)
        elif self.underMouse():
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(255, 255, 255, 14))
            p.drawRoundedRect(r, 12, 12)
        color = QColor(theme.ACCENT2) if checked else QColor("#C9C9D1")
        draw_icon(p, self._icon, QRectF(16, (self.height() - 20) / 2, 20, 20), color)
        font = QFont(self.font())
        font.setPointSizeF(10.5)
        font.setWeight(QFont.Weight.Bold if checked else QFont.Weight.DemiBold)
        p.setFont(font)
        p.setPen(QColor("white") if checked else QColor("#B5B5BE"))
        p.drawText(QRectF(48, 0, self.width() - 60, self.height()),
                   Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, self.text())
        if self._badge:
            p.setPen(QPen(QColor("#101013"), 2))
            p.setBrush(QColor(theme.ERR))
            p.drawEllipse(QRectF(self.width() - 26, self.height() / 2 - 6, 12, 12))

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

    def __init__(self, name: str, online: bool, size: int = 42, portrait=None, on_click=None, parent=None):
        super().__init__(parent)
        self.name, self.online = name, online
        self.portrait = portrait          # QPixmap ou None (initiale)
        self._on_click = on_click
        self.setFixedSize(size, size)
        if on_click:
            self.setCursor(Qt.CursorShape.PointingHandCursor)
            self.setToolTip("Changer l'icône")

    def mouseReleaseEvent(self, event):
        if self._on_click and event.button() == Qt.MouseButton.LeftButton:
            self._on_click()
        super().mouseReleaseEvent(event)

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        d = min(self.width(), self.height()) - 4
        circle = QRectF(2, 2, d, d)
        c1, c2 = _AVATAR_COLORS[sum(map(ord, self.name)) % len(_AVATAR_COLORS)]
        grad = QLinearGradient(circle.topLeft(), circle.bottomRight())
        grad.setColorAt(0, QColor(c1 if self.online else "#4A4A52"))
        grad.setColorAt(1, QColor(c2 if self.online else "#33333A"))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(grad)
        p.drawEllipse(circle)
        if self.portrait is not None and not self.portrait.isNull():
            clip = QPainterPath()
            clip.addEllipse(circle)
            p.save()
            p.setClipPath(clip)
            if not self.online:
                p.setOpacity(0.45)
            pad = d * 0.04
            target = QRectF(circle.left() + pad, circle.top() + pad, d - 2 * pad, d - 2 * pad)
            p.drawPixmap(target.toRect(), self.portrait)
            p.restore()
        else:
            font = QFont(self.font())
            font.setPointSizeF(12)
            font.setWeight(QFont.Weight.ExtraBold)
            p.setFont(font)
            p.setPen(QColor("white" if self.online else "#9A9AA3"))
            p.drawText(circle, Qt.AlignmentFlag.AlignCenter, (self.name[:1] or "?").upper())
        dot = QRectF(self.width() - 12, self.height() - 12, 10, 10)
        p.setPen(QPen(QColor(theme.CARD), 2))
        p.setBrush(QColor(theme.OK if self.online else "#5A5A62"))
        p.drawEllipse(dot)
