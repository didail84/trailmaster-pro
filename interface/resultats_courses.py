import json

from PySide6.QtWidgets import QDialog, QMessageBox

from interface.ecran_liste import EcranListe, Champ
from interface.seances import DialogueChoixActivite
from interface.apercu_survol import installer_apercu_survol
from noyau.donnees import activites as dact, parcours as dparc  # accès aux données
from noyau.donnees import courses as dcourse


def _calculer_activite_liee(id_ligne, valeurs):
    resultat = dcourse.sortie_du_resultat(id_ligne)

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

    if athlete_id is None:
        ligne_athlete = dcourse.resultat(id_resultat, "athlete_id")
        athlete_id = ligne_athlete[0] if ligne_athlete else None

    activites_recentes = dact.pour_liaison(athlete_id, 50)

    if not activites_recentes:
        QMessageBox.information(ecran, "Aucune activité", "Aucune activité trouvée pour cet athlète.")
        return

    dialogue = DialogueChoixActivite(activites_recentes, ecran)
    if dialogue.exec() != QDialog.DialogCode.Accepted or dialogue.activite_choisie is None:
        return

    activite_id = dialogue.activite_choisie[0]

    dcourse.lier_resultat_a_une_sortie(id_resultat, activite_id)

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
        ligne = dcourse.resultat(id_resultat, "nom_course", "date", "activite_id")
        if not ligne:
            return None
        nom_course, date, activite_id = ligne

        points = []
        if activite_id is not None:
            trace_json = dparc.trace_de_l_activite(activite_id)
            if trace_json:
                points = json.loads(trace_json)

        return (nom_course, date or "", points)
