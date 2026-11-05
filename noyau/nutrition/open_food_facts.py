"""
Recherche d'un produit sur Open Food Facts (base collaborative ouverte,
licence ODbL) par son code-barres ou par son nom, pour remplir sa fiche
sans recopier l'étiquette. Connexion Internet nécessaire ; seule la
recherche demandée est envoyée (le code-barres ou les mots cherchés).

Les valeurs d'Open Food Facts sont saisies par des contributeurs : elles
sont proposées à vérifier avant d'enregistrer.
"""

import json
import re
import urllib.parse
import urllib.request

AGENT = "TrailHubCenter/3.3 (https://github.com/didail84/trailmaster-pro)"
URL_PRODUIT = "https://world.openfoodfacts.org/api/v2/product/{code}.json?fields={champs}"
URL_RECHERCHE = ("https://world.openfoodfacts.org/cgi/search.pl?search_terms={q}&search_simple=1&json=1"
                 "&page_size=12&fields={champs}")
CHAMPS = ("code,product_name,product_name_fr,brands,nutriments,nutriscore_grade,serving_quantity,serving_size,"
          "categories_tags,quantity")


class ErreurOpenFoodFacts(Exception):
    pass


def _nombre(v):
    try:
        return None if v in (None, "") else float(v)
    except (TypeError, ValueError):
        return None


def code_valide(code):
    return bool(re.fullmatch(r"\d{8,14}", (code or "").strip()))


def _categorie(tags, nom):
    t = " ".join(tags or []) + " " + (nom or "").lower()
    for mots, cat in ((("gel",), "Gel"), (("bar", "barre"), "Barre"), (("drink", "boisson", "beverage"), "Boisson"),
                      (("pate-de-fruit", "pâte de fruit", "fruit-paste"), "Pâte de fruits"),
                      (("compote", "puree"), "Compote"), (("electrolyte", "electrolytes"), "Électrolytes")):
        if any(m in t for m in mots):
            return cat
    return "Autre"


def produit_depuis_json(donnees):
    """Transforme la réponse d'Open Food Facts en champs de produit (produits_nutrition), ou None."""
    p = donnees.get("product") if "product" in donnees else donnees
    if not p:
        return None
    n = p.get("nutriments") or {}
    nom = (p.get("product_name_fr") or p.get("product_name") or "").strip()
    if not nom:
        return None
    tags = p.get("categories_tags") or []
    boisson = any("beverage" in t or "boisson" in t or "drink" in t for t in tags)
    kcal = _nombre(n.get("energy-kcal_100g"))
    if kcal is None and _nombre(n.get("energy-kj_100g")) is not None:
        kcal = round(_nombre(n.get("energy-kj_100g")) / 4.184, 1)
    if kcal is None and _nombre(n.get("energy_100g")) is not None:      # en kJ dans OFF
        kcal = round(_nombre(n.get("energy_100g")) / 4.184, 1)
    sel = _nombre(n.get("salt_100g"))
    if sel is None and _nombre(n.get("sodium_100g")) is not None:
        sel = round(_nombre(n.get("sodium_100g")) * 2.5, 3)
    cafeine = _nombre(n.get("caffeine_100g"))
    portion = _nombre(p.get("serving_quantity"))
    grade = (p.get("nutriscore_grade") or "").upper()
    return {
        "nom": nom, "marque": (p.get("brands") or "").split(",")[0].strip() or None,
        "categorie": _categorie(tags, nom), "type_nutriscore": "boisson" if boisson else "aliment",
        "portion": portion, "unite_portion": "ml" if boisson else "g",
        "energie_kcal": kcal, "glucides_g": _nombre(n.get("carbohydrates_100g")),
        "sucres_g": _nombre(n.get("sugars_100g")), "fibres_g": _nombre(n.get("fiber_100g")),
        "proteines_g": _nombre(n.get("proteins_100g")), "lipides_g": _nombre(n.get("fat_100g")),
        "ags_g": _nombre(n.get("saturated-fat_100g")), "sel_g": sel,
        "fruits_legumes_pct": _nombre(n.get("fruits-vegetables-legumes-estimate-from-ingredients_100g")) or 0,
        "cafeine_mg": round(cafeine * 1000 * portion / 100) if cafeine and portion else 0,
        "code_barre": p.get("code"), "nutriscore_officiel": grade if grade in ("A", "B", "C", "D", "E") else None,
        "source": "Open Food Facts", "notes": f"Portion indiquée : {p.get('serving_size')}" if p.get("serving_size") else "",
    }


def _lire(url, delai=12):
    req = urllib.request.Request(url, headers={"User-Agent": AGENT})
    try:
        with urllib.request.urlopen(req, timeout=delai) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception as e:
        raise ErreurOpenFoodFacts(f"Open Food Facts n'a pas répondu ({e.__class__.__name__}). "
                                  "Vérifie la connexion Internet et réessaie.") from e


def chercher_code(code):
    code = (code or "").strip()
    if not code_valide(code):
        raise ErreurOpenFoodFacts("Un code-barres compte 8 à 14 chiffres (sous le code-barres de l'emballage).")
    d = _lire(URL_PRODUIT.format(code=code, champs=CHAMPS))
    if d.get("status") in (0, "failure") or not d.get("product"):
        raise ErreurOpenFoodFacts("Ce code-barres n'est pas dans Open Food Facts : saisis l'étiquette à la main.")
    p = produit_depuis_json(d)
    if not p:
        raise ErreurOpenFoodFacts("La fiche Open Food Facts de ce produit est incomplète.")
    p["code_barre"] = p.get("code_barre") or code
    return p


def chercher_nom(mots):
    mots = (mots or "").strip()
    if len(mots) < 3:
        raise ErreurOpenFoodFacts("Tape au moins 3 lettres (marque et nom du produit).")
    d = _lire(URL_RECHERCHE.format(q=urllib.parse.quote(mots), champs=CHAMPS))
    res = [produit_depuis_json(p) for p in d.get("products") or []]
    return [r for r in res if r]
