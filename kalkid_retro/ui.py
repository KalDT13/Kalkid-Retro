"""Interface PySide6 de Kalkid Rétro : application de bureau (menu latéral, fenêtre large, deux colonnes)."""

from __future__ import annotations

import ctypes
import os
import sys
import winreg
from datetime import datetime

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QAction, QColor, QIcon, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QComboBox, QDialog, QFileDialog, QFrame, QGridLayout,
                               QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMainWindow, QMenu,
                               QMessageBox, QPlainTextEdit, QProgressBar, QPushButton, QScrollArea, QSpinBox,
                               QStackedWidget, QSystemTrayIcon, QVBoxLayout, QWidget)

from . import APP_NAME, __version__, portraits, prereq, updater
from .config import EVENTS
from .controller import Controller
from .theme import ACCENT2, ERR, MUTED, OK, WARN, make_icon, round_logo
from .widgets import Avatar, SideNavItem, Switch

EVENT_ICONS = {"combat": "⚔", "mp": "💬", "groupe": "👥", "echange": "🔄"}
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"

MACRO_WARNING = (
    "Ces outils envoient des actions sur plusieurs comptes à la fois (clics synchronisés, invitations "
    "automatiques). Ankama tolère les outils de gestion de fenêtres mais interdit les macros : ton compte "
    "pourrait être sanctionné. Ils sont désactivés par défaut. Tu les utilises à tes risques."
)

# largeurs fixes partagées par l'en-tête et les lignes de personnages (colonnes alignées)
CHIP = 34
CHIP_GAP = 6
EVENTS_WIDTH = len(EVENT_ICONS) * CHIP + (len(EVENT_ICONS) - 1) * CHIP_GAP
EXCLUDE_WIDTH = 78


# --- briques communes -----------------------------------------------------------------
def label(text: str = "", name: str = "", wrap: bool = False) -> QLabel:
    lbl = QLabel(text)
    if name:
        lbl.setObjectName(name)
    lbl.setWordWrap(wrap)
    return lbl


def card(object_name: str = "card") -> tuple[QFrame, QVBoxLayout]:
    frame = QFrame()
    frame.setObjectName(object_name)
    lay = QVBoxLayout(frame)
    lay.setContentsMargins(18, 14, 18, 14)
    lay.setSpacing(8)
    return frame, lay


def make_switch(checked: bool, on_toggle) -> Switch:
    sw = Switch(checked)
    sw.toggled.connect(on_toggle)
    return sw


def option_row(title: str, desc: str, control: QWidget) -> QFrame:
    frame, lay = card()
    row = QHBoxLayout()
    row.setSpacing(14)
    texts = QVBoxLayout()
    texts.setSpacing(2)
    texts.addWidget(label(title, "cardTitle"))
    if desc:
        texts.addWidget(label(desc, "muted", wrap=True))
    row.addLayout(texts, 1)
    row.addWidget(control, 0, Qt.AlignmentFlag.AlignVCenter)
    lay.addLayout(row)
    return frame


def field_row(text: str, *controls: QWidget) -> QHBoxLayout:
    row = QHBoxLayout()
    row.setSpacing(8)
    row.addWidget(label(text))
    row.addStretch(1)
    for c in controls:
        row.addWidget(c)
    return row


def spin(value: int, minimum: int, maximum: int, on_change, suffix: str = " ms") -> QSpinBox:
    box = QSpinBox()
    box.setRange(minimum, maximum)
    box.setValue(value)
    box.setSuffix(suffix)
    box.setFixedWidth(100)
    box.valueChanged.connect(on_change)
    return box


class Tile(QFrame):
    """Petite tuile de statistique (valeur + libellé)."""

    def __init__(self, value: str, text: str, hot: bool = False):
        super().__init__()
        self.setObjectName("tileHot" if hot else "tile")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 12, 16, 12)
        lay.setSpacing(0)
        self.value = label(value, "tileValue")
        self.text = label(text, "tileLabel")
        lay.addWidget(self.value)
        lay.addWidget(self.text)

    def set_all(self, value: str | None = None, text: str | None = None):
        if value is not None:
            self.value.setText(value)
        if text is not None:
            self.text.setText(text)


class HotkeyButton(QPushButton):
    """Affiche un raccourci ; un clic lance la capture de la prochaine combinaison."""

    def __init__(self, ctl: Controller, action: str):
        super().__init__()
        self.ctl, self.action = ctl, action
        self.setMinimumWidth(130)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.clicked.connect(self._start)
        ctl.hotkey_captured.connect(self._captured)
        self._refresh()

    def _refresh(self):
        self.setText(self.ctl.cfg.get("hotkeys", self.action, default="") or "Aucun")

    def _start(self):
        self.setText("Appuie sur une touche…")
        self.ctl.capture_hotkey(self.action)

    def _captured(self, action: str, value: str):
        if action == self.action:
            self._refresh()


def page_frame(title: str, subtitle: str, body: QWidget, right: QWidget | None = None) -> QWidget:
    """En-tête de page (titre, sous-titre, action à droite) + contenu."""
    page = QWidget()
    page.setObjectName("page")
    lay = QVBoxLayout(page)
    lay.setContentsMargins(28, 22, 28, 20)
    lay.setSpacing(14)
    head = QHBoxLayout()
    titles = QVBoxLayout()
    titles.setSpacing(0)
    titles.addWidget(label(title, "pageTitle"))
    titles.addWidget(label(subtitle, "muted"))
    head.addLayout(titles, 1)
    if right is not None:
        head.addWidget(right, 0, Qt.AlignmentFlag.AlignVCenter)
    lay.addLayout(head)
    lay.addWidget(body, 1)
    return page


def columns(left: list[QWidget], right: list[QWidget] | None = None, ratio: tuple[int, int] = (1, 1)) -> QScrollArea:
    """Contenu défilant sur une ou deux colonnes."""
    inner = QWidget()
    inner.setObjectName("pageInner")
    row = QHBoxLayout(inner)
    row.setContentsMargins(0, 0, 8, 0)
    row.setSpacing(16)
    for widgets, stretch in ((left, ratio[0]), (right, ratio[1])):
        if widgets is None:
            continue
        col = QVBoxLayout()
        col.setSpacing(12)
        for w in widgets:
            col.addWidget(w)
        col.addStretch(1)
        row.addLayout(col, stretch)
    area = QScrollArea()
    area.setWidgetResizable(True)
    area.setFrameShape(QFrame.Shape.NoFrame)
    area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    area.setWidget(inner)
    return area


# --- portraits ------------------------------------------------------------------------
class PortraitDialog(QDialog):
    """Choix de l'icône d'un personnage : portrait de classe, image personnalisée ou initiale."""

    def __init__(self, ctl: Controller, pseudo: str, parent=None):
        super().__init__(parent)
        self.ctl, self.pseudo = ctl, pseudo
        self.setWindowTitle(f"Icône de {pseudo}")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(22, 20, 22, 18)
        lay.setSpacing(12)
        lay.addWidget(label(f"Icône de {pseudo}", "cardTitle"))
        lay.addWidget(label("Choisis la classe et le sexe de ton personnage.", "muted"))

        current = ctl.portrait_key(pseudo)
        grid = QGridLayout()
        grid.setSpacing(8)
        for i, key in enumerate(portraits.available_keys()):
            btn = QPushButton()
            btn.setObjectName("portrait")
            btn.setCheckable(True)
            btn.setChecked(key == current)
            btn.setFixedSize(76, 76)
            btn.setIconSize(QSize(60, 60))
            pix = portraits.pixmap(key, 120)
            if pix is not None:
                btn.setIcon(QIcon(pix))
            btn.setToolTip(portraits.LABELS.get(key, key))
            btn.clicked.connect(lambda _=False, k=key: self._choose(k))
            grid.addWidget(btn, i // 6, i % 6)
        holder = QWidget()
        holder.setLayout(grid)
        lay.addWidget(holder)

        actions = QHBoxLayout()
        none = QPushButton("Aucune icône")
        none.clicked.connect(lambda: self._choose(None))
        custom = QPushButton("Image personnalisée…")
        custom.clicked.connect(self._custom)
        close = QPushButton("Fermer")
        close.clicked.connect(self.reject)
        actions.addWidget(none)
        actions.addWidget(custom)
        actions.addStretch(1)
        actions.addWidget(close)
        lay.addLayout(actions)

    def _choose(self, key):
        self.ctl.set_portrait(self.pseudo, key)
        self.accept()

    def _custom(self):
        path, _ = QFileDialog.getOpenFileName(self, "Choisir une image", "", "Images (*.png *.jpg *.jpeg *.webp)")
        if not path:
            return
        key = portraits.set_custom(self.pseudo, path)
        if key:
            self._choose(key)
        else:
            QMessageBox.warning(self, "Icône", "Impossible de lire cette image.")


def open_portrait_dialog(ctl: Controller, pseudo: str, parent: QWidget) -> None:
    PortraitDialog(ctl, pseudo, parent).exec()


# --- page Personnages -----------------------------------------------------------------
class CharacterRow(QFrame):
    def __init__(self, ctl: Controller, pseudo: str):
        super().__init__()
        self.setObjectName("row")
        self.setFixedHeight(58)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 0, 12, 0)
        lay.setSpacing(10)
        online = pseudo in ctl.windows
        is_main = ctl.cfg.get("main", default="") == pseudo

        # le dialogue s'ouvre après le retour de l'événement souris (la ligne peut être reconstruite)
        lay.addWidget(Avatar(pseudo, online, 42, portraits.pixmap(ctl.portrait_key(pseudo), 84),
                             on_click=lambda: QTimer.singleShot(0, lambda: open_portrait_dialog(
                                 ctl, pseudo, self.window()))))
        texts = QVBoxLayout()
        texts.setSpacing(0)
        name = label(pseudo, "cardTitle")
        name.setStyleSheet(f"color: {'white' if online else MUTED}; font-weight: 700;")
        status = "En ligne" if online else "Hors ligne"
        if is_main:
            status += "  ·  ★ Principal"
        texts.addStretch(1)
        texts.addWidget(name)
        texts.addWidget(label(status, "muted"))
        texts.addStretch(1)
        lay.addLayout(texts, 1)

        events = QHBoxLayout()
        events.setSpacing(CHIP_GAP)
        enabled = ctl.events_for(pseudo)
        for key, icon in EVENT_ICONS.items():
            b = QPushButton(icon)
            b.setObjectName("chip")
            b.setCheckable(True)
            b.setFixedSize(CHIP, CHIP)
            b.setToolTip(f"Autofocus : {EVENTS[key]}")
            b.setChecked(key in enabled)
            b.toggled.connect(lambda state, k=key, p=pseudo: ctl.set_event(p, k, state))
            events.addWidget(b)
        lay.addLayout(events)

        main = QPushButton("★")
        main.setObjectName("chip")
        main.setCheckable(True)
        main.setFixedSize(CHIP, CHIP)
        main.setToolTip("Personnage principal")
        main.setChecked(is_main)
        main.clicked.connect(lambda checked, p=pseudo: self._set_main(ctl, p, checked))
        lay.addWidget(main)

        excl = QPushButton("Exclure")
        excl.setObjectName("pill")
        excl.setCheckable(True)
        excl.setFixedSize(EXCLUDE_WIDTH, CHIP)
        excl.setToolTip("Exclure des raccourcis et des outils")
        excl.setChecked(ctl.is_excluded(pseudo))
        excl.toggled.connect(lambda state, p=pseudo: ctl.set_excluded(p, state))
        lay.addWidget(excl)

    @staticmethod
    def _set_main(ctl: Controller, pseudo: str, checked: bool):
        ctl.cfg.set("main", pseudo if checked else "")
        ctl.windows_changed.emit()


class CharactersPage(QWidget):
    def __init__(self, ctl: Controller):
        super().__init__()
        self.ctl = ctl
        body = QWidget()
        body.setObjectName("pageInner")
        row = QHBoxLayout(body)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(16)

        # --- colonne gauche : liste des personnages ---
        left = QVBoxLayout()
        left.setSpacing(6)
        head = QHBoxLayout()
        head.setContentsMargins(12, 0, 12, 0)
        head.setSpacing(10)
        head.addSpacing(42)
        head.addWidget(label("PERSONNAGE", "colhead"), 1)
        for text, width in (("AUTOFOCUS", EVENTS_WIDTH), ("PRINC.", CHIP), ("", EXCLUDE_WIDTH)):
            col = label(text, "colhead")
            col.setFixedWidth(width)
            col.setAlignment(Qt.AlignmentFlag.AlignCenter)
            head.addWidget(col)
        left.addLayout(head)
        self.list = QListWidget()
        self.list.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.list.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.list.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.list.model().rowsMoved.connect(lambda *a: QTimer.singleShot(0, self._order_changed))
        left.addWidget(self.list, 1)
        self.empty = label("Aucune fenêtre Dofus Rétro détectée.\nLance le jeu, elles apparaîtront ici.", "muted")
        self.empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        left.addWidget(self.empty)
        row.addLayout(left, 1)

        # --- colonne droite : stats, autofocus global, presets ---
        right = QVBoxLayout()
        right.setSpacing(12)
        tiles = QHBoxLayout()
        tiles.setSpacing(12)
        self.tile_online = Tile("0", "connectés", hot=True)
        self.tile_total = Tile("0", "personnages")
        tiles.addWidget(self.tile_online)
        tiles.addWidget(self.tile_total)
        right.addLayout(tiles)

        allbox, al = card()
        al.addWidget(label("Autofocus pour tous", "cardTitle"))
        al.addWidget(label("Active ou coupe un type de notification sur tous les personnages.", "muted", wrap=True))
        chips = QHBoxLayout()
        chips.setSpacing(CHIP_GAP)
        for key, icon in EVENT_ICONS.items():
            b = QPushButton(icon)
            b.setObjectName("chip")
            b.setFixedSize(CHIP + 6, CHIP + 6)
            b.setToolTip(f"« {EVENTS[key]} » pour tous")
            b.clicked.connect(lambda _=False, k=key: self._toggle_column(k))
            chips.addWidget(b)
        chips.addStretch(1)
        al.addLayout(chips)
        right.addWidget(allbox)

        presets, pl = card()
        pl.addWidget(label("Presets", "cardTitle"))
        pl.addWidget(label("Enregistre l'ordre, le principal, les exclusions et l'autofocus.", "muted", wrap=True))
        self.preset_combo = QComboBox()
        self.preset_combo.activated.connect(self._load_preset)
        delete = QPushButton("Supprimer")
        delete.clicked.connect(self._delete_preset)
        pr = QHBoxLayout()
        pr.addWidget(self.preset_combo, 1)
        pr.addWidget(delete)
        pl.addLayout(pr)
        self.preset_name = QLineEdit()
        self.preset_name.setPlaceholderText("Nom du nouveau preset")
        save = QPushButton("Enregistrer")
        save.setObjectName("primary")
        save.clicked.connect(self._save_preset)
        pn = QHBoxLayout()
        pn.addWidget(self.preset_name, 1)
        pn.addWidget(save)
        pl.addLayout(pn)
        right.addWidget(presets)
        right.addStretch(1)
        side = QWidget()
        side.setObjectName("pageInner")
        side.setFixedWidth(330)
        side.setLayout(right)
        right.setContentsMargins(0, 0, 0, 0)
        row.addWidget(side)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(page_frame("Personnages", "Glisse une ligne pour changer l'ordre de passage.", body))

        ctl.windows_changed.connect(self.rebuild)
        self.rebuild()
        self._refresh_presets()

    def rebuild(self):
        self.list.blockSignals(True)
        self.list.clear()
        order = self.ctl.order()
        for pseudo in order:
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, pseudo)
            item.setSizeHint(QSize(100, 66))
            self.list.addItem(item)
            self.list.setItemWidget(item, CharacterRow(self.ctl, pseudo))
        self.list.blockSignals(False)
        self.empty.setVisible(not order)
        online = len(self.ctl.windows)
        self.tile_online.set_all(str(online), "connecté" + ("s" if online > 1 else ""))
        self.tile_total.set_all(str(len(order)), "personnage" + ("s" if len(order) > 1 else ""))

    def _order_changed(self):
        order = [self.list.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.list.count())]
        self.ctl.set_order(order)

    def _toggle_column(self, key: str):
        order = self.ctl.order()
        target = not all(key in self.ctl.events_for(p) for p in order)
        for pseudo in order:
            self.ctl.set_event(pseudo, key, target)
        self.rebuild()

    def _refresh_presets(self):
        self.preset_combo.blockSignals(True)
        self.preset_combo.clear()
        self.preset_combo.addItem("Charger un preset…")
        for name in self.ctl.cfg.get("presets", default={}):
            self.preset_combo.addItem(name)
        self.preset_combo.blockSignals(False)

    def _save_preset(self):
        name = self.preset_name.text().strip()
        if name:
            self.ctl.save_preset(name)
            self.preset_name.clear()
            self._refresh_presets()

    def _load_preset(self, index: int):
        if index > 0:
            self.ctl.load_preset(self.preset_combo.itemText(index))

    def _delete_preset(self):
        if self.preset_combo.currentIndex() > 0:
            self.ctl.delete_preset(self.preset_combo.currentText())
            self._refresh_presets()


# --- page Autofocus --------------------------------------------------------------------
class AutofocusPage(QWidget):
    def __init__(self, ctl: Controller):
        super().__init__()
        self.ctl = ctl
        enabled = ctl.cfg.get("autofocus", "enabled", default=True)
        self.switch = make_switch(enabled, self._toggled)

        self.tile_state = Tile("Actif" if enabled else "Inactif", "autofocus", hot=True)
        self.tile_read = Tile("0", "notifications lues")
        self.tile_focus = Tile("0", "changements de fenêtre")
        tiles = QHBoxLayout()
        tiles.setSpacing(12)
        for t in (self.tile_state, self.tile_read, self.tile_focus):
            tiles.addWidget(t)
        tiles_w = QWidget()
        tiles_w.setObjectName("pageInner")
        tiles_w.setLayout(tiles)
        tiles.setContentsMargins(0, 0, 0, 0)

        status_frame, sl = card()
        self.status = label("Accès aux notifications : en attente…", "cardTitle")
        sl.addWidget(self.status)
        sl.addWidget(label(
            "Mise en place : 1) en jeu, Options > Général > « Notification en arrière-plan » ; "
            "2) Windows, Paramètres > Système > Notifications : activées ; 3) coupe le son des notifications "
            "de Dofus si besoin.", "muted", wrap=True))
        debug = option_row("Mode debug", "Affiche dans le journal chaque notification Dofus lue.",
                           make_switch(ctl.cfg.get("autofocus", "debug", default=False),
                                       lambda v: ctl.cfg.set("autofocus", "debug", v)))

        log_frame, ll = card()
        head = QHBoxLayout()
        head.addWidget(label("Journal", "cardTitle"))
        head.addStretch(1)
        clear = QPushButton("Effacer")
        head.addWidget(clear)
        ll.addLayout(head)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(500)
        clear.clicked.connect(self.log.clear)
        ll.addWidget(self.log, 1)

        body = QWidget()
        body.setObjectName("pageInner")
        row = QHBoxLayout(body)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(16)
        left = QVBoxLayout()
        left.setSpacing(12)
        left.addWidget(tiles_w)
        left.addWidget(status_frame)
        left.addWidget(debug)
        left.addStretch(1)
        row.addLayout(left, 1)
        row.addWidget(log_frame, 1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(page_frame("Autofocus", "Bascule sur le bon personnage dès que le jeu t'envoie une "
                                                 "notification.", body, self.switch))

        ctl.log.connect(self.add_log)
        ctl.info_changed.connect(self.update_counters)
        QTimer(self, interval=1000, timeout=lambda: self.isVisible() and self.update_counters()).start()

    def _toggled(self, enabled: bool):
        self.ctl.set_autofocus_enabled(enabled)
        self.tile_state.set_all("Actif" if enabled else "Inactif")

    def update_counters(self):
        ok = self.ctl.notifs.access_ok
        self.status.setText("Accès aux notifications : " + ("accordé ✓" if ok else "non accordé ✗"))
        self.status.setStyleSheet(f"color: {OK if ok else ERR};")
        self.tile_read.set_all(str(self.ctl.notifs.read_count))
        self.tile_focus.set_all(str(self.ctl.focus_count))

    def add_log(self, level: str, message: str):
        colors = {"ok": OK, "error": ERR, "notif": ACCENT2}
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(colors.get(level, MUTED)))
        cursor = self.log.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertText(f"{datetime.now():%H:%M:%S}  {message}\n", fmt)
        self.log.setTextCursor(cursor)
        self.log.ensureCursorVisible()


# --- page Prérequis --------------------------------------------------------------------
STATE_COLORS = {prereq.OK: OK, prereq.WARN: WARN, prereq.ERROR: ERR, prereq.PENDING: MUTED}


class PrereqPage(QWidget):
    """Liste les prérequis et indique ce qui manque, avec un lien vers le bon réglage Windows."""

    def __init__(self, ctl: Controller):
        super().__init__()
        self.ctl = ctl
        self.checks: list[prereq.Check] = []
        self.summary = Tile("…", "vérification", hot=True)
        self.grid = QGridLayout()
        self.grid.setSpacing(12)
        self.grid.setColumnStretch(0, 1)
        self.grid.setColumnStretch(1, 1)
        self.grid.setAlignment(Qt.AlignmentFlag.AlignTop)
        grid_w = QWidget()
        grid_w.setObjectName("pageInner")
        grid_w.setLayout(self.grid)
        self.grid.setContentsMargins(0, 0, 8, 0)

        area = QScrollArea()
        area.setWidgetResizable(True)
        area.setFrameShape(QFrame.Shape.NoFrame)
        area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        area.setWidget(grid_w)

        recheck = QPushButton("Revérifier")
        recheck.setObjectName("primary")
        recheck.clicked.connect(self.refresh)
        right = QWidget()
        right.setObjectName("pageInner")
        rl = QHBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(12)
        rl.addWidget(self.summary)
        rl.addWidget(recheck, 0, Qt.AlignmentFlag.AlignVCenter)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(page_frame("Prérequis", "Kalkid Rétro contrôle que ton PC est prêt.", area, right))
        self.refresh()

    def refresh(self) -> list[prereq.Check]:
        self.checks = prereq.check_all(self.ctl)
        while self.grid.count():
            item = self.grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        errors = sum(c.state == prereq.ERROR for c in self.checks)
        oks = sum(c.state == prereq.OK for c in self.checks)
        self.summary.set_all(f"{oks}/{len(self.checks)}", "tout est prêt ✓" if oks == len(self.checks)
                             else (f"{errors} à corriger" if errors else "à vérifier"))
        for i, check in enumerate(self.checks):
            frame, lay = card()
            row = QHBoxLayout()
            row.setSpacing(12)
            dot = label("●")
            dot.setStyleSheet(f"color: {STATE_COLORS[check.state]}; font-size: 14pt;")
            dot.setFixedWidth(20)
            texts = QVBoxLayout()
            texts.setSpacing(2)
            texts.addWidget(label(check.title, "cardTitle"))
            texts.addWidget(label(check.detail, "muted", wrap=True))
            row.addWidget(dot, 0, Qt.AlignmentFlag.AlignTop)
            row.addLayout(texts, 1)
            if check.fix_uri and check.state in (prereq.ERROR, prereq.WARN):
                fix = QPushButton("Ouvrir")
                fix.setObjectName("primary")
                fix.clicked.connect(lambda _=False, uri=check.fix_uri: os.startfile(uri))
                row.addWidget(fix, 0, Qt.AlignmentFlag.AlignVCenter)
            lay.addLayout(row)
            self.grid.addWidget(frame, i // 2, i % 2)
        return self.checks


# --- page Raccourcis -------------------------------------------------------------------
class ShortcutsPage(QWidget):
    def __init__(self, ctl: Controller):
        super().__init__()
        left = [
            option_row("Fenêtre suivante", "Passe au personnage suivant dans l'ordre.", HotkeyButton(ctl, "next")),
            option_row("Fenêtre précédente", "Revient au personnage précédent.", HotkeyButton(ctl, "prev")),
        ]
        right = [
            option_row("Personnage principal", "Passe sur le personnage marqué ★.", HotkeyButton(ctl, "main")),
            option_row("Seulement en jeu", "Les raccourcis ne fonctionnent que si une fenêtre Dofus Rétro est "
                                           "au premier plan (recommandé).",
                       make_switch(ctl.cfg.get("hotkeys_only_in_game", default=True),
                                   lambda v: (ctl.cfg.set("hotkeys_only_in_game", v), ctl.rebind_hotkeys()))),
        ]
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(page_frame("Raccourcis", "Clique sur un raccourci puis appuie sur la touche voulue.",
                                    columns(left, right)))


# --- page Outils -----------------------------------------------------------------------
class ToolsPage(QWidget):
    def __init__(self, ctl: Controller, confirm_macros):
        super().__init__()
        self.ctl = ctl
        cfg = ctl.cfg
        self._confirm = confirm_macros

        def set_tool(key):
            return lambda value: (cfg.set("tools", key, value), ctl.rebind_hotkeys())

        self.info = label("Dernier clic : aucun clic pour l'instant", "muted", wrap=True)

        warn, wl = card("warn")
        wl.addWidget(label("⚠  Outils de macro", "cardTitle"))
        wl.addWidget(label(MACRO_WARNING, "muted", wrap=True))

        # --- colonne gauche : clics ---
        left: list[QWidget] = [option_row("Anti-clignotement", "Éteint le clignotement des fenêtres du jeu "
                               "dans la barre des tâches.", make_switch(cfg.get("tools", "no_flash", default=True),
                                                                        set_tool("no_flash")))]
        self.clicks = make_switch(cfg.get("tools", "clicks_enabled", default=False), self._clicks_toggled)
        left.append(option_row("Clics synchronisés", "Clic molette : clic gauche au même endroit sur tous les "
                               "comptes, avec un délai aléatoire.", self.clicks))
        tune, tl = card()
        tl.addLayout(field_row("Délai aléatoire entre fenêtres",
                               spin(cfg.get("tools", "delay_min", default=90), 0, 5000, set_tool("delay_min")),
                               label("à"),
                               spin(cfg.get("tools", "delay_max", default=130), 0, 5000, set_tool("delay_max"))))
        tl.addLayout(field_row("Clic molette actif",
                               make_switch(cfg.get("tools", "wheel", default=True), set_tool("wheel"))))
        tl.addLayout(field_row("Raccourci « clic sans délai »", HotkeyButton(ctl, "click_all")))
        tl.addWidget(self.info)
        left.append(tune)

        # --- colonne droite : invitation de groupe ---
        self.invite = make_switch(cfg.get("tools", "invite_enabled", default=False), self._invite_toggled)
        right: list[QWidget] = [option_row("Invitation de groupe", "Le chef invite tous les personnages connectés, "
                                "chacun valide puis invite le suivant.", self.invite)]
        grp, gl = card()
        self.leader = QComboBox()
        self.leader.setMinimumWidth(170)
        self.leader.activated.connect(lambda _: cfg.set("tools", "leader", self.leader.currentText()))
        gl.addLayout(field_row("Chef de groupe", self.leader))
        self.chat_pos = label("")
        self.chat_pos.setStyleSheet(f"color: {ACCENT2}; font-weight: 700;")
        gl.addLayout(field_row("Position du chat", self.chat_pos, HotkeyButton(ctl, "capture_chat")))
        gl.addWidget(label("Place la souris sur le champ de saisie du chat dans le jeu, puis presse la touche "
                           "ci-dessus.", "muted", wrap=True))
        gl.addLayout(field_row("Attente après /invite",
                               spin(cfg.get("tools", "invite_wait", default=200), 0, 5000, set_tool("invite_wait"))))
        gl.addLayout(field_row("Pause entre deux invités",
                               spin(cfg.get("tools", "invite_pause", default=50), 0, 5000, set_tool("invite_pause"))))
        self.invite_btn = QPushButton("Inviter tout le monde")
        self.invite_btn.setObjectName("primary")
        self.invite_btn.clicked.connect(ctl.invite_group)
        gl.addLayout(field_row("Raccourci « inviter tout le monde »", HotkeyButton(ctl, "invite")))
        gl.addWidget(self.invite_btn)
        right.append(grp)

        body = QWidget()
        body.setObjectName("pageInner")
        bl = QVBoxLayout(body)
        bl.setContentsMargins(0, 0, 0, 0)
        bl.setSpacing(12)
        bl.addWidget(warn)
        bl.addWidget(columns(left, right), 1)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(page_frame("Outils", "Fonctions optionnelles pour le multicompte (désactivées par défaut).",
                                    body))

        ctl.windows_changed.connect(self.refresh_leader)
        ctl.chat_pos_changed.connect(self.refresh_chat_pos)
        ctl.info_changed.connect(self.refresh_info)
        self.refresh_leader()
        self.refresh_chat_pos()
        self._sync_enabled()

    def refresh_info(self):
        gaps = " · ".join(str(g) for g in self.ctl.last_gaps)
        text = f"Dernier clic : {self.ctl.last_info}"
        if gaps:
            text += f"\nÉcarts réels (ms) : {gaps}"
        self.info.setText(text)

    def _clicks_toggled(self, value: bool):
        if value and not self._confirm():
            self.clicks.set_checked_silently(False)
            return
        self.ctl.cfg.set("tools", "clicks_enabled", value)
        self.ctl.rebind_hotkeys()

    def _invite_toggled(self, value: bool):
        if value and not self._confirm():
            self.invite.set_checked_silently(False)
            return
        self.ctl.cfg.set("tools", "invite_enabled", value)
        self.ctl.rebind_hotkeys()
        self._sync_enabled()

    def _sync_enabled(self):
        self.invite_btn.setEnabled(bool(self.ctl.cfg.get("tools", "invite_enabled", default=False)))

    def refresh_leader(self):
        current = self.ctl.cfg.get("tools", "leader", default="") or self.ctl.cfg.get("main", default="")
        self.leader.blockSignals(True)
        self.leader.clear()
        order = self.ctl.order()
        self.leader.addItems(order)
        if current in order:
            self.leader.setCurrentText(current)
        elif order:
            self.leader.setCurrentIndex(0)
        self.leader.blockSignals(False)
        if order and self.leader.currentText():
            self.ctl.cfg.set("tools", "leader", self.leader.currentText())

    def refresh_chat_pos(self):
        x = self.ctl.cfg.get("tools", "chat_x", default=-1)
        y = self.ctl.cfg.get("tools", "chat_y", default=-1)
        self.chat_pos.setText("non définie" if x < 0 else f"X {x} · Y {y}")


# --- page Réglages ----------------------------------------------------------------------
def _autostart_enabled() -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            winreg.QueryValueEx(key, APP_NAME)
            return True
    except OSError:
        return False


def _set_autostart(enabled: bool) -> None:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            if enabled:
                command = (f'"{sys.executable}" --hidden' if getattr(sys, "frozen", False)
                           else f'"{sys.executable}" -m kalkid_retro --hidden')
                winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, command)
            else:
                winreg.DeleteValue(key, APP_NAME)
    except OSError:
        pass


class UpdateCard(QFrame):
    """Vérification des mises à jour et installation de la dernière version."""

    def __init__(self, ctl: Controller):
        super().__init__()
        self.setObjectName("card")
        self.ctl = ctl
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 14, 18, 14)
        lay.setSpacing(8)
        lay.addWidget(label("Mises à jour", "cardTitle"))
        self.status = label(f"Version installée : v{__version__}", "muted", wrap=True)
        lay.addWidget(self.status)
        self.bar = QProgressBar()
        self.bar.setRange(0, 100)
        self.bar.setTextVisible(False)
        self.bar.setFixedHeight(8)
        self.bar.hide()
        lay.addWidget(self.bar)
        row = QHBoxLayout()
        self.check_btn = QPushButton("Vérifier les mises à jour")
        self.check_btn.clicked.connect(self._check)
        self.update_btn = QPushButton("Mettre à jour")
        self.update_btn.setObjectName("primary")
        self.update_btn.clicked.connect(self._install)
        self.update_btn.hide()
        self.page_btn = QPushButton("Ouvrir la page de téléchargement")
        self.page_btn.clicked.connect(lambda: os.startfile(updater.RELEASES_PAGE))
        self.page_btn.hide()
        row.addWidget(self.check_btn)
        row.addWidget(self.update_btn)
        row.addWidget(self.page_btn)
        row.addStretch(1)
        lay.addLayout(row)
        lay.addLayout(field_row("Vérifier au lancement",
                                make_switch(ctl.cfg.get("settings", "check_updates", default=True),
                                            lambda v: ctl.cfg.set("settings", "check_updates", v))))
        up = ctl.updater
        up.checked.connect(self._checked)
        up.progress.connect(self.bar.setValue)
        up.failed.connect(self._failed)
        up.installing.connect(self._installing)
        if up.info is not None:
            self._show_available(up.info)

    def _check(self):
        self.check_btn.setEnabled(False)
        self.status.setStyleSheet("")
        self.status.setText("Vérification en cours…")
        self.ctl.updater.check()

    def _show_available(self, info):
        self.status.setStyleSheet(f"color: {ACCENT2};")
        self.status.setText(f"Nouvelle version disponible : v{info.version}  (installée : v{__version__})")
        self.update_btn.setText(f"Mettre à jour vers v{info.version}")
        self.update_btn.show()
        self.page_btn.hide()

    def _checked(self, info, error: str):
        self.check_btn.setEnabled(True)
        if error:
            self.status.setStyleSheet(f"color: {ERR};")
            self.status.setText(error)
            self.update_btn.hide()
        elif info is not None:
            self._show_available(info)
        else:
            self.status.setStyleSheet(f"color: {OK};")
            self.status.setText(f"Tu as la dernière version (v{__version__}) ✓")
            self.update_btn.hide()

    def _install(self):
        self.update_btn.setEnabled(False)
        self.check_btn.setEnabled(False)
        self.bar.setValue(0)
        self.bar.show()
        self.status.setStyleSheet("")
        self.status.setText("Téléchargement de la mise à jour…")
        self.ctl.updater.install()

    def _failed(self, message: str):
        self.bar.hide()
        self.update_btn.setEnabled(True)
        self.check_btn.setEnabled(True)
        self.status.setStyleSheet(f"color: {ERR};")
        self.status.setText(message)
        self.page_btn.show()

    def _installing(self):
        self.status.setStyleSheet(f"color: {OK};")
        self.status.setText("Mise à jour téléchargée : redémarrage de l'application…")
        QTimer.singleShot(600, self.window().quit_app)


class SettingsPage(QWidget):
    def __init__(self, ctl: Controller):
        super().__init__()
        cfg = ctl.cfg
        info, il = card()
        il.addWidget(label(f"{APP_NAME}  v{__version__}", "cardTitle"))
        il.addWidget(label(
            "Gestionnaire de fenêtres multicompte pour Dofus Rétro : autofocus par notifications, ordre des "
            "personnages, raccourcis, et outils optionnels (clics synchronisés, invitation de groupe).",
            "muted", wrap=True))
        il.addWidget(label("Projet open source (licence MIT) : github.com/KalDT13/Kalkid-Retro", "muted", wrap=True))
        il.addWidget(label(
            "Le principe de l'autofocus par notifications Windows a été popularisé par Dracoon (Slyss49). "
            "Kalkid Rétro est une implémentation indépendante, sans code repris de Dracoon. Cet outil n'est "
            "pas affilié à Ankama.", "muted", wrap=True))
        left = [
            UpdateCard(ctl),
            option_row("Réduire dans la zone de notification", "La croix de la fenêtre range l'application près "
                       "de l'horloge au lieu de la fermer.",
                       make_switch(cfg.get("settings", "close_to_tray", default=True),
                                   lambda v: cfg.set("settings", "close_to_tray", v))),
            option_row("Démarrer réduit", "Au lancement, l'application démarre directement dans la zone de "
                       "notification.", make_switch(cfg.get("settings", "start_hidden", default=False),
                                                    lambda v: cfg.set("settings", "start_hidden", v))),
            option_row("Lancer avec Windows", "Démarre Kalkid Rétro à l'ouverture de session.",
                       make_switch(_autostart_enabled(), _set_autostart)),
        ]
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(page_frame("Réglages", "Comportement de l'application.", columns(left, [info])))


# --- fenêtre principale -----------------------------------------------------------------
class MainWindow(QMainWindow):
    def __init__(self, ctl: Controller):
        super().__init__()
        self.ctl = ctl
        self._quitting = False
        self._first_check = True
        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(make_icon())
        self.resize(1120, 740)
        self.setMinimumSize(980, 640)

        root = QWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)
        main = QHBoxLayout(root)
        main.setContentsMargins(0, 0, 0, 0)
        main.setSpacing(0)

        # --- menu latéral ---
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(230)
        sl = QVBoxLayout(sidebar)
        sl.setContentsMargins(16, 22, 16, 18)
        sl.setSpacing(4)
        brand = QHBoxLayout()
        brand.setSpacing(12)
        logo = QLabel()
        logo.setPixmap(round_logo(44))
        logo.setFixedSize(44, 44)
        brand.addWidget(logo)
        names = QVBoxLayout()
        names.setSpacing(0)
        names.addWidget(label("Kalkid Rétro", "appTitle"))
        names.addWidget(label(f"v{__version__}", "muted"))
        brand.addLayout(names, 1)
        sl.addLayout(brand)
        sl.addSpacing(22)

        self.stack = QStackedWidget()
        self.prereq_page = PrereqPage(ctl)
        pages = [
            ("people", "Personnages", CharactersPage(ctl)),
            ("bell", "Autofocus", AutofocusPage(ctl)),
            ("shield", "Prérequis", self.prereq_page),
            ("keyboard", "Raccourcis", ShortcutsPage(ctl)),
            ("sliders", "Outils", ToolsPage(ctl, self._confirm_macros)),
            ("gear", "Réglages", SettingsPage(ctl)),
        ]
        self.nav_items: list[SideNavItem] = []
        for index, (icon, text, page) in enumerate(pages):
            self.stack.addWidget(page)
            item = SideNavItem(icon, text)
            item.clicked.connect(lambda _=False, i=index: self.stack.setCurrentIndex(i))
            sl.addWidget(item)
            self.nav_items.append(item)
        self.prereq_index = 2
        self.nav_items[0].setChecked(True)
        sl.addStretch(1)

        self.update_chip = QPushButton()
        self.update_chip.setObjectName("primary")
        self.update_chip.setCursor(Qt.CursorShape.PointingHandCursor)
        self.update_chip.clicked.connect(lambda: self._goto(5))
        self.update_chip.hide()
        sl.addWidget(self.update_chip)
        ctl.updater.checked.connect(self._update_checked)
        self.chip = label("", "tag")
        self.subtitle = label("", "muted")
        sl.addWidget(self.chip, 0, Qt.AlignmentFlag.AlignLeft)
        sl.addWidget(self.subtitle)
        main.addWidget(sidebar)

        # --- contenu ---
        content = QVBoxLayout()
        content.setContentsMargins(0, 0, 0, 0)
        content.setSpacing(0)
        self.banner_frame = QFrame()
        self.banner_frame.setObjectName("banner")
        bl = QHBoxLayout(self.banner_frame)
        bl.setContentsMargins(0, 0, 0, 0)
        self.banner = QPushButton()
        self.banner.setObjectName("banner")
        self.banner.setCursor(Qt.CursorShape.PointingHandCursor)
        bl.addWidget(self.banner)
        wrap = QHBoxLayout()
        wrap.setContentsMargins(28, 16, 28, 0)
        wrap.addWidget(self.banner_frame)
        content.addLayout(wrap)
        self.banner_frame.hide()
        self.banner.clicked.connect(lambda: self._goto(self.prereq_index))
        content.addWidget(self.stack, 1)
        main.addLayout(content, 1)

        ctl.windows_changed.connect(self.update_status)
        ctl.info_changed.connect(self.update_status)
        self.update_status()

        self.tray = QSystemTrayIcon(make_icon(), self)
        self.tray.setToolTip(APP_NAME)
        menu = QMenu()
        open_action = QAction("Ouvrir", menu)
        open_action.triggered.connect(self.show_window)
        quit_action = QAction("Quitter", menu)
        quit_action.triggered.connect(self.quit_app)
        menu.addAction(open_action)
        menu.addAction(quit_action)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(lambda reason: self.show_window()
                                    if reason == QSystemTrayIcon.ActivationReason.Trigger else None)
        self.tray.show()

        # Rien ne tourne en tâche de fond quand la fenêtre est cachée : ces minuteries ne sont
        # actives que lorsqu'elle est affichée (l'autofocus et les raccourcis n'en ont pas besoin).
        self.refresh_timer = QTimer(self, interval=3000, timeout=ctl.refresh_windows)
        self.prereq_timer = QTimer(self, interval=5000, timeout=self.update_prereq)
        QTimer.singleShot(2500, self.update_prereq)   # laisse à l'accès aux notifications le temps de répondre

    def _update_checked(self, info, _error: str):
        """Pastille dans le menu quand une nouvelle version est disponible."""
        if info is not None:
            self.update_chip.setText(f"⬆  Mise à jour v{info.version}")
            self.update_chip.show()
        else:
            self.update_chip.hide()

    def _goto(self, index: int):
        self.stack.setCurrentIndex(index)
        self.nav_items[index].setChecked(True)

    def update_status(self):
        n = len(self.ctl.windows)
        self.subtitle.setText(f"{n} fenêtre{'s' if n > 1 else ''} connectée{'s' if n > 1 else ''}")
        af = self.ctl.cfg.get("autofocus", "enabled", default=True)
        self.chip.setText("● Autofocus actif" if af else "○ Autofocus off")

    def update_prereq(self):
        checks = self.prereq_page.refresh()
        problems = prereq.blocking_problems(checks)
        self.nav_items[self.prereq_index].set_badge(bool(problems))
        if problems:
            self.banner.setText(f"⚠  Configuration incomplète : {problems[0].title}. Clique ici pour voir quoi "
                                f"corriger ({len(problems)} problème{'s' if len(problems) > 1 else ''}).")
            self.banner_frame.show()
            if self._first_check:
                self._goto(self.prereq_index)
        else:
            self.banner_frame.hide()
        self._first_check = False

    def _confirm_macros(self) -> bool:
        if self.ctl.cfg.get("settings", "warning_ack", default=False):
            return True
        answer = QMessageBox.warning(self, "Outils de macro", MACRO_WARNING + "\n\nActiver quand même ?",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                     QMessageBox.StandardButton.No)
        if answer == QMessageBox.StandardButton.Yes:
            self.ctl.cfg.set("settings", "warning_ack", True)
            return True
        return False

    # --- fenêtre / zone de notification ---
    def showEvent(self, event):
        super().showEvent(event)
        try:   # barre de titre sombre (Windows 10 20H1+ / 11)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(int(self.winId()), 20, ctypes.byref(ctypes.c_int(1)), 4)
        except Exception:
            pass
        self.ctl.refresh_windows()
        self.refresh_timer.start()
        self.prereq_timer.start()

    def hideEvent(self, event):
        super().hideEvent(event)
        self.refresh_timer.stop()
        self.prereq_timer.stop()

    def show_window(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def quit_app(self):
        self._quitting = True
        self.tray.hide()
        self.ctl.shutdown()
        QApplication.quit()

    def closeEvent(self, event):
        if not self._quitting and self.ctl.cfg.get("settings", "close_to_tray", default=True):
            event.ignore()
            self.hide()
        else:
            self.quit_app()
            event.accept()
