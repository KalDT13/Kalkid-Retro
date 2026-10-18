"""Diagnostic rapide : python tools/check_notifs.py

Affiche l'état de l'accès aux notifications et le mode de lecture, puis écoute 10 secondes les
notifications de Dofus (déclenche-en une en jeu pour tester l'autofocus).
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from kalkid_retro.notifs import NotificationWatcher  # noqa: E402

watcher = NotificationWatcher(
    lambda n: print(f"  notification : [{n.event or '?'}] {n.pseudo} : {n.body}"),
    lambda level, msg: print(f"  {level}: {msg}"),
)
watcher.start()
time.sleep(10)
print("accès accordé :", watcher.access_ok, "| mode événementiel :", watcher.event_driven,
      "| notifications lues :", watcher.read_count)
start = time.time()
watcher.stop()
watcher._thread.join(3)
print(f"arrêt propre en {time.time() - start:.2f} s")
