"""
Synchronisation des activités Strava vers la base TrailMaster Pro.
Convertit le format Strava (JSON + flux séparés par type) vers notre
schéma habituel (table activites + parcours_gpx, points au format
(lat, lon, alt, temps_relatif_s, fc, cadence)).
"""

import time
from datetime import datetime

from data.completer_activites import completer_activite
from data.database import connexion, obtenir_parametre, definir_parametre
from interface.date_utils import parser_date_flexible
from interface.strava_api import (
    rafraichir_jetons,
    obtenir_activites,
    obtenir_flux_activite,
)


FENETRE_TEMPS_MINUTES = 15


TYPES_STRAVA_VERS_APP = {
    "TrailRun": "Trail",
    "Run": "Course",
    "VirtualRun": "Course",
    "MountainBikeRide": "VTT",
    "GravelRide": "VTT",
    "Ride": "Vélo",
    "VirtualRide": "Vélo",
    "EBikeRide": "Vélo",
    "Hike": "Randonnée",
    "Walk": "Randonnée",
}


def _type_app(sport_type, type_generique):
    return TYPES_STRAVA_VERS_APP.get(sport_type) or TYPES_STRAVA_VERS_APP.get(type_generique, "Autre")


def _date_iso_depuis_strava(date_locale_texte):
    try:
        return datetime.strptime(date_locale_texte, "%Y-%m-%dT%H:%M:%SZ").strftime("%Y-%m-%d %H:%M:%S")
    except (ValueError, TypeError):
        return date_locale_texte


def _construire_points(flux):
    latlng = flux.get("latlng")
    if not latlng:
        return []

    altitude = flux.get("altitude") or []
    heartrate = flux.get("heartrate") or []
    cadence = flux.get("cadence") or []
    temps = flux.get("time") or []

    points = []
    for i, latlon in enumerate(latlng):
        lat, lon = latlon
        alt = altitude[i] if i < len(altitude) else 0.0
        t = temps[i] if i < len(temps) else None
        hr = heartrate[i] if i < len(heartrate) else None
        cad = cadence[i] if i < len(cadence) else None
        points.append((lat, lon, alt, t, hr, cad))

    return points


def obtenir_jetons_valides(client_id, client_secret):
    """Retourne (access_token, jetons_mis_a_jour_ou_None, erreur)."""

    access_token = obtenir_parametre("strava_access_token")
    refresh_token = obtenir_parametre("strava_refresh_token")
    expires_at = obtenir_parametre("strava_expires_at")

    if not access_token or not refresh_token:
        return None, None, "Non connecté à Strava."

    if expires_at and time.time() > float(expires_at) - 60:
        jetons, erreur = rafraichir_jetons(client_id, client_secret, refresh_token)
        if erreur:
            return None, None, erreur
        sauvegarder_jetons(jetons)
        return jetons["access_token"], jetons, None

    return access_token, None, None


def sauvegarder_jetons(jetons):
    definir_parametre("strava_access_token", jetons["access_token"])
    definir_parametre("strava_refresh_token", jetons["refresh_token"])
    definir_parametre("strava_expires_at", jetons["expires_at"])


def _activite_deja_connue(cur, athlete_id, strava_id, date_iso, distance_km):
    return _trouver_activite_connue(cur, athlete_id, strava_id, date_iso, distance_km) is not None


def _trouver_activite_connue(cur, athlete_id, strava_id, date_iso, distance_km):
    """Vérifie qu'aucune activité — quelle que soit sa source (import
    manuel Garmin/Strava passé, ou synchro précédente) — ne correspond
    déjà à celle-ci. Sans ce contrôle élargi, une première synchro qui
    recouvre une période déjà importée manuellement créerait des
    doublons (même sortie comptée deux fois dans la charge/ACWR).

    La comparaison se fait sur une fenêtre de quelques minutes autour
    de l'horodatage exact (pas "le même jour") : une comparaison à la
    journée entière classerait à tort deux vraies sorties distinctes
    le même jour comme un doublon."""

    cur.execute(
        "SELECT id FROM activites WHERE athlete_id=? AND identifiant_externe=? AND source='Strava (sync)'",
        (athlete_id, strava_id),
    )
    ligne = cur.fetchone()
    if ligne:
        return ligne[0]

    date_activite = parser_date_flexible(date_iso)
    if date_activite is None:
        return None

    cur.execute(
        "SELECT date, distance, id FROM activites WHERE athlete_id=? AND date LIKE ?",
        (athlete_id, date_activite.strftime("%Y-%m-%d") + "%"),
    )
    for date_existante_texte, distance_existante, id_existant in cur.fetchall():
        date_existante = parser_date_flexible(date_existante_texte)
        if date_existante is None or distance_existante is None:
            continue
        ecart_minutes = abs((date_existante - date_activite).total_seconds()) / 60
        if ecart_minutes > FENETRE_TEMPS_MINUTES:
            continue
        ecart_distance = abs(distance_existante - distance_km)
        if ecart_distance <= max(0.3, distance_km * 0.1):
            return id_existant

    return None


# Compte rendu de la dernière synchronisation (lu par l'écran Strava).
DERNIER_BILAN = {"completees": 0}


def _parametres_resume(activite, type_app, distance_km, duree_s):
    """Paramètres calculables depuis le résumé Strava (sans flux GPS)."""
    vitesse_moy = allure_moy = None
    if distance_km and duree_s:
        vitesse_moy = round(distance_km / (duree_s / 3600), 2)
        allure_moy = round((duree_s / 60) / distance_km, 2)

    vitesse_max = allure_max = None
    if activite.get("max_speed"):
        v = activite["max_speed"] * 3.6
        if 0 < v <= (80 if type_app in ("Vélo", "VTT") else 40) and (vitesse_moy is None or v >= vitesse_moy):
            vitesse_max = round(v, 2)
            allure_max = round(60 / v, 2)

    cadence = activite.get("average_cadence")
    if cadence:
        # Strava donne la cadence d'un seul pied en course : on double.
        if type_app in ("Trail", "Course", "Randonnée") and cadence < 120:
            cadence = cadence * 2
        cadence = round(cadence)

    fc_max = activite.get("max_heartrate")
    return {
        "vitesse_moyenne": vitesse_moy, "allure_moyenne": allure_moy,
        "frequence_cardiaque_moyenne": activite.get("average_heartrate"),
        "frequence_cardiaque_max": round(fc_max) if fc_max else None,
        "calories": activite.get("calories"),
        "vitesse_max": vitesse_max, "allure_max": allure_max,
        "cadence_moyenne": cadence or None,
        # Détail avancé (v91)
        "effort_percu": activite.get("perceived_exertion"),
        "suffer_score": activite.get("suffer_score"),
        "temperature_moyenne": activite.get("average_temp"),
        "puissance_moyenne": round(activite["average_watts"]) if activite.get("device_watts") and activite.get("average_watts") else None,
        "puissance_max": round(activite["max_watts"]) if activite.get("device_watts") and activite.get("max_watts") else None,
    }


def _denivele_negatif_depuis_flux(flux, denivele_positif):
    """D− ≈ D+ − (altitude d'arrivée − altitude de départ) : cohérent avec
    le D+ corrigé par Strava, sans cumuler le bruit du capteur."""
    altitude = (flux or {}).get("altitude") or []
    if len(altitude) < 2:
        return None
    return max(0, round(denivele_positif - (altitude[-1] - altitude[0]))) or None


def synchroniser(athlete_id, client_id, client_secret, callback_progression=None, historique_complet=False):
    """Récupère les nouvelles activités Strava depuis la dernière
    synchronisation et les insère en base. Parcourt toutes les pages
    disponibles (pas seulement la première). Retourne (nb_nouvelles,
    nb_erreurs, erreur_globale)."""

    access_token, _, erreur = obtenir_jetons_valides(client_id, client_secret)
    if erreur:
        return 0, 0, erreur

    derniere_sync = obtenir_parametre(f"strava_derniere_activite_epoch_{athlete_id}")
    apres = int(derniere_sync) if derniere_sync else None
    if historique_complet:
        apres = None  # tout relire : les sorties déjà connues sont complétées, pas dupliquées
    DERNIER_BILAN["completees"] = 0

    toutes_activites = []
    page = 1
    while True:
        lot, erreur = obtenir_activites(access_token, apres_timestamp=apres, page=page, par_page=100)
        if erreur:
            return 0, 0, erreur
        if not lot:
            break
        toutes_activites.extend(lot)
        if len(lot) < 100:
            break
        page += 1

    if not toutes_activites:
        return 0, 0, None

    conn = connexion()
    cur = conn.cursor()

    nb_nouvelles = 0
    nb_erreurs = 0
    epoch_le_plus_recent = apres or 0

    for i, activite in enumerate(toutes_activites):
        if callback_progression:
            callback_progression(i + 1, len(toutes_activites))

        try:
            strava_id = str(activite["id"])
            date_iso = _date_iso_depuis_strava(activite.get("start_date_local", ""))
            distance_km = round((activite.get("distance") or 0) / 1000, 3)

            type_app = _type_app(activite.get("sport_type"), activite.get("type"))
            denivele = round(activite.get("total_elevation_gain") or 0)
            duree_s = activite.get("moving_time") or 0
            extra = _parametres_resume(activite, type_app, distance_km, duree_s)

            id_connu = _trouver_activite_connue(cur, athlete_id, strava_id, date_iso, distance_km)
            if id_connu is not None:
                if completer_activite(cur, id_connu, extra):
                    DERNIER_BILAN["completees"] += 1
                continue

            fc_moyenne = activite.get("average_heartrate")
            calories = activite.get("calories")

            cur.execute(
                """
                INSERT INTO activites (
                    athlete_id, date, nom, type, distance, denivele, duree,
                    frequence_cardiaque_moyenne, calories, source, identifiant_externe,
                    vitesse_moyenne, allure_moyenne, frequence_cardiaque_max,
                    vitesse_max, allure_max, cadence_moyenne
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    athlete_id, date_iso, activite.get("name", ""), type_app,
                    distance_km, denivele, duree_s, fc_moyenne, calories,
                    "Strava (sync)", strava_id,
                    extra["vitesse_moyenne"], extra["allure_moyenne"],
                    extra["frequence_cardiaque_max"], extra["vitesse_max"],
                    extra["allure_max"], extra["cadence_moyenne"],
                ),
            )
            nouvelle_activite_id = cur.lastrowid
            completer_activite(cur, nouvelle_activite_id, extra)

            flux, erreur_flux = obtenir_flux_activite(access_token, activite["id"])
            if not erreur_flux and flux:
                dneg = _denivele_negatif_depuis_flux(flux, denivele)
                if dneg:
                    cur.execute(
                        "UPDATE activites SET denivele_negatif=? WHERE id=?",
                        (dneg, nouvelle_activite_id),
                    )
            if not erreur_flux and flux and flux.get("latlng"):
                points = _construire_points(flux)
                if points:
                    import json
                    cur.execute(
                        """
                        INSERT INTO parcours_gpx (
                            athlete_id, nom, distance_km, denivele_positif,
                            trace_json, activite_id
                        ) VALUES (?,?,?,?,?,?)
                        """,
                        (
                            athlete_id, activite.get("name", ""), distance_km,
                            denivele, json.dumps(points), nouvelle_activite_id,
                        ),
                    )

            nb_nouvelles += 1

            timestamp_activite = activite.get("start_date")
            if timestamp_activite:
                try:
                    epoch_activite = int(
                        datetime.strptime(timestamp_activite, "%Y-%m-%dT%H:%M:%SZ").timestamp()
                    )
                    epoch_le_plus_recent = max(epoch_le_plus_recent, epoch_activite)
                except ValueError:
                    pass

        except Exception:
            nb_erreurs += 1

    conn.commit()
    conn.close()

    if epoch_le_plus_recent:
        definir_parametre(f"strava_derniere_activite_epoch_{athlete_id}", epoch_le_plus_recent)

    return nb_nouvelles, nb_erreurs, None
