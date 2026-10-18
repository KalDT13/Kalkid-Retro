"""Convertit un SVG en PNG transparent : python tools/svg_to_png.py entree.svg sortie.png [taille] [apercu.png]"""

import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QGuiApplication, QImage, QPainter
from PySide6.QtSvg import QSvgRenderer

app = QGuiApplication([])
source, target = sys.argv[1], sys.argv[2]
size = int(sys.argv[3]) if len(sys.argv) > 3 else 512
preview = sys.argv[4] if len(sys.argv) > 4 else None

renderer = QSvgRenderer(source)
print("SVG valide :", renderer.isValid(), renderer.defaultSize())
image = QImage(size, size, QImage.Format.Format_ARGB32)
image.fill(Qt.GlobalColor.transparent)
painter = QPainter(image)
renderer.render(painter)
painter.end()
print("PNG écrit :", image.save(target))

if preview:   # aperçu sur damier pour contrôler la transparence
    board = QImage(size, size, QImage.Format.Format_ARGB32)
    board.fill(QColor("#14161f"))
    painter = QPainter(board)
    step = max(1, int(size / 20))
    for row in range(20):
        for col in range(20):
            if (row + col) % 2:
                painter.fillRect(col * step, row * step, step, step, QColor("#2a2d3a"))
    painter.drawImage(0, 0, image)
    painter.end()
    board.scaled(600, 600, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation).save(preview)
