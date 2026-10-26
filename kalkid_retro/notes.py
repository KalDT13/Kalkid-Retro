"""Pense-bête : petite liste de ressources à récupérer (nom + quantité), à cocher, dans une fenêtre flottante.

Aucune minuterie, aucune lecture du jeu : la fenêtre ne consomme rien tant qu'on ne la manipule pas.
"""

from __future__ import annotations

from PySide6.QtCore import QRect, Qt, Signal
from PySide6.QtGui import QFont, QGuiApplication
from PySide6.QtWidgets import (QCheckBox, QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton, QScrollArea,
                               QSpinBox, QVBoxLayout, QWidget)

from .config import Config
from .theme import ACCENT2, MUTED

DEFAULT_SIZE = (310, 470)


class NoteRow(QFrame):
    """Une ligne : case à cocher, nom de la ressource, quantité, suppression."""

    toggled = Signal(int, bool)
    deleted = Signal(int)

    def __init__(self, index: int, item: dict):
        super().__init__()
        self.setObjectName("noteRow")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 6, 6, 6)
        lay.setSpacing(8)
        done = bool(item.get("done"))

        box = QCheckBox()
        box.setChecked(done)
        box.setToolTip("Fait / à faire")
        box.toggled.connect(lambda state: self.toggled.emit(index, state))
        lay.addWidget(box)

        name = QLabel(item.get("name", ""))
        name.setWordWrap(True)
        font = QFont(name.font())
        font.setStrikeOut(done)
        name.setFont(font)
        name.setStyleSheet(f"color: {MUTED if done else 'white'};")
        lay.addWidget(name, 1)

        qty = QLabel(f"×{item.get('qty', 1)}")
        qty.setStyleSheet(f"color: {MUTED if done else ACCENT2}; font-weight: 700;")
        lay.addWidget(qty)

        delete = QPushButton("✕")
        delete.setObjectName("ghost")
        delete.setFixedSize(24, 24)
        delete.setToolTip("Supprimer")
        delete.setCursor(Qt.CursorShape.PointingHandCursor)
        delete.clicked.connect(lambda: self.deleted.emit(index))
        lay.addWidget(delete)


class NoteWindow(QWidget):
    """Fenêtre flottante du pense-bête (toujours au premier plan par défaut, déplaçable sur le côté)."""

    def __init__(self, cfg: Config):
        super().__init__(None, Qt.WindowType.Tool | Qt.WindowType.WindowStaysOnTopHint)
        self.cfg = cfg
        self.items: list[dict] = [dict(i) for i in cfg.get("notes", "items", default=[]) if isinstance(i, dict)]
        self.setWindowTitle("Pense-bête")
        self.resize(*DEFAULT_SIZE)
        self.setMinimumSize(250, 260)

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 12, 14, 12)
        root.setSpacing(8)

        head = QHBoxLayout()
        title = QLabel("Pense-bête")
        title.setObjectName("cardTitle")
        self.progress = QLabel("")
        self.progress.setObjectName("muted")
        head.addWidget(title)
        head.addWidget(self.progress, 1)
        self.pin = QPushButton("📌")
        self.pin.setObjectName("chip")
        self.pin.setCheckable(True)
        self.pin.setFixedSize(30, 30)
        self.pin.setChecked(bool(cfg.get("notes", "on_top", default=True)))
        self.pin.setToolTip("Garder le pense-bête au-dessus des autres fenêtres")
        self.pin.toggled.connect(self._set_on_top)
        head.addWidget(self.pin)
        root.addLayout(head)

        self.area = QScrollArea()
        self.area.setWidgetResizable(True)
        self.area.setFrameShape(QFrame.Shape.NoFrame)
        self.area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.inner = QWidget()
        self.inner.setObjectName("pageInner")
        self.rows = QVBoxLayout(self.inner)
        self.rows.setContentsMargins(0, 0, 4, 0)
        self.rows.setSpacing(6)
        self.area.setWidget(self.inner)
        root.addWidget(self.area, 1)

        self.empty = QLabel("Rien à faire pour l'instant.\nAjoute une ressource ci-dessous.")
        self.empty.setObjectName("muted")
        self.empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(self.empty)

        tools = QHBoxLayout()
        clear_done = QPushButton("Retirer les faits")
        clear_done.clicked.connect(self.clear_done)
        uncheck = QPushButton("Tout décocher")
        uncheck.clicked.connect(self.uncheck_all)
        tools.addWidget(clear_done)
        tools.addWidget(uncheck)
        root.addLayout(tools)

        add = QHBoxLayout()
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("Ressource (ex. Peau de Bouftou)")
        self.name_edit.returnPressed.connect(self._add_from_form)
        self.qty_spin = QSpinBox()
        self.qty_spin.setRange(1, 99999)
        self.qty_spin.setValue(1)
        self.qty_spin.setPrefix("×")
        self.qty_spin.setFixedWidth(84)
        self.qty_spin.lineEdit().returnPressed.connect(self._add_from_form)
        add_btn = QPushButton("Ajouter")
        add_btn.setObjectName("primary")
        add_btn.clicked.connect(self._add_from_form)
        add.addWidget(self.name_edit, 1)
        add.addWidget(self.qty_spin)
        root.addLayout(add)
        root.addWidget(add_btn)

        self._apply_on_top(self.pin.isChecked())
        self.refresh()

    # --- données ---------------------------------------------------------------
    def _save(self) -> None:
        self.cfg.set("notes", "items", self.items)

    def add_item(self, name: str, qty: int) -> None:
        name = name.strip()
        if not name:
            return
        for item in self.items:          # même ressource : on additionne la quantité
            if item["name"].casefold() == name.casefold():
                item["qty"] = int(item.get("qty", 0)) + qty
                item["done"] = False
                break
        else:
            self.items.append({"name": name, "qty": qty, "done": False})
        self._save()
        self.refresh()

    def set_done(self, index: int, done: bool) -> None:
        if 0 <= index < len(self.items):
            self.items[index]["done"] = done
            self._save()
            self.refresh()

    def delete(self, index: int) -> None:
        if 0 <= index < len(self.items):
            del self.items[index]
            self._save()
            self.refresh()

    def clear_done(self) -> None:
        self.items = [i for i in self.items if not i.get("done")]
        self._save()
        self.refresh()

    def uncheck_all(self) -> None:
        for item in self.items:
            item["done"] = False
        self._save()
        self.refresh()

    # --- affichage ---------------------------------------------------------------
    def refresh(self) -> None:
        while self.rows.count():
            item = self.rows.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        for index, item in enumerate(self.items):
            row = NoteRow(index, item)
            row.toggled.connect(self.set_done)
            row.deleted.connect(self.delete)
            self.rows.addWidget(row)
        self.rows.addStretch(1)
        done = sum(1 for i in self.items if i.get("done"))
        self.progress.setText(f"{done}/{len(self.items)} faits" if self.items else "")
        self.empty.setVisible(not self.items)
        self.area.setVisible(bool(self.items))

    def _add_from_form(self) -> None:
        self.add_item(self.name_edit.text(), self.qty_spin.value())
        self.name_edit.clear()
        self.qty_spin.setValue(1)
        self.name_edit.setFocus()

    # --- fenêtre -------------------------------------------------------------------
    def _apply_on_top(self, on: bool) -> None:
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, on)

    def _set_on_top(self, on: bool) -> None:
        self.cfg.set("notes", "on_top", on)
        self._apply_on_top(on)
        if self.isVisible():
            self.show()          # recréer la fenêtre pour appliquer le nouveau drapeau
            self.raise_()

    def show_note(self) -> None:
        geometry = self.cfg.get("notes", "geometry", default=None)
        screen = QGuiApplication.primaryScreen().availableGeometry()
        if geometry and len(geometry) == 4 and screen.intersects(QRect(*geometry)):
            self.setGeometry(*geometry)
        else:       # par défaut : collée au bord droit de l'écran
            self.move(screen.right() - self.width() - 24, screen.top() + 90)
        self.show()
        self.raise_()

    def save_geometry(self) -> None:
        g = self.geometry()
        self.cfg.set("notes", "geometry", [g.x(), g.y(), g.width(), g.height()])

    def closeEvent(self, event) -> None:
        self.save_geometry()
        event.ignore()           # on masque seulement : le bouton et le raccourci la réaffichent
        self.hide()
