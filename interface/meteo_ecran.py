from PySide6.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QComboBox,
    QPushButton,
    QFrame,
    QDateEdit,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QScrollArea,
)
from PySide6.QtCore import QDate, Qt

from data.database import connexion, obtenir_athletes
from interface.ecran_liste import (
    obtenir_style_ecran, configurer_table_redimensionnable, creer_bouton_retour_tableau_bord,
)
from interface.secteurs_utils import regrouper_en_secteurs
from interface.meteo import obtenir_meteo_actuelle_et_previsions, obtenir_meteo_historique


def _localisation_principale(athlete_id):
    """Centre de la zone la plus fréquentée de l'athlète (voir Secteurs/
    Carte thermique) — sert de position par défaut pour la météo."""

    conn = connexion()
    cur = conn.cursor()
    cur.execute("SELECT id, trace_json FROM parcours_gpx WHERE athlete_id=?", (athlete_id,))
    lignes = cur.fetchall()
    conn.close()

    import json
    traces = []
    for id_, trace_json in lignes:
        if not trace_json:
            continue
        points = json.loads(trace_json)
        if points:
            traces.append({"id": id_, "point_depart": (points[0][0], points[0][1])})

    if not traces:
        return None

    secteurs = regrouper_en_secteurs(traces, rayon_km=15)
    plus_gros = max(secteurs, key=lambda s: len(s["traces"]))
    return plus_gros["centre"]


class MeteoEcran(QMainWindow):

    def __init__(self, athlete_id_initial=None):
        super().__init__()

        self.setWindowTitle("TrailMaster Pro – Météo")
        self.resize(1200, 850)
        self.setMinimumSize(950, 650)

        conteneur_scroll = QScrollArea()
        conteneur_scroll.setWidgetResizable(True)
        conteneur_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        conteneur_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        conteneur_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.setCentralWidget(conteneur_scroll)

        central = QWidget()
        conteneur_scroll.setWidget(central)

        principal = QVBoxLayout(central)
        principal.setContentsMargins(25, 20, 25, 20)
        principal.setSpacing(15)

        principal.addWidget(creer_bouton_retour_tableau_bord(self), 0, Qt.AlignmentFlag.AlignLeft)

        titre = QLabel("🌦️  Météo")
        titre.setObjectName("titrePage")
        sous_titre = QLabel(
            "Via Open-Meteo (gratuit, sans clé) — nécessite une connexion internet, "
            "basé sur ta zone d'entraînement principale"
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

        bouton_actualiser = QPushButton("🔄 Actualiser la météo")
        bouton_actualiser.setObjectName("boutonPrincipal")
        bouton_actualiser.clicked.connect(self.actualiser_previsions)

        barre.addWidget(label_athlete)
        barre.addWidget(self.combo_athlete)
        barre.addStretch()
        barre.addWidget(bouton_actualiser)
        principal.addLayout(barre)

        self.label_localisation = QLabel("—")
        self.label_localisation.setObjectName("texteSecondaire")
        principal.addWidget(self.label_localisation)

        cadre_actuel = QFrame()
        cadre_actuel.setObjectName("carteForm")
        actuel_layout = QVBoxLayout(cadre_actuel)
        titre_actuel = QLabel("Maintenant")
        titre_actuel.setObjectName("titreCarte")
        actuel_layout.addWidget(titre_actuel)
        self.label_actuel = QLabel("—")
        self.label_actuel.setStyleSheet("font-size: 20px; font-weight: bold; color: white;")
        actuel_layout.addWidget(self.label_actuel)
        principal.addWidget(cadre_actuel)

        cadre_previsions = QFrame()
        cadre_previsions.setObjectName("carteForm")
        previsions_layout = QVBoxLayout(cadre_previsions)
        titre_previsions = QLabel("Prévisions 7 jours")
        titre_previsions.setObjectName("titreCarte")
        previsions_layout.addWidget(titre_previsions)

        self.table_previsions = QTableWidget()
        self.table_previsions.setColumnCount(5)
        self.table_previsions.setHorizontalHeaderLabels(
            ["Date", "Conditions", "Min / Max", "Précipitations", "Vent max"]
        )
        configurer_table_redimensionnable(self.table_previsions)
        self.table_previsions.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        previsions_layout.addWidget(self.table_previsions)
        principal.addWidget(cadre_previsions)

        cadre_histo = QFrame()
        cadre_histo.setObjectName("carteForm")
        histo_layout = QVBoxLayout(cadre_histo)
        titre_histo = QLabel("Météo d'une date passée (ex. le jour d'une course)")
        titre_histo.setObjectName("titreCarte")
        histo_layout.addWidget(titre_histo)

        barre_histo = QHBoxLayout()
        self.champ_date_histo = QDateEdit()
        self.champ_date_histo.setCalendarPopup(True)
        self.champ_date_histo.setDate(QDate.currentDate().addDays(-30))
        bouton_histo = QPushButton("Consulter")
        bouton_histo.setObjectName("boutonSecondaire")
        bouton_histo.clicked.connect(self.consulter_historique)
        barre_histo.addWidget(self.champ_date_histo)
        barre_histo.addWidget(bouton_histo)
        barre_histo.addStretch()
        histo_layout.addLayout(barre_histo)

        self.label_histo = QLabel("—")
        self.label_histo.setObjectName("texteSecondaire")
        self.label_histo.setWordWrap(True)
        histo_layout.addWidget(self.label_histo)

        principal.addWidget(cadre_histo)

        self.setStyleSheet(obtenir_style_ecran())

        if athlete_id_initial is not None:
            for i in range(self.combo_athlete.count()):
                if self.combo_athlete.itemData(i) == athlete_id_initial:
                    self.combo_athlete.setCurrentIndex(i)
                    break

        self._localisation = None

    def _obtenir_localisation(self):
        athlete_id = self.combo_athlete.currentData()
        if athlete_id is None:
            return None
        if self._localisation is None:
            self._localisation = _localisation_principale(athlete_id)
        return self._localisation

    def actualiser_previsions(self):
        self._localisation = None
        localisation = self._obtenir_localisation()

        if localisation is None:
            self.label_localisation.setText(
                "Sélectionne un athlète ayant au moins une trace GPS enregistrée."
            )
            return

        lat, lon = localisation
        self.label_localisation.setText(f"Zone principale : {lat:.3f}, {lon:.3f}")
        self.label_actuel.setText("Récupération de la météo...")

        donnees, erreur = obtenir_meteo_actuelle_et_previsions(lat, lon)

        if erreur:
            self.label_actuel.setText(f"⚠️ {erreur}")
            self.table_previsions.setRowCount(0)
            return

        actuel = donnees["actuel"]
        self.label_actuel.setText(
            f"{actuel['temperature']}°C — {actuel['description']} — "
            f"vent {actuel['vent_kmh']} km/h — humidité {actuel['humidite']}%"
        )

        previsions = donnees["previsions"]
        self.table_previsions.setRowCount(len(previsions))
        for i, jour in enumerate(previsions):
            self.table_previsions.setItem(i, 0, QTableWidgetItem(jour["date"]))
            self.table_previsions.setItem(i, 1, QTableWidgetItem(jour["description"]))
            self.table_previsions.setItem(
                i, 2, QTableWidgetItem(f"{jour['temperature_min']}° / {jour['temperature_max']}°")
            )
            self.table_previsions.setItem(i, 3, QTableWidgetItem(f"{jour['precipitation_mm']} mm"))
            self.table_previsions.setItem(i, 4, QTableWidgetItem(f"{jour['vent_max_kmh']} km/h"))

        self.table_previsions.resizeColumnsToContents()

    def consulter_historique(self):
        localisation = self._obtenir_localisation()
        if localisation is None:
            self.label_histo.setText("Sélectionne d'abord un athlète.")
            return

        lat, lon = localisation
        date_iso = self.champ_date_histo.date().toString("yyyy-MM-dd")

        self.label_histo.setText("Récupération de la météo historique...")
        donnees, erreur = obtenir_meteo_historique(lat, lon, date_iso)

        if erreur:
            self.label_histo.setText(f"⚠️ {erreur}")
            return

        self.label_histo.setText(
            f"{donnees['date']} : {donnees['description']}, "
            f"{donnees['temperature_min']}° / {donnees['temperature_max']}°, "
            f"{donnees['precipitation_mm']} mm de précipitations, "
            f"vent max {donnees['vent_max_kmh']} km/h"
        )
