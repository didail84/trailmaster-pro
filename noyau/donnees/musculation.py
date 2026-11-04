"""
Accès au renforcement et à la mobilité (tables `musculation_suivi`,
`musculation_exercices`, `planning_mobilite`, `mobilite_exercices`).

Requêtes reprises telles qu'elles étaient dans les écrans (étape 1.4b).
"""

from noyau.donnees import base


def ajouter_suivi(champs, cur=None):
    """Nouvelle séance de renforcement ou de cardio machine ; renvoie son id."""
    return base.inserer("musculation_suivi", champs, cur)


def suivi(athlete_id):
    """Historique complet (17 colonnes), le plus récent d'abord."""
    return base.lire_tous(
        "SELECT date, type_seance, exercice, charge_kg, series, rpe, douleur, "
        "charge_proposee, decision, appareil, duree_min, type_intensite, "
        "valeur_intensite, distance_km, fc_moyenne, calories, groupe_musculaire "
        "FROM musculation_suivi WHERE athlete_id=? ORDER BY date DESC",
        (athlete_id,),
    )


def suivi_par_jour_entre(athlete_id, debut_iso, fin_iso):
    """(jour, exercice, charge_kg, series, reps_prevues, rpe, duree_min,
    type_seance, groupe_musculaire) entre deux jours inclus."""
    return base.lire_tous(
        "SELECT substr(date,1,10), exercice, charge_kg, series, reps_prevues, rpe, "
        "duree_min, type_seance, groupe_musculaire FROM musculation_suivi "
        "WHERE athlete_id=? AND substr(date,1,10) BETWEEN ? AND ? ORDER BY date, id",
        (athlete_id, debut_iso, fin_iso),
    )


def exercices(athlete_id):
    """Plan de musculation : (groupe_seance, exercice, charge_depart_kg, bloc1…bloc6)."""
    return base.lire_tous(
        "SELECT groupe_seance, exercice, charge_depart_kg, bloc1, bloc2, bloc3, bloc4, bloc5, bloc6 "
        "FROM musculation_exercices WHERE athlete_id=? ORDER BY groupe_seance, id",
        (athlete_id,),
    )


def planning_mobilite(athlete_id):
    return base.lire_tous(
        "SELECT jour, duree, bloc, contenu, intensite, moment FROM planning_mobilite "
        "WHERE athlete_id=?",
        (athlete_id,),
    )


def exercices_mobilite(athlete_id):
    return base.lire_tous(
        "SELECT categorie, exercice, moment_ou_objectif, zone, bloc1, bloc2, bloc3, bloc4, "
        "bloc5, bloc6, progression FROM mobilite_exercices WHERE athlete_id=? ORDER BY categorie, id",
        (athlete_id,),
    )
