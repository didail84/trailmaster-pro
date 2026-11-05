"""
Bilan de tes essais de tolérance (étape 3.3) : verdict par produit, apport
de glucides par heure le plus haut bien toléré, entraînement du ventre, et
menu heure par heure construit avec TES produits validés.
"""

from noyau.nutrition.catalogue import par_portion, sodium_mg_portion
from noyau.course import ravitaillement as rav

VERDICTS = (
    ("valide", "Validé", "#2E7D32"),
    ("a_confirmer", "À confirmer", "#1976D2"),
    ("prudence", "Avec prudence", "#E65100"),
    ("eviter", "À éviter", "#C62828"),
    ("jamais", "Jamais testé", "#757575"),
)
LIBELLE_VERDICT = {c: l for c, l, _ in VERDICTS}
COULEUR_VERDICT = {c: k for c, _, k in VERDICTS}


def verdict(essais_produit):
    """essais_produit : du plus récent au plus ancien. Renvoie {code, libelle, nb, detail}."""
    nb = len(essais_produit)
    if not nb:
        return {"code": "jamais", "libelle": LIBELLE_VERDICT["jamais"], "nb": 0,
                "detail": "Aucun essai noté : teste-le d'abord à l'entraînement."}
    recents = essais_produit[:3]
    graves = [e for e in recents if e["ressenti"] in ("gene", "arret")]
    legers = [e for e in recents if e["ressenti"] == "leger"]
    bons = [e for e in essais_produit if e["ressenti"] == "bien"]
    longs = [e for e in bons if e.get("contexte") in ("Sortie longue", "Course") or (e.get("duree_min") or 0) >= 120]
    if any(e["ressenti"] == "arret" for e in recents) or len(graves) >= 2 or (graves and not bons):
        code, detail = "eviter", "Gêne digestive lors de tes derniers essais : à garder pour l'entraînement, ou à écarter."
    elif graves or len(legers) >= 2:
        code, detail = "prudence", "Toléré par moments seulement : essaie une plus petite quantité, plus d'eau avec."
    elif len(bons) >= 2 and longs:
        code, detail = "valide", f"{len(bons)} essais sans souci, dont au moins un long : prêt pour la course."
    else:
        code, detail = "a_confirmer", ("Bien passé, mais à refaire au moins une fois sur une sortie longue "
                                       "(2 h ou plus) avant une course.")
    return {"code": code, "libelle": LIBELLE_VERDICT[code], "nb": nb, "detail": detail}


def bilan(produits, essais):
    """{produit_id: verdict} pour tes produits, + apport maximal bien toléré."""
    par_produit = {}
    for e in essais:
        par_produit.setdefault(e["produit_id"], []).append(e)
    verdicts = {p["id"]: verdict(par_produit.get(p["id"], [])) for p in produits}
    bien = [e["glucides_g_h"] for e in essais if e["ressenti"] == "bien" and e.get("glucides_g_h")]
    gene = [e["glucides_g_h"] for e in essais if e["ressenti"] in ("gene", "arret") and e.get("glucides_g_h")]
    return {"verdicts": verdicts, "max_g_h_tolere": max(bien) if bien else None,
            "min_g_h_gene": min(gene) if gene else None}


def entrainement_du_ventre(max_tolere, cible):
    """Conseil pour monter progressivement l'apport de glucides par heure."""
    if not cible:
        return None
    if max_tolere is None:
        return (f"Ta course demande environ {cible} g de glucides par heure. Note tes prochains essais avec les "
                "glucides pris par heure : on verra jusqu'où ton ventre suit.")
    if max_tolere >= cible:
        return f"Tu as déjà bien toléré {max_tolere:g} g/h : la cible de {cible} g/h est à ta portée."
    semaines = int(-(-(cible - max_tolere) // 10))
    return (f"Ton plus haut apport bien toléré est {max_tolere:g} g/h pour une cible de {cible} g/h. Monte de 10 g/h "
            f"par semaine sur une sortie longue : environ {semaines} semaine{'s' if semaines > 1 else ''} "
            "d'entraînement du ventre.")


def menu_avec_mes_produits(plan, produits, verdicts=None):
    """Menu heure par heure (comme ravitaillement.menu_exemple) avec tes produits favoris ou validés.
    Une boisson de tes produits couvre la moitié de l'eau ; gels, barres et fruits complètent.
    Renvoie [{heure, items: [(produit, quantité)], glucides_g, sodium_mg, eau_ml, pastilles}] ou [] si
    tu n'as aucun produit utilisable."""
    if not plan:
        return []
    verdicts = verdicts or {}
    def utilisable(p):
        v = verdicts.get(p["id"], {}).get("code")
        return v != "eviter" and (p.get("favori") or v == "valide") and par_portion(p, "glucides_g")
    choix = [p for p in produits if utilisable(p)]
    boissons = [p for p in choix if p.get("categorie") == "Boisson"]
    solides = [p for p in choix if p.get("categorie") not in ("Boisson", "Électrolytes")]
    if not solides and not boissons:
        return []
    boisson = boissons[0] if boissons else None
    menu, i = [], 0
    for h in plan["heures"]:
        cible = h["glucides_g"]
        items, gluc, sodium = [], 0.0, 0.0
        eau = h["eau_ml"]
        if boisson and cible:
            ml = int(round(h["eau_ml"] * 0.5 / 50.0) * 50)
            n = ml / boisson["portion"] if boisson.get("portion") else 0
            if n > 0:
                items.append((boisson, round(n, 2)))
                gluc += par_portion(boisson, "glucides_g") * n
                sodium += (sodium_mg_portion(boisson) or 0) * n
                eau -= ml
        essais = 0
        while solides and cible - gluc >= 10 and essais < 12 and len(items) < 4:
            p = solides[i % len(solides)]
            i += 1
            essais += 1
            g = par_portion(p, "glucides_g")
            if g <= (cible - gluc) * 1.35 or not items:
                items.append((p, 1))
                gluc += g
                sodium += sodium_mg_portion(p) or 0
        if solides and cible - gluc >= 10:
            # il manque une petite quantité : une demi-portion du produit le plus léger
            p = min(solides, key=lambda x: par_portion(x, "glucides_g"))
            items.append((p, 0.5))
            gluc += par_portion(p, "glucides_g") / 2
            sodium += (sodium_mg_portion(p) or 0) / 2
        pastilles = max(0, int(round((h["sodium_mg"] - sodium) / rav.PASTILLE_SEL_MG))) if h["duree_h"] >= 0.5 else 0
        menu.append({"heure": h["heure"], "items": items, "glucides_g": int(round(gluc)), "cible_g": cible,
                     "sodium_mg": int(round(sodium)), "sodium_cible_mg": h["sodium_mg"],
                     "eau_ml": max(0, int(eau)), "pastilles": pastilles})
    return menu


def texte_ligne_menu(ligne):
    parts, cumul, ordre = [], {}, []
    for p, n in ligne["items"]:
        if p["id"] not in cumul:
            ordre.append(p)
        cumul[p["id"]] = cumul.get(p["id"], 0) + n
    for p in ordre:
        n = cumul[p["id"]]
        if p.get("categorie") == "Boisson":
            parts.append(f"{int(round(n * p['portion']))} ml de {p['nom']}")
        else:
            parts.append(f"{n:g} × {p['nom']}".replace(".", ","))
    if ligne["eau_ml"]:
        parts.append(f"{ligne['eau_ml']} ml d'eau")
    if ligne["pastilles"]:
        parts.append(f"{ligne['pastilles']} pastille{'s' if ligne['pastilles'] > 1 else ''} d'électrolytes")
    return " + ".join(parts) if parts else "eau à volonté"


def produits_pour_la_course(produits, verdicts):
    """Tes produits favoris ou validés, sans ceux à éviter, qui apportent des glucides (hors boissons)."""
    return [p for p in produits
            if verdicts.get(p["id"], {}).get("code") != "eviter"
            and (p.get("favori") or verdicts.get(p["id"], {}).get("code") == "valide")
            and p.get("categorie") not in ("Boisson", "Électrolytes") and par_portion(p, "glucides_g")]


def composer(glucides_g, produits):
    """Combinaison de tes produits qui atteint `glucides_g` (à une demi-portion près), en les alternant.
    Renvoie [(produit, nombre)] du plus utilisé au moins utilisé."""
    utiles = [p for p in produits if (par_portion(p, "glucides_g") or 0) > 0]
    if not utiles or glucides_g <= 0:
        return []
    compte, total, i = {}, 0.0, 0
    while total < glucides_g - 0.5 * min(par_portion(p, "glucides_g") for p in utiles) and i < 200:
        p = utiles[i % len(utiles)]
        compte[p["id"]] = compte.get(p["id"], 0) + 1
        total += par_portion(p, "glucides_g")
        i += 1
    par_id = {p["id"]: p for p in utiles}
    return sorted(((par_id[k], n) for k, n in compte.items()), key=lambda x: -x[1])


def produits_course_de(athlete_id):
    """Raccourci pour la Stratégie de course : tes produits favoris ou validés, lus dans la base."""
    if athlete_id is None:
        return []
    from noyau.donnees import nutrition_course as dnut
    ps = dnut.produits(athlete_id)
    return produits_pour_la_course(ps, bilan(ps, dnut.essais(athlete_id))["verdicts"])
