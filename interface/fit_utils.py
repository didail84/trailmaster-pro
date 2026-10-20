"""
Lecture de fichiers .fit (format binaire natif Garmin) via la
librairie fitparse. Retourne la même structure que gpx_utils.parser_gpx
pour rester interchangeable dans le reste de l'application.

Chaque point est retourné sous la forme (lat, lon, altitude,
temps_relatif_s, fc, cadence) — cadence est la valeur brute du champ
FIT (souvent le nombre de pas d'UN SEUL pied par minute chez Garmin ;
multiplier par 2 pour la cadence totale usuelle).

Note : dans un export "Exporter vos données" Garmin Connect classique,
les fichiers .fit du dossier des fichiers téléversés sont en grande
majorité des fichiers de suivi quotidien (pas, sommeil, stress) et des
segments de parcours communautaires — pas des enregistrements GPS
d'activité individuelle. Un vrai enregistrement d'activité (le seul
type exploitable ici) contient des messages "record" avec position
GPS ; cette fonction retourne une liste de points vide si ce n'est
pas le cas, plutôt que d'échouer.
"""

from fitparse import FitFile


SEMICERCLES_VERS_DEGRES = 180 / (2 ** 31)


def parser_fit(chemin_fichier):
    """Lit un fichier .fit et retourne la même structure que
    gpx_utils.parser_gpx : points, distance_km, denivele_positif,
    denivele_negatif, altitude_min, altitude_max, date_debut, date_fin."""

    fichier = FitFile(str(chemin_fichier))

    points = []
    horodatage_debut = None
    horodatage_fin = None
    for enregistrement in fichier.get_messages("record"):
        lat_brute = enregistrement.get_value("position_lat")
        lon_brute = enregistrement.get_value("position_long")
        if lat_brute is None or lon_brute is None:
            continue

        lat = lat_brute * SEMICERCLES_VERS_DEGRES
        lon = lon_brute * SEMICERCLES_VERS_DEGRES
        # Certains appareils/exports utilisent "enhanced_altitude" (plus
        # précis) plutôt que "altitude" — on essaie les deux.
        altitude = enregistrement.get_value("enhanced_altitude")
        if altitude is None:
            altitude = enregistrement.get_value("altitude") or 0.0

        fc = enregistrement.get_value("heart_rate")
        cadence = enregistrement.get_value("cadence")

        horodatage_point = enregistrement.get_value("timestamp")
        if horodatage_debut is None:
            horodatage_debut = horodatage_point
        if horodatage_point is not None:
            horodatage_fin = horodatage_point

        temps_relatif_s = (
            (horodatage_point - horodatage_debut).total_seconds()
            if horodatage_point is not None and horodatage_debut is not None
            else None
        )

        points.append((lat, lon, altitude, temps_relatif_s, fc, cadence))

    if not points:
        return {
            "points": [],
            "distance_km": 0.0,
            "denivele_positif": 0,
            "denivele_negatif": 0,
            "altitude_min": 0,
            "altitude_max": 0,
            "date_debut": None,
            "date_fin": None,
        }

    # Réutilise le même calcul de distance/dénivelé que pour un GPX,
    # pour rester cohérent entre les deux sources.
    from interface.gpx_utils import _distance_haversine_km

    distance_km = 0.0
    denivele_positif = 0.0
    denivele_negatif = 0.0
    SEUIL_BRUIT_M = 0.5

    for i in range(1, len(points)):
        lat1, lon1, alt1 = points[i - 1][0], points[i - 1][1], points[i - 1][2]
        lat2, lon2, alt2 = points[i][0], points[i][1], points[i][2]

        distance_km += _distance_haversine_km(lat1, lon1, lat2, lon2)

        diff_altitude = alt2 - alt1
        if diff_altitude > SEUIL_BRUIT_M:
            denivele_positif += diff_altitude
        elif diff_altitude < -SEUIL_BRUIT_M:
            denivele_negatif += abs(diff_altitude)

    altitudes = [p[2] for p in points]

    return {
        "points": points,
        "distance_km": round(distance_km, 2),
        "denivele_positif": round(denivele_positif),
        "denivele_negatif": round(denivele_negatif),
        "altitude_min": round(min(altitudes)),
        "altitude_max": round(max(altitudes)),
        "date_debut": horodatage_debut,
        "date_fin": horodatage_fin,
    }


_SPORT_VERS_TYPE = {
    "running": "Course",
    "cycling": "Vélo",
    "hiking": "Randonnée",
    "walking": "Randonnée",
    "training": "Cardio machine",
}
_SOUS_SPORT_VERS_TYPE = {
    "trail": "Trail",
    "trail_running": "Trail",
    "mountain": "VTT",
    "mountain_biking": "VTT",
    "gravel_cycling": "Vélo",
    "road": "Route",
    "treadmill": "Cardio machine",
    "indoor_cycling": "Cardio machine",
}


def _type_depuis_sport_fit(sport, sous_sport):
    """Traduit les champs 'sport'/'sub_sport' du FIT (chaînes en anglais,
    vocabulaire du SDK Garmin) vers un des types déjà utilisés partout
    ailleurs dans TrailMaster (Trail, Course, VTT, Vélo, Randonnée,
    Route, Cardio machine, Autre)."""

    sous_sport = (sous_sport or "").lower()
    if sous_sport in _SOUS_SPORT_VERS_TYPE:
        return _SOUS_SPORT_VERS_TYPE[sous_sport]
    sport = (sport or "").lower()
    return _SPORT_VERS_TYPE.get(sport, "Autre")


def parser_resume_session_fit(chemin_fichier):
    """Lit le message 'session' d'un .FIT — les totaux calculés par la
    montre elle-même (distance, durée, D+/D-, FC, calories, cadence),
    à ne pas confondre avec parser_fit() qui ne lit que les points GPS
    bruts et recalcule tout de son côté. Les deux sont complémentaires :
    ce résumé sert à remplir les champs d'une activité, parser_fit()
    fournit la trace pour la carte.

    Retourne un dict avec des clés déjà dans les unités utilisées par
    TrailMaster (km, m, secondes, bpm, km/h, pas/min), ou {} si le
    fichier ne contient aucun message 'session' exploitable (fichier
    de suivi quotidien plutôt qu'un enregistrement d'activité, par
    exemple)."""

    try:
        fichier = FitFile(str(chemin_fichier))
        messages_session = list(fichier.get_messages("session"))
    except Exception:
        return {}

    if not messages_session:
        return {}

    # Une activité multi-sport (rare) aurait plusieurs sessions ; on ne
    # gère que le cas courant d'une session unique par fichier.
    session = messages_session[0]

    def valeur(champ):
        try:
            return session.get_value(champ)
        except KeyError:
            return None

    distance_m = valeur("total_distance")
    duree_s = valeur("total_timer_time")
    cadence_brute = valeur("avg_cadence")

    resultat = {
        "type": _type_depuis_sport_fit(valeur("sport"), valeur("sub_sport")),
        "distance_km": round(distance_m / 1000, 3) if distance_m else None,
        "duree_s": round(duree_s) if duree_s else None,
        "denivele_positif": round(valeur("total_ascent")) if valeur("total_ascent") is not None else None,
        "denivele_negatif": round(valeur("total_descent")) if valeur("total_descent") is not None else None,
        "fc_moyenne": round(valeur("avg_heart_rate")) if valeur("avg_heart_rate") is not None else None,
        "fc_max": round(valeur("max_heart_rate")) if valeur("max_heart_rate") is not None else None,
        "calories": valeur("total_calories"),
        # avg_cadence du FIT est en général la cadence d'UN SEUL pied
        # (même convention que fitparse ailleurs dans ce fichier) —
        # doublée pour la cadence totale usuelle en course à pied.
        "cadence_moyenne": round(cadence_brute * 2) if cadence_brute is not None else None,
        "vitesse_moyenne_kmh": round(valeur("avg_speed") * 3.6, 2) if valeur("avg_speed") is not None else None,
        "vitesse_max_kmh": round(valeur("max_speed") * 3.6, 2) if valeur("max_speed") is not None else None,
        "date_debut": valeur("start_time"),
        "date_fin": valeur("timestamp"),
    }
    return resultat


def extraire_signaux_recuperation(chemin_fichier):
    """Cherche des signaux de récupération (HRV, stress) dans un .FIT,
    quand la montre les enregistre — non garanti selon le modèle et le
    type de fichier (un simple enregistrement d'activité GPS n'en
    contient souvent aucun ; ces signaux viennent plutôt des fichiers
    de suivi quotidien "monitoring"/"stress" d'un export complet).

    Retourne {"hrv_ms": float|None, "stress_moyen": int|None,
    "date": date|None} — jamais d'exception : une absence de signal
    donne juste des valeurs à None plutôt que de faire échouer l'import.

    HRV : les fichiers FIT n'exposent pas un "score HRV" tout fait côté
    activité — seulement, parfois, les intervalles RR bruts dans des
    messages "hrv". On en tire une approximation RMSSD (écart type des
    variations successives d'intervalles), l'indicateur HRV le plus
    courant, plutôt qu'une moyenne brute qui n'aurait pas de sens.
    """

    resultat = {"hrv_ms": None, "stress_moyen": None, "date": None}

    try:
        fichier = FitFile(str(chemin_fichier))
    except Exception:
        return resultat

    # --- HRV : intervalles RR (en secondes) dans les messages "hrv" ---
    rr_intervalles_ms = []
    try:
        for message in fichier.get_messages("hrv"):
            valeur = message.get_value("time")
            if valeur is None:
                continue
            valeurs = valeur if isinstance(valeur, (list, tuple)) else [valeur]
            for v in valeurs:
                if v is not None and 0.25 <= v <= 2.0:  # bornes physiologiques plausibles
                    rr_intervalles_ms.append(v * 1000)
    except Exception:
        pass

    if len(rr_intervalles_ms) >= 5:
        diffs = [
            rr_intervalles_ms[i + 1] - rr_intervalles_ms[i]
            for i in range(len(rr_intervalles_ms) - 1)
        ]
        if diffs:
            moyenne_carres = sum(d ** 2 for d in diffs) / len(diffs)
            resultat["hrv_ms"] = round(moyenne_carres ** 0.5, 1)

    # --- Stress : champ "stress_level" parfois présent sur les
    # messages "monitoring" (export quotidien) ou, plus rarement,
    # directement sur les "record" d'une activité.
    stress_valeurs = []
    horodatage = None
    for type_message in ("monitoring", "stress_level", "record"):
        try:
            for message in fichier.get_messages(type_message):
                v = message.get_value("stress_level")
                if v is not None and 0 <= v <= 100:
                    stress_valeurs.append(v)
                if horodatage is None:
                    horodatage = message.get_value("timestamp")
        except Exception:
            continue

    if stress_valeurs:
        resultat["stress_moyen"] = round(sum(stress_valeurs) / len(stress_valeurs))

    if horodatage is not None:
        resultat["date"] = horodatage.date() if hasattr(horodatage, "date") else None

    return resultat
