"""
Estimation de la puissance de course à pied, inspirée de la méthode
GOVSS (Gravity Ordered Velocity Stress Score, Skiba 2006), elle-même
basée sur le coût métabolique de la course en fonction de la pente
(équation de Minetti et al., 2002).

Deux limites importantes à connaître :

1. La trace GPS stockée ne contient que latitude/longitude/altitude
   par point, pas d'horodatage individuel. On ne peut donc pas
   connaître la vitesse réelle à chaque instant — on utilise la
   vitesse MOYENNE de toute la sortie, appliquée à chaque segment. Le
   coût énergétique, lui, est calculé séparément pour chaque segment à
   partir de sa vraie pente (ça ne nécessite pas de temps par point).
   C'est donc une estimation moyenne de la puissance sur l'ensemble de
   la sortie, pas une courbe de puissance instantanée.

2. L'équation de Minetti donne un coût MÉTABOLIQUE (équivalent à la
   consommation d'oxygène), pas la puissance mécanique qu'affichent
   les montres/capteurs du commerce (Stryd et assimilés). Le corps
   humain n'est efficace qu'à environ 25 % pour convertir cette
   énergie métabolique en mouvement — on applique donc ce rendement
   pour obtenir un chiffre du même ordre de grandeur que ces appareils.
   Sans ce facteur, l'estimation affiche des valeurs 3 à 4 fois trop
   élevées (une sortie tranquille ressortirait à 600-700 W, ce qui
   correspond à l'effort d'un cycliste professionnel, pas d'un
   coureur récréatif).
"""

from interface.gpx_utils import _distance_haversine_km


RENDEMENT_COURSE = 0.25


def _cout_course_minetti(pente_fraction):
    """Coût énergétique de la course (J/kg/m) en fonction de la pente
    (fraction, ex. 0.10 pour +10 %). Modèle valide entre -45 % et +45 %."""

    i = max(-0.45, min(0.45, pente_fraction))
    return (
        155.4 * i**5 - 30.4 * i**4 - 43.3 * i**3
        + 46.3 * i**2 + 19.5 * i + 3.6
    )


def calculer_puissance_estimee(points, distance_totale_km, duree_totale_s, poids_kg=None):
    """Retourne la puissance moyenne estimée (W/kg, et en Watts si le
    poids de l'athlète est connu) pour une sortie, à partir de sa trace
    et de sa distance/durée réelles (issues de l'activité liée)."""

    if len(points) < 2 or not duree_totale_s or duree_totale_s <= 0 or not distance_totale_km:
        return None

    vitesse_moyenne_m_s = (distance_totale_km * 1000) / duree_totale_s

    cout_pondere_total = 0.0
    distance_totale_m = 0.0

    for i in range(1, len(points)):
        lat1, lon1, alt1 = points[i - 1][0], points[i - 1][1], points[i - 1][2]
        lat2, lon2, alt2 = points[i][0], points[i][1], points[i][2]
        d_m = _distance_haversine_km(lat1, lon1, lat2, lon2) * 1000
        if d_m <= 0:
            continue

        pente = (alt2 - alt1) / d_m
        cout = _cout_course_minetti(pente)

        cout_pondere_total += cout * d_m
        distance_totale_m += d_m

    if distance_totale_m == 0:
        return None

    cout_moyen_j_kg_m = cout_pondere_total / distance_totale_m
    puissance_metabolique_w_kg = cout_moyen_j_kg_m * vitesse_moyenne_m_s
    puissance_w_kg = puissance_metabolique_w_kg * RENDEMENT_COURSE

    resultat = {"puissance_w_par_kg": round(puissance_w_kg, 2)}
    if poids_kg:
        resultat["puissance_watts"] = round(puissance_w_kg * poids_kg)

    return resultat
