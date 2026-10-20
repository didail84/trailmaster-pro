"""
Lecture et analyse de fichiers GPX (trace GPS), sans dépendance externe.

Gère les variantes de namespace XML les plus courantes (Garmin, Strava,
montres GPS génériques) et calcule distance / dénivelé à partir des
points de trace, en pur Python (stdlib uniquement).

Chaque point est retourné sous la forme (lat, lon, altitude,
temps_relatif_s, fc) — temps_relatif_s et fc valent None quand
l'information n'est pas présente dans le fichier (fréquent pour les
GPX plus anciens, qui n'ont souvent que lat/lon/altitude/temps).
"""

import math
import xml.etree.ElementTree as ET
from datetime import datetime


def parser_gpx(chemin_fichier):
    """Lit un fichier .gpx et retourne un dictionnaire :
    {
        "points": [(lat, lon, altitude, temps_relatif_s, fc), ...],
        "distance_km": float,
        "denivele_positif": int,
        "denivele_negatif": int,
        "altitude_min": int,
        "altitude_max": int,
        "date_debut": datetime | None,
        "date_fin": datetime | None,
    }
    """

    arbre = ET.parse(chemin_fichier)
    racine = arbre.getroot()

    # Le tag racine ressemble à '{http://www.topografix.com/GPX/1/1}gpx'.
    # On récupère ce namespace pour construire les chemins de recherche,
    # car il varie selon le logiciel exportateur.
    if racine.tag.startswith("{"):
        namespace_uri = racine.tag[1:].split("}")[0]
        ns = {"g": namespace_uri}
        prefixe = "g:"
    else:
        ns = {}
        prefixe = ""

    def trouver_tous(elem, chemin_relatif):
        return elem.findall(f".//{prefixe}{chemin_relatif}", ns)

    def trouver_altitude(point_elem):
        ele = point_elem.find(f"{prefixe}ele", ns)
        if ele is not None and ele.text:
            try:
                return float(ele.text)
            except ValueError:
                return 0.0
        return 0.0

    def trouver_horodatage(point_elem):
        temps = point_elem.find(f"{prefixe}time", ns)
        if temps is not None and temps.text:
            texte = temps.text.strip()
            try:
                # Ex. "2012-02-18T08:17:09Z"
                return datetime.strptime(texte, "%Y-%m-%dT%H:%M:%SZ")
            except ValueError:
                pass
            try:
                # Ex. "2012-02-18T08:17:09.123Z" (secondes fractionnaires)
                return datetime.strptime(texte, "%Y-%m-%dT%H:%M:%S.%fZ")
            except ValueError:
                pass
            try:
                date = datetime.fromisoformat(texte.replace("Z", "+00:00"))
                return date.replace(tzinfo=None)
            except ValueError:
                return None
        return None

    def trouver_fc(point_elem):
        # La fréquence cardiaque est dans une extension dont le préfixe
        # de namespace varie selon le logiciel (gpxtpx:hr le plus souvent).
        # On cherche n'importe quel élément descendant nommé "hr", quel
        # que soit son namespace, plutôt que de coder un préfixe précis.
        for sous_elem in point_elem.iter():
            nom_local = sous_elem.tag.split("}")[-1]
            if nom_local.lower() == "hr" and sous_elem.text:
                try:
                    return int(float(sous_elem.text))
                except ValueError:
                    return None
        return None

    points = []
    horodatage_debut = None
    horodatage_fin = None

    # Cas le plus courant : des points de trace (trkpt) dans un ou
    # plusieurs segments (trkseg).
    for trkpt in trouver_tous(racine, "trkpt"):
        lat = float(trkpt.attrib["lat"])
        lon = float(trkpt.attrib["lon"])
        altitude = trouver_altitude(trkpt)
        horodatage_point = trouver_horodatage(trkpt)
        fc = trouver_fc(trkpt)

        if horodatage_debut is None:
            horodatage_debut = horodatage_point
        if horodatage_point is not None:
            horodatage_fin = horodatage_point

        temps_relatif_s = (
            (horodatage_point - horodatage_debut).total_seconds()
            if horodatage_point is not None and horodatage_debut is not None
            else None
        )

        points.append((lat, lon, altitude, temps_relatif_s, fc))

    # Repli : certains exports GPX (simples points d'intérêt) utilisent
    # des waypoints (wpt) plutôt qu'une trace continue.
    if not points:
        for wpt in trouver_tous(racine, "wpt"):
            lat = float(wpt.attrib["lat"])
            lon = float(wpt.attrib["lon"])
            points.append((lat, lon, trouver_altitude(wpt), None, None))

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

    distance_km = 0.0
    denivele_positif = 0.0
    denivele_negatif = 0.0

    # Seuil de 0.5 m entre deux points consécutifs pour ignorer le bruit
    # de mesure du capteur GPS/altimètre plutôt que du vrai dénivelé.
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


def _distance_haversine_km(lat1, lon1, lat2, lon2):
    """Distance à vol d'oiseau entre deux points GPS (formule de Haversine)."""

    rayon_terre_km = 6371.0

    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = (
        math.sin(delta_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
    )
    c = 2 * math.asin(math.sqrt(a))

    return rayon_terre_km * c
