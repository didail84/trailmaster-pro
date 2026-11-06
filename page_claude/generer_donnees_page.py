"""
Recopie dans la page Claude les données du logiciel dont elle a besoin pour
calculer exactement comme lui :
  - nutrition de course : barèmes du Nutri-Score, ingrédients, recettes de
    départ, produits génériques ;
  - matériel obligatoire : catalogue des équipements et caractéristiques ;
  - fractionné : bibliothèque des séances types.

    python page_claude/generer_donnees_page.py

Le test tests/test_page_donnees.py vérifie que la page est à jour.
"""

import json
import re
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

from noyau.nutrition import nutriscore as ns, catalogue as cat          # noqa: E402
from noyau.nutrition.ingredients import INGREDIENTS, MODELES, LIQUIDES, SODIUM_PAR_G_SEL  # noqa: E402
from noyau.materiel import equipements as meq, comparaison as mcmp                      # noqa: E402
from noyau.entrainement import fractionne as efr                                         # noqa: E402

PAGE = RACINE / "page_claude" / "trail_hub_center.html"
REPERES = {"NUTRITION": None, "MATERIEL": None, "FRACTIONNE": None}


def donnees():
    return {
        "aliment": ns.ALIMENT, "boisson": ns.BOISSON, "fvl": [list(x) for x in ns.FVL],
        "edulcorants": ns.EDULCORANTS_POINTS, "couleurs": ns.COULEURS, "kj": ns.KJ_PAR_KCAL,
        "sodiumParGSel": SODIUM_PAR_G_SEL, "ingredients": INGREDIENTS, "liquides": sorted(LIQUIDES),
        "modeles": [{"nom": m[0], "categorie": m[1], "portions": m[2], "ingredients": [{"code": c, "g": g} for c, g in m[3]],
                     "preparation": m[4], "conservation": m[5]} for m in MODELES],
        "generiques": [{k: v for k, v in g.items()} for g in cat.GENERIQUES],
    }


def donnees_materiel():
    return {
        "equipements": {c: {"nom": e["nom"], "famille": e["famille"], "carac": e["carac"]}
                        for c, e in meq.EQUIPEMENTS.items()},
        "caracteristiques": {k: list(v) for k, v in meq.CARACTERISTIQUES.items()},
        "niveaux": [list(n) for n in meq.NIVEAUX], "aControler": sorted(mcmp.A_CONTROLER),
        "controleJours": mcmp.CONTROLE_JOURS,
    }


def donnees_fractionne():
    return {"bibliotheque": list(efr.BIBLIOTHEQUE), "formats": [list(x) for x in efr.FORMATS],
            "terrains": [list(x) for x in efr.TERRAINS]}


def bloc(nom):
    contenu = {"NUTRITION": donnees, "MATERIEL": donnees_materiel, "FRACTIONNE": donnees_fractionne}[nom]()
    return f"/*{nom}_DEBUT*/" + json.dumps(contenu, ensure_ascii=False, separators=(",", ":")) + f"/*{nom}_FIN*/"


def mettre_a_jour():
    texte = PAGE.read_text(encoding="utf-8")
    for nom in REPERES:
        motif = re.compile(re.escape(f"/*{nom}_DEBUT*/") + r".*?" + re.escape(f"/*{nom}_FIN*/"), re.S)
        if not motif.search(texte):
            raise SystemExit(f"Repères {nom}_DEBUT / {nom}_FIN absents de la page.")
        texte = motif.sub(lambda _m, n=nom: bloc(n), texte)
    PAGE.write_text(texte, encoding="utf-8")


if __name__ == "__main__":
    mettre_a_jour()
    print("Page Claude mise à jour.")
