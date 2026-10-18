"""Thème sombre / orange de Kalkid Rétro."""

from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPixmap

BG = "#0F1117"
CARD = "#1A1D2B"
FIELD = "#2A2E42"
TXT = "#E8E8F0"
MUTED = "#8A8FA8"
ACCENT = "#F5A31A"
OK = "#4CAF78"
ERR = "#E05252"

STYLESHEET = f"""
* {{ font-family: "Segoe UI", sans-serif; font-size: 10pt; color: {TXT}; }}
QMainWindow, QWidget#root {{ background: {BG}; }}
QLabel {{ background: transparent; }}
QLabel#muted {{ color: {MUTED}; font-size: 9pt; }}
QLabel#h1 {{ color: {ACCENT}; font-size: 20pt; font-weight: 800; }}
QLabel#h1b {{ color: {TXT}; font-size: 13pt; font-weight: 700; }}
QLabel#title {{ font-size: 12pt; font-weight: 700; }}
QLabel#colhead {{ color: {MUTED}; font-size: 9pt; font-weight: 600; }}

QTabBar {{ background: transparent; }}
QTabBar::tab {{ background: transparent; color: {MUTED}; padding: 8px 18px; margin-right: 2px;
               font-weight: 700; font-size: 10.5pt; border-bottom: 3px solid transparent; }}
QTabBar::tab:hover {{ color: {TXT}; }}
QTabBar::tab:selected {{ color: {ACCENT}; border-bottom: 3px solid {ACCENT}; }}
QTabWidget::pane {{ border: none; border-top: 1px solid {FIELD}; background: {BG}; }}

QFrame#card {{ background: {CARD}; border-radius: 6px; }}
QFrame#warn {{ background: {CARD}; border: 1px solid {ACCENT}; border-radius: 6px; }}
QFrame#row {{ background: {CARD}; border-radius: 6px; }}

QPushButton {{ background: {FIELD}; color: {MUTED}; border: none; border-radius: 4px;
              padding: 6px 14px; font-weight: 700; }}
QPushButton:hover {{ color: {TXT}; }}
QPushButton:checked {{ background: {ACCENT}; color: {BG}; }}
QPushButton:disabled {{ color: #555a70; }}
QPushButton#primary {{ background: {ACCENT}; color: {BG}; padding: 9px 20px; }}
QPushButton#primary:hover {{ background: #ffb83d; color: {BG}; }}
QPushButton#primary:disabled {{ background: {FIELD}; color: #555a70; }}
QPushButton#banner {{ background: #3a1d1d; color: #ffb4b4; border: none; border-radius: 0; padding: 9px 24px;
                     text-align: left; font-weight: 600; }}
QPushButton#banner:hover {{ background: #4a2323; color: #ffd0d0; }}
QPushButton#ev {{ padding: 0; font-size: 12pt; }}
QPushButton#ev:checked {{ background: #3b2e12; border: 1px solid {ACCENT}; color: {ACCENT}; }}
QPushButton#link {{ background: transparent; color: {ACCENT}; text-decoration: underline; padding: 2px; }}

QLineEdit, QSpinBox, QComboBox {{ background: {FIELD}; border: none; border-radius: 4px; padding: 5px 8px;
                                 selection-background-color: {ACCENT}; selection-color: {BG}; }}
QComboBox::drop-down {{ border: none; width: 22px; }}
QComboBox QAbstractItemView {{ background: {FIELD}; selection-background-color: {ACCENT};
                              selection-color: {BG}; border: none; outline: none; }}
QSpinBox::up-button, QSpinBox::down-button {{ width: 0; }}

QListWidget {{ background: transparent; border: none; outline: none; }}
QListWidget::item {{ background: transparent; border: none; margin: 0 0 6px 0; }}
QListWidget::item:selected {{ background: transparent; }}

QPlainTextEdit {{ background: {CARD}; border: none; border-radius: 6px; padding: 8px;
                 font-family: Consolas, monospace; font-size: 9pt; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 0; }}
QScrollBar::handle:vertical {{ background: {FIELD}; border-radius: 5px; min-height: 30px; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QToolTip {{ background: {CARD}; color: {TXT}; border: 1px solid {FIELD}; padding: 4px; }}
QMessageBox {{ background: {BG}; }}
"""


def make_icon(size: int = 256) -> QIcon:
    """Icône générée par code : carré arrondi orange avec un « K »."""
    pix = QPixmap(size, size)
    pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setBrush(QColor(ACCENT))
    p.setPen(Qt.PenStyle.NoPen)
    p.drawRoundedRect(QRectF(size * 0.04, size * 0.04, size * 0.92, size * 0.92), size * 0.22, size * 0.22)
    font = QFont("Segoe UI", int(size * 0.5))
    font.setWeight(QFont.Weight.Black)
    p.setFont(font)
    p.setPen(QColor(BG))
    p.drawText(QRectF(0, 0, size, size * 0.97), Qt.AlignmentFlag.AlignCenter, "K")
    p.end()
    return QIcon(pix)
