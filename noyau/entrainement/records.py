"""
Records personnels et prédiction de temps de course.

Records : pour chaque distance de référence (5 km, 10 km, semi,
marathon), on retient la meilleure performance parmi les activités
Trail/Course dont la distance réelle est proche de cette référence
(tolérance -3 % / +20 %, une course étant rarement plus courte que sa
distance officielle mais souvent un peu plus longue en trace GPS).
Le temps affiché est celui réellement enregistré, pas une valeur
recalculée — plus honnête qu'une extrapolation qui ferait croire à une
précision qu'on n'a pas.

Prédiction : formule de Riegel (T2 = T1 × (D2/D1)^1.06), un standard
simple et largement utilisé en course à pied. Quand plusieurs records
sont connus, la prédiction pour une distance est la moyenne des
estimations obtenues à partir de chacun des autres records connus,
plutôt que de se fier à un seul record de référence.
"""

from data.database import connexion


DISTANCES_REFERENCE = [
    ("5 km", 5.0),
    ("10 km", 10.0),
    ("Semi-marathon", 21.1),
    ("Marathon", 42.2),
]

EXPOSANT_RIEGEL = 1.06


def _formater_duree(secondes):
    if not secondes:
        return "—"
    secondes = int(secondes)
    h, reste = divmod(secondes, 3600)
    m, s = divmod(reste, 60)
    if h > 0:
        return f"{h}h{m:02d}min{s:02d}"
    return f"{m}min{s:02d}"


def calculer_records(athlete_id):
    """Retourne un dict {label: infos} pour chaque distance de
    référence, plus deux records bonus (plus longue sortie, plus gros
    dénivelé) tous types éligibles confondus."""

    conn = connexion()
    cur = conn.cursor()
    cur.execute(
        "SELECT date, type, distance, duree FROM activites "
        "WHERE athlete_id=? AND type IN ('Trail','Course') AND duree > 0 AND distance > 0",
        (athlete_id,),
    )
    activites_course = cur.fetchall()
    conn.close()

    records = {}
    for label, distance_reference in DISTANCES_REFERENCE:
        candidats = [
            a for a in activites_course
            if distance_reference * 0.97 <= a[2] <= distance_reference * 1.10
        ]
        if not candidats:
            records[label] = None
            continue

        meilleur = min(candidats, key=lambda a: a[3])
        date, type_, distance, duree = meilleur
        allure = (duree / 60) / distance

        records[label] = {
            "distance_reference": distance_reference,
            "distance_reelle": round(distance, 2),
            "duree_s": duree,
            "duree_texte": _formater_duree(duree),
            "date": date,
            "type": type_,
            "allure_min_km": round(allure, 2),
        }

    conn = connexion()
    cur = conn.cursor()
    cur.execute(
        "SELECT date, type, distance, denivele FROM activites "
        "WHERE athlete_id=? AND type IN ('Trail','VTT','Randonnée','Course','Vélo')",
        (athlete_id,),
    )
    toutes_activites = cur.fetchall()
    conn.close()

    if toutes_activites:
        plus_longue = max(toutes_activites, key=lambda a: a[2] or 0)
        plus_denivele = max(toutes_activites, key=lambda a: a[3] or 0)

        records["Plus longue sortie"] = {
            "distance_reelle": round(plus_longue[2] or 0, 2),
            "date": plus_longue[0],
            "type": plus_longue[1],
        }
        records["Plus gros dénivelé"] = {
            "denivele": round(plus_denivele[3] or 0),
            "distance_reelle": round(plus_denivele[2] or 0, 2),
            "date": plus_denivele[0],
            "type": plus_denivele[1],
        }

    return records


def calculer_predictions(records):
    """À partir des records connus (5/10/semi/marathon), retourne une
    prédiction de temps pour chaque distance de référence — moyenne des
    estimations de Riegel calculées depuis chacun des autres records
    connus. None si aucun record n'est disponible pour l'estimer."""

    connues = [
        (distance_reference, records[label]["duree_s"])
        for label, distance_reference in DISTANCES_REFERENCE
        if records.get(label)
    ]

    predictions = {}
    for label, distance_reference in DISTANCES_REFERENCE:
        estimations = []
        for distance_connue, duree_connue in connues:
            if distance_connue == distance_reference:
                continue
            estimations.append(
                duree_connue * (distance_reference / distance_connue) ** EXPOSANT_RIEGEL
            )

        if estimations:
            duree_predite = sum(estimations) / len(estimations)
            predictions[label] = {
                "duree_s": round(duree_predite),
                "duree_texte": _formater_duree(duree_predite),
                "a_partir_de": len(estimations),
            }
        else:
            predictions[label] = None

    return predictions
