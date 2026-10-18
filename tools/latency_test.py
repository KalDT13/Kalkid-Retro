"""Mesure le délai entre l'arrivée d'une notification Windows et sa détection par Kalkid Rétro.

Envoie une notification de test (qui apparaît brièvement à l'écran) et chronomètre la détection.
Usage : python tools/latency_test.py
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from winsdk.windows.data.xml.dom import XmlDocument  # noqa: E402
from winsdk.windows.ui.notifications import ToastNotification, ToastNotificationManager  # noqa: E402

from kalkid_retro.notifs import NotificationWatcher  # noqa: E402

AUMID = "com.dofus.d1elauncher"   # identifiant de l'application Dofus connue de Windows
received: list[tuple[float, object]] = []

watcher = NotificationWatcher(lambda n: received.append((time.perf_counter(), n)),
                              lambda level, msg: print(f"  [{level}] {msg}"))
watcher.start()
time.sleep(3)   # le temps que la surveillance démarre

delays = []
for i in range(5):
    received.clear()
    xml = XmlDocument()
    xml.load_xml(f"<toast><visual><binding template='ToastGeneric'><text>TestKalkid{i}</text>"
                 f"<text>Test : c'est à toi de jouer</text></binding></visual></toast>")
    toast = ToastNotification(xml)
    t0 = time.perf_counter()
    ToastNotificationManager.create_toast_notifier(AUMID).show(toast)
    deadline = time.time() + 4
    while not received and time.time() < deadline:
        time.sleep(0.002)
    if received:
        delays.append((received[0][0] - t0) * 1000)
        print(f"essai {i + 1} : détecté en {delays[-1]:.0f} ms ({received[0][1].event})")
    else:
        print(f"essai {i + 1} : non détecté en 4 s")
    time.sleep(1.5)

watcher.stop()
if delays:
    print(f"moyenne : {sum(delays) / len(delays):.0f} ms · pire cas : {max(delays):.0f} ms")
