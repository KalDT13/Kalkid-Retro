"""Interface PySide6 de Kalkid Rétro."""

from __future__ import annotations

import os
import sys
import winreg
from datetime import datetime

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QAction, QColor, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QComboBox, QFrame, QHBoxLayout, QInputDialog,
                               QLabel, QLineEdit, QListWidget, QListWidgetItem, QMainWindow, QMessageBox,
                               QPlainTextEdit, QPushButton, QScrollArea, QSpinBox, QSystemTrayIcon, QTabWidget,
                               QVBoxLayout, QWidget, QMenu)

from . import APP_NAME, __version__, prereq
from .config import EVENTS
from .controller import Controller
from .theme import ACCENT, ERR, MUTED, OK, TXT, make_icon

EVENT_ICONS = {"combat": "⚔", "mp": "💬", "groupe": "👥", "echange": "🔄"}
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"

MACRO_WARNING = (
    "Ces outils envoient des actions sur plusieurs comptes à la fois (clics synchronisés, invitations "
    "automatiques). Ankama tolère les outils de gestion de fenêtres mais interdit les macros : ton compte "
    "pourrait être sanctionné. Ils sont désactivés par défaut. Tu les utilises à tes risques."
)


# --- petits composants --------------------------------------------------------------
def label(text: str, name: str = "", wrap: bool = False) -> QLabel:
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
    lay.setSpacing(6)
    return frame, lay


def toggle(checked: bool, on_toggle, labels=("ON", "OFF"), width: int = 78) -> QPushButton:
    btn = QPushButton()
    btn.setCheckable(True)
    btn.setFixedWidth(width)

    def refresh():
        btn.setText(labels[0] if btn.isChecked() else labels[1])

    btn.setChecked(checked)
    refresh()
    btn.toggled.connect(lambda state: (refresh(), on_toggle(state)))
    return btn


def option_row(title: str, desc: str, control: QWidget) -> QFrame:
    frame, lay = card()
    row = QHBoxLayout()
    texts = QVBoxLayout()
    texts.setSpacing(2)
    texts.addWidget(label(title, "title"))
    if desc:
        texts.addWidget(label(desc, "muted", wrap=True))
    row.addLayout(texts, 1)
    row.addWidget(control, 0, Qt.AlignmentFlag.AlignVCenter)
    lay.addLayout(row)
    return frame


def scroll_page(*widgets: QWidget) -> QScrollArea:
    area = QScrollArea()
    area.setWidgetResizable(True)
    area.setFrameShape(QFrame.Shape.NoFrame)
    inner = QWidget()
    inner.setObjectName("root")
    lay = QVBoxLayout(inner)
    lay.setContentsMargins(24, 18, 24, 18)
    lay.setSpacing(10)
    for w in widgets:
        lay.addWidget(w)
    lay.addStretch(1)
    area.setWidget(inner)
    return area


def spin(value: int, minimum: int, maximum: int, on_change, suffix: str = " ms") -> QSpinBox:
    box = QSpinBox()
    box.setRange(minimum, maximum)
    box.setValue(value)
    box.setSuffix(suffix)
    box.setFixedWidth(100)
    box.valueChanged.connect(on_change)
    return box


class HotkeyButton(QPushButton):
    """Bouton qui affiche un raccourci ; un clic lance la capture de la prochaine combinaison."""

    def __init__(self, ctl: Controller, action: str):
        super().__init__()
        self.ctl, self.action = ctl, action
        self.setMinimumWidth(150)
        self.clicked.connect(self._start)
        ctl.hotkey_captured.connect(self._captured)
        self._refresh()

    def _refresh(self):
        self.setText(self.ctl.cfg.get("hotkeys", self.action, default="") or "— aucun —")

    def _start(self):
        self.setText("Appuie sur une touche… (Échap = annuler)")
        self.ctl.capture_hotkey(self.action)

    def _captured(self, action: str, value: str):
        if action == self.action:
            self._refresh()


# --- onglet Personnages -------------------------------------------------------------
class CharacterRow(QFrame):
    def __init__(self, ctl: Controller, pseudo: str, index: int):
        super().__init__()
        self.setObjectName("row")
        self.setFixedHeight(54)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 0, 12, 0)
        lay.setSpacing(8)
        online = pseudo in ctl.windows

        grip = label("⠿", "muted")
        grip.setFixedWidth(16)
        idx = label(str(index), "muted")
        idx.setFixedWidth(22)
        dot = label("●")
        dot.setStyleSheet(f"color: {OK if online else '#555a70'};")
        dot.setFixedWidth(14)
        dot.setToolTip("Fenêtre ouverte" if online else "Fenêtre fermée")
        name = label(pseudo, "title")
        name.setStyleSheet(f"font-weight: 700; color: {TXT if online else MUTED};")
        for w in (grip, idx, dot):
            lay.addWidget(w)
        lay.addWidget(name, 1)

        enabled = ctl.events_for(pseudo)
        self.event_buttons: dict[str, QPushButton] = {}
        for key, icon in EVENT_ICONS.items():
            b = QPushButton(icon)
            b.setObjectName("ev")
            b.setCheckable(True)
            b.setFixedSize(40, 32)
            b.setToolTip(f"Autofocus : {EVENTS[key]}")
            b.setChecked(key in enabled)
            b.toggled.connect(lambda state, k=key, p=pseudo: ctl.set_event(p, k, state))
            self.event_buttons[key] = b
            lay.addWidget(b)

        main = QPushButton("★")
        main.setObjectName("ev")
        main.setCheckable(True)
        main.setFixedSize(46, 32)
        main.setToolTip("Personnage principal")
        main.setChecked(ctl.cfg.get("main", default="") == pseudo)
        main.clicked.connect(lambda checked, p=pseudo: self._set_main(ctl, p, checked))
        lay.addWidget(main)

        excl = QPushButton("Exclure")
        excl.setCheckable(True)
        excl.setFixedSize(90, 32)
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
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 14, 24, 14)
        lay.setSpacing(8)

        head = QHBoxLayout()
        head.setContentsMargins(12, 0, 12, 0)
        head.setSpacing(8)
        spacer = QWidget()
        spacer.setFixedWidth(16 + 22 + 14 + 24)
        head.addWidget(spacer)
        head.addWidget(label("Personnages", "colhead"), 1)
        head.addWidget(label("Autofocus :", "colhead"))
        self.col_buttons: dict[str, QPushButton] = {}
        for key, icon in EVENT_ICONS.items():
            b = QPushButton(icon)
            b.setObjectName("ev")
            b.setFixedSize(40, 32)
            b.setToolTip(f"Activer / désactiver « {EVENTS[key]} » pour tous")
            b.clicked.connect(lambda _=False, k=key: self._toggle_column(k))
            self.col_buttons[key] = b
            head.addWidget(b)
        end = QWidget()
        end.setFixedWidth(46 + 90 + 16)
        head.addWidget(end)
        lay.addLayout(head)

        self.list = QListWidget()
        self.list.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.list.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.list.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.list.model().rowsMoved.connect(lambda *a: QTimer.singleShot(0, self._order_changed))
        lay.addWidget(self.list, 1)

        self.empty = label("Aucune fenêtre Dofus Rétro détectée.", "muted")
        self.empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self.empty)

        bottom = QHBoxLayout()
        self.preset_name = QLineEdit()
        self.preset_name.setPlaceholderText("Nom du preset")
        self.preset_name.setFixedWidth(170)
        save = QPushButton("Enregistrer comme preset")
        save.clicked.connect(self._save_preset)
        self.preset_combo = QComboBox()
        self.preset_combo.setMinimumWidth(190)
        self.preset_combo.activated.connect(self._load_preset)
        delete = QPushButton("Supprimer")
        delete.clicked.connect(self._delete_preset)
        bottom.addWidget(self.preset_name)
        bottom.addWidget(save)
        bottom.addStretch(1)
        bottom.addWidget(self.preset_combo)
        bottom.addWidget(delete)
        lay.addLayout(bottom)

        ctl.windows_changed.connect(self.rebuild)
        self.rebuild()
        self._refresh_presets()

    def rebuild(self):
        self.list.blockSignals(True)
        self.list.clear()
        order = self.ctl.order()
        for i, pseudo in enumerate(order, 1):
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, pseudo)
            row = CharacterRow(self.ctl, pseudo, i)
            item.setSizeHint(QSize(100, 60))
            self.list.addItem(item)
            self.list.setItemWidget(item, row)
        self.list.blockSignals(False)
        self.empty.setVisible(not order)

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


# --- onglet Autofocus ---------------------------------------------------------------
class AutofocusPage(QWidget):
    def __init__(self, ctl: Controller):
        super().__init__()
        self.ctl = ctl
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 18, 24, 18)
        lay.setSpacing(10)

        lay.addWidget(option_row(
            "Autofocus", "Passe automatiquement sur la fenêtre du personnage concerné quand le jeu envoie une "
                         "notification (combat, message privé, groupe, échange).",
            toggle(ctl.cfg.get("autofocus", "enabled", default=True), ctl.set_autofocus_enabled)))

        stats_frame, stats = card()
        self.status = label("Accès aux notifications : en attente…", "muted")
        self.counters = label("", "muted")
        stats.addWidget(self.status)
        stats.addWidget(self.counters)
        setup = label(
            "Mise en place : 1) en jeu, Options > Général > « Notification en arrière-plan » ; "
            "2) Windows, Paramètres > Système > Notifications : activées ; 3) coupe le son des notifications "
            "de Dofus si besoin.", "muted", wrap=True)
        stats.addWidget(setup)
        lay.addWidget(stats_frame)

        lay.addWidget(option_row("Mode debug", "Affiche dans le journal chaque notification Dofus lue.",
                                 toggle(ctl.cfg.get("autofocus", "debug", default=False),
                                        lambda v: ctl.cfg.set("autofocus", "debug", v))))

        head = QHBoxLayout()
        head.addWidget(label("Journal", "title"))
        head.addStretch(1)
        clear = QPushButton("Effacer")
        head.addWidget(clear)
        lay.addLayout(head)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(500)
        clear.clicked.connect(self.log.clear)
        lay.addWidget(self.log, 1)

        ctl.log.connect(self.add_log)
        ctl.info_changed.connect(self.update_counters)
        QTimer(self, interval=1000, timeout=lambda: self.isVisible() and self.update_counters()).start()

    def update_counters(self):
        ok = self.ctl.notifs.access_ok
        self.status.setText("Accès aux notifications : " + ("accordé ✓" if ok else "non accordé ✗"))
        self.status.setStyleSheet(f"color: {OK if ok else ERR};")
        self.counters.setText(f"Notifications lues : {self.ctl.notifs.read_count}   ·   "
                              f"Changements de fenêtre : {self.ctl.focus_count}")

    def add_log(self, level: str, message: str):
        colors = {"ok": OK, "error": ERR, "notif": ACCENT}
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(colors.get(level, MUTED)))
        cursor = self.log.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertText(f"{datetime.now():%H:%M:%S}  {message}\n", fmt)
        self.log.setTextCursor(cursor)
        self.log.ensureCursorVisible()


# --- onglet Prérequis ---------------------------------------------------------------
STATE_STYLE = {
    prereq.OK: ("●", OK), prereq.WARN: ("●", ACCENT), prereq.ERROR: ("●", ERR), prereq.PENDING: ("●", MUTED),
}


class PrereqPage(QWidget):
    """Liste les prérequis et indique ce qui manque, avec un raccourci vers le bon réglage Windows."""

    def __init__(self, ctl: Controller):
        super().__init__()
        self.ctl = ctl
        self.checks: list[prereq.Check] = []
        self._holder = QVBoxLayout()
        self._holder.setSpacing(8)
        intro = label("Kalkid Rétro vérifie que ton PC est prêt. Rouge = à corriger, orange = à vérifier, "
                      "vert = OK.", "muted", wrap=True)
        recheck = QPushButton("Revérifier")
        recheck.setObjectName("primary")
        recheck.clicked.connect(self.refresh)
        top = QHBoxLayout()
        top.addWidget(intro, 1)
        top.addWidget(recheck)
        wrapper = QWidget()
        wl = QVBoxLayout(wrapper)
        wl.setContentsMargins(0, 0, 0, 0)
        wl.addLayout(top)
        wl.addLayout(self._holder)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(scroll_page(wrapper))
        self.refresh()

    def refresh(self) -> list[prereq.Check]:
        self.checks = prereq.check_all(self.ctl)
        while self._holder.count():
            item = self._holder.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        for check in self.checks:
            frame, lay = card()
            row = QHBoxLayout()
            symbol, color = STATE_STYLE[check.state]
            dot = label(symbol)
            dot.setStyleSheet(f"color: {color}; font-size: 16pt;")
            dot.setFixedWidth(26)
            texts = QVBoxLayout()
            texts.setSpacing(2)
            texts.addWidget(label(check.title, "title"))
            texts.addWidget(label(check.detail, "muted", wrap=True))
            row.addWidget(dot, 0, Qt.AlignmentFlag.AlignTop)
            row.addLayout(texts, 1)
            if check.fix_uri and check.state in (prereq.ERROR, prereq.WARN):
                fix = QPushButton("Ouvrir le réglage")
                fix.clicked.connect(lambda _=False, uri=check.fix_uri: os.startfile(uri))
                row.addWidget(fix, 0, Qt.AlignmentFlag.AlignVCenter)
            lay.addLayout(row)
            self._holder.addWidget(frame)
        return self.checks


# --- onglet Raccourcis --------------------------------------------------------------
class ShortcutsPage(QWidget):
    def __init__(self, ctl: Controller):
        super().__init__()
        rows = [
            option_row("Fenêtre suivante", "Passe au personnage suivant dans l'ordre.", HotkeyButton(ctl, "next")),
            option_row("Fenêtre précédente", "Revient au personnage précédent.", HotkeyButton(ctl, "prev")),
            option_row("Personnage principal", "Passe sur le personnage marqué ★.", HotkeyButton(ctl, "main")),
            option_row("Seulement en jeu", "Les raccourcis ne fonctionnent que si une fenêtre Dofus Rétro est "
                                           "au premier plan (recommandé).",
                       toggle(ctl.cfg.get("hotkeys_only_in_game", default=True),
                              lambda v: (ctl.cfg.set("hotkeys_only_in_game", v), ctl.rebind_hotkeys()))),
        ]
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(scroll_page(*rows))


# --- onglet Outils ------------------------------------------------------------------
class ToolsPage(QWidget):
    def __init__(self, ctl: Controller, confirm_macros):
        super().__init__()
        self.ctl = ctl
        cfg = ctl.cfg
        self._confirm = confirm_macros

        def set_tool(key):
            return lambda value: (cfg.set("tools", key, value), ctl.rebind_hotkeys())

        widgets: list[QWidget] = []
        widgets.append(option_row("Anti-clignotement", "Éteint le clignotement des fenêtres du jeu dans la "
                                  "barre des tâches.", toggle(cfg.get("tools", "no_flash", default=True),
                                                              set_tool("no_flash"))))

        warn, wl = card("warn")
        wl.addWidget(label("⚠  Outils de macro", "title"))
        wl.addWidget(label(MACRO_WARNING, "muted", wrap=True))
        widgets.append(warn)

        # Clics synchronisés
        self.clicks = toggle(cfg.get("tools", "clicks_enabled", default=False), self._clicks_toggled)
        widgets.append(option_row("Clics synchronisés", "Clic molette : clic gauche au même endroit sur tous "
                                  "les comptes, avec un délai aléatoire. Le raccourci ci-dessous clique sans "
                                  "délai.", self.clicks))
        tune, tl = card()
        row1 = QHBoxLayout()
        row1.addWidget(label("Délai aléatoire entre fenêtres (molette)"))
        row1.addStretch(1)
        row1.addWidget(spin(cfg.get("tools", "delay_min", default=90), 0, 5000, set_tool("delay_min")))
        row1.addWidget(label("à"))
        row1.addWidget(spin(cfg.get("tools", "delay_max", default=130), 0, 5000, set_tool("delay_max")))
        tl.addLayout(row1)
        row2 = QHBoxLayout()
        row2.addWidget(label("Clic molette actif"))
        row2.addStretch(1)
        row2.addWidget(toggle(cfg.get("tools", "wheel", default=True), set_tool("wheel")))
        tl.addLayout(row2)
        row3 = QHBoxLayout()
        row3.addWidget(label("Raccourci « clic sans délai »"))
        row3.addStretch(1)
        row3.addWidget(HotkeyButton(ctl, "click_all"))
        tl.addLayout(row3)
        widgets.append(tune)

        # Invitation de groupe
        self.invite = toggle(cfg.get("tools", "invite_enabled", default=False), self._invite_toggled)
        widgets.append(option_row("Invitation de groupe", "Le chef invite tous les personnages connectés, "
                                  "chacun valide puis invite le suivant.", self.invite))
        grp, gl = card()
        r1 = QHBoxLayout()
        r1.addWidget(label("Chef de groupe"))
        r1.addStretch(1)
        self.leader = QComboBox()
        self.leader.setMinimumWidth(180)
        self.leader.activated.connect(lambda _: cfg.set("tools", "leader", self.leader.currentText()))
        r1.addWidget(self.leader)
        gl.addLayout(r1)
        r2 = QHBoxLayout()
        r2.addWidget(label("Position du chat"))
        r2.addStretch(1)
        self.chat_pos = label("")
        self.chat_pos.setStyleSheet(f"color: {ACCENT}; font-weight: 700;")
        r2.addWidget(self.chat_pos)
        r2.addWidget(HotkeyButton(ctl, "capture_chat"))
        gl.addLayout(r2)
        gl.addWidget(label("Place la souris sur le champ de saisie du chat dans le jeu, puis presse la touche "
                           "ci-dessus.", "muted", wrap=True))
        r3 = QHBoxLayout()
        r3.addWidget(label("Attente après /invite"))
        r3.addStretch(1)
        r3.addWidget(spin(cfg.get("tools", "invite_wait", default=200), 0, 5000, set_tool("invite_wait")))
        gl.addLayout(r3)
        r4 = QHBoxLayout()
        r4.addWidget(label("Pause entre deux invités"))
        r4.addStretch(1)
        r4.addWidget(spin(cfg.get("tools", "invite_pause", default=50), 0, 5000, set_tool("invite_pause")))
        gl.addLayout(r4)
        r5 = QHBoxLayout()
        r5.addWidget(label("Raccourci « inviter tout le monde »"))
        r5.addStretch(1)
        r5.addWidget(HotkeyButton(ctl, "invite"))
        self.invite_btn = QPushButton("Inviter tout le monde")
        self.invite_btn.setObjectName("primary")
        self.invite_btn.clicked.connect(ctl.invite_group)
        r5.addWidget(self.invite_btn)
        gl.addLayout(r5)
        widgets.append(grp)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(scroll_page(*widgets))

        ctl.windows_changed.connect(self.refresh_leader)
        ctl.chat_pos_changed.connect(self.refresh_chat_pos)
        self.refresh_leader()
        self.refresh_chat_pos()
        self._sync_enabled()

    def _clicks_toggled(self, value: bool):
        if value and not self._confirm():
            self.clicks.blockSignals(True)
            self.clicks.setChecked(False)
            self.clicks.setText("OFF")
            self.clicks.blockSignals(False)
            return
        self.ctl.cfg.set("tools", "clicks_enabled", value)
        self.ctl.rebind_hotkeys()

    def _invite_toggled(self, value: bool):
        if value and not self._confirm():
            self.invite.blockSignals(True)
            self.invite.setChecked(False)
            self.invite.setText("OFF")
            self.invite.blockSignals(False)
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


# --- onglets Paramètres / Info ----------------------------------------------------------
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


class SettingsPage(QWidget):
    def __init__(self, ctl: Controller):
        super().__init__()
        cfg = ctl.cfg
        rows = [
            option_row("Réduire dans la zone de notification", "La croix de la fenêtre range l'application près "
                       "de l'horloge au lieu de la fermer.",
                       toggle(cfg.get("settings", "close_to_tray", default=True),
                              lambda v: cfg.set("settings", "close_to_tray", v))),
            option_row("Démarrer réduit", "Au lancement, l'application démarre directement dans la zone de "
                       "notification.", toggle(cfg.get("settings", "start_hidden", default=False),
                                               lambda v: cfg.set("settings", "start_hidden", v))),
            option_row("Lancer avec Windows", "Démarre Kalkid Rétro à l'ouverture de session.",
                       toggle(_autostart_enabled(), _set_autostart)),
        ]
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(scroll_page(*rows))


class InfoPage(QWidget):
    def __init__(self):
        super().__init__()
        frame, lay = card()
        lay.addWidget(label(f"{APP_NAME}  v{__version__}", "title"))
        lay.addWidget(label(
            "Gestionnaire de fenêtres multicompte pour Dofus Rétro : autofocus par notifications, ordre des "
            "personnages, raccourcis, et outils optionnels (clics synchronisés, invitation de groupe).",
            "muted", wrap=True))
        lay.addWidget(label("Projet open source (licence MIT) : github.com/KalDT13/Kalkid-Retro", "muted", wrap=True))
        lay.addWidget(label(
            "Le concept d'autofocus par notifications Windows a été popularisé par Dracoon (Slyss49). "
            "Kalkid Rétro est une implémentation indépendante, sans code repris de Dracoon.", "muted", wrap=True))
        lay.addWidget(label("Cet outil n'est pas affilié à Ankama. Les outils de macro peuvent être "
                            "sanctionnés : voir l'onglet Outils.", "muted", wrap=True))
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(scroll_page(frame))


# --- fenêtre principale ----------------------------------------------------------------
class MainWindow(QMainWindow):
    def __init__(self, ctl: Controller):
        super().__init__()
        self.ctl = ctl
        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(make_icon())
        self.resize(900, 720)
        self.setMinimumSize(780, 560)

        root = QWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)
        lay = QVBoxLayout(root)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        header = QHBoxLayout()
        header.setContentsMargins(24, 14, 24, 4)
        header.setSpacing(8)
        header.addWidget(label("KALKID", "h1"))
        header.addWidget(label("RÉTRO", "h1b"), 0, Qt.AlignmentFlag.AlignBottom)
        header.addStretch(1)
        lay.addLayout(header)

        self.banner = QPushButton()
        self.banner.setObjectName("banner")
        self.banner.setCursor(Qt.CursorShape.PointingHandCursor)
        self.banner.hide()
        lay.addWidget(self.banner)

        tabs = QTabWidget()
        self.tabs = tabs
        tabs.setDocumentMode(True)
        self.prereq_page = PrereqPage(ctl)
        tabs.addTab(CharactersPage(ctl), "Personnages")
        tabs.addTab(AutofocusPage(ctl), "Autofocus")
        self.prereq_index = tabs.addTab(self.prereq_page, "Prérequis")
        self.banner.clicked.connect(lambda: tabs.setCurrentIndex(self.prereq_index))
        tabs.addTab(ShortcutsPage(ctl), "Raccourcis")
        tabs.addTab(ToolsPage(ctl, self._confirm_macros), "Outils")
        tabs.addTab(SettingsPage(ctl), "Paramètres")
        tabs.addTab(InfoPage(), "Info")
        lay.addWidget(tabs, 1)

        self.status = label("", "muted")
        self.status.setContentsMargins(24, 6, 24, 8)
        lay.addWidget(self.status)

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
        self._quitting = False

        # Rien ne tourne en tâche de fond quand la fenêtre est cachée : ces minuteries ne sont
        # actives que lorsqu'elle est affichée (l'autofocus et les raccourcis n'en ont pas besoin).
        self.refresh_timer = QTimer(self, interval=3000, timeout=ctl.refresh_windows)
        self.prereq_timer = QTimer(self, interval=5000, timeout=self.update_prereq)
        self._first_check = True
        QTimer.singleShot(2500, self.update_prereq)   # laisse le temps à l'accès aux notifications de répondre

    def update_prereq(self):
        checks = self.prereq_page.refresh()
        problems = prereq.blocking_problems(checks)
        self.tabs.setTabText(self.prereq_index, "Prérequis ⚠" if problems else "Prérequis")
        if problems:
            self.banner.setText(f"⚠  Configuration incomplète : {problems[0].title}. Clique ici pour voir quoi "
                                f"corriger ({len(problems)} problème{'s' if len(problems) > 1 else ''}).")
            self.banner.show()
            if self._first_check:
                self.tabs.setCurrentIndex(self.prereq_index)
        else:
            self.banner.hide()
        self._first_check = False

    def showEvent(self, event):
        super().showEvent(event)
        self.ctl.refresh_windows()
        self.refresh_timer.start()
        self.prereq_timer.start()

    def hideEvent(self, event):
        super().hideEvent(event)
        self.refresh_timer.stop()
        self.prereq_timer.stop()

    def update_status(self):
        n = len(self.ctl.windows)
        gaps = " · ".join(str(g) for g in self.ctl.last_gaps)
        text = f"●  {n} fenêtre{'s' if n > 1 else ''} détectée{'s' if n > 1 else ''}   ·   Dernier clic : {self.ctl.last_info}"
        if gaps:
            text += f"   ·   Écarts (ms) : {gaps}"
        self.status.setText(text)

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
