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
user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                ctypes.c_int, wintypes.UINT]


@dataclass(frozen=True)
class GameWindow:
    hwnd: int
    pseudo: str
    title: str


user32.InternalGetWindowText.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.InternalGetWindowText.restype = ctypes.c_int


def _title(hwnd) -> str:
    """Titre d'une fenêtre SANS interroger son application.

    GetWindowText envoie un message à la fenêtre d'une autre application et attend sa réponse : si cette
    application est occupée ou bloquée, l'appelant reste bloqué. InternalGetWindowText lit le titre déjà
    connu du système et ne peut jamais attendre une autre application.
    """
    buf = ctypes.create_unicode_buffer(512)
    length = user32.InternalGetWindowText(hwnd, buf, 512)
    return buf.value if length > 0 else ""


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


class _GUITHREADINFO(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("flags", wintypes.DWORD), ("hwndActive", wintypes.HWND),
                ("hwndFocus", wintypes.HWND), ("hwndCapture", wintypes.HWND), ("hwndMenuOwner", wintypes.HWND),
                ("hwndMoveSize", wintypes.HWND), ("hwndCaret", wintypes.HWND), ("rcCaret", wintypes.RECT)]


user32.GetGUIThreadInfo.argtypes = [wintypes.DWORD, ctypes.POINTER(_GUITHREADINFO)]
user32.IsChild.argtypes = [wintypes.HWND, wintypes.HWND]
user32.SwitchToThisWindow.argtypes = [wintypes.HWND, wintypes.BOOL]
WM_ACTIVATE, WM_SETFOCUS = 0x0006, 0x0007


def has_keyboard_focus(hwnd: int) -> bool:
    """Vrai si la fenêtre est au premier plan ET qu'un de ses éléments (la zone de jeu) a le focus clavier.

    GetGUIThreadInfo lit l'état de saisie d'un autre processus sans lui envoyer de message ni relier les files
    de saisie : on peut donc l'appeler sans risque de blocage.
    """
    if not hwnd or foreground_hwnd() != hwnd:
        return False
    info = _GUITHREADINFO()
    info.cbSize = ctypes.sizeof(_GUITHREADINFO)
    tid = user32.GetWindowThreadProcessId(hwnd, None)
    if not tid or not user32.GetGUIThreadInfo(tid, ctypes.byref(info)):
        return False
    focus_hwnd = info.hwndFocus
    return bool(focus_hwnd) and (focus_hwnd == hwnd or bool(user32.IsChild(hwnd, focus_hwnd)))


def _wait(predicate, timeout: float, step: float = 0.01) -> bool:
    end = time.monotonic() + timeout
    while True:
        if predicate():
            return True
        if time.monotonic() >= end:
            return False
        time.sleep(step)


def focus_ex(hwnd: int) -> tuple[bool, str]:
    """Met la fenêtre au premier plan ET lui donne le focus clavier, en escaladant si besoin.

    Retourne (au premier plan, détail). Aucune méthode n'utilise AttachThreadInput : relier la file de
    saisie à celle d'une autre application peut bloquer la souris de tout le système.
    """
    if not hwnd or not is_valid(hwnd):
        return False, "fenêtre introuvable"
    if user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, SW_RESTORE)
    if has_keyboard_focus(hwnd):
        return True, "déjà actif"
    # Niveau 1 : une pression sur Alt (injectée) autorise SetForegroundWindow
    if foreground_hwnd() != hwnd:
        user32.keybd_event(VK_MENU, 0, 0, 0)
        user32.keybd_event(VK_MENU, 0, KEYEVENTF_KEYUP, 0)
        user32.SetForegroundWindow(hwnd)
        if not _wait(lambda: foreground_hwnd() == hwnd, 0.15):
            # Niveau 2 : même mécanisme que le changement de fenêtre par Alt+Tab
            user32.SwitchToThisWindow(hwnd, True)
            _wait(lambda: foreground_hwnd() == hwnd, 0.2)
    if foreground_hwnd() != hwnd:
        return False, "Windows a refusé de passer la fenêtre au premier plan"
    if _wait(lambda: has_keyboard_focus(hwnd), 0.12):
        return True, "focus clavier confirmé"
    # Niveau 3 : la fenêtre est devant mais le jeu n'a pas le focus clavier (il faudrait cliquer dedans) :
    # on envoie à la fenêtre et à sa zone de jeu les messages d'activation que Windows enverrait.
    render = render_widget(hwnd)
    user32.PostMessageW(hwnd, WM_ACTIVATE, 1, 0)
    user32.PostMessageW(hwnd, WM_SETFOCUS, 0, 0)
    if render != hwnd:
        user32.PostMessageW(render, WM_SETFOCUS, 0, 0)
    if _wait(lambda: has_keyboard_focus(hwnd), 0.25):
        return True, "focus clavier confirmé (activation forcée)"
    return True, "fenêtre au premier plan, focus clavier non confirmé"


def focus(hwnd: int) -> bool:
    """Met la fenêtre au premier plan avec le focus clavier (voir focus_ex)."""
    return focus_ex(hwnd)[0]


def idle_ms() -> int:
    """Temps écoulé depuis la dernière action de l'utilisateur (clavier ou souris)."""
    class LASTINPUTINFO(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.UINT), ("dwTime", wintypes.DWORD)]
    info = LASTINPUTINFO(ctypes.sizeof(LASTINPUTINFO), 0)
    if not user32.GetLastInputInfo(ctypes.byref(info)):
        return 0
    return (kernel32.GetTickCount() - info.dwTime) & 0xFFFFFFFF


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


# --- Ordre des boutons dans la barre des tâches -------------------------------
# Windows range les boutons de la barre des tâches dans l'ordre où les fenêtres y arrivent. En changeant
# l'identifiant de groupe (AppUserModelID) de chaque fenêtre dans l'ordre voulu, on les dissocie puis on
# les regroupe dans cet ordre.
class _GUID(ctypes.Structure):
    _fields_ = [("Data1", ctypes.c_ulong), ("Data2", ctypes.c_ushort), ("Data3", ctypes.c_ushort),
                ("Data4", ctypes.c_ubyte * 8)]


class _PROPERTYKEY(ctypes.Structure):
    _fields_ = [("fmtid", _GUID), ("pid", ctypes.c_ulong)]


class _PROPVARIANT(ctypes.Structure):
    # PROPVARIANT fait 24 octets en 64 bits : type (2) + réservé (6) + union de 16 octets
    _fields_ = [("vt", ctypes.c_ushort), ("r1", ctypes.c_ushort), ("r2", ctypes.c_ushort),
                ("r3", ctypes.c_ushort), ("ptr", ctypes.c_void_p), ("pad", ctypes.c_void_p)]


def _guid(text: str) -> _GUID:
    import uuid
    return _GUID.from_buffer_copy(uuid.UUID(text).bytes_le)


_PKEY_APPUSERMODEL_ID = _PROPERTYKEY(_guid("{9F4C2855-9F79-4B39-A8D0-E1D42DE1D5F3}"), 5)
_IID_IPROPERTYSTORE = _guid("{886D8EEB-8CF2-4446-8D02-CDBA1DBDCF99}")
_VT_EMPTY, _VT_LPWSTR = 0, 31
GROUP_ID = "KalkidRetro.DofusRetro"


def set_app_id(hwnd: int, app_id: str | None) -> bool:
    """Définit l'identifiant de groupe de la barre des tâches d'une fenêtre (None = valeur par défaut)."""
    shell32 = ctypes.WinDLL("shell32")
    shell32.SHGetPropertyStoreForWindow.restype = ctypes.HRESULT
    shell32.SHGetPropertyStoreForWindow.argtypes = [wintypes.HWND, ctypes.POINTER(_GUID),
                                                    ctypes.POINTER(ctypes.c_void_p)]
    store = ctypes.c_void_p()
    try:
        shell32.SHGetPropertyStoreForWindow(hwnd, ctypes.byref(_IID_IPROPERTYSTORE), ctypes.byref(store))
    except OSError:
        return False
    if not store.value:
        return False
    vtable = ctypes.cast(ctypes.cast(store.value, ctypes.POINTER(ctypes.c_void_p))[0],
                         ctypes.POINTER(ctypes.c_void_p))
    release = ctypes.WINFUNCTYPE(ctypes.c_ulong, ctypes.c_void_p)(vtable[2])
    set_value = ctypes.WINFUNCTYPE(ctypes.HRESULT, ctypes.c_void_p, ctypes.POINTER(_PROPERTYKEY),
                                   ctypes.POINTER(_PROPVARIANT))(vtable[6])
    commit = ctypes.WINFUNCTYPE(ctypes.HRESULT, ctypes.c_void_p)(vtable[7])
    try:
        value = _PROPVARIANT()
        buffer = None
        if app_id:
            buffer = ctypes.create_unicode_buffer(app_id)      # doit rester vivant pendant SetValue
            value.vt = _VT_LPWSTR
            value.ptr = ctypes.cast(buffer, ctypes.c_void_p).value
        else:
            value.vt = _VT_EMPTY
        set_value(store.value, ctypes.byref(_PKEY_APPUSERMODEL_ID), ctypes.byref(value))
        commit(store.value)
        return True
    except OSError:
        return False
    finally:
        release(store.value)


def reorder_taskbar(hwnds: list[int]) -> int:
    """Range les fenêtres dans l'ordre donné (barre des tâches et Alt+Tab). Retourne le nombre de fenêtres traitées."""
    hwnds = [h for h in hwnds if is_valid(h)]
    if len(hwnds) < 2:
        return len(hwnds)
    done = 0
    for h in hwnds:                       # 1) dissocie : un identifiant unique par fenêtre, dans l'ordre voulu
        done += bool(set_app_id(h, f"KalkidRetro.Window.{h}"))
        time.sleep(0.12)
    time.sleep(0.3)
    flags = 0x0010 | 0x0002 | 0x0001      # SWP_NOACTIVATE | SWP_NOMOVE | SWP_NOSIZE
    for upper, lower in zip(hwnds, hwnds[1:]):   # 2) ordre d'empilement (Alt+Tab), sans changer de fenêtre active
        user32.SetWindowPos(upper, lower, 0, 0, 0, 0, flags)
        time.sleep(0.05)
    time.sleep(0.2)
    for h in hwnds:                       # 3) regroupe, toujours dans l'ordre
        set_app_id(h, GROUP_ID)
        time.sleep(0.12)
    return done


def restore_taskbar_grouping(hwnds: list[int]) -> int:
    """Rétablit le regroupement d'origine (identifiant par défaut)."""
    return sum(bool(set_app_id(h, None)) for h in hwnds if is_valid(h))


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
VK_MENU = 0x12   # touche Alt


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


def suppress_menu_activation() -> None:
    """Évite qu'un raccourci en Alt soit vu comme un simple appui sur Alt.

    Quand on avale la touche d'un raccourci Alt+X, l'application au premier plan voit « Alt enfoncé puis relâché »
    et peut activer son menu, ce qui lui vole le focus clavier. On intercale une touche neutre (code 0xE8, non
    attribuée) : l'application voit alors une combinaison Alt+touche et ne fait rien.
    """
    _send([_key(0xE8), _key(0xE8, 0, KEYEVENTF_KEYUP)])


def real_click(screen_x: int, screen_y: int) -> None:
    user32.SetCursorPos(screen_x, screen_y)
    _send([
        INPUT(type=INPUT_MOUSE, mi=MOUSEINPUT(0, 0, 0, MOUSEEVENTF_LEFTDOWN, 0, 0)),
        INPUT(type=INPUT_MOUSE, mi=MOUSEINPUT(0, 0, 0, MOUSEEVENTF_LEFTUP, 0, 0)),
    ])
