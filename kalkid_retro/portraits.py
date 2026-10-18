"""Portraits des personnages (icônes de classes) : fournis avec l'application, ou image personnalisée.

Les portraits de classes (assets/portraits/<classe>_<m|f>.png) sont embarqués dans l'exe. Les images
personnalisées choisies par l'utilisateur sont copiées dans %APPDATA%\\KalkidRetro\\portraits.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPixmap

from .config import CONFIG_DIR

CUSTOM_DIR = CONFIG_DIR / "portraits"
BUNDLED_DIR = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent)) / "assets" / "portraits"

CLASSES = [("feca", "Féca"), ("osamodas", "Osamodas"), ("enutrof", "Enutrof"), ("sram", "Sram"),
           ("xelor", "Xélor"), ("ecaflip", "Ecaflip"), ("eniripsa", "Eniripsa"), ("iop", "Iop"),
           ("cra", "Crâ"), ("sadida", "Sadida"), ("sacrieur", "Sacrieur"), ("pandawa", "Pandawa")]
GENDERS = [("m", "homme"), ("f", "femme")]

KNOWN_KEYS = [f"{c}_{g}" for c, _ in CLASSES for g, _ in GENDERS]
LABELS = {f"{c}_{g}": f"{cname} ({gname})" for c, cname in CLASSES for g, gname in GENDERS}

_cache: dict[tuple[str, int], QPixmap] = {}


def _path_for(key: str) -> Path | None:
    if not key or not re.fullmatch(r"[A-Za-z0-9_-]+", key):
        return None
    for folder in (CUSTOM_DIR, BUNDLED_DIR):
        path = folder / f"{key}.png"
        if path.is_file():
            return path
    return None


def available_keys() -> list[str]:
    """Portraits de classes disponibles, dans l'ordre classe puis genre."""
    return [k for k in KNOWN_KEYS if _path_for(k) is not None]


def _safe(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]", "_", name)


def set_custom(pseudo: str, source: str | Path) -> str | None:
    """Image personnalisée pour un personnage : copiée (redimensionnée) dans le dossier utilisateur."""
    img = QImage(str(source))
    if img.isNull():
        return None
    key = f"custom_{_safe(pseudo)}"
    CUSTOM_DIR.mkdir(parents=True, exist_ok=True)
    img = img.scaled(256, 256, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
    if not img.save(str(CUSTOM_DIR / f"{key}.png"), "PNG"):
        return None
    for cached in [k for k in _cache if k[0] == key]:
        _cache.pop(cached, None)
    return key


def pixmap(key: str | None, size: int) -> QPixmap | None:
    """Portrait mis à l'échelle (mis en cache), ou None si absent."""
    path = _path_for(key or "")
    if path is None:
        return None
    cached = _cache.get((key, size))
    if cached is not None:
        return cached
    pix = QPixmap(str(path))
    if pix.isNull():
        return None
    pix = pix.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
    _cache[(key, size)] = pix
    return pix
