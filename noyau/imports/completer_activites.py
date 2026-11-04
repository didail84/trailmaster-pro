"""
Complète une activité DÉJÀ présente en base avec les champs qui y sont
vides, sans jamais écraser une valeur existante (ni créer de doublon).

Sert aux imports Garmin / Strava : quand une activité est reconnue comme
déjà connue (même empreinte, même identifiant ou même sortie à quelques
minutes près), on récupère au passage les paramètres que les anciennes
versions n'importaient pas (D−, vitesse et allure max, cadence, VO₂max,
FC max, vitesse/allure moyennes…).
"""

# Colonnes de la table `activites` que l'on peut compléter.
COLONNES_COMPLETABLES = (
    "distance", "denivele", "duree",
    "vitesse_moyenne", "allure_moyenne",
    "frequence_cardiaque_moyenne", "frequence_cardiaque_max", "calories",
    "denivele_negatif", "vitesse_max", "allure_max",
    "cadence_moyenne", "vo2max",
    "te_aerobie", "te_anaerobie", "charge_garmin",
    "temps_zone_1", "temps_zone_2", "temps_zone_3", "temps_zone_4", "temps_zone_5",
    "puissance_moyenne", "puissance_max", "oscillation_verticale",
    "temps_contact_sol", "longueur_foulee", "temperature_moyenne",
    "effort_percu", "suffer_score",
)


def completer_activite(cur, activite_id, valeurs):
    """Remplit, pour l'activité `activite_id`, les colonnes vides
    (NULL ou 0) avec `valeurs` (dict colonne -> valeur). Retourne True
    si au moins une colonne a été complétée."""

    a_mettre = {
        c: v for c, v in valeurs.items()
        if c in COLONNES_COMPLETABLES and v not in (None, "", 0)
    }
    if not a_mettre:
        return False

    colonnes = ", ".join(a_mettre)
    cur.execute(f"SELECT {colonnes} FROM activites WHERE id=?", (activite_id,))
    ligne = cur.fetchone()
    if ligne is None:
        return False

    manquantes = {
        c: v for (c, v), actuel in zip(a_mettre.items(), ligne)
        if actuel is None or actuel == 0
    }
    if not manquantes:
        return False

    sets = ", ".join(f"{c}=?" for c in manquantes)
    cur.execute(f"UPDATE activites SET {sets} WHERE id=?", (*manquantes.values(), activite_id))
    return True
