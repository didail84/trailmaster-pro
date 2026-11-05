"""
Catalogue des produits de course (gels, barres, boissons, pâtes de fruits,
salé) : produits GÉNÉRIQUES livrés avec le logiciel + tes produits (base),
et les calculs communs à un produit (valeurs par portion, Nutri-Score,
prix pour 60 g de glucides).

Les génériques donnent des valeurs typiques d'un produit de ce genre,
sans marque : pour un produit précis, ajoute-le avec son étiquette ou
cherche-le par son code-barres sur Open Food Facts.
"""

from noyau.nutrition import nutriscore
from noyau.nutrition.ingredients import SODIUM_PAR_G_SEL

CATEGORIES = ("Gel", "Barre", "Boisson", "Pâte de fruits", "Compote", "Fruit", "Salé", "Électrolytes", "Autre")

CHAMPS_PRODUIT = (
    "nom", "marque", "categorie", "type_nutriscore", "portion", "unite_portion",
    "energie_kcal", "glucides_g", "sucres_g", "fibres_g", "proteines_g", "lipides_g", "ags_g", "sel_g",
    "fruits_legumes_pct", "edulcorants", "cafeine_mg", "glucose_fructose", "prix_portion",
    "code_barre", "nutriscore_officiel", "source", "recette_id", "favori", "notes",
)
# Valeurs pour 100 g (ou 100 ml pour une boisson telle que bue) ; caféine par portion.
NUTRIMENTS_100 = ("energie_kcal", "glucides_g", "sucres_g", "fibres_g", "proteines_g", "lipides_g", "ags_g", "sel_g")


def _g(code, nom, categorie, portion, kcal, gluc, sucres, fibres, prot, lip, ags, sel, unite="g",
       type_ns="aliment", fvl=0, cafeine=0, gf=None, notes=""):
    return {"id": f"g:{code}", "nom": nom, "marque": "Générique", "categorie": categorie, "type_nutriscore": type_ns,
            "portion": portion, "unite_portion": unite, "energie_kcal": kcal, "glucides_g": gluc, "sucres_g": sucres,
            "fibres_g": fibres, "proteines_g": prot, "lipides_g": lip, "ags_g": ags, "sel_g": sel,
            "fruits_legumes_pct": fvl, "edulcorants": 0, "cafeine_mg": cafeine, "glucose_fructose": gf,
            "prix_portion": None, "code_barre": None, "nutriscore_officiel": None, "source": "Générique",
            "recette_id": None, "favori": 0, "notes": notes, "generique": True}


GENERIQUES = (
    _g("gel", "Gel énergétique classique", "Gel", 35, 280, 71, 30, 0, 0, 0, 0, 0.3, gf="surtout glucose"),
    _g("gel_cafeine", "Gel énergétique caféiné", "Gel", 35, 280, 71, 30, 0, 0, 0, 0, 0.3, cafeine=75,
       gf="surtout glucose"),
    _g("gel_2_1", "Gel haute dose 2:1 (40 g)", "Gel", 60, 270, 66, 25, 0, 0, 0, 0, 0.2, gf="1:0,5"),
    _g("barre", "Barre énergétique céréales-fruits", "Barre", 40, 380, 65, 30, 4, 6, 8, 2, 0.3),
    _g("pate_fruits", "Pâte de fruits d'effort", "Pâte de fruits", 25, 300, 75, 65, 1, 0, 0, 0, 0.05),
    _g("compote", "Compote de fruits en gourde", "Compote", 90, 70, 15, 13, 1.5, 0.3, 0.2, 0.05, 0.0, fvl=95),
    _g("boisson", "Boisson d'effort 6 % (préparée)", "Boisson", 500, 24, 6, 4, 0, 0, 0, 0, 0.1, unite="ml",
       type_ns="boisson"),
    _g("boisson_haute", "Boisson d'effort haute dose 9 % (préparée)", "Boisson", 500, 36, 9, 3, 0, 0, 0, 0, 0.12,
       unite="ml", type_ns="boisson", gf="1:0,5"),
    _g("pastille", "Pastille d'électrolytes (250 mg de sodium)", "Électrolytes", 4.5, 0, 0, 0, 0, 0, 0, 0, 14.1,
       type_ns="non_applicable", notes="À dissoudre dans un bidon d'eau."),
    _g("banane", "Banane", "Fruit", 120, 90, 20, 15, 2.7, 1.2, 0.3, 0.1, 0.0, fvl=100),
    _g("dattes", "Dattes (2 grosses)", "Fruit", 25, 282, 64, 63, 8, 2.5, 0.4, 0.03, 0.01, fvl=100),
    _g("pain_epices", "Pain d'épices", "Barre", 30, 330, 73, 40, 2.5, 4, 1.5, 0.3, 0.4),
    _g("chips", "Chips salées (petit sachet)", "Salé", 30, 540, 50, 0.5, 4.5, 6.5, 34, 3, 1.3),
    _g("fromage", "Fromage à pâte dure (comté…)", "Salé", 30, 410, 0, 0, 0, 28, 33, 20, 0.8, type_ns="fromage"),
)
_GEN_PAR_ID = {p["id"]: p for p in GENERIQUES}


def generique(id_):
    return dict(_GEN_PAR_ID[id_]) if id_ in _GEN_PAR_ID else None


def par_portion(p, champ):
    v, portion = p.get(champ), p.get("portion")
    if v is None or not portion:
        return None
    return v * portion / 100


def sodium_mg_portion(p):
    s = par_portion(p, "sel_g")
    return None if s is None else s * SODIUM_PAR_G_SEL


def nutriscore_de(p):
    """{lettre, …} calculé ; « officiel » ajouté quand l'étiquette ou Open Food Facts le donne."""
    r = nutriscore.calculer({k: p.get(k) for k in NUTRIMENTS_100 + ("fruits_legumes_pct", "edulcorants")},
                            p.get("type_nutriscore") or "aliment")
    off = (p.get("nutriscore_officiel") or "").strip().upper()
    if off in ("A", "B", "C", "D", "E"):
        r = dict(r)
        r["officiel"] = off
    return r


def prix_pour_60g(p):
    """Prix pour 60 g de glucides (≈ 1 h d'effort long), ou None."""
    g = par_portion(p, "glucides_g")
    if not p.get("prix_portion") or not g:
        return None
    return p["prix_portion"] / g * 60


def libelle_portion(p):
    portion = p.get("portion")
    if not portion:
        return "—"
    return f"{portion:g} {p.get('unite_portion') or 'g'}".replace(".", ",")
