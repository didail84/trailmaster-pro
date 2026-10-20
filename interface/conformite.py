"""
Comparaison entre une séance structurée prévue (une liste d'étapes :
échauffement, effort, récupération...) et l'activité réellement
réalisée, pour en tirer un score de conformité.

Chaque étape est un dict :
    {
        "type": "Échauffement" | "Effort" | "Récupération" | "Retour au calme",
        "mode": "duree" | "distance",
        "valeur": float,               # minutes si mode="duree", km si mode="distance"
        "allure_cible": "5:30" | None,  # min:sec par km
        "fc_cible": int | None,
    }

Le score compare le volume total prévu (distance et/ou durée, selon ce
qui est déterminable) au volume réellement réalisé. Il ne vérifie pas
le respect de la structure interne (durée exacte de chaque répétition)
— cela demanderait un alignement précis dans le temps de l'activité
réalisée avec le plan, ce que les données actuelles ne permettent pas
de façon fiable.
"""


def parser_allure(texte):
    """Convertit "5:30" (min:sec par km) en minutes par km (5.5).
    Retourne None si le texte est vide ou mal formé."""

    if not texte:
        return None
    texte = texte.strip()
    if ":" not in texte:
        try:
            return float(texte.replace(",", "."))
        except ValueError:
            return None
    try:
        minutes, secondes = texte.split(":")
        return int(minutes) + int(secondes) / 60
    except (ValueError, IndexError):
        return None


def _distance_etape_km(etape):
    if etape["mode"] == "distance":
        return etape["valeur"]
    allure = parser_allure(etape.get("allure_cible"))
    if allure and allure > 0:
        return etape["valeur"] / allure
    return None


def _duree_etape_min(etape):
    if etape["mode"] == "duree":
        return etape["valeur"]
    allure = parser_allure(etape.get("allure_cible"))
    if allure and allure > 0:
        return etape["valeur"] * allure
    return None


def distance_totale_prevue_km(etapes):
    valeurs = [_distance_etape_km(e) for e in etapes]
    valeurs = [v for v in valeurs if v is not None]
    return round(sum(valeurs), 2) if valeurs else None


def duree_totale_prevue_min(etapes):
    valeurs = [_duree_etape_min(e) for e in etapes]
    valeurs = [v for v in valeurs if v is not None]
    return round(sum(valeurs), 1) if valeurs else None


def calculer_score_conformite(etapes, distance_realisee_km, duree_realisee_min):
    """Retourne un dict {score, distance_prevue, duree_prevue,
    interpretation} ou None si rien n'est comparable (aucune étape ne
    permet de déduire une distance ou une durée totale prévue)."""

    distance_prevue = distance_totale_prevue_km(etapes)
    duree_prevue = duree_totale_prevue_min(etapes)

    ecarts = []
    if distance_prevue and distance_realisee_km:
        ecarts.append(abs(distance_realisee_km - distance_prevue) / distance_prevue)
    if duree_prevue and duree_realisee_min:
        ecarts.append(abs(duree_realisee_min - duree_prevue) / duree_prevue)

    if not ecarts:
        return None

    ecart_moyen = sum(ecarts) / len(ecarts)
    score = round(max(0, 100 - ecart_moyen * 150))

    if score >= 90:
        interpretation = "Séance respectée"
    elif score >= 60:
        interpretation = "Séance partiellement respectée"
    else:
        interpretation = "Séance très différente du plan"

    return {
        "score": score,
        "distance_prevue": distance_prevue,
        "duree_prevue": duree_prevue,
        "interpretation": interpretation,
    }
