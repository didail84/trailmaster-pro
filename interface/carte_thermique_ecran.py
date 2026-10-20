import json

from PySide6.QtCore import Qt

from PySide6.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QComboBox,
    QFrame,
    QCheckBox,
    QScrollArea,
)

from data.database import connexion, creer_base_de_donnees, obtenir_athletes
from interface.ecran_liste import obtenir_style_ecran
from interface.carte_thermique import CarteThermique
from interface.secteurs_utils import regrouper_en_secteurs


class CarteThermiqueEcran(QMainWindow):

    def __init__(self, athlete_id_initial=None):
        super().__init__()

        creer_base_de_donnees()

        self.setWindowTitle("TrailMaster Pro – Carte thermique")
        self.resize(1300, 900)
        self.setMinimumSize(1000, 700)

        central = QWidget()
        conteneur_scroll = QScrollArea()
        conteneur_scroll.setWidgetResizable(True)
        conteneur_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        conteneur_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        conteneur_scroll.setFrameShape(QFrame.Shape.NoFrame)
        conteneur_scroll.setWidget(central)
        self.setCentralWidget(conteneur_scroll)

        principal = QVBoxLayout(central)
        principal.setContentsMargins(25, 20, 25, 20)
        principal.setSpacing(15)

        titre = QLabel("🔥  Carte thermique")
        titre.setObjectName("titrePage")
        sous_titre = QLabel(
            "Toutes tes traces superposées — les zones les plus fréquentées ressortent "
            "plus intensément (schématique, sans fond de carte réel)"
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

        label_type = QLabel("Type :")
        label_type.setObjectName("labelChamp")
        self.combo_type = QComboBox()
        self.combo_type.addItems(["Tous", "Trail", "Course", "VTT", "Vélo", "Randonnée"])

        self.case_voyages = QCheckBox("Inclure les sorties loin de chez moi (voyages)")

        barre.addWidget(label_athlete)
        barre.addWidget(self.combo_athlete)
        barre.addSpacing(15)
        barre.addWidget(label_type)
        barre.addWidget(self.combo_type)
        barre.addSpacing(15)
        barre.addWidget(self.case_voyages)
        barre.addStretch()
        principal.addLayout(barre)

        self.label_stats = QLabel("—")
        self.label_stats.setObjectName("texteSecondaire")
        principal.addWidget(self.label_stats)

        cadre_carte = QFrame()
        cadre_carte.setObjectName("carteForm")
        carte_layout = QVBoxLayout(cadre_carte)
        self.carte = CarteThermique()
        carte_layout.addWidget(self.carte)
        principal.addWidget(cadre_carte, 1)

        self.setStyleSheet(obtenir_style_ecran())

        if athlete_id_initial is not None:
            for i in range(self.combo_athlete.count()):
                if self.combo_athlete.itemData(i) == athlete_id_initial:
                    self.combo_athlete.setCurrentIndex(i)
                    break

        self.combo_athlete.currentIndexChanged.connect(self.actualiser)
        self.combo_type.currentIndexChanged.connect(self.actualiser)
        self.case_voyages.stateChanged.connect(self.actualiser)
        self.actualiser()

    def actualiser(self):
        athlete_id = self.combo_athlete.currentData()
        if athlete_id is None:
            self.carte.definir_traces([])
            self.label_stats.setText("Sélectionne un athlète.")
            return

        type_filtre = self.combo_type.currentText()

        conn = connexion()
        cur = conn.cursor()
        if type_filtre == "Tous":
            cur.execute(
                "SELECT id, trace_json FROM parcours_gpx WHERE athlete_id=?",
                (athlete_id,),
            )
        else:
            cur.execute(
                """
                SELECT p.id, p.trace_json FROM parcours_gpx p
                LEFT JOIN activites a ON p.activite_id = a.id
                WHERE p.athlete_id=? AND a.type=?
                """,
                (athlete_id, type_filtre),
            )
        lignes = cur.fetchall()
        conn.close()

        traces = []
        traces_par_id = {}
        for (id_parcours, trace_json) in lignes:
            if not trace_json:
                continue
            points = json.loads(trace_json)
            if not points:
                continue
            traces_par_id[id_parcours] = [(p[0], p[1]) for p in points]

        if not self.case_voyages.isChecked() and traces_par_id:
            # Recentre par défaut sur la zone la plus fréquentée : sans ce
            # filtre, une seule sortie loin de chez soi (voyage) peut à
            # elle seule étirer le cadrage sur des centaines de km et
            # rendre la vraie zone d'entraînement minuscule à l'écran.
            traces_pour_clustering = [
                {"id": id_, "point_depart": pts[0]} for id_, pts in traces_par_id.items()
            ]
            secteurs = regrouper_en_secteurs(traces_pour_clustering, rayon_km=15)
            plus_gros = max(secteurs, key=lambda s: len(s["traces"]))
            ids_zone_principale = {t["id"] for t in plus_gros["traces"]}
            traces = [pts for id_, pts in traces_par_id.items() if id_ in ids_zone_principale]
        else:
            traces = list(traces_par_id.values())

        self.carte.definir_traces(traces)
        nb_exclues = len(traces_par_id) - len(traces)
        message = f"{len(traces)} trace(s) affichée(s)"
        if nb_exclues > 0:
            message += f" — {nb_exclues} sortie(s) loin de la zone principale masquée(s) (case à cocher pour les inclure)"
        self.label_stats.setText(message)
