"""Thème moderne sombre / orange de Kalkid Rétro (cartes arrondies, dégradés, navigation circulaire)."""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPainterPath, QPixmap

BG = "#0B0B0D"
CARD = "#17171A"
CARD_BORDER = "#242428"
FIELD = "#232327"
FIELD_HOVER = "#2D2D32"
TXT = "#F4F4F6"
MUTED = "#9A9AA3"
ACCENT = "#FF5A36"
ACCENT2 = "#FF9A62"
OK = "#3DDC84"
WARN = "#FFB020"
ERR = "#FF5A5A"

STYLESHEET = f"""
* {{ font-family: "Segoe UI Variable Text", "Segoe UI", sans-serif; font-size: 10pt; color: {TXT}; }}
QMainWindow {{ background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #24130C, stop:0.28 #0F0D0D, stop:1 {BG}); }}
QWidget#root, QWidget#page, QWidget#pageInner {{ background: transparent; }}
QLabel {{ background: transparent; }}
QLabel#muted {{ color: {MUTED}; font-size: 9pt; }}
QLabel#appTitle {{ font-size: 15pt; font-weight: 800; }}
QLabel#h2 {{ font-size: 12pt; font-weight: 700; }}
QLabel#cardTitle {{ font-size: 10.5pt; font-weight: 700; }}
QLabel#section {{ font-size: 12pt; font-weight: 700; margin-top: 4px; }}

QScrollArea {{ background: transparent; border: none; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}
QScrollBar:vertical {{ background: transparent; width: 8px; margin: 4px 0; }}
QScrollBar::handle:vertical {{ background: #34343A; border-radius: 4px; min-height: 30px; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}

QFrame#card {{ background: {CARD}; border: 1px solid {CARD_BORDER}; border-radius: 20px; }}
QFrame#row  {{ background: {CARD}; border: 1px solid {CARD_BORDER}; border-radius: 18px; }}
QFrame#warn {{ background: {CARD}; border: 1px solid {ACCENT}; border-radius: 20px; }}
QFrame#hero {{ background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 {ACCENT2}, stop:1 {ACCENT});
               border: none; border-radius: 22px; }}
QFrame#hero QLabel {{ color: white; }}
QFrame#hero QLabel#heroSub {{ color: rgba(255,255,255,85%); font-size: 9pt; }}
QFrame#hero QLabel#heroTitle {{ font-size: 15pt; font-weight: 800; }}
QFrame#hero QLabel#heroStat {{ font-size: 20pt; font-weight: 800; }}
QLabel#tag {{ background: rgba(0,0,0,30%); color: white; border-radius: 9px; padding: 2px 9px; font-size: 8pt; }}
QFrame#sidebar {{ background: #101013; border: none; border-right: 1px solid {CARD_BORDER}; }}
QLabel#pageTitle {{ font-size: 19pt; font-weight: 800; }}
QLabel#colhead {{ color: {MUTED}; font-size: 8pt; font-weight: 700; }}
QFrame#tile {{ background: {CARD}; border: 1px solid {CARD_BORDER}; border-radius: 16px; }}
QFrame#tileHot {{ background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 {ACCENT2}, stop:1 {ACCENT});
                 border: none; border-radius: 16px; }}
QFrame#tileHot QLabel {{ color: white; }}
QLabel#tileValue {{ font-size: 19pt; font-weight: 800; }}
QLabel#tileLabel {{ color: {MUTED}; font-size: 8.5pt; }}
QFrame#tileHot QLabel#tileLabel {{ color: rgba(255,255,255,85%); }}
QFrame#banner {{ background: #3A1B16; border-radius: 16px; }}
QFrame#banner QLabel {{ color: #FFC9BE; }}

QPushButton {{ background: {FIELD}; color: {TXT}; border: none; border-radius: 17px; padding: 8px 18px;
              font-weight: 600; }}
QPushButton:hover {{ background: {FIELD_HOVER}; }}
QPushButton:pressed {{ background: #3A3A41; }}
QPushButton:disabled {{ color: #5A5A62; background: #1D1D20; }}
QPushButton#primary {{ background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {ACCENT2}, stop:1 {ACCENT});
                      color: white; padding: 10px 22px; font-weight: 700; }}
QPushButton#primary:hover {{ background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #FFAD7C, stop:1 #FF6E4D); }}
QPushButton#primary:disabled {{ background: #26262A; color: #5A5A62; }}
QPushButton#heroBtn {{ background: #1A1A1D; color: white; padding: 11px 22px; font-weight: 700; border-radius: 19px; }}
QPushButton#heroBtn:hover {{ background: #26262A; }}
QDialog {{ background: {BG}; }}
QProgressBar {{ background: {FIELD}; border: none; border-radius: 4px; }}
QProgressBar::chunk {{ border-radius: 4px; background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {ACCENT2}, stop:1 {ACCENT}); }}
QPushButton#portrait {{ padding: 0; border-radius: 16px; background: {FIELD}; border: 1px solid transparent; }}
QPushButton#portrait:hover {{ background: {FIELD_HOVER}; }}
QPushButton#portrait:checked {{ background: rgba(255,90,54,22%); border: 1px solid {ACCENT}; }}
QPushButton#chip {{ padding: 0; font-size: 12pt; border-radius: 17px; background: {FIELD}; }}
QPushButton#chip:checked {{ background: rgba(255,90,54,22%); border: 1px solid {ACCENT}; border-radius: 17px; }}
QPushButton#chip:hover {{ background: {FIELD_HOVER}; border-radius: 17px; }}
QPushButton#chip:checked:hover {{ background: rgba(255,90,54,34%); border: 1px solid {ACCENT}; border-radius: 17px; }}
QPushButton#pill {{ padding: 6px 14px; color: {MUTED}; }}
QPushButton#pill:checked {{ background: {ACCENT}; color: white; }}
QPushButton#banner {{ background: transparent; color: #FFC9BE; text-align: left; padding: 10px 16px;
                     border-radius: 16px; font-weight: 600; }}
QPushButton#banner:hover {{ background: rgba(255,255,255,5%); }}

QLineEdit, QSpinBox, QComboBox {{ background: {FIELD}; border: 1px solid transparent; border-radius: 15px;
                                 padding: 6px 12px; selection-background-color: {ACCENT}; }}
QLineEdit:focus, QSpinBox:focus, QComboBox:focus {{ border: 1px solid {ACCENT}; }}
QComboBox::drop-down {{ border: none; width: 24px; }}
QComboBox QAbstractItemView {{ background: {CARD}; border: 1px solid {CARD_BORDER}; border-radius: 10px;
                              selection-background-color: {ACCENT}; outline: none; padding: 4px; }}
QSpinBox::up-button, QSpinBox::down-button {{ width: 0; }}

QListWidget {{ background: transparent; border: none; outline: none; }}
QListWidget::item {{ background: transparent; border: none; margin: 0 0 8px 0; }}
QListWidget::item:selected {{ background: transparent; }}

QPlainTextEdit {{ background: {CARD}; border: 1px solid {CARD_BORDER}; border-radius: 16px; padding: 10px;
                 font-family: Consolas, monospace; font-size: 9pt; }}
QToolTip {{ background: {CARD}; color: {TXT}; border: 1px solid {CARD_BORDER}; padding: 5px; border-radius: 6px; }}
QMessageBox {{ background: {BG}; }}
"""


def _asset_dir() -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    return base / "assets"


def logo_path() -> Path | None:
    """assets/logo.png s'il existe (logo fourni par l'auteur), sinon None."""
    path = _asset_dir() / "logo.png"
    return path if path.exists() else None


def _generated_pixmap(size: int) -> QPixmap:
    pix = QPixmap(size, size)
    pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setBrush(QColor(ACCENT))
    p.setPen(Qt.PenStyle.NoPen)
    p.drawRoundedRect(QRectF(size * 0.04, size * 0.04, size * 0.92, size * 0.92), size * 0.28, size * 0.28)
    font = QFont("Segoe UI", int(size * 0.46))
    font.setWeight(QFont.Weight.Black)
    p.setFont(font)
    p.setPen(QColor("white"))
    p.drawText(QRectF(0, 0, size, size * 0.97), Qt.AlignmentFlag.AlignCenter, "K")
    p.end()
    return pix


def logo_pixmap(size: int = 256) -> QPixmap:
    path = logo_path()
    if path:
        pix = QPixmap(str(path))
        if not pix.isNull():
            return pix.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatio,
                              Qt.TransformationMode.SmoothTransformation)
    return _generated_pixmap(size)


def make_icon(size: int = 256) -> QIcon:
    return QIcon(logo_pixmap(size))


def round_logo(size: int) -> QPixmap:
    """Logo de l'en-tête : le logo détouré tel quel (sans cadre) ; sinon pastille ronde générée."""
    if logo_path():
        return logo_pixmap(size * 2).scaled(size, size, Qt.AspectRatioMode.KeepAspectRatio,
                                            Qt.TransformationMode.SmoothTransformation)
    src = logo_pixmap(size * 2)
    out = QPixmap(size * 2, size * 2)
    out.fill(Qt.GlobalColor.transparent)
    p = QPainter(out)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    clip = QPainterPath()
    clip.addEllipse(QRectF(4, 4, size * 2 - 8, size * 2 - 8))
    p.setClipPath(clip)
    x = (size * 2 - src.width()) / 2
    y = (size * 2 - src.height()) / 2
    p.fillRect(QRectF(0, 0, size * 2, size * 2), QColor("#1A1A1D"))
    p.drawPixmap(int(x), int(y), src)
    p.setClipping(False)
    p.setPen(QColor(ACCENT))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawEllipse(QRectF(3, 3, size * 2 - 6, size * 2 - 6))
    p.end()
    return out.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
