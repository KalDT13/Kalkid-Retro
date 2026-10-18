"""Génère assets/kalkid.ico à partir de l'icône dessinée par code (utilisé au build)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtGui import QGuiApplication  # noqa: E402

from kalkid_retro.theme import make_icon  # noqa: E402

app = QGuiApplication([])
out = Path(__file__).resolve().parent.parent / "assets"
out.mkdir(exist_ok=True)
pixmap = make_icon(256).pixmap(256, 256)
if not pixmap.save(str(out / "kalkid.ico"), "ICO"):
    raise SystemExit("Impossible d'écrire l'icône")
print("ok:", out / "kalkid.ico")
