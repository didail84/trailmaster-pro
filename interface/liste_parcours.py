"""
Liste des parcours enregistrés (table parcours_gpx) — vue d'ensemble
qui manquait : jusqu'ici un parcours n'était consultable qu'un par un,
via le sélecteur de Carte réelle. Ici, on les voit tous, avec un
aperçu au survol (croquis instantané puis vraie carte satellite) sans
avoir à cliquer sur chacun.
"""

import json

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QComboBox,
    QTableWidget,
    QTableWidgetItem,
    QFrame,
    QScrollArea,
    QHeaderView,
    QMessageBox,
)

from data.database import connexion, creer_base_de_donnees, obtenir_athletes
from interface.ecran_liste import obtenir_style_ecran, configurer_table_redimensionnable
from interface.theme import charger_polices
from interface.apercu_survol import installer_apercu_survol


class ListeParcours(QMainWindow):

    def __init__(self, athlete_id_initial=None):
        super().__init__()

        creer_base_de_donnees()
        charger_polices()

        self.setWindowTitle("TrailMaster Pro – Mes parcours")
        self.resize(1100, 750)
        self.setMinimumSize(850, 550)

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

        titre = QLabel("📍 Mes parcours")
        titre.setObjectName("titrePage")
        sous_titre = QLabel(
            "Tous les parcours enregistrés — laisse la souris sur une ligne pour voir "
            "le tracé (croquis instantané puis carte satellite), sans cliquer."
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
        self.combo_athlete.currentIndexChanged.connect(self.charger_parcours)

        bouton_actualiser = QPushButton("🔄 Actualiser")
        bouton_actualiser.setObjectName("boutonSecondaire")
        bouton_actualiser.clicked.connect(self.charger_parcours)

        barre.addWidget(label_athlete)
        barre.addWidget(self.combo_athlete)
        barre.addStretch()
        barre.addWidget(bouton_actualiser)
        principal.addLayout(barre)

        self.label_info = QLabel("")
        self.label_info.setObjectName("texteSecondaire")
        principal.addWidget(self.label_info)

        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["Nom", "Distance", "D+ / D-", "Date d'ajout", "Origine"])
        configurer_table_redimensionnable(self.table)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        principal.addWidget(self.table, 1)

        barre_actions = QHBoxLayout()
        bouton_ouvrir_carte = QPushButton("🗺️ Ouvrir sur Carte réelle")
        bouton_ouvrir_carte.setObjectName("boutonPrincipal")
        bouton_ouvrir_carte.clicked.connect(self.ouvrir_sur_carte_reelle)
        bouton_supprimer = QPushButton("Supprimer")
        bouton_supprimer.setObjectName("boutonSecondaire")
        bouton_supprimer.clicked.connect(self.supprimer_parcours)
        barre_actions.addWidget(bouton_ouvrir_carte)
        barre_actions.addWidget(bouton_supprimer)
        barre_actions.addStretch()
        principal.addLayout(barre_actions)

        self.setStyleSheet(obtenir_style_ecran())

        self._apercu = installer_apercu_survol(
            self.table, self._id_pour_ligne, self._apercu_pour_parcours
        )

        self._lignes_ids = []
        self.charger_parcours()

    def _id_pour_ligne(self, ligne):
        if 0 <= ligne < len(self._lignes_ids):
            return self._lignes_ids[ligne]
        return None

    def _apercu_pour_parcours(self, parcours_id):
        conn = connexion()
        cur = conn.cursor()
        cur.execute("SELECT nom, distance_km, trace_json FROM parcours_gpx WHERE id=?", (parcours_id,))
        ligne = cur.fetchone()
        conn.close()
        if not ligne:
            return None
        nom, distance, trace_json = ligne
        points = json.loads(trace_json) if trace_json else []
        sous_texte = f"{distance} km" if distance else ""
        return (nom, sous_texte, points)

    def charger_parcours(self):
        athlete_id = self.combo_athlete.currentData()

        conn = connexion()
        cur = conn.cursor()
        if athlete_id is None:
            cur.execute(
                "SELECT id, nom, distance_km, denivele_positif, denivele_negatif, "
                "date_ajout, activite_id FROM parcours_gpx ORDER BY date_ajout DESC LIMIT 500"
            )
        else:
            cur.execute(
                "SELECT id, nom, distance_km, denivele_positif, denivele_negatif, "
                "date_ajout, activite_id FROM parcours_gpx WHERE athlete_id=? "
                "ORDER BY date_ajout DESC LIMIT 500",
                (athlete_id,),
            )
        lignes = cur.fetchall()
        conn.close()

        self._lignes_ids = [l[0] for l in lignes]
        self.table.setRowCount(len(lignes))

        for i, (_id, nom, distance, dplus, dmoins, date_ajout, activite_id) in enumerate(lignes):
            self.table.setItem(i, 0, QTableWidgetItem(nom or "(sans nom)"))
            self.table.setItem(i, 1, QTableWidgetItem(f"{distance} km" if distance else "—"))
            self.table.setItem(
                i, 2, QTableWidgetItem(f"+{dplus or 0} m / -{dmoins or 0} m")
            )
            self.table.setItem(i, 3, QTableWidgetItem(str(date_ajout or "")[:16]))
            self.table.setItem(
                i, 4, QTableWidgetItem("Sortie enregistrée" if activite_id else "Parcours créé")
            )

        self.label_info.setText(f"{len(lignes)} parcours enregistré(s).")

    def ouvrir_sur_carte_reelle(self):
        ligne = self.table.currentRow()
        if ligne < 0:
            QMessageBox.information(self, "Sélection requise", "Sélectionne d'abord un parcours.")
            return

        from interface.carte_reelle import CarteReelle

        parcours_id = self._lignes_ids[ligne]
        athlete_id = self.combo_athlete.currentData()
        self._fenetre_carte = CarteReelle(
            athlete_id_initial=athlete_id, parcours_id_initial=parcours_id
        )
        self._fenetre_carte.show()

    def supprimer_parcours(self):
        ligne = self.table.currentRow()
        if ligne < 0:
            QMessageBox.information(self, "Sélection requise", "Sélectionne d'abord un parcours.")
            return

        parcours_id = self._lignes_ids[ligne]
        nom = self.table.item(ligne, 0).text()

        reponse = QMessageBox.question(
            self, "Confirmer la suppression",
            f"Supprimer le parcours « {nom} » ? Cette action est irréversible "
            "(si ce parcours est lié à une sortie enregistrée, la sortie elle-même n'est pas touchée).",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reponse != QMessageBox.StandardButton.Yes:
            return

        conn = connexion()
        cur = conn.cursor()
        cur.execute("DELETE FROM parcours_gpx WHERE id=?", (parcours_id,))
        conn.commit()
        conn.close()

        self.charger_parcours()
