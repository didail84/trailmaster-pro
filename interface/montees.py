"""
Détection automatique des montées individuelles à l'intérieur d'une
trace GPS (analyse du seul profil altimétrique déjà stocké — distance
et altitude entre points consécutifs, aucune donnée supplémentaire
requise).

Une montée est une séquence de points où l'altitude augmente de façon
globalement continue ; de petites redescentes sont tolérées à
l'intérieur d'une montée (bruit GPS/altimétrique), au-delà d'un seuil
la montée est considérée terminée.
"""

from interface.gpx_utils import _distance_haversine_km


SEUIL_GAIN_MINIMUM_M = 20     # en dessous, on ignore (faux plat/bruit)
SEUIL_FIN_MONTEE_M = 4        # redescente qui marque la fin d'une montée


def detecter_montees(points, seuil_gain_minimum_m=SEUIL_GAIN_MINIMUM_M):
    """points : liste de (lat, lon, altitude). Retourne une liste de
    montées triées par dénivelé décroissant."""

    if len(points) < 2:
        return []

    montees = []
    debut_idx = None
    denivele_courant = 0.0
    distance_courante_km = 0.0

    for i in range(1, len(points)):
        lat1, lon1, alt1 = points[i - 1][0], points[i - 1][1], points[i - 1][2]
        lat2, lon2, alt2 = points[i][0], points[i][1], points[i][2]
        d_km = _distance_haversine_km(lat1, lon1, lat2, lon2)
        diff_alt = alt2 - alt1

        if diff_alt > 0:
            if debut_idx is None:
                debut_idx = i - 1
                denivele_courant = 0.0
                distance_courante_km = 0.0
            denivele_courant += diff_alt
            distance_courante_km += d_km

        elif debut_idx is not None:
            if diff_alt < -SEUIL_FIN_MONTEE_M:
                # Redescente franche : la montée en cours se termine ici.
                if denivele_courant >= seuil_gain_minimum_m:
                    montees.append(_construire_montee(
                        points, debut_idx, i - 1, denivele_courant, distance_courante_km
                    ))
                debut_idx = None
                denivele_courant = 0.0
                distance_courante_km = 0.0
            else:
                # Petite variation tolérée : la montée continue.
                distance_courante_km += d_km

    if debut_idx is not None and denivele_courant >= seuil_gain_minimum_m:
        montees.append(_construire_montee(
            points, debut_idx, len(points) - 1, denivele_courant, distance_courante_km
        ))

    montees.sort(key=lambda m: m["denivele"], reverse=True)
    return montees


def _construire_montee(points, debut_idx, fin_idx, denivele, distance_km):
    altitude_depart = points[debut_idx][2]
    altitude_arrivee = points[fin_idx][2]
    pente_moyenne = (
        round((denivele / (distance_km * 1000)) * 100, 1) if distance_km > 0 else 0
    )

    return {
        "altitude_depart": round(altitude_depart),
        "altitude_arrivee": round(altitude_arrivee),
        "denivele": round(denivele),
        "distance_km": round(distance_km, 2),
        "pente_moyenne": pente_moyenne,
        "categorie": _categoriser_montee(denivele, pente_moyenne),
    }


def _categoriser_montee(denivele, pente_moyenne):
    """Catégorisation inspirée du Tour de France (score = dénivelé ×
    pente moyenne) — indicative, pas une classification officielle."""

    score = denivele * max(pente_moyenne, 0)

    if score >= 10000:
        return "Hors catégorie"
    if score >= 5000:
        return "Catégorie 1"
    if score >= 2000:
        return "Catégorie 2"
    if score >= 800:
        return "Catégorie 3"
    return "Catégorie 4"
