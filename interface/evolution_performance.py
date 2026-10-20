"""
Évolution mensuelle de plusieurs indicateurs de performance sur une
longue période (jusqu'à 2 ans) — même principe que le « Graphique
polyvalent » du tableau de bord, mais mois par mois plutôt que jour par
jour, pour visualiser une tendance de fond (amélioration, plateau,
déclin) plutôt que les à-coups quotidiens.

Le VO2max utilise une fenêtre glissante de 180 jours (le meilleur
effort proche du maximal sur les 6 derniers mois à chaque point), et
non le record absolu depuis toujours (voir interface/vo2max.py) — un
record vieux de deux ans fausse l'image de la forme actuelle, alors
qu'une fenêtre glissante suit la forme réelle au fil du temps.
"""

from datetime import date, timedelta

from data.database import connexion
from interface.vo2max import estimer_vo2max


FENETRE_VO2MAX_JOURS = 180

MESURES_EVOLUTION = {
    "vo2max": {
        "libelle": "VO2max estimé (ml/kg/min)",
        "note": (
            f"Meilleur effort Trail/Course (≥3 km) sur une fenêtre glissante de "
            f"{FENETRE_VO2MAX_JOURS} jours à chaque point — reflète la forme du "
            "moment plutôt qu'un record vieux de plusieurs années."
        ),
    },
    "fc_moyenne": {
        "libelle": "FC moyenne (bpm)",
        "note": "FC moyenne de toutes les sorties avec cardio, moyennée par mois.",
    },
    "allure_moyenne": {
        "libelle": "Allure moyenne (min/km)",
        "note": "Allure moyenne des sorties Trail/Course, moyennée par mois — plus bas = plus rapide.",
    },
    "denivele": {
        "libelle": "Dénivelé D+ cumulé (m)",
        "note": "D+ total grimpé dans le mois, tous types de sortie confondus.",
    },
    "distance": {
        "libelle": "Distance cumulée (km)",
        "note": "Distance totale parcourue dans le mois, tous types de sortie confondus.",
    },
    "duree": {
        "libelle": "Durée cumulée (h)",
        "note": "Temps d'entraînement total dans le mois, tous types de sortie confondus.",
    },
}


def _premier_jour_mois(annee, mois):
    return date(annee, mois, 1)


def _dernier_jour_mois(annee, mois):
    if mois == 12:
        return date(annee, 12, 31)
    return date(annee, mois + 1, 1) - timedelta(days=1)


def _mois_glissants(nb_mois):
    """Liste de (année, mois) du plus ancien au plus récent, nb_mois
    mois en arrière, mois courant inclus."""
    aujourd_hui = date.today()
    resultat = []
    annee, mois = aujourd_hui.year, aujourd_hui.month
    for _ in range(nb_mois):
        resultat.append((annee, mois))
        mois -= 1
        if mois < 1:
            mois = 12
            annee -= 1
    return list(reversed(resultat))


def _activites_athlete(athlete_id, date_min_iso):
    conn = connexion()
    cur = conn.cursor()
    cur.execute(
        "SELECT date, type, distance, denivele, duree, frequence_cardiaque_moyenne, "
        "allure_moyenne, vo2max FROM activites WHERE athlete_id=? AND date >= ?",
        (athlete_id, date_min_iso),
    )
    lignes = cur.fetchall()
    conn.close()
    return lignes


def serie_evolution_mensuelle(athlete_id, mesure, nb_mois=24):
    """Retourne [(label_mois, valeur_ou_None), ...], du plus ancien au
    plus récent, pour la mesure demandée (clé de MESURES_EVOLUTION)."""

    mois_liste = _mois_glissants(nb_mois)
    date_min = _premier_jour_mois(*mois_liste[0]) - timedelta(days=FENETRE_VO2MAX_JOURS)
    activites = _activites_athlete(athlete_id, date_min.isoformat())

    resultat = []
    derniere_valeur = None
    for annee, mois in mois_liste:
        label = f"{mois:02d}/{str(annee)[2:]}"
        debut_mois = _premier_jour_mois(annee, mois)
        fin_mois = _dernier_jour_mois(annee, mois)

        if mesure == "vo2max":
            debut_fenetre = fin_mois - timedelta(days=FENETRE_VO2MAX_JOURS)
            candidats = [
                a for a in activites
                if a[1] in ("Trail", "Course") and (a[2] or 0) >= 3 and (a[4] or 0) > 0
                and debut_fenetre.isoformat() <= str(a[0])[:10] <= fin_mois.isoformat()
            ]
            estimations = [
                a[7] if a[7] else estimer_vo2max(a[2], a[4])
                for a in candidats
            ]
            estimations = [v for v in estimations if v]
            valeur = round(max(estimations), 1) if estimations else None

        elif mesure == "fc_moyenne":
            valeurs = [
                a[5] for a in activites
                if a[5] and debut_mois.isoformat() <= str(a[0])[:10] <= fin_mois.isoformat()
            ]
            valeur = round(sum(valeurs) / len(valeurs)) if valeurs else None

        elif mesure == "allure_moyenne":
            # Bornes larges (2 à 20 min/km) pour écarter les valeurs
            # aberrantes issues d'un GPS en défaut ou d'une distance
            # quasi nulle enregistrée par erreur, sans fausser la
            # moyenne du mois.
            valeurs = [
                a[6] for a in activites
                if a[6] and 2 <= a[6] <= 20 and a[1] in ("Trail", "Course")
                and debut_mois.isoformat() <= str(a[0])[:10] <= fin_mois.isoformat()
            ]
            valeur = round(sum(valeurs) / len(valeurs), 2) if valeurs else None

        elif mesure == "denivele":
            valeurs = [
                a[3] or 0 for a in activites
                if debut_mois.isoformat() <= str(a[0])[:10] <= fin_mois.isoformat()
            ]
            valeur = round(sum(valeurs)) if valeurs else None

        elif mesure == "distance":
            valeurs = [
                a[2] or 0 for a in activites
                if debut_mois.isoformat() <= str(a[0])[:10] <= fin_mois.isoformat()
            ]
            valeur = round(sum(valeurs)) if valeurs else None

        elif mesure == "duree":
            valeurs = [
                a[4] or 0 for a in activites
                if debut_mois.isoformat() <= str(a[0])[:10] <= fin_mois.isoformat()
            ]
            valeur = round(sum(valeurs) / 3600, 1) if valeurs else None

        else:
            valeur = None

        resultat.append((label, valeur))

    # On ne garde pas les mois sans aucune donnée en tête de série (avant
    # la première sortie connue) ; dans la série, un mois isolé sans
    # donnée reprend la dernière valeur connue pour ne pas casser la
    # courbe (celle-ci n'affiche pas de « trou »).
    while resultat and resultat[0][1] is None:
        resultat.pop(0)

    resultat_rempli = []
    for label, valeur in resultat:
        if valeur is None:
            valeur = derniere_valeur
        else:
            derniere_valeur = valeur
        resultat_rempli.append((label, valeur))

    return resultat_rempli
