"""
Allure critique — approximation d'une "courbe puissance-durée" (Critical
Power / Critical Speed) à partir des sorties déjà enregistrées, sans
capteur de puissance ni traitement seconde par seconde du tracé GPS.

Principe simplifié, clairement documenté comme tel : pour chaque palier
de durée (10 min, 20 min, 30 min...), on cherche la MEILLEURE allure
moyenne parmi les sorties dont la durée totale est proche de ce palier
(±25%) — c'est une approximation par séance entière, pas une vraie
fenêtre glissante intra-séance comme le ferait un fichier FIT analysé
seconde par seconde. Suffisant pour repérer une tendance et calibrer
grossièrement des zones d'allure, pas pour un calcul scientifique.

100% local, aucune dépendance réseau.
"""

from data.database import connexion, obtenir_parametre, definir_parametre
from interface.date_utils import parser_date_flexible


PALIERS_MIN = [10, 20, 30, 45, 60, 90, 120, 180, 240]
TOLERANCE_PAR_DEFAUT = 0.25
CLE_PARAMETRE_TOLERANCE = "allure_critique_tolerance"


def obtenir_tolerance():
    valeur = obtenir_parametre(CLE_PARAMETRE_TOLERANCE)
    try:
        tolerance = float(valeur) if valeur else TOLERANCE_PAR_DEFAUT
        return tolerance if 0.05 <= tolerance <= 0.6 else TOLERANCE_PAR_DEFAUT
    except (TypeError, ValueError):
        return TOLERANCE_PAR_DEFAUT


def definir_tolerance(tolerance):
    definir_parametre(CLE_PARAMETRE_TOLERANCE, tolerance)


def _formater_allure(allure_min_km):
    minutes = int(allure_min_km)
    secondes = round((allure_min_km - minutes) * 60)
    if secondes == 60:
        minutes += 1
        secondes = 0
    return f"{minutes}:{secondes:02d}"


def calculer_courbe_allure_critique(athlete_id, nb_jours=365, types=("Trail", "Course", "Route")):
    """Retourne une liste de dicts {palier_min, allure_texte,
    allure_min_km, nb_sorties_considerees, date} triée par palier
    croissant — les paliers sans sortie suffisamment proche sont omis
    plutôt que remplis d'une valeur inventée."""

    conn = connexion()
    cur = conn.cursor()
    cur.execute(
        "SELECT date, type, distance, duree FROM activites "
        "WHERE athlete_id=? AND distance>0 AND duree>0",
        (athlete_id,),
    )
    lignes = cur.fetchall()
    conn.close()

    from datetime import datetime, timedelta
    date_min = datetime.now().date() - timedelta(days=nb_jours)

    sorties = []
    for date_texte, type_, distance, duree in lignes:
        if types and (type_ or "") not in types:
            continue
        date_obj = parser_date_flexible(date_texte)
        if date_obj is None or date_obj.date() < date_min:
            continue
        duree_min = duree / 60
        allure = duree_min / distance  # min/km
        sorties.append({"duree_min": duree_min, "allure": allure, "date": date_obj.date()})

    resultat = []
    tolerance = obtenir_tolerance()
    for palier in PALIERS_MIN:
        bas, haut = palier * (1 - tolerance), palier * (1 + tolerance)
        candidates = [s for s in sorties if bas <= s["duree_min"] <= haut]
        if not candidates:
            continue
        meilleure = min(candidates, key=lambda s: s["allure"])
        resultat.append({
            "palier_min": palier,
            "allure_min_km": round(meilleure["allure"], 2),
            "allure_texte": _formater_allure(meilleure["allure"]),
            "nb_sorties_considerees": len(candidates),
            "date": meilleure["date"],
        })

    return resultat
