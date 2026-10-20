from data.database import connexion
from interface.ecran_liste import EcranListe, Champ


# Types d'activités pertinents pour calculer l'usure réelle de chaque
# catégorie de matériel — None = toutes les activités comptent.
TYPES_MATERIEL_VERS_ACTIVITES = {
    "Chaussures": ["Trail", "Course", "Randonnée"],
    "Bâtons": ["Trail", "Randonnée"],
    "Sac à dos": ["Trail", "Course", "Randonnée", "VTT"],
}


def _calculer_km_reel(id_ligne, valeurs):
    nom, type_materiel, date_achat, km_actuels, km_max, statut, notes = valeurs

    if not date_achat:
        return "— (pas de date d'achat)"

    conn = connexion()
    cur = conn.cursor()
    cur.execute("SELECT athlete_id FROM materiel WHERE id=?", (id_ligne,))
    resultat = cur.fetchone()
    if not resultat:
        conn.close()
        return "—"
    athlete_id = resultat[0]

    types_pertinents = TYPES_MATERIEL_VERS_ACTIVITES.get(type_materiel)
    if types_pertinents:
        marqueurs = ",".join("?" * len(types_pertinents))
        cur.execute(
            f"SELECT SUM(distance) FROM activites WHERE athlete_id=? AND date >= ? "
            f"AND type IN ({marqueurs})",
            (athlete_id, date_achat, *types_pertinents),
        )
    else:
        cur.execute(
            "SELECT SUM(distance) FROM activites WHERE athlete_id=? AND date >= ?",
            (athlete_id, date_achat),
        )
    total = cur.fetchone()[0]
    conn.close()

    return f"{round(total or 0, 1)} km"


class Materiel(EcranListe):

    def __init__(self, athlete_id_initial=None):
        champs = [
            Champ("nom", "Nom", "texte", obligatoire=True),
            Champ(
                "type", "Type", "choix",
                choix=["Chaussures", "Sac à dos", "Vêtement", "Montre GPS", "Bâtons", "Autre"],
            ),
            Champ("date_achat", "Date d'achat", "date"),
            Champ("km_actuels", "Km parcourus (saisi)", "decimal"),
            Champ("km_max_recommande", "Km max recommandé", "decimal"),
            Champ(
                "statut", "Statut", "choix",
                choix=["Actif", "À surveiller", "Retiré"],
            ),
            Champ("notes", "Notes", "texte_long"),
        ]
        super().__init__(
            titre="Matériel",
            sous_titre="Suivi de l'usure du matériel (chaussures, sac, vêtements...)",
            icone="🎒",
            table_sql="materiel",
            champs=champs,
            athlete_id_initial=athlete_id_initial,
            tri="id DESC",
            colonnes_calculees=[
                {"label": "Km réel (calculé depuis tes activités)", "fonction": _calculer_km_reel},
            ],
        )
