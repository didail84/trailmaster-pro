"""
Import des activités depuis l'export natif "Exporter vos données" de
Garmin Connect (fichiers *_summarizedActivities.json), plutôt que
depuis un CSV.

Ce format contient le vrai type d'activité, la vraie durée, le vrai
dénivelé et la fréquence cardiaque — des champs que le CSV d'origine
ne fournissait pas correctement (voir le bug corrigé dans
import_donnees.py : toutes les activités importées en CSV avaient
type="Autre", durée=0 et dénivelé=0).

Unités natives Garmin dans ce format :
  - distance, elevationGain, elevationLoss : centimètres
  - duration                                : millisecondes
  - beginTimestamp / startTimeLocal         : millisecondes (epoch)
"""

import hashlib
import json
import statistics
from datetime import datetime


# Correspondance entre le type d'activité Garmin et les libellés
# utilisés dans l'application (mêmes libellés que interface/coach.py).
TYPES_GARMIN_VERS_APP = {
    "trail_running": "Trail",
    "running": "Course",
    "treadmill_running": "Course",
    "street_running": "Course",
    "track_running": "Course",
    "indoor_running": "Course",
    "mountain_biking": "VTT",
    "cycling": "Vélo",
    "road_biking": "Vélo",
    "indoor_cycling": "Vélo",
    "hiking": "Randonnée",
    "mountaineering": "Randonnée",
    "walking": "Randonnée",
}


def _type_app(type_garmin):
    return TYPES_GARMIN_VERS_APP.get((type_garmin or "").strip(), "Autre")


def _date_iso(activite_garmin):
    # startTimeLocal encode déjà l'heure locale (pas besoin de fuseau
    # supplémentaire) : on lit son timestamp en UTC pour éviter une
    # double conversion.
    horodatage_ms = activite_garmin.get("startTimeLocal") or activite_garmin.get("beginTimestamp")
    if not horodatage_ms:
        return None
    try:
        date = datetime.utcfromtimestamp(horodatage_ms / 1000)
        return date.strftime("%Y-%m-%d %H:%M:%S")
    except (ValueError, OSError, OverflowError):
        return None


def _creer_empreinte(activite):
    texte = "|".join([
        activite["date"],
        activite["type"],
        f"{activite['distance']:.3f}",
        str(activite["denivele"]),
        str(activite["duree"]),
    ])
    return hashlib.sha256(texte.encode("utf-8")).hexdigest()


def _facteur_vitesse(activites_brutes):
    """Les vitesses de l'export Garmin ne sont pas en m/s mais dans une
    unité interne (souvent des dizaines de m/s). Plutôt que de supposer,
    on la déduit des activités elles-mêmes : distance / durée donne la
    vitesse réelle en m/s, comparée à avgSpeed. Retourne le facteur à
    appliquer à une vitesse de l'export pour obtenir des m/s."""

    rapports = []
    for b in activites_brutes:
        v, d, t = b.get("avgSpeed"), b.get("distance"), b.get("duration")
        if v and d and t and v > 0 and d > 0 and t > 0:
            rapports.append((d / 100.0) / (t / 1000.0) / v)
    if len(rapports) < 3:
        return 10.0
    mediane = statistics.median(rapports)
    # On « accroche » au facteur plausible le plus proche (échelle log).
    import math
    candidats = (0.1, 1.0, 10.0, 100.0)
    return min(candidats, key=lambda c: abs(math.log(mediane / c)))


def _cadence(brute, type_app):
    """Cadence en pas/min (course) ou tours/min (vélo), ou None."""
    if type_app in ("Vélo", "VTT"):
        v = brute.get("avgBikingCadenceInRevPerMinute") or brute.get("avgBikeCadence")
        return round(v) if v else None
    double = brute.get("avgDoubleCadence")
    if double:
        return round(double)
    v = brute.get("avgRunCadence")
    if not v:
        return None
    # Cadence d'un seul pied (≈ 80-90) : on double pour obtenir les pas/min.
    if type_app in ("Trail", "Course") and v < 120:
        v = v * 2
    return round(v)


def _entre(valeur, bas, haut, decimales=1):
    """Valeur numérique si elle est dans la plage plausible, sinon None."""
    try:
        x = float(valeur)
    except (TypeError, ValueError):
        return None
    return round(x, decimales) if bas <= x <= haut else None


def _donnees_avancees(brute, type_app, duree_s):
    """Paramètres « fatigue / intensité » d'une sortie : effet
    d'entraînement, charge Garmin, temps par zone de FC, puissance,
    dynamique de course, température. Chaque valeur est vérifiée (plage
    plausible) : une unité inattendue donne None plutôt qu'un chiffre faux."""
    sortie = {
        "te_aerobie": _entre(brute.get("aerobicTrainingEffect"), 0, 5.5),
        "te_anaerobie": _entre(brute.get("anaerobicTrainingEffect"), 0, 5.5),
        "charge_garmin": _entre(brute.get("activityTrainingLoad"), 1, 2000),
    }

    # Temps par zone de FC : secondes ou millisecondes selon l'export →
    # on le déduit en comparant la somme des zones à la durée de la sortie.
    zones = [brute.get(f"hrTimeInZone_{i}") for i in range(1, 6)]
    if any(z for z in zones) and duree_s:
        somme = sum(z for z in zones if z)
        facteur = 0.001 if somme > duree_s * 100 else 1.0
        for i, z in enumerate(zones, 1):
            sortie[f"temps_zone_{i}"] = round(z * facteur) if z else None

    if type_app in ("Trail", "Course", "Randonnée", "Vélo", "VTT"):
        sortie["puissance_moyenne"] = _entre(brute.get("avgPower"), 20, 1000, 0)
        sortie["puissance_max"] = _entre(brute.get("maxPower"), 20, 3000, 0)

    if type_app in ("Trail", "Course"):
        osc = _entre(brute.get("avgVerticalOscillation"), 1, 400)
        if osc is not None and osc > 30:      # exprimée en mm
            osc = round(osc / 10, 1)
        sortie["oscillation_verticale"] = osc if osc and 3 <= osc <= 20 else None

        gct = _entre(brute.get("avgGroundContactTime"), 100, 600, 0)
        sortie["temps_contact_sol"] = int(gct) if gct else None

        foulee = _entre(brute.get("avgStrideLength"), 0.3, 400, 2)
        if foulee is not None and foulee > 5:  # exprimée en cm
            foulee = round(foulee / 100, 2)
        sortie["longueur_foulee"] = foulee if foulee and 0.4 <= foulee <= 3 else None

    t_min, t_max = brute.get("minTemperature"), brute.get("maxTemperature")
    t_moy = brute.get("avgTemperature")
    if t_moy is None and t_min is not None and t_max is not None:
        try:
            t_moy = (float(t_min) + float(t_max)) / 2
        except (TypeError, ValueError):
            t_moy = None
    sortie["temperature_moyenne"] = _entre(t_moy, -30, 55)

    return {k: v for k, v in sortie.items() if v is not None}


def parser_export_garmin_json(chemin_fichier):
    """Lit un fichier *_summarizedActivities.json et retourne une liste
    de dicts prêts à insérer dans la table `activites` (sans athlete_id,
    à renseigner par l'appelant)."""

    with open(chemin_fichier, encoding="utf-8") as f:
        contenu = json.load(f)

    if not contenu or "summarizedActivitiesExport" not in contenu[0]:
        return []

    activites_brutes = contenu[0]["summarizedActivitiesExport"]
    facteur_vitesse = _facteur_vitesse(activites_brutes)
    resultat = []
    nom_fichier = str(chemin_fichier)

    for brute in activites_brutes:
        date_iso = _date_iso(brute)
        if date_iso is None:
            continue

        distance_cm = brute.get("distance") or 0
        distance_km = round(distance_cm / 100000, 4)

        denivele_cm = brute.get("elevationGain") or 0
        denivele_m = round(denivele_cm / 100)

        duree_ms = brute.get("duration") or 0
        duree_s = round(duree_ms / 1000)

        vitesse_moyenne = None
        allure_moyenne = None
        if duree_s > 0 and distance_km > 0:
            vitesse_moyenne = round(distance_km / (duree_s / 3600), 2)
            allure_moyenne = round((duree_s / 60) / distance_km, 2)

        type_app = _type_app(brute.get("activityType"))

        denivele_neg_m = round((brute.get("elevationLoss") or 0) / 100)

        vitesse_max = None
        allure_max = None
        if brute.get("maxSpeed"):
            v_kmh = brute["maxSpeed"] * facteur_vitesse * 3.6
            # Écarte les pics GPS aberrants et les valeurs sous la moyenne.
            if 0 < v_kmh <= (80 if type_app in ("Vélo", "VTT") else 40) and (
                vitesse_moyenne is None or v_kmh >= vitesse_moyenne
            ):
                vitesse_max = round(v_kmh, 2)
                allure_max = round(60 / v_kmh, 2)

        vo2 = brute.get("vO2MaxValue")

        activite = {
            "date": date_iso,
            "nom": brute.get("name") or "",
            "type": type_app,
            "distance": distance_km,
            "denivele": denivele_m,
            "duree": duree_s,
            "vitesse_moyenne": vitesse_moyenne,
            "allure_moyenne": allure_moyenne,
            "frequence_cardiaque_moyenne": round(brute["avgHr"]) if brute.get("avgHr") else None,
            "frequence_cardiaque_max": round(brute["maxHr"]) if brute.get("maxHr") else None,
            "calories": round(brute["calories"]) if brute.get("calories") else None,
            "denivele_negatif": denivele_neg_m or None,
            "vitesse_max": vitesse_max,
            "allure_max": allure_max,
            "cadence_moyenne": _cadence(brute, type_app),
            "vo2max": round(vo2, 1) if vo2 else None,
            "source": "Garmin",
            "fichier_source": nom_fichier,
            "identifiant_externe": str(brute.get("activityId") or ""),
            "notes": "",
        }
        activite.update(_donnees_avancees(brute, type_app, duree_s))
        activite["empreinte"] = _creer_empreinte(activite)

        resultat.append(activite)

    return resultat
