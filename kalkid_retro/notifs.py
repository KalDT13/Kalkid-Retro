"""Lecture des notifications Windows du jeu (API UserNotificationListener).

Dofus Rétro peut émettre des notifications Windows en arrière-plan (option en jeu :
Options > Général > Notification en arrière-plan). Le titre de la notification est le
pseudo du personnage concerné, le corps décrit l'événement.

Réactivité / légèreté : Windows ne fournit pas l'événement « nouvelle notification » aux
applications non empaquetées. On surveille donc le dossier où Windows écrit ses notifications
(le système nous réveille à chaque écriture, sans aucune boucle) et on ne lit les notifications
qu'à ce moment-là. Une lecture lente (filet de sécurité) couvre le cas où ce réveil échouerait.
"""

from __future__ import annotations

import asyncio
import ctypes
import os
import re
import threading
from ctypes import wintypes
from dataclasses import dataclass
from typing import Callable

# (clé d'événement, motif cherché dans le corps de la notification)
EVENT_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("combat", re.compile(r"de jouer", re.IGNORECASE)),
    ("echange", re.compile(r"te propose de faire un échange", re.IGNORECASE)),
    ("groupe", re.compile(r"t['’]invite .+ rejoindre son groupe", re.IGNORECASE)),
    ("mp", re.compile(r"^de ", re.IGNORECASE)),
]

POLL_INTERVAL = 0.1        # lecture toutes les 100 ms tant qu'une fenêtre de jeu est ouverte
IDLE_CHECK = 2.0           # sans fenêtre de jeu : un simple test toutes les 2 s
FALLBACK_POLL = POLL_INTERVAL
BURST_SCANS = 12           # lectures rapprochées après chaque écriture de Windows…
BURST_INTERVAL = 0.05      # …toutes les 50 ms (≈ 0,6 s au total)

INVALID_HANDLE = ctypes.c_void_p(-1).value
FILE_NOTIFY_CHANGE_SIZE = 0x00000008
FILE_NOTIFY_CHANGE_LAST_WRITE = 0x00000010
WAIT_OBJECT_0 = 0


@dataclass
class GameNotification:
    pseudo: str          # titre : personnage qui reçoit la notification
    body: str            # texte(s) suivants
    event: str | None    # "combat", "echange", "groupe", "mp" ou None si inconnu


# Le titre de la notification est celui de la fenêtre du jeu : « Pseudo - Dofus Retro v1.49.7 »
TITLE_RE = re.compile(r"^(?P<pseudo>.+?)\s*-\s*Dofus", re.IGNORECASE)


def pseudo_from_title(title: str) -> str:
    """Pseudo du personnage à partir du titre de la notification (ou le titre tel quel s'il est déjà un pseudo)."""
    title = (title or "").strip()
    match = TITLE_RE.match(title)
    return match.group("pseudo").strip() if match else title


def classify(body: str) -> str | None:
    for key, pattern in EVENT_PATTERNS:
        if pattern.search(body):
            return key
    return None


def notifications_dir() -> str:
    return os.path.join(os.environ.get("LOCALAPPDATA", ""), "Microsoft", "Windows", "Notifications")


class NotificationWatcher:
    """Surveille les notifications dans un thread dédié et appelle `on_notification`."""

    def __init__(self, on_notification: Callable[[GameNotification], None],
                 on_status: Callable[[str, str], None] | None = None,
                 is_active: Callable[[], bool] | None = None):
        self._on_notification = on_notification
        self._is_active = is_active or (lambda: True)
        self._on_status = on_status or (lambda level, message: None)
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self.access_ok = False
        self.access_error = ""       # message d'erreur si l'accès est refusé
        self.event_driven = False    # vrai si la surveillance du dossier est active
        self.read_count = 0
        self._aio_loop: asyncio.AbstractEventLoop | None = None
        self._wake: asyncio.Event | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            if not self._stop.is_set():
                return
            self._thread.join(timeout=3)      # arrêt en cours : on attend qu'il se termine
        self._stop.clear()
        self.event_driven = False
        self._thread = threading.Thread(target=self._run, daemon=True, name="kalkid-notifs")
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        loop, wake = self._aio_loop, self._wake
        if loop is not None and wake is not None:
            try:
                loop.call_soon_threadsafe(wake.set)   # réveille la boucle pour qu'elle s'arrête
            except RuntimeError:
                pass

    def _run(self) -> None:
        try:
            asyncio.run(self._main())
        except Exception as exc:  # winsdk absent, accès refusé, etc.
            self._on_status("error", f"Lecture des notifications arrêtée : {exc}")

    # --- réveil par le système de fichiers ----------------------------------------
    def _watch_folder(self, loop: asyncio.AbstractEventLoop, wake: asyncio.Event) -> bool:
        """Thread bloqué dans le noyau tant que Windows n'écrit rien : zéro CPU entre deux notifications."""
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.FindFirstChangeNotificationW.argtypes = [wintypes.LPCWSTR, wintypes.BOOL, wintypes.DWORD]
        kernel32.FindFirstChangeNotificationW.restype = wintypes.HANDLE
        kernel32.FindNextChangeNotification.argtypes = [wintypes.HANDLE]
        kernel32.FindCloseChangeNotification.argtypes = [wintypes.HANDLE]
        kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        handle = kernel32.FindFirstChangeNotificationW(
            notifications_dir(), False, FILE_NOTIFY_CHANGE_LAST_WRITE | FILE_NOTIFY_CHANGE_SIZE)
        if not handle or handle == INVALID_HANDLE:
            return False

        def work():
            try:
                while not self._stop.is_set():
                    if kernel32.WaitForSingleObject(handle, 500) == WAIT_OBJECT_0:
                        try:
                            loop.call_soon_threadsafe(wake.set)
                        except RuntimeError:
                            break
                        kernel32.FindNextChangeNotification(handle)
            finally:
                kernel32.FindCloseChangeNotification(handle)

        threading.Thread(target=work, daemon=True, name="kalkid-notif-folder").start()
        return True

    # --- boucle principale ----------------------------------------------------------
    async def _main(self) -> None:
        try:
            from winsdk.windows.ui.notifications import KnownNotificationBindings, NotificationKinds
            from winsdk.windows.ui.notifications.management import (
                UserNotificationListener, UserNotificationListenerAccessStatus)
        except ImportError:
            self._on_status("error", "Module winsdk introuvable : autofocus indisponible.")
            return

        listener = UserNotificationListener.current
        access = await listener.request_access_async()
        if access != UserNotificationListenerAccessStatus.ALLOWED:
            self.access_ok = False
            self.access_error = ("Accès aux notifications refusé. Active-les dans "
                                 "Paramètres > Système > Notifications.")
            self._on_status("error", self.access_error)
            return
        self.access_ok = True
        self.access_error = ""
        self._on_status("ok", "Accès aux notifications accordé.")

        try:
            generic = KnownNotificationBindings.get_toast_generic()
        except AttributeError:
            generic = KnownNotificationBindings.toast_generic

        loop = asyncio.get_running_loop()
        wake = asyncio.Event()
        self._aio_loop, self._wake = loop, wake
        self.event_driven = self._watch_folder(loop, wake)
        timeout = FALLBACK_POLL if self.event_driven else POLL_INTERVAL
        if not self.event_driven:
            self._on_status("info", "Surveillance du dossier indisponible : lecture périodique.")

        seen: set[int] = set()
        failures: dict[int, int] = {}
        first = True

        async def scan() -> None:
            nonlocal first
            try:
                notifications = await listener.get_notifications_async(NotificationKinds.TOAST)
                current_ids = set()
                for item in notifications:
                    current_ids.add(item.id)
                    if item.id in seen:
                        continue
                    if first:          # notifications déjà présentes au démarrage : ignorées
                        seen.add(item.id)
                        continue
                    # Marquée « lue » seulement une fois traitée : si Windows n'a pas fini d'écrire
                    # la notification, la lecture échoue et sera retentée au prochain passage.
                    try:
                        self._handle(item, generic)
                        seen.add(item.id)
                    except Exception as exc:
                        failures[item.id] = failures.get(item.id, 0) + 1
                        if failures[item.id] >= 5:
                            seen.add(item.id)
                            self._on_status("error", f"Notification illisible ignorée : {exc}")
                seen.intersection_update(current_ids)
                for stale in [i for i in failures if i not in current_ids]:
                    failures.pop(stale, None)
                first = False
            except Exception as exc:
                self._on_status("error", f"Erreur de lecture : {exc}")

        last_check = 0.0
        active = True
        while not self._stop.is_set():
            # Sans fenêtre de jeu, inutile de lire : on ne fait qu'un test léger toutes les 2 s.
            now = loop.time()
            if now - last_check >= (1.0 if active else IDLE_CHECK):
                last_check = now
                try:
                    active = bool(self._is_active())
                except Exception:
                    active = True
            if active:
                await scan()
            try:
                await asyncio.wait_for(wake.wait(), timeout=timeout if active else IDLE_CHECK)
            except asyncio.TimeoutError:
                wake.clear()
                continue
            wake.clear()
            # Windows vient d'écrire : une notification peut n'être visible que 100-400 ms dans la
            # liste. On relit donc tout de suite, puis en rafale brève (pas de lecture le reste du temps).
            for _ in range(BURST_SCANS):
                if self._stop.is_set():
                    break
                await scan()
                await asyncio.sleep(BURST_INTERVAL)
            wake.clear()

    @staticmethod
    def _is_dofus(item) -> bool:
        """Ne lit que les notifications de Dofus (jamais celles des autres applications)."""
        try:
            app = item.app_info
            names = f"{app.app_user_model_id} {app.display_info.display_name}".lower()
        except Exception:
            return False
        return "dofus" in names

    def _handle(self, item, generic) -> None:
        if not self._is_dofus(item):
            return
        binding = item.notification.visual.get_binding(generic)
        if binding is None:
            return
        texts = [t.text for t in binding.get_text_elements()]
        if not texts:
            return
        pseudo, body = pseudo_from_title(texts[0]), " ".join(texts[1:]).strip()
        self.read_count += 1
        self._on_notification(GameNotification(pseudo, body, classify(body)))
