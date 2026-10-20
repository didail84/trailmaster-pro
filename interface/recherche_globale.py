"""
Recherche globale — un seul champ de recherche qui interroge en même
temps les activités, les séances structurées, les résultats de
courses, les objectifs et les parcours enregistrés, plutôt que d'avoir
à se souvenir dans quelle catégorie se trouve telle information.

100% local (une seule requête SQL par table, sur la base déjà présente
sur l'ordinateur) — aucune dépendance réseau.
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QComboBox,
    QFrame,
    QScrollArea,
    QHeaderView,
)

from data.database import connexion, creer_base_de_donnees, obtenir_athletes, obtenir_parametre, definir_parametre
from interface.ecran_liste import (
    obtenir_style_ecran, configurer_table_redimensionnable, creer_bouton_retour_tableau_bord,
)
from interface.theme import charger_polices

NB_RESULTATS_MAX_PAR_CATEGORIE_DEFAUT = 50
CLE_PARAMETRE_NB_RESULTATS = "recherche_nb_resultats_max"


def obtenir_nb_resultats_max():
    valeur = obtenir_parametre(CLE_PARAMETRE_NB_RESULTATS)
    try:
        return int(valeur) if valeur else NB_RESULTATS_MAX_PAR_CATEGORIE_DEFAUT
    except (TypeError, ValueError):
        return NB_RESULTATS_MAX_PAR_CATEGORIE_DEFAUT


def definir_nb_resultats_max(nombre):
    definir_parametre(CLE_PARAMETRE_NB_RESULTATS, nombre)


def rechercher_partout(athlete_id, texte):
    """Cherche `texte` (insensible à la casse) dans les tables
    principales, pour un athlète donné (ou tous si athlete_id est
    None). Retourne une liste de tuples
    (categorie, nom, date_ou_vide, id_ligne)."""

    if not texte or not texte.strip():
        return []

    motif = f"%{texte.strip()}%"
    resultats = []
    conn = connexion()
    cur = conn.cursor()

    condition_athlete = "AND athlete_id = ?" if athlete_id else ""
    parametres_base = (athlete_id,) if athlete_id else ()
    NB_RESULTATS_MAX_PAR_CATEGORIE = obtenir_nb_resultats_max()

    cur.execute(
        f"SELECT id, nom, date, type FROM activites "
        f"WHERE nom LIKE ? {condition_athlete} ORDER BY date DESC LIMIT ?",
        (motif, *parametres_base, NB_RESULTATS_MAX_PAR_CATEGORIE),
    )
    for id_, nom, date, type_ in cur.fetchall():
        resultats.append(("Activité", nom or type_ or "(sans nom)", date or "", id_))

    cur.execute(
        f"SELECT id, nom, date_prevue FROM seances_structurees "
        f"WHERE nom LIKE ? {condition_athlete} ORDER BY date_prevue DESC LIMIT ?",
        (motif, *parametres_base, NB_RESULTATS_MAX_PAR_CATEGORIE),
    )
    for id_, nom, date in cur.fetchall():
        resultats.append(("Séance", nom, date or "", id_))

    cur.execute(
        f"SELECT id, nom_course, date FROM resultats_courses "
        f"WHERE nom_course LIKE ? {condition_athlete} ORDER BY date DESC LIMIT ?",
        (motif, *parametres_base, NB_RESULTATS_MAX_PAR_CATEGORIE),
    )
    for id_, nom, date in cur.fetchall():
        resultats.append(("Résultat de course", nom, date or "", id_))

    cur.execute(
        f"SELECT id, titre, date_cible FROM objectifs "
        f"WHERE (titre LIKE ? OR description LIKE ?) {condition_athlete} "
        f"ORDER BY date_cible DESC LIMIT ?",
        (motif, motif, *parametres_base, NB_RESULTATS_MAX_PAR_CATEGORIE),
    )
    for id_, titre, date in cur.fetchall():
        resultats.append(("Objectif", titre, date or "", id_))

    cur.execute(
        f"SELECT id, nom, date_ajout FROM parcours_gpx "
        f"WHERE nom LIKE ? {condition_athlete} ORDER BY date_ajout DESC LIMIT ?",
        (motif, *parametres_base, NB_RESULTATS_MAX_PAR_CATEGORIE),
    )
    for id_, nom, date in cur.fetchall():
        resultats.append(("Parcours", nom, date or "", id_))

    conn.close()
    return resultats


class RechercheGlobale(QMainWindow):

    def __init__(self, athlete_id_initial=None):
        super().__init__()

        creer_base_de_donnees()
        charger_polices()

        self.setWindowTitle("TrailMaster Pro – Recherche globale")
        self.resize(1000, 700)
        self.setMinimumSize(800, 550)

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

        principal.addWidget(creer_bouton_retour_tableau_bord(self), 0, Qt.AlignmentFlag.AlignLeft)

        titre = QLabel("🔎 Recherche globale")
        titre.setObjectName("titrePage")
        sous_titre = QLabel(
            "Cherche en même temps dans les activités, séances, résultats de courses, "
            "objectifs et parcours enregistrés."
        )
        sous_titre.setObjectName("sousTitrePage")
        principal.addWidget(titre)
        principal.addWidget(sous_titre)

        barre = QHBoxLayout()
        label_athlete = QLabel("Athlète :")
        label_athlete.setObjectName("labelChamp")
        self.combo_athlete = QComboBox()
        self.combo_athlete.addItem("Tous les athlètes", None)
        for a in obtenir_athletes():
            self.combo_athlete.addItem(f"{a[2]} {a[1]}", a[0])
        if athlete_id_initial is not None:
            for i in range(self.combo_athlete.count()):
                if self.combo_athlete.itemData(i) == athlete_id_initial:
                    self.combo_athlete.setCurrentIndex(i)
                    break

        self.champ_recherche = QLineEdit()
        self.champ_recherche.setPlaceholderText("Nom de sortie, de séance, de course, d'objectif, de parcours…")
        self.champ_recherche.returnPressed.connect(self.lancer_recherche)

        bouton_chercher = QPushButton("🔎 Chercher")
        bouton_chercher.setObjectName("boutonPrincipal")
        bouton_chercher.clicked.connect(self.lancer_recherche)

        barre.addWidget(label_athlete)
        barre.addWidget(self.combo_athlete)
        barre.addWidget(self.champ_recherche, 1)
        barre.addWidget(bouton_chercher)
        principal.addLayout(barre)

        self.label_info = QLabel("Tape un mot puis appuie sur Entrée (ou clique sur Chercher).")
        self.label_info.setObjectName("texteSecondaire")
        principal.addWidget(self.label_info)

        self.table = QTableWidget()
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(["Catégorie", "Nom", "Date"])
        configurer_table_redimensionnable(self.table)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        principal.addWidget(self.table, 1)

        self.setStyleSheet(obtenir_style_ecran())
        self.champ_recherche.setFocus()

    def lancer_recherche(self):
        texte = self.champ_recherche.text().strip()
        self.table.setRowCount(0)

        if not texte:
            self.label_info.setText("Tape un mot puis appuie sur Entrée (ou clique sur Chercher).")
            return

        athlete_id = self.combo_athlete.currentData()
        resultats = rechercher_partout(athlete_id, texte)

        if not resultats:
            self.label_info.setText(f"Aucun résultat pour « {texte} ».")
            return

        self.label_info.setText(f"{len(resultats)} résultat(s) pour « {texte} ».")
        self.table.setRowCount(len(resultats))
        for ligne, (categorie, nom, date, _id) in enumerate(resultats):
            self.table.setItem(ligne, 0, QTableWidgetItem(categorie))
            self.table.setItem(ligne, 1, QTableWidgetItem(nom))
            self.table.setItem(ligne, 2, QTableWidgetItem(date))
