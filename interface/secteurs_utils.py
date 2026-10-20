"""
Analyse par secteurs géographiques des traces GPX enregistrées.

Regroupe les tracés dont le point de départ est proche (mêmes environs)
en "secteurs", puis calcule pour chacun un score combinant :
  - la fraîcheur : depuis combien de temps ce secteur n'a pas été
    fréquenté (pour varier les sorties plutôt que toujours répéter
    les mêmes parcours)
  - le profil : à quel point la distance/le dénivelé moyens de ce
    secteur correspondent à l'objectif d'entraînement du moment

Aucune dépendance externe, aucun appel réseau — tout est calculé à
partir des traces déjà en base (voir interface/parcours_gpx.py).
"""

from collections import Counter
from datetime import datetime

from data.database import connexion
from interface.date_utils import parser_date_flexible
from interface.gpx_utils import _distance_haversine_km


RAYON_SECTEUR_KM = 4.0


def obtenir_traces_avec_contexte(athlete_id):
    """Retourne les traces de l'athlète avec leur date et type
    d'activité liée (via activite_id), triées par date croissante."""

    conn = connexion()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT p.id, p.nom, p.distance_km, p.denivele_positif, p.trace_json,
               a.date, a.type
        FROM parcours_gpx p
        LEFT JOIN activites a ON p.activite_id = a.id
        WHERE p.athlete_id = ?
        """,
        (athlete_id,),
    )
    lignes = cur.fetchall()
    conn.close()

    import json

    traces = []
    for id_, nom, distance_km, denivele, trace_json, date_texte, type_ in lignes:
        if not trace_json:
            continue
        try:
            points = json.loads(trace_json)
        except (ValueError, TypeError):
            continue
        if not points:
            continue

        date = parser_date_flexible(date_texte) if date_texte else None

        traces.append({
            "id": id_,
            "nom": nom or "Sans nom",
            "distance_km": distance_km or 0,
            "denivele_positif": denivele or 0,
            "point_depart": (points[0][0], points[0][1]),
            "points": points,
            "date": date,
            "type": type_ or "Autre",
        })

    traces.sort(key=lambda t: t["date"] or datetime.min)
    return traces


def regrouper_en_secteurs(traces, rayon_km=RAYON_SECTEUR_KM):
    """Regroupe les traces par proximité géographique de leur point de
    départ (algorithme glouton : chaque trace rejoint le premier
    secteur existant dont le centre est à moins de rayon_km, sinon
    elle en crée un nouveau)."""

    secteurs = []

    for trace in traces:
        lat, lon = trace["point_depart"]

        secteur_trouve = None
        for secteur in secteurs:
            centre_lat, centre_lon = secteur["centre"]
            if _distance_haversine_km(lat, lon, centre_lat, centre_lon) <= rayon_km:
                secteur_trouve = secteur
                break

        if secteur_trouve:
            secteur_trouve["traces"].append(trace)
            lats = [t["point_depart"][0] for t in secteur_trouve["traces"]]
            lons = [t["point_depart"][1] for t in secteur_trouve["traces"]]
            secteur_trouve["centre"] = (sum(lats) / len(lats), sum(lons) / len(lons))
        else:
            secteurs.append({"centre": (lat, lon), "traces": [trace]})

    return secteurs


def _nom_secteur(secteur):
    noms = [t["nom"] for t in secteur["traces"]]
    plus_frequent = Counter(noms).most_common(1)
    if plus_frequent and plus_frequent[0][1] > 1:
        return plus_frequent[0][0]
    # Aucun nom répété : on prend celui de la trace la plus ancienne
    return secteur["traces"][0]["nom"]


def calculer_stats_secteurs(athlete_id, distance_visee_km=None, denivele_vise_m=None,
                             rayon_km=RAYON_SECTEUR_KM):
    """Retourne une liste de secteurs avec leurs statistiques et scores,
    triée par score global décroissant (le meilleur choix en premier)."""

    traces = obtenir_traces_avec_contexte(athlete_id)
    secteurs_bruts = regrouper_en_secteurs(traces, rayon_km=rayon_km)

    aujourdhui = datetime.now()
    resultat = []

    for secteur in secteurs_bruts:
        traces_secteur = secteur["traces"]
        n = len(traces_secteur)

        distances = [t["distance_km"] for t in traces_secteur]
        deniveles = [t["denivele_positif"] for t in traces_secteur]
        dates = [t["date"] for t in traces_secteur if t["date"] is not None]

        distance_moyenne = round(sum(distances) / n, 1) if n else 0
        denivele_moyen = round(sum(deniveles) / n) if n else 0
        derniere_visite = max(dates) if dates else None
        types_pratiques = Counter(t["type"] for t in traces_secteur)

        if derniere_visite:
            jours_depuis = (aujourdhui - derniere_visite).days
        else:
            jours_depuis = None

        # Score fraîcheur : 0 (visité aujourd'hui) à 100 (60 jours ou plus,
        # ou jamais daté) — encourage à varier plutôt qu'à répéter.
        if jours_depuis is None:
            score_fraicheur = 100
        else:
            score_fraicheur = round(min(max(jours_depuis, 0) / 60 * 100, 100))

        # Score profil : proximité entre la distance/le dénivelé moyens du
        # secteur et l'objectif saisi. Sans objectif renseigné, le profil
        # ne pénalise ni n'avantage aucun secteur (score neutre à 100).
        if distance_visee_km or denivele_vise_m:
            ecarts = []
            if distance_visee_km:
                ecarts.append(abs(distance_moyenne - distance_visee_km) / max(distance_visee_km, 0.1))
            if denivele_vise_m:
                ecarts.append(abs(denivele_moyen - denivele_vise_m) / max(denivele_vise_m, 1))
            ecart_moyen = sum(ecarts) / len(ecarts)
            score_profil = round(max(100 - ecart_moyen * 100, 0))
        else:
            score_profil = 100

        score_global = round((score_fraicheur + score_profil) / 2)

        resultat.append({
            "nom": _nom_secteur(secteur),
            "centre": secteur["centre"],
            "nb_sorties": n,
            "types": dict(types_pratiques),
            "distance_moyenne": distance_moyenne,
            "denivele_moyen": denivele_moyen,
            "derniere_visite": derniere_visite,
            "jours_depuis_visite": jours_depuis,
            "score_fraicheur": score_fraicheur,
            "score_profil": score_profil,
            "score_global": score_global,
            "traces": traces_secteur,
        })

    resultat.sort(key=lambda s: s["score_global"], reverse=True)
    return resultat
