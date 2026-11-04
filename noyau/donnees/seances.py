"""
Accès aux séances structurées (table `seances_structurees`).

Requêtes reprises telles qu'elles étaient dans les écrans (étape 1.4b).
"""

from noyau.donnees import base

# Colonnes affichées par l'écran « Séances structurées » (s. = séance, p. = parcours prévu)
COLONNES_LISTE = (
    "s.id, s.nom, s.type_seance, s.date_prevue, s.statut, s.score_conformite, "
    "s.etapes_json, s.parcours_id, p.nom, p.distance_km, s.commentaire_replanification"
)


def valeurs(seance_id, *colonnes):
    """Colonnes choisies d'une séance (tuple) ou None."""
    return base.valeurs("seances_structurees", seance_id, colonnes)


def creer(champs, cur=None):
    """Nouvelle séance « Prévue » à partir d'un dict {colonne: valeur} ; renvoie son id."""
    return base.inserer("seances_structurees", {**champs, "statut": "Prévue"}, cur)


def lister_avec_parcours(athlete_id=None):
    """Séances avec le nom et la distance de leur parcours prévu, la plus
    lointaine d'abord ; toutes les séances si athlete_id est None."""
    if athlete_id is None:
        return base.lire_tous(
            f"SELECT {COLONNES_LISTE} FROM seances_structurees s "
            "LEFT JOIN parcours_gpx p ON s.parcours_id = p.id "
            "ORDER BY s.date_prevue DESC"
        )
    return base.lire_tous(
        f"SELECT {COLONNES_LISTE} FROM seances_structurees s "
        "LEFT JOIN parcours_gpx p ON s.parcours_id = p.id "
        "WHERE s.athlete_id=? ORDER BY s.date_prevue DESC",
        (athlete_id,),
    )


def entre_dates(athlete_id, debut_iso, fin_iso):
    """(id, nom, type_seance, date_prevue, statut) prévues entre deux dates."""
    return base.lire_tous(
        "SELECT id, nom, type_seance, date_prevue, statut FROM seances_structurees WHERE athlete_id=? "
        "AND date_prevue>=? AND date_prevue<=?",
        (athlete_id, debut_iso, fin_iso),
    )


def deplacer(seance_id, jour_iso):
    """Change la date d'une séance encore « Prévue » ; True si elle a bougé."""
    return base.ecrire_compte(
        "UPDATE seances_structurees SET date_prevue=? WHERE id=? AND statut='Prévue'",
        (jour_iso, seance_id),
    ) > 0


def marquer_realisee(seance_id, activite_id, score_conformite):
    base.ecrire(
        "UPDATE seances_structurees SET statut=?, activite_id=?, score_conformite=? WHERE id=?",
        ("Réalisée", activite_id, score_conformite, seance_id),
    )


def supprimer(seance_id):
    """Supprime la séance et ses comparaisons prévu/réalisé, ensemble (sans
    cela, la base refusait la suppression d'une séance déjà comparée)."""
    with base.transaction() as cur:
        cur.execute("DELETE FROM comparaisons_courses WHERE seance_id=?", (seance_id,))
        cur.execute("DELETE FROM seances_structurees WHERE id=?", (seance_id,))
