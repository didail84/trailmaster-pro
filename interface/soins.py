"""
Suivi des soins d'entretien ou de rééducation : massage, kinésithérapeute,
ostéopathe... — séparé des Blessures (qui suivent une blessure du début à
la guérison) car un soin peut aussi être un simple entretien préventif
sans blessure associée. Un soin peut néanmoins être relié à une fiche
Blessure existante quand il en découle (ex. suivi de kiné le sur une
tendinite déjà enregistrée).
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QTableWidget,
    QTableWidgetItem,
    QDialogButtonBox,
    QMessageBox,
)

from data.database import connexion
from interface.ecran_liste import EcranListe, Champ, configurer_table_redimensionnable


def _calculer_blessure_liee(id_ligne, valeurs):
    conn = connexion()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT b.zone_corporelle, b.type_blessure, b.date_debut
        FROM soins s
        LEFT JOIN blessures b ON s.blessure_id = b.id
        WHERE s.id=?
        """,
        (id_ligne,),
    )
    resultat = cur.fetchone()
    conn.close()

    if not resultat or resultat[0] is None:
        return "—"

    zone, type_blessure, date_debut = resultat
    détail = type_blessure or "blessure"
    return f"{zone or ''} — {détail} ({str(date_debut)[:10]})"


class DialogueChoixBlessure(QDialog):
    """Petite fenêtre de sélection d'une blessure existante parmi une liste."""

    def __init__(self, blessures, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Choisir la blessure liée")
        self.resize(500, 400)
        self.blessure_choisie = None

        layout = QVBoxLayout(self)

        self.liste = QTableWidget()
        self.liste.setColumnCount(4)
        self.liste.setHorizontalHeaderLabels(["Date début", "Zone", "Type", "Statut"])
        configurer_table_redimensionnable(self.liste)
        self.liste.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.liste.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.liste.setRowCount(len(blessures))

        self.blessures = blessures
        for i, (id_, date_debut, zone, type_blessure, statut) in enumerate(blessures):
            self.liste.setItem(i, 0, QTableWidgetItem(str(date_debut)[:10]))
            self.liste.setItem(i, 1, QTableWidgetItem(zone or ""))
            self.liste.setItem(i, 2, QTableWidgetItem(type_blessure or ""))
            self.liste.setItem(i, 3, QTableWidgetItem(statut or ""))
        self.liste.resizeColumnsToContents()

        layout.addWidget(self.liste)

        boutons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        boutons.accepted.connect(self._valider)
        boutons.rejected.connect(self.reject)
        layout.addWidget(boutons)

    def _valider(self):
        ligne = self.liste.currentRow()
        if ligne < 0:
            QMessageBox.information(self, "Sélection requise", "Sélectionne une blessure.")
            return
        self.blessure_choisie = self.blessures[ligne]
        self.accept()


def _lier_blessure(ecran):
    ligne = ecran.table.currentRow()
    if ligne < 0:
        QMessageBox.information(ecran, "Sélection requise", "Sélectionne d'abord un soin.")
        return

    id_soin = ecran.lignes_ids[ligne]
    athlete_id = ecran.athlete_selectionne_id()

    conn = connexion()
    cur = conn.cursor()

    if athlete_id is None:
        cur.execute("SELECT athlete_id FROM soins WHERE id=?", (id_soin,))
        ligne_athlete = cur.fetchone()
        athlete_id = ligne_athlete[0] if ligne_athlete else None

    cur.execute(
        "SELECT id, date_debut, zone_corporelle, type_blessure, statut FROM blessures "
        "WHERE athlete_id=? ORDER BY date_debut DESC LIMIT 50",
        (athlete_id,),
    )
    blessures_recentes = cur.fetchall()
    conn.close()

    if not blessures_recentes:
        QMessageBox.information(
            ecran, "Aucune blessure",
            "Aucune blessure enregistrée pour cet athlète — ajoute-la d'abord dans l'onglet Blessures.",
        )
        return

    dialogue = DialogueChoixBlessure(blessures_recentes, ecran)
    if dialogue.exec() != QDialog.DialogCode.Accepted or dialogue.blessure_choisie is None:
        return

    blessure_id = dialogue.blessure_choisie[0]

    conn = connexion()
    cur = conn.cursor()
    cur.execute("UPDATE soins SET blessure_id=?, motif='Blessure' WHERE id=?", (blessure_id, id_soin))
    conn.commit()
    conn.close()

    QMessageBox.information(ecran, "Lié", "Le soin est maintenant lié à cette blessure.")
    ecran.charger_donnees()


class Soins(EcranListe):

    def __init__(self, athlete_id_initial=None):
        champs = [
            Champ("date", "Date", "date", obligatoire=True),
            Champ(
                "type_soin", "Type de soin", "choix",
                choix=["Massage", "Kinésithérapeute", "Ostéopathe", "Autre"],
            ),
            Champ(
                "motif", "Motif", "choix",
                choix=["Entretien", "Blessure"],
            ),
            Champ("praticien", "Praticien", "texte"),
            Champ("notes", "Notes", "texte_long"),
        ]
        super().__init__(
            titre="Soins",
            sous_titre="Massages, kinésithérapeute, ostéopathe — entretien ou suivi de blessure",
            icone="💆",
            table_sql="soins",
            champs=champs,
            athlete_id_initial=athlete_id_initial,
            tri="date DESC",
            colonnes_calculees=[
                {"label": "Blessure liée", "fonction": _calculer_blessure_liee},
            ],
            bouton_extra=("🔗 Lier une blessure", _lier_blessure),
        )
