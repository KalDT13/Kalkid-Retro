"""Logique centrale : ordre des fenêtres, autofocus, clics synchronisés, invitations."""

from __future__ import annotations

import os
import random
import threading
import time

from PySide6.QtCore import QObject, Signal

from . import winutil
from .config import EVENTS, Config
from .hotkeys import HookManager
from .notifs import GameNotification, NotificationWatcher
from .updater import Updater


def _wait_foreground(hwnd: int, timeout: float = 0.35) -> bool:
    """Attend (brièvement) que `hwnd` soit au premier plan : l'activation des fenêtres du jeu n'est pas instantanée."""
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if winutil.foreground_hwnd() == hwnd:
            return True
        time.sleep(0.02)
    return winutil.foreground_hwnd() == hwnd


class Controller(QObject):
    log = Signal(str, str)            # niveau ("info" | "ok" | "error" | "notif"), message
    windows_changed = Signal()
    info_changed = Signal()           # texte d'état (dernier clic, compteurs…)
    chat_pos_changed = Signal()
    chat_capture_state = Signal(bool)     # True pendant l'attente du clic sur le chat
    capture_finished = Signal(bool, str)  # succès, message
    taskbar_done = Signal(bool, str)      # rangement de la barre des tâches : succès, message
    invite_state = Signal(bool)           # True pendant une invitation de groupe
    invite_finished = Signal(bool, str)   # succès, message
    tools_changed = Signal()              # un réglage d'outil a changé hors de la page Outils
    leader_changed = Signal()             # le chef de groupe a changé
    hotkey_captured = Signal(str, str)  # nom de l'action, raccourci capturé

    def __init__(self, config: Config):
        super().__init__()
        self.cfg = config
        self.windows: dict[str, winutil.GameWindow] = {}   # pseudo -> fenêtre ouverte
        self.last_info = "aucun clic pour l'instant"
        self.last_gaps: list[int] = []
        self._busy_click = False
        self._busy_invite = False
        self._capturing_chat = False
        self._busy_taskbar = False
        self._stop = threading.Event()

        # Mis à jour par un thread : les hooks ne doivent jamais interroger Windows (trop lent)
        self.game_fg = False
        self._fg_was_game = False
        self._last_game_hwnd = 0
        self._guard_times: list[float] = []
        self.last_focus_detail = ""

        self.hooks = HookManager()
        self.hooks.set_condition(lambda: self.game_fg)
        self.hooks.set_foreground_callback(self._on_foreground)
        self.hooks.on_suspended = lambda message: self.log.emit("error", message)
        self.hooks.set_middle_click(lambda: self.click_all(True), self._wheel_enabled)
        self.notifs = NotificationWatcher(self._on_notification, self.log.emit,
                                          lambda: bool(winutil.list_windows()))
        self.notif_count = 0
        self.focus_count = 0
        self.updater = Updater()

    # --- cycle de vie -----------------------------------------------------------
    def _clear_legacy_pins(self) -> None:
        """La 0.10.0 proposait d'épingler des fenêtres « toujours au premier plan » : fonction retirée. Si des
        fenêtres avaient été épinglées, on les remet à l'état normal une fois, puis on oublie la liste."""
        legacy = self.cfg.get("pinned", default=[])
        if not legacy:
            return
        for win in winutil.list_windows():
            if win.pseudo in legacy:
                winutil.release_topmost(win.hwnd)
        self.cfg.set("pinned", [])

    def start(self) -> None:
        self._clear_legacy_pins()
        self.refresh_windows()
        self.rebind_hotkeys()
        self.hooks.start()
        if self.cfg.get("autofocus", "enabled", default=True):
            self.notifs.start()
        if self.cfg.get("settings", "check_updates", default=True):
            threading.Timer(4.0, self.updater.check).start()   # une seule vérification, en arrière-plan
        threading.Thread(target=self._anti_flash_loop, daemon=True, name="kalkid-flash").start()

    GUARD_IDLE_MS = 700        # sans action de l'utilisateur depuis au moins 0,7 s : le focus a été « volé »
    GUARD_DELAY = 0.15         # laisse l'autre fenêtre finir de s'afficher avant de reprendre le focus
    GUARD_MAX = 3              # au plus 3 reprises de focus par fenêtre de 10 s (évite une bagarre de focus)

    def _on_foreground(self, hwnd: int) -> None:
        """Appelé par Windows à chaque changement de fenêtre active (aucun polling)."""
        is_game = bool(hwnd) and winutil.pseudo_from_title(winutil.window_title(hwnd)) is not None
        left_game = self._fg_was_game and not is_game
        game_hwnd = self._last_game_hwnd
        self.game_fg = is_game
        self._fg_was_game = is_game
        if is_game:
            self._last_game_hwnd = hwnd
        elif left_game and self.cfg.get("autofocus", "keep_focus", default=False):
            self._maybe_keep_focus(game_hwnd, hwnd)

    def _maybe_keep_focus(self, game_hwnd: int, new_hwnd: int) -> None:
        """Rend le focus au jeu si une autre application l'a pris SANS action de l'utilisateur.

        Si l'utilisateur vient de taper ou de cliquer (Alt+Tab, clic sur Discord…), on ne touche à rien.
        """
        if not game_hwnd or not winutil.is_valid(game_hwnd) or winutil.idle_ms() < self.GUARD_IDLE_MS:
            return
        if winutil.pid_of(new_hwnd) == os.getpid():            # notre propre fenêtre
            return
        now = time.monotonic()
        self._guard_times = [t for t in self._guard_times if now - t < 10]
        if len(self._guard_times) >= self.GUARD_MAX:
            return
        self._guard_times.append(now)

        def restore():
            if winutil.idle_ms() < self.GUARD_IDLE_MS or winutil.is_game_foreground():
                return          # l'utilisateur a repris la main entre-temps
            ok, detail = winutil.focus_ex(game_hwnd)
            pseudo = winutil.pseudo_from_title(winutil.window_title(game_hwnd)) or "le jeu"
            self.log.emit("ok" if ok else "error",
                          f"Focus rendu à {pseudo} (une autre fenêtre l'avait pris sans action de ta part) · {detail}")

        threading.Timer(self.GUARD_DELAY, restore).start()

    def shutdown(self) -> None:
        self._stop.set()
        self.hooks.stop()
        self.notifs.stop()

    # --- fenêtres et ordre -------------------------------------------------------
    def refresh_windows(self) -> None:
        found = {w.pseudo: w for w in winutil.list_windows()}
        changed = {k: v.hwnd for k, v in found.items()} != {k: v.hwnd for k, v in self.windows.items()}
        self.windows = found
        order = list(self.cfg.get("order", default=[]))
        added = False
        for pseudo in found:
            if pseudo not in order:
                order.append(pseudo)
                added = True
        if added:
            self.cfg.set("order", order)
        if changed or added:
            self.windows_changed.emit()

    def order(self) -> list[str]:
        return list(self.cfg.get("order", default=[]))

    def set_order(self, order: list[str]) -> None:
        self.cfg.set("order", order)
        self.windows_changed.emit()

    def is_excluded(self, pseudo: str) -> bool:
        return pseudo in self.cfg.get("excluded", default=[])

    def set_excluded(self, pseudo: str, value: bool) -> None:
        ex = [p for p in self.cfg.get("excluded", default=[]) if p != pseudo]
        if value:
            ex.append(pseudo)
        self.cfg.set("excluded", ex)

    def active_windows(self) -> list[winutil.GameWindow]:
        """Fenêtres ouvertes, dans l'ordre, hors exclusions."""
        return [self.windows[p] for p in self.order() if p in self.windows and not self.is_excluded(p)]

    def cycle(self, step: int) -> None:
        self.refresh_windows()
        wins = self.active_windows()
        if not wins:
            return
        current = winutil.foreground_pseudo()
        pseudos = [w.pseudo for w in wins]
        idx = pseudos.index(current) if current in pseudos else (-1 if step > 0 else 0)
        target = wins[(idx + step) % len(wins)]
        ok, detail = winutil.focus_ex(target.hwnd)
        if not ok or "non confirmé" in detail:
            self.log.emit("error", f"Passage sur {target.pseudo} : {detail}")

    def focus_pseudo(self, pseudo: str) -> bool:
        # Chemin rapide : fenêtre déjà connue et toujours valide (aucune énumération des fenêtres).
        win = self.windows.get(pseudo)
        if not (win and winutil.is_valid(win.hwnd)):
            self.refresh_windows()
            win = self.windows.get(pseudo)
        if not win:
            self.last_focus_detail = "fenêtre introuvable"
            return False
        ok, self.last_focus_detail = winutil.focus_ex(win.hwnd)
        return ok

    def focus_main(self) -> None:
        main = self.cfg.get("main", default="")
        if main:
            self.focus_pseudo(main)

    # --- barre des tâches -------------------------------------------------------
    def apply_taskbar_order(self) -> None:
        """Range les fenêtres de la barre des tâches dans l'ordre de la liste (ordre d'initiative)."""
        if self._busy_taskbar:
            return
        threading.Thread(target=self._taskbar, args=(True,), daemon=True, name="kalkid-taskbar").start()

    def restore_taskbar(self) -> None:
        if self._busy_taskbar:
            return
        threading.Thread(target=self._taskbar, args=(False,), daemon=True, name="kalkid-taskbar").start()

    def _taskbar(self, apply: bool) -> None:
        self._busy_taskbar = True
        try:
            self.refresh_windows()
            hwnds = [w.hwnd for w in self.active_windows()]
            if not hwnds:
                self.log.emit("error", "Aucune fenêtre Dofus Rétro ouverte.")
                self.taskbar_done.emit(False, "Aucune fenêtre Dofus Rétro ouverte.")
                return
            if apply:
                count = winutil.reorder_taskbar(hwnds)
                message = f"{count} fenêtre{'s' if count > 1 else ''} rangée{'s' if count > 1 else ''} dans l'ordre de la liste."
            else:
                count = winutil.restore_taskbar_grouping(hwnds)
                message = "Regroupement d'origine rétabli."
            self.log.emit("ok", message)
            self.taskbar_done.emit(count > 0, message if count > 0 else "Windows a refusé la modification.")
        finally:
            self._busy_taskbar = False

    # --- portraits --------------------------------------------------------------
    def portrait_key(self, pseudo: str) -> str | None:
        return self.cfg.get("portraits", default={}).get(pseudo)

    def set_portrait(self, pseudo: str, key: str | None) -> None:
        mapping = dict(self.cfg.get("portraits", default={}))
        if key:
            mapping[pseudo] = key
        else:
            mapping.pop(pseudo, None)
        self.cfg.set("portraits", mapping)
        self.windows_changed.emit()

    # --- autofocus --------------------------------------------------------------
    def events_for(self, pseudo: str) -> list[str]:
        events = self.cfg.get("autofocus", "events", default={})
        return list(events.get(pseudo, list(EVENTS)))   # tout activé par défaut

    def set_event(self, pseudo: str, event: str, value: bool) -> None:
        events = dict(self.cfg.get("autofocus", "events", default={}))
        current = [e for e in events.get(pseudo, list(EVENTS)) if e != event]
        if value:
            current.append(event)
        events[pseudo] = current
        self.cfg.set("autofocus", "events", events)

    def set_autofocus_enabled(self, enabled: bool) -> None:
        self.cfg.set("autofocus", "enabled", enabled)
        if enabled:
            self.notifs.start()
        else:
            self.notifs.stop()

    def _on_notification(self, notif: GameNotification) -> None:
        self.notif_count += 1
        if self.cfg.get("autofocus", "debug", default=False):
            self.log.emit("notif", f"[{notif.event or '?'}] {notif.pseudo} : {notif.body}")
        if not self.cfg.get("autofocus", "enabled", default=True) or not notif.event:
            return
        if self.is_excluded(notif.pseudo) or notif.event not in self.events_for(notif.pseudo):
            return
        if self.focus_pseudo(notif.pseudo):
            self.focus_count += 1
            self.log.emit("ok" if "non confirmé" not in self.last_focus_detail else "error",
                          f"Focus sur {notif.pseudo} ({EVENTS.get(notif.event, notif.event)}) · {self.last_focus_detail}")
        else:
            self.log.emit("error", f"Fenêtre « {notif.pseudo} » introuvable.")
        self.info_changed.emit()

    # --- raccourcis -------------------------------------------------------------
    def _wheel_enabled(self) -> bool:
        return bool(self.cfg.get("tools", "clicks_enabled", default=False)
                    and self.cfg.get("tools", "wheel", default=True))

    def rebind_hotkeys(self) -> None:
        hk = self.cfg.get("hotkeys", default={})
        in_game = bool(self.cfg.get("hotkeys_only_in_game", default=True))
        tools = self.cfg.get("tools", default={})
        bindings = {
            hk.get("next", ""): (lambda: self.cycle(1), in_game),
            hk.get("prev", ""): (lambda: self.cycle(-1), in_game),
            hk.get("main", ""): (self.focus_main, in_game),
        }
        if tools.get("clicks_enabled"):
            bindings[hk.get("click_all", "")] = (lambda: self.click_all(False), True)
        if tools.get("invite_enabled"):
            bindings[hk.get("invite", "")] = (self.invite_group, True)
        # Un raccourci en Alt (ex. Alt+Échap) : on intercale une touche neutre pour que le jeu ne voie pas un
        # simple appui sur Alt (qui activerait son menu et lui volerait le focus clavier).
        wrapped = {}
        for text, (callback, only_game) in bindings.items():
            if text and "alt" in text.lower():
                callback = self._alt_safe(callback)
            wrapped[text] = (callback, only_game)
        self.hooks.set_bindings({k: v for k, v in wrapped.items() if k})
        self.hooks.refresh_mouse_hook()   # le hook souris n'existe que si le clic molette est activé

    @staticmethod
    def _alt_safe(callback):
        def run():
            winutil.suppress_menu_activation()
            callback()
        return run

    def capture_hotkey(self, action: str) -> None:
        """Attend la prochaine combinaison pressée et l'enregistre pour `action`."""
        def done(text: str):
            if text.lower() != "esc":
                self.cfg.set("hotkeys", action, text)
                self.rebind_hotkeys()
            self.hotkey_captured.emit(action, self.cfg.get("hotkeys", action, default=""))
        self.hooks.capture_next(done)

    def cancel_capture(self) -> None:
        self.hooks.cancel_capture()

    # --- clics synchronisés -----------------------------------------------------
    def click_all(self, random_delay: bool) -> None:
        if self._busy_click:
            return
        threading.Thread(target=self._click_all, args=(random_delay,), daemon=True).start()

    def _click_all(self, random_delay: bool) -> None:
        self._busy_click = True
        try:
            origin = winutil.foreground_hwnd()
            if not origin:
                return
            x, y = winutil.cursor_client_pos(origin)
            # Pas d'énumération des fenêtres à chaque clic : on utilise la liste en mémoire (rafraîchie
            # régulièrement) et on ne ré-énumère que si une fenêtre a disparu ou si la liste est vide.
            wins = [w for w in self.active_windows() if winutil.is_valid(w.hwnd)]
            if not wins or len(wins) < len(self.active_windows()):
                self.refresh_windows()
                wins = self.active_windows()
            lo = min(self.cfg.get("tools", "delay_min", default=90), self.cfg.get("tools", "delay_max", default=130))
            hi = max(self.cfg.get("tools", "delay_min", default=90), self.cfg.get("tools", "delay_max", default=130))
            # Dofus active sa fenêtre dès qu'elle reçoit un clic : chaque clic fait passer la fenêtre visée au
            # premier plan. On clique donc la fenêtre d'origine EN DERNIER, pour que le focus te revienne.
            wins = [w for w in wins if w.hwnd != origin] + [w for w in wins if w.hwnd == origin]
            t0 = time.monotonic()
            last, gaps = None, []
            for i, win in enumerate(wins):
                winutil.post_click(win.hwnd, x, y)
                now = time.monotonic()
                if last is not None:
                    gaps.append(round((now - last) * 1000))
                last = now
                if random_delay and i < len(wins) - 1:
                    time.sleep(random.randint(lo, hi) / 1000)
            # Sans fenêtre d'origine dans la liste (exclue, par ex.), ou si une autre a gardé le premier plan :
            # on te rend la main. Sinon l'autofocus ne te prévient plus (le jeu ne notifie pas la fenêtre active).
            if winutil.is_valid(origin) and not _wait_foreground(origin):
                winutil.focus_ex(origin)
            self.last_gaps = gaps
            self.last_info = f"{len(wins)} fenêtres en {time.monotonic() - t0:.2f} s"
            self.info_changed.emit()
        finally:
            self._busy_click = False

    def _anti_flash_loop(self) -> None:
        while not self._stop.wait(1.0):
            if self.cfg.get("tools", "no_flash", default=True):
                for win in list(self.windows.values()):
                    winutil.stop_flash(win.hwnd)

    # --- invitation de groupe ---------------------------------------------------
    def start_chat_capture(self) -> None:
        """Passe sur une fenêtre Dofus ; le prochain clic gauche mémorise la position du chat."""
        if self._capturing_chat:
            return
        self.refresh_windows()
        leader = self.windows.get(self.cfg.get("tools", "leader", default="")) or self.windows.get(
            self.cfg.get("main", default=""))
        target = leader or next(iter(self.active_windows()), None) or next(iter(self.windows.values()), None)
        if target is None:
            self.log.emit("error", "Aucune fenêtre Dofus Rétro ouverte : lance le jeu d'abord.")
            self.capture_finished.emit(False, "Aucune fenêtre Dofus Rétro ouverte.")
            return
        winutil.focus(target.hwnd)
        self._capturing_chat = True
        self.chat_capture_state.emit(True)
        self.hooks.capture_click(self._on_chat_click, lambda: self._end_chat_capture(False, "Annulé."))
        # sécurité : on abandonne si l'utilisateur ne clique pas
        self._capture_timer = threading.Timer(45.0, lambda: self._end_chat_capture(False, "Délai dépassé."))
        self._capture_timer.start()

    def _on_chat_click(self) -> None:
        hwnd = winutil.foreground_hwnd()
        if not hwnd or not winutil.foreground_pseudo():
            self._end_chat_capture(False, "Le clic n'était pas dans une fenêtre Dofus Rétro.")
            return
        x, y = winutil.cursor_client_pos(hwnd)
        self.cfg.set("tools", "chat_x", x)
        self.cfg.set("tools", "chat_y", y)
        self.log.emit("ok", f"Position du chat enregistrée : {x} / {y}")
        self.chat_pos_changed.emit()
        self._end_chat_capture(True, f"Position du chat enregistrée : X {x} · Y {y}")

    def _end_chat_capture(self, ok: bool, message: str) -> None:
        timer = getattr(self, "_capture_timer", None)
        if timer is not None:
            timer.cancel()
        self.hooks.cancel_click_capture()
        if not self._capturing_chat:
            return
        self._capturing_chat = False
        self.chat_capture_state.emit(False)
        self.capture_finished.emit(ok, message)

    def invite_group(self) -> None:
        if self._busy_invite:
            return
        threading.Thread(target=self._invite_group, daemon=True).start()

    def set_leader(self, pseudo: str) -> None:
        self.cfg.set("tools", "leader", pseudo)
        self.leader_changed.emit()

    def _invite_failed(self, message: str) -> None:
        self.log.emit("error", message)
        self.invite_finished.emit(False, message)

    def _invite_group(self) -> None:
        self._busy_invite = True
        self.invite_state.emit(True)
        try:
            tools = self.cfg.get("tools", default={})
            self.refresh_windows()
            leader = tools.get("leader") or self.cfg.get("main", default="")
            leader_win = self.windows.get(leader)
            if not leader_win:
                self._invite_failed(f"Chef de groupe introuvable : « {leader or 'non défini'} ». "
                                    "Choisis un chef parmi les personnages connectés.")
                return
            if tools.get("chat_x", -1) < 0:
                self._invite_failed("Position du chat non définie : clique sur « Définir sur le jeu », "
                                    "puis sur le champ de saisie du chat.")
                return
            if not any(w.pseudo != leader for w in self.active_windows()):
                self._invite_failed("Aucun autre personnage connecté à inviter.")
                return
            wait = max(0, tools.get("invite_wait", 200)) / 1000
            pause = max(0, tools.get("invite_pause", 50)) / 1000
            current, sent = leader_win, 0
            for win in self.active_windows():
                if win.pseudo == leader:
                    continue
                # 1) la fenêtre courante envoie l'invitation
                winutil.focus(current.hwnd)
                winutil.wait_foreground(current.hwnd)
                time.sleep(0.1)
                sx, sy = winutil.client_to_screen(current.hwnd, tools["chat_x"], tools["chat_y"])
                winutil.real_click(sx, sy)
                time.sleep(0.1)
                winutil.send_text(f"/invite {win.pseudo}")
                time.sleep(0.05)
                winutil.send_enter()
                # 2) attente réglable, puis l'invité passe au premier plan et valide
                time.sleep(wait)
                winutil.focus(win.hwnd)
                winutil.wait_foreground(win.hwnd)
                winutil.send_enter()
                time.sleep(pause)
                current, sent = win, sent + 1
            self.last_info = f"{sent} invitation{'s' if sent > 1 else ''} envoyée{'s' if sent > 1 else ''} par {leader}"
            self.log.emit("ok", self.last_info)
            self.info_changed.emit()
            self.invite_finished.emit(True, self.last_info)
        finally:
            self._busy_invite = False
            self.invite_state.emit(False)

    # --- presets ----------------------------------------------------------------
    def save_preset(self, name: str) -> None:
        presets = dict(self.cfg.get("presets", default={}))
        presets[name] = {
            "order": self.order(),
            "main": self.cfg.get("main", default=""),
            "excluded": list(self.cfg.get("excluded", default=[])),
            "events": dict(self.cfg.get("autofocus", "events", default={})),
        }
        self.cfg.set("presets", presets)

    def load_preset(self, name: str) -> None:
        preset = self.cfg.get("presets", default={}).get(name)
        if not preset:
            return
        self.cfg.set("order", list(preset.get("order", [])))
        self.cfg.set("main", preset.get("main", ""))
        self.cfg.set("excluded", list(preset.get("excluded", [])))
        self.cfg.set("autofocus", "events", dict(preset.get("events", {})))
        self.refresh_windows()
        self.windows_changed.emit()

    def delete_preset(self, name: str) -> None:
        presets = dict(self.cfg.get("presets", default={}))
        presets.pop(name, None)
        self.cfg.set("presets", presets)
