import json

from PySide6.QtWidgets import QDialog, QMessageBox

from data.database import connexion
from interface.ecran_liste import EcranListe, Champ
from interface.seances import DialogueChoixActivite
from interface.apercu_survol import installer_apercu_survol


def _calculer_activite_liee(id_ligne, valeurs):
    conn = connexion()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT a.date, a.distance FROM resultats_courses r
        LEFT JOIN activites a ON r.activite_id = a.id
        WHERE r.id=? AND r.activite_id IS NOT NULL
        """,
        (id_ligne,),
    )
    resultat = cur.fetchone()
    conn.close()

    if not resultat:
        return "Non liée"

    date_activite, distance_activite = resultat
    return f"Oui ({str(date_activite)[:10]}, {distance_activite} km)"


def _lier_activite(ecran):
    ligne = ecran.table.currentRow()
    if ligne < 0:
        QMessageBox.information(ecran, "Sélection requise", "Sélectionne d'abord un résultat de course.")
        return

    id_resultat = ecran.lignes_ids[ligne]
    athlete_id = ecran.athlete_selectionne_id()

    conn = connexion()
    cur = conn.cursor()

    if athlete_id is None:
        cur.execute("SELECT athlete_id FROM resultats_courses WHERE id=?", (id_resultat,))
        ligne_athlete = cur.fetchone()
        athlete_id = ligne_athlete[0] if ligne_athlete else None

    cur.execute(
        "SELECT id, date, type, distance, duree FROM activites "
        "WHERE athlete_id=? ORDER BY date DESC LIMIT 50",
        (athlete_id,),
    )
    activites_recentes = cur.fetchall()
    conn.close()

    if not activites_recentes:
        QMessageBox.information(ecran, "Aucune activité", "Aucune activité trouvée pour cet athlète.")
        return

    dialogue = DialogueChoixActivite(activites_recentes, ecran)
    if dialogue.exec() != QDialog.DialogCode.Accepted or dialogue.activite_choisie is None:
        return

    activite_id = dialogue.activite_choisie[0]

    conn = connexion()
    cur = conn.cursor()
    cur.execute("UPDATE resultats_courses SET activite_id=? WHERE id=?", (activite_id, id_resultat))
    conn.commit()
    conn.close()

    QMessageBox.information(ecran, "Liée", "Le résultat de course est maintenant lié à cette activité.")
    ecran.charger_donnees()


class ResultatsCourses(EcranListe):

    def __init__(self, athlete_id_initial=None):
        champs = [
            Champ("nom_course", "Course", "texte", obligatoire=True),
            Champ("date", "Date", "date", obligatoire=True),
            Champ("distance", "Distance (km)", "decimal"),
            Champ("denivele", "D+ (m)", "entier"),
            Champ("temps", "Temps (hh:mm:ss)", "texte"),
            Champ("classement_general", "Classement général", "entier"),
            Champ("classement_categorie", "Classement catégorie", "entier"),
            Champ(
                "objectif_atteint", "Objectif atteint", "choix",
                choix=["Oui", "Partiel", "Non"],
            ),
            Champ("notes", "Notes", "texte_long"),
        ]
        super().__init__(
            titre="Résultats de courses",
            sous_titre="Historique des compétitions et performances",
            icone="🏆",
            table_sql="resultats_courses",
            champs=champs,
            athlete_id_initial=athlete_id_initial,
            tri="date DESC",
            colonnes_calculees=[
                {"label": "Activité GPS liée", "fonction": _calculer_activite_liee},
            ],
            bouton_extra=("🔗 Lier une activité", _lier_activite),
        )

        self._apercu = installer_apercu_survol(
            self.table, self._id_resultat_pour_ligne, self._apercu_pour_resultat
        )

    def _id_resultat_pour_ligne(self, ligne):
        if 0 <= ligne < len(self.lignes_ids):
            return self.lignes_ids[ligne]
        return None

    def _apercu_pour_resultat(self, id_resultat):
        conn = connexion()
        cur = conn.cursor()
        cur.execute(
            "SELECT nom_course, date, activite_id FROM resultats_courses WHERE id=?",
            (id_resultat,),
        )
        ligne = cur.fetchone()
        if not ligne:
            conn.close()
            return None
        nom_course, date, activite_id = ligne

        points = []
        if activite_id is not None:
            cur.execute(
                "SELECT trace_json FROM parcours_gpx WHERE activite_id=? LIMIT 1", (activite_id,)
            )
            resultat = cur.fetchone()
            if resultat and resultat[0]:
                points = json.loads(resultat[0])
        conn.close()

        return (nom_course, date or "", points)
