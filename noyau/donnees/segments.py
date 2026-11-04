"""
Accès aux segments précis et à leurs passages (tables `segments` et
`segments_efforts`).

Requêtes reprises telles qu'elles étaient dans les écrans (étape 1.4b).
"""

import json

from noyau.donnees import base


def creer(champs):
    """Nouveau segment à partir d'un dict {colonne: valeur} ; renvoie son id."""
    return base.inserer("segments", champs)


def lister(athlete_id):
    """(id, nom, distance_km, denivele_positif), le plus récent d'abord."""
    return base.lire_tous(
        "SELECT id, nom, distance_km, denivele_positif FROM segments "
        "WHERE athlete_id=? ORDER BY date_creation DESC",
        (athlete_id,),
    )


def points_reference(segment_id):
    """Liste des points de référence du segment (décodée du JSON)."""
    ligne = base.lire_un("SELECT points_reference_json FROM segments WHERE id=?", (segment_id,))
    return json.loads(ligne[0])


def supprimer(segment_id):
    """Supprime le segment et tous ses passages, ensemble."""
    with base.transaction() as cur:
        cur.execute("DELETE FROM segments_efforts WHERE segment_id=?", (segment_id,))
        cur.execute("DELETE FROM segments WHERE id=?", (segment_id,))


# ------------------------------------------------------------------
# Passages
# ------------------------------------------------------------------

def parcours_deja_trouves(segment_id, cur=None):
    """Ensemble des parcours où un passage est déjà enregistré."""
    return set(r[0] for r in base.lire_tous(
        "SELECT parcours_id FROM segments_efforts WHERE segment_id=?", (segment_id,), cur))


def ajouter_passage(segment_id, parcours_id, activite_id, date, duree_s, cur=None):
    return base.ecrire(
        """
        INSERT INTO segments_efforts (segment_id, parcours_id, activite_id, date, duree_s)
        VALUES (?, ?, ?, ?, ?)
        """,
        (segment_id, parcours_id, activite_id, date, duree_s),
        cur,
    )


def resume_passages(segment_id):
    """(nombre de passages, meilleur temps en secondes ou None)."""
    return base.lire_un("SELECT COUNT(*), MIN(duree_s) FROM segments_efforts WHERE segment_id=?", (segment_id,))


def classement(segment_id):
    """(date, duree_s) de chaque passage chronométré, le plus rapide d'abord."""
    return base.lire_tous(
        "SELECT date, duree_s FROM segments_efforts WHERE segment_id=? "
        "AND duree_s IS NOT NULL ORDER BY duree_s ASC",
        (segment_id,),
    )


def passages_de_l_activite(activite_id):
    """(nom du segment, distance_km, duree_s) des segments passés pendant une sortie."""
    return base.lire_tous(
        "SELECT s.nom, s.distance_km, e.duree_s FROM segments_efforts e "
        "JOIN segments s ON e.segment_id = s.id "
        "WHERE e.activite_id=?",
        (activite_id,),
    )
