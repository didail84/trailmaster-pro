"""
Intégration météo via Open-Meteo (https://open-meteo.com) — gratuit,
sans clé API, sans compte, pour un usage non commercial. Nécessite une
connexion internet à chaque appel.

Aucune dépendance externe : utilise uniquement urllib (bibliothèque
standard de Python), pas besoin d'installer "requests".
"""

import json
import urllib.request
import urllib.error

from interface.erreurs_reseau import message_erreur_reseau


URL_PREVISION = "https://api.open-meteo.com/v1/forecast"
URL_HISTORIQUE = "https://archive-api.open-meteo.com/v1/archive"

CODES_METEO = {
    0: "Ciel dégagé", 1: "Principalement dégagé", 2: "Partiellement nuageux", 3: "Couvert",
    45: "Brouillard", 48: "Brouillard givrant",
    51: "Bruine légère", 53: "Bruine modérée", 55: "Bruine dense",
    56: "Bruine verglaçante légère", 57: "Bruine verglaçante dense",
    61: "Pluie légère", 63: "Pluie modérée", 65: "Pluie forte",
    66: "Pluie verglaçante légère", 67: "Pluie verglaçante forte",
    71: "Neige légère", 73: "Neige modérée", 75: "Neige forte", 77: "Grains de neige",
    80: "Averses légères", 81: "Averses modérées", 82: "Averses violentes",
    85: "Averses de neige légères", 86: "Averses de neige fortes",
    95: "Orage", 96: "Orage avec grêle légère", 99: "Orage avec grêle forte",
}


def _description_code(code):
    return CODES_METEO.get(code, f"Code météo {code}")


def _requete_json(url):
    try:
        with urllib.request.urlopen(url, timeout=10) as reponse:
            return json.loads(reponse.read().decode("utf-8")), None
    except urllib.error.URLError as erreur:
        return None, message_erreur_reseau(erreur)
    except Exception as erreur:
        return None, f"Erreur lors de la récupération de la météo : {erreur}"


def obtenir_meteo_actuelle_et_previsions(latitude, longitude):
    """Retourne (donnees, erreur). donnees = {"actuel": {...},
    "previsions": [7 jours]}."""

    url = (
        f"{URL_PREVISION}?latitude={latitude}&longitude={longitude}"
        "&current=temperature_2m,relative_humidity_2m,precipitation,weather_code,wind_speed_10m"
        "&daily=weather_code,temperature_2m_max,temperature_2m_min,precipitation_sum,wind_speed_10m_max"
        "&timezone=auto&forecast_days=7"
    )

    contenu, erreur = _requete_json(url)
    if erreur:
        return None, erreur

    try:
        actuel_brut = contenu["current"]
        quotidien = contenu["daily"]

        actuel = {
            "temperature": actuel_brut["temperature_2m"],
            "humidite": actuel_brut["relative_humidity_2m"],
            "precipitation": actuel_brut["precipitation"],
            "vent_kmh": actuel_brut["wind_speed_10m"],
            "description": _description_code(actuel_brut["weather_code"]),
        }

        previsions = []
        for i, date in enumerate(quotidien["time"]):
            previsions.append({
                "date": date,
                "temperature_min": quotidien["temperature_2m_min"][i],
                "temperature_max": quotidien["temperature_2m_max"][i],
                "precipitation_mm": quotidien["precipitation_sum"][i],
                "vent_max_kmh": quotidien["wind_speed_10m_max"][i],
                "description": _description_code(quotidien["weather_code"][i]),
            })

        return {"actuel": actuel, "previsions": previsions}, None
    except (KeyError, IndexError) as erreur:
        return None, f"Réponse météo inattendue (champ manquant : {erreur})"


def obtenir_meteo_historique(latitude, longitude, date_iso):
    """date_iso au format YYYY-MM-DD. Retourne (donnees, erreur)."""

    url = (
        f"{URL_HISTORIQUE}?latitude={latitude}&longitude={longitude}"
        f"&start_date={date_iso}&end_date={date_iso}"
        "&daily=weather_code,temperature_2m_max,temperature_2m_min,precipitation_sum,wind_speed_10m_max"
        "&timezone=auto"
    )

    contenu, erreur = _requete_json(url)
    if erreur:
        return None, erreur

    try:
        quotidien = contenu["daily"]
        if not quotidien["time"]:
            return None, "Aucune donnée météo disponible pour cette date."

        return {
            "date": quotidien["time"][0],
            "temperature_min": quotidien["temperature_2m_min"][0],
            "temperature_max": quotidien["temperature_2m_max"][0],
            "precipitation_mm": quotidien["precipitation_sum"][0],
            "vent_max_kmh": quotidien["wind_speed_10m_max"][0],
            "description": _description_code(quotidien["weather_code"][0]),
        }, None
    except (KeyError, IndexError) as erreur:
        return None, f"Réponse météo inattendue (champ manquant : {erreur})"
