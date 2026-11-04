"""
Analyses de trace GPS de la v98 (aucun widget) :
  - ré-échantillonnage d'une trace tous les 25 m (altitude lissée)
  - allure ajustée à la pente (GAP, modèle de Minetti)           [P2]
  - montées : VAM, catégorie à la Strava                          [P1]
  - résistance à la fatigue par blocs de 30 minutes               [P3]
  - efficacité de course (m par battement, allure à FC fixe)      [P5]
  - vitesse selon la pente / le terrain                            [P9]

Une trace = liste de points [lat, lon, alt, temps_s, fc, (cadence)] telle
qu'enregistrée dans parcours_gpx.trace_json. Quand le temps ou la FC
manquent, les fonctions renvoient `None` / listes vides : rien n'est
inventé.
"""

import math
from statistics import mean, median

PAS_M = 25.0
LISSAGE_ECHANTILLONS = 5          # ≈ 125 m d'altitude lissée
PAUSE_VITESSE_MS = 0.4            # en dessous : à l'arrêt


# ----------------------------------------------------------------------
# Géométrie
# ----------------------------------------------------------------------

def _haversine_m(lat1, lon1, lat2, lon2):
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(min(1.0, math.sqrt(a)))


def cout_minetti(g):
    """Coût énergétique de la course (J/kg/m) selon la pente g (0,10 = 10 %)."""
    g = max(-0.45, min(0.45, g))
    return 155.4 * g ** 5 - 30.4 * g ** 4 - 43.3 * g ** 3 + 46.3 * g ** 2 + 19.5 * g + 3.6


COUT_PLAT = cout_minetti(0.0)


def facteur_pente(g):
    """Multiplicateur de vitesse pour ramener une vitesse sur pente g à
    son équivalent à plat. Montée : modèle de Minetti (coût énergétique).
    Descente : correction douce façon Strava — on gagne jusqu'à ~9 %
    de vitesse sur une descente régulière, puis les descentes très raides
    deviennent plus lentes que le plat (freinage, technique) ; le modèle
    énergétique pur de Minetti sous-estimerait trop l'effort en descente
    de trail."""
    if g >= 0:
        return cout_minetti(g) / COUT_PLAT
    g = max(g, -0.45)
    if g >= -0.09:
        return 1.0 + g
    return 0.91 + (-0.09 - g)


# ----------------------------------------------------------------------
# Profil ré-échantillonné
# ----------------------------------------------------------------------

def profil(points, pas=PAS_M):
    """Renvoie une liste d'échantillons (un tous les `pas` mètres) :
    {d, alt, t, fc, pente, v, v_gap, pause} ou [] si trace inutilisable.
    `t`/`v`/`v_gap` valent None sans temps par point."""
    if not points or len(points) < 3:
        return []
    cum, dist = [0.0], 0.0
    for a, b in zip(points, points[1:]):
        dist += _haversine_m(a[0], a[1], b[0], b[1])
        cum.append(dist)
    total = cum[-1]
    if total < 200:
        return []
    avec_temps = sum(1 for p in points if len(p) > 3 and p[3] is not None) > 0.8 * len(points)

    def interp(i0, i1, d, idx):
        a, b = points[i0], points[i1]
        va = a[idx] if len(a) > idx else None
        vb = b[idx] if len(b) > idx else None
        if va is None or vb is None:
            return va if vb is None else vb
        span = cum[i1] - cum[i0]
        f = 0.0 if span <= 0 else (d - cum[i0]) / span
        return va + (vb - va) * f

    echant = []
    j = 0
    d = 0.0
    while d <= total:
        while j < len(cum) - 2 and cum[j + 1] < d:
            j += 1
        alt = interp(j, j + 1, d, 2)
        t = interp(j, j + 1, d, 3) if avec_temps else None
        fc = points[j][4] if len(points[j]) > 4 else None
        if len(points[j + 1]) > 4 and points[j + 1][4] and (d - cum[j]) > (cum[j + 1] - cum[j]) / 2:
            fc = points[j + 1][4]
        echant.append({"d": d, "alt_brute": alt if alt is not None else 0.0, "t": t, "fc": fc})
        d += pas
    n = len(echant)
    if n < 6:
        return []

    h = LISSAGE_ECHANTILLONS // 2
    for i, e in enumerate(echant):
        lot = [echant[k]["alt_brute"] for k in range(max(0, i - h), min(n, i + h + 1))]
        e["alt"] = sum(lot) / len(lot)

    for i, e in enumerate(echant):
        i0, i1 = max(0, i - 2), min(n - 1, i + 2)
        dd = echant[i1]["d"] - echant[i0]["d"]
        e["pente"] = (echant[i1]["alt"] - echant[i0]["alt"]) / dd if dd > 0 else 0.0
        e["v"] = e["v_gap"] = None
        e["pause"] = False
        if avec_temps:
            ta, tb = echant[i0]["t"], echant[i1]["t"]
            if ta is not None and tb is not None and tb > ta:
                v = dd / (tb - ta)
                e["v"] = v
                e["pause"] = v < PAUSE_VITESSE_MS
                e["v_gap"] = v * facteur_pente(e["pente"])
    return echant


def _valide(e):
    return e["v"] is not None and not e["pause"] and e["v"] < 8.5  # < 8,5 m/s : pas du transport


def _allure_min_km(v_ms):
    return 1000.0 / v_ms / 60.0 if v_ms and v_ms > 0 else None


# ----------------------------------------------------------------------
# P2 — Allure ajustée à la pente
# ----------------------------------------------------------------------

def allure_ajustee(points, prof=None):
    """{allure, allure_ajustee, gain_pct, splits:[{km, allure, allure_ajustee, d_plus}]}
    ou None sans temps."""
    prof = prof if prof is not None else profil(points)
    if not prof or prof[0]["t"] is None:
        return None
    v_ok = [e for e in prof if _valide(e)]
    if len(v_ok) < 10:
        return None
    dist = len(v_ok) * PAS_M
    temps = sum(PAS_M / e["v"] for e in v_ok)
    temps_gap = sum(PAS_M / e["v_gap"] for e in v_ok if e["v_gap"])
    allure = temps / dist * 1000 / 60
    allure_gap = temps_gap / dist * 1000 / 60
    splits, courant = [], []
    for e in prof:
        courant.append(e)
        if e["d"] - courant[0]["d"] >= 1000 - PAS_M:
            ok = [x for x in courant if _valide(x)]
            if len(ok) >= 10:
                t = sum(PAS_M / x["v"] for x in ok)
                tg = sum(PAS_M / x["v_gap"] for x in ok if x["v_gap"])
                dp = sum(max(0.0, b["alt"] - a["alt"]) for a, b in zip(courant, courant[1:]))
                fcs = [x["fc"] for x in courant if x["fc"]]
                splits.append({"km": len(splits) + 1, "allure": t / (len(ok) * PAS_M) * 1000 / 60,
                               "allure_ajustee": tg / (len(ok) * PAS_M) * 1000 / 60, "d_plus": round(dp),
                               "fc": round(mean(fcs)) if fcs else None})
            courant = []
    return {"allure": allure, "allure_ajustee": allure_gap,
            "gain_pct": round((allure / allure_gap - 1) * 100, 1) if allure_gap else None, "splits": splits}


def courbes_allure(points, prof=None):
    """[(km, allure_min_km, allure_ajustee_min_km, altitude)] lissé sur ~200 m,
    pour tracer la courbe d'une sortie."""
    prof = prof if prof is not None else profil(points)
    if not prof or prof[0]["t"] is None:
        return []
    res = []
    fen = 8
    for i in range(0, len(prof), 4):
        lot = [e for e in prof[max(0, i - fen):i + fen + 1] if _valide(e)]
        if len(lot) < 4:
            continue
        v = len(lot) * PAS_M / sum(PAS_M / e["v"] for e in lot)
        vg = len(lot) * PAS_M / sum(PAS_M / e["v_gap"] for e in lot if e["v_gap"])
        a, ag = _allure_min_km(v), _allure_min_km(vg)
        if a and ag and a < 30:
            res.append((prof[i]["d"] / 1000.0, a, ag, prof[i]["alt"]))
    return res


# ----------------------------------------------------------------------
# P1 — Montées, VAM, catégories
# ----------------------------------------------------------------------

def _categorie(score):
    if score >= 80000:
        return "HC"
    for seuil, nom in ((64000, "Cat. 1"), (32000, "Cat. 2"), (16000, "Cat. 3"), (8000, "Cat. 4")):
        if score >= seuil:
            return nom
    return None


def montees(points, seuil_zigzag=12.0, gain_min=30.0, pente_min=0.03, longueur_min=250.0, prof=None):
    """Montées détectées par « zigzag » sur l'altitude lissée. Chaque montée :
    {km_debut, longueur_m, gain_m, pente_pct, pente_max_pct, duree_s, vam, score, categorie}."""
    prof = prof if prof is not None else profil(points)
    if not prof:
        return []
    alt = [e["alt"] for e in prof]
    n = len(alt)
    # points d'inflexion avec hystérésis (« zigzag »)
    pivots = [0]
    direction, ext = 0, 0
    for i in range(1, n):
        if direction == 0:
            if alt[i] - alt[0] >= seuil_zigzag:
                direction, ext = 1, i
            elif alt[0] - alt[i] >= seuil_zigzag:
                direction, ext = -1, i
            continue
        if direction == 1:
            if alt[i] > alt[ext]:
                ext = i
            elif alt[ext] - alt[i] >= seuil_zigzag:
                pivots.append(ext)
                direction, ext = -1, i
        else:
            if alt[i] < alt[ext]:
                ext = i
            elif alt[i] - alt[ext] >= seuil_zigzag:
                pivots.append(ext)
                direction, ext = 1, i
    pivots.append(ext if direction != 0 else n - 1)
    pivots.append(n - 1)
    pivots = sorted(set(pivots))

    res = []
    for a, b in zip(pivots, pivots[1:]):
        gain = alt[b] - alt[a]
        if gain < gain_min:
            continue
        longueur = prof[b]["d"] - prof[a]["d"]
        if longueur < longueur_min:
            continue
        pente = gain / longueur
        if pente < pente_min:
            continue
        duree = None
        if prof[a]["t"] is not None and prof[b]["t"] is not None and prof[b]["t"] > prof[a]["t"]:
            duree = prof[b]["t"] - prof[a]["t"]
        pentes = [e["pente"] for e in prof[a:b + 1]]
        score = longueur * pente * 100
        res.append({
            "km_debut": round(prof[a]["d"] / 1000, 2), "longueur_m": round(longueur), "gain_m": round(gain),
            "pente_pct": round(pente * 100, 1), "pente_max_pct": round(min(max(pentes), 0.6) * 100, 1),
            "duree_s": round(duree) if duree else None,
            "vam": round(gain / duree * 3600) if duree and duree > 60 else None,
            "score": round(score), "categorie": _categorie(score) if pente >= 0.03 and longueur >= 500 else None,
        })
    return res


# ----------------------------------------------------------------------
# P3 — Résistance à la fatigue
# ----------------------------------------------------------------------

def durabilite(points, duree_bloc_s=1800, debut_s=600, prof=None):
    """Efficacité (vitesse ajustée ÷ FC) par blocs de 30 min, mesurée à partir
    de la 10e minute, relative au premier bloc. Demande ≥ 1 h 30 de trace
    avec FC. Renvoie None sinon."""
    prof = prof if prof is not None else profil(points)
    if not prof or prof[0]["t"] is None:
        return None
    utile = [e for e in prof if _valide(e) and e["fc"] and e["fc"] > 80]
    if len(utile) < 100:
        return None
    t0 = prof[0]["t"]
    fin = prof[-1]["t"] - t0
    if fin < 5400:
        return None
    blocs = []
    b = 0
    while debut_s + (b + 1) * duree_bloc_s <= fin + duree_bloc_s * 0.4:
        a, z = debut_s + b * duree_bloc_s, debut_s + (b + 1) * duree_bloc_s
        lot = [e for e in utile if a <= e["t"] - t0 < z]
        if len(lot) >= 25:
            vg = mean(e["v_gap"] for e in lot)
            fc = mean(e["fc"] for e in lot)
            blocs.append({"debut_min": round(a / 60), "v_gap": vg, "fc": fc, "efficacite": vg * 60 / fc,
                          "allure_ajustee": _allure_min_km(vg)})
        b += 1
        if b > 20:
            break
    if len(blocs) < 3:
        return None
    ref = blocs[0]["efficacite"]
    for bl in blocs:
        bl["pct"] = round((bl["efficacite"] / ref - 1) * 100, 1)
    return {"blocs": blocs, "baisse_finale_pct": blocs[-1]["pct"], "duree_h": round(fin / 3600, 2)}


# ----------------------------------------------------------------------
# P5 — Efficacité de course
# ----------------------------------------------------------------------

def efficacite(points, fc_cible=None, prof=None):
    """{m_par_battement, allure_ajustee_fc} : mètres ajustés à la pente par
    battement cardiaque, et allure ajustée quand la FC est dans la bande
    fc_cible ± 5 (si fournie et ≥ 5 min dans la bande)."""
    prof = prof if prof is not None else profil(points)
    if not prof or prof[0]["t"] is None:
        return None
    utile = [e for e in prof if _valide(e) and e["fc"] and e["fc"] > 80 and e["v"] > 1.2]
    if len(utile) < 60:
        return None
    vg = mean(e["v_gap"] for e in utile)
    fc = mean(e["fc"] for e in utile)
    res = {"m_par_battement": vg * 60 / fc, "fc_moy": fc, "allure_ajustee_fc": None}
    if fc_cible:
        bande = [e for e in utile if abs(e["fc"] - fc_cible) <= 5]
        if len(bande) * PAS_M / max(mean(e["v"] for e in bande) if bande else 1, 0.1) >= 300:
            res["allure_ajustee_fc"] = _allure_min_km(mean(e["v_gap"] for e in bande))
    return res


# ----------------------------------------------------------------------
# P9 — Vitesse selon la pente
# ----------------------------------------------------------------------

CLASSES_PENTE = [
    ("Descente raide (< −12 %)", -9, -0.12),
    ("Descente (−12 à −5 %)", -0.12, -0.05),
    ("Faux plat descendant (−5 à −2 %)", -0.05, -0.02),
    ("Plat (±2 %)", -0.02, 0.02),
    ("Faux plat montant (2 à 5 %)", 0.02, 0.05),
    ("Montée (5 à 12 %)", 0.05, 0.12),
    ("Montée raide (12 à 20 %)", 0.12, 0.20),
    ("Mur (> 20 %)", 0.20, 9),
]


def vitesse_par_pente(points, prof=None):
    """Cumuls par classe de pente : {classe: [dist_m, temps_s, somme_fc_t, temps_fc]}."""
    prof = prof if prof is not None else profil(points)
    cumul = {c[0]: [0.0, 0.0, 0.0, 0.0] for c in CLASSES_PENTE}
    if not prof or prof[0]["t"] is None:
        return cumul
    for e in prof:
        if not _valide(e) or e["v"] < 0.3:
            continue
        for nom, bas, haut in CLASSES_PENTE:
            if bas <= e["pente"] < haut:
                dt = PAS_M / e["v"]
                c = cumul[nom]
                c[0] += PAS_M
                c[1] += dt
                if e["fc"]:
                    c[2] += e["fc"] * dt
                    c[3] += dt
                break
    return cumul


def fusionner_cumuls(liste):
    total = {c[0]: [0.0, 0.0, 0.0, 0.0] for c in CLASSES_PENTE}
    for cumul in liste:
        for k, v in cumul.items():
            for i in range(4):
                total[k][i] += v[i]
    return total


def resume_pente(cumul):
    """[{classe, part_distance_pct, allure_min_km, vitesse_kmh, fc}] pour les
    classes avec au moins 500 m."""
    dist_tot = sum(v[0] for v in cumul.values()) or 1
    res = []
    for nom, _b, _h in CLASSES_PENTE:
        d, t, sfc, tfc = cumul[nom]
        if d < 500 or t <= 0:
            continue
        v = d / t
        res.append({"classe": nom, "part_distance_pct": round(d / dist_tot * 100, 1),
                    "allure_min_km": _allure_min_km(v), "vitesse_kmh": v * 3.6,
                    "fc": round(sfc / tfc) if tfc > 0 else None, "distance_km": round(d / 1000, 1)})
    return res


# ----------------------------------------------------------------------
# Analyse complète d'une sortie (un seul ré-échantillonnage)
# ----------------------------------------------------------------------

_CACHE = {}


def analyser_sortie(activite_id, points, fc_cible=None, utiliser_cache=True):
    """Toutes les analyses d'une trace d'un coup : {gap, montees,
    durabilite, efficacite, pente}. Mis en cache en mémoire."""
    cle = (activite_id, fc_cible, len(points))
    if utiliser_cache and cle in _CACHE:
        return _CACHE[cle]
    prof = profil(points)
    res = {
        "gap": allure_ajustee(points, prof) if prof else None,
        "montees": montees(points, prof=prof) if prof else [],
        "durabilite": durabilite(points, prof=prof) if prof else None,
        "efficacite": efficacite(points, fc_cible, prof) if prof else None,
        "pente": vitesse_par_pente(points, prof) if prof else fusionner_cumuls([]),
    }
    _CACHE[cle] = res
    return res


def analyses_sur_periode(athlete_id, nb_jours=365, types=("Trail", "Course", "Randonnée"), fc_cible=None):
    """Analyse de toutes les sorties avec trace sur la période :
    [{id, date, nom, type, distance, denivele, duree, analyse}], de la plus
    récente à la plus ancienne. Lit les traces une par une (pas tout en
    mémoire)."""
    import json
    from datetime import date, timedelta
    from data.database import connexion

    depuis = (date.today() - timedelta(days=nb_jours)).isoformat()
    conn = connexion()
    cur = conn.cursor()
    marques = ",".join("?" * len(types))
    cur.execute(
        f"SELECT a.id, a.date, a.nom, a.type, a.distance, a.denivele, a.duree FROM activites a "
        f"WHERE a.athlete_id=? AND a.date>=? AND a.type IN ({marques}) AND a.distance>=2 "
        f"AND EXISTS (SELECT 1 FROM parcours_gpx p WHERE p.activite_id=a.id AND p.trace_json IS NOT NULL) "
        f"ORDER BY a.date DESC", (athlete_id, depuis, *types))
    lignes = cur.fetchall()
    res = []
    for id_, d, nom, type_, dist, deniv, duree in lignes:
        cur.execute("SELECT trace_json FROM parcours_gpx WHERE activite_id=? AND trace_json IS NOT NULL LIMIT 1", (id_,))
        r = cur.fetchone()
        try:
            pts = json.loads(r[0]) if r else []
        except (ValueError, TypeError):
            pts = []
        if not isinstance(pts, list) or len(pts) < 10:
            continue
        res.append({"id": id_, "date": d, "nom": nom, "type": type_, "distance": dist, "denivele": deniv,
                    "duree": duree, "analyse": analyser_sortie(id_, pts, fc_cible)})
    conn.close()
    return res
