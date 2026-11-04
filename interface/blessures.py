from PySide6.QtWidgets import QDialog, QMessageBox

from interface.ecran_liste import EcranListe, Champ
from interface.seances import DialogueChoixActivite
from noyau.donnees import activites as dact  # accès aux données
from noyau.donnees import blessures as dbles


def _calculer_origine(id_ligne, valeurs):
    resultat = dbles.origine(id_ligne)

    if not resultat:
        return "Saisie manuelle"

    date_act, type_act, distance_act, date_muscu, exercice, groupe = resultat

    if date_act:
        return f"Sortie {type_act or ''} du {str(date_act)[:10]} ({distance_act or 0} km)"
    if date_muscu:
        détail = exercice or groupe or "séance"
        return f"Musculation — {détail} du {str(date_muscu)[:10]}"
    return "Saisie manuelle"


def _lier_activite(ecran):
    ligne = ecran.table.currentRow()
    if ligne < 0:
        QMessageBox.information(ecran, "Sélection requise", "Sélectionne d'abord une blessure.")
        return

    id_blessure = ecran.lignes_ids[ligne]
    athlete_id = ecran.athlete_selectionne_id()

    if athlete_id is None:
        ligne_athlete = dbles.valeurs(id_blessure, "athlete_id")
        athlete_id = ligne_athlete[0] if ligne_athlete else None

    activites_recentes = dact.pour_liaison(athlete_id, 50)

    if not activites_recentes:
        QMessageBox.information(ecran, "Aucune activité", "Aucune activité trouvée pour cet athlète.")
        return

    dialogue = DialogueChoixActivite(activites_recentes, ecran)
    if dialogue.exec() != QDialog.DialogCode.Accepted or dialogue.activite_choisie is None:
        return

    activite_id = dialogue.activite_choisie[0]

    dbles.lier_a_une_sortie(id_blessure, activite_id)

    QMessageBox.information(ecran, "Liée", "La blessure est maintenant liée à cette sortie.")
    ecran.charger_donnees()


class Blessures(EcranListe):

    def __init__(self, athlete_id_initial=None):
        champs = [
            Champ("date_debut", "Date début", "date", obligatoire=True),
            Champ("date_fin", "Date fin", "date"),
            Champ("zone_corporelle", "Zone", "texte", obligatoire=True),
            Champ("type_blessure", "Type de blessure", "texte"),
            Champ(
                "gravite", "Gravité", "choix",
                choix=["Légère", "Modérée", "Sévère"],
            ),
            Champ("cause", "Cause probable", "texte"),
            Champ(
                "statut", "Statut", "choix",
                choix=["En cours", "En reprise", "Guérie"],
            ),
            Champ("notes", "Notes", "texte_long"),
        ]
        super().__init__(
            titre="Blessures",
            sous_titre="Historique des blessures, causes et reprise",
            icone="🩹",
            table_sql="blessures",
            champs=champs,
            athlete_id_initial=athlete_id_initial,
            tri="date_debut DESC",
            colonnes_calculees=[
                {"label": "Origine", "fonction": _calculer_origine},
            ],
            bouton_extra=("🔗 Lier une sortie", _lier_activite),
        )
