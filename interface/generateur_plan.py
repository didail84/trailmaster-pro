"""
Génération d'un plan d'entraînement structuré par objectif (10 km,
semi-marathon, marathon, trail court, trail long/ultra), sur un nombre
de semaines donné.

Principe (méthode classique de périodisation, pas un coach qui
s'adapte à la façon dont les séances précédentes ont été réalisées) :
  - Phase base (~40% du plan) : volume progressif, endurance fondamentale
  - Phase développement (~40-45%) : ajout fractionné/côtes en alternance
  - Phase affûtage (~15-20% finaux) : réduction du volume, on garde
    un peu d'intensité, repos avant la course
  - Une semaine de récupération (volume réduit ~30%) tous les 4
    semaines de base/développement

Les allures de chaque type de séance sont dérivées d'une allure
objectif (celle visée sur la distance de la course), avec des écarts
standards (endurance +20%, seuil +3%, fractionné -10%, récupération
+35%) — une simplification raisonnable, pas une prescription
individualisée par un vrai coach.
"""

from datetime import timedelta

from interface.conformite import parser_allure


PARAMETRES_DISTANCE = {
    "10 km": {"volume_debut": 20, "volume_pic": 35, "long_debut": 8, "long_pic": 14},
    "Semi-marathon": {"volume_debut": 25, "volume_pic": 45, "long_debut": 10, "long_pic": 18},
    "Marathon": {"volume_debut": 30, "volume_pic": 65, "long_debut": 12, "long_pic": 32},
    "Trail court (< 30 km)": {"volume_debut": 25, "volume_pic": 50, "long_debut": 10, "long_pic": 22},
    "Trail long / Ultra (> 50 km)": {"volume_debut": 35, "volume_pic": 75, "long_debut": 15, "long_pic": 35},
}

FACTEUR_NIVEAU = {
    "Débutant": 0.7,
    "Intermédiaire": 1.0,
    "Confirmé": 1.3,
}

JOURS_DISPONIBLES = {
    3: [1, 3, 6],           # mardi, jeudi, dimanche
    4: [1, 3, 5, 6],        # + samedi
    5: [0, 1, 3, 5, 6],     # + lundi
    6: [0, 1, 2, 3, 5, 6],  # + mercredi
}

NOMS_JOURS = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]


def _formater_allure(minutes_par_km):
    if not minutes_par_km:
        return None
    m = int(minutes_par_km)
    s = round((minutes_par_km - m) * 60)
    if s == 60:
        m += 1
        s = 0
    return f"{m}:{s:02d}"


def _allures_semaine(allure_objectif_min_km):
    if not allure_objectif_min_km:
        return {}
    return {
        "endurance": allure_objectif_min_km * 1.20,
        "seuil": allure_objectif_min_km * 1.03,
        "fractionne": allure_objectif_min_km * 0.90,
        "recuperation": allure_objectif_min_km * 1.35,
    }


def _phase_semaine(indice_semaine, nb_semaines, semaines_affutage):
    if indice_semaine > nb_semaines - semaines_affutage:
        return "affutage"
    if indice_semaine <= round(nb_semaines * 0.4):
        return "base"
    return "developpement"


def _est_semaine_recuperation(indice_semaine, phase):
    return phase != "affutage" and indice_semaine % 4 == 0


def _volume_semaine(indice_semaine, nb_semaines, volume_debut, volume_pic, phase, semaines_affutage):
    semaine_pic = max(nb_semaines - semaines_affutage, 1)

    if phase == "affutage":
        semaines_restantes = nb_semaines - indice_semaine
        reduction = {0: 0.5, 1: 0.7, 2: 0.85}.get(semaines_restantes, 0.6)
        return round(volume_pic * reduction)

    progression = min(indice_semaine / semaine_pic, 1.0)
    volume = volume_debut + (volume_pic - volume_debut) * progression

    if _est_semaine_recuperation(indice_semaine, phase):
        volume *= 0.7

    return round(volume)


def _distance_longue_semaine(indice_semaine, nb_semaines, long_debut, long_pic, phase, semaines_affutage):
    semaine_pic = max(nb_semaines - semaines_affutage, 1)

    if phase == "affutage":
        semaines_restantes = nb_semaines - indice_semaine
        reduction = {0: 0.4, 1: 0.6, 2: 0.8}.get(semaines_restantes, 0.6)
        return round(long_pic * reduction, 1)

    progression = min(indice_semaine / semaine_pic, 1.0)
    distance = long_debut + (long_pic - long_debut) * progression

    if _est_semaine_recuperation(indice_semaine, phase):
        distance *= 0.75

    return round(distance, 1)


def _etape(type_, mode, valeur, allure_min_km=None):
    return {
        "type": type_,
        "mode": mode,
        "valeur": round(valeur, 2),
        "allure_cible": _formater_allure(allure_min_km),
        "fc_cible": None,
    }


def _construire_semaine(jours, volume, longue, phase, recuperation, allures, indice):
    reste_volume = max(volume - longue, 0)
    n_autres = len(jours) - 1

    seances = [{
        "jour_offset": jours[-1],
        "nom": "Sortie longue",
        "type_seance": "Sortie longue",
        "etapes": [_etape("Effort", "distance", longue, allures.get("endurance"))],
    }]

    if n_autres <= 0:
        return seances

    if phase == "base" or recuperation:
        volume_par_jour = reste_volume / n_autres
        for j in jours[:-1]:
            seances.append({
                "jour_offset": j,
                "nom": "Endurance fondamentale",
                "type_seance": "Endurance fondamentale",
                "etapes": [_etape("Effort", "distance", volume_par_jour, allures.get("endurance"))],
            })
        return seances

    jours_qualite = jours[:-1][:1]
    jours_endurance = jours[:-1][1:]

    volume_qualite = min(reste_volume * 0.35, 12)
    volume_restant = max(reste_volume - volume_qualite, 0)
    volume_par_jour_endurance = volume_restant / max(len(jours_endurance), 1)

    type_qualite = "Fractionné" if indice % 2 == 1 else "Côtes"
    allure_qualite = allures.get("fractionne") if type_qualite == "Fractionné" else allures.get("seuil")

    etapes_qualite = [_etape("Échauffement", "distance", 2, allures.get("endurance"))]
    n_repets = 6 if type_qualite == "Fractionné" and phase == "developpement" else (
        4 if type_qualite == "Fractionné" else 5
    )
    distance_effort = 0.8 if type_qualite == "Fractionné" else 0.6
    for _ in range(n_repets):
        etapes_qualite.append(_etape("Effort", "distance", distance_effort, allure_qualite))
        etapes_qualite.append(_etape("Récupération", "distance", 0.4, allures.get("recuperation")))
    etapes_qualite.append(_etape("Retour au calme", "distance", 2, allures.get("endurance")))

    seances.append({
        "jour_offset": jours_qualite[0] if jours_qualite else jours[0],
        "nom": type_qualite,
        "type_seance": type_qualite,
        "etapes": etapes_qualite,
    })

    for j in jours_endurance:
        seances.append({
            "jour_offset": j,
            "nom": "Endurance fondamentale",
            "type_seance": "Endurance fondamentale",
            "etapes": [_etape("Effort", "distance", volume_par_jour_endurance, allures.get("endurance"))],
        })

    return seances


def generer_plan(distance_cible, nb_semaines, niveau, jours_par_semaine, allure_objectif_texte):
    """Retourne une liste de semaines : [{indice, phase, recuperation,
    volume_km, seances: [...]}, ...]. Ne touche pas à la base — c'est
    à l'appelant d'enregistrer le résultat s'il convient."""

    params = PARAMETRES_DISTANCE[distance_cible]
    facteur = FACTEUR_NIVEAU.get(niveau, 1.0)

    volume_debut = params["volume_debut"] * facteur
    volume_pic = params["volume_pic"] * facteur
    long_debut = params["long_debut"] * facteur
    long_pic = params["long_pic"] * facteur

    allure_objectif = parser_allure(allure_objectif_texte)
    allures = _allures_semaine(allure_objectif)

    jours = JOURS_DISPONIBLES.get(jours_par_semaine, JOURS_DISPONIBLES[4])
    semaines_affutage = max(2, round(nb_semaines * 0.15))

    semaines = []
    for indice in range(1, nb_semaines + 1):
        phase = _phase_semaine(indice, nb_semaines, semaines_affutage)
        recuperation = _est_semaine_recuperation(indice, phase)
        volume = _volume_semaine(indice, nb_semaines, volume_debut, volume_pic, phase, semaines_affutage)
        longue = _distance_longue_semaine(indice, nb_semaines, long_debut, long_pic, phase, semaines_affutage)

        seances_semaine = _construire_semaine(jours, volume, longue, phase, recuperation, allures, indice)

        semaines.append({
            "indice": indice,
            "phase": phase,
            "recuperation": recuperation,
            "volume_km": volume,
            "seances": seances_semaine,
        })

    return semaines


def date_seance(date_debut, indice_semaine, jour_offset):
    """date_debut : date du lundi de la semaine 1 du plan."""
    return date_debut + timedelta(weeks=indice_semaine - 1, days=jour_offset)
