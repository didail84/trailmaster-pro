"""
Estimation du VO2max à partir d'une performance de course, avec la
formule de Daniels & Gilbert (la même base que les tables VDOT connues
des coureurs) :

    vitesse (m/min) = distance_m / durée_min
    VO2 = -4.60 + 0.182258 × vitesse + 0.000104 × vitesse²
    %VO2max = 0.8 + 0.1894393×e^(-0.012778×t) + 0.2989558×e^(-0.1932605×t)
    VO2max = VO2 / %VO2max

À utiliser sur un effort proche du maximal (une course, pas une sortie
tranquille) : sur une sortie facile, la formule sous-estime largement
le VO2max réel puisqu'elle suppose un effort quasi maximal.
"""

import math


def _vo2_daniels_gilbert(vitesse_m_min):
    return -4.60 + 0.182258 * vitesse_m_min + 0.000104 * vitesse_m_min ** 2


def _pourcentage_vo2max(duree_min):
    return (
        0.8
        + 0.1894393 * math.exp(-0.012778 * duree_min)
        + 0.2989558 * math.exp(-0.1932605 * duree_min)
    )


def estimer_vo2max(distance_km, duree_s):
    """Retourne le VO2max estimé (ml/kg/min) pour une performance donnée,
    ou None si les données sont insuffisantes."""

    if not distance_km or not duree_s or duree_s <= 0:
        return None

    duree_min = duree_s / 60
    vitesse_m_min = (distance_km * 1000) / duree_min

    vo2 = _vo2_daniels_gilbert(vitesse_m_min)
    pourcentage = _pourcentage_vo2max(duree_min)

    if pourcentage <= 0:
        return None

    return round(vo2 / pourcentage, 1)


def estimer_vo2max_recent(athlete_id, jours=180):
    """VO2max estimé à partir du meilleur effort Trail/Course (≥3 km) des
    `jours` derniers jours seulement — contrairement à
    estimer_vo2max_depuis_records (record absolu, qui peut dater de
    plusieurs années), ce chiffre reflète la forme récente/actuelle de
    l'athlète. Retourne {"vo2max":, "date":} ou None si pas assez de
    données récentes."""

    from datetime import date, timedelta
    from data.database import connexion

    date_min = (date.today() - timedelta(days=jours)).isoformat()

    conn = connexion()
    cur = conn.cursor()
    cur.execute(
        "SELECT date, distance, duree, vo2max FROM activites "
        "WHERE athlete_id=? AND type IN ('Trail','Course') AND distance >= 3 "
        "AND duree > 0 AND date >= ?",
        (athlete_id, date_min),
    )
    lignes = cur.fetchall()
    conn.close()

    meilleur = None
    for date_, distance, duree, vo2max_mesure in lignes:
        valeur = vo2max_mesure if vo2max_mesure else estimer_vo2max(distance, duree)
        if valeur and (meilleur is None or valeur > meilleur[0]):
            meilleur = (valeur, date_)

    if not meilleur:
        return None
    return {"vo2max": round(meilleur[0], 1), "date": meilleur[1]}


def estimer_vo2max_depuis_records(records, distances_reference):
    """À partir du dict de records (voir interface/records.py), calcule
    le VO2max estimé pour chaque distance connue et retourne aussi le
    meilleur (le plus élevé, généralement le plus représentatif du
    plafond physiologique de l'athlète)."""

    estimations = {}
    for label, _ in distances_reference:
        record = records.get(label)
        if not record:
            estimations[label] = None
            continue
        valeur = estimer_vo2max(record["distance_reelle"], record["duree_s"])
        estimations[label] = {
            "vo2max": valeur,
            "date": record["date"],
        } if valeur else None

    valides = [(label, e) for label, e in estimations.items() if e]
    meilleur = max(valides, key=lambda x: x[1]["vo2max"]) if valides else None

    return {
        "par_distance": estimations,
        "meilleur_label": meilleur[0] if meilleur else None,
        "meilleur_vo2max": meilleur[1]["vo2max"] if meilleur else None,
        "meilleur_date": meilleur[1]["date"] if meilleur else None,
    }
