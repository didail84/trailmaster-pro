"""
Calcul d'une recette « fait maison » (barre, gel, boisson) : valeurs par
portion et pour 100 g, glucides par portion, sodium, rapport
glucose:fructose, concentration d'une boisson, Nutri-Score, coût.

Une recette est une liste d'ingrédients :
    {"code": "miel", "g": 100}                         ingrédient de la base
    {"code": "miel", "g": 100, "valeurs": {...}}        valeurs corrigées pour 100 g
    {"nom": "Gel de mon magasin", "g": 40, "valeurs": {...}}   ingrédient libre
avec, au choix, "prix_kg" (€/kg) pour le coût.
"""

from noyau.nutrition.ingredients import INGREDIENTS, LIQUIDES, SODIUM_PAR_G_SEL
from noyau.nutrition import nutriscore

NUTRIMENTS = ("kcal", "glucides_g", "sucres_g", "fibres_g", "proteines_g", "lipides_g", "ags_g", "sel_g",
              "glucose_g", "fructose_g", "cafeine_mg")


def valeurs_ingredient(item):
    """Valeurs pour 100 g d'une ligne de recette (base corrigée par l'étiquette)."""
    base = dict(INGREDIENTS.get(item.get("code"), {}))
    base.update({k: v for k, v in (item.get("valeurs") or {}).items() if v is not None})
    return base


def nom_ingredient(item):
    return item.get("nom") or INGREDIENTS.get(item.get("code"), {}).get("nom") or "Ingrédient"


def est_liquide(item):
    return item.get("code") in LIQUIDES or bool(item.get("liquide"))


def calculer(ingredients, nb_portions=1, categorie="Barre", perte_cuisson_pct=0):
    """Renvoie un dict : total_g, portion_g, par_portion{…}, pour_100g{…}, sodium_mg_portion,
    ratio_glucose_fructose (texte), part_fructose, concentration_g_l (boisson), cout_portion,
    nutriscore{…}, avertissements[]. None si la recette est vide."""
    lignes = [i for i in ingredients or [] if (i.get("g") or 0) > 0]
    if not lignes:
        return None
    nb_portions = max(1.0, float(nb_portions or 1))
    total = {k: 0.0 for k in NUTRIMENTS}
    masse = sum(i["g"] for i in lignes)
    masse_finale = masse * (1 - (perte_cuisson_pct or 0) / 100)
    masse_fvl = 0.0
    liquide = 0.0
    cout, cout_connu = 0.0, True
    for i in lignes:
        v = valeurs_ingredient(i)
        for k in NUTRIMENTS:
            total[k] += (v.get(k) or 0) * i["g"] / 100
        if v.get("fvl"):
            masse_fvl += i["g"]
        if est_liquide(i):
            liquide += i["g"]
        if i.get("prix_kg") is None:
            cout_connu = False
        else:
            cout += i["prix_kg"] * i["g"] / 1000
    boisson = categorie in ("Boisson", "Récupération")
    portion_g = masse_finale / nb_portions
    par_portion = {k: total[k] / nb_portions for k in NUTRIMENTS}
    pour_100 = {k: total[k] / masse_finale * 100 for k in NUTRIMENTS} if masse_finale else {}
    sodium_portion = par_portion["sel_g"] * SODIUM_PAR_G_SEL
    gl, fr = total["glucose_g"], total["fructose_g"]
    ratio = None
    if gl + fr > 0:
        ratio = "glucose seulement" if fr < 0.05 * (gl + fr) else (
            "fructose seulement" if gl < 0.05 * (gl + fr) else f"1:{fr / gl:.1f}".replace(".", ","))
    part_fructose = fr / (gl + fr) if gl + fr else None
    volume_l = masse_finale / 1000 if boisson else None
    concentration = total["glucides_g"] / volume_l if boisson and volume_l else None

    avert = []
    g_portion = par_portion["glucides_g"]
    if categorie == "Gel" and g_portion < 15:
        avert.append(f"Gel léger : {g_portion:.0f} g de glucides par portion (un gel du commerce en apporte 20 à 30 g).")
    if categorie == "Gel" and portion_g and g_portion / portion_g < 0.45:
        avert.append("Gel très liquide (moins de 45 % de glucides) : il coulera de la flasque, réduis l'eau.")
    if boisson and concentration is not None:
        if concentration > 80 and _part_maltodextrine(lignes) > 0.5:
            avert.append(f"{concentration:.0f} g de glucides par litre : boisson concentrée, mais à base de maltodextrine, "
                         "souvent mieux tolérée qu'un sirop au même dosage. À tester à l'entraînement.")
        elif concentration > 80:
            avert.append(f"{concentration:.0f} g de glucides par litre : boisson concentrée (hypertonique), elle hydrate moins "
                         "vite et peut gêner l'estomac ; garde de l'eau pure à côté.")
        elif concentration < 30 and categorie == "Boisson":
            avert.append(f"Seulement {concentration:.0f} g de glucides par litre : boisson surtout hydratante.")
    if part_fructose is not None and part_fructose > 0.6 and total["glucides_g"] >= 20:
        avert.append("Beaucoup de fructose (plus de 60 % des sucres) : risque de ballonnements à fort débit ; "
                     "équilibre avec du glucose ou de la maltodextrine.")
    if categorie in ("Boisson", "Gel") and sodium_portion < 50 and g_portion >= 15:
        avert.append("Presque pas de sodium : ajoute une pincée de sel (environ 0,5 g par 500 ml) si tu transpires.")
    if par_portion["fibres_g"] > 4 and categorie != "Récupération":
        avert.append(f"{par_portion['fibres_g']:.0f} g de fibres par portion : à manger plutôt au calme ou avant l'effort.")
    if par_portion["cafeine_mg"] >= 20:
        avert.append(f"Environ {par_portion['cafeine_mg']:.0f} mg de caféine par portion.")

    type_ns = "boisson" if boisson else "aliment"
    ns_entree = {"energie_kcal": pour_100.get("kcal"), "sucres_g": pour_100.get("sucres_g"),
                 "ags_g": pour_100.get("ags_g"), "sel_g": pour_100.get("sel_g"),
                 "fibres_g": pour_100.get("fibres_g"), "proteines_g": pour_100.get("proteines_g"),
                 "fruits_legumes_pct": masse_fvl / masse * 100 if masse else 0}
    return {
        "total_g": round(masse_finale), "nb_portions": nb_portions, "portion_g": round(portion_g, 1),
        "par_portion": {k: round(v, 1) for k, v in par_portion.items()},
        "pour_100g": {k: round(v, 2) for k, v in pour_100.items()},
        "total": {k: round(v, 1) for k, v in total.items()},
        "sodium_mg_portion": round(sodium_portion),
        "ratio_glucose_fructose": ratio, "part_fructose": None if part_fructose is None else round(part_fructose, 2),
        "concentration_g_l": None if concentration is None else round(concentration),
        "fruits_legumes_pct": round(ns_entree["fruits_legumes_pct"]),
        "cout_total": round(cout, 2) if cout_connu else None,
        "cout_portion": round(cout / nb_portions, 2) if cout_connu else None,
        "nutriscore": nutriscore.calculer(ns_entree, type_ns), "type_nutriscore": type_ns,
        "avertissements": avert,
    }


def _part_maltodextrine(lignes):
    gl = sum((valeurs_ingredient(i).get("glucides_g") or 0) * i["g"] / 100 for i in lignes)
    md = sum((valeurs_ingredient(i).get("glucides_g") or 0) * i["g"] / 100
             for i in lignes if i.get("code") in ("maltodextrine", "sirop_riz"))
    return md / gl if gl else 0


def ajuster_glucides(ingredients, nb_portions, cible_g_portion, code_sucre="maltodextrine", categorie="Barre"):
    """Quantité de `code_sucre` à ajouter (en g, pour toute la recette) pour atteindre
    `cible_g_portion` g de glucides par portion. 0 si la cible est déjà atteinte."""
    r = calculer(ingredients, nb_portions, categorie)
    actuel = r["par_portion"]["glucides_g"] if r else 0
    manque = max(0.0, cible_g_portion - actuel) * max(1.0, nb_portions)
    teneur = INGREDIENTS[code_sucre]["glucides_g"] / 100
    return round(manque / teneur) if teneur else 0


def produit_depuis_recette(nom, categorie, calcul):
    """Champs d'un produit du catalogue (table produits_nutrition) pour une recette calculée."""
    p = calcul["pour_100g"]
    cat_produit = {"Gel": "Gel", "Barre": "Barre", "Boisson": "Boisson", "Boule ou pâte de fruits": "Pâte de fruits",
                   "Salé": "Salé", "Récupération": "Boisson"}.get(categorie, "Autre")
    return {
        "nom": nom, "marque": "Fait maison", "categorie": cat_produit,
        "type_nutriscore": calcul["type_nutriscore"],
        "portion": calcul["portion_g"], "unite_portion": "ml" if calcul["type_nutriscore"] == "boisson" else "g",
        "energie_kcal": p.get("kcal"), "glucides_g": p.get("glucides_g"), "sucres_g": p.get("sucres_g"),
        "fibres_g": p.get("fibres_g"), "proteines_g": p.get("proteines_g"), "lipides_g": p.get("lipides_g"),
        "ags_g": p.get("ags_g"), "sel_g": p.get("sel_g"),
        "fruits_legumes_pct": calcul["fruits_legumes_pct"], "edulcorants": 0,
        "cafeine_mg": calcul["par_portion"].get("cafeine_mg") or 0,
        "glucose_fructose": calcul["ratio_glucose_fructose"],
        "prix_portion": calcul["cout_portion"], "source": "Fait maison",
    }
