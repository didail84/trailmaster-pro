"""
Comparaison allure/FC cible vs réalisé pour une séance liée à une
activité (utile en particulier pour les "Course de préparation" du
programme Ultra, qui portent une cible précise — voir
interface/generateur_ultra.py). L'écart est conservé dans
comparaisons_courses pour objectiver, au fil des mois, si les
prédictions Riegel utilisées par le logiciel sont optimistes ou
pessimistes par rapport à la réalité de cet athlète.

100% local, aucun appel réseau.
"""

import json

from data.database import connexion
from interface.conformite import parser_allure


def _allure_cible_moyenne(etapes):
    """Moyenne des allures cibles des étapes d'"Effort" (ignore
    échauffement/récupération/retour au calme), pondérée par leur
    distance prévue — repli sur toutes les étapes si aucune n'est
    taguée "Effort"."""

    efforts = [e for e in etapes if e.get("type") == "Effort" and e.get("allure_cible")]
    source = efforts or [e for e in etapes if e.get("allure_cible")]
    if not source:
        return None

    total_poids = 0.0
    total = 0.0
    for e in source:
        allure = parser_allure(e["allure_cible"])
        if allure is None:
            continue
        poids = e.get("valeur", 1) if e.get("mode") == "distance" else 1
        total += allure * poids
        total_poids += poids

    return round(total / total_poids, 2) if total_poids > 0 else None


def _fc_cible_moyenne(etapes):
    valeurs = [e["fc_cible"] for e in etapes if e.get("fc_cible")]
    return round(sum(valeurs) / len(valeurs)) if valeurs else None


def comparer_seance_realisee(seance_id):
    """Retourne un dict {allure_cible, allure_reelle, ecart_allure_pct,
    fc_cible, fc_reelle, texte} ou None si la séance n'a pas de cible
    exploitable ou pas d'activité liée."""

    conn = connexion()
    cur = conn.cursor()
    cur.execute(
        "SELECT s.athlete_id, s.etapes_json, s.activite_id, "
        "a.distance, a.duree, a.frequence_cardiaque_moyenne "
        "FROM seances_structurees s LEFT JOIN activites a ON s.activite_id = a.id "
        "WHERE s.id=?",
        (seance_id,),
    )
    ligne = cur.fetchone()
    conn.close()

    if not ligne:
        return None
    athlete_id, etapes_json, activite_id, distance, duree, fc_moyenne = ligne
    if activite_id is None:
        return None

    etapes = json.loads(etapes_json) if etapes_json else []
    allure_cible = _allure_cible_moyenne(etapes)
    fc_cible = _fc_cible_moyenne(etapes)

    allure_reelle = None
    if distance and duree:
        allure_reelle = round((duree / 60) / distance, 2)

    if allure_cible is None and fc_cible is None:
        return None

    ecart_allure_pct = None
    if allure_cible and allure_reelle:
        ecart_allure_pct = round((allure_reelle - allure_cible) / allure_cible * 100, 1)

    morceaux = []
    if allure_cible and allure_reelle:
        sens = "plus lent" if ecart_allure_pct > 0 else "plus rapide"
        morceaux.append(
            f"Allure cible {allure_cible:.2f} min/km, réalisée {allure_reelle:.2f} min/km "
            f"({abs(ecart_allure_pct)}% {sens} que la cible)"
        )
    if fc_cible and fc_moyenne:
        morceaux.append(f"FC cible ≈{fc_cible} bpm, réalisée {fc_moyenne} bpm")
    texte = " · ".join(morceaux) if morceaux else "Pas assez de données pour comparer."

    return {
        "athlete_id": athlete_id,
        "seance_id": seance_id,
        "activite_id": activite_id,
        "allure_cible": allure_cible,
        "allure_reelle": allure_reelle,
        "ecart_allure_pct": ecart_allure_pct,
        "fc_cible": fc_cible,
        "fc_reelle": fc_moyenne,
        "texte": texte,
    }


def enregistrer_comparaison(comparaison):
    conn = connexion()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO comparaisons_courses (
            athlete_id, seance_id, activite_id, allure_cible, allure_reelle,
            ecart_allure_pct, fc_cible, fc_reelle
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            comparaison["athlete_id"], comparaison["seance_id"], comparaison["activite_id"],
            comparaison["allure_cible"], comparaison["allure_reelle"],
            comparaison["ecart_allure_pct"], comparaison["fc_cible"], comparaison["fc_reelle"],
        ),
    )
    conn.commit()
    conn.close()


def tendance_ecart_allure(athlete_id, nb_dernieres=10):
    """Moyenne des derniers écarts d'allure (%) enregistrés pour cet
    athlète — un écart moyen positif et répété signifie que les
    prédictions Riegel du logiciel sont optimistes pour lui (il court
    ses courses de repère plus lentement que prévu), négatif qu'elles
    sont pessimistes. Sert d'indicateur de recalibrage, affiché tel
    quel plutôt qu'appliqué automatiquement (pas assez de données pour
    un recalage fiable sans supervision)."""

    conn = connexion()
    cur = conn.cursor()
    cur.execute(
        "SELECT ecart_allure_pct FROM comparaisons_courses "
        "WHERE athlete_id=? AND ecart_allure_pct IS NOT NULL "
        "ORDER BY date_generation DESC LIMIT ?",
        (athlete_id, nb_dernieres),
    )
    valeurs = [v for (v,) in cur.fetchall()]
    conn.close()

    if not valeurs:
        return None
    return round(sum(valeurs) / len(valeurs), 1)
