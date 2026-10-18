"""Mises à jour : compare la version installée à la dernière release GitHub et installe la nouvelle.

Sécurité : seuls les téléchargements en HTTPS depuis github.com (ou son CDN de fichiers) sont acceptés ;
le fichier doit être un exécutable Windows et, quand la release publie une somme SHA-256, elle est vérifiée.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from PySide6.QtCore import QObject, Signal

from . import __version__

REPO = "KalDT13/Kalkid-Retro"
API_LATEST = f"https://api.github.com/repos/{REPO}/releases/latest"
RELEASES_PAGE = f"https://github.com/{REPO}/releases/latest"
ASSET_NAME = "Kalkid-Retro.exe"
ALLOWED_HOSTS = ("github.com", "githubusercontent.com")   # releases + CDN des fichiers
USER_AGENT = f"KalkidRetro/{__version__}"


@dataclass
class UpdateInfo:
    version: str
    url: str
    size: int
    sha256_url: str = ""
    page: str = RELEASES_PAGE


def parse_version(text: str) -> tuple[int, ...]:
    return tuple(int(n) for n in re.findall(r"\d+", text or ""))


def is_newer(remote: str, local: str = __version__) -> bool:
    return parse_version(remote) > parse_version(local)


def _host_allowed(url: str) -> bool:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    return parsed.scheme == "https" and any(host == h or host.endswith("." + h) for h in ALLOWED_HOSTS)


def _open(url: str, timeout: int = 15):
    if not _host_allowed(url):
        raise ValueError(f"Adresse non autorisée : {url}")
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/octet-stream"})
    return urllib.request.urlopen(request, timeout=timeout)


def fetch_latest() -> UpdateInfo | None:
    """Dernière release publiée, ou None si aucune.

    On suit la redirection de github.com/<repo>/releases/latest vers .../releases/tag/<vX.Y.Z> :
    contrairement à l'API GitHub, cette adresse n'est pas soumise à la limite de requêtes.
    """
    request = urllib.request.Request(RELEASES_PAGE, method="HEAD", headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=15) as response:
        final_url = response.geturl()
    match = re.search(r"/releases/tag/([^/?#]+)", final_url)
    if not match:
        return None
    tag = match.group(1)
    base = f"https://github.com/{REPO}/releases/download/{tag}"
    return UpdateInfo(tag.lstrip("vV"), f"{base}/{ASSET_NAME}", 0, f"{base}/{ASSET_NAME}.sha256", final_url)


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


class Updater(QObject):
    checked = Signal(object, str)     # UpdateInfo ou None, message d'erreur ("" si ok)
    progress = Signal(int)            # pourcentage de téléchargement
    failed = Signal(str)
    installing = Signal()             # téléchargement terminé : l'application va redémarrer

    def __init__(self):
        super().__init__()
        self.info: UpdateInfo | None = None
        self._busy = False

    # --- vérification -----------------------------------------------------------
    def check(self) -> None:
        threading.Thread(target=self._check, daemon=True, name="kalkid-update-check").start()

    def _check(self) -> None:
        try:
            info = fetch_latest()
        except Exception as exc:
            self.checked.emit(None, f"Impossible de joindre GitHub : {exc}")
            return
        self.info = info if info and is_newer(info.version) else None
        self.checked.emit(self.info, "")

    # --- installation -----------------------------------------------------------
    def install(self) -> None:
        if self._busy or self.info is None:
            return
        self._busy = True
        threading.Thread(target=self._install, args=(self.info,), daemon=True, name="kalkid-update").start()

    def _install(self, info: UpdateInfo) -> None:
        try:
            if not is_frozen():
                raise RuntimeError("La mise à jour automatique ne fonctionne que dans l'exe. "
                                   "Télécharge la nouvelle version depuis la page des Releases.")
            current = Path(sys.executable)
            target = self._download(info, current.parent)
            self._launch_swap(current, target)
            self.installing.emit()
        except Exception as exc:
            self.failed.emit(str(exc))
        finally:
            self._busy = False

    def _download(self, info: UpdateInfo, folder: Path) -> Path:
        # même dossier que l'exe (déplacement atomique) ; sinon dossier temporaire
        for base in (folder, Path(tempfile.gettempdir())):
            try:
                target = base / "Kalkid-Retro.update.exe"
                with open(target, "wb"):
                    pass
                break
            except OSError:
                continue
        else:
            raise RuntimeError("Aucun dossier accessible en écriture pour télécharger la mise à jour.")

        expected = ""
        if info.sha256_url:
            try:
                with _open(info.sha256_url) as r:
                    expected = r.read(256).decode("ascii", "ignore").strip().split()[0].lower()
            except Exception:
                expected = ""   # releases anciennes sans somme de contrôle : on se fie à HTTPS + MZ
        digest = hashlib.sha256()
        done = 0
        with _open(info.url, timeout=30) as response, open(target, "wb") as out:
            total = int(response.headers.get("Content-Length") or info.size or 0)
            while chunk := response.read(256 * 1024):
                out.write(chunk)
                digest.update(chunk)
                done += len(chunk)
                if total:
                    self.progress.emit(min(100, int(done * 100 / total)))
        with open(target, "rb") as fh:
            if fh.read(2) != b"MZ":
                target.unlink(missing_ok=True)
                raise RuntimeError("Le fichier téléchargé n'est pas un exécutable Windows valide.")
        if expected and digest.hexdigest().lower() != expected:
            target.unlink(missing_ok=True)
            raise RuntimeError("Somme de contrôle SHA-256 incorrecte : mise à jour annulée.")
        return target

    @staticmethod
    def _launch_swap(current: Path, new: Path) -> None:
        """Script qui attend la fermeture de l'appli, remplace l'exe puis le relance."""
        script = Path(tempfile.gettempdir()) / "kalkid_retro_update.bat"
        script.write_text(
            "@echo off\r\n"
            "set TRIES=0\r\n"
            ":retry\r\n"
            "ping -n 2 127.0.0.1 >nul\r\n"
            f'move /y "{new}" "{current}" >nul 2>&1\r\n'
            "if not errorlevel 1 goto done\r\n"
            "set /a TRIES+=1\r\n"
            "if %TRIES% lss 60 goto retry\r\n"
            "exit /b 1\r\n"
            ":done\r\n"
            f'start "" "{current}"\r\n'
            'del "%~f0"\r\n', encoding="ascii", errors="replace")
        env = {k: v for k, v in os.environ.items() if not k.startswith("_MEI") and not k.startswith("_PYI")}
        env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"   # le nouvel exe doit s'extraire lui-même
        subprocess.Popen(["cmd", "/c", str(script)], env=env, close_fds=True,
                         creationflags=0x08000000 | 0x00000008)   # CREATE_NO_WINDOW | DETACHED_PROCESS
