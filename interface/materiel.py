from interface.ecran_liste import EcranListe, Champ
from noyau.donnees import activites as dact  # accès aux données
from noyau.donnees import listes as dliste


# Types d'activités pertinents pour calculer l'usure réelle de chaque
# catégorie de matériel — None = toutes les activités comptent.
TYPES_MATERIEL_VERS_ACTIVITES = {
    "Chaussures": ["Trail", "Course", "Randonnée"],
    "Bâtons": ["Trail", "Randonnée"],
    "Sac à dos": ["Trail", "Course", "Randonnée", "VTT"],
}


def _calculer_km_reel(id_ligne, valeurs):
    nom, type_materiel, _marque, date_achat = valeurs[:4]

    if not date_achat:
        return "— (pas de date d'achat)"

    resultat = dliste.valeurs("materiel", id_ligne, "athlete_id")
    if not resultat:
        return "—"
    athlete_id = resultat[0]

    types_pertinents = TYPES_MATERIEL_VERS_ACTIVITES.get(type_materiel)
    total = dact.somme_distance_depuis(athlete_id, date_achat, types_pertinents)

    return f"{round(total or 0, 1)} km"


def _marques():
    from noyau.donnees import annuaire as dan
    return dan.noms_de_marques()


def _magasins():
    from noyau.donnees import annuaire as dan
    return dan.noms_de_magasins()


class Materiel(EcranListe):

    def __init__(self, athlete_id_initial=None):
        champs = [
            Champ("nom", "Nom", "texte", obligatoire=True),
            Champ(
                "type", "Type", "choix",
                choix=["Chaussures", "Sac à dos", "Vêtement", "Montre GPS", "Bâtons", "Autre"],
            ),
            Champ("marque", "Marque", "texte", suggestions=_marques),
            Champ("date_achat", "Date d'achat", "date"),
            Champ("magasin", "Acheté chez", "texte", suggestions=_magasins),
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
