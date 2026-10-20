"""
Widget de visualisation d'une trace GPX : tracé schématique (vue du
dessus, sans tuiles de carte externes) + profil altimétrique, dessinés
directement avec QPainter.
"""

from PySide6.QtCore import Qt, QPointF, QRectF, Signal
from PySide6.QtGui import QPainter, QPen, QBrush, QColor, QPolygonF
from PySide6.QtWidgets import QWidget

from interface.survol_graphique import dessiner_infobulle


class TraceCanvas(QWidget):

    marqueur_clique = Signal(int)      # indice du marqueur (photo) cliqué

    def __init__(self, parent=None):
        super().__init__(parent)
        self.marqueurs = []           # [(lat, lon, texte)] — ex. photos de la sortie
        self._marqueurs_px = []       # [(QPointF, indice)] mémorisés au dessin
        self.points = []      # liste de (lat, lon)
        self.altitudes = []   # liste de float, même longueur que points
        self.setMinimumHeight(320)
        self.setMouseTracking(True)
        self._survol = None        # indice du point survolé sur le profil
        self._zone_profil = None   # (x, y, w, h) du profil, mémorisée au dessin

    def definir_trace(self, points, altitudes):
        self.points = points
        self.altitudes = altitudes
        self._survol = None
        self._distances = None
        self.update()

    def definir_marqueurs(self, marqueurs):
        """marqueurs : liste de (lat, lon, texte) affichés en pastilles numérotées."""
        self.marqueurs = list(marqueurs)
        self.update()

    def _marqueur_sous(self, pos):
        for point, i in self._marqueurs_px:
            if (point.x() - pos.x()) ** 2 + (point.y() - pos.y()) ** 2 <= 13 ** 2:
                return i
        return None

    def mousePressEvent(self, event):
        i = self._marqueur_sous(event.position())
        if i is not None:
            self.marqueur_clique.emit(i)

    def _distances_cumulees(self):
        """Distance cumulée (km) à chaque point, calculée une fois."""
        if getattr(self, "_distances", None) is None:
            from interface.gpx_utils import _distance_haversine_km
            cumul, d = [0.0], 0.0
            for a, b in zip(self.points, self.points[1:]):
                d += _distance_haversine_km(a[0], a[1], b[0], b[1])
                cumul.append(d)
            self._distances = cumul
        return self._distances

    def mouseMoveEvent(self, event):
        i_marq = self._marqueur_sous(event.position())
        self.setCursor(Qt.CursorShape.PointingHandCursor if i_marq is not None
                       else Qt.CursorShape.ArrowCursor)
        if i_marq is not None:
            self.setToolTip(self.marqueurs[i_marq][2] if i_marq < len(self.marqueurs) else "")
        else:
            self.setToolTip("")
        z = self._zone_profil
        n = len(self.altitudes)
        if not z or n < 2:
            return
        x, y, w, h = z
        pos = event.position()
        if not (y <= pos.y() <= y + h):
            if self._survol is not None:
                self._survol = None
                self.update()
            return
        i = round((pos.x() - (x + 20)) / max(w - 40, 1) * (n - 1))
        i = max(0, min(n - 1, i))
        if i != self._survol:
            self._survol = i
            self.update()

    def leaveEvent(self, event):
        if self._survol is not None:
            self._survol = None
            self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        painter.fillRect(self.rect(), QColor("#15191D"))

        if not self.points:
            painter.setPen(QColor("#7F878D"))
            painter.drawText(
                self.rect(),
                Qt.AlignmentFlag.AlignCenter,
                "Importez un fichier GPX pour visualiser le tracé",
            )
            painter.end()
            return

        largeur = self.width()
        hauteur = self.height()

        zone_trace_h = int(hauteur * 0.6)
        zone_profil_h = hauteur - zone_trace_h - 12

        self._dessiner_trace(painter, 0, 0, largeur, zone_trace_h)
        self._dessiner_profil(painter, 0, zone_trace_h + 12, largeur, zone_profil_h)

        painter.end()

    # ------------------------------------------------------------
    def _dessiner_trace(self, painter, x, y, w, h):
        marge = 20

        lats = [p[0] for p in self.points]
        lons = [p[1] for p in self.points]
        lat_min, lat_max = min(lats), max(lats)
        lon_min, lon_max = min(lons), max(lons)

        # Évite une division par zéro sur un tracé quasi ponctuel (peu de points)
        span_lat = max(lat_max - lat_min, 0.0001)
        span_lon = max(lon_max - lon_min, 0.0001)

        def vers_pixel(lat, lon):
            px = x + marge + (lon - lon_min) / span_lon * (w - 2 * marge)
            # La latitude augmente vers le nord, l'axe Y de l'écran vers
            # le bas : on inverse pour orienter le tracé correctement.
            py = y + marge + (1 - (lat - lat_min) / span_lat) * (h - 2 * marge)
            return QPointF(px, py)

        polygone = QPolygonF([vers_pixel(p[0], p[1]) for p in self.points])

        painter.setPen(QPen(QColor("#2E7D32"), 3))
        painter.drawPolyline(polygone)

        if len(polygone) > 0:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(QColor("#43A047")))
            painter.drawEllipse(polygone.first(), 5, 5)
            painter.setBrush(QBrush(QColor("#D32F2F")))
            painter.drawEllipse(polygone.last(), 5, 5)

        # Photos : pastilles orange numérotées, cliquables
        self._marqueurs_px = []
        for i, (lat, lon, _texte) in enumerate(self.marqueurs):
            centre = vers_pixel(lat, lon)
            # Une photo prise hors du tracé reste visible, au bord de la carte
            centre = QPointF(min(max(centre.x(), x + 12), x + w - 12),
                             min(max(centre.y(), y + 12), y + h - 12))
            self._marqueurs_px.append((centre, i))
            painter.setPen(QPen(QColor("#FFFFFF"), 2))
            painter.setBrush(QBrush(QColor("#FB8C00")))
            painter.drawEllipse(centre, 10, 10)
            painter.setPen(QColor("#FFFFFF"))
            painter.drawText(QRectF(centre.x() - 10, centre.y() - 10, 20, 20),
                             Qt.AlignmentFlag.AlignCenter, str(i + 1))

    def _dessiner_profil(self, painter, x, y, w, h):
        if not self.altitudes or h <= 0:
            return

        marge = 20
        alt_min, alt_max = min(self.altitudes), max(self.altitudes)
        span_alt = max(alt_max - alt_min, 1)
        n = len(self.altitudes)

        def vers_pixel(i, altitude):
            px = x + marge + (i / max(n - 1, 1)) * (w - 2 * marge)
            py = y + h - marge - (altitude - alt_min) / span_alt * (h - 2 * marge)
            return QPointF(px, py)

        ligne_points = [vers_pixel(i, alt) for i, alt in enumerate(self.altitudes)]

        zone_points = (
            [QPointF(x + marge, y + h - marge)]
            + ligne_points
            + [QPointF(x + w - marge, y + h - marge)]
        )

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor(46, 125, 50, 90)))
        painter.drawPolygon(QPolygonF(zone_points))

        painter.setPen(QPen(QColor("#43A047"), 2))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPolyline(QPolygonF(ligne_points))

        painter.setPen(QColor("#7F878D"))
        painter.drawText(x + marge, y + 14, f"{round(alt_max)} m")
        painter.drawText(x + marge, y + h - 6, f"{round(alt_min)} m")

        self._zone_profil = (x, y, w, h)

        # Info-bulle au survol du profil : altitude, distance, pente locale
        i = self._survol
        if i is not None and i < n:
            point = vers_pixel(i, self.altitudes[i])
            painter.setPen(QPen(QColor("#6B737A"), 1, Qt.PenStyle.DashLine))
            painter.drawLine(int(point.x()), int(y + marge), int(point.x()), int(y + h - marge))
            painter.setPen(QPen(QColor("#15191D"), 2))
            painter.setBrush(QColor("#43A047"))
            painter.drawEllipse(point, 4.5, 4.5)
            distances = self._distances_cumulees()
            lignes = [("#43A047", f"Altitude : {round(self.altitudes[i])} m")]
            if i < len(distances):
                lignes.append((None, f"Distance : {distances[i]:.2f} km"))
                j0, j1 = max(i - 5, 0), min(i + 5, n - 1)
                dkm = distances[j1] - distances[j0]
                if dkm > 0.02:
                    pente = (self.altitudes[j1] - self.altitudes[j0]) / (dkm * 1000) * 100
                    lignes.append((None, f"Pente : {pente:+.0f} %"))
            dessiner_infobulle(painter, QRectF(self.rect()), point.x(), point.y(), "Profil", lignes)
