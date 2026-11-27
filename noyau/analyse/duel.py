"""
Duel sur un même parcours : deux passages sur la même boucle, comparés
portion par portion (temps, montée, descente, fréquence cardiaque).

Les traces viennent de parcours_gpx (trace liée à la sortie), points
(lat, lon, altitude, temps relatif en s, FC). Deux sorties sont « sur le
même parcours » quand elles partent à moins de 300 m l'une de l'autre,
arrivent à moins de 300 m, et que leurs distances diffèrent de moins de
12 %. La comparaison se fait à distance égale (chaque trace est découpée
en portions de même longueur relative), ce qui encaisse les petits écarts
de GPS.
"""

import json
import math

from data.database import connexion

RAYON_M = 300
ECART_DISTANCE = 0.12


def _dist_m(a, b):
    r = 6371000.0
    la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


def traces_disponibles(athlete_id):
    """{activite_id: {"nom", "date", "points"}} des sorties qui ont une trace."""
    conn = connexion()
    try:
        lignes = conn.execute(
            "SELECT a.id, a.nom, a.date, p.trace_json FROM parcours_gpx p JOIN activites a ON a.id = p.activite_id "
            "WHERE a.athlete_id=? AND p.trace_json IS NOT NULL ORDER BY a.date DESC", (athlete_id,)).fetchall()
    finally:
        conn.close()
    res = {}
    for aid, nom, d, tj in lignes:
        try:
            pts = [p for p in json.loads(tj) if p and p[0] is not None and p[1] is not None]
        except (ValueError, TypeError):
            continue
        if len(pts) >= 10 and aid not in res:
            res[aid] = {"nom": nom, "date": d, "points": pts}
    return res


def cumul_km(points):
    c, tot = [0.0], 0.0
    for i in range(1, len(points)):
        tot += _dist_m(points[i - 1], points[i]) / 1000
        c.append(tot)
    return c


def meme_parcours(pa, pb):
    if _dist_m(pa[0], pb[0]) > RAYON_M or _dist_m(pa[-1], pb[-1]) > RAYON_M:
        return False
    da, db = cumul_km(pa)[-1], cumul_km(pb)[-1]
    return da > 0 and db > 0 and abs(da - db) / max(da, db) <= ECART_DISTANCE


def candidats(athlete_id, activite_id, traces=None):
    """Sorties sur le même parcours que `activite_id` : [(id, nom, date)], la plus récente d'abord."""
    traces = traces if traces is not None else traces_disponibles(athlete_id)
    ref = traces.get(activite_id)
    if not ref:
        return []
    return [(aid, t["nom"], t["date"]) for aid, t in traces.items()
            if aid != activite_id and meme_parcours(ref["points"], t["points"])]


def paires(athlete_id, traces=None):
    """Toutes les sorties qui ont au moins un « jumeau » : [(id, nom, date, nb_jumeaux)]."""
    traces = traces if traces is not None else traces_disponibles(athlete_id)
    res = []
    for aid, t in traces.items():
        n = len(candidats(athlete_id, aid, traces))
        if n:
            res.append((aid, t["nom"], t["date"], n))
    return res


def _portions(points, n):
    """n portions de même longueur : [{km_debut, km_fin, temps_s, montee_m, descente_m, fc}]."""
    cum = cumul_km(points)
    total = cum[-1]
    bornes = [total * i / n for i in range(n + 1)]
    res, j = [], 0
    for k in range(n):
        i0 = j
        while j < len(points) - 1 and cum[j + 1] <= bornes[k + 1]:
            j += 1
        seg = points[i0:j + 1] if j > i0 else points[i0:i0 + 2]
        t0, t1 = seg[0][3] if len(seg[0]) > 3 else None, seg[-1][3] if len(seg[-1]) > 3 else None
        montee = descente = 0.0
        for a, b in zip(seg, seg[1:]):
            if a[2] is None or b[2] is None:
                continue
            d = b[2] - a[2]
            if d > 0.5:
                montee += d
            elif d < -0.5:
                descente -= d
        fcs = [p[4] for p in seg if len(p) > 4 and p[4]]
        res.append({"km_debut": round(bornes[k], 2), "km_fin": round(bornes[k + 1], 2),
                    "temps_s": (t1 - t0) if t0 is not None and t1 is not None else None,
                    "montee_m": round(montee), "descente_m": round(descente),
                    "fc": round(sum(fcs) / len(fcs)) if fcs else None})
    return res


def comparer(athlete_id, id_a, id_b, n=10, traces=None):
    """Comparaison portion par portion. Le temps « écart » est B − A (négatif : B plus rapide)."""
    traces = traces if traces is not None else traces_disponibles(athlete_id)
    a, b = traces.get(id_a), traces.get(id_b)
    if not a or not b:
        raise ValueError("Une des deux sorties n'a pas de trace GPS enregistrée.")
    if not meme_parcours(a["points"], b["points"]):
        raise ValueError("Ces deux sorties ne suivent pas le même parcours (départ, arrivée ou distance trop différents).")
    pa, pb = _portions(a["points"], n), _portions(b["points"], n)
    lignes = []
    for x, y in zip(pa, pb):
        ecart = (y["temps_s"] - x["temps_s"]) if x["temps_s"] is not None and y["temps_s"] is not None else None
        terrain = "montée" if x["montee_m"] > x["descente_m"] + 10 else ("descente" if x["descente_m"] > x["montee_m"] + 10 else "plat")
        lignes.append({"km_debut": x["km_debut"], "km_fin": x["km_fin"], "terrain": terrain,
                       "a": x, "b": y, "ecart_s": ecart})
    ta = sum(l["a"]["temps_s"] or 0 for l in lignes)
    tb = sum(l["b"]["temps_s"] or 0 for l in lignes)
    gains = [l for l in lignes if l["ecart_s"] is not None]
    meilleur = min(gains, key=lambda l: l["ecart_s"]) if gains else None
    pire = max(gains, key=lambda l: l["ecart_s"]) if gains else None
    return {"a": {"id": id_a, "nom": a["nom"], "date": a["date"], "temps_s": ta or None, "km": round(cumul_km(a["points"])[-1], 2)},
            "b": {"id": id_b, "nom": b["nom"], "date": b["date"], "temps_s": tb or None, "km": round(cumul_km(b["points"])[-1], 2)},
            "portions": lignes, "ecart_total_s": (tb - ta) if ta and tb else None,
            "resume": resume(lignes, ta, tb, meilleur, pire)}


def _mmss(s):
    s = int(round(abs(s)))
    return f"{s // 60} min {s % 60:02d} s" if s >= 60 else f"{s} s"


def resume(lignes, ta, tb, meilleur, pire):
    if not ta or not tb:
        return "Les traces n'ont pas d'horodatage : seuls la montée et la descente sont comparées."
    sens = "plus rapide" if tb < ta else "plus lent"
    t = f"Le second passage est {sens} de {_mmss(tb - ta)} au total."
    if meilleur and meilleur["ecart_s"] < 0:
        t += f" Il gagne le plus entre km {str(meilleur['km_debut']).replace('.', ',')} et {str(meilleur['km_fin']).replace('.', ',')} ({meilleur['terrain']}, {_mmss(meilleur['ecart_s'])})."
    if pire and pire["ecart_s"] > 0:
        t += f" Il perd le plus entre km {str(pire['km_debut']).replace('.', ',')} et {str(pire['km_fin']).replace('.', ',')} ({pire['terrain']}, {_mmss(pire['ecart_s'])})."
    return t
