"""
Création d'un parcours en cliquant des points sur une vraie carte — le
tracé "colle" aux sentiers/chemins réels entre chaque point cliqué
(comme Openrunner ou Footpath), via le service public gratuit OSRM
(profil piéton).

Deux services publics gratuits sont utilisés, en plus des tuiles
OpenStreetMap déjà utilisées par Carte réelle :
  - OSRM (router.project-osrm.org) pour le calcul d'itinéraire piéton.
    C'est un service "best effort", sans garantie de disponibilité —
    en cas d'échec, le tracé retombe automatiquement sur une ligne
    droite entre les deux points plutôt que de bloquer.
  - Open-Elevation pour le profil altimétrique (le tracé dessiné n'a
    pas d'altitude native, contrairement à une trace GPS enregistrée).

Nécessite une connexion internet à chaque utilisation, comme Carte
réelle et Météo.
"""

import json
import tempfile
from pathlib import Path

from PySide6.QtCore import QUrl, QTimer
from PySide6.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QComboBox,
    QPushButton,
    QFrame,
    QLineEdit,
    QMessageBox,
    QFileDialog,
)
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebEngineCore import QWebEngineSettings

from data.database import connexion, creer_base_de_donnees, obtenir_athletes
from interface.ecran_liste import obtenir_style_ecran
from interface.elevation import obtenir_altitudes
from interface.export_gpx import exporter_gpx


DOSSIER_LEAFLET = Path(__file__).parent / "assets" / "leaflet"
CHEMIN_TEMP_HTML = Path(tempfile.gettempdir()) / "trailmaster_createur_parcours.html"

GABARIT_HTML = """
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8" />
<link rel="stylesheet" href="%s" />
<script src="%s"></script>
<style>
  html, body, #carte { height: 100%%; margin: 0; padding: 0; background: #15191D; }
  #infoDistance {
      position: absolute; top: 10px; right: 10px; z-index: 1000;
      background: rgba(20,24,28,0.9); color: white; padding: 8px 14px;
      border-radius: 8px; font-family: sans-serif; font-size: 14px;
  }
</style>
</head>
<body>
<div id="carte"></div>
<div id="infoDistance">0.00 km — clique sur la carte pour commencer</div>
<script>
  var carte = L.map('carte').setView([46.6, 2.4], 6);

  // Mêmes fonds de carte au choix que l'écran Carte réelle (Plan /
  // Satellite / Relief / Hybride) — gratuits, sans clé d'API.
  var fondPlan = L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
      attribution: '&copy; OpenStreetMap contributors, itinéraire par OSRM',
      maxZoom: 19
  });
  var fondSatellite = L.tileLayer(
      'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', {
      attribution: 'Imagerie &copy; Esri, Maxar, Earthstar Geographics',
      maxZoom: 19
  });
  var fondRelief = L.tileLayer('https://tile.opentopomap.org/{z}/{x}/{y}.png', {
      attribution: '&copy; OpenStreetMap contributors, SRTM | &copy; OpenTopoMap (CC-BY-SA)',
      maxZoom: 17
  });
  var etiquettesSatellite = L.tileLayer(
      'https://server.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}', {
      attribution: 'Esri',
      maxZoom: 19,
      pane: 'shadowPane'
  });
  var fondHybride = L.layerGroup([fondSatellite, etiquettesSatellite]);

  var fondsDisponibles = {
      "Plan": fondPlan,
      "Satellite": fondSatellite,
      "Relief": fondRelief,
      "Hybride (satellite + noms)": fondHybride
  };

  var dernierFond = null;
  try { dernierFond = localStorage.getItem('trailmaster_fond_carte'); } catch (e) {}
  (fondsDisponibles[dernierFond] || fondPlan).addTo(carte);

  L.control.layers(fondsDisponibles, null, {position: 'topright'}).addTo(carte);
  carte.on('baselayerchange', function (e) {
      try { localStorage.setItem('trailmaster_fond_carte', e.name); } catch (err) {}
  });

  L.control.scale({imperial: false, position: 'bottomleft'}).addTo(carte);

  var waypoints = [];
  var segments = [];
  var distanceKm = 0;
  var couche = L.layerGroup().addTo(carte);
  var enCalcul = false;

  function distanceHaversine(a, b) {
      var R = 6371;
      var dLat = (b[0]-a[0]) * Math.PI/180;
      var dLon = (b[1]-a[1]) * Math.PI/180;
      var x = Math.sin(dLat/2)*Math.sin(dLat/2) +
              Math.cos(a[0]*Math.PI/180)*Math.cos(b[0]*Math.PI/180)*
              Math.sin(dLon/2)*Math.sin(dLon/2);
      return R * 2 * Math.atan2(Math.sqrt(x), Math.sqrt(1-x));
  }

  function majAffichage(messageExtra) {
      document.getElementById('infoDistance').innerText =
          distanceKm.toFixed(2) + ' km' + (messageExtra ? ' — ' + messageExtra : '');
  }

  function tracerLigneDroite(depart, arrivee) {
      L.polyline([depart, arrivee], {color: '#FF7828', weight: 4, dashArray: '6,6'}).addTo(couche);
      var d = distanceHaversine(depart, arrivee);
      segments.push({points: [depart, arrivee], distance: d});
      distanceKm += d;
  }

  carte.on('click', function(e) {
      if (enCalcul) return;
      var point = [e.latlng.lat, e.latlng.lng];
      L.circleMarker(point, {radius: 5, color: '#FF7828', fillColor: '#FF7828', fillOpacity: 1}).addTo(couche);

      if (waypoints.length > 0) {
          var depart = waypoints[waypoints.length - 1];
          enCalcul = true;
          majAffichage('calcul de l\\'itinéraire...');

          var url = 'https://router.project-osrm.org/route/v1/foot/' +
              depart[1] + ',' + depart[0] + ';' + point[1] + ',' + point[0] +
              '?overview=full&geometries=geojson';

          fetch(url).then(function(r) { return r.json(); }).then(function(data) {
              if (data.code === 'Ok' && data.routes && data.routes.length > 0) {
                  var coords = data.routes[0].geometry.coordinates.map(function(c) { return [c[1], c[0]]; });
                  L.polyline(coords, {color: '#FF7828', weight: 4}).addTo(couche);
                  var d = data.routes[0].distance / 1000;
                  segments.push({points: coords, distance: d});
                  distanceKm += d;
                  majAffichage();
              } else {
                  tracerLigneDroite(depart, point);
                  majAffichage('service de routage indisponible, ligne droite utilisée');
              }
              enCalcul = false;
          }).catch(function() {
              tracerLigneDroite(depart, point);
              majAffichage('pas de connexion au service de routage, ligne droite utilisée');
              enCalcul = false;
          });
      }

      waypoints.push(point);
  });

  function toutEffacer() {
      waypoints = [];
      segments = [];
      distanceKm = 0;
      couche.clearLayers();
      majAffichage('clique sur la carte pour commencer');
  }

  function annulerDernierPoint() {
      if (waypoints.length === 0) return;
      waypoints.pop();
      if (segments.length > 0) {
          var dernier = segments.pop();
          distanceKm -= dernier.distance;
      }
      couche.clearLayers();
      waypoints.forEach(function(p) {
          L.circleMarker(p, {radius: 5, color: '#FF7828', fillColor: '#FF7828', fillOpacity: 1}).addTo(couche);
      });
      segments.forEach(function(s) {
          L.polyline(s.points, {color: '#FF7828', weight: 4}).addTo(couche);
      });
      majAffichage();
  }

  function obtenirTousLesPoints() {
      var tous = [];
      segments.forEach(function(s) {
          s.points.forEach(function(p) { tous.push(p); });
      });
      return JSON.stringify(tous);
  }

  function obtenirDistanceKm() {
      return distanceKm;
  }

  function forcerRedimensionnement() {
      // Nécessaire quand cette carte s'affiche dans un onglet ouvert par
      // défaut (avant que la fenêtre ait sa taille finale à l'écran) :
      // Leaflet calcule alors la grille de tuiles sur une taille de
      // conteneur incorrecte (souvent 0x0) et n'affiche aucune tuile,
      // même si les points/clics fonctionnent normalement (fond noir).
      // On force Leaflet à recalculer une fois la fenêtre réellement
      // affichée et dimensionnée.
      if (typeof carte !== 'undefined') {
          carte.invalidateSize();
      }
  }
</script>
</body>
</html>"""


class CreateurParcours(QMainWindow):

    def __init__(self, athlete_id_initial=None):
        super().__init__()

        creer_base_de_donnees()

        self.setWindowTitle("TrailMaster Pro – Créer un parcours")
        self.resize(1350, 900)
        self.setMinimumSize(1050, 700)

        central = QWidget()
        self.setCentralWidget(central)

        principal = QVBoxLayout(central)
        principal.setContentsMargins(25, 20, 25, 15)
        principal.setSpacing(12)

        titre = QLabel("🖊️  Créer un parcours")
        titre.setObjectName("titrePage")
        sous_titre = QLabel(
            "Clique sur la carte pour poser des points — le tracé suit automatiquement "
            "les sentiers réels entre chaque point (comme Openrunner). Nécessite internet."
        )
        sous_titre.setObjectName("sousTitrePage")
        principal.addWidget(titre)
        principal.addWidget(sous_titre)

        barre = QHBoxLayout()
        label_athlete = QLabel("Athlète :")
        label_athlete.setObjectName("labelChamp")
        self.combo_athlete = QComboBox()
        self.athletes = obtenir_athletes()
        self.combo_athlete.addItem("Sélectionner...", None)
        for a in self.athletes:
            self.combo_athlete.addItem(f"{a[2]} {a[1]}", a[0])

        self.champ_nom = QLineEdit()
        self.champ_nom.setPlaceholderText("Nom du parcours")

        barre.addWidget(label_athlete)
        barre.addWidget(self.combo_athlete)
        barre.addWidget(self.champ_nom, 1)
        principal.addLayout(barre)

        barre_actions = QHBoxLayout()
        bouton_annuler_point = QPushButton("↩️ Annuler le dernier point")
        bouton_annuler_point.setObjectName("boutonSecondaire")
        bouton_annuler_point.clicked.connect(self.annuler_dernier_point)

        bouton_effacer = QPushButton("🗑️ Tout effacer")
        bouton_effacer.setObjectName("boutonSecondaire")
        bouton_effacer.clicked.connect(self.tout_effacer)

        bouton_enregistrer = QPushButton("💾 Enregistrer ce parcours")
        bouton_enregistrer.setObjectName("boutonPrincipal")
        bouton_enregistrer.clicked.connect(self.enregistrer_parcours)

        bouton_exporter = QPushButton("⬇️ Exporter en GPX")
        bouton_exporter.setObjectName("boutonSecondaire")
        bouton_exporter.clicked.connect(self.exporter_parcours)

        barre_actions.addWidget(bouton_annuler_point)
        barre_actions.addWidget(bouton_effacer)
        barre_actions.addStretch()
        barre_actions.addWidget(bouton_exporter)
        barre_actions.addWidget(bouton_enregistrer)
        principal.addLayout(barre_actions)

        cadre_carte = QFrame()
        cadre_carte.setObjectName("carteForm")
        carte_layout = QVBoxLayout(cadre_carte)
        self.vue_web = QWebEngineView()
        self.vue_web.setMinimumHeight(500)
        # Page locale (file://) devant charger des tuiles distantes et
        # appeler OSRM/Open-Elevation en JS — sans ça QtWebEngine bloque
        # tout accès réseau distant par défaut (voir la même remarque
        # dans carte_reelle.py).
        self.vue_web.settings().setAttribute(
            QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True
        )
        carte_layout.addWidget(self.vue_web)
        principal.addWidget(cadre_carte, 1)

        self.label_statut = QLabel("")
        self.label_statut.setObjectName("texteSecondaire")
        self.label_statut.setWordWrap(True)
        principal.addWidget(self.label_statut)

        self.setStyleSheet(obtenir_style_ecran())

        if athlete_id_initial is not None:
            for i in range(self.combo_athlete.count()):
                if self.combo_athlete.itemData(i) == athlete_id_initial:
                    self.combo_athlete.setCurrentIndex(i)
                    break

        self.vue_web.loadFinished.connect(self._verifier_chargement)
        self._charger_carte()

    def _charger_carte(self):
        chemin_css = (DOSSIER_LEAFLET / "leaflet.css").as_uri()
        chemin_js = (DOSSIER_LEAFLET / "leaflet.js").as_uri()
        html = GABARIT_HTML % (chemin_css, chemin_js)

        try:
            CHEMIN_TEMP_HTML.write_text(html, encoding="utf-8")
        except OSError as erreur:
            self.label_statut.setText(f"⚠️ Impossible d'écrire le fichier de carte : {erreur}")
            return

        self.vue_web.load(QUrl.fromLocalFile(str(CHEMIN_TEMP_HTML)))

    def _verifier_chargement(self, succes):
        if not succes:
            self.label_statut.setText(
                "⚠️ Le composant carte n'a pas réussi à charger la page. "
                "Vérifie ta connexion internet, ou signale ce message si le problème persiste."
            )
            return
        # Cet écran est souvent le tout premier onglet affiché (donc chargé
        # avant que la fenêtre n'ait sa taille définitive à l'écran) : on
        # force un recalcul de la grille de tuiles une fois la page prête,
        # puis une nouvelle fois un peu plus tard pour couvrir le cas où la
        # fenêtre est encore redimensionnée par Qt juste après l'ouverture.
        self._forcer_redimensionnement_carte()
        QTimer.singleShot(300, self._forcer_redimensionnement_carte)

    def _forcer_redimensionnement_carte(self):
        # Peut être appelé avant que la page soit chargée (showEvent /
        # resizeEvent déclenchés très tôt) : on protège l'appel pour ne
        # pas polluer la console si la fonction JS n'existe pas encore.
        self.vue_web.page().runJavaScript(
            "if (typeof forcerRedimensionnement === 'function') { forcerRedimensionnement(); }"
        )

    def showEvent(self, event):
        super().showEvent(event)
        self._forcer_redimensionnement_carte()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._forcer_redimensionnement_carte()

    def annuler_dernier_point(self):
        self.vue_web.page().runJavaScript("annulerDernierPoint();")

    def tout_effacer(self):
        self.vue_web.page().runJavaScript("toutEffacer();")

    def _recuperer_points(self, callback):
        self.vue_web.page().runJavaScript("obtenirTousLesPoints();", callback)

    def enregistrer_parcours(self):
        athlete_id = self.combo_athlete.currentData()
        nom = self.champ_nom.text().strip()

        if athlete_id is None:
            QMessageBox.warning(self, "Athlète requis", "Sélectionne un athlète.")
            return
        if not nom:
            QMessageBox.warning(self, "Nom requis", "Donne un nom à ce parcours.")
            return

        def suite(points_json):
            self._finaliser_enregistrement(athlete_id, nom, points_json)

        self._recuperer_points(suite)

    def _finaliser_enregistrement(self, athlete_id, nom, points_json):
        try:
            points_latlon = json.loads(points_json) if points_json else []
        except (TypeError, ValueError):
            points_latlon = []

        if len(points_latlon) < 2:
            QMessageBox.warning(
                self, "Parcours trop court",
                "Clique au moins deux points sur la carte pour créer un parcours."
            )
            return

        self.label_statut.setText("Récupération du profil altimétrique...")
        altitudes, erreur_altitude = obtenir_altitudes(points_latlon)

        points_complets = [
            (lat, lon, alt) for (lat, lon), alt in zip(points_latlon, altitudes)
        ]

        distance_km = self._distance_totale(points_complets)
        denivele_positif = self._denivele_positif(points_complets)

        conn = connexion()
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO parcours_gpx
               (athlete_id, nom, distance_km, denivele_positif, trace_json)
               VALUES (?,?,?,?,?)""",
            (athlete_id, nom, round(distance_km, 2), round(denivele_positif),
             json.dumps(points_complets)),
        )
        conn.commit()
        conn.close()

        message = f"✅ Parcours « {nom} » enregistré : {distance_km:.2f} km, {round(denivele_positif)} m D+."
        if erreur_altitude:
            message += f"\n⚠️ Altitude approximative (0 m par défaut) : {erreur_altitude}"
        self.label_statut.setText(message)

        QMessageBox.information(self, "Parcours enregistré", message)

    def exporter_parcours(self):
        def suite(points_json):
            try:
                points_latlon = json.loads(points_json) if points_json else []
            except (TypeError, ValueError):
                points_latlon = []

            if len(points_latlon) < 2:
                QMessageBox.warning(
                    self, "Parcours trop court",
                    "Clique au moins deux points sur la carte avant d'exporter."
                )
                return

            nom = self.champ_nom.text().strip() or "parcours"
            chemin, _ = QFileDialog.getSaveFileName(
                self, "Exporter en GPX", f"{nom}.gpx", "Fichier GPX (*.gpx)"
            )
            if not chemin:
                return

            points_complets = [(lat, lon, 0) for lat, lon in points_latlon]
            exporter_gpx(nom, points_complets, chemin)
            self.label_statut.setText(f"✅ Exporté vers {chemin}")

        self._recuperer_points(suite)

    def _distance_totale(self, points):
        from interface.gpx_utils import _distance_haversine_km

        total = 0.0
        for i in range(1, len(points)):
            total += _distance_haversine_km(
                points[i - 1][0], points[i - 1][1], points[i][0], points[i][1]
            )
        return total

    def _denivele_positif(self, points):
        total = 0.0
        for i in range(1, len(points)):
            diff = points[i][2] - points[i - 1][2]
            if diff > 0:
                total += diff
        return total
