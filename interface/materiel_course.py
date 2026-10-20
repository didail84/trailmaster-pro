"""
Matériel obligatoire/conseillé pour une course — à distinguer de
l'onglet "Matériel" du Suivi (interface/materiel.py), qui lui suit
l'usure de ton propre équipement (chaussures, bâtons...), pas ce qu'il
faut emporter pour une course donnée.

Deux façons de l'utiliser :
  - en choisissant une course déjà enregistrée dans "Courses à venir"
    (distance, dénivelé, saison déduits automatiquement) ;
  - en saisie manuelle (n'importe quelle distance/dénivelé), pour une
    course qui n'est pas dans ta liste.

Rappel affiché dans l'écran : chaque organisateur fixe son propre
règlement — cette liste est un repère basé sur les standards courants
du trail français, pas le règlement officiel exact de la course
choisie.
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
    QDoubleSpinBox, QSpinBox, QCheckBox, QPushButton, QFrame, QScrollArea,
    QListWidget, QListWidgetItem,
)

from data.database import connexion
from data.reference_materiel_course import calculer_materiel
from interface.theme import (
    PALETTE, POLICE_TITRE, POLICE_TEXTE, POLICE_TEXTE_DEMI, charger_polices,
    obtenir_couleur_accent, obtenir_couleur_accent_douce,
)


MOIS_VERS_SAISON = {
    12: "Hiver", 1: "Hiver", 2: "Hiver",
    3: "Printemps", 4: "Printemps", 5: "Printemps",
    6: "Été", 7: "Été", 8: "Été",
    9: "Automne", 10: "Automne", 11: "Automne",
}


def _style_page():
    return f"""
        QWidget {{
            background-color: {PALETTE['fond']};
            color: {PALETTE['texte']};
            font-family: '{POLICE_TEXTE}', sans-serif;
        }}
        #boutonRetourTableauBord {{
            background-color: transparent;
            color: {PALETTE['texte_secondaire']};
            border: none;
            font-size: 12.5px;
            padding: 8px 12px 4px 12px;
            text-align: left;
        }}
        #boutonRetourTableauBord:hover {{
            color: {obtenir_couleur_accent()};
        }}
        #titrePage {{
            font-family: '{POLICE_TITRE}', sans-serif;
            font-size: 20px;
            font-weight: 700;
        }}
        #sousTitrePage {{
            color: {PALETTE['texte_secondaire']};
            font-size: 12.5px;
        }}
        #carteReglage {{
            background-color: {PALETTE['carte']};
            border: 1px solid {PALETTE['bordure']};
            border-radius: 10px;
        }}
        QComboBox, QDoubleSpinBox, QSpinBox {{
            background-color: {PALETTE['fond_secondaire']};
            border: 1px solid {PALETTE['bordure']};
            border-radius: 8px;
            padding: 6px 10px;
            color: {PALETTE['texte']};
        }}
        #boutonGenerer {{
            background-color: {obtenir_couleur_accent()};
            color: white;
            border: none;
            border-radius: 8px;
            padding: 10px 18px;
            font-weight: 600;
        }}
        #titreColonne {{
            font-family: '{POLICE_TEXTE_DEMI}', sans-serif;
            font-size: 15px;
        }}
        QListWidget {{
            background-color: {PALETTE['carte']};
            border: 1px solid {PALETTE['bordure']};
            border-radius: 8px;
        }}
        QListWidget::item {{
            padding: 8px 6px;
        }}
    """


class MaterielCourse(QMainWindow):

    def __init__(self, athlete_id_initial=None, course_preselectionnee=None):
        """course_preselectionnee : dict optionnel {nom, distance_km,
        denivele_m, type_terrain, date} pour ouvrir l'écran directement
        pré-rempli depuis l'onglet Courses à venir, sans repasser par
        le menu déroulant."""

        super().__init__()
        charger_polices()
        self.athlete_id = athlete_id_initial
        self.setWindowTitle("TrailMaster Pro – Matériel pour une course")
        self.resize(1100, 820)
        self.setMinimumSize(900, 600)

        central = QWidget()
        central.setStyleSheet(_style_page())
        layout = QVBoxLayout(central)
        layout.setContentsMargins(24, 10, 24, 20)
        layout.setSpacing(14)
        self.setCentralWidget(central)

        bouton_retour = QPushButton("← Aujourd'hui")
        bouton_retour.setObjectName("boutonRetourTableauBord")
        bouton_retour.setCursor(Qt.CursorShape.PointingHandCursor)
        bouton_retour.clicked.connect(self.close)
        layout.addWidget(bouton_retour, 0, Qt.AlignmentFlag.AlignLeft)

        titre = QLabel("🎒  Matériel pour une course")
        titre.setObjectName("titrePage")
        sous_titre = QLabel(
            "Repère basé sur les standards courants du trail français (distance, dénivelé, "
            "conditions) — vérifie toujours le règlement officiel exact de la course visée, "
            "chaque organisateur fixe sa propre liste."
        )
        sous_titre.setObjectName("sousTitrePage")
        sous_titre.setWordWrap(True)
        layout.addWidget(titre)
        layout.addWidget(sous_titre)

        # ------------------------------------------------------------
        # RÉGLAGES
        # ------------------------------------------------------------

        carte = QFrame()
        carte.setObjectName("carteReglage")
        carte_layout = QVBoxLayout(carte)
        carte_layout.setContentsMargins(18, 16, 18, 16)
        carte_layout.setSpacing(12)

        ligne_course = QHBoxLayout()
        label_course = QLabel("Course enregistrée :")
        self.combo_course = QComboBox()
        self.combo_course.addItem("— Saisie manuelle —", None)
        self._charger_courses_enregistrees()
        self.combo_course.currentIndexChanged.connect(self._course_selectionnee_changee)
        ligne_course.addWidget(label_course)
        ligne_course.addWidget(self.combo_course, 1)
        carte_layout.addLayout(ligne_course)

        ligne_valeurs = QHBoxLayout()

        bloc_distance = QVBoxLayout()
        bloc_distance.addWidget(QLabel("Distance (km)"))
        self.champ_distance = QDoubleSpinBox()
        self.champ_distance.setRange(0, 400)
        self.champ_distance.setValue(30)
        self.champ_distance.setDecimals(1)
        bloc_distance.addWidget(self.champ_distance)
        ligne_valeurs.addLayout(bloc_distance)

        bloc_denivele = QVBoxLayout()
        bloc_denivele.addWidget(QLabel("D+ (m)"))
        self.champ_denivele = QSpinBox()
        self.champ_denivele.setRange(0, 15000)
        self.champ_denivele.setValue(1200)
        self.champ_denivele.setSingleStep(50)
        bloc_denivele.addWidget(self.champ_denivele)
        ligne_valeurs.addLayout(bloc_denivele)

        bloc_saison = QVBoxLayout()
        bloc_saison.addWidget(QLabel("Saison"))
        self.combo_saison = QComboBox()
        self.combo_saison.addItems(["Printemps", "Été", "Automne", "Hiver"])
        bloc_saison.addWidget(self.combo_saison)
        ligne_valeurs.addLayout(bloc_saison)

        carte_layout.addLayout(ligne_valeurs)

        ligne_cases = QHBoxLayout()
        self.case_nocturne = QCheckBox("Portion nocturne prévue")
        self.case_altitude = QCheckBox("Haute montagne / altitude élevée")
        ligne_cases.addWidget(self.case_nocturne)
        ligne_cases.addWidget(self.case_altitude)
        ligne_cases.addStretch()
        carte_layout.addLayout(ligne_cases)

        bouton_generer = QPushButton("Générer la liste de matériel")
        bouton_generer.setObjectName("boutonGenerer")
        bouton_generer.setCursor(Qt.CursorShape.PointingHandCursor)
        bouton_generer.clicked.connect(self._generer)
        carte_layout.addWidget(bouton_generer, 0, Qt.AlignmentFlag.AlignLeft)

        layout.addWidget(carte)

        # ------------------------------------------------------------
        # RÉSULTAT
        # ------------------------------------------------------------

        zone_resultat = QHBoxLayout()
        zone_resultat.setSpacing(16)

        bloc_obligatoire = QVBoxLayout()
        titre_obligatoire = QLabel("✅ Obligatoire")
        titre_obligatoire.setObjectName("titreColonne")
        bloc_obligatoire.addWidget(titre_obligatoire)
        self.liste_obligatoire = QListWidget()
        bloc_obligatoire.addWidget(self.liste_obligatoire)
        zone_resultat.addLayout(bloc_obligatoire)

        bloc_conseille = QVBoxLayout()
        titre_conseille = QLabel("👍 Conseillé")
        titre_conseille.setObjectName("titreColonne")
        bloc_conseille.addWidget(titre_conseille)
        self.liste_conseille = QListWidget()
        bloc_conseille.addWidget(self.liste_conseille)
        zone_resultat.addLayout(bloc_conseille)

        layout.addLayout(zone_resultat, 1)

        if course_preselectionnee:
            self._appliquer_course(course_preselectionnee)
        self._generer()

    # ------------------------------------------------------------

    def _charger_courses_enregistrees(self):
        conn = connexion()
        cur = conn.cursor()
        if self.athlete_id is not None:
            cur.execute(
                "SELECT id, nom, date, distance_km, denivele_m, type_terrain FROM courses_calendrier "
                "WHERE athlete_id=? ORDER BY date ASC",
                (self.athlete_id,),
            )
        else:
            cur.execute(
                "SELECT id, nom, date, distance_km, denivele_m, type_terrain FROM courses_calendrier "
                "ORDER BY date ASC"
            )
        self._courses = cur.fetchall()
        conn.close()

        for id_, nom, date_, distance_km, denivele_m, type_terrain in self._courses:
            libelle = f"{nom} — {str(date_)[:10]} ({distance_km} km)"
            self.combo_course.addItem(libelle, id_)

    def _course_selectionnee_changee(self):
        id_course = self.combo_course.currentData()
        if id_course is None:
            return
        for id_, nom, date_, distance_km, denivele_m, type_terrain in self._courses:
            if id_ == id_course:
                self._appliquer_course({
                    "nom": nom, "date": date_, "distance_km": distance_km,
                    "denivele_m": denivele_m, "type_terrain": type_terrain,
                })
                self._generer()
                break

    def _appliquer_course(self, course):
        if course.get("distance_km") is not None:
            self.champ_distance.setValue(float(course["distance_km"]))
        if course.get("denivele_m") is not None:
            self.champ_denivele.setValue(int(course["denivele_m"]))

        nom = (course.get("nom") or "").lower()
        terrain = (course.get("type_terrain") or "").lower()
        self.case_nocturne.setChecked("nocturne" in nom)
        self.case_altitude.setChecked(
            (course.get("denivele_m") or 0) >= 3000 or "haute montagne" in terrain
        )

        date_str = str(course.get("date") or "")
        if len(date_str) >= 7:
            try:
                mois = int(date_str[5:7])
                saison = MOIS_VERS_SAISON.get(mois)
                if saison:
                    self.combo_saison.setCurrentText(saison)
            except ValueError:
                pass

    def _generer(self):
        resultat = calculer_materiel(
            distance_km=self.champ_distance.value(),
            denivele_m=self.champ_denivele.value(),
            nocturne=self.case_nocturne.isChecked(),
            altitude_elevee=self.case_altitude.isChecked(),
            saison=self.combo_saison.currentText(),
        )

        self.liste_obligatoire.clear()
        for nom, raison in resultat["obligatoire"]:
            item = QListWidgetItem(f"{nom}\n{raison}")
            self.liste_obligatoire.addItem(item)

        self.liste_conseille.clear()
        for nom, raison in resultat["conseille"]:
            item = QListWidgetItem(f"{nom}\n{raison}")
            self.liste_conseille.addItem(item)
