"""
Recopie dans la page Claude les données de la nutrition de course du
logiciel (barèmes du Nutri-Score, ingrédients, recettes de départ,
produits génériques), pour que la page calcule exactement comme lui.

    python page_claude/generer_donnees_nutrition.py

Le test tests/test_page_nutrition.py vérifie que la page est à jour.
"""

import json
import re
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

from noyau.nutrition import nutriscore as ns, catalogue as cat          # noqa: E402
from noyau.nutrition.ingredients import INGREDIENTS, MODELES, LIQUIDES, SODIUM_PAR_G_SEL  # noqa: E402

PAGE = RACINE / "page_claude" / "trail_hub_center.html"
DEBUT, FIN = "/*NUTRITION_DEBUT*/", "/*NUTRITION_FIN*/"


def donnees():
    return {
        "aliment": ns.ALIMENT, "boisson": ns.BOISSON, "fvl": [list(x) for x in ns.FVL],
        "edulcorants": ns.EDULCORANTS_POINTS, "couleurs": ns.COULEURS, "kj": ns.KJ_PAR_KCAL,
        "sodiumParGSel": SODIUM_PAR_G_SEL, "ingredients": INGREDIENTS, "liquides": sorted(LIQUIDES),
        "modeles": [{"nom": m[0], "categorie": m[1], "portions": m[2], "ingredients": [{"code": c, "g": g} for c, g in m[3]],
                     "preparation": m[4], "conservation": m[5]} for m in MODELES],
        "generiques": [{k: v for k, v in g.items()} for g in cat.GENERIQUES],
    }


def bloc():
    return DEBUT + json.dumps(donnees(), ensure_ascii=False, separators=(",", ":")) + FIN


def mettre_a_jour():
    texte = PAGE.read_text(encoding="utf-8")
    motif = re.compile(re.escape(DEBUT) + r".*?" + re.escape(FIN), re.S)
    if not motif.search(texte):
        raise SystemExit("Repères NUTRITION_DEBUT / NUTRITION_FIN absents de la page.")
    PAGE.write_text(motif.sub(lambda _m: bloc(), texte), encoding="utf-8")


if __name__ == "__main__":
    mettre_a_jour()
    print("Page Claude mise à jour.")
