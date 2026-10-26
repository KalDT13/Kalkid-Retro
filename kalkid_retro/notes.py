"""Pense-bête : liste de ressources à récupérer (obtenu / nécessaire), collable depuis un site de recettes.

Aucune minuterie, aucune lecture du jeu : la fenêtre ne consomme rien tant qu'on ne la manipule pas.
"""

from __future__ import annotations

import re

from PySide6.QtCore import QRect, Qt, QTimer, Signal
from PySide6.QtGui import QFont, QGuiApplication, QKeySequence, QShortcut
from PySide6.QtWidgets import (QCheckBox, QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton, QScrollArea,
                               QSpinBox, QVBoxLayout, QWidget)

from .config import Config
from .theme import ACCENT2, MUTED, OK

DEFAULT_SIZE = (440, 560)

# --- lecture d'un texte collé ---------------------------------------------------------------------
_CONTROL_WORDS = {"min", "max"}
_RE_NUMBER = re.compile(r"^\d+$")
_RE_SLASH = re.compile(r"^/\s*(\d+)$")                          # « / 4 »
_RE_INLINE = re.compile(r"^(?P<name>.+?)\s+(?P<have>\d+)\s*/\s*(?P<qty>\d+)$")   # « Corail Magistral 0 / 4 »
_RE_QTY_FIRST = re.compile(r"^(?P<qty>\d+)\s*[x×]?\s+(?P<name>[^\d/].*)$")       # « 4 Corail » ou « 4x Corail »
_RE_QTY_LAST = re.compile(r"^(?P<name>.+?)\s*(?:[x×:]|\()\s*(?P<qty>\d+)\)?$")   # « Corail x4 », « Corail : 4 »


def _clean(name: str) -> str:
    return name.strip(" \t-•*·:").strip()


def parse_recipe(text: str) -> list[dict]:
    """Transforme un texte collé en liste [{"name", "qty" (nécessaire), "have" (obtenu)}].

    Gère le format copié depuis OfficeBook (un bloc par ressource : nom, min, max, quantité, « / N ») et des
    écritures plus simples : « Corail Magistral 0 / 4 », « 4x Corail Magistral », « Corail Magistral x4 ».
    """
    lines = [ln.strip() for ln in (text or "").replace("\r", "").split("\n") if ln.strip()]

    # 1) format en blocs (OfficeBook) : un nom, puis min / max / nombre / « / N » dans n'importe quel ordre
    items: list[dict] = []
    name, have, qty = None, 0, None

    def flush():
        nonlocal name, have, qty
        if name and qty:
            items.append({"name": name, "qty": qty, "have": min(have, 99999)})
        name, have, qty = None, 0, None

    for ln in lines:
        low = ln.lower()
        if low in _CONTROL_WORDS:
            continue
        slash = _RE_SLASH.match(ln)
        if slash:
            qty = int(slash.group(1))
            flush()
            continue
        if _RE_NUMBER.match(ln):
            have = int(ln)
            continue
        flush() if (name and qty) else None
        name = _clean(ln)
        have, qty = 0, None
    flush()
    if items:
        return items

    # 2) une ressource par ligne
    items = []
    for ln in lines:
        m = _RE_INLINE.match(ln)
        if m:
            items.append({"name": _clean(m.group("name")), "qty": int(m.group("qty")), "have": int(m.group("have"))})
            continue
        m = _RE_QTY_FIRST.match(ln) or _RE_QTY_LAST.match(ln)
        if m and _clean(m.group("name")):
            items.append({"name": _clean(m.group("name")), "qty": int(m.group("qty")), "have": 0})
    return items


def _normalize(item: dict) -> dict:
    """Anciennes entrées (name, qty, done) -> (name, qty, have)."""
    qty = max(1, int(item.get("qty", 1) or 1))
    if "have" in item:
        have = max(0, int(item["have"] or 0))
    else:
        have = qty if item.get("done") else 0
    return {"name": str(item.get("name", "")).strip(), "qty": qty, "have": have}


# --- interface ------------------------------------------------------------------------------------
class NoteRow(QFrame):
    """Une ressource : case (faite), nom, min / max, quantité obtenue, « / nécessaire », suppression."""

    have_changed = Signal(int, int)
    deleted = Signal(int)

    def __init__(self, index: int, item: dict):
        super().__init__()
        self.setObjectName("noteRow")
        self._qty = item["qty"]
        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 6, 6, 6)
        lay.setSpacing(6)

        self.box = QCheckBox()
        self.box.setToolTip("Fait : met la quantité au maximum (décoché : remet à 0)")
        lay.addWidget(self.box)

        self.name = QLabel(item["name"])
        self.name.setWordWrap(True)
        self.name.setToolTip(item["name"])
        lay.addWidget(self.name, 1)

        self.min_btn = QPushButton("min")
        self.min_btn.setObjectName("mini")
        self.min_btn.setToolTip("Remet à 0")
        self.max_btn = QPushButton("max")
        self.max_btn.setObjectName("mini")
        self.max_btn.setToolTip("Quantité nécessaire atteinte")
        lay.addWidget(self.min_btn)
        lay.addWidget(self.max_btn)

        self.spin = QSpinBox()
        self.spin.setRange(0, 99999)
        self.spin.setFixedWidth(68)
        self.spin.setValue(item["have"])
        lay.addWidget(self.spin)

        self.total = QLabel(f"/ {item['qty']}")
        self.total.setMinimumWidth(40)
        lay.addWidget(self.total)

        delete = QPushButton("✕")
        delete.setObjectName("ghost")
        delete.setFixedSize(24, 24)
        delete.setToolTip("Supprimer")
        delete.setCursor(Qt.CursorShape.PointingHandCursor)
        lay.addWidget(delete)

        self.spin.valueChanged.connect(lambda v: self._changed(index, v))
        self.min_btn.clicked.connect(lambda: self.spin.setValue(0))
        self.max_btn.clicked.connect(lambda: self.spin.setValue(self._qty))
        self.box.clicked.connect(lambda checked: self.spin.setValue(self._qty if checked else 0))
        delete.clicked.connect(lambda: self.deleted.emit(index))
        self._paint(item["have"])

    def _changed(self, index: int, value: int) -> None:
        self._paint(value)
        self.have_changed.emit(index, value)

    def _paint(self, have: int) -> None:
        done = have >= self._qty
        self.box.blockSignals(True)
        self.box.setChecked(done)
        self.box.blockSignals(False)
        font = QFont(self.name.font())
        font.setStrikeOut(done)
        self.name.setFont(font)
        self.name.setStyleSheet(f"color: {MUTED if done else 'white'};")
        self.total.setStyleSheet(f"color: {OK if done else ACCENT2}; font-weight: 700;")


class NoteWindow(QWidget):
    """Fenêtre flottante du pense-bête (toujours au premier plan par défaut, déplaçable sur le côté)."""

    def __init__(self, cfg: Config):
        super().__init__(None, Qt.WindowType.Tool | Qt.WindowType.WindowStaysOnTopHint)
        self.cfg = cfg
        raw = [i for i in cfg.get("notes", "items", default=[]) if isinstance(i, dict)]
        self.items: list[dict] = [n for n in (_normalize(i) for i in raw) if n["name"]]
        self.setWindowTitle("Pense-bête")
        self.resize(*DEFAULT_SIZE)
        self.setMinimumSize(380, 280)

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

        paste = QPushButton("Coller une recette  (Ctrl+V)")
        paste.setObjectName("primary")
        paste.setToolTip("Colle ici le texte copié sur OfficeBook : les ressources et les quantités sont ajoutées")
        paste.clicked.connect(self.paste_recipe)
        root.addWidget(paste)
        self.hint = QLabel("")
        self.hint.setObjectName("muted")
        self.hint.setWordWrap(True)
        root.addWidget(self.hint)

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

        self.empty = QLabel("Rien à faire pour l'instant.\nColle une recette, ou ajoute une ressource ci-dessous.")
        self.empty.setObjectName("muted")
        self.empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(self.empty)

        tools = QHBoxLayout()
        clear_done = QPushButton("Retirer les faits")
        clear_done.clicked.connect(self.clear_done)
        uncheck = QPushButton("Tout remettre à 0")
        uncheck.clicked.connect(self.reset_all)
        clear_all = QPushButton("Vider")
        clear_all.clicked.connect(self.clear_all)
        tools.addWidget(clear_done)
        tools.addWidget(uncheck)
        tools.addWidget(clear_all)
        root.addLayout(tools)

        add = QHBoxLayout()
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("Ressource (ex. Peau de Bouftou)")
        self.name_edit.returnPressed.connect(self._add_from_form)
        self.qty_spin = QSpinBox()
        self.qty_spin.setRange(1, 99999)
        self.qty_spin.setValue(1)
        self.qty_spin.setPrefix("× ")
        self.qty_spin.setFixedWidth(92)
        self.qty_spin.lineEdit().returnPressed.connect(self._add_from_form)
        add_btn = QPushButton("Ajouter")
        add_btn.clicked.connect(self._add_from_form)
        add.addWidget(self.name_edit, 1)
        add.addWidget(self.qty_spin)
        add.addWidget(add_btn)
        root.addLayout(add)

        # Ctrl+V : colle la recette dans la liste (si le texte n'en est pas une, collage normal dans le champ actif)
        QShortcut(QKeySequence.StandardKey.Paste, self, activated=self._paste_shortcut,
                  context=Qt.ShortcutContext.WidgetWithChildrenShortcut)

        self._apply_on_top(self.pin.isChecked())
        self.refresh()

    # --- données ---------------------------------------------------------------
    def _save(self) -> None:
        self.cfg.set("notes", "items", self.items)

    def add_item(self, name: str, qty: int, have: int = 0) -> None:
        name = name.strip()
        if not name:
            return
        for item in self.items:          # même ressource : on additionne la quantité nécessaire
            if item["name"].casefold() == name.casefold():
                item["qty"] += qty
                break
        else:
            self.items.append({"name": name, "qty": max(1, qty), "have": max(0, have)})

    def set_have(self, index: int, value: int) -> None:
        if 0 <= index < len(self.items):
            self.items[index]["have"] = value
            self._save()
            self._update_progress()

    def delete(self, index: int) -> None:
        if 0 <= index < len(self.items):
            del self.items[index]
            self._save()
            self.refresh()

    @staticmethod
    def _is_done(item: dict) -> bool:
        return item["have"] >= item["qty"]

    def clear_done(self) -> None:
        self.items = [i for i in self.items if not self._is_done(i)]
        self._save()
        self.refresh()

    def reset_all(self) -> None:
        for item in self.items:
            item["have"] = 0
        self._save()
        self.refresh()

    def clear_all(self) -> None:
        self.items = []
        self._save()
        self.refresh()

    # --- collage ------------------------------------------------------------------
    def paste_recipe(self, text: str | None = None) -> int:
        """Ajoute les ressources du texte collé (presse-papiers par défaut). Retourne le nombre ajouté."""
        if text is None:
            text = QGuiApplication.clipboard().text()
        parsed = parse_recipe(text)
        for item in parsed:
            self.add_item(item["name"], item["qty"], item["have"])
        if parsed:
            self._save()
            self.refresh()
            self._say(f"{len(parsed)} ressource{'s' if len(parsed) > 1 else ''} ajoutée{'s' if len(parsed) > 1 else ''}.")
        else:
            self._say("Rien de reconnu dans le presse-papiers : copie la liste des ressources sur OfficeBook.")
        return len(parsed)

    def _paste_shortcut(self) -> None:
        text = QGuiApplication.clipboard().text()
        parsed = parse_recipe(text)
        if parsed and (len(parsed) > 1 or "/" in text):
            self.paste_recipe(text)
            return
        focus = self.focusWidget()      # texte ordinaire : collage normal dans le champ en cours
        if isinstance(focus, QLineEdit):
            focus.paste()

    def _say(self, message: str) -> None:
        self.hint.setText(message)
        QTimer.singleShot(4000, lambda: self.hint.setText("") if self.hint.text() == message else None)

    # --- affichage ---------------------------------------------------------------
    def refresh(self) -> None:
        while self.rows.count():
            item = self.rows.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        for index, item in enumerate(self.items):
            row = NoteRow(index, item)
            row.have_changed.connect(self.set_have)
            row.deleted.connect(self.delete)
            self.rows.addWidget(row)
        self.rows.addStretch(1)
        self._update_progress()
        self.empty.setVisible(not self.items)
        self.area.setVisible(bool(self.items))

    def _update_progress(self) -> None:
        done = sum(1 for i in self.items if self._is_done(i))
        self.progress.setText(f"{done}/{len(self.items)} faits" if self.items else "")

    def _add_from_form(self) -> None:
        name = self.name_edit.text()
        if name.strip():
            self.add_item(name, self.qty_spin.value())
            self._save()
            self.refresh()
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
