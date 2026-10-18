"""Logique centrale : ordre des fenêtres, autofocus, clics synchronisés, invitations."""

from __future__ import annotations

import random
import threading
import time

from PySide6.QtCore import QObject, Signal

from . import winutil
from .config import EVENTS, Config
from .hotkeys import HookManager
from .notifs import GameNotification, NotificationWatcher


class Controller(QObject):
    log = Signal(str, str)            # niveau ("info" | "ok" | "error" | "notif"), message
    windows_changed = Signal()
    info_changed = Signal()           # texte d'état (dernier clic, compteurs…)
    chat_pos_changed = Signal()
    hotkey_captured = Signal(str, str)  # nom de l'action, raccourci capturé

    def __init__(self, config: Config):
        super().__init__()
        self.cfg = config
        self.windows: dict[str, winutil.GameWindow] = {}   # pseudo -> fenêtre ouverte
        self.last_info = "aucun clic pour l'instant"
        self.last_gaps: list[int] = []
        self._busy_click = False
        self._busy_invite = False
        self._stop = threading.Event()

        # Mis à jour par un thread : les hooks ne doivent jamais interroger Windows (trop lent)
        self.game_fg = False

        self.hooks = HookManager()
        self.hooks.set_condition(lambda: self.game_fg)
        self.hooks.set_foreground_callback(self._on_foreground)
        self.hooks.set_middle_click(lambda: self.click_all(True), self._wheel_enabled)
        self.notifs = NotificationWatcher(self._on_notification, self.log.emit,
                                          lambda: bool(winutil.list_windows()))
        self.notif_count = 0
        self.focus_count = 0

    # --- cycle de vie -----------------------------------------------------------
    def start(self) -> None:
        self.refresh_windows()
        self.rebind_hotkeys()
        self.hooks.start()
        if self.cfg.get("autofocus", "enabled", default=True):
            self.notifs.start()
        threading.Thread(target=self._anti_flash_loop, daemon=True, name="kalkid-flash").start()

    def _on_foreground(self, hwnd: int) -> None:
        """Appelé par Windows à chaque changement de fenêtre active (aucun polling)."""
        self.game_fg = bool(hwnd) and winutil.pseudo_from_title(winutil.window_title(hwnd)) is not None

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
        winutil.focus(wins[(idx + step) % len(wins)].hwnd)

    def focus_pseudo(self, pseudo: str) -> bool:
        # Chemin rapide : fenêtre déjà connue et toujours valide (aucune énumération des fenêtres).
        win = self.windows.get(pseudo)
        if not (win and winutil.is_valid(win.hwnd)):
            self.refresh_windows()
            win = self.windows.get(pseudo)
        return bool(win and winutil.focus(win.hwnd))

    def focus_main(self) -> None:
        main = self.cfg.get("main", default="")
        if main:
            self.focus_pseudo(main)

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
            self.log.emit("ok", f"Focus sur {notif.pseudo} ({EVENTS.get(notif.event, notif.event)})")
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
            bindings[hk.get("capture_chat", "")] = (self.capture_chat, True)
            bindings[hk.get("invite", "")] = (self.invite_group, True)
        self.hooks.set_bindings({k: v for k, v in bindings.items() if k})

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
            self.refresh_windows()
            wins = self.active_windows()
            lo = min(self.cfg.get("tools", "delay_min", default=90), self.cfg.get("tools", "delay_max", default=130))
            hi = max(self.cfg.get("tools", "delay_min", default=90), self.cfg.get("tools", "delay_max", default=130))
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
    def capture_chat(self) -> None:
        hwnd = winutil.foreground_hwnd()
        if not hwnd or not winutil.foreground_pseudo():
            return
        x, y = winutil.cursor_client_pos(hwnd)
        self.cfg.set("tools", "chat_x", x)
        self.cfg.set("tools", "chat_y", y)
        self.log.emit("ok", f"Position du chat enregistrée : {x} / {y}")
        self.chat_pos_changed.emit()

    def invite_group(self) -> None:
        if self._busy_invite:
            return
        threading.Thread(target=self._invite_group, daemon=True).start()

    def _invite_group(self) -> None:
        self._busy_invite = True
        try:
            tools = self.cfg.get("tools", default={})
            self.refresh_windows()
            leader = tools.get("leader") or self.cfg.get("main", default="")
            leader_win = self.windows.get(leader)
            if not leader_win:
                self.log.emit("error", f"Chef de groupe introuvable : « {leader or 'non défini'} ».")
                return
            if tools.get("chat_x", -1) < 0:
                self.log.emit("error", "Position du chat non définie (Outils > Groupe, puis touche de capture).")
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
            self.last_info = f"{sent} invitations envoyées par {leader}"
            self.log.emit("ok", self.last_info)
            self.info_changed.emit()
        finally:
            self._busy_invite = False

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
