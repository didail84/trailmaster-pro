"""
Petite fenêtre pour ajouter une sortie à la main — notamment pour
transformer un jour affiché comme « Repos » (aucune activité enregistrée
ce jour-là) en une vraie sortie, quand on a oublié de l'importer ou de
la synchroniser depuis Strava/la montre.

Ouverte en double-cliquant sur un jour de repos, dans l'historique des
activités ou dans le calendrier des sorties — la date du jour cliqué est
pré-remplie mais reste modifiable.
"""

from PySide6.QtCore import Qt, QDate
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QFormLayout, QHBoxLayout, QLabel, QLineEdit,
    QComboBox, QDateEdit, QSpinBox, QDoubleSpinBox, QTextEdit, QPushButton,
    QMessageBox,
)

from data.database import creer_activite_manuelle
from interface.ecran_liste import obtenir_style_ecran


TYPES_ACTIVITE = ["Trail", "Course", "VTT", "Vélo", "Randonnée", "Route", "Cardio machine", "Autre"]


class DialogueNouvelleActivite(QDialog):

    def __init__(self, athlete_id, date_iso=None, parent=None, au_enregistrement=None):
        super().__init__(parent)
        self.athlete_id = athlete_id
        self.au_enregistrement = au_enregistrement

        self.setWindowTitle("TrailMaster Pro – Nouvelle sortie")
        self.resize(420, 420)

        layout = QVBoxLayout(self)

        titre = QLabel("➕ Ajouter une sortie")
        titre.setObjectName("titreCarte")
        layout.addWidget(titre)

        note = QLabel(
            "Transforme un jour de repos en sortie quand elle n'a pas été "
            "importée/synchronisée automatiquement."
        )
        note.setObjectName("texteSecondaire")
        note.setWordWrap(True)
        layout.addWidget(note)

        formulaire = QFormLayout()

        self.champ_date = QDateEdit()
        self.champ_date.setCalendarPopup(True)
        if date_iso:
            self.champ_date.setDate(QDate.fromString(date_iso[:10], "yyyy-MM-dd"))
        else:
            self.champ_date.setDate(QDate.currentDate())
        formulaire.addRow("Date :", self.champ_date)

        self.combo_type = QComboBox()
        self.combo_type.addItems(TYPES_ACTIVITE)
        formulaire.addRow("Type :", self.combo_type)

        self.champ_nom = QLineEdit()
        self.champ_nom.setPlaceholderText("Ex. Sortie facile en forêt")
        formulaire.addRow("Nom :", self.champ_nom)

        self.champ_distance = QDoubleSpinBox()
        self.champ_distance.setRange(0, 400)
        self.champ_distance.setDecimals(1)
        self.champ_distance.setSuffix(" km")
        formulaire.addRow("Distance :", self.champ_distance)

        self.champ_denivele = QSpinBox()
        self.champ_denivele.setRange(0, 20000)
        self.champ_denivele.setSuffix(" m")
        formulaire.addRow("D+ :", self.champ_denivele)

        self.champ_duree = QSpinBox()
        self.champ_duree.setRange(0, 2000)
        self.champ_duree.setSuffix(" min")
        formulaire.addRow("Durée :", self.champ_duree)

        self.champ_notes = QTextEdit()
        self.champ_notes.setPlaceholderText("Notes (optionnel)")
        self.champ_notes.setMaximumHeight(80)
        formulaire.addRow("Notes :", self.champ_notes)

        layout.addLayout(formulaire)

        barre_boutons = QHBoxLayout()
        bouton_annuler = QPushButton("Annuler")
        bouton_annuler.clicked.connect(self.reject)
        bouton_enregistrer = QPushButton("💾 Enregistrer")
        bouton_enregistrer.setObjectName("boutonPrincipal")
        bouton_enregistrer.clicked.connect(self.enregistrer)
        barre_boutons.addStretch()
        barre_boutons.addWidget(bouton_annuler)
        barre_boutons.addWidget(bouton_enregistrer)
        layout.addLayout(barre_boutons)

        self.setStyleSheet(obtenir_style_ecran())

    def enregistrer(self):
        if self.athlete_id is None:
            QMessageBox.warning(self, "Athlète requis", "Aucun athlète sélectionné.")
            return

        date_iso = self.champ_date.date().toString("yyyy-MM-dd")
        creer_activite_manuelle(
            self.athlete_id,
            date_iso,
            self.champ_nom.text().strip() or None,
            self.combo_type.currentText(),
            distance_km=self.champ_distance.value() or None,
            denivele_m=self.champ_denivele.value() or None,
            duree_min=self.champ_duree.value() or None,
            notes=self.champ_notes.toPlainText().strip() or None,
        )

        if self.au_enregistrement:
            self.au_enregistrement()

        self.accept()
