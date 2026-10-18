"""Raccourcis clavier / souris globaux via des hooks bas niveau Windows (ctypes)."""

from __future__ import annotations

import ctypes
import queue
import threading
from ctypes import wintypes
from typing import Callable

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

WH_KEYBOARD_LL, WH_MOUSE_LL = 13, 14
WM_KEYDOWN, WM_KEYUP, WM_SYSKEYDOWN, WM_SYSKEYUP = 0x0100, 0x0101, 0x0104, 0x0105
WM_LBUTTONDOWN, WM_LBUTTONUP = 0x0201, 0x0202
WM_MBUTTONDOWN, WM_MBUTTONUP = 0x0207, 0x0208
WM_QUIT = 0x0012

MOD_CTRL, MOD_ALT, MOD_SHIFT, MOD_WIN = 1, 2, 4, 8
_MOD_KEYS = {0x10: MOD_SHIFT, 0xA0: MOD_SHIFT, 0xA1: MOD_SHIFT,
             0x11: MOD_CTRL, 0xA2: MOD_CTRL, 0xA3: MOD_CTRL,
             0x12: MOD_ALT, 0xA4: MOD_ALT, 0xA5: MOD_ALT,
             0x5B: MOD_WIN, 0x5C: MOD_WIN}

# Noms de touches -> code virtuel
_NAMED = {
    "TAB": 0x09, "CAPSLOCK": 0x14, "ESC": 0x1B, "SPACE": 0x20, "ENTER": 0x0D,
    "BACKSPACE": 0x08, "INSERT": 0x2D, "DELETE": 0x2E, "HOME": 0x24, "END": 0x23,
    "PAGEUP": 0x21, "PAGEDOWN": 0x22, "LEFT": 0x25, "UP": 0x26, "RIGHT": 0x27, "DOWN": 0x28,
    "`": 0xC0, "²": 0xDE,
}
for _i in range(1, 25):
    _NAMED[f"F{_i}"] = 0x6F + _i
for _c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
    _NAMED[_c] = ord(_c)
for _d in "0123456789":
    _NAMED[_d] = ord(_d)
for _i in range(10):
    _NAMED[f"NUM{_i}"] = 0x60 + _i
_VK_NAMES = {v: k for k, v in _NAMED.items()}

ULONG_PTR = ctypes.c_size_t


class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [("vkCode", wintypes.DWORD), ("scanCode", wintypes.DWORD), ("flags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", ULONG_PTR)]


class MSLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [("pt", wintypes.POINT), ("mouseData", wintypes.DWORD), ("flags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", ULONG_PTR)]


EVENT_SYSTEM_FOREGROUND = 0x0003
WINEVENT_OUTOFCONTEXT = 0x0000
WINEVENTPROC = ctypes.WINFUNCTYPE(None, wintypes.HANDLE, wintypes.DWORD, wintypes.HWND, wintypes.LONG,
                                  wintypes.LONG, wintypes.DWORD, wintypes.DWORD)
user32.SetWinEventHook.argtypes = [wintypes.DWORD, wintypes.DWORD, wintypes.HMODULE, WINEVENTPROC,
                                   wintypes.DWORD, wintypes.DWORD, wintypes.DWORD]
user32.SetWinEventHook.restype = wintypes.HANDLE
user32.UnhookWinEvent.argtypes = [wintypes.HANDLE]
user32.GetForegroundWindow.restype = wintypes.HWND

HOOKPROC = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)
user32.SetWindowsHookExW.argtypes = [ctypes.c_int, HOOKPROC, wintypes.HINSTANCE, wintypes.DWORD]
user32.SetWindowsHookExW.restype = wintypes.HHOOK
user32.CallNextHookEx.argtypes = [wintypes.HHOOK, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM]
user32.CallNextHookEx.restype = ctypes.c_ssize_t
user32.UnhookWindowsHookEx.argtypes = [wintypes.HHOOK]
user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
user32.PostThreadMessageW.argtypes = [wintypes.DWORD, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
kernel32.GetModuleHandleW.restype = wintypes.HMODULE

# Événements injectés (SendInput) : on ignore ceux que ce programme génère lui-même
INJECTED = 0x10        # LLKHF_INJECTED (clavier)
MOUSE_INJECTED = 0x01  # LLMHF_INJECTED (souris)


def parse_hotkey(text: str) -> tuple[int, int] | None:
    """'Ctrl+Shift+F2' -> (modificateurs, vk). None si vide ou invalide."""
    if not text:
        return None
    mods, vk = 0, 0
    for part in [p.strip() for p in text.split("+") if p.strip()]:
        up = part.upper()
        if up in ("CTRL", "CONTROL"):
            mods |= MOD_CTRL
        elif up == "ALT":
            mods |= MOD_ALT
        elif up == "SHIFT":
            mods |= MOD_SHIFT
        elif up in ("WIN", "WINDOWS"):
            mods |= MOD_WIN
        elif up in _NAMED:
            vk = _NAMED[up]
        else:
            return None
    return (mods, vk) if vk else None


def format_hotkey(mods: int, vk: int) -> str:
    parts = []
    if mods & MOD_CTRL:
        parts.append("Ctrl")
    if mods & MOD_ALT:
        parts.append("Alt")
    if mods & MOD_SHIFT:
        parts.append("Shift")
    if mods & MOD_WIN:
        parts.append("Win")
    name = _VK_NAMES.get(vk, f"0x{vk:02X}")
    parts.append(name.capitalize() if len(name) > 1 and not name.startswith("F") else name)
    return "+".join(parts)


def _current_mods() -> int:
    mods = 0
    if user32.GetAsyncKeyState(0x11) & 0x8000:
        mods |= MOD_CTRL
    if user32.GetAsyncKeyState(0x12) & 0x8000:
        mods |= MOD_ALT
    if user32.GetAsyncKeyState(0x10) & 0x8000:
        mods |= MOD_SHIFT
    if (user32.GetAsyncKeyState(0x5B) | user32.GetAsyncKeyState(0x5C)) & 0x8000:
        mods |= MOD_WIN
    return mods


class HookManager:
    """Gère les hooks clavier/souris dans un thread dédié.

    Les callbacks ne sont jamais exécutés dans le hook (Windows coupe les hooks lents) :
    ils passent par une file traitée par un thread de travail.
    """

    def __init__(self):
        self._bindings: dict[tuple[int, int], tuple[Callable[[], None], bool]] = {}
        self._middle: Callable[[], None] | None = None
        self._middle_enabled: Callable[[], bool] = lambda: False
        self._condition: Callable[[], bool] = lambda: True
        self._capture: Callable[[str], None] | None = None
        self._click_capture: tuple[Callable[[], None], Callable[[], None]] | None = None
        self._swallow_up = False
        self._lock = threading.Lock()
        self._pressed: set[int] = set()
        self._queue: queue.Queue = queue.Queue()
        self._thread: threading.Thread | None = None
        self._worker: threading.Thread | None = None
        self._tid = 0
        self._kb_hook = None
        self._ms_hook = None
        self._kb_proc = HOOKPROC(self._keyboard_proc)
        self._ms_proc = HOOKPROC(self._mouse_proc)
        self._fg_proc = WINEVENTPROC(self._foreground_event)
        self._fg_hook = None
        self._on_foreground: Callable[[int], None] | None = None
        self._running = False

    @property
    def installed(self) -> bool:
        """Vrai si les deux hooks (clavier et souris) sont bien en place."""
        return bool(self._kb_hook and self._ms_hook)

    def set_foreground_callback(self, fn: Callable[[int], None]) -> None:
        """fn(hwnd) est appelé à chaque changement de fenêtre au premier plan (sans polling)."""
        self._on_foreground = fn

    def _foreground_event(self, hook, event, hwnd, id_object, id_child, thread, time_ms):
        if self._on_foreground:
            try:
                self._on_foreground(int(hwnd or 0))
            except Exception:
                pass

    # --- configuration ----------------------------------------------------------
    def set_condition(self, fn: Callable[[], bool]) -> None:
        """Les raccourcis marqués 'seulement en jeu' ne réagissent que si fn() est vrai."""
        self._condition = fn

    def set_bindings(self, bindings: dict[str, tuple[Callable[[], None], bool]]) -> None:
        """bindings: {'Shift+Tab': (callback, only_in_game)}."""
        parsed = {}
        for text, value in bindings.items():
            key = parse_hotkey(text)
            if key:
                parsed[key] = value
        with self._lock:
            self._bindings = parsed

    def set_middle_click(self, callback: Callable[[], None] | None, enabled: Callable[[], bool]) -> None:
        self._middle = callback
        self._middle_enabled = enabled

    def capture_next(self, callback: Callable[[str], None]) -> None:
        """Le prochain raccourci pressé est transmis à callback (puis consommé)."""
        self._capture = callback

    def cancel_capture(self) -> None:
        self._capture = None

    def capture_click(self, on_click: Callable[[], None], on_cancel: Callable[[], None]) -> None:
        """Le prochain clic gauche est consommé (il n'atteint pas le jeu) et déclenche on_click ;
        la touche Échap annule et déclenche on_cancel."""
        self._swallow_up = False
        self._click_capture = (on_click, on_cancel)

    def cancel_click_capture(self) -> None:
        self._click_capture = None

    # --- cycle de vie -----------------------------------------------------------
    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._worker = threading.Thread(target=self._work, daemon=True, name="kalkid-hotkey-worker")
        self._worker.start()
        self._thread = threading.Thread(target=self._run_hooks, daemon=True, name="kalkid-hooks")
        self._thread.start()

    def stop(self) -> None:
        if not self._running:
            return
        self._running = False
        if self._tid:
            user32.PostThreadMessageW(self._tid, WM_QUIT, 0, 0)
        self._queue.put(None)

    def _run_hooks(self) -> None:
        self._tid = kernel32.GetCurrentThreadId()
        hmod = kernel32.GetModuleHandleW(None)
        self._kb_hook = user32.SetWindowsHookExW(WH_KEYBOARD_LL, self._kb_proc, hmod, 0)
        self._ms_hook = user32.SetWindowsHookExW(WH_MOUSE_LL, self._ms_proc, hmod, 0)
        self._fg_hook = user32.SetWinEventHook(EVENT_SYSTEM_FOREGROUND, EVENT_SYSTEM_FOREGROUND, None,
                                               self._fg_proc, 0, 0, WINEVENT_OUTOFCONTEXT)
        self._foreground_event(None, 0, user32.GetForegroundWindow(), 0, 0, 0, 0)   # état initial
        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))
        if self._kb_hook:
            user32.UnhookWindowsHookEx(self._kb_hook)
        if self._ms_hook:
            user32.UnhookWindowsHookEx(self._ms_hook)
        if self._fg_hook:
            user32.UnhookWinEvent(self._fg_hook)

    def _work(self) -> None:
        while True:
            fn = self._queue.get()
            if fn is None:
                return
            try:
                fn()
            except Exception:  # un raccourci qui plante ne doit pas tuer les autres
                import traceback
                traceback.print_exc()

    # --- hooks ------------------------------------------------------------------
    def _keyboard_proc(self, n_code, w_param, l_param):
        try:
            if n_code >= 0:
                info = ctypes.cast(l_param, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
                if not (info.flags & INJECTED):
                    vk = info.vkCode
                    down = w_param in (WM_KEYDOWN, WM_SYSKEYDOWN)
                    if down:
                        first = vk not in self._pressed
                        self._pressed.add(vk)
                        if vk not in _MOD_KEYS and self._handle_key(vk, first):
                            return 1
                    elif w_param in (WM_KEYUP, WM_SYSKEYUP):
                        self._pressed.discard(vk)
        except Exception:
            pass
        return user32.CallNextHookEx(None, n_code, w_param, l_param)

    def _handle_key(self, vk: int, first: bool) -> bool:
        click_cap = self._click_capture
        if click_cap is not None and vk == 0x1B:          # Échap : annule la capture du clic
            if first:
                self._click_capture = None
                self._queue.put(click_cap[1])
            return True
        mods = _current_mods()
        cap = self._capture
        if cap is not None:
            if first:
                self._capture = None
                text = format_hotkey(mods, vk)
                self._queue.put(lambda: cap(text))
            return True
        with self._lock:
            entry = self._bindings.get((mods, vk))
        if not entry:
            return False
        callback, only_in_game = entry
        if only_in_game and not self._condition():
            return False
        if first:
            self._queue.put(callback)
        return True

    def _mouse_proc(self, n_code, w_param, l_param):
        try:
            if n_code >= 0 and w_param in (WM_LBUTTONDOWN, WM_LBUTTONUP):
                info = ctypes.cast(l_param, ctypes.POINTER(MSLLHOOKSTRUCT)).contents
                if not (info.flags & MOUSE_INJECTED):
                    cap = self._click_capture
                    if cap is not None and w_param == WM_LBUTTONDOWN:
                        self._click_capture = None
                        self._swallow_up = True
                        self._queue.put(cap[0])
                        return 1                            # ce clic n'atteint pas le jeu
                    if self._swallow_up and w_param == WM_LBUTTONUP:
                        self._swallow_up = False
                        return 1
            if n_code >= 0 and w_param in (WM_MBUTTONDOWN, WM_MBUTTONUP):
                info = ctypes.cast(l_param, ctypes.POINTER(MSLLHOOKSTRUCT)).contents
                if (not (info.flags & MOUSE_INJECTED) and self._middle is not None
                        and self._middle_enabled() and self._condition()):
                    if w_param == WM_MBUTTONDOWN:
                        self._queue.put(self._middle)
                    return 1
        except Exception:
            pass
        return user32.CallNextHookEx(None, n_code, w_param, l_param)
