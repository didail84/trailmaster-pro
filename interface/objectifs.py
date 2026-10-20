from datetime import date

from PySide6.QtWidgets import QDialog, QMessageBox

from data.database import connexion, affichage_simplifie_actif
from interface.ecran_liste import EcranListe, Champ, configurer_table_redimensionnable
from interface.date_utils import parser_date_flexible
from interface.dialogue_tactique_course import DialogueTactiqueCourse


def _calculer_resultat_lie(id_ligne, valeurs):
    conn = connexion()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT r.nom_course, r.date, r.classement_general
        FROM objectifs o
        LEFT JOIN resultats_courses r ON o.resultat_id = r.id
        WHERE o.id=? AND o.resultat_id IS NOT NULL
        """,
        (id_ligne,),
    )
    resultat = cur.fetchone()
    conn.close()

    if not resultat:
        return "Non lié"

    nom_course, date_course, classement = resultat
    texte = f"{nom_course or '—'} ({str(date_course)[:10]})"
    if classement:
        texte += f" — {classement}e"
    return texte


def _calculer_echeance(id_ligne, valeurs):
    # valeurs correspond à l'ordre des champs déclarés ci-dessous :
    # (titre, description, date_cible, type_objectif, statut, priorite, resultat_id)
    date_cible_texte = valeurs[2]
    statut = valeurs[4]

    if statut == "Atteint":
        return "🎯 Atteint"
    if statut == "Abandonné":
        return "—"

    date_cible = parser_date_flexible(date_cible_texte)
    if date_cible is None:
        return "—"

    jours_restants = (date_cible.date() - date.today()).days
    if jours_restants < 0:
        return f"Passé de {abs(jours_restants)} j"
    if jours_restants == 0:
        return "Aujourd'hui !"
    return f"J-{jours_restants}"


def _lier_resultat(ecran):
    ligne = ecran.table.currentRow()
    if ligne < 0:
        QMessageBox.information(ecran, "Sélection requise", "Sélectionne d'abord un objectif.")
        return

    id_objectif = ecran.lignes_ids[ligne]
    athlete_id = ecran.athlete_selectionne_id()

    conn = connexion()
    cur = conn.cursor()

    if athlete_id is None:
        cur.execute("SELECT athlete_id FROM objectifs WHERE id=?", (id_objectif,))
        ligne_athlete = cur.fetchone()
        athlete_id = ligne_athlete[0] if ligne_athlete else None

    cur.execute(
        "SELECT id, nom_course, date, classement_general FROM resultats_courses "
        "WHERE athlete_id=? ORDER BY date DESC LIMIT 50",
        (athlete_id,),
    )
    resultats_recents = cur.fetchall()
    conn.close()

    if not resultats_recents:
        QMessageBox.information(
            ecran, "Aucun résultat",
            "Aucun résultat de course enregistré pour cet athlète — "
            "ajoute-le d'abord dans « Résultats de courses »."
        )
        return

    dialogue = DialogueChoixResultat(resultats_recents, ecran)
    if dialogue.exec() != QDialog.DialogCode.Accepted or dialogue.resultat_choisi is None:
        return

    resultat_id = dialogue.resultat_choisi[0]

    conn = connexion()
    cur = conn.cursor()
    cur.execute(
        "UPDATE objectifs SET resultat_id=?, statut='Atteint' WHERE id=?",
        (resultat_id, id_objectif),
    )
    conn.commit()
    conn.close()

    QMessageBox.information(
        ecran, "Objectif atteint 🎯",
        "L'objectif est maintenant lié à ce résultat de course et marqué « Atteint »."
    )
    ecran.charger_donnees()


def _analyser_tactique(ecran):
    ligne = ecran.table.currentRow()
    if ligne < 0:
        QMessageBox.information(ecran, "Sélection requise", "Sélectionne d'abord un objectif.")
        return

    id_objectif = ecran.lignes_ids[ligne]

    conn = connexion()
    cur = conn.cursor()
    cur.execute(
        "SELECT titre, date_cible, type_objectif, athlete_id FROM objectifs WHERE id=?",
        (id_objectif,),
    )
    ligne_objectif = cur.fetchone()
    conn.close()

    if not ligne_objectif:
        return
    titre, date_cible, type_objectif, athlete_id = ligne_objectif

    if type_objectif != "Course":
        QMessageBox.information(
            ecran, "Objectif non concerné",
            "Cette analyse est destinée aux objectifs de type « Course ». "
            "Change le type de cet objectif si c'en est bien une."
        )
        return
    if athlete_id is None:
        QMessageBox.information(
            ecran, "Athlète requis",
            "Cet objectif n'est rattaché à aucun athlète précis — sélectionne un athlète "
            "avant de créer ce type d'objectif."
        )
        return

    dialogue = DialogueTactiqueCourse(id_objectif, athlete_id, titre, date_cible, parent=ecran)
    dialogue.exec()


class Objectifs(EcranListe):

    def __init__(self, athlete_id_initial=None):
        champs = [
            Champ("titre", "Titre", "texte", obligatoire=True),
            Champ("description", "Description", "texte_long"),
            Champ("date_cible", "Date cible", "date"),
            Champ(
                "type_objectif", "Type", "choix",
                choix=["Course", "Performance", "Santé", "Autre"],
            ),
            Champ(
                "statut", "Statut", "choix",
                choix=["À venir", "En cours", "Atteint", "Abandonné"],
            ),
            Champ(
                "priorite", "Priorité", "choix",
                choix=["Haute", "Moyenne", "Basse"],
            ),
        ]
        super().__init__(
            titre="Objectifs",
            sous_titre="Objectifs de course, de performance et de santé",
            icone="🎯",
            table_sql="objectifs",
            champs=champs,
            athlete_id_initial=athlete_id_initial,
            tri="date_cible ASC",
            colonnes_calculees=[
                {"label": "Résultat lié", "fonction": _calculer_resultat_lie},
                {"label": "Échéance", "fonction": _calculer_echeance},
            ],
            bouton_extra=(
                [("🔗 Lier un résultat de course", _lier_resultat)]
                if affichage_simplifie_actif()
                else [
                    ("🔗 Lier un résultat de course", _lier_resultat),
                    ("🤖 Analyser la tactique de course", _analyser_tactique),
                ]
            ),
        )


class DialogueChoixResultat(QDialog):
    """Petite fenêtre de sélection d'un résultat de course parmi une liste
    — même mécanique que DialogueChoixActivite (interface/seances.py)."""

    def __init__(self, resultats, parent=None):
        from PySide6.QtWidgets import (
            QVBoxLayout, QTableWidget, QTableWidgetItem, QHeaderView,
            QDialogButtonBox,
        )

        super().__init__(parent)
        self.setWindowTitle("Choisir le résultat de course")
        self.resize(500, 400)
        self.resultat_choisi = None

        layout = QVBoxLayout(self)

        self.liste = QTableWidget()
        self.liste.setColumnCount(3)
        self.liste.setHorizontalHeaderLabels(["Course", "Date", "Classement"])
        configurer_table_redimensionnable(self.liste)
        self.liste.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.liste.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.liste.setRowCount(len(resultats))

        self.resultats = resultats
        for i, (id_, nom_course, date_, classement) in enumerate(resultats):
            self.liste.setItem(i, 0, QTableWidgetItem(nom_course or "—"))
            self.liste.setItem(i, 1, QTableWidgetItem(str(date_)[:10] if date_ else "—"))
            self.liste.setItem(i, 2, QTableWidgetItem(str(classement) if classement else "—"))

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
            QMessageBox.information(self, "Sélection requise", "Sélectionne un résultat.")
            return
        self.resultat_choisi = self.resultats[ligne]
        self.accept()
