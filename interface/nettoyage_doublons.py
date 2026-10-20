from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QComboBox,
    QPushButton,
    QFrame,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QCheckBox,
    QMessageBox,
    QScrollArea,
)

from data.database import obtenir_athletes
from interface.ecran_liste import obtenir_style_ecran, configurer_table_redimensionnable
from interface.doublons import detecter_doublons, supprimer_doublons, fusionner_groupe


class NettoyageDoublons(QMainWindow):

    def __init__(self, athlete_id_initial=None):
        super().__init__()

        self.setWindowTitle("TrailMaster Pro – Nettoyage des doublons")
        self.resize(1200, 800)
        self.setMinimumSize(950, 600)

        self.groupes_courants = []
        self.cases_suppression = []
        self.lignes_activites = []

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

        titre = QLabel("🧹  Nettoyage des doublons")
        titre.setObjectName("titrePage")
        sous_titre = QLabel(
            "Repère les activités enregistrées deux fois (même sortie, à quelques minutes "
            "d'écart et distance proche) — utile après une première synchro Strava par exemple, "
            "ou quand une sortie suivie en direct depuis le téléphone est ensuite resynchronisée "
            "depuis une montre Garmin ou Strava."
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

        bouton_rechercher = QPushButton("🔍 Rechercher les doublons")
        bouton_rechercher.setObjectName("boutonPrincipal")
        bouton_rechercher.clicked.connect(self.rechercher_doublons)

        barre.addWidget(label_athlete)
        barre.addWidget(self.combo_athlete)
        barre.addStretch()
        barre.addWidget(bouton_rechercher)
        principal.addLayout(barre)

        self.label_resultat = QLabel("—")
        self.label_resultat.setObjectName("texteSecondaire")
        self.label_resultat.setWordWrap(True)
        principal.addWidget(self.label_resultat)

        self.table = QTableWidget()
        colonnes = ["Supprimer ?", "Groupe", "Date", "Nom", "Type", "Distance (km)", "D+ (m)", "Durée", "Source"]
        self.table.setColumnCount(len(colonnes))
        self.table.setHorizontalHeaderLabels(colonnes)
        configurer_table_redimensionnable(self.table)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        principal.addWidget(self.table, 1)

        barre_actions = QHBoxLayout()
        bouton_supprimer = QPushButton("🗑️ Supprimer les activités cochées")
        bouton_supprimer.setObjectName("boutonSecondaire")
        bouton_supprimer.clicked.connect(self.supprimer_selection)
        bouton_fusionner = QPushButton("🔀 Fusionner automatiquement chaque groupe")
        bouton_fusionner.setObjectName("boutonPrincipal")
        bouton_fusionner.clicked.connect(self.fusionner_tous_les_groupes)
        barre_actions.addWidget(bouton_supprimer)
        barre_actions.addWidget(bouton_fusionner)
        principal.addLayout(barre_actions)

        note_fusion = QLabel(
            "« Fusionner » garde la version la plus fiable de chaque groupe (une source "
            "Garmin/Strava plutôt qu'un suivi en direct par téléphone, la plus complète en cas "
            "d'égalité) et lui rattache tout ce qui était lié aux autres versions (séance liée, "
            "résultat de course, blessure) au lieu de le perdre — recommandé plutôt que "
            "« Supprimer » quand l'une des versions vient d'un suivi en direct."
        )
        note_fusion.setObjectName("texteSecondaire")
        note_fusion.setWordWrap(True)
        principal.addWidget(note_fusion)

        self.setStyleSheet(obtenir_style_ecran())

        if athlete_id_initial is not None:
            for i in range(self.combo_athlete.count()):
                if self.combo_athlete.itemData(i) == athlete_id_initial:
                    self.combo_athlete.setCurrentIndex(i)
                    break

    def _formater_duree(self, secondes):
        if not secondes:
            return "—"
        secondes = int(secondes)
        h, reste = divmod(secondes, 3600)
        m, s = divmod(reste, 60)
        return f"{h}h{m:02d}" if h else f"{m}min"

    def rechercher_doublons(self):
        athlete_id = self.combo_athlete.currentData()
        if athlete_id is None:
            QMessageBox.warning(self, "Athlète requis", "Sélectionne un athlète.")
            return

        self.groupes_courants = detecter_doublons(athlete_id)
        self.table.setRowCount(0)
        self.cases_suppression = []
        self.lignes_activites = []

        if not self.groupes_courants:
            self.label_resultat.setText("Aucun doublon détecté. ✅")
            return

        nb_lignes_total = sum(len(g) for g in self.groupes_courants)
        self.table.setRowCount(nb_lignes_total)

        ligne = 0
        for num_groupe, groupe in enumerate(self.groupes_courants, start=1):
            for position, activite in enumerate(groupe):
                case = QCheckBox()
                case.setChecked(position != 0)
                self.table.setCellWidget(ligne, 0, case)
                self.cases_suppression.append(case)
                self.lignes_activites.append(activite)

                self.table.setItem(ligne, 1, QTableWidgetItem(f"#{num_groupe}"))
                self.table.setItem(ligne, 2, QTableWidgetItem(str(activite["date"])[:16]))
                self.table.setItem(ligne, 3, QTableWidgetItem(activite["nom"] or "—"))
                self.table.setItem(ligne, 4, QTableWidgetItem(activite["type"] or "—"))
                self.table.setItem(ligne, 5, QTableWidgetItem(f"{activite['distance']:.2f}"))
                self.table.setItem(ligne, 6, QTableWidgetItem(str(activite["denivele"])))
                self.table.setItem(ligne, 7, QTableWidgetItem(self._formater_duree(activite["duree"])))
                self.table.setItem(ligne, 8, QTableWidgetItem(activite["source"] or "—"))

                ligne += 1

        self.table.resizeColumnsToContents()
        self.label_resultat.setText(
            f"{len(self.groupes_courants)} groupe(s) de doublons, {nb_lignes_total} activités concernées. "
            "La case est précochée sur la version la moins complète de chaque groupe — vérifie avant de supprimer."
        )

    def supprimer_selection(self):
        ids_a_supprimer = [
            activite["id"]
            for case, activite in zip(self.cases_suppression, self.lignes_activites)
            if case.isChecked()
        ]

        if not ids_a_supprimer:
            QMessageBox.information(self, "Rien à supprimer", "Aucune activité n'est cochée.")
            return

        confirmation = QMessageBox.question(
            self, "Confirmer la suppression",
            f"Supprimer définitivement {len(ids_a_supprimer)} activité(s) (et leur trace GPS "
            "associée le cas échéant) ?"
        )
        if confirmation != QMessageBox.StandardButton.Yes:
            return

        supprimer_doublons(ids_a_supprimer)
        QMessageBox.information(self, "Terminé", f"{len(ids_a_supprimer)} activité(s) supprimée(s).")
        self.rechercher_doublons()

    def fusionner_tous_les_groupes(self):
        if not self.groupes_courants:
            QMessageBox.information(
                self, "Rien à fusionner",
                "Lance d'abord une recherche de doublons."
            )
            return

        confirmation = QMessageBox.question(
            self, "Confirmer la fusion",
            f"Fusionner les {len(self.groupes_courants)} groupe(s) de doublons détectés ? "
            "Pour chaque groupe, la version la plus fiable est gardée (une source Garmin/Strava "
            "plutôt qu'un suivi en direct par téléphone) et les autres versions y sont fusionnées "
            "(séance/résultat de course/blessure liés reportés dessus) puis supprimées."
        )
        if confirmation != QMessageBox.StandardButton.Yes:
            return

        nb_groupes_fusionnes = 0
        for groupe in self.groupes_courants:
            if fusionner_groupe(groupe) is not None:
                nb_groupes_fusionnes += 1

        QMessageBox.information(
            self, "Terminé",
            f"{nb_groupes_fusionnes} groupe(s) fusionné(s)."
        )
        self.rechercher_doublons()
