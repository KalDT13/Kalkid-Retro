"""Interface PySide6 de Kalkid Rétro (design moderne : cartes arrondies, dégradés, navigation circulaire)."""

from __future__ import annotations

import ctypes
import os
import sys
import winreg
from datetime import datetime

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QAction, QColor, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QComboBox, QFrame, QHBoxLayout, QLabel, QLineEdit,
                               QListWidget, QListWidgetItem, QMainWindow, QMenu, QMessageBox, QPlainTextEdit,
                               QPushButton, QScrollArea, QSpinBox, QStackedWidget, QSystemTrayIcon, QVBoxLayout,
                               QWidget)

from . import APP_NAME, __version__, prereq
from .config import EVENTS
from .controller import Controller
from .theme import ACCENT, ACCENT2, ERR, MUTED, OK, WARN, make_icon, round_logo
from .widgets import Avatar, NavButton, Switch

EVENT_ICONS = {"combat": "⚔", "mp": "💬", "groupe": "👥", "echange": "🔄"}
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"

MACRO_WARNING = (
    "Ces outils envoient des actions sur plusieurs comptes à la fois (clics synchronisés, invitations "
    "automatiques). Ankama tolère les outils de gestion de fenêtres mais interdit les macros : ton compte "
    "pourrait être sanctionné. Ils sont désactivés par défaut. Tu les utilises à tes risques."
)


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
    lay.setContentsMargins(20, 16, 20, 16)
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
    texts.setSpacing(3)
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


def scroll_page(*widgets: QWidget) -> QScrollArea:
    area = QScrollArea()
    area.setWidgetResizable(True)
    area.setFrameShape(QFrame.Shape.NoFrame)
    area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    inner = QWidget()
    inner.setObjectName("pageInner")
    lay = QVBoxLayout(inner)
    lay.setContentsMargins(22, 6, 22, 18)
    lay.setSpacing(12)
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
    box.setFixedWidth(104)
    box.valueChanged.connect(on_change)
    return box


class Hero(QFrame):
    """Grande carte à dégradé orange en tête de page (comme les cartes d'événement du modèle)."""

    def __init__(self, tag: str, title: str, sub: str, stat: str = "", stat_label: str = "",
                 button: QPushButton | None = None):
        super().__init__()
        self.setObjectName("hero")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(22, 18, 22, 18)
        left = QVBoxLayout()
        left.setSpacing(5)
        self.tag = label(tag, "tag")
        self.title = label(title, "heroTitle")
        self.sub = label(sub, "heroSub", wrap=True)
        left.addWidget(self.tag, 0, Qt.AlignmentFlag.AlignLeft)
        left.addWidget(self.title)
        left.addWidget(self.sub)
        if button is not None:
            button.setObjectName("heroBtn")
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            left.addSpacing(6)
            left.addWidget(button, 0, Qt.AlignmentFlag.AlignLeft)
        lay.addLayout(left, 1)
        right = QVBoxLayout()
        right.setSpacing(0)
        self.stat = label(stat, "heroStat")
        self.stat.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.stat_label = label(stat_label, "heroSub")
        self.stat_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        right.addStretch(1)
        right.addWidget(self.stat)
        right.addWidget(self.stat_label)
        lay.addLayout(right)

    def set_all(self, tag=None, title=None, sub=None, stat=None, stat_label=None):
        for widget, value in ((self.tag, tag), (self.title, title), (self.sub, sub),
                              (self.stat, stat), (self.stat_label, stat_label)):
            if value is not None:
                widget.setText(value)


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


# --- page Personnages -----------------------------------------------------------------
class CharacterRow(QFrame):
    def __init__(self, ctl: Controller, pseudo: str):
        super().__init__()
        self.setObjectName("row")
        self.setFixedHeight(68)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 0, 14, 0)
        lay.setSpacing(8)
        online = pseudo in ctl.windows
        is_main = ctl.cfg.get("main", default="") == pseudo

        lay.addWidget(Avatar(pseudo, online))
        texts = QVBoxLayout()
        texts.setSpacing(1)
        name = label(pseudo, "cardTitle")
        name.setStyleSheet(f"color: {'white' if online else MUTED}; font-weight: 700;")
        status = "En ligne" if online else "Hors ligne"
        if is_main:
            status += "  ·  ★ Principal"
        sub = label(status, "muted")
        texts.addStretch(1)
        texts.addWidget(name)
        texts.addWidget(sub)
        texts.addStretch(1)
        lay.addLayout(texts, 1)

        enabled = ctl.events_for(pseudo)
        for key, icon in EVENT_ICONS.items():
            b = QPushButton(icon)
            b.setObjectName("chip")
            b.setCheckable(True)
            b.setFixedSize(36, 36)
            b.setToolTip(f"Autofocus : {EVENTS[key]}")
            b.setChecked(key in enabled)
            b.toggled.connect(lambda state, k=key, p=pseudo: ctl.set_event(p, k, state))
            lay.addWidget(b)

        main = QPushButton("★")
        main.setObjectName("chip")
        main.setCheckable(True)
        main.setFixedSize(36, 36)
        main.setToolTip("Personnage principal")
        main.setChecked(is_main)
        main.clicked.connect(lambda checked, p=pseudo: self._set_main(ctl, p, checked))
        lay.addWidget(main)

        excl = QPushButton("Exclure")
        excl.setObjectName("pill")
        excl.setCheckable(True)
        excl.setFixedHeight(36)
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
        outer = QVBoxLayout(self)
        outer.setContentsMargins(22, 6, 22, 0)
        outer.setSpacing(12)

        self.hero = Hero("● Multicompte", "Tes personnages", "Glisse une ligne pour changer l'ordre de passage.",
                         "0", "connectés")
        outer.addWidget(self.hero)

        # autofocus global par type d'événement
        allbox, al = card()
        row = QHBoxLayout()
        row.addWidget(label("Autofocus pour tous", "cardTitle"))
        row.addStretch(1)
        for key, icon in EVENT_ICONS.items():
            b = QPushButton(icon)
            b.setObjectName("chip")
            b.setFixedSize(36, 36)
            b.setToolTip(f"Activer / désactiver « {EVENTS[key]} » pour tous")
            b.clicked.connect(lambda _=False, k=key: self._toggle_column(k))
            row.addWidget(b)
        al.addLayout(row)
        outer.addWidget(allbox)

        self.list = QListWidget()
        self.list.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.list.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.list.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.list.model().rowsMoved.connect(lambda *a: QTimer.singleShot(0, self._order_changed))
        outer.addWidget(self.list, 1)

        self.empty = label("Aucune fenêtre Dofus Rétro détectée.\nLance le jeu, elles apparaîtront ici.", "muted")
        self.empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        outer.addWidget(self.empty)

        presets, pl = card()
        top = QHBoxLayout()
        top.addWidget(label("Presets", "cardTitle"))
        top.addStretch(1)
        self.preset_combo = QComboBox()
        self.preset_combo.setMinimumWidth(190)
        self.preset_combo.activated.connect(self._load_preset)
        delete = QPushButton("Supprimer")
        delete.clicked.connect(self._delete_preset)
        top.addWidget(self.preset_combo)
        top.addWidget(delete)
        pl.addLayout(top)
        bottom = QHBoxLayout()
        self.preset_name = QLineEdit()
        self.preset_name.setPlaceholderText("Nom du nouveau preset")
        save = QPushButton("Enregistrer")
        save.setObjectName("primary")
        save.clicked.connect(self._save_preset)
        bottom.addWidget(self.preset_name, 1)
        bottom.addWidget(save)
        pl.addLayout(bottom)
        outer.addWidget(presets)

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
            item.setSizeHint(QSize(100, 76))
            self.list.addItem(item)
            self.list.setItemWidget(item, CharacterRow(self.ctl, pseudo))
        self.list.blockSignals(False)
        self.empty.setVisible(not order)
        online = len(self.ctl.windows)
        self.hero.set_all(stat=str(online), stat_label="connecté" + ("s" if online > 1 else ""))

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
        self.toggle_btn = QPushButton("Désactiver" if enabled else "Activer")
        self.toggle_btn.clicked.connect(self._toggle)
        self.hero = Hero("● Actif" if enabled else "○ Inactif", "Autofocus",
                         "Bascule sur le bon personnage dès que le jeu t'envoie une notification.",
                         "0", "notifications lues", self.toggle_btn)

        stats_frame, stats = card()
        self.status = label("Accès aux notifications : en attente…", "cardTitle")
        self.counters = label("", "muted")
        stats.addWidget(self.status)
        stats.addWidget(self.counters)
        stats.addWidget(label(
            "Mise en place : 1) en jeu, Options > Général > « Notification en arrière-plan » ; "
            "2) Windows, Paramètres > Système > Notifications : activées ; 3) coupe le son des notifications "
            "de Dofus si besoin.", "muted", wrap=True))

        debug = option_row("Mode debug", "Affiche dans le journal chaque notification Dofus lue.",
                           make_switch(ctl.cfg.get("autofocus", "debug", default=False),
                                       lambda v: ctl.cfg.set("autofocus", "debug", v)))

        head = QHBoxLayout()
        head.addWidget(label("Journal", "section"))
        head.addStretch(1)
        clear = QPushButton("Effacer")
        head.addWidget(clear)
        head_w = QWidget()
        head_w.setLayout(head)
        head.setContentsMargins(0, 0, 0, 0)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(500)
        self.log.setMinimumHeight(170)
        clear.clicked.connect(self.log.clear)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(scroll_page(self.hero, stats_frame, debug, head_w, self.log))

        ctl.log.connect(self.add_log)
        ctl.info_changed.connect(self.update_counters)
        QTimer(self, interval=1000, timeout=lambda: self.isVisible() and self.update_counters()).start()

    def _toggle(self):
        enabled = not self.ctl.cfg.get("autofocus", "enabled", default=True)
        self.ctl.set_autofocus_enabled(enabled)
        self.toggle_btn.setText("Désactiver" if enabled else "Activer")
        self.hero.set_all(tag="● Actif" if enabled else "○ Inactif")

    def update_counters(self):
        ok = self.ctl.notifs.access_ok
        self.status.setText("Accès aux notifications : " + ("accordé ✓" if ok else "non accordé ✗"))
        self.status.setStyleSheet(f"color: {OK if ok else ERR};")
        self.counters.setText(f"Changements de fenêtre : {self.ctl.focus_count}")
        self.hero.set_all(stat=str(self.ctl.notifs.read_count))

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
        recheck = QPushButton("Revérifier")
        recheck.clicked.connect(self.refresh)
        self.hero = Hero("● Diagnostic", "Vérification…", "Kalkid Rétro contrôle que ton PC est prêt.",
                         "", "", recheck)
        self._holder = QVBoxLayout()
        self._holder.setSpacing(10)
        holder_w = QWidget()
        holder_w.setLayout(self._holder)
        self._holder.setContentsMargins(0, 0, 0, 0)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(scroll_page(self.hero, holder_w))
        self.refresh()

    def refresh(self) -> list[prereq.Check]:
        self.checks = prereq.check_all(self.ctl)
        while self._holder.count():
            item = self._holder.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        errors = sum(c.state == prereq.ERROR for c in self.checks)
        warns = sum(c.state == prereq.WARN for c in self.checks)
        oks = sum(c.state == prereq.OK for c in self.checks)
        if errors:
            self.hero.set_all(tag="● À corriger", title=f"{errors} point{'s' if errors > 1 else ''} bloquant"
                              f"{'s' if errors > 1 else ''}", sub="Corrige les lignes rouges pour que tout marche.",
                              stat=f"{oks}/{len(self.checks)}", stat_label="validés")
        elif warns:
            self.hero.set_all(tag="● Presque prêt", title="Quelques points à vérifier",
                              sub="Rien de bloquant, mais lis les lignes orange.",
                              stat=f"{oks}/{len(self.checks)}", stat_label="validés")
        else:
            self.hero.set_all(tag="● Prêt", title="Tout est en ordre ✓", sub="Ton PC est prêt pour Kalkid Rétro.",
                              stat=f"{oks}/{len(self.checks)}", stat_label="validés")
        for check in self.checks:
            frame, lay = card()
            row = QHBoxLayout()
            row.setSpacing(12)
            dot = label("●")
            dot.setStyleSheet(f"color: {STATE_COLORS[check.state]}; font-size: 15pt;")
            dot.setFixedWidth(22)
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
            self._holder.addWidget(frame)
        return self.checks


# --- page Raccourcis -------------------------------------------------------------------
class ShortcutsPage(QWidget):
    def __init__(self, ctl: Controller):
        super().__init__()
        hero = Hero("● Clavier", "Raccourcis", "Clique sur un raccourci puis appuie sur la touche voulue.",
                    "3", "actions")
        rows = [
            hero,
            option_row("Fenêtre suivante", "Passe au personnage suivant dans l'ordre.", HotkeyButton(ctl, "next")),
            option_row("Fenêtre précédente", "Revient au personnage précédent.", HotkeyButton(ctl, "prev")),
            option_row("Personnage principal", "Passe sur le personnage marqué ★.", HotkeyButton(ctl, "main")),
            option_row("Seulement en jeu", "Les raccourcis ne fonctionnent que si une fenêtre Dofus Rétro est "
                                           "au premier plan (recommandé).",
                       make_switch(ctl.cfg.get("hotkeys_only_in_game", default=True),
                                   lambda v: (ctl.cfg.set("hotkeys_only_in_game", v), ctl.rebind_hotkeys()))),
        ]
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(scroll_page(*rows))


# --- page Outils -----------------------------------------------------------------------
class ToolsPage(QWidget):
    def __init__(self, ctl: Controller, confirm_macros):
        super().__init__()
        self.ctl = ctl
        cfg = ctl.cfg
        self._confirm = confirm_macros

        def set_tool(key):
            return lambda value: (cfg.set("tools", key, value), ctl.rebind_hotkeys())

        self.hero = Hero("● Outils", "Outils multicompte", "Dernier clic : aucun clic pour l'instant",
                         "", "")
        widgets: list[QWidget] = [self.hero]
        widgets.append(option_row("Anti-clignotement", "Éteint le clignotement des fenêtres du jeu dans la "
                                  "barre des tâches.", make_switch(cfg.get("tools", "no_flash", default=True),
                                                                   set_tool("no_flash"))))

        warn, wl = card("warn")
        wl.addWidget(label("⚠  Outils de macro", "cardTitle"))
        wl.addWidget(label(MACRO_WARNING, "muted", wrap=True))
        widgets.append(warn)

        # Clics synchronisés
        self.clicks = make_switch(cfg.get("tools", "clicks_enabled", default=False), self._clicks_toggled)
        widgets.append(option_row("Clics synchronisés", "Clic molette : clic gauche au même endroit sur tous "
                                  "les comptes, avec un délai aléatoire.", self.clicks))
        tune, tl = card()
        tl.addLayout(field_row("Délai aléatoire entre fenêtres",
                               spin(cfg.get("tools", "delay_min", default=90), 0, 5000, set_tool("delay_min")),
                               label("à"),
                               spin(cfg.get("tools", "delay_max", default=130), 0, 5000, set_tool("delay_max"))))
        tl.addLayout(field_row("Clic molette actif",
                               make_switch(cfg.get("tools", "wheel", default=True), set_tool("wheel"))))
        tl.addLayout(field_row("Raccourci « clic sans délai »", HotkeyButton(ctl, "click_all")))
        widgets.append(tune)

        # Invitation de groupe
        self.invite = make_switch(cfg.get("tools", "invite_enabled", default=False), self._invite_toggled)
        widgets.append(option_row("Invitation de groupe", "Le chef invite tous les personnages connectés, "
                                  "chacun valide puis invite le suivant.", self.invite))
        grp, gl = card()
        self.leader = QComboBox()
        self.leader.setMinimumWidth(180)
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
        gl.addLayout(field_row("Raccourci « inviter tout le monde »", HotkeyButton(ctl, "invite"), self.invite_btn))
        widgets.append(grp)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(scroll_page(*widgets))

        ctl.windows_changed.connect(self.refresh_leader)
        ctl.chat_pos_changed.connect(self.refresh_chat_pos)
        ctl.info_changed.connect(self.refresh_hero)
        self.refresh_leader()
        self.refresh_chat_pos()
        self._sync_enabled()

    def refresh_hero(self):
        gaps = " · ".join(str(g) for g in self.ctl.last_gaps)
        sub = f"Dernier clic : {self.ctl.last_info}"
        if gaps:
            sub += f"   ·   écarts (ms) : {gaps}"
        self.hero.set_all(sub=sub)

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


class SettingsPage(QWidget):
    def __init__(self, ctl: Controller):
        super().__init__()
        cfg = ctl.cfg
        hero = Hero("● Application", "Réglages", f"{APP_NAME}  v{__version__}", "", "")
        info, il = card()
        il.addWidget(label("À propos", "cardTitle"))
        il.addWidget(label(
            "Gestionnaire de fenêtres multicompte pour Dofus Rétro : autofocus par notifications, ordre des "
            "personnages, raccourcis, et outils optionnels (clics synchronisés, invitation de groupe).",
            "muted", wrap=True))
        il.addWidget(label("Projet open source (licence MIT) : github.com/KalDT13/Kalkid-Retro", "muted", wrap=True))
        il.addWidget(label(
            "Le principe de l'autofocus par notifications Windows a été popularisé par Dracoon (Slyss49). "
            "Kalkid Rétro est une implémentation indépendante, sans code repris de Dracoon. Cet outil n'est "
            "pas affilié à Ankama.", "muted", wrap=True))
        rows = [
            hero,
            option_row("Réduire dans la zone de notification", "La croix de la fenêtre range l'application près "
                       "de l'horloge au lieu de la fermer.",
                       make_switch(cfg.get("settings", "close_to_tray", default=True),
                                   lambda v: cfg.set("settings", "close_to_tray", v))),
            option_row("Démarrer réduit", "Au lancement, l'application démarre directement dans la zone de "
                       "notification.", make_switch(cfg.get("settings", "start_hidden", default=False),
                                                    lambda v: cfg.set("settings", "start_hidden", v))),
            option_row("Lancer avec Windows", "Démarre Kalkid Rétro à l'ouverture de session.",
                       make_switch(_autostart_enabled(), _set_autostart)),
            info,
        ]
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(scroll_page(*rows))


# --- fenêtre principale -----------------------------------------------------------------
class MainWindow(QMainWindow):
    def __init__(self, ctl: Controller):
        super().__init__()
        self.ctl = ctl
        self._quitting = False
        self._first_check = True
        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(make_icon())
        self.resize(660, 900)
        self.setMinimumSize(560, 640)

        root = QWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)
        lay = QVBoxLayout(root)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        # en-tête : logo + titre + état
        header = QHBoxLayout()
        header.setContentsMargins(24, 18, 24, 12)
        header.setSpacing(12)
        logo = QLabel()
        logo.setPixmap(round_logo(52))
        logo.setFixedSize(52, 52)
        header.addWidget(logo)
        titles = QVBoxLayout()
        titles.setSpacing(0)
        titles.addWidget(label("Kalkid Rétro", "appTitle"))
        self.subtitle = label("", "muted")
        titles.addWidget(self.subtitle)
        header.addLayout(titles, 1)
        self.chip = label("", "tag")
        header.addWidget(self.chip, 0, Qt.AlignmentFlag.AlignVCenter)
        lay.addLayout(header)

        # bandeau d'alerte (prérequis bloquants)
        self.banner_frame = QFrame()
        self.banner_frame.setObjectName("banner")
        bl = QHBoxLayout(self.banner_frame)
        bl.setContentsMargins(0, 0, 0, 0)
        self.banner = QPushButton()
        self.banner.setObjectName("banner")
        self.banner.setCursor(Qt.CursorShape.PointingHandCursor)
        bl.addWidget(self.banner)
        wrap = QHBoxLayout()
        wrap.setContentsMargins(22, 0, 22, 8)
        wrap.addWidget(self.banner_frame)
        lay.addLayout(wrap)
        self.banner_frame.hide()

        # pages
        self.stack = QStackedWidget()
        self.prereq_page = PrereqPage(ctl)
        pages = [
            ("people", "Persos", CharactersPage(ctl)),
            ("bell", "Autofocus", AutofocusPage(ctl)),
            ("shield", "Prérequis", self.prereq_page),
            ("keyboard", "Touches", ShortcutsPage(ctl)),
            ("sliders", "Outils", ToolsPage(ctl, self._confirm_macros)),
            ("gear", "Réglages", SettingsPage(ctl)),
        ]
        self.nav_buttons: list[NavButton] = []
        navbar = QFrame()
        navbar.setObjectName("navbar")
        nl = QHBoxLayout(navbar)
        nl.setContentsMargins(14, 8, 14, 8)
        nl.setSpacing(0)
        for index, (icon, text, page) in enumerate(pages):
            self.stack.addWidget(page)
            btn = NavButton(icon, text)
            btn.clicked.connect(lambda _=False, i=index: self.stack.setCurrentIndex(i))
            nl.addWidget(btn, 1)
            self.nav_buttons.append(btn)
        self.prereq_index = 2
        self.nav_buttons[0].setChecked(True)
        self.banner.clicked.connect(lambda: self._goto(self.prereq_index))
        lay.addWidget(self.stack, 1)
        navwrap = QHBoxLayout()
        navwrap.setContentsMargins(22, 6, 22, 18)
        navwrap.addWidget(navbar)
        lay.addLayout(navwrap)

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

    def _goto(self, index: int):
        self.stack.setCurrentIndex(index)
        self.nav_buttons[index].setChecked(True)

    def update_status(self):
        n = len(self.ctl.windows)
        self.subtitle.setText(f"{n} fenêtre{'s' if n > 1 else ''} connectée{'s' if n > 1 else ''}")
        af = self.ctl.cfg.get("autofocus", "enabled", default=True)
        self.chip.setText("● Autofocus actif" if af else "○ Autofocus off")

    def update_prereq(self):
        checks = self.prereq_page.refresh()
        problems = prereq.blocking_problems(checks)
        self.nav_buttons[self.prereq_index].set_badge(bool(problems))
        if problems:
            self.banner.setText(f"⚠  Configuration incomplète : {problems[0].title}. Touche ici pour voir quoi "
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
