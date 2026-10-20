"""
Import des traces depuis un export Strava ("Exporter vos données").

Strava fournit un fichier activities.csv récapitulatif (attention : la
colonne "Distance" y apparaît deux fois — une version conviviale en km
et une version technique en mètres plus loin ; csv.DictReader ne garde
que la dernière, il faut donc lire les colonnes par position) et un
dossier activities/ avec un fichier par activité, dans des formats
variables : .fit.gz, .gpx.gz, .gpx, .fit, ou un .json (export mobile
Strava, plus rare).
"""

import csv
import gzip
import json
import shutil
import tempfile
from pathlib import Path

from interface.gpx_utils import parser_gpx, _distance_haversine_km
from interface.fit_utils import parser_fit


def lire_activites_csv(chemin_csv):
    """Lit activities.csv et retourne une liste de dicts robustes aux
    colonnes dupliquées du fichier Strava."""

    with open(chemin_csv, encoding="utf-8") as f:
        lecteur = csv.reader(f)
        entete = next(lecteur)

        idx_id = entete.index("ID de l'activité")
        idx_date = entete.index("Date de l'activité")
        idx_nom = entete.index("Nom de l'activité")
        idx_type = entete.index("Type d'activité")
        idx_distance = entete.index("Distance")  # 1ère occurrence = km
        idx_fichier = entete.index("Nom du fichier")

        idx_denivele = entete.index("Dénivelé positif") if "Dénivelé positif" in entete else None
        idx_duree = entete.index("Durée de déplacement") if "Durée de déplacement" in entete else None
        idx_fc = entete.index("Fréquence cardiaque moyenne") if "Fréquence cardiaque moyenne" in entete else None
        idx_calories = entete.index("Calories") if "Calories" in entete else None

        lignes = list(lecteur)

    def flottant(valeur):
        if not valeur:
            return None
        try:
            return float(valeur.replace(",", "."))
        except ValueError:
            return None

    resultat = []
    for l in lignes:
        if len(l) <= idx_fichier:
            continue
        resultat.append({
            "id": l[idx_id],
            "date_texte": l[idx_date],
            "nom": l[idx_nom],
            "type": l[idx_type],
            "distance_km": flottant(l[idx_distance]) or 0.0,
            "fichier": l[idx_fichier],
            "denivele_positif": flottant(l[idx_denivele]) if idx_denivele is not None else None,
            "duree_s": flottant(l[idx_duree]) if idx_duree is not None else None,
            "fc_moyenne": flottant(l[idx_fc]) if idx_fc is not None else None,
            "calories": flottant(l[idx_calories]) if idx_calories is not None else None,
        })

    return resultat


def _parser_json_mobile(chemin_fichier):
    """Format brut de l'appli mobile Strava (rare, quelques activités
    seulement) : {"data": [{"fields": [...], "values": [[...], ...]}]}."""

    with open(chemin_fichier, encoding="utf-8") as f:
        contenu = json.load(f)

    if not contenu.get("data"):
        return {"points": [], "distance_km": 0.0, "denivele_positif": 0,
                "denivele_negatif": 0, "altitude_min": 0, "altitude_max": 0,
                "date_debut": None, "date_fin": None}

    bloc = contenu["data"][0]
    champs = bloc["fields"]
    idx_latlng = champs.index("latlng") if "latlng" in champs else None
    idx_ele = champs.index("elevation") if "elevation" in champs else None
    idx_temps = champs.index("time") if "time" in champs else None

    points = []
    temps_debut = None
    for valeurs in bloc["values"]:
        if idx_latlng is None or valeurs[idx_latlng] is None:
            continue
        lat, lon = valeurs[idx_latlng]
        altitude = valeurs[idx_ele] if idx_ele is not None and valeurs[idx_ele] is not None else 0.0

        temps_relatif_s = None
        if idx_temps is not None and valeurs[idx_temps] is not None:
            if temps_debut is None:
                temps_debut = valeurs[idx_temps]
            temps_relatif_s = valeurs[idx_temps] - temps_debut

        points.append((lat, lon, altitude, temps_relatif_s, None))

    if not points:
        return {"points": [], "distance_km": 0.0, "denivele_positif": 0,
                "denivele_negatif": 0, "altitude_min": 0, "altitude_max": 0,
                "date_debut": None, "date_fin": None}

    distance_km = 0.0
    denivele_positif = 0.0
    denivele_negatif = 0.0
    for i in range(1, len(points)):
        lat1, lon1, alt1 = points[i - 1][0], points[i - 1][1], points[i - 1][2]
        lat2, lon2, alt2 = points[i][0], points[i][1], points[i][2]
        distance_km += _distance_haversine_km(lat1, lon1, lat2, lon2)
        diff = alt2 - alt1
        if diff > 0.5:
            denivele_positif += diff
        elif diff < -0.5:
            denivele_negatif += abs(diff)

    altitudes = [p[2] for p in points]

    return {
        "points": points,
        "distance_km": round(distance_km, 2),
        "denivele_positif": round(denivele_positif),
        "denivele_negatif": round(denivele_negatif),
        "altitude_min": round(min(altitudes)),
        "altitude_max": round(max(altitudes)),
        "date_debut": contenu["metadata"].get("start_date"),
        "date_fin": None,
    }


def parser_fichier_trace(chemin_fichier):
    """Point d'entrée unique : dispatch selon l'extension et retourne
    toujours la même structure (points/distance_km/denivele_.../date_debut)."""

    chemin = Path(chemin_fichier)
    nom = chemin.name.lower()

    if nom.endswith(".fit.gz"):
        with tempfile.NamedTemporaryFile(suffix=".fit", delete=False) as tmp:
            with gzip.open(chemin, "rb") as source:
                shutil.copyfileobj(source, tmp)
            chemin_temp = tmp.name
        try:
            return parser_fit(chemin_temp)
        finally:
            Path(chemin_temp).unlink(missing_ok=True)

    if nom.endswith(".gpx.gz"):
        with tempfile.NamedTemporaryFile(suffix=".gpx", delete=False) as tmp:
            with gzip.open(chemin, "rb") as source:
                shutil.copyfileobj(source, tmp)
            chemin_temp = tmp.name
        try:
            return parser_gpx(chemin_temp)
        finally:
            Path(chemin_temp).unlink(missing_ok=True)

    if nom.endswith(".fit"):
        return parser_fit(chemin)

    if nom.endswith(".gpx"):
        return parser_gpx(chemin)

    if nom.endswith(".json"):
        return _parser_json_mobile(chemin)

    return {"points": [], "distance_km": 0.0, "denivele_positif": 0,
            "denivele_negatif": 0, "altitude_min": 0, "altitude_max": 0,
            "date_debut": None, "date_fin": None}
