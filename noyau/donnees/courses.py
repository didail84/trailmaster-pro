"""
Accès aux courses à venir, aux résultats et aux objectifs (tables
`courses_calendrier`, `resultats_courses`, `objectifs`).

Requêtes reprises telles qu'elles étaient dans les écrans (étape 1.4c).
"""

from noyau.donnees import base


# ------------------------------------------------------------------
# Courses à venir (courses_calendrier)
# ------------------------------------------------------------------

def course(course_id, *colonnes):
    """Colonnes choisies d'une course du calendrier (tuple) ou None."""
    return base.valeurs("courses_calendrier", course_id, colonnes)


def courses_par_date(athlete_id=None):
    """(id, nom, date, distance_km, denivele_m, type_terrain), la plus proche
    d'abord ; tous les athlètes si athlete_id est None."""
    if athlete_id is not None:
        return base.lire_tous(
            "SELECT id, nom, date, distance_km, denivele_m, type_terrain FROM courses_calendrier "
            "WHERE athlete_id=? ORDER BY date ASC",
            (athlete_id,),
        )
    return base.lire_tous(
        "SELECT id, nom, date, distance_km, denivele_m, type_terrain FROM courses_calendrier "
        "ORDER BY date ASC"
    )


def courses_pour_roadbook(athlete_id):
    """(id, nom, date, distance_km, denivele_m), les courses sans date en dernier."""
    return base.lire_tous(
        "SELECT id, nom, date, distance_km, denivele_m FROM courses_calendrier "
        "WHERE athlete_id=? ORDER BY COALESCE(date,'9999')",
        (athlete_id,),
    )


# ------------------------------------------------------------------
# Résultats de courses
# ------------------------------------------------------------------

def resultat(resultat_id, *colonnes):
    return base.valeurs("resultats_courses", resultat_id, colonnes)


def sortie_du_resultat(resultat_id):
    """(date, distance) de la sortie liée au résultat, ou None."""
    return base.lire_un(
        """
        SELECT a.date, a.distance FROM resultats_courses r
        LEFT JOIN activites a ON r.activite_id = a.id
        WHERE r.id=? AND r.activite_id IS NOT NULL
        """,
        (resultat_id,),
    )


def lier_resultat_a_une_sortie(resultat_id, activite_id):
    base.ecrire("UPDATE resultats_courses SET activite_id=? WHERE id=?", (activite_id, resultat_id))


def resultats_pour_liaison(athlete_id, limite):
    """(id, nom_course, date, classement_general) des derniers résultats — pour un objectif."""
    return base.lire_tous(
        "SELECT id, nom_course, date, classement_general FROM resultats_courses "
        "WHERE athlete_id=? ORDER BY date DESC LIMIT ?",
        (athlete_id, limite),
    )


# ------------------------------------------------------------------
# Objectifs
# ------------------------------------------------------------------

def objectif(objectif_id, *colonnes):
    return base.valeurs("objectifs", objectif_id, colonnes)


def resultat_de_l_objectif(objectif_id):
    """(nom_course, date, classement_general) du résultat lié, ou None."""
    return base.lire_un(
        """
        SELECT r.nom_course, r.date, r.classement_general
        FROM objectifs o
        LEFT JOIN resultats_courses r ON o.resultat_id = r.id
        WHERE o.id=? AND o.resultat_id IS NOT NULL
        """,
        (objectif_id,),
    )


def marquer_objectif_atteint(objectif_id, resultat_id):
    base.ecrire("UPDATE objectifs SET resultat_id=?, statut='Atteint' WHERE id=?", (resultat_id, objectif_id))
