"""
Nutri-Score (lettres A à E) selon l'algorithme révisé appliqué en France
depuis 2024 (projet d'arrêté notifié par la France à la Commission
européenne, base TRIS : tableaux des aliments généraux et des boissons,
seuils de classement A à E).

Le Nutri-Score note un produit pour l'alimentation de TOUS LES JOURS, par
100 g ou 100 ml. Un gel ou une pâte de fruits, faits pour l'effort, sont
presque toujours D ou E (ce sont des sucres concentrés) : c'est normal et
ça ne dit rien de leur utilité pendant une course. Le comparatif de
produits l'affiche à côté des critères d'effort (glucides par portion,
sodium, prix, tolérance), jamais à leur place.

Non calculés ici : matières grasses, fruits à coque et graines purs
(tableau particulier) et produits non concernés (pastilles d'électrolytes,
compléments) : la fonction renvoie alors None avec la raison.
"""

KJ_PAR_KCAL = 4.184

# Chaque liste : bornes « strictement supérieur à » ; points = nombre de bornes dépassées.
ALIMENT = {
    "energie_kj": [335 * i for i in range(1, 11)],
    "ags_g": [float(i) for i in range(1, 11)],
    "sucres_g": [3.4, 6.8, 10, 14, 17, 20, 24, 27, 31, 34, 37, 41, 44, 48, 51],
    "sel_g": [round(0.2 * i, 1) for i in range(1, 21)],
    "fibres_g": [3.0, 4.1, 5.2, 6.3, 7.4],
    "proteines_g": [2.4, 4.8, 7.2, 9.6, 12, 14, 17],
}
BOISSON = {
    "energie_kj": [30, 90, 150, 210, 240, 270, 300, 330, 360, 390],
    "ags_g": [float(i) for i in range(1, 11)],
    "sucres_g": [0.5, 2, 3.5, 5, 6, 7, 8, 9, 10, 11],
    "sel_g": [round(0.2 * i, 1) for i in range(1, 21)],
    "fibres_g": [3.0, 4.1, 5.2, 6.3, 7.4],
    "proteines_g": [1.2, 1.5, 1.8, 2.1, 2.4, 2.7, 3.0],
}
# Fruits, légumes et légumineuses (%) : > 40 → 1 point, > 60 → 2, > 80 → 5 (aliments et boissons)
FVL = ((80, 5), (60, 2), (40, 1))
EDULCORANTS_POINTS = 4

TYPES = (
    ("aliment", "Aliment (gel, barre, compote…)"),
    ("boisson", "Boisson (telle que bue)"),
    ("fromage", "Fromage"),
    ("eau", "Eau"),
    ("matiere_grasse", "Matière grasse, fruits à coque, graines"),
    ("non_applicable", "Non concerné (pastille, complément)"),
)
COULEURS = {"A": "#038141", "B": "#85BB2F", "C": "#FECB02", "D": "#EE8100", "E": "#E63E11"}


def _points(valeur, bornes):
    if valeur is None:
        return 0
    return sum(1 for b in bornes if valeur > b + 1e-9)


def _points_fvl(pct):
    for borne, pts in FVL:
        if (pct or 0) > borne:
            return pts
    return 0


def _v(x, d=1):
    t = f"{x or 0:.{d}f}".replace(".", ",")
    return t[:-2] if t.endswith(",0") else t


def energie_kj(p):
    if p.get("energie_kj") is not None:
        return p["energie_kj"]
    if p.get("energie_kcal") is not None:
        return p["energie_kcal"] * KJ_PAR_KCAL
    return None


def calculer(p, type_produit="aliment"):
    """p : valeurs pour 100 g (ou 100 ml pour une boisson) : energie_kcal ou energie_kj,
    sucres_g, ags_g, sel_g, fibres_g, proteines_g, fruits_legumes_pct, edulcorants.
    Renvoie {lettre, score, negatif, positif, detail: [(composante, valeur, points)], note}
    ou {lettre: None, raison} si le Nutri-Score ne s'applique pas ou si des valeurs manquent."""
    if type_produit == "eau":
        return {"lettre": "A", "score": None, "detail": [], "note": "L'eau est toujours classée A."}
    if type_produit in ("matiere_grasse", "non_applicable"):
        return {"lettre": None, "raison": "Nutri-Score non calculé pour ce type de produit."}
    kj = energie_kj(p)
    manquants = [lib for cle, lib in (("sucres_g", "sucres"), ("ags_g", "acides gras saturés"), ("sel_g", "sel"))
                 if p.get(cle) is None]
    if kj is None:
        manquants.insert(0, "énergie")
    if manquants:
        return {"lettre": None, "raison": "Il manque : " + ", ".join(manquants) + "."}
    boisson = type_produit == "boisson"
    t = BOISSON if boisson else ALIMENT
    pe, pa, ps, pl = (_points(kj, t["energie_kj"]), _points(p.get("ags_g"), t["ags_g"]),
                      _points(p.get("sucres_g"), t["sucres_g"]), _points(p.get("sel_g"), t["sel_g"]))
    pedul = EDULCORANTS_POINTS if boisson and p.get("edulcorants") else 0
    negatif = pe + pa + ps + pl + pedul
    pf, pp, pv = (_points(p.get("fibres_g"), t["fibres_g"]), _points(p.get("proteines_g"), t["proteines_g"]),
                  _points_fvl(p.get("fruits_legumes_pct")))
    proteines_comptees = boisson or type_produit == "fromage" or negatif < 11
    positif = pf + pv + (pp if proteines_comptees else 0)
    score = negatif - positif
    if boisson:
        lettre = "B" if score <= 2 else "C" if score <= 6 else "D" if score <= 9 else "E"
    else:
        lettre = "A" if score <= 0 else "B" if score <= 2 else "C" if score <= 10 else "D" if score <= 18 else "E"
    detail = [("Énergie", f"{kj:.0f} kJ", pe), ("Acides gras saturés", f"{_v(p.get('ags_g'))} g", pa),
              ("Sucres", f"{_v(p.get('sucres_g'))} g", ps), ("Sel", f"{_v(p.get('sel_g'), 2)} g", pl)]
    if boisson:
        detail.append(("Édulcorants", "oui" if p.get("edulcorants") else "non", pedul))
    detail += [("Fibres", f"{_v(p.get('fibres_g'))} g", -pf),
               ("Protéines", f"{_v(p.get('proteines_g'))} g" + ("" if proteines_comptees else " (non comptées : N ≥ 11)"),
                -pp if proteines_comptees else 0),
               ("Fruits, légumes, légumineuses", f"{_v(p.get('fruits_legumes_pct'), 0)} %", -pv)]
    note = None
    if lettre in ("D", "E") and (p.get("sucres_g") or 0) >= 20:
        note = ("Classement normal pour un produit d'effort très sucré : le Nutri-Score juge l'alimentation de "
                "tous les jours, pas un ravitaillement de course.")
    return {"lettre": lettre, "score": score, "negatif": negatif, "positif": positif,
            "detail": [(c, v, pts) for c, v, pts in detail], "note": note}


def lettre(p, type_produit="aliment"):
    return calculer(p, type_produit).get("lettre")
