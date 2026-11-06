"""
Fractionné (Trail Hub Center, étape 3.5, bloc 14) : court ou long, à plat
ou en côte.

  - bibliothèque de séances types (et tes séances perso) ;
  - cibles calculées depuis ta VMA : temps de chaque répétition, temps au
    100, 200 et 400 m, distance attendue sur une répétition en durée ; en
    côte, vitesse réelle estimée selon la pente (coût énergétique de
    Minetti, comme le reste du logiciel) ;
  - déroulé minuté (échauffement, efforts, récupérations, retour au calme)
    pour le minuteur à bips et l'envoi à la montre ;
  - détection des répétitions dans la trace GPS d'une sortie ;
  - analyse des temps réels : % de VMA tenu, écart à la cible, régularité,
    baisse en fin de séance, conseil.

Une séance (structure) :
  {"nom", "format": "court"|"long", "terrain": "plat"|"cote",
   "echauffement_min", "retour_calme_min",
   "blocs": [{"series", "repetitions", "effort": {"mode": "distance"|"duree", "valeur"}  (m ou s),
              "pct_vma", "pente_pct", "recup": {"mode", "valeur", "type"}, "recup_series_s"}],
   "objectif", "description"}
"""

from statistics import mean, pstdev

from noyau.traces.analyse_traces import facteur_pente, _haversine_m

FORMATS = (("court", "Court"), ("long", "Long"))
TERRAINS = (("plat", "À plat"), ("cote", "En côte"))
LIBELLE_FORMAT = dict(FORMATS)
LIBELLE_TERRAIN = dict(TERRAINS)
TYPES_RECUP = ("trot", "marche", "descente en trottinant", "arrêt")


def _bloc(rep, mode, valeur, pct, recup_s, series=1, recup_series_s=0, pente=0, type_recup="trot",
          recup_mode="duree"):
    return {"series": series, "repetitions": rep, "effort": {"mode": mode, "valeur": valeur}, "pct_vma": pct,
            "pente_pct": pente, "recup": {"mode": recup_mode, "valeur": recup_s, "type": type_recup},
            "recup_series_s": recup_series_s}


def _s(code, nom, fmt, terrain, blocs, objectif, description, ech=20, rac=10):
    return {"code": code, "nom": nom, "format": fmt, "terrain": terrain, "echauffement_min": ech,
            "retour_calme_min": rac, "blocs": blocs, "objectif": objectif, "description": description}


BIBLIOTHEQUE = (
    # --- Court à plat : VMA ---
    _s("30_30", "30/30 (2 × 10)", "court", "plat", [_bloc(10, "duree", 30, 100, 30, 2, 180)], "VMA",
       "Le classique pour développer la VMA : 30 s vite, 30 s en trottinant."),
    _s("15_15", "15/15 (2 × 12)", "court", "plat", [_bloc(12, "duree", 15, 110, 15, 2, 180)], "VMA, vitesse",
       "Très court et très vite : la foulée reste relâchée."),
    _s("10x200", "10 × 200 m", "court", "plat", [_bloc(10, "distance", 200, 105, 45)], "VMA, vitesse",
       "Sur piste : récupération de 45 s en trottinant."),
    _s("8x300", "8 × 300 m", "court", "plat", [_bloc(8, "distance", 300, 103, 60)], "VMA",
       "Le 300 m apprend à tenir l'allure quand ça pique."),
    _s("10x400", "10 × 400 m", "court", "plat", [_bloc(10, "distance", 400, 100, 90)], "VMA",
       "Le tour de piste à VMA, 1 min 30 de récupération."),
    _s("pyramide", "Pyramide 200-400-600-800-600-400-200", "court", "plat",
       [_bloc(1, "distance", 200, 105, 60), _bloc(1, "distance", 400, 100, 90), _bloc(1, "distance", 600, 97, 120),
        _bloc(1, "distance", 800, 95, 150), _bloc(1, "distance", 600, 97, 120), _bloc(1, "distance", 400, 100, 90),
        _bloc(1, "distance", 200, 105, 60)], "VMA, gestion de l'allure",
       "Monter puis redescendre : la vitesse s'adapte à la longueur."),
    # --- Long à plat : seuil, allure 10 km ---
    _s("6x1000", "6 × 1000 m", "long", "plat", [_bloc(6, "distance", 1000, 92, 120)], "Allure 10 km, VMA longue",
       "Le grand classique pour l'allure 10 km."),
    _s("5x1000_95", "5 × 1000 m vite", "long", "plat", [_bloc(5, "distance", 1000, 95, 150)], "VMA longue",
       "Plus court mais plus rapide que le 6 × 1000 m."),
    _s("4x2000", "4 × 2000 m", "long", "plat", [_bloc(4, "distance", 2000, 88, 150)], "Seuil haut",
       "Entre le semi et le 10 km : régularité avant tout."),
    _s("3x3000", "3 × 3000 m au seuil", "long", "plat", [_bloc(3, "distance", 3000, 85, 180)], "Seuil",
       "Allure « confortablement dure », on peut dire quelques mots."),
    _s("3x10min", "3 × 10 min au seuil", "long", "plat", [_bloc(3, "duree", 600, 85, 120)], "Seuil",
       "Version en durée : pratique hors piste."),
    _s("2x15min", "2 × 15 min allure semi", "long", "plat", [_bloc(2, "duree", 900, 82, 180)], "Seuil bas, endurance",
       "Pour préparer un semi ou un trail rapide."),
    # --- Court en côte : puissance, VMA en montée ---
    _s("c10x30", "10 × 30 s en côte", "court", "cote", [_bloc(10, "duree", 30, 105, 60, pente=10,
                                                               type_recup="descente en trottinant")],
       "Puissance, VMA en montée", "Côte de 8 à 12 % : fréquence élevée, buste droit, retour en trottinant.", ech=25),
    _s("c12x100", "12 × 100 m en côte raide", "court", "cote", [_bloc(12, "distance", 100, 105, 60, pente=14,
                                                                       type_recup="descente en trottinant")],
       "Force, puissance", "Côte raide (12 à 15 %) : appuis courts, bras actifs.", ech=25),
    _s("c8x45", "8 × 45 s en côte", "court", "cote", [_bloc(8, "duree", 45, 100, 75, pente=8,
                                                             type_recup="descente en trottinant")],
       "VMA en montée", "Côte régulière de 6 à 10 %.", ech=25),
    _s("c2x6x1", "2 × 6 × 1 min en côte", "court", "cote", [_bloc(6, "duree", 60, 98, 60, 2, 240, pente=8,
                                                                   type_recup="descente en trottinant")],
       "VMA en montée", "Deux séries, 4 min entre les séries.", ech=25),
    # --- Long en côte : seuil en montée, spécifique trail ---
    _s("c5x3min", "5 × 3 min en côte", "long", "cote", [_bloc(5, "duree", 180, 90, 150, pente=7,
                                                               type_recup="descente en trottinant")],
       "Seuil en montée", "Côte de 5 à 8 % : allure tenue jusqu'au bout.", ech=25),
    _s("c4x5min", "4 × 5 min en côte", "long", "cote", [_bloc(4, "duree", 300, 87, 180, pente=7,
                                                               type_recup="descente en trottinant")],
       "Seuil en montée, spécifique trail", "Montée longue en courant, sans marcher.", ech=25),
    _s("c3x8min", "3 × 8 min en côte", "long", "cote", [_bloc(3, "duree", 480, 84, 240, pente=8,
                                                               type_recup="descente en trottinant")],
       "Spécifique trail", "Peut se faire en alternant course et marche rapide si la pente dépasse 15 %.", ech=25),
    _s("c4x1000", "4 × 1000 m en côte", "long", "cote", [_bloc(4, "distance", 1000, 88, 240, pente=6,
                                                                type_recup="descente en trottinant")],
       "Seuil en montée", "Côte longue et régulière ; récupération en redescendant.", ech=25),
)
_PAR_CODE = {s["code"]: s for s in BIBLIOTHEQUE}


def modele(code):
    return _PAR_CODE.get(code)


def _fr(v, d=1):
    t = f"{v:.{d}f}".replace(".", ",")
    return t[:-2] if t.endswith(",0") else t


def texte_temps(s):
    """Secondes → « 1:32 », « 45 s », « 1 h 02:10 », avec dixièmes si moins de 60 s."""
    if s is None:
        return "—"
    s = float(s)
    if s < 60:
        return f"{_fr(s, 1)} s"
    s = int(round(s))
    h, reste = divmod(s, 3600)
    m, sec = divmod(reste, 60)
    return f"{h} h {m:02d}:{sec:02d}" if h else f"{m}:{sec:02d}"


def lire_temps(texte):
    """« 1:32 », « 1'32 », « 92 », « 92,5 », « 1:02:10 » → secondes ; None si illisible."""
    t = (texte or "").strip().replace("''", "").replace("\"", "").replace("'", ":").replace(",", ".").replace(" ", "")
    if not t:
        return None
    try:
        if ":" in t:
            parts = [float(p) for p in t.split(":") if p != ""]
            if not parts or any(p < 0 for p in parts):
                return None
            s = 0.0
            for p in parts:
                s = s * 60 + p
            return s
        v = float(t.rstrip("s"))
        return v if v > 0 else None
    except ValueError:
        return None


def duree_courte(s):
    """45 → « 45 s », 90 → « 1 min 30 », 180 → « 3 min »."""
    s = int(round(s or 0))
    if s < 60:
        return f"{s} s"
    m, r = divmod(s, 60)
    return f"{m} min" + (f" {r:02d}" if r else "")


def allure_texte(vitesse_kmh):
    if not vitesse_kmh:
        return "—"
    s = 3600 / vitesse_kmh
    return f"{int(s // 60)}:{int(round(s % 60)):02d}/km".replace(":60", ":59")


def vitesse_cote(vitesse_plat_kmh, pente_pct):
    """Vitesse réelle attendue en côte pour le même effort que `vitesse_plat_kmh` à plat."""
    return vitesse_plat_kmh / facteur_pente((pente_pct or 0) / 100)


def libelle_effort(e):
    if e["mode"] == "distance":
        return f"{int(e['valeur'])} m" if e["valeur"] < 1000 or e["valeur"] % 1000 else f"{int(e['valeur'] // 1000)} km"
    return duree_courte(e["valeur"])


def cible_repetition(bloc, vma_kmh, terrain="plat"):
    """{vitesse_kmh, allure, temps_s, distance_m, dplus_m} attendus pour une répétition du bloc."""
    v_plat = vma_kmh * bloc["pct_vma"] / 100
    pente = (bloc.get("pente_pct") or 0) if terrain == "cote" else 0
    v = vitesse_cote(v_plat, pente) if pente else v_plat
    e = bloc["effort"]
    if e["mode"] == "distance":
        dist = e["valeur"]
        temps = dist / (v / 3.6)
    else:
        temps = e["valeur"]
        dist = v / 3.6 * temps
    return {"vitesse_kmh": round(v, 2), "vitesse_plat_kmh": round(v_plat, 2), "allure": allure_texte(v),
            "allure_plat": allure_texte(v_plat), "temps_s": round(temps, 1), "distance_m": round(dist),
            "dplus_m": round(dist * pente / 100) if pente else 0}


def repetitions(structure):
    """Liste à plat des répétitions : [{bloc, serie, rep, numero}] dans l'ordre."""
    res, n = [], 0
    for b, bloc in enumerate(structure["blocs"]):
        for s in range(max(1, int(bloc.get("series") or 1))):
            for r in range(max(1, int(bloc["repetitions"]))):
                n += 1
                res.append({"bloc": b, "serie": s, "rep": r, "numero": n})
    return res


def cibles(structure, vma_kmh):
    """Cibles de toute la séance : [{numero, bloc, serie, rep, libelle, ...cible}] + totaux."""
    lignes = []
    for r in repetitions(structure):
        bloc = structure["blocs"][r["bloc"]]
        c = cible_repetition(bloc, vma_kmh, structure["terrain"])
        lignes.append({**r, **c, "libelle": libelle_effort(bloc["effort"]), "pct_vma": bloc["pct_vma"],
                       "pente_pct": bloc.get("pente_pct") or 0})
    # sommes en dixièmes de seconde entiers : même résultat quelle que soit la version de Python (et dans la page)
    temps_effort = sum(round(l["temps_s"] * 10) for l in lignes) / 10
    dist_effort = sum(l["distance_m"] for l in lignes)
    return {"lignes": lignes, "temps_effort_s": round(temps_effort), "distance_effort_m": round(dist_effort),
            "dplus_m": sum(l["dplus_m"] for l in lignes), "duree_totale_s": round(sum(round(p["duree_s"] * 10) for p in deroule(structure, vma_kmh)) / 10)}


def temps_de_passage(vma_kmh, pct=100, distances=(100, 200, 300, 400, 500, 1000)):
    """Temps au 100, 200, 400 m… à `pct` % de VMA : [(distance_m, secondes)]."""
    v = vma_kmh * pct / 100 / 3.6
    return [(d, round(d / v, 1)) for d in distances]


def tableau_allures(vma_kmh, pcts=(80, 85, 90, 95, 100, 105, 110), distances=(100, 200, 300, 400, 1000)):
    """Tableau des temps de passage : [(pct, allure, [secondes par distance])]."""
    return [(p, allure_texte(vma_kmh * p / 100), [s for _d, s in temps_de_passage(vma_kmh, p, distances)])
            for p in pcts]


def _duree_recup(recup, vitesse_trot_kmh):
    if recup["mode"] == "duree":
        return recup["valeur"]
    return recup["valeur"] / (vitesse_trot_kmh / 3.6)


def deroule(structure, vma_kmh):
    """Les phases dans l'ordre pour le minuteur : [{phase, libelle, duree_s, numero?, cible?, distance_m?}].
    Une répétition en distance a la durée de son temps cible (le minuteur annonce la fin attendue)."""
    trot = vma_kmh * 0.55
    phases = []
    if structure.get("echauffement_min"):
        phases.append({"phase": "echauffement", "libelle": "Échauffement", "duree_s": structure["echauffement_min"] * 60})
    reps = repetitions(structure)
    for i, r in enumerate(reps):
        bloc = structure["blocs"][r["bloc"]]
        c = cible_repetition(bloc, vma_kmh, structure["terrain"])
        e = bloc["effort"]
        cible_txt = (f"{texte_temps(c['temps_s'])} sur {libelle_effort(e)}" if e["mode"] == "distance"
                     else f"≈ {c['distance_m']} m en {libelle_effort(e)}")
        phases.append({"phase": "effort", "libelle": f"Effort {r['numero']}/{len(reps)} — {libelle_effort(e)}",
                       "duree_s": c["temps_s"], "numero": r["numero"], "cible": cible_txt,
                       "allure": c["allure"], "mode": e["mode"], "distance_m": c["distance_m"]})
        dernier = i == len(reps) - 1
        if dernier:
            break
        suivant = reps[i + 1]
        if suivant["bloc"] == r["bloc"] and suivant["serie"] != r["serie"] and bloc.get("recup_series_s"):
            phases.append({"phase": "recup", "libelle": "Récupération entre les séries", "duree_s": bloc["recup_series_s"]})
        elif bloc["recup"]["valeur"]:
            phases.append({"phase": "recup", "libelle": f"Récupération ({bloc['recup'].get('type') or 'trot'})",
                           "duree_s": round(_duree_recup(bloc["recup"], trot))})
    if structure.get("retour_calme_min"):
        phases.append({"phase": "retour", "libelle": "Retour au calme", "duree_s": structure["retour_calme_min"] * 60})
    return phases


def etapes_montre(structure, vma_kmh):
    """Étapes au format des séances structurées (export FIT) : allure cible à plat, effort libre en côte."""
    etapes = []
    for p in deroule(structure, vma_kmh):
        if p["phase"] == "echauffement":
            etapes.append({"type": "Échauffement", "mode": "duree", "valeur": round(p["duree_s"] / 60, 2),
                           "allure_cible": None, "fc_cible": None})
        elif p["phase"] == "effort":
            plat = structure["terrain"] == "plat"
            allure = p["allure"].replace("/km", "") if plat else None
            if p["mode"] == "distance":
                etapes.append({"type": "Effort", "mode": "distance", "valeur": round(p["distance_m"] / 1000, 3),
                               "allure_cible": allure, "fc_cible": None})
            else:
                etapes.append({"type": "Effort", "mode": "duree", "valeur": round(p["duree_s"] / 60, 3),
                               "allure_cible": allure, "fc_cible": None})
        elif p["phase"] == "recup":
            etapes.append({"type": "Récupération", "mode": "duree", "valeur": round(p["duree_s"] / 60, 2),
                           "allure_cible": None, "fc_cible": None})
        else:
            etapes.append({"type": "Retour au calme", "mode": "duree", "valeur": round(p["duree_s"] / 60, 2),
                           "allure_cible": None, "fc_cible": None})
    return etapes


def resume(structure, vma_kmh=None):
    """« 2 × 10 × 30 s à 100 % VMA, récup 30 s trot (3 min entre les séries) »."""
    morceaux = []
    for b in structure["blocs"]:
        t = (f"{b['series']} × " if (b.get("series") or 1) > 1 else "") + f"{b['repetitions']} × {libelle_effort(b['effort'])}"
        t += f" à {b['pct_vma']:g} % VMA"
        if structure["terrain"] == "cote" and b.get("pente_pct"):
            t += f" (côte ≈ {b['pente_pct']:g} %)"
        if b["recup"]["valeur"]:
            r = b["recup"]
            t += f", récup {duree_courte(r['valeur']) if r['mode'] == 'duree' else str(int(r['valeur'])) + ' m'} {r.get('type') or 'trot'}"
        if (b.get("series") or 1) > 1 and b.get("recup_series_s"):
            t += f" ({duree_courte(b['recup_series_s'])} entre les séries)"
        morceaux.append(t)
    if len(structure["blocs"]) > 3 and len({libelle_effort(b["effort"]) for b in structure["blocs"]}) > 2:
        return " – ".join(libelle_effort(b["effort"]) for b in structure["blocs"]) + " (pyramide)"
    return " ; ".join(morceaux)


# ----------------------------------------------------------------------
# Analyse des temps réels
# ----------------------------------------------------------------------

def analyser(structure, vma_kmh, realisees):
    """realisees : [{numero, temps_s?, distance_m?, dplus_m?, fc?}] (une par répétition faite).
    Renvoie {lignes, nb, pct_vma_moyen, ecart_moyen_pct, regularite_cv, baisse_fin_pct, verdict, conseils}."""
    cib = {l["numero"]: l for l in cibles(structure, vma_kmh)["lignes"]}
    lignes = []
    for r in realisees:
        c = cib.get(r.get("numero"))
        if not c:
            continue
        bloc = structure["blocs"][c["bloc"]]
        e = bloc["effort"]
        t = r.get("temps_s") if e["mode"] == "distance" else (r.get("temps_s") or e["valeur"])
        d = r.get("distance_m") if e["mode"] == "duree" else (r.get("distance_m") or e["valeur"])
        if not t or not d:
            continue
        v = d / t * 3.6
        pente = (r.get("dplus_m") / d * 100) if r.get("dplus_m") and d else (c["pente_pct"] if structure["terrain"] == "cote" else 0)
        v_plat = v * facteur_pente(pente / 100) if pente else v
        pct = v_plat / vma_kmh * 100
        ecart = (v - c["vitesse_kmh"]) / c["vitesse_kmh"] * 100
        lignes.append({**r, "temps_s": round(t, 1), "distance_m": round(d), "vitesse_kmh": round(v, 2),
                       "allure": allure_texte(v), "pct_vma": round(pct, 1), "ecart_pct": round(ecart, 1),
                       "cible_temps_s": c["temps_s"], "cible_distance_m": c["distance_m"],
                       "ecart_s": round(t - c["temps_s"], 1) if e["mode"] == "distance" else None,
                       "ecart_m": round(d - c["distance_m"]) if e["mode"] == "duree" else None,
                       "vitesse_ascension_mh": round(r["dplus_m"] / t * 3600) if r.get("dplus_m") else None})
    if not lignes:
        return {"lignes": [], "nb": 0, "verdict": "Aucun temps saisi.", "conseils": []}
    pcts = [l["pct_vma"] for l in lignes]
    ecarts = [l["ecart_pct"] for l in lignes]
    cv = pstdev(pcts) / mean(pcts) * 100 if len(pcts) > 1 else 0.0
    tiers = max(1, len(lignes) // 3)
    baisse = (mean(pcts[-tiers:]) - mean(pcts[:tiers])) / mean(pcts[:tiers]) * 100 if len(lignes) >= 3 else 0.0
    moy_ecart = mean(ecarts)
    nb_prevues = len(cib)
    conseils = []
    if moy_ecart > 4:
        verdict = "Plus vite que prévu"
        conseils.append("Tu as couru nettement plus vite que la cible : ta VMA est peut-être sous-estimée, "
                        "ou les répétitions étaient trop courtes pour toi. Refais un test ou monte la cible de 2 à 3 %.")
    elif moy_ecart < -5:
        verdict = "Plus lent que prévu"
        conseils.append("Cible pas tenue : fatigue, chaleur, terrain, ou VMA surestimée. Allonge la récupération "
                        "ou baisse la cible de 3 à 5 % la prochaine fois.")
    else:
        verdict = "Dans la cible"
    if baisse < -5:
        conseils.append(f"Baisse de {_fr(-baisse)} % en fin de séance : départ trop rapide ou récupération trop courte.")
    elif baisse > 4:
        conseils.append(f"Tu as fini {_fr(baisse)} % plus vite que tu n'as commencé : départ prudent, bonne gestion.")
    if cv > 4:
        conseils.append(f"Répétitions irrégulières (écart de {_fr(cv)} %) : cherche une allure plus constante.")
    elif len(lignes) >= 4:
        conseils.append("Répétitions très régulières : bonne maîtrise de l'allure.")
    if len(lignes) < nb_prevues:
        conseils.append(f"{len(lignes)} répétitions sur {nb_prevues} prévues.")
    return {"lignes": lignes, "nb": len(lignes), "nb_prevues": nb_prevues, "pct_vma_moyen": round(mean(pcts), 1),
            "ecart_moyen_pct": round(moy_ecart, 1), "regularite_cv": round(cv, 1), "baisse_fin_pct": round(baisse, 1),
            "verdict": verdict, "conseils": conseils}


# ----------------------------------------------------------------------
# Détection des répétitions dans la trace GPS
# ----------------------------------------------------------------------

def _preparer_trace(points):
    """Distance cumulée réelle et « à plat » (pente corrigée), temps, altitude lissée, FC."""
    pts = [p for p in points if len(p) >= 4 and p[3] is not None]
    if len(pts) < 20:
        return None
    t = [float(p[3]) for p in pts]
    alt = [float(p[2]) if p[2] is not None else None for p in pts]
    if any(a is None for a in alt):
        alt = [0.0] * len(pts)
    k = 5
    alt_l = [mean(alt[max(0, i - k):i + k + 1]) for i in range(len(alt))]
    d, deq, dplus = [0.0], [0.0], [0.0]
    for i in range(1, len(pts)):
        seg = _haversine_m(pts[i - 1][0], pts[i - 1][1], pts[i][0], pts[i][1])
        dz = alt_l[i] - alt_l[i - 1]
        g = max(-0.45, min(0.45, dz / seg)) if seg > 1 else 0.0
        d.append(d[-1] + seg)
        deq.append(deq[-1] + seg * facteur_pente(g))
        dplus.append(dplus[-1] + max(0.0, dz))
    fc = [p[4] if len(p) > 4 else None for p in pts]
    return {"t": t, "d": d, "deq": deq, "dplus": dplus, "fc": fc}


def _fenetres(tr, mode, valeur, cote):
    """Toutes les fenêtres candidates [(score, i, j)] couvrant `valeur` m ou s."""
    t, d, deq = tr["t"], tr["d"], tr["deq"]
    n = len(t)
    res = []
    j = 0
    for i in range(n):
        if j < i:
            j = i
        if mode == "distance":
            while j < n - 1 and d[j] - d[i] < valeur:
                j += 1
            if d[j] - d[i] < valeur * 0.97:
                break
        else:
            while j < n - 1 and t[j] - t[i] < valeur:
                j += 1
            if t[j] - t[i] < valeur * 0.97:
                break
        dt = t[j] - t[i]
        if dt <= 0:
            continue
        if cote:
            if tr["dplus"][j] - tr["dplus"][i] < 0.03 * (d[j] - d[i]):     # il faut que ça monte
                continue
            score = (deq[j] - deq[i]) / dt
        else:
            score = (d[j] - d[i]) / dt
        res.append((score, i, j))
    return res


def detecter(points, structure):
    """Cherche dans la trace les répétitions de la séance : pour chaque bloc, les N fenêtres les plus
    rapides (à plat) ou les plus « dures » en pente corrigée (en côte) qui ne se chevauchent pas.
    Les blocs les plus longs sont cherchés d'abord, pour qu'un 200 m ne soit pas pris dans un 800 m.
    Renvoie [{numero, debut_s, temps_s, distance_m, dplus_m, fc}] dans l'ordre de la séance, ou []."""
    tr = _preparer_trace(points)
    if not tr:
        return []
    reps = repetitions(structure)
    cote = structure["terrain"] == "cote"
    # les répétitions identiques (même distance ou même durée) sont cherchées ensemble, puis rangées
    # dans l'ordre de la séance : les deux 400 m d'une pyramide ne s'échangent pas
    groupes = {}
    for r in reps:
        e = structure["blocs"][r["bloc"]]["effort"]
        groupes.setdefault((e["mode"], e["valeur"]), []).append(r)
    ordre = sorted(groupes, key=lambda k: -(k[1] * (1 if k[0] == "duree" else 0.3)))
    pris = []
    trouves = {}
    for cle in ordre:
        mode, valeur = cle
        candidats = sorted(_fenetres(tr, mode, valeur, cote), reverse=True)
        choisis = []
        for score, i, j in candidats:
            ti, tj = tr["t"][i], tr["t"][j]
            if any(ti < f + 3 and tj > dbt - 3 for dbt, f in pris):
                continue
            pris.append((ti, tj))
            choisis.append((i, j))
            if len(choisis) == len(groupes[cle]):
                break
        choisis.sort()
        for r, (i, j) in zip(groupes[cle], choisis):
            fcs = [f for f in tr["fc"][i:j + 1] if f]
            trouves[r["numero"]] = {"numero": r["numero"], "debut_s": round(tr["t"][i]),
                                    "temps_s": round(tr["t"][j] - tr["t"][i], 1),
                                    "distance_m": round(tr["d"][j] - tr["d"][i]),
                                    "dplus_m": round(tr["dplus"][j] - tr["dplus"][i]) if cote else None,
                                    "fc": round(mean(fcs)) if fcs else None}
    res = [trouves[r["numero"]] for r in reps if r["numero"] in trouves]
    return res


def estimer_vma(structure, analyse):
    """VMA suggérée par les répétitions courtes à plat bien tenues (ou None) : vitesse moyenne des
    répétitions divisée par le % de VMA visé, si la séance a été régulière et sans baisse."""
    if structure["terrain"] != "plat" or not analyse.get("lignes") or analyse["nb"] < 4:
        return None
    if analyse["regularite_cv"] > 4 or analyse["baisse_fin_pct"] < -5:
        return None
    cib = {l["numero"]: l for l in cibles(structure, 15)["lignes"]}
    estim = [l["vitesse_kmh"] / (cib[l["numero"]]["pct_vma"] / 100) for l in analyse["lignes"] if l["numero"] in cib]
    return round(mean(estim), 1) if estim else None


def nom_seance(structure):
    return structure.get("nom") or "Fractionné"


def categorie(structure):
    return f"{LIBELLE_FORMAT.get(structure['format'], structure['format'])} · {LIBELLE_TERRAIN.get(structure['terrain'], '')}"


def verifier_structure(structure):
    """Message d'erreur lisible, ou None si la séance est valide."""
    if not (structure.get("nom") or "").strip():
        return "Donne un nom à la séance."
    if structure.get("format") not in LIBELLE_FORMAT or structure.get("terrain") not in LIBELLE_TERRAIN:
        return "Choisis court ou long, à plat ou en côte."
    if not structure.get("blocs"):
        return "Ajoute au moins un bloc de répétitions."
    for b in structure["blocs"]:
        if (b.get("repetitions") or 0) < 1 or (b.get("series") or 1) < 1:
            return "Chaque bloc doit avoir au moins une répétition."
        if b["effort"]["mode"] not in ("distance", "duree") or (b["effort"]["valeur"] or 0) <= 0:
            return "Chaque répétition doit avoir une distance ou une durée."
        if not 50 <= (b.get("pct_vma") or 0) <= 130:
            return "L'intensité doit être entre 50 et 130 % de VMA."
        if b["effort"]["mode"] == "distance" and b["effort"]["valeur"] > 10000:
            return "Une répétition de plus de 10 km n'est plus du fractionné."
    return None



def bilan_realise(r):
    """Analyse d'un fractionné fait (ligne de fractionnes_realises), avec sa VMA de référence."""
    vma = r.get("vma_ref") or 15
    return analyser(r["structure"], vma, r.get("repetitions") or [])


def progression(realises):
    """Par séance (nom) : [{date, pct_vma, vitesse_kmh, verdict}] du plus ancien au plus récent ; seulement
    les séances faites au moins deux fois."""
    par_nom = {}
    for r in sorted(realises, key=lambda x: (x["date"], x.get("id") or 0)):
        a = bilan_realise(r)
        if not a.get("nb"):
            continue
        v = mean(l["vitesse_kmh"] for l in a["lignes"])
        par_nom.setdefault(r["nom"], []).append({"date": r["date"], "pct_vma": a["pct_vma_moyen"],
                                                 "vitesse_kmh": round(v, 2), "verdict": a["verdict"],
                                                 "vma_ref": r.get("vma_ref")})
    return {n: pts for n, pts in par_nom.items() if len(pts) >= 2}


def texte_progression(points):
    """« +3,2 % de vitesse moyenne depuis la première fois (4 séances) »."""
    if len(points) < 2:
        return ""
    a, b = points[0]["vitesse_kmh"], points[-1]["vitesse_kmh"]
    ev = (b - a) / a * 100 if a else 0
    signe = "+" if ev >= 0 else "−"
    return f"{signe}{_fr(abs(ev))} % de vitesse moyenne depuis la première fois ({len(points)} séances)."
