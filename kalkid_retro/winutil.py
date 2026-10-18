"""Fonctions Windows (ctypes) : détection, focus et clics sur les fenêtres Dofus Rétro."""

from __future__ import annotations

import ctypes
import re
import time
from ctypes import wintypes
from dataclasses import dataclass

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

# Titre d'une fenêtre : "Pseudo - Dofus Retro v1.49.7"
TITLE_RE = re.compile(r"^(?P<pseudo>.+?)\s+-\s+Dofus Retro", re.IGNORECASE)

SW_RESTORE = 9
WM_MOUSEMOVE = 0x0200
WM_LBUTTONDOWN = 0x0201
WM_LBUTTONUP = 0x0202
MK_LBUTTON = 0x0001

WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

user32.EnumWindows.argtypes = [WNDENUMPROC, wintypes.LPARAM]
user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
user32.IsWindowVisible.argtypes = [wintypes.HWND]
user32.IsIconic.argtypes = [wintypes.HWND]
user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
user32.GetForegroundWindow.restype = wintypes.HWND
user32.SetForegroundWindow.argtypes = [wintypes.HWND]
user32.BringWindowToTop.argtypes = [wintypes.HWND]
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
user32.AttachThreadInput.argtypes = [wintypes.DWORD, wintypes.DWORD, wintypes.BOOL]
user32.FindWindowExW.argtypes = [wintypes.HWND, wintypes.HWND, wintypes.LPCWSTR, wintypes.LPCWSTR]
user32.FindWindowExW.restype = wintypes.HWND
user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.GetCursorPos.argtypes = [ctypes.POINTER(wintypes.POINT)]
user32.ScreenToClient.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.POINT)]
user32.ClientToScreen.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.POINT)]
user32.SetCursorPos.argtypes = [ctypes.c_int, ctypes.c_int]
user32.IsWindow.argtypes = [wintypes.HWND]


@dataclass(frozen=True)
class GameWindow:
    hwnd: int
    pseudo: str
    title: str


def _title(hwnd) -> str:
    length = user32.GetWindowTextLengthW(hwnd)
    if length <= 0:
        return ""
    buf = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buf, length + 1)
    return buf.value


def window_title(hwnd: int) -> str:
    return _title(hwnd) if hwnd else ""


def pid_of(hwnd: int) -> int:
    pid = wintypes.DWORD(0)
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return int(pid.value)


class _TOKEN_ELEVATION(ctypes.Structure):
    _fields_ = [("TokenIsElevated", wintypes.DWORD)]


def is_process_elevated(pid: int) -> bool | None:
    """True si le processus tourne en administrateur ; None si on ne peut pas le savoir."""
    advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
    kernel32.OpenProcess.restype = wintypes.HANDLE
    process = kernel32.OpenProcess(0x1000, False, pid)   # PROCESS_QUERY_LIMITED_INFORMATION
    if not process:
        return None
    try:
        token = wintypes.HANDLE()
        if not advapi32.OpenProcessToken(process, 0x0008, ctypes.byref(token)):   # TOKEN_QUERY
            return None
        try:
            elevation = _TOKEN_ELEVATION()
            size = wintypes.DWORD(0)
            if not advapi32.GetTokenInformation(token, 20, ctypes.byref(elevation),
                                                ctypes.sizeof(elevation), ctypes.byref(size)):
                return None
            return bool(elevation.TokenIsElevated)
        finally:
            kernel32.CloseHandle(token)
    finally:
        kernel32.CloseHandle(process)


def is_self_elevated() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def pseudo_from_title(title: str) -> str | None:
    m = TITLE_RE.match(title or "")
    return m.group("pseudo").strip() if m else None


def list_windows() -> list[GameWindow]:
    """Toutes les fenêtres Dofus Rétro ouvertes (visibles, même réduites)."""
    found: list[GameWindow] = []

    def callback(hwnd, _):
        if user32.IsWindowVisible(hwnd):
            title = _title(hwnd)
            pseudo = pseudo_from_title(title)
            if pseudo:
                found.append(GameWindow(int(hwnd), pseudo, title))
        return True

    user32.EnumWindows(WNDENUMPROC(callback), 0)
    return found


def foreground_hwnd() -> int:
    return int(user32.GetForegroundWindow() or 0)


def foreground_pseudo() -> str | None:
    hwnd = foreground_hwnd()
    return pseudo_from_title(_title(hwnd)) if hwnd else None


def is_game_foreground() -> bool:
    return foreground_pseudo() is not None


def is_valid(hwnd: int) -> bool:
    return bool(user32.IsWindow(hwnd))


def focus(hwnd: int) -> bool:
    """Met la fenêtre au premier plan (contourne le blocage du focus de Windows)."""
    if not hwnd or not is_valid(hwnd):
        return False
    if user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, SW_RESTORE)
    fg = user32.GetForegroundWindow()
    if fg == hwnd:
        return True
    cur_tid = kernel32.GetCurrentThreadId()
    fg_tid = user32.GetWindowThreadProcessId(fg, None) if fg else 0
    attached = False
    if fg_tid and fg_tid != cur_tid:
        attached = bool(user32.AttachThreadInput(cur_tid, fg_tid, True))
    try:
        user32.BringWindowToTop(hwnd)
        ok = bool(user32.SetForegroundWindow(hwnd))
    finally:
        if attached:
            user32.AttachThreadInput(cur_tid, fg_tid, False)
    return ok or foreground_hwnd() == hwnd


def wait_foreground(hwnd: int, timeout: float = 2.0) -> bool:
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if foreground_hwnd() == hwnd:
            return True
        time.sleep(0.01)
    return foreground_hwnd() == hwnd


# --- Clics en arrière-plan -----------------------------------------------------
def render_widget(hwnd: int) -> int:
    """Zone de rendu Chromium de la fenêtre (c'est elle qui reçoit les clics du jeu)."""
    child = user32.FindWindowExW(hwnd, None, "Chrome_RenderWidgetHostHWND", None)
    return int(child) if child else int(hwnd)


def cursor_client_pos(hwnd: int) -> tuple[int, int]:
    """Position du curseur relative à la zone de rendu de la fenêtre."""
    pt = wintypes.POINT()
    user32.GetCursorPos(ctypes.byref(pt))
    user32.ScreenToClient(render_widget(hwnd), ctypes.byref(pt))
    return pt.x, pt.y


def client_to_screen(hwnd: int, x: int, y: int) -> tuple[int, int]:
    pt = wintypes.POINT(x, y)
    user32.ClientToScreen(render_widget(hwnd), ctypes.byref(pt))
    return pt.x, pt.y


def post_click(hwnd: int, x: int, y: int) -> None:
    """Clic gauche envoyé à la fenêtre sans la mettre au premier plan."""
    target = render_widget(hwnd)
    lparam = ((y & 0xFFFF) << 16) | (x & 0xFFFF)
    user32.PostMessageW(target, WM_MOUSEMOVE, 0, lparam)
    user32.PostMessageW(target, WM_LBUTTONDOWN, MK_LBUTTON, lparam)
    user32.PostMessageW(target, WM_LBUTTONUP, 0, lparam)


# --- Clignotement de la barre des tâches --------------------------------------
class FLASHWINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.UINT),
        ("hwnd", wintypes.HWND),
        ("dwFlags", wintypes.DWORD),
        ("uCount", wintypes.UINT),
        ("dwTimeout", wintypes.DWORD),
    ]


def stop_flash(hwnd: int) -> None:
    info = FLASHWINFO(ctypes.sizeof(FLASHWINFO), hwnd, 0, 0, 0)  # 0 = FLASHW_STOP
    user32.FlashWindowEx(ctypes.byref(info))


# --- Saisie clavier / souris réelle (SendInput) --------------------------------
INPUT_MOUSE, INPUT_KEYBOARD = 0, 1
KEYEVENTF_KEYUP, KEYEVENTF_UNICODE = 0x0002, 0x0004
MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP = 0x0002, 0x0004
VK_RETURN = 0x0D


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD), ("wScan", wintypes.WORD), ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t),
    ]


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG), ("dy", wintypes.LONG), ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t),
    ]


class _INPUTUNION(ctypes.Union):
    _fields_ = [("ki", KEYBDINPUT), ("mi", MOUSEINPUT)]


class INPUT(ctypes.Structure):
    _anonymous_ = ("u",)
    _fields_ = [("type", wintypes.DWORD), ("u", _INPUTUNION)]


user32.SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int]


def _send(inputs: list[INPUT]) -> None:
    arr = (INPUT * len(inputs))(*inputs)
    user32.SendInput(len(inputs), arr, ctypes.sizeof(INPUT))


def _key(vk: int = 0, scan: int = 0, flags: int = 0) -> INPUT:
    return INPUT(type=INPUT_KEYBOARD, ki=KEYBDINPUT(vk, scan, flags, 0, 0))


def send_text(text: str) -> None:
    """Tape du texte (caractères Unicode) dans la fenêtre au premier plan."""
    for ch in text:
        code = ord(ch)
        _send([_key(0, code, KEYEVENTF_UNICODE), _key(0, code, KEYEVENTF_UNICODE | KEYEVENTF_KEYUP)])
        time.sleep(0.004)


def send_enter() -> None:
    _send([_key(VK_RETURN), _key(VK_RETURN, 0, KEYEVENTF_KEYUP)])


def real_click(screen_x: int, screen_y: int) -> None:
    user32.SetCursorPos(screen_x, screen_y)
    _send([
        INPUT(type=INPUT_MOUSE, mi=MOUSEINPUT(0, 0, 0, MOUSEEVENTF_LEFTDOWN, 0, 0)),
        INPUT(type=INPUT_MOUSE, mi=MOUSEINPUT(0, 0, 0, MOUSEEVENTF_LEFTUP, 0, 0)),
    ])
