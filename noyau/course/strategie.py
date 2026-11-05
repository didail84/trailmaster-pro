"""
Stratégie de course (Trail Hub Center, étape 3 — bloc 15 du Master Plan).

S'appuie sur le Roadbook de la v108 (tracé, points de passage, barrières,
nutrition par tronçon) et ajoute :
  - le temps appris sur TES sorties (régression distance + D+, ajustée à
    la saison) comme base de l'estimation ;
  - trois scénarios — prudent, réaliste, ambitieux — avec les heures de
    passage et la marge sur chaque barrière pour chacun ; l'écart entre
    les scénarios vient de la dispersion réelle de tes sorties autour du
    modèle (à défaut : −6 % / +10 %) ;
  - les sacs d'assistance : pour chaque point où tes proches t'attendent,
    ce qu'il faut y préparer pour aller jusqu'au point d'assistance suivant ;
  - les données du bracelet d'allures (heures de passage à porter au poignet).

Tout est une estimation : les temps se lisent comme des repères. Aucun
widget ici ; l'écran Roadbook s'en sert.
"""

from noyau.course import roadbook as rbk

SCENARIOS = (
    ("prudent", "Prudent"),
    ("realiste", "Réaliste"),
    ("ambitieux", "Ambitieux"),
)
LIBELLE_SCENARIO = dict(SCENARIOS)
FACTEURS_PAR_DEFAUT = {"prudent": 1.10, "realiste": 1.0, "ambitieux": 0.94}
BORNES = {"prudent": (1.04, 1.25), "ambitieux": (0.85, 0.97)}

TYPE_ASSISTANCE = "Assistance"
HEURE_NUIT_DEBUT, HEURE_NUIT_FIN = 19, 7      # repère simple : de 19 h à 7 h il faut la frontale


def duree_apprise(athlete_id, distance_km, denivele_m, date_course=None):
    """{secondes, nb_sorties, facteurs, message} depuis tes sorties, ou None."""
    from noyau.course.estimation_temps_course import estimer_temps_course
    if athlete_id is None or not distance_km:
        return None
    est = estimer_temps_course(athlete_id, distance_km, denivele_m, date_course)
    if not est:
        return None
    return {"secondes": est["secondes"], "nb_sorties": est["nb_sorties"],
            "extrapolation": est.get("extrapolation", False),
            "ajustement_saison": est.get("ajustement_saison", False),
            "facteurs": facteurs_scenarios(est.get("ratio_bas"), est.get("ratio_haut"))}


def facteurs_scenarios(ratio_bas=None, ratio_haut=None):
    """Multiplicateurs du temps réaliste pour chaque scénario. Tirés de la
    dispersion de tes sorties autour du modèle quand elle est connue, bornés
    pour rester plausibles en course ; sinon −6 % / +10 %."""
    f = dict(FACTEURS_PAR_DEFAUT)
    if ratio_bas and ratio_haut and ratio_haut > ratio_bas:
        milieu = (ratio_bas + ratio_haut) / 2
        lo, hi = BORNES["ambitieux"]
        f["ambitieux"] = round(min(hi, max(lo, ratio_bas / milieu)), 3)
        lo, hi = BORNES["prudent"]
        f["prudent"] = round(min(hi, max(lo, ratio_haut / milieu)), 3)
    return f


def calculer_scenarios(trace, points_course, depart_hhmm, duree_realiste_s, jour=None, facteurs=None):
    """{code: {"libelle", "facteur", "allure_plat", "passages", "temps_s", "pire_marge", "point_pire"}}.
    Chaque scénario recalcule les passages avec la pente (même méthode que le Roadbook)."""
    if len(trace) < 2 or not duree_realiste_s:
        return {}
    facteurs = facteurs or FACTEURS_PAR_DEFAUT
    res = {}
    for code, libelle in SCENARIOS:
        f = facteurs.get(code, FACTEURS_PAR_DEFAUT[code])
        allure = rbk.allure_plat_pour_duree(trace, duree_realiste_s * f)
        passages = rbk.calculer_passages(trace, points_course, depart_hhmm, allure, jour)
        pire, nom = rbk.temps_limite_theorique(passages)
        res[code] = {"libelle": libelle, "facteur": f, "allure_plat": allure, "passages": passages,
                     "temps_s": passages[-1]["temps_s"], "pire_marge": pire, "point_pire": nom}
    return res


def verdict_barrieres(scenarios):
    """Phrase courte sur les barrières, du scénario le plus exigeant au plus large."""
    p = scenarios.get("prudent")
    if not p or p["pire_marge"] is None:
        return None, None
    r = scenarios["realiste"]
    if p["pire_marge"] >= rbk.MARGE_SERREE_MIN:
        return "ok", (f"Même en scénario prudent, toutes les barrières passent (marge la plus faible : "
                      f"{p['pire_marge']} min à « {p['point_pire']} »).")
    if r["pire_marge"] is not None and r["pire_marge"] >= 0:
        return "serre", (f"En scénario prudent, la marge tombe à {p['pire_marge']} min à « {p['point_pire']} » : "
                         f"pars sur le plan réaliste et surveille ce point.")
    return "depasse", (f"Barrière en danger : en scénario réaliste tu passes « {r['point_pire']} » avec "
                       f"{r['pire_marge']} min de marge. Il faut viser le plan ambitieux ou une autre course.")


def _nuit(dt):
    return dt.hour >= HEURE_NUIT_DEBUT or dt.hour < HEURE_NUIT_FIN


def sacs_assistance(scenarios, nutrition, temperature_c=15, mes_produits=None):
    """Pour chaque point « Assistance » : quand tes proches doivent y être et ce
    que le sac doit contenir pour aller jusqu'à l'assistance suivante (ou
    l'arrivée). `nutrition` : lignes de rbk.nutrition_par_troncon (scénario réaliste).
    Renvoie [{nom, km, heures: {code: datetime}, jusqua, duree_s, glucides_g, eau_ml,
    gels, barres, ravitos, lignes: [texte]}].
    `mes_produits` : tes produits favoris ou validés (Nutrition de course) ; le sac est alors
    composé avec eux plutôt qu'avec des gels et barres « standard »."""
    from noyau.course.ravitaillement import GEL_G, BARRE_G
    real = scenarios.get("realiste")
    if not real:
        return []
    passages = real["passages"]
    idx = [i for i, p in enumerate(passages) if p["type"] == TYPE_ASSISTANCE]
    if not idx:
        return []
    nutri_par_nom = {(n["nom"], n["km"]): n for n in nutrition}
    sacs = []
    for k, i in enumerate(idx):
        fin = idx[k + 1] if k + 1 < len(idx) else len(passages) - 1
        p = passages[i]
        troncons = passages[i + 1:fin + 1]
        duree = sum(t["troncon_s"] for t in troncons)
        gluc = sum(nutri_par_nom.get((t["nom"], t["km"]), {}).get("glucides_g", 0) for t in troncons)
        eau = sum(nutri_par_nom.get((t["nom"], t["km"]), {}).get("eau_ml", 0) for t in troncons)
        ravitos = [t["nom"] for t in troncons[:-1] if t["type"] == "Ravitaillement"]
        heures = {code: sc["passages"][i]["passage"] for code, sc in scenarios.items()}
        # nuit pendant le tronçon, en scénario prudent (le plus tard)
        prud = scenarios.get("prudent", real)["passages"]
        nuit = any(_nuit(prud[j]["passage"]) for j in range(i, fin + 1))
        gels = int(round(gluc * 0.7 / GEL_G))
        barres = int(round(gluc * 0.3 / BARRE_G))
        portions = " et ".join(x for x in (f"{gels} gel(s)" if gels else "", f"{barres} barre(s)" if barres else "") if x)
        compo = []
        if mes_produits:
            from noyau.nutrition.tolerances import composer
            compo = composer(gluc, mes_produits)
        if compo:
            texte = " + ".join(f"{n} × {p_['nom']}" for p_, n in compo)
            lignes = [f"Nourriture pour {rbk.texte_duree(duree)} : environ {gluc} g de glucides, avec tes produits : "
                      f"{texte}."]
        else:
            lignes = [f"Nourriture pour {rbk.texte_duree(duree)} : environ {gluc} g de glucides"
                      + (f", soit {portions}" if portions else "") + " — ou tes produits testés à l'entraînement."]
        if ravitos:
            lignes.append(f"Eau : {eau} ml sur le tronçon ; remplis tes flasques à {', '.join(ravitos)}.")
        else:
            lignes.append(f"Eau : {eau} ml sur le tronçon, sans ravitaillement officiel avant le point suivant : "
                          "pars avec tes flasques pleines (et une réserve).")
        if nuit:
            lignes.append("Frontale chargée + piles ou batterie de rechange : tu cours de nuit sur ce tronçon "
                          "(au moins en scénario prudent).")
        if nuit or temperature_c < 8:
            raison = "la nuit, il fait froid à l'arrêt" if nuit else f"{temperature_c:g} °C annoncés"
            lignes.append(f"Couche chaude et veste imperméable sèches ({raison}).")
        if duree >= 3 * 3600:
            lignes.append("Tee-shirt et chaussettes de rechange, crème anti-frottements.")
        lignes.append("Boisson ou repas salé pris sur place (soupe, compote, boisson de récupération).")
        sacs.append({"nom": p["nom"], "km": p["km"], "heures": heures,
                     "jusqua": passages[fin]["nom"], "duree_s": duree, "glucides_g": gluc, "eau_ml": eau,
                     "gels": gels, "barres": barres, "ravitos": ravitos, "nuit": nuit, "lignes": lignes,
                     "produits": [(p_["nom"], n) for p_, n in compo]})
    return sacs


def lignes_bracelet(scenarios):
    """Une ligne par point pour le bracelet : km, nom, heures réaliste et prudente,
    barrière, D+ / D− jusqu'au point suivant."""
    real = scenarios.get("realiste")
    if not real:
        return []
    prud = scenarios.get("prudent", real)["passages"]
    amb = scenarios.get("ambitieux", real)["passages"]
    pas = real["passages"]
    out = []
    for i, p in enumerate(pas):
        suivant = pas[i + 1] if i + 1 < len(pas) else None
        out.append({"km": p["km"], "nom": p["nom"], "type": p["type"],
                    "ambitieux": rbk.texte_heure(amb[i]["passage"]),
                    "realiste": rbk.texte_heure(p["passage"]),
                    "prudent": rbk.texte_heure(prud[i]["passage"]),
                    "barriere": p["barriere_txt"] or "",
                    "suite_dplus": suivant["troncon_dplus"] if suivant else None,
                    "suite_dmoins": suivant["troncon_dmoins"] if suivant else None,
                    "suite_km": suivant["troncon_km"] if suivant else None})
    return out
