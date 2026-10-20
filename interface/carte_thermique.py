"""
Carte thermique personnelle : superpose toutes les traces enregistrées
sur un même repère schématique. Chaque trace est dessinée avec une
faible opacité ; les zones parcourues souvent apparaissent donc plus
"chaudes" par pur effet d'accumulation de la transparence.

Limite assumée : pas de fond de carte réel (rues, relief) —
uniquement la forme géométrique de tes parcours, mise à l'échelle.
"""

from PySide6.QtCore import Qt, QPointF
from PySide6.QtGui import QPainter, QColor, QPen, QPolygonF
from PySide6.QtWidgets import QWidget


PAS_SOUS_ECHANTILLONNAGE = 3


class CarteThermique(QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)
        self.traces = []
        self.setMinimumHeight(500)

    def definir_traces(self, traces):
        self.traces = traces
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor("#0D1013"))

        if not self.traces:
            painter.setPen(QColor("#7F878D"))
            painter.drawText(
                self.rect(), Qt.AlignmentFlag.AlignCenter,
                "Aucune trace à afficher pour cet athlète"
            )
            painter.end()
            return

        marge = 20
        largeur = max(self.width() - 2 * marge, 1)
        hauteur = max(self.height() - 2 * marge, 1)

        lats = [p[0] for trace in self.traces for p in trace]
        lons = [p[1] for trace in self.traces for p in trace]
        lat_min, lat_max = min(lats), max(lats)
        lon_min, lon_max = min(lons), max(lons)

        span_lat = max(lat_max - lat_min, 0.0005)
        span_lon = max(lon_max - lon_min, 0.0005)

        echelle = min(largeur / span_lon, hauteur / span_lat)
        decalage_x = marge + (largeur - span_lon * echelle) / 2
        decalage_y = marge + (hauteur - span_lat * echelle) / 2

        def vers_pixel(lat, lon):
            px = decalage_x + (lon - lon_min) * echelle
            py = decalage_y + (1 - (lat - lat_min) / span_lat) * hauteur
            return QPointF(px, py)

        painter.setPen(QPen(QColor(255, 120, 40, 16), 1.4))
        for trace in self.traces:
            sous_echantillon = trace[::PAS_SOUS_ECHANTILLONNAGE] or trace
            if len(sous_echantillon) < 2:
                continue
            polyligne = QPolygonF([vers_pixel(p[0], p[1]) for p in sous_echantillon])
            painter.drawPolyline(polyligne)

        painter.end()
