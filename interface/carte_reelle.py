"""
Vraie carte (rues, relief) via Leaflet + OpenStreetMap, affichée dans
un composant web embarqué (QtWebEngine).

La librairie Leaflet elle-même est embarquée dans l'appli (dossier
interface/assets/leaflet/) — elle se charge donc instantanément, sans
dépendre d'internet. Seules les tuiles de carte (rues, relief) sont
récupérées depuis OpenStreetMap à chaque ouverture ; sans connexion,
la carte s'affiche normalement (contrôles, cadrage) mais les tuiles
restent grises — c'est la seule partie de l'appli qui dépend
d'internet.
"""

import json
import tempfile
from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QComboBox,
    QPushButton,
    QFrame,
)
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebEngineCore import QWebEngineSettings

from data.database import connexion, creer_base_de_donnees, obtenir_athletes
from interface.ecran_liste import obtenir_style_ecran
from interface.secteurs_utils import regrouper_en_secteurs


PAS_SOUS_ECHANTILLONNAGE = 3
NB_TRACES_MAX_HEATMAP = 400

DOSSIER_LEAFLET = Path(__file__).parent / "assets" / "leaflet"
CHEMIN_TEMP_HTML = Path(tempfile.gettempdir()) / "trailmaster_carte_reelle.html"

GABARIT_HTML = """
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8" />
<link rel="stylesheet" href="%s" />
<script src="%s"></script>
<style>
  html, body, #carte { height: 100%%; margin: 0; padding: 0; background: #15191D; }
  .leaflet-control-layers { font-family: sans-serif; font-size: 13px; }
</style>
</head>
<body>
<div id="carte"></div>
<script>
  var carte = L.map('carte');

  // Fonds de carte au choix (comme le sélecteur Plan/Satellite de Google
  // Maps) — tous gratuits et sans clé d'API : OpenStreetMap (plan),
  // Esri World Imagery (satellite réel), OpenTopoMap (relief/sentiers).
  var fondPlan = L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
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

  var traces = %s;
  var tousPoints = [];

  traces.forEach(function(trace) {
      // Liseré sombre en dessous : garde le tracé lisible quel que soit
      // le fond de carte (rue claire, forêt, eau...), pas seulement sur
      // fond neutre avant que les tuiles ne soient chargées.
      L.polyline(trace, {color: '#000000', weight: 4.5, opacity: Math.min(%s * 1.6, 0.6)}).addTo(carte);
      L.polyline(trace, {color: '#FF7828', weight: 2.5, opacity: %s}).addTo(carte);
      tousPoints = tousPoints.concat(trace);
  });

  if (tousPoints.length > 0) {
      carte.fitBounds(L.latLngBounds(tousPoints), {padding: [30, 30]});
  } else {
      carte.setView([46.6, 2.4], 6);
  }
</script>
</body>
</html>"""


class CarteReelle(QMainWindow):

    def __init__(self, athlete_id_initial=None, parcours_id_initial=None):
        super().__init__()

        creer_base_de_donnees()

        self._parcours_id_initial = parcours_id_initial

        self.setWindowTitle("TrailMaster Pro – Carte réelle")
        self.resize(1300, 900)
        self.setMinimumSize(1000, 700)

        central = QWidget()
        self.setCentralWidget(central)

        principal = QVBoxLayout(central)
        principal.setContentsMargins(25, 20, 25, 20)
        principal.setSpacing(15)

        titre = QLabel("🗺️  Carte réelle")
        titre.setObjectName("titrePage")
        sous_titre = QLabel(
            "Plan, satellite ou relief au choix (sélecteur en haut à droite de la carte) — "
            "nécessite une connexion internet, seule fonctionnalité de l'appli dans ce cas"
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

        label_mode = QLabel("Afficher :")
        label_mode.setObjectName("labelChamp")
        self.combo_mode = QComboBox()
        self.combo_mode.addItem("Une sortie précise", "sortie")
        self.combo_mode.addItem("Toutes mes traces (zone principale)", "heatmap")

        self.combo_parcours = QComboBox()
        self.combo_parcours.setMinimumWidth(250)

        bouton_afficher = QPushButton("🔄 Afficher sur la carte")
        bouton_afficher.setObjectName("boutonPrincipal")
        bouton_afficher.clicked.connect(self.afficher_carte)

        barre.addWidget(label_athlete)
        barre.addWidget(self.combo_athlete)
        barre.addSpacing(10)
        barre.addWidget(label_mode)
        barre.addWidget(self.combo_mode)
        barre.addWidget(self.combo_parcours)
        barre.addStretch()
        barre.addWidget(bouton_afficher)
        principal.addLayout(barre)

        self.label_info = QLabel("Sélectionne un athlète pour commencer.")
        self.label_info.setObjectName("texteSecondaire")
        principal.addWidget(self.label_info)

        cadre_carte = QFrame()
        cadre_carte.setObjectName("carteForm")
        carte_layout = QVBoxLayout(cadre_carte)
        self.vue_web = QWebEngineView()
        self.vue_web.setMinimumHeight(500)
        # La page de la carte est chargée en local (fichier temporaire
        # file://) mais doit récupérer les tuiles sur de vrais serveurs
        # distants (OpenStreetMap, Esri, OpenTopoMap) — QtWebEngine bloque
        # ça par défaut pour une page locale (LocalContentCanAccessRemoteUrls
        # = False), ce qui laisse le fond de carte vide alors que tout le
        # reste (bibliothèque Leaflet, tracé, contrôles) fonctionne très
        # bien puisqu'il ne dépend que du contenu local.
        self.vue_web.settings().setAttribute(
            QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True
        )
        self.vue_web.loadFinished.connect(self._verifier_chargement)
        carte_layout.addWidget(self.vue_web)
        principal.addWidget(cadre_carte, 1)

        self.setStyleSheet(obtenir_style_ecran())

        self.combo_athlete.currentIndexChanged.connect(self.charger_parcours)
        self.combo_mode.currentIndexChanged.connect(self._basculer_mode)

        if athlete_id_initial is not None:
            for i in range(self.combo_athlete.count()):
                if self.combo_athlete.itemData(i) == athlete_id_initial:
                    self.combo_athlete.setCurrentIndex(i)
                    break

        self.charger_parcours()

        if self._parcours_id_initial is not None:
            self.combo_mode.setCurrentIndex(0)  # "Une sortie précise"
            for i in range(self.combo_parcours.count()):
                if self.combo_parcours.itemData(i) == self._parcours_id_initial:
                    self.combo_parcours.setCurrentIndex(i)
                    break
            self._basculer_mode()
            self.afficher_carte()
        else:
            self._basculer_mode()

    def _basculer_mode(self):
        self.combo_parcours.setVisible(self.combo_mode.currentData() == "sortie")

    def charger_parcours(self):
        athlete_id = self.combo_athlete.currentData()
        self.combo_parcours.clear()

        if athlete_id is None:
            return

        conn = connexion()
        cur = conn.cursor()
        cur.execute(
            "SELECT id, nom, distance_km FROM parcours_gpx WHERE athlete_id=? "
            "ORDER BY date_ajout DESC LIMIT 300",
            (athlete_id,),
        )
        for id_, nom, distance in cur.fetchall():
            self.combo_parcours.addItem(f"{nom} ({distance} km)", id_)
        conn.close()

    def afficher_carte(self):
        athlete_id = self.combo_athlete.currentData()
        if athlete_id is None:
            self.label_info.setText("Sélectionne un athlète.")
            return

        mode = self.combo_mode.currentData()

        if mode == "sortie":
            parcours_id = self.combo_parcours.currentData()
            if parcours_id is None:
                self.label_info.setText("Sélectionne une sortie.")
                return
            traces = self._trace_unique(parcours_id)
            opacite = "0.9"
            self.label_info.setText("1 trace affichée (chargement des tuiles OpenStreetMap...)")
        else:
            traces = self._traces_zone_principale(athlete_id)
            opacite = "0.35"
            self.label_info.setText(
                f"{len(traces)} trace(s) affichée(s) — zone principale uniquement "
                "(chargement des tuiles OpenStreetMap...)"
            )

        if not DOSSIER_LEAFLET.exists():
            self.label_info.setText(
                f"⚠️ Fichiers Leaflet introuvables ({DOSSIER_LEAFLET}). "
                "La carte ne peut pas s'afficher — réinstalle TrailMaster Pro depuis le dernier zip."
            )
            return

        chemin_css = (DOSSIER_LEAFLET / "leaflet.css").as_uri()
        chemin_js = (DOSSIER_LEAFLET / "leaflet.js").as_uri()
        html = GABARIT_HTML % (chemin_css, chemin_js, json.dumps(traces), opacite, opacite)

        # Écrit un vrai fichier HTML dans le dossier temporaire du système
        # (toujours accessible en écriture, contrairement au dossier
        # d'installation de l'appli qui peut être en lecture seule) et le
        # charge via .load() — plus fiable que setHtml() pour ce genre de
        # contenu avec ressources locales.
        try:
            CHEMIN_TEMP_HTML.write_text(html, encoding="utf-8")
        except OSError as erreur:
            self.label_info.setText(f"⚠️ Impossible d'écrire le fichier de carte : {erreur}")
            return

        self.vue_web.load(QUrl.fromLocalFile(str(CHEMIN_TEMP_HTML)))

    def _verifier_chargement(self, succes):
        if not succes:
            self.label_info.setText(
                "⚠️ Le composant carte n'a pas réussi à charger la page. "
                "Vérifie ta connexion internet, ou signale ce message si le problème persiste."
            )

    def _trace_unique(self, parcours_id):
        conn = connexion()
        cur = conn.cursor()
        cur.execute("SELECT trace_json FROM parcours_gpx WHERE id=?", (parcours_id,))
        resultat = cur.fetchone()
        conn.close()

        if not resultat or not resultat[0]:
            return []

        points = json.loads(resultat[0])
        sous_echantillon = points[::PAS_SOUS_ECHANTILLONNAGE] or points
        return [[[p[0], p[1]] for p in sous_echantillon]]

    def _traces_zone_principale(self, athlete_id):
        conn = connexion()
        cur = conn.cursor()
        cur.execute("SELECT id, trace_json FROM parcours_gpx WHERE athlete_id=?", (athlete_id,))
        lignes = cur.fetchall()
        conn.close()

        traces_par_id = {}
        for id_parcours, trace_json in lignes:
            if not trace_json:
                continue
            points = json.loads(trace_json)
            if not points:
                continue
            traces_par_id[id_parcours] = points

        if not traces_par_id:
            return []

        traces_pour_clustering = [
            {"id": id_, "point_depart": (pts[0][0], pts[0][1])}
            for id_, pts in traces_par_id.items()
        ]
        secteurs = regrouper_en_secteurs(traces_pour_clustering, rayon_km=15)
        plus_gros = max(secteurs, key=lambda s: len(s["traces"]))
        ids_zone = [t["id"] for t in plus_gros["traces"]][:NB_TRACES_MAX_HEATMAP]

        resultat = []
        for id_ in ids_zone:
            points = traces_par_id[id_]
            sous_echantillon = points[::PAS_SOUS_ECHANTILLONNAGE] or points
            resultat.append([[p[0], p[1]] for p in sous_echantillon])

        return resultat
