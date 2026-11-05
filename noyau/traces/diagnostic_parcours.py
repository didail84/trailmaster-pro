"""
Diagnostic de difficulté d'un parcours et comparaison de deux tracés
(Trail Hub Center, étape 3.2 — bloc 16 du Master Plan).

À partir du seul tracé (latitude, longitude, altitude) :
  - distance, D+ et D− sur l'altitude lissée (comme les analyses de sortie),
    km-effort (km + D+/100) et catégorie de course ITRA qui en découle ;
  - répartition de la distance par classe de pente, et du D+ par quart de
    parcours (savoir si le dur est au début ou à la fin) ;
  - principales montées et descentes, pente la plus raide tenue sur 200 m et 1 km ;
  - indicateurs de technicité ESTIMÉS : part de pentes à plus de 25 % (souvent
    en marchant, parfois avec les mains), descentes raides, sinuosité (lacets,
    sentier qui serpente) et altitude. Un GPS ne voit ni les cailloux ni les
    racines : ces indicateurs sont des repères, pas une cotation du terrain.

Aucun widget ici. Utilisé par l'écran « Diagnostic de parcours » et l'IA.
"""


from noyau.traces.analyse_traces import profil as profil_25m, _haversine_m

# Classes de pente : (borne basse, borne haute, libellé, code)
CLASSES_PENTE = (
    (-1.0, -0.15, "Descente raide (< −15 %)", "descente_raide"),
    (-0.15, -0.05, "Descente (−15 à −5 %)", "descente"),
    (-0.05, 0.05, "Plat ou presque (−5 à +5 %)", "plat"),
    (0.05, 0.15, "Montée courante (5 à 15 %)", "montee"),
    (0.15, 0.25, "Montée raide (15 à 25 %)", "montee_raide"),
    (0.25, 1.0, "Très raide (> 25 %)", "tres_raide"),
)

# Catégories ITRA d'une course selon son km-effort
CATEGORIES_ITRA = ((25, "XXS"), (45, "XS"), (75, "S"), (115, "M"), (155, "L"), (210, "XL"), (float("inf"), "XXL"))

# Repères de terrain selon le D+ par km (lecture indicative)
TERRAINS = ((15, "Roulant"), (30, "Vallonné"), (50, "Montagneux"), (75, "Très montagneux"),
            (float("inf"), "Alpin, très raide"))


def categorie_itra(km_effort):
    for borne, cat in CATEGORIES_ITRA:
        if km_effort < borne:
            return cat
    return "XXL"


def terrain(dplus_par_km):
    for borne, nom in TERRAINS:
        if dplus_par_km < borne:
            return nom
    return TERRAINS[-1][1]


def _pente_max_soutenue(prof, longueur_m, signe=1):
    """Pente moyenne la plus forte (en montée si signe=1, en descente si -1)
    tenue sur `longueur_m` mètres, en %."""
    n = len(prof)
    meilleure, j = None, 0
    for i in range(n):
        while j < n - 1 and prof[j]["d"] - prof[i]["d"] < longueur_m:
            j += 1
        dd = prof[j]["d"] - prof[i]["d"]
        if dd < longueur_m * 0.9:
            break
        g = (prof[j]["alt"] - prof[i]["alt"]) / dd * signe
        if meilleure is None or g > meilleure:
            meilleure = g
    return None if meilleure is None else round(meilleure * 100, 1)


def _sinuosite(points, fenetre_m=200.0):
    """Rapport moyen « longueur parcourue / distance à vol d'oiseau » sur des
    fenêtres de 200 m : 1,0 = ligne droite ; au-delà de 1,3 = sentier qui serpente."""
    cum, d = [0.0], 0.0
    for a, b in zip(points, points[1:]):
        d += _haversine_m(a[0], a[1], b[0], b[1])
        cum.append(d)
    ratios, i = [], 0
    for j in range(1, len(points)):
        if cum[j] - cum[i] >= fenetre_m:
            droit = _haversine_m(points[i][0], points[i][1], points[j][0], points[j][1])
            if droit > 20:
                ratios.append((cum[j] - cum[i]) / droit)
            i = j
    return round(sum(ratios) / len(ratios), 2) if ratios else None


def _montees_nettes(prof, signe=1, seuil=12.0, gain_min=40.0, pente_min=0.03):
    """Montées (signe=1) ou descentes (signe=-1) par « zigzag » sur l'altitude lissée,
    bornes resserrées : le plat avant le pied et après le sommet n'est pas compté.
    [{km_debut, longueur_m, gain_m, pente_pct, pente_max_pct, categorie}]."""
    alt = [e["alt"] * signe for e in prof]
    n = len(alt)
    pivots, direction, ext = [0], 0, 0
    for i in range(1, n):
        if direction == 0:
            if abs(alt[i] - alt[0]) >= seuil:
                direction, ext = (1 if alt[i] > alt[0] else -1), i
            continue
        if (alt[i] - alt[ext]) * direction > 0:
            ext = i
        elif (alt[ext] - alt[i]) * direction >= seuil:
            pivots.append(ext)
            direction, ext = -direction, i
    pivots += [ext, n - 1]
    pivots = sorted(set(pivots))
    res = []
    for a, b in zip(pivots, pivots[1:]):
        gain = alt[b] - alt[a]
        if gain < gain_min:
            continue
        marge = 0.03 * gain
        a2 = max(i for i in range(a, b + 1) if alt[i] <= alt[a] + marge)
        b2 = min(i for i in range(a2, b + 1) if alt[i] >= alt[b] - marge)
        longueur = prof[b2]["d"] - prof[a2]["d"]
        gain2 = alt[b2] - alt[a2]
        if longueur < 250 or gain2 / longueur < pente_min:
            continue
        pente_max = max(e["pente"] * signe for e in prof[a2:b2 + 1])
        score = longueur * gain2 / longueur * 100
        cat = None
        if signe == 1 and longueur >= 500:
            for borne, nom in ((80000, "HC"), (64000, "Cat. 1"), (32000, "Cat. 2"), (16000, "Cat. 3"), (8000, "Cat. 4")):
                if score >= borne:
                    cat = nom
                    break
        res.append({"km_debut": round(prof[a2]["d"] / 1000, 1), "longueur_m": round(longueur),
                    "gain_m": round(gain2), "pente_pct": round(gain2 / longueur * 100, 1),
                    "pente_max_pct": round(min(pente_max, 0.6) * 100, 1), "categorie": cat})
    return res


def diagnostiquer(points, nom=""):
    """Diagnostic complet (dict) ou None si le tracé est inutilisable (pas d'altitude, trop court)."""
    pts = [p for p in points or [] if isinstance(p, (list, tuple)) and len(p) >= 3 and p[2] is not None]
    if len(pts) < 10:
        return None
    prof = profil_25m([[p[0], p[1], p[2]] for p in pts])
    if not prof:
        return None
    distance_km = prof[-1]["d"] / 1000
    dplus = dmoins = 0.0
    for a, b in zip(prof, prof[1:]):
        dz = b["alt"] - a["alt"]
        if dz > 0:
            dplus += dz
        else:
            dmoins -= dz
    alts = [e["alt"] for e in prof]

    # Répartition par classe de pente (part de la distance)
    pas = prof[1]["d"] - prof[0]["d"] if len(prof) > 1 else 25.0
    km_classe = {c: 0.0 for *_x, c in CLASSES_PENTE}
    for e in prof[1:]:
        for bas, haut, _lib, code in CLASSES_PENTE:
            if bas <= e["pente"] < haut:
                km_classe[code] += pas / 1000
                break
    repartition = [{"code": code, "libelle": lib, "km": round(km_classe[code], 2),
                    "pct": round(km_classe[code] / distance_km * 100, 1) if distance_km else 0.0}
                   for _b, _h, lib, code in CLASSES_PENTE]

    # D+ et D− par quart de parcours
    quarts = []
    for q in range(4):
        d0, d1 = distance_km * 1000 * q / 4, distance_km * 1000 * (q + 1) / 4
        up = down = 0.0
        for a, b in zip(prof, prof[1:]):
            if d0 <= a["d"] < d1:
                dz = b["alt"] - a["alt"]
                up += max(dz, 0)
                down += max(-dz, 0)
        quarts.append({"quart": q + 1, "km_debut": round(d0 / 1000, 1), "km_fin": round(d1 / 1000, 1),
                       "dplus": round(up), "dmoins": round(down)})
    part_fin = (quarts[2]["dplus"] + quarts[3]["dplus"]) / dplus if dplus else 0.5
    placement = ("le dénivelé est surtout dans la seconde moitié : garde des forces"
                 if part_fin >= 0.6 else
                 "le dénivelé est surtout dans la première moitié : ne pars pas trop vite dans les premières montées"
                 if part_fin <= 0.4 else "le dénivelé est réparti sur tout le parcours")

    # Montées et descentes principales (bornes resserrées sur la partie qui monte vraiment)
    montees_principales = sorted(_montees_nettes(prof, 1), key=lambda x: -x["gain_m"])[:6]
    descentes = [{"km_debut": x["km_debut"], "longueur_m": x["longueur_m"], "perte_m": x["gain_m"],
                  "pente_pct": x["pente_pct"], "pente_max_pct": x["pente_max_pct"]}
                 for x in sorted(_montees_nettes(prof, -1), key=lambda x: -x["gain_m"])[:4]]

    km_effort = distance_km + dplus / 100
    dplus_km = dplus / distance_km if distance_km else 0
    tres_raide = next(r for r in repartition if r["code"] == "tres_raide")
    descente_raide = next(r for r in repartition if r["code"] == "descente_raide")
    sinuo = _sinuosite(pts)
    km_haut = sum(pas / 1000 for e in prof if e["alt"] >= 2000)

    technicite = []
    if tres_raide["pct"] >= 3:
        technicite.append(f"{_virgule(tres_raide['pct'])} % de la distance au-dessus de 25 % de pente : passages où l'on marche, "
                          "parfois avec les mains ou les bâtons.")
    if descente_raide["pct"] >= 8:
        technicite.append(f"{_virgule(descente_raide['pct'])} % de la distance en descente raide (plus de 15 %) : "
                          "quadriceps et technique de descente sollicités.")
    if sinuo and sinuo >= 1.3:
        technicite.append(f"Sinuosité de {_virgule(sinuo, 2)} : sentier qui serpente ou en lacets, relances fréquentes.")
    if km_haut >= 1:
        technicite.append(f"{_virgule(km_haut)} km au-dessus de 2 000 m : souffle plus court, météo de montagne.")
    # Note de technicité 0-5, ESTIMÉE depuis le tracé (pas une cotation du terrain)
    note_tech = min(5.0, tres_raide["pct"] / 4 + descente_raide["pct"] / 8 + max(0.0, (sinuo or 1.0) - 1.1) * 5
                    + (1.0 if km_haut >= 1 else 0.0))

    return {
        "nom": nom, "distance_km": round(distance_km, 2), "dplus_m": round(dplus), "dmoins_m": round(dmoins),
        "alt_min": round(min(alts)), "alt_max": round(max(alts)),
        "km_effort": round(km_effort, 1), "categorie_itra": categorie_itra(km_effort),
        "dplus_par_km": round(dplus_km), "terrain": terrain(dplus_km),
        "repartition_pentes": repartition, "quarts": quarts, "part_dplus_seconde_moitie_pct": round(part_fin * 100),
        "placement_denivele": placement,
        "montees": montees_principales, "descentes": descentes,
        "pente_max_200m_pct": _pente_max_soutenue(prof, 200), "pente_max_1km_pct": _pente_max_soutenue(prof, 1000),
        "descente_max_200m_pct": _pente_max_soutenue(prof, 200, -1),
        "sinuosite": sinuo, "km_au_dessus_2000m": round(km_haut, 1),
        "technicite": technicite, "note_technicite": round(note_tech, 1),
        "profil": [(round(e["d"] / 1000, 3), round(e["alt"], 1)) for e in prof[::4]],
    }


def _virgule(v, d=1):
    """Nombre à la française : 9.3 → « 9,3 » (et 10.0 → « 10 »)."""
    t = f"{v:.{d}f}"
    if "." in t:
        t = t.rstrip("0").rstrip(".")
    return t.replace(".", ",")


def resume(diag):
    """Deux ou trois phrases lisibles."""
    if not diag:
        return ""
    t = (f"{_virgule(diag['distance_km'], 1)} km et {diag['dplus_m']} m de D+ : {diag['km_effort']:.0f} km-effort, "
         f"catégorie ITRA {diag['categorie_itra']}. Terrain {diag['terrain'].lower()} ({diag['dplus_par_km']} m de D+ par km) ; "
         f"{diag['placement_denivele']}.")
    if diag["montees"]:
        m = diag["montees"][0]
        t += (f" Plus grosse montée : {m['gain_m']} m sur {_virgule(m['longueur_m'] / 1000, 1)} km à {_virgule(m['pente_pct'], 1)} % "
              f"de moyenne, à partir du km {_virgule(m['km_debut'], 1)}.")
    return t


# ----------------------------------------------------------------------
# Comparaison de deux tracés
# ----------------------------------------------------------------------

def _pct(r):
    return {x["code"]: x["pct"] for x in r["repartition_pentes"]}


def comparer(a, b):
    """{"lignes": [(mesure, valeur A, valeur B, écart texte)], "phrases": [...]}."""
    def ecart(va, vb, unite="", pourcent=True):
        if va is None or vb is None:
            return "—"
        diff = vb - va
        txt = f"{diff:+.0f}{unite}" if unite or abs(diff) >= 10 else f"{diff:+.1f}"
        if pourcent and va:
            txt += f" ({diff / va * 100:+.0f} %)"
        return txt.replace(".", ",")

    pa, pb = _pct(a), _pct(b)
    raide_a = pa["montee_raide"] + pa["tres_raide"]
    raide_b = pb["montee_raide"] + pb["tres_raide"]
    lignes = [
        ("Distance", f"{a['distance_km']:.1f} km", f"{b['distance_km']:.1f} km", ecart(a["distance_km"], b["distance_km"], " km")),
        ("Dénivelé positif", f"{a['dplus_m']} m", f"{b['dplus_m']} m", ecart(a["dplus_m"], b["dplus_m"], " m")),
        ("Dénivelé négatif", f"{a['dmoins_m']} m", f"{b['dmoins_m']} m", ecart(a["dmoins_m"], b["dmoins_m"], " m")),
        ("Km-effort", f"{a['km_effort']:.0f}", f"{b['km_effort']:.0f}", ecart(a["km_effort"], b["km_effort"])),
        ("Catégorie ITRA", a["categorie_itra"], b["categorie_itra"], "" if a["categorie_itra"] == b["categorie_itra"] else "différente"),
        ("D+ par km", f"{a['dplus_par_km']} m", f"{b['dplus_par_km']} m", ecart(a["dplus_par_km"], b["dplus_par_km"], " m")),
        ("Montée à plus de 15 %", f"{raide_a:.0f} %", f"{raide_b:.0f} %", ecart(raide_a, raide_b, " pts", False)),
        ("Descente à plus de 15 %", f"{pa['descente_raide']:.0f} %", f"{pb['descente_raide']:.0f} %",
         ecart(pa["descente_raide"], pb["descente_raide"], " pts", False)),
        ("Pente la plus raide sur 1 km", f"{a['pente_max_1km_pct'] or 0:.0f} %", f"{b['pente_max_1km_pct'] or 0:.0f} %", ""),
        ("Altitude maximale", f"{a['alt_max']} m", f"{b['alt_max']} m", ecart(a["alt_max"], b["alt_max"], " m", False)),
        ("D+ dans la 2e moitié", f"{a['part_dplus_seconde_moitie_pct']} %", f"{b['part_dplus_seconde_moitie_pct']} %", ""),
        ("Technicité estimée (0 à 5)", f"{a['note_technicite']:.1f}", f"{b['note_technicite']:.1f}", ""),
    ]
    lignes = [(m, va.replace(".", ","), vb.replace(".", ","), e) for m, va, vb, e in lignes]
    phrases = []
    ke = (b["km_effort"] - a["km_effort"]) / a["km_effort"] * 100 if a["km_effort"] else 0
    nom_a, nom_b = a.get("nom") or "A", b.get("nom") or "B"
    if abs(ke) < 5:
        phrases.append(f"Effort global équivalent (km-effort à {ke:+.0f} %).")
    else:
        (plus, moins), grand, petit = ((nom_b, nom_a), b["km_effort"], a["km_effort"]) if ke > 0 else \
            ((nom_a, nom_b), a["km_effort"], b["km_effort"])
        surplus = (grand / petit - 1) * 100 if petit else 0
        phrases.append(f"« {plus} » demande environ {surplus:.0f} % d'effort de plus que « {moins} » (km-effort).")
    if abs(raide_b - raide_a) >= 5:
        plus = nom_b if raide_b > raide_a else nom_a
        phrases.append(f"« {plus} » est nettement plus raide en montée : plus de marche, bâtons utiles.")
    if abs(pb["descente_raide"] - pa["descente_raide"]) >= 5:
        plus = nom_b if pb["descente_raide"] > pa["descente_raide"] else nom_a
        phrases.append(f"« {plus} » a davantage de descentes raides : prépare les quadriceps.")
    if abs(b["part_dplus_seconde_moitie_pct"] - a["part_dplus_seconde_moitie_pct"]) >= 15:
        tard = nom_b if b["part_dplus_seconde_moitie_pct"] > a["part_dplus_seconde_moitie_pct"] else nom_a
        phrases.append(f"Sur « {tard} », le dénivelé arrive plus tard : la gestion de course compte davantage.")
    return {"lignes": lignes, "phrases": phrases}
