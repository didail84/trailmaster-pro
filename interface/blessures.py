from PySide6.QtWidgets import QDialog, QMessageBox

from data.database import connexion
from interface.ecran_liste import EcranListe, Champ
from interface.seances import DialogueChoixActivite


def _calculer_origine(id_ligne, valeurs):
    conn = connexion()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT a.date, a.type, a.distance, m.date, m.exercice, m.groupe_musculaire
        FROM blessures b
        LEFT JOIN activites a ON b.activite_id = a.id
        LEFT JOIN musculation_suivi m ON b.musculation_suivi_id = m.id
        WHERE b.id=?
        """,
        (id_ligne,),
    )
    resultat = cur.fetchone()
    conn.close()

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

    conn = connexion()
    cur = conn.cursor()

    if athlete_id is None:
        cur.execute("SELECT athlete_id FROM blessures WHERE id=?", (id_blessure,))
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
    cur.execute(
        "UPDATE blessures SET activite_id=?, musculation_suivi_id=NULL WHERE id=?",
        (activite_id, id_blessure),
    )
    conn.commit()
    conn.close()

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
