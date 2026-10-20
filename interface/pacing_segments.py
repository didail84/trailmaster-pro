"""
Pacing segmenté ("PacePro maison") — découpe un tracé GPX/FIT déjà
importé en segments de longueur fixe, calcule le profil (D+/D-, pente
moyenne) de chacun, puis en déduit une allure cible par segment à
partir d'une allure de référence (allure "plat") et d'un ajustement
simple selon la pente.

Ajustement de pente : approximation linéaire inspirée des travaux de
Minetti sur le coût énergétique de la course en pente — pas un calcul
physiologique individualisé, mais une règle simple et documentée :
+12 s/km par tranche de 1% de pente en montée, -6 s/km par tranche de
1% de pente en descente (la descente ralentit moins qu'elle n'accélère,
au-delà d'une certaine pente elle redevient même plus lente à cause du
freinage — non modélisé ici, cas rare en usage courant).

100% local, aucune dépendance réseau.
"""

from interface.gpx_utils import _distance_haversine_km


SECONDES_PAR_POURCENT_MONTEE = 12
SECONDES_PAR_POURCENT_DESCENTE = 6


def decouper_par_segments(points, longueur_segment_km=1.0):
    """points : liste de tuples (lat, lon, altitude, ...) comme
    retournés par gpx_utils.parser_gpx / fit_utils.parser_fit.

    Retourne une liste de segments {distance_km, denivele_positif,
    denivele_negatif, pente_moyenne_pct}."""

    if len(points) < 2:
        return []

    segments = []
    distance_cumulee = 0.0
    denivele_pos = 0.0
    denivele_neg = 0.0
    distance_segment = 0.0
    SEUIL_BRUIT_M = 0.5

    for i in range(1, len(points)):
        lat1, lon1, alt1 = points[i - 1][0], points[i - 1][1], points[i - 1][2]
        lat2, lon2, alt2 = points[i][0], points[i][1], points[i][2]

        d = _distance_haversine_km(lat1, lon1, lat2, lon2)
        distance_cumulee += d
        distance_segment += d

        diff_alt = alt2 - alt1
        if diff_alt > SEUIL_BRUIT_M:
            denivele_pos += diff_alt
        elif diff_alt < -SEUIL_BRUIT_M:
            denivele_neg += abs(diff_alt)

        if distance_segment >= longueur_segment_km:
            pente = ((denivele_pos - denivele_neg) / (distance_segment * 1000)) * 100 if distance_segment > 0 else 0
            segments.append({
                "distance_km": round(distance_segment, 2),
                "denivele_positif": round(denivele_pos),
                "denivele_negatif": round(denivele_neg),
                "pente_moyenne_pct": round(pente, 1),
            })
            distance_segment = 0.0
            denivele_pos = 0.0
            denivele_neg = 0.0

    # Dernier segment partiel (plus court que longueur_segment_km)
    if distance_segment > 0.05:
        pente = ((denivele_pos - denivele_neg) / (distance_segment * 1000)) * 100 if distance_segment > 0 else 0
        segments.append({
            "distance_km": round(distance_segment, 2),
            "denivele_positif": round(denivele_pos),
            "denivele_negatif": round(denivele_neg),
            "pente_moyenne_pct": round(pente, 1),
        })

    return segments


def _formater_allure(allure_min_km):
    minutes = int(allure_min_km)
    secondes = round((allure_min_km - minutes) * 60)
    if secondes == 60:
        minutes += 1
        secondes = 0
    return f"{minutes}:{secondes:02d}"


def calculer_pacing(segments, allure_plat_min_km):
    """Ajoute à chaque segment une allure cible et un temps cible,
    puis retourne (segments_avec_pacing, temps_total_texte)."""

    resultat = []
    temps_cumule_s = 0.0

    for seg in segments:
        pente = seg["pente_moyenne_pct"]
        ajustement_s_km = (
            pente * SECONDES_PAR_POURCENT_MONTEE if pente > 0
            else pente * SECONDES_PAR_POURCENT_DESCENTE  # pente négative -> ajustement négatif
        )
        allure_cible = max(allure_plat_min_km + ajustement_s_km / 60, allure_plat_min_km * 0.5)
        temps_segment_s = allure_cible * seg["distance_km"] * 60
        temps_cumule_s += temps_segment_s

        resultat.append({
            **seg,
            "allure_cible_min_km": round(allure_cible, 2),
            "allure_cible_texte": _formater_allure(allure_cible),
            "temps_segment_s": round(temps_segment_s),
            "temps_cumule_s": round(temps_cumule_s),
        })

    h, reste = divmod(int(temps_cumule_s), 3600)
    m = reste // 60
    temps_total_texte = f"{h}h{m:02d}" if h else f"{m}min"

    return resultat, temps_total_texte
