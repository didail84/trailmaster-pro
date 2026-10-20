"""
Analyse de la dynamique de course à partir du flux détaillé de la
trace (temps, fréquence cardiaque et cadence par point, quand
disponibles).

Nécessite des points au format enrichi (lat, lon, alt, temps_relatif_s,
fc[, cadence]) — c'est-à-dire une trace dont l'import a capturé ces
champs. Les traces plus anciennes ou issues de sources qui n'exposent
pas la FC par point (beaucoup de GPX Runtastic/Geonaute 2012-2015,
notamment) n'ont pas cette donnée : dans ce cas, les fonctions
retournent None plutôt que d'inventer un chiffre.
"""

from interface.gpx_utils import _distance_haversine_km


DUREE_MINIMUM_DECOUPLAGE_S = 20 * 60  # sous ce seuil, la mesure n'est pas fiable
ECART_TEMPS_MAX_SEGMENT_S = 30        # au-delà, on suppose une pause/coupure GPS
DECOUPLAGE_MAX_PLAUSIBLE_PCT = 50     # au-delà, le résultat est jugé aberrant


def _points_avec_fc_et_temps(points):
    valides = [
        p for p in points
        if len(p) >= 5 and p[3] is not None and p[4]
    ]
    valides.sort(key=lambda p: p[3])
    return valides


def _stats_segment(sous_liste):
    """Vitesse moyenne (m/s) et FC moyenne sur une portion de trace,
    calculées à partir des distances/temps réels entre points. Les
    segments séparés par plus de ECART_TEMPS_MAX_SEGMENT_S (pause,
    coupure GPS, arrêt à un ravitaillement...) sont ignorés : sinon un
    seul arrêt prolongé fait chuter artificiellement la vitesse
    moyenne calculée sur toute la portion."""

    distance_m = 0.0
    duree_s = 0.0
    fc_valeurs = []

    for i in range(1, len(sous_liste)):
        p1, p2 = sous_liste[i - 1], sous_liste[i]
        dt = p2[3] - p1[3]
        if dt <= 0 or dt > ECART_TEMPS_MAX_SEGMENT_S:
            continue
        d = _distance_haversine_km(p1[0], p1[1], p2[0], p2[1]) * 1000
        distance_m += d
        duree_s += dt
        fc_valeurs.append(p2[4])

    if duree_s <= 0 or not fc_valeurs:
        return None

    return distance_m / duree_s, sum(fc_valeurs) / len(fc_valeurs)


def _interpreter_decouplage(pct):
    if pct <= 5:
        return "Bonne endurance aérobie : FC restée stable sur la sortie."
    if pct <= 10:
        return "Dérive normale, rien d'alarmant."
    return "Dérive cardiaque marquée (fatigue, chaleur, ou base aérobie à renforcer)."


def calculer_decouplage_cardiaque(points):
    """Compare le facteur d'efficacité (vitesse/FC) entre la première
    et la seconde moitié (découpage par le temps réel) de la sortie.
    Retourne None si la trace n'a pas de FC par point ou est trop
    courte pour que la mesure soit significative."""

    points_valides = _points_avec_fc_et_temps(points)
    if len(points_valides) < 20:
        return None

    duree_totale = points_valides[-1][3]
    if duree_totale < DUREE_MINIMUM_DECOUPLAGE_S:
        return None

    milieu = duree_totale / 2
    premiere = [p for p in points_valides if p[3] <= milieu]
    seconde = [p for p in points_valides if p[3] > milieu]

    stats1 = _stats_segment(premiere)
    stats2 = _stats_segment(seconde)
    if not stats1 or not stats2:
        return None

    vitesse1, fc1 = stats1
    vitesse2, fc2 = stats2
    if fc1 <= 0 or fc2 <= 0 or vitesse1 <= 0:
        return None

    ef1 = vitesse1 / fc1
    ef2 = vitesse2 / fc2
    decouplage_pct = round(((ef1 - ef2) / ef1) * 100, 1)

    if abs(decouplage_pct) > DECOUPLAGE_MAX_PLAUSIBLE_PCT:
        # Résultat hors de toute plage physiologiquement plausible :
        # presque certainement un artefact (pause non filtrée, signal
        # GPS/FC de mauvaise qualité...) plutôt qu'une vraie dérive.
        return None

    return {
        "decouplage_pct": decouplage_pct,
        "vitesse_premiere_kmh": round(vitesse1 * 3.6, 2),
        "vitesse_seconde_kmh": round(vitesse2 * 3.6, 2),
        "fc_premiere": round(fc1),
        "fc_seconde": round(fc2),
        "interpretation": _interpreter_decouplage(decouplage_pct),
    }


def calculer_cadence_moyenne(points):
    """Retourne la cadence moyenne (pas/min) si l'information est
    présente dans la trace, sinon None. Beaucoup d'appareils Garmin
    comptent la cadence sur un seul pied (~75-95) : on la double
    automatiquement si la valeur semble être dans cette plage plutôt
    que déjà en pas/minute total (~150-190)."""

    cadences = [p[5] for p in points if len(p) > 5 and p[5]]
    if not cadences:
        return None

    moyenne = sum(cadences) / len(cadences)
    doublee = moyenne < 120

    return {
        "cadence_spm": round(moyenne * 2) if doublee else round(moyenne),
        "doublee": doublee,
    }
