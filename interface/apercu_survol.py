"""
Aperçu au survol — sans cliquer, laisser la souris un instant sur une
ligne (sortie, résultat de course, parcours) fait apparaître une petite
fenêtre flottante avec le tracé :

  - Option A : un croquis du parcours dessiné instantanément (hors
    ligne, aucune dépendance réseau) ;
  - Option B : la vraie carte (satellite par défaut, plan au choix),
    via le même moteur Leaflet que l'écran Carte réelle, qui vient
    remplacer le croquis dès que les tuiles ont fini de charger.

Un seul widget d'aperçu (et une seule vue web) est créé par fenêtre et
réutilisé à chaque ligne survolée — recréer un QWebEngineView à chaque
survol serait lourd et provoquerait des à-coups.
"""

import json
import tempfile
from pathlib import Path

from PySide6.QtCore import Qt, QEvent, QObject, QTimer, QUrl
from PySide6.QtGui import QPainter, QColor, QPen, QPainterPath, QCursor
from PySide6.QtWidgets import QWidget, QLabel, QVBoxLayout, QStackedLayout, QFrame, QApplication

try:
    from PySide6.QtWebEngineWidgets import QWebEngineView
    from PySide6.QtWebEngineCore import QWebEngineSettings
    _WEBENGINE_DISPONIBLE = True
except ImportError:
    _WEBENGINE_DISPONIBLE = False


DOSSIER_LEAFLET = Path(__file__).parent / "assets" / "leaflet"
CHEMIN_TEMP_HTML = Path(tempfile.gettempdir()) / "trailmaster_apercu_survol.html"

LARGEUR_APERCU = 300
HAUTEUR_CROQUIS = 170
HAUTEUR_CARTE = 210
DELAI_CROQUIS_MS = 120     # avant d'afficher le croquis (évite les à-coups si la souris ne fait que passer)
DELAI_CARTE_MS = 420       # délai additionnel avant de charger la vraie carte (satellite)

GABARIT_HTML_APERCU = """
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8" />
<link rel="stylesheet" href="%s" />
<script src="%s"></script>
<style>
  html, body, #carte { height: 100%%; margin: 0; padding: 0; background: #15191D; }
  .leaflet-control-layers { font-family: sans-serif; font-size: 11px; }
  .leaflet-control-attribution { font-size: 8px; }
</style>
</head>
<body>
<div id="carte"></div>
<script>
  var carte = L.map('carte', {zoomControl: false, attributionControl: false});

  var fondSatellite = L.tileLayer(
      'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
      {maxZoom: 19});
  var fondPlan = L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {maxZoom: 19});

  L.control.layers({"Satellite": fondSatellite, "Plan": fondPlan}, null, {position: 'topright'}).addTo(carte);
  fondSatellite.addTo(carte);

  var trace = %s;
  if (trace.length > 1) {
      L.polyline(trace, {color: '#000000', weight: 4, opacity: 0.5}).addTo(carte);
      L.polyline(trace, {color: '#FF7828', weight: 2.2, opacity: 0.95}).addTo(carte);
      carte.fitBounds(L.latLngBounds(trace), {padding: [12, 12]});
  } else {
      carte.setView([46.6, 2.4], 5);
  }
</script>
</body>
</html>"""


class _CroquisTrace(QWidget):
    """Option A — dessin instantané du tracé (proportions respectées),
    sans aucune dépendance réseau."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.points = []
        self.setMinimumHeight(HAUTEUR_CROQUIS)

    def definir_points(self, points):
        self.points = points or []
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor("#15191D"))

        if len(self.points) < 2:
            painter.setPen(QColor("#6B767D"))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "Pas de tracé enregistré")
            return

        lats = [p[0] for p in self.points]
        lons = [p[1] for p in self.points]
        min_lat, max_lat = min(lats), max(lats)
        min_lon, max_lon = min(lons), max(lons)
        etendue_lat = (max_lat - min_lat) or 0.0001
        etendue_lon = (max_lon - min_lon) or 0.0001

        marge = 14
        largeur = max(self.width() - 2 * marge, 1)
        hauteur = max(self.height() - 2 * marge, 1)

        # Respecte les proportions réelles du tracé (pas d'étirement) :
        # on cale sur la dimension la plus contraignante des deux.
        echelle = min(largeur / etendue_lon, hauteur / etendue_lat)
        decalage_x = marge + (largeur - etendue_lon * echelle) / 2
        decalage_y = marge + (hauteur - etendue_lat * echelle) / 2

        def point_ecran(p):
            x = decalage_x + (p[1] - min_lon) * echelle
            y = decalage_y + (max_lat - p[0]) * echelle
            return x, y

        chemin = QPainterPath()
        x0, y0 = point_ecran(self.points[0])
        chemin.moveTo(x0, y0)
        for p in self.points[1:]:
            x, y = point_ecran(p)
            chemin.lineTo(x, y)

        stylo = QPen(QColor("#FF7828"))
        stylo.setWidthF(2.4)
        stylo.setCapStyle(Qt.PenCapStyle.RoundCap)
        stylo.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(stylo)
        painter.drawPath(chemin)

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#66BB6A"))
        painter.drawEllipse(int(x0) - 3, int(y0) - 3, 6, 6)
        xf, yf = point_ecran(self.points[-1])
        painter.setBrush(QColor("#EF5350"))
        painter.drawEllipse(int(xf) - 3, int(yf) - 3, 6, 6)


class ApercuSurvolTrace(QFrame):
    """Fenêtre flottante d'aperçu — un seul exemplaire créé par écran,
    réutilisé à chaque ligne survolée."""

    def __init__(self, parent=None):
        super().__init__(parent, Qt.WindowType.ToolTip)
        self.setObjectName("apercuSurvolTrace")
        self.setFixedWidth(LARGEUR_APERCU)
        self.setStyleSheet(
            "#apercuSurvolTrace { background-color: #1B2126; border: 1px solid #262E34; "
            "border-radius: 10px; } "
            "QLabel#titreApercu { color: #F3F6F7; font-size: 12.5px; font-weight: 600; "
            "padding: 8px 10px 2px 10px; } "
            "QLabel#sousTitreApercu { color: #9AA7AE; font-size: 11px; padding: 0px 10px 6px 10px; }"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 8)
        layout.setSpacing(0)

        self.titre = QLabel("")
        self.titre.setObjectName("titreApercu")
        self.sous_titre = QLabel("")
        self.sous_titre.setObjectName("sousTitreApercu")
        layout.addWidget(self.titre)
        layout.addWidget(self.sous_titre)

        conteneur_visuel = QWidget()
        self._pile = QStackedLayout(conteneur_visuel)
        self._pile.setContentsMargins(0, 0, 0, 0)

        self.croquis = _CroquisTrace()
        self._pile.addWidget(self.croquis)

        self.vue_web = None
        if _WEBENGINE_DISPONIBLE:
            self.vue_web = QWebEngineView()
            self.vue_web.setFixedHeight(HAUTEUR_CARTE)
            # Page locale (file://) devant charger des tuiles distantes —
            # sans ça QtWebEngine bloque les tuiles par défaut (voir la
            # même remarque dans carte_reelle.py).
            self.vue_web.settings().setAttribute(
                QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True
            )
            self._pile.addWidget(self.vue_web)

        layout.addWidget(conteneur_visuel)

        self._minuteur_croquis = QTimer(self)
        self._minuteur_croquis.setSingleShot(True)
        self._minuteur_croquis.timeout.connect(self._afficher_croquis)

        self._minuteur_carte = QTimer(self)
        self._minuteur_carte.setSingleShot(True)
        self._minuteur_carte.timeout.connect(self._charger_carte)

        self._points_en_attente = None
        self.hide()

    def programmer_affichage(self, nom, sous_texte, points, position_globale):
        """Annule tout affichage en cours et programme celui-ci — le
        croquis apparaît après DELAI_CROQUIS_MS, la vraie carte
        DELAI_CARTE_MS plus tard, seulement si la souris n'a pas
        entre-temps changé de ligne."""

        self._minuteur_croquis.stop()
        self._minuteur_carte.stop()

        self.titre.setText(nom or "(sans nom)")
        self.sous_titre.setText(sous_texte or "")
        self._points_en_attente = points
        self._deplacer_pres_du_curseur(position_globale)

        self._pile.setCurrentWidget(self.croquis)
        self._minuteur_croquis.start(DELAI_CROQUIS_MS)

    def masquer(self):
        self._minuteur_croquis.stop()
        self._minuteur_carte.stop()
        self.hide()

    def _deplacer_pres_du_curseur(self, position_globale):
        x = position_globale.x() + 18
        y = position_globale.y() + 18

        ecran = QApplication.screenAt(position_globale)
        if ecran is not None:
            zone = ecran.availableGeometry()
            hauteur_totale = self.sizeHint().height() or (HAUTEUR_CROQUIS + 60)
            if x + LARGEUR_APERCU > zone.right():
                x = position_globale.x() - LARGEUR_APERCU - 18
            if y + hauteur_totale > zone.bottom():
                y = position_globale.y() - hauteur_totale - 18

        self.move(x, y)

    def _afficher_croquis(self):
        if self._points_en_attente is None:
            return
        self.croquis.definir_points(self._points_en_attente)
        self._pile.setCurrentWidget(self.croquis)
        self.show()
        self.raise_()

        if self._points_en_attente and _WEBENGINE_DISPONIBLE:
            self._minuteur_carte.start(DELAI_CARTE_MS)

    def _charger_carte(self):
        if not self._points_en_attente or self.vue_web is None or not self.isVisible():
            return
        if not DOSSIER_LEAFLET.exists():
            return  # pas de bascule vers la carte — le croquis reste affiché

        chemin_css = (DOSSIER_LEAFLET / "leaflet.css").as_uri()
        chemin_js = (DOSSIER_LEAFLET / "leaflet.js").as_uri()
        html = GABARIT_HTML_APERCU % (chemin_css, chemin_js, json.dumps(self._points_en_attente))

        try:
            CHEMIN_TEMP_HTML.write_text(html, encoding="utf-8")
        except OSError:
            return

        try:
            self.vue_web.loadFinished.disconnect()
        except (RuntimeError, TypeError):
            pass
        self.vue_web.loadFinished.connect(self._sur_carte_chargee)
        self.vue_web.load(QUrl.fromLocalFile(str(CHEMIN_TEMP_HTML)))

    def _sur_carte_chargee(self, succes):
        if succes and self.isVisible():
            self._pile.setCurrentWidget(self.vue_web)


class GestionnaireApercuSurvol(QObject):
    """Installe le survol sur une QTableWidget : détermine quel id de
    ligne est survolé, et délègue l'affichage à un ApercuSurvolTrace
    partagé. `obtenir_id_ligne(ligne) -> id | None` et
    `obtenir_apercu(id) -> (nom, sous_texte, points) | None` sont
    fournis par l'écran appelant, qui connaît son propre schéma."""

    def __init__(self, table, obtenir_id_ligne, obtenir_apercu):
        super().__init__(table)
        self.table = table
        self.obtenir_id_ligne = obtenir_id_ligne
        self.obtenir_apercu = obtenir_apercu
        self.popup = ApercuSurvolTrace(table.window())

        self._ligne_survolee = None
        self._id_survole = None

        table.setMouseTracking(True)
        table.viewport().setMouseTracking(True)
        table.viewport().installEventFilter(self)

    def eventFilter(self, objet, event):
        if event.type() == QEvent.Type.MouseMove:
            self._sur_deplacement(event)
        elif event.type() in (QEvent.Type.Leave, QEvent.Type.FocusOut):
            self._sur_sortie()
        return False

    def _sur_deplacement(self, event):
        pos = event.position().toPoint() if hasattr(event, "position") else event.pos()
        ligne = self.table.rowAt(pos.y())

        if ligne == self._ligne_survolee:
            if ligne != -1:
                self.popup._deplacer_pres_du_curseur(QCursor.pos())
            return

        self._ligne_survolee = ligne
        if ligne == -1:
            self._sur_sortie()
            return

        id_ligne = self.obtenir_id_ligne(ligne)
        if id_ligne is None or id_ligne == self._id_survole and self.popup.isVisible():
            return
        self._id_survole = id_ligne

        resultat = self.obtenir_apercu(id_ligne)
        if resultat is None:
            self.popup.masquer()
            return

        nom, sous_texte, points = resultat
        self.popup.programmer_affichage(nom, sous_texte, points, QCursor.pos())

    def _sur_sortie(self):
        self._ligne_survolee = None
        self._id_survole = None
        self.popup.masquer()


def installer_apercu_survol(table, obtenir_id_ligne, obtenir_apercu):
    """Point d'entrée pratique : crée et retourne le gestionnaire
    (à garder en vie via un attribut d'instance, ex. self._apercu =
    installer_apercu_survol(...), sinon il serait détruit par le
    ramasse-miettes Python et le survol cesserait de fonctionner)."""

    return GestionnaireApercuSurvol(table, obtenir_id_ligne, obtenir_apercu)
