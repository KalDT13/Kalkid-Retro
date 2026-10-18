"""Configuration persistante (JSON dans %APPDATA%\\KalkidRetro)."""

from __future__ import annotations

import copy
import json
import os
import threading
from pathlib import Path

CONFIG_DIR = Path(os.environ.get("APPDATA", str(Path.home()))) / "KalkidRetro"
CONFIG_PATH = CONFIG_DIR / "config.json"

# Événements d'autofocus reconnus (clé -> libellé)
EVENTS = {
    "combat": "Combat",
    "mp": "Message privé",
    "groupe": "Groupe / Guilde",
    "echange": "Échange",
}

DEFAULTS: dict = {
    "order": [],            # pseudos, dans l'ordre de cycle
    "main": "",             # personnage principal
    "excluded": [],         # exclus des raccourcis / outils
    "portraits": {},        # pseudo -> clé de portrait ("iop_m", "custom_Pseudo"…)
    "autofocus": {
        "enabled": True,
        "debug": False,
        "events": {},       # pseudo -> liste d'événements actifs
    },
    "hotkeys": {
        "next": "Tab",
        "prev": "Shift+Tab",
        "main": "",
        "click_all": "F1",
        "capture_chat": "F8",
        "invite": "F9",
    },
    "hotkeys_only_in_game": True,
    "tools": {
        "clicks_enabled": False,    # désactivé par défaut (voir README)
        "wheel": True,
        "delay_min": 90,
        "delay_max": 130,
        "no_flash": True,
        "invite_enabled": False,    # désactivé par défaut (voir README)
        "leader": "",
        "chat_x": -1,
        "chat_y": -1,
        "invite_wait": 200,
        "invite_pause": 50,
    },
    "presets": {},          # nom -> {"order": [...], "main": "", "excluded": [], "events": {...}}
    "settings": {
        "close_to_tray": True,
        "start_hidden": False,
        "warning_ack": False,
    },
}


def _merge(base: dict, new: dict) -> dict:
    """Fusionne `new` dans `base` (récursif) sans perdre les clés par défaut."""
    out = copy.deepcopy(base)
    for key, value in new.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict) and key not in ("events", "presets"):
            out[key] = _merge(out[key], value)
        else:
            out[key] = value
    return out


class Config:
    def __init__(self, path: Path = CONFIG_PATH):
        self.path = path
        self._lock = threading.RLock()
        self.data: dict = copy.deepcopy(DEFAULTS)
        self.load()

    def load(self) -> None:
        with self._lock:
            try:
                with open(self.path, "r", encoding="utf-8") as fh:
                    self.data = _merge(DEFAULTS, json.load(fh))
            except FileNotFoundError:
                self.data = copy.deepcopy(DEFAULTS)
            except (json.JSONDecodeError, OSError):
                # fichier corrompu : on le garde de côté et on repart des valeurs par défaut
                try:
                    self.path.replace(self.path.with_suffix(".json.bak"))
                except OSError:
                    pass
                self.data = copy.deepcopy(DEFAULTS)

    def save(self) -> None:
        with self._lock:
            try:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                tmp = self.path.with_suffix(".tmp")
                with open(tmp, "w", encoding="utf-8") as fh:
                    json.dump(self.data, fh, ensure_ascii=False, indent=2)
                tmp.replace(self.path)
            except OSError:
                pass

    # accès pratiques ---------------------------------------------------------
    def get(self, *keys, default=None):
        with self._lock:
            node = self.data
            for key in keys:
                if not isinstance(node, dict) or key not in node:
                    return default
                node = node[key]
            return node

    def set(self, *args) -> None:
        """set("tools", "delay_min", 150) : dernier argument = valeur."""
        *keys, value = args
        with self._lock:
            node = self.data
            for key in keys[:-1]:
                node = node.setdefault(key, {})
            node[keys[-1]] = value
        self.save()
