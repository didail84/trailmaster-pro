"""
Accès aux traces et parcours (table `parcours_gpx`).

Requêtes reprises telles qu'elles étaient dans les écrans (étape 1.4a).
"""

from noyau.donnees import base


def valeurs(parcours_id, *colonnes, cur=None):
    """Colonnes choisies d'un parcours (tuple) ou None."""
    return base.valeurs("parcours_gpx", parcours_id, colonnes, cur=cur)


def trace(parcours_id):
    """Le texte JSON de la trace, ou None."""
    ligne = valeurs(parcours_id, "trace_json")
    return ligne[0] if ligne else None


def trace_de_l_activite(activite_id):
    """Trace JSON du premier parcours rattaché à une sortie, ou None."""
    ligne = base.lire_un("SELECT trace_json FROM parcours_gpx WHERE activite_id=? LIMIT 1", (activite_id,))
    return ligne[0] if ligne else None


def lie_a_l_activite(activite_id):
    """(id, trace_json) du parcours rattaché ayant une trace, ou None."""
    return base.lire_un(
        "SELECT id, trace_json FROM parcours_gpx WHERE activite_id=? AND trace_json IS NOT NULL",
        (activite_id,),
    )


def avec_son_activite(parcours_id):
    """(trace_json, athlete_id, distance de la sortie liée, durée de la sortie liée)."""
    return base.lire_un(
        """
        SELECT p.trace_json, p.athlete_id, a.distance, a.duree
        FROM parcours_gpx p
        LEFT JOIN activites a ON p.activite_id = a.id
        WHERE p.id=?
        """,
        (parcours_id,),
    )


# ------------------------------------------------------------------
# Listes
# ------------------------------------------------------------------

def liste_courte(athlete_id, limite=None, par_id=False):
    """(id, nom, distance_km), le plus récent d'abord — pour les listes
    déroulantes. par_id=True trie par numéro au lieu de la date d'ajout."""
    if par_id:
        return base.lire_tous(
            "SELECT id, nom, distance_km FROM parcours_gpx WHERE athlete_id=? ORDER BY id DESC",
            (athlete_id,),
        )
    return base.lire_tous(
        "SELECT id, nom, distance_km FROM parcours_gpx WHERE athlete_id=? "
        "ORDER BY date_ajout DESC LIMIT ?",
        (athlete_id, limite if limite is not None else -1),
    )


def traces_de_l_athlete(athlete_id, type_activite=None):
    """(id, trace_json) de tous les parcours de l'athlète ; avec
    type_activite, seulement ceux liés à une sortie de ce type."""
    if type_activite is None:
        return base.lire_tous("SELECT id, trace_json FROM parcours_gpx WHERE athlete_id=?", (athlete_id,))
    return base.lire_tous(
        """
        SELECT p.id, p.trace_json FROM parcours_gpx p
        LEFT JOIN activites a ON p.activite_id = a.id
        WHERE p.athlete_id=? AND a.type=?
        """,
        (athlete_id, type_activite),
    )


def traces_et_activites(athlete_id):
    """(id, trace_json, activite_id) de tous les parcours de l'athlète."""
    return base.lire_tous(
        "SELECT id, trace_json, activite_id FROM parcours_gpx WHERE athlete_id=?",
        (athlete_id,),
    )


def liste_pour_tableau(athlete_id=None, limite=500):
    """(id, nom, distance_km, D+, D-, date_ajout, activite_id), le plus
    récent d'abord ; tous les athlètes si athlete_id est None."""
    if athlete_id is None:
        return base.lire_tous(
            "SELECT id, nom, distance_km, denivele_positif, denivele_negatif, "
            "date_ajout, activite_id FROM parcours_gpx ORDER BY date_ajout DESC LIMIT ?",
            (limite,),
        )
    return base.lire_tous(
        "SELECT id, nom, distance_km, denivele_positif, denivele_negatif, "
        "date_ajout, activite_id FROM parcours_gpx WHERE athlete_id=? "
        "ORDER BY date_ajout DESC LIMIT ?",
        (athlete_id, limite),
    )


def liste_complete():
    """(id, nom, date_ajout, distance_km, D+, D-, altitude_min, altitude_max), tous athlètes."""
    return base.lire_tous(
        """
        SELECT id, nom, date_ajout, distance_km, denivele_positif, denivele_negatif,
               altitude_min, altitude_max
        FROM parcours_gpx
        ORDER BY date_ajout DESC
        """
    )


# ------------------------------------------------------------------
# Écritures
# ------------------------------------------------------------------

def inserer(champs, cur=None):
    """Enregistre un parcours à partir d'un dict {colonne: valeur} ; renvoie son id."""
    return base.inserer("parcours_gpx", champs, cur)


def supprimer(parcours_id):
    base.ecrire("DELETE FROM parcours_gpx WHERE id=?", (parcours_id,))
