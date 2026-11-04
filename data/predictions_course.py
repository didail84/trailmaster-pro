"""
Prédiction de chrono (v103) à partir du VO₂max estimé, par la formule de
Daniels-Gilbert inversée. Le dénivelé est converti en distance à plat
(125 m de D+ ≈ 1 km, même convention que la VMA).

C'est une ESTIMATION BASSE : le VO₂max vient de sorties réelles, rarement des
efforts maximaux, donc les chronos prédits sont plutôt pessimistes. Au-delà du
semi, l'endurance (volume, ravitaillement) compte autant que le moteur : on
l'indique plutôt que de promettre un chrono exact.
"""

from interface.vo2max import estimer_vo2max

DISTANCES = [("5 km", 5.0), ("10 km", 10.0), ("Semi-marathon", 21.0975), ("Marathon", 42.195)]


def duree_pour_vo2(vo2, distance_eq_km):
    """Durée (s) pour laquelle estimer_vo2max(distance, durée) = vo2 (dichotomie)."""
    if not vo2 or vo2 <= 0 or distance_eq_km <= 0:
        return None
    bas, haut = distance_eq_km * 150.0, distance_eq_km * 900.0   # 2:30 à 15:00 /km
    if estimer_vo2max(distance_eq_km, bas) < vo2:
        return None            # plus vite que le plausible
    if estimer_vo2max(distance_eq_km, haut) > vo2:
        return None
    for _ in range(60):
        mil = (bas + haut) / 2
        # même distance : plus on est lent, plus le VO2max estimé est bas
        if estimer_vo2max(distance_eq_km, mil) > vo2:
            bas = mil
        else:
            haut = mil
    return round((bas + haut) / 2)


def predire(vo2max, distance_km, denivele_m=0):
    """Durée prédite en secondes (distance à plat équivalente), ou None."""
    d_eq = distance_km + max(denivele_m or 0, 0) / 125.0
    return duree_pour_vo2(vo2max, d_eq)


def texte_duree(sec):
    if sec is None:
        return "—"
    h, r = divmod(int(sec), 3600)
    m, s = divmod(r, 60)
    return f"{h}h{m:02d}'{s:02d}" if h else f"{m}'{s:02d}"


def table_predictions(vo2max):
    lignes = []
    for nom, km in DISTANCES:
        t = predire(vo2max, km)
        lignes.append({"nom": nom, "km": km, "duree_s": t, "duree": texte_duree(t),
                       "allure": (f"{int(t / km // 60)}:{int(round(t / km % 60)):02d} /km"
                                  if t else "—")})
    return lignes


def vo2max_de_reference(athlete_id):
    """VO₂max estimé le plus récent (série « estimation basse »), ou None."""
    from interface.estimations_basses import serie_estimations
    s = serie_estimations(athlete_id)
    if not s or not s["vo2max"]:
        return None
    return s["vo2max"][-1][1]
