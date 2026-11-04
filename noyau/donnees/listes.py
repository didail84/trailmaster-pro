"""
Accès générique utilisé par l'écran de liste commun (EcranListe) :
Blessures, Soins, Sommeil, Matériel, Nutrition, Résultats, Objectifs,
Courses à venir, Zones d'entraînement, Poids & récupération…

Les noms de table et de colonnes sont vérifiés ; l'ordre de tri vient
du code de chaque écran (jamais d'une saisie) et peut contenir une
expression (CASE … END), il est donc transmis tel quel.
"""

from noyau.donnees import base


def lister(table, colonnes, tri, athlete_id=None):
    """(id, colonnes…) de chaque ligne, triées ; toutes si athlete_id est None."""
    table = base.verifier_colonnes([table])[0]
    colonnes_sql = ", ".join(base.verifier_colonnes(list(colonnes)))
    if athlete_id is None:
        return base.lire_tous(f"SELECT id, {colonnes_sql} FROM {table} ORDER BY {tri}")
    return base.lire_tous(
        f"SELECT id, {colonnes_sql} FROM {table} WHERE athlete_id=? ORDER BY {tri}",
        (athlete_id,),
    )


def ajouter(table, athlete_id, colonnes, valeurs):
    """Nouvelle ligne pour l'athlète ; renvoie son id."""
    return base.inserer(table, {"athlete_id": athlete_id, **dict(zip(colonnes, valeurs))})


def supprimer(table, ligne_id):
    base.ecrire(f"DELETE FROM {base.verifier_colonnes([table])[0]} WHERE id=?", (ligne_id,))


def valeurs(table, ligne_id, *colonnes):
    """Colonnes choisies d'une ligne (tuple) ou None."""
    return base.valeurs(table, ligne_id, colonnes)
