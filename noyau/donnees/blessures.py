"""
Accès aux blessures et aux soins (tables `blessures` et `soins`).

Requêtes reprises telles qu'elles étaient dans les écrans (étape 1.4c).
"""

from noyau.donnees import base


# ------------------------------------------------------------------
# Blessures
# ------------------------------------------------------------------

def valeurs(blessure_id, *colonnes):
    return base.valeurs("blessures", blessure_id, colonnes)


def ajouter(champs):
    """Nouvelle blessure à partir d'un dict {colonne: valeur} ; renvoie son id."""
    return base.inserer("blessures", champs)


def origine(blessure_id):
    """(date, type, distance de la sortie liée, date, exercice, groupe de la
    séance de musculation liée), ou None."""
    return base.lire_un(
        """
        SELECT a.date, a.type, a.distance, m.date, m.exercice, m.groupe_musculaire
        FROM blessures b
        LEFT JOIN activites a ON b.activite_id = a.id
        LEFT JOIN musculation_suivi m ON b.musculation_suivi_id = m.id
        WHERE b.id=?
        """,
        (blessure_id,),
    )


def lier_a_une_sortie(blessure_id, activite_id):
    base.ecrire("UPDATE blessures SET activite_id=?, musculation_suivi_id=NULL WHERE id=?",
                (activite_id, blessure_id))


def de_l_athlete(athlete_id):
    """(id, date_debut, date_fin, zone, type, gravite, statut), la plus récente d'abord."""
    return base.lire_tous(
        "SELECT id, date_debut, date_fin, zone_corporelle, type_blessure, gravite, statut "
        "FROM blessures WHERE athlete_id=? ORDER BY date_debut DESC",
        (athlete_id,),
    )


def pour_journal(athlete_id):
    """(date_debut, date_fin, zone, type, statut) de toutes les blessures."""
    return base.lire_tous(
        "SELECT date_debut, date_fin, zone_corporelle, type_blessure, statut FROM blessures WHERE athlete_id=?",
        (athlete_id,),
    )


def en_cours(athlete_id):
    """(zone, type) des blessures « En cours »."""
    return base.lire_tous(
        "SELECT zone_corporelle, type_blessure FROM blessures WHERE athlete_id=? AND statut='En cours'",
        (athlete_id,),
    )


def pour_liaison(athlete_id, limite):
    """(id, date_debut, zone, type, statut) des dernières blessures — pour rattacher un soin."""
    return base.lire_tous(
        "SELECT id, date_debut, zone_corporelle, type_blessure, statut FROM blessures "
        "WHERE athlete_id=? ORDER BY date_debut DESC LIMIT ?",
        (athlete_id, limite),
    )


# ------------------------------------------------------------------
# Soins
# ------------------------------------------------------------------

def soin_valeurs(soin_id, *colonnes):
    return base.valeurs("soins", soin_id, colonnes)


def blessure_du_soin(soin_id):
    """(zone, type, date_debut) de la blessure liée au soin, ou (None, None, None)."""
    return base.lire_un(
        """
        SELECT b.zone_corporelle, b.type_blessure, b.date_debut
        FROM soins s
        LEFT JOIN blessures b ON s.blessure_id = b.id
        WHERE s.id=?
        """,
        (soin_id,),
    )


def lier_soin_a_une_blessure(soin_id, blessure_id):
    base.ecrire("UPDATE soins SET blessure_id=?, motif='Blessure' WHERE id=?", (blessure_id, soin_id))
