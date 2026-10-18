"""Vérification des prérequis pour que Kalkid Rétro fonctionne (lecture seule, aucune modification)."""

from __future__ import annotations

import sys
import winreg
from dataclasses import dataclass

from . import winutil

OK, WARN, ERROR, PENDING = "ok", "warn", "error", "pending"

MIN_BUILD = 14393  # Windows 10 1607 : première version avec l'API de lecture des notifications


@dataclass
class Check:
    key: str
    title: str
    state: str          # ok | warn | error | pending
    detail: str
    fix_uri: str = ""   # lien ms-settings: pour ouvrir le bon réglage Windows
    blocking: bool = False   # un échec empêche une fonction principale (autofocus)


def _reg_dword(root, path: str, name: str) -> int | None:
    try:
        with winreg.OpenKey(root, path) as key:
            value, _ = winreg.QueryValueEx(key, name)
            return int(value)
    except OSError:
        return None


def check_windows() -> Check:
    if sys.platform != "win32":
        return Check("os", "Système Windows", ERROR, "Kalkid Rétro fonctionne uniquement sous Windows.", blocking=True)
    build = sys.getwindowsversion().build
    if build < MIN_BUILD:
        return Check("os", "Version de Windows", ERROR,
                     f"Windows 10 (1607) ou plus récent requis (build détecté : {build}).", blocking=True)
    return Check("os", "Version de Windows", OK, f"Windows compatible (build {build}).")


def check_toasts_enabled() -> Check:
    value = _reg_dword(winreg.HKEY_CURRENT_USER,
                       r"Software\Microsoft\Windows\CurrentVersion\PushNotifications", "ToastEnabled")
    if value == 0:
        return Check("toast", "Notifications Windows", ERROR,
                     "Les notifications sont désactivées dans Windows.",
                     "ms-settings:notifications", blocking=True)
    return Check("toast", "Notifications Windows", OK, "Activées.")


def check_dofus_toasts() -> Check:
    base = r"Software\Microsoft\Windows\CurrentVersion\Notifications\Settings"
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, base) as root:
            index = 0
            while True:
                try:
                    name = winreg.EnumKey(root, index)
                except OSError:
                    break
                index += 1
                if "dofus" not in name.lower():
                    continue
                enabled = _reg_dword(winreg.HKEY_CURRENT_USER, f"{base}\\{name}", "Enabled")
                if enabled == 0:
                    return Check("dofus_toast", "Notifications de Dofus", ERROR,
                                 "Les notifications de l'application Dofus sont désactivées dans Windows.",
                                 "ms-settings:notifications", blocking=True)
                return Check("dofus_toast", "Notifications de Dofus", OK, "Autorisées pour l'application Dofus.")
    except OSError:
        pass
    return Check("dofus_toast", "Notifications de Dofus", WARN,
                 "Application Dofus pas encore connue de Windows : elle apparaît après la première notification "
                 "du jeu (voir l'option en jeu).")


def check_listener(controller) -> Check:
    watcher = controller.notifs
    if not controller.cfg.get("autofocus", "enabled", default=True):
        return Check("listener", "Accès aux notifications", WARN, "Autofocus désactivé.")
    if watcher.access_ok:
        mode = "événementiel (réaction immédiate)" if watcher.event_driven else "lecture périodique"
        return Check("listener", "Accès aux notifications", OK, f"Accordé · mode {mode}.")
    if watcher.access_error:
        return Check("listener", "Accès aux notifications", ERROR, watcher.access_error,
                     "ms-settings:privacy-notifications", blocking=True)
    return Check("listener", "Accès aux notifications", PENDING, "Vérification en cours…")


def check_in_game_option(controller) -> Check:
    if controller.notifs.read_count > 0:
        return Check("ingame", "Option en jeu", OK, "Le jeu envoie bien des notifications.")
    return Check("ingame", "Option en jeu", WARN,
                 "Non vérifiable automatiquement : dans Dofus, Options > Général > « Notification en "
                 "arrière-plan » doit être activée. Ce voyant passe au vert dès qu'une notification du jeu "
                 "est reçue.")


def check_game_windows(controller) -> Check:
    count = len(controller.windows)
    if count == 0:
        return Check("windows", "Fenêtres Dofus Rétro", WARN,
                     "Aucune fenêtre détectée : lance Dofus Rétro (titre « Pseudo - Dofus Retro … »).")
    return Check("windows", "Fenêtres Dofus Rétro", OK,
                 f"{count} fenêtre{'s' if count > 1 else ''} détectée{'s' if count > 1 else ''}.")


def check_hooks(controller) -> Check:
    if controller.hooks.installed:
        return Check("hooks", "Raccourcis clavier et souris", OK, "Hooks installés.")
    return Check("hooks", "Raccourcis clavier et souris", ERROR,
                 "Impossible d'installer les raccourcis globaux (un antivirus ou une règle de sécurité les "
                 "bloque peut-être).", blocking=True)


def check_privileges(controller) -> Check:
    if winutil.is_self_elevated():
        return Check("rights", "Droits d'exécution", OK, "Kalkid Rétro tourne en administrateur.")
    for win in controller.windows.values():
        if winutil.is_process_elevated(winutil.pid_of(win.hwnd)):
            return Check("rights", "Droits d'exécution", ERROR,
                         "Dofus tourne en administrateur mais pas Kalkid Rétro : Windows bloque alors les "
                         "raccourcis et le changement de fenêtre. Relance Kalkid Rétro en administrateur "
                         "(ou lance Dofus sans).", blocking=True)
    return Check("rights", "Droits d'exécution", OK, "Aucun conflit de droits détecté.")


def check_all(controller) -> list[Check]:
    return [
        check_windows(),
        check_toasts_enabled(),
        check_dofus_toasts(),
        check_listener(controller),
        check_in_game_option(controller),
        check_game_windows(controller),
        check_hooks(controller),
        check_privileges(controller),
    ]


def blocking_problems(checks: list[Check]) -> list[Check]:
    return [c for c in checks if c.state == ERROR and c.blocking]
