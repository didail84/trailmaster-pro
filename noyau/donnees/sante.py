"""
Accès au suivi corporel et à la récupération (tables `suivi_corporel`,
`sommeil`, `recuperation_quotidienne`, `garmin_quotidien`).

Requêtes reprises telles qu'elles étaient dans les écrans (étape 1.4c).
"""

from noyau.donnees import base


# ------------------------------------------------------------------
# Poids, jambes, fatigue (suivi_corporel)
# ------------------------------------------------------------------

def dernier_poids(athlete_id):
    """(poids_kg, date) de la dernière pesée renseignée, ou None."""
    return base.lire_un(
        "SELECT poids_kg, date FROM suivi_corporel WHERE athlete_id=? AND poids_kg IS NOT NULL "
        "AND poids_kg > 0 ORDER BY date DESC, id DESC LIMIT 1",
        (athlete_id,),
    )


def releve(releve_id):
    """(athlete_id, date, moment — « matin » par défaut, poids_kg) d'un relevé."""
    return base.lire_un(
        "SELECT athlete_id, date, COALESCE(moment, 'matin'), poids_kg FROM suivi_corporel WHERE id=?",
        (releve_id,),
    )


def poids_du_matin_precedent(athlete_id, date_iso):
    """(poids_kg,) de la pesée du matin précédant une date, ou None."""
    return base.lire_un(
        "SELECT poids_kg FROM suivi_corporel WHERE athlete_id=? AND poids_kg > 0 "
        "AND COALESCE(moment, 'matin')='matin' AND date < ? ORDER BY date DESC, id DESC LIMIT 1",
        (athlete_id, date_iso),
    )


def fatigue_du_matin(athlete_id):
    """(date, fatigue_jambes, fatigue_generale) des relevés du matin renseignés."""
    return base.lire_tous(
        "SELECT date, fatigue_jambes, fatigue_generale FROM suivi_corporel "
        "WHERE athlete_id=? AND COALESCE(moment, 'matin')='matin' "
        "AND (fatigue_jambes IS NOT NULL OR fatigue_generale IS NOT NULL) ORDER BY date, id",
        (athlete_id,),
    )


def releves_entre(athlete_id, depuis_iso, jusqu_a_iso):
    """(date, poids_kg, etat_jambes, notes) entre deux dates."""
    return base.lire_tous(
        "SELECT date, poids_kg, etat_jambes, notes FROM suivi_corporel WHERE athlete_id=? AND date>=? AND date<=?",
        (athlete_id, depuis_iso, jusqu_a_iso),
    )


def releves_complets(athlete_id):
    """(date, poids_kg, etat_jambes, fatigue_jambes, fatigue_generale, notes), du plus ancien au plus récent."""
    return base.lire_tous(
        "SELECT date, poids_kg, etat_jambes, fatigue_jambes, fatigue_generale, notes FROM suivi_corporel "
        "WHERE athlete_id=? ORDER BY date",
        (athlete_id,),
    )


def nettoyer_cases_vides(colonnes_numeriques):
    """Remet à « non renseigné » les 0 et les états vides écrits par le
    formulaire dans les cases laissées vides, en une seule opération."""
    with base.transaction() as cur:
        for colonne in base.verifier_colonnes(list(colonnes_numeriques)):
            cur.execute(f"UPDATE suivi_corporel SET {colonne}=NULL WHERE {colonne}=0")
        cur.execute("UPDATE suivi_corporel SET etat_jambes=NULL WHERE etat_jambes=''")
        cur.execute("UPDATE suivi_corporel SET moment='matin' WHERE moment IS NULL OR moment=''")


# ------------------------------------------------------------------
# Sommeil et récupération
# ------------------------------------------------------------------

def sommeil_entre(athlete_id, debut_iso, fin_iso):
    """(date, heure_coucher, heure_lever, duree_heures) ; tous les athlètes si athlete_id est None."""
    if athlete_id is not None:
        return base.lire_tous(
            "SELECT date, heure_coucher, heure_lever, duree_heures FROM sommeil "
            "WHERE athlete_id=? AND date >= ? AND date <= ?",
            (athlete_id, debut_iso, fin_iso),
        )
    return base.lire_tous(
        "SELECT date, heure_coucher, heure_lever, duree_heures FROM sommeil "
        "WHERE date >= ? AND date <= ?",
        (debut_iso, fin_iso),
    )


def recuperation_entre(athlete_id, colonnes, debut_iso, fin_iso):
    """Colonnes choisies de recuperation_quotidienne, du plus ancien au plus récent."""
    return base.lire_tous(
        f"SELECT {', '.join(base.verifier_colonnes(list(colonnes)))} FROM recuperation_quotidienne "
        "WHERE athlete_id=? AND date>=? AND date<=? ORDER BY date",
        (athlete_id, debut_iso, fin_iso),
    )


def sante_garmin_recente(athlete_id, nb):
    """Derniers jours de santé (récupération + données Garmin du même jour), le plus récent d'abord."""
    return base.lire_tous(
        """
        SELECT r.date, r.fc_repos, r.hrv_nuit_ms, r.hrv_statut, r.sommeil_duree_h, r.sommeil_score,
               r.body_battery_max, r.stress_moyen, r.spo2_moyenne,
               g.pas, g.readiness_score, g.statut_entrainement, g.vo2max
        FROM recuperation_quotidienne r
        LEFT JOIN garmin_quotidien g ON g.athlete_id=r.athlete_id AND g.date=r.date
        WHERE r.athlete_id=? ORDER BY r.date DESC LIMIT ?
        """,
        (athlete_id, nb),
    )
