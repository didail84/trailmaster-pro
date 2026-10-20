"""
Estimation du temps de course pour une distance et un dénivelé donnés,
à partir des VRAIES sorties Trail/Course de l'athlète (pas de barème
générique) : régression sur les deux dernières années d'activités pour
apprendre son propre rythme (allure à plat + coût du dénivelé), avec un
ajustement si suffisamment de sorties existent dans la même saison que
la course visée (on court en général un peu plus vite/lentement en
hiver qu'en plein été, par exemple).

Modèle volontairement simple (régression linéaire à la main, sans
dépendance externe) : durée ≈ a·distance_km + b·dénivelé_m + c.
Avec 1255 activités disponibles mais seulement les sorties Trail/Course
des deux dernières années prises en compte, pour rester pertinent par
rapport à la forme actuelle de l'athlète plutôt que son niveau d'il y a
plusieurs années.
"""

from datetime import date, timedelta

from data.database import connexion


MOIS_VERS_SAISON = {
    12: "Hiver", 1: "Hiver", 2: "Hiver",
    3: "Printemps", 4: "Printemps", 5: "Printemps",
    6: "Été", 7: "Été", 8: "Été",
    9: "Automne", 10: "Automne", 11: "Automne",
}

NB_MINIMUM_SORTIES = 5
NB_MINIMUM_SORTIES_SAISON = 6


def _resoudre_systeme_3x3(matrice, vecteur):
    """Résolution d'un système linéaire 3x3 par élimination de Gauss —
    évite une dépendance externe (numpy) pour une régression à 3
    coefficients seulement."""

    a = [ligne[:] for ligne in matrice]
    b = vecteur[:]

    for i in range(3):
        pivot = a[i][i]
        if abs(pivot) < 1e-9:
            for k in range(i + 1, 3):
                if abs(a[k][i]) > 1e-9:
                    a[i], a[k] = a[k], a[i]
                    b[i], b[k] = b[k], b[i]
                    pivot = a[i][i]
                    break
            else:
                return None
        for k in range(3):
            if k != i:
                facteur = a[k][i] / pivot
                for j in range(3):
                    a[k][j] -= facteur * a[i][j]
                b[k] -= facteur * b[i]

    return [b[i] / a[i][i] if abs(a[i][i]) > 1e-9 else 0.0 for i in range(3)]


def _regression_duree(lignes):
    """lignes : liste de (distance_km, denivele_m, duree_s). Renvoie
    (a, b, c) pour duree ≈ a·distance + b·denivele + c, ou None si pas
    assez de données ou système dégénéré."""

    n = len(lignes)
    if n < NB_MINIMUM_SORTIES:
        return None

    sx = sy = sz = sxx = syy = sxy = sxz = syz = 0.0
    for distance, denivele, duree in lignes:
        sx += distance
        sy += denivele
        sz += duree
        sxx += distance * distance
        syy += denivele * denivele
        sxy += distance * denivele
        sxz += distance * duree
        syz += denivele * duree

    matrice = [
        [sxx, sxy, sx],
        [sxy, syy, sy],
        [sx, sy, n],
    ]
    vecteur = [sxz, syz, sz]

    return _resoudre_systeme_3x3(matrice, vecteur)


def _formater_duree(secondes):
    if secondes is None or secondes <= 0:
        return "—"
    secondes = int(round(secondes))
    heures, reste = divmod(secondes, 3600)
    minutes = reste // 60
    if heures > 0:
        return f"{heures} h {minutes:02d} min"
    return f"{minutes} min"


def estimer_temps_course(athlete_id, distance_km, denivele_m, date_course=None, annees=2):
    """Renvoie un dict {secondes, duree_formatee, nb_sorties, ajustement_saison}
    ou None si pas assez d'historique Trail/Course pour estimer quoi que
    ce soit de fiable."""

    if not distance_km or athlete_id is None:
        return None

    conn = connexion()
    cur = conn.cursor()
    limite = (date.today() - timedelta(days=365 * annees)).isoformat()
    cur.execute(
        """
        SELECT date, distance, denivele, duree FROM activites
        WHERE athlete_id=? AND type IN ('Trail', 'Course')
          AND date >= ? AND distance > 0.5 AND duree > 60
        """,
        (athlete_id, limite),
    )
    lignes = cur.fetchall()
    conn.close()

    donnees = [(d, n or 0, duree) for (_, d, n, duree) in lignes]
    coefficients = _regression_duree(donnees)
    if coefficients is None:
        return None

    distance_max_connue = max((d for d, _, _ in donnees), default=0)
    extrapolation = bool(distance_max_connue) and distance_km > 2.5 * distance_max_connue

    a, b, c = coefficients
    estimation_brute = a * distance_km + b * (denivele_m or 0) + c
    if estimation_brute <= 0:
        # Modèle dégénéré sur ce profil de sorties (ex. toutes très
        # courtes) — mieux vaut ne rien afficher qu'un temps absurde.
        return None

    ajustement_saison = False
    estimation_finale = estimation_brute

    if date_course:
        try:
            mois_cible = int(str(date_course)[5:7])
            saison_cible = MOIS_VERS_SAISON.get(mois_cible)
        except (ValueError, IndexError):
            saison_cible = None

        if saison_cible:
            sous_ensemble = [
                (dt, d, n or 0, duree) for (dt, d, n, duree) in lignes
                if MOIS_VERS_SAISON.get(int(str(dt)[5:7])) == saison_cible
            ]
            if len(sous_ensemble) >= NB_MINIMUM_SORTIES_SAISON:
                ratios = []
                for _, d, n, duree in sous_ensemble:
                    attendu = a * d + b * n + c
                    if attendu > 0:
                        ratios.append(duree / attendu)
                if ratios:
                    ratio_moyen = sum(ratios) / len(ratios)
                    ratio_moyen = max(0.85, min(1.20, ratio_moyen))
                    estimation_finale = estimation_brute * ratio_moyen
                    ajustement_saison = True

    return {
        "secondes": estimation_finale,
        "duree_formatee": _formater_duree(estimation_finale),
        "nb_sorties": len(donnees),
        "ajustement_saison": ajustement_saison,
        "extrapolation": extrapolation,
    }
