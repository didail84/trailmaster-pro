"""
Meilleurs efforts par durée et vitesse critique (v104), calculés sur les traces.
Les vitesses sont « à plat équivalent » (pente corrigée par le modèle de Minetti) :
un effort en côte et un effort à plat deviennent comparables.

Vitesse critique (CS) : droite distance = CS × durée + D′ ajustée sur les meilleurs
efforts de 3 à 30 min. CS ≈ vitesse soutenable ~30–40 min (proche du seuil), D′ =
réserve au-dessus. ESTIMATION BASSE : tes sorties ne sont pas des efforts maximaux.
"""

from datetime import date, timedelta

import data.metriques as met
from data.analyse_traces import profil, facteur_pente, PAS_M

DUREES_S = (60, 180, 300, 600, 1200, 1800, 3600)
DUREES_CS = (180, 300, 600, 1200, 1800)


def _meilleurs_dans_trace(echant, durees):
    """{duree: distance plate équivalente max (m)} par fenêtre glissante sur le temps."""
    pts = [(e["t"], e["d"], e["pente"]) for e in echant if e.get("t") is not None]
    if len(pts) < 10:
        return {}
    t0 = [p[0] for p in pts]
    eq = [0.0]
    for i in range(1, len(pts)):
        dd = pts[i][1] - pts[i - 1][1]
        eq.append(eq[-1] + dd * facteur_pente(pts[i][2]))
    res = {}
    for D in durees:
        if t0[-1] - t0[0] < D:
            continue
        meilleur, j = 0.0, 0
        for i in range(len(pts)):
            while j + 1 < len(pts) and t0[j] - t0[i] < D:
                j += 1
            if t0[j] - t0[i] >= D * 0.98:
                meilleur = max(meilleur, eq[j] - eq[i])
        if meilleur > 0:
            res[D] = meilleur
    return res


def meilleurs_par_duree(athlete_id, jours=365, durees=DUREES_S):
    """[{duree_s, vitesse_kmh, distance_m, date, nom}] pour chaque durée atteinte."""
    debut = date.today() - timedelta(days=jours)
    meilleurs = {}
    for a in met.activites_periode(athlete_id, debut, None, types=("Trail", "Course")):
        pts = met.trace_de_activite(a["id"])
        if len(pts) < 20:
            continue
        for D, dist in _meilleurs_dans_trace(profil(pts), durees).items():
            if D not in meilleurs or dist > meilleurs[D]["distance_m"]:
                meilleurs[D] = {"duree_s": D, "distance_m": dist, "vitesse_kmh": dist / D * 3.6,
                                "date": str(a["date"])[:10], "nom": a.get("nom") or ""}
    return [meilleurs[D] for D in sorted(meilleurs)]


def vitesse_critique(efforts):
    """efforts : liste de {duree_s, distance_m}. Régression d = CS·t + D′ sur 3–30 min.
    Retourne {cs_kmh, d_prime_m, r2, nb} ou None."""
    pts = [(e["duree_s"], e["distance_m"]) for e in efforts if e["duree_s"] in DUREES_CS]
    if len(pts) < 3:
        return None
    n = len(pts)
    mx = sum(p[0] for p in pts) / n
    my = sum(p[1] for p in pts) / n
    sxx = sum((p[0] - mx) ** 2 for p in pts)
    if sxx == 0:
        return None
    cs = sum((p[0] - mx) * (p[1] - my) for p in pts) / sxx
    dp = my - cs * mx
    ss_tot = sum((p[1] - my) ** 2 for p in pts)
    ss_res = sum((p[1] - (cs * p[0] + dp)) ** 2 for p in pts)
    r2 = 1 - ss_res / ss_tot if ss_tot else 0
    if cs <= 0 or dp < 0 or r2 < 0.98:
        return None
    return {"cs_kmh": round(cs * 3.6, 2), "d_prime_m": round(dp), "r2": round(r2, 4), "nb": n}
