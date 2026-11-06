"""
Recopie dans la page Claude les données du logiciel dont elle a besoin pour
calculer exactement comme lui :
  - nutrition de course : barèmes du Nutri-Score, ingrédients, recettes de
    départ, produits génériques ;
  - matériel obligatoire : catalogue des équipements et caractéristiques ;
  - fractionné : bibliothèque des séances types ;
  - calendrier : disciplines FFA, régions, statuts des inscriptions ;
  - annuaire : clubs, écoles, magasins et marques de la base livrée ;
  - club : catégories FFA, types de licence, pièces de santé, statuts, vacances
    scolaires et types de séances de l'agenda.

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
from noyau.club import categories as ccat, adhesions as cadh, agenda as cag              # noqa: E402

PAGE = RACINE / "page_claude" / "trail_hub_center.html"
REPERES = {"NUTRITION": None, "MATERIEL": None, "FRACTIONNE": None, "CLUB": None, "ANNUAIRE": None, "CALENDRIER": None}


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


def donnees_club():
    return {"categories": [list(c) for c in ccat._CATEGORIES], "moisDebut": ccat.MOIS_DEBUT_SAISON,
            "licences": [[c, l, list(u) if u else None] for c, l, u in ccat.TYPES_LICENCE],
            "sante": [list(x) for x in cadh.SANTE], "statuts": [list(x) for x in cadh.STATUTS],
            "types": [list(x) for x in cag.TYPES], "presences": [list(x) for x in cag.STATUTS_PRESENCE],
            "vacances": {s: {z: [list(v) for v in p] for z, p in zs.items()} for s, zs in cag.VACANCES.items()},
            "nomVacances": cag.NOM_VACANCES, "ponts": [list(x) for x in cag.PONTS],
            "estimations": sorted([list(x) for x in cag.ESTIMATIONS]), "decrochage": cag.ABSENCES_DECROCHAGE}


def donnees_annuaire():
    from noyau.annuaire import regles as ar
    ref = ar.lire_reference()
    champs = ("type", "nom", "sigle", "enseigne", "categorie", "commune", "code_postal", "departement", "adresse", "site",
              "affiliation", "source", "notes")
    return {"version": ref["version"], "zone": ref["zone"], "avertissement": ref["avertissement"],
            "types": [list(x) for x in ar.TYPES], "categoriesMagasin": [list(x) for x in ar.CATEGORIES_MAGASIN],
            "categoriesMarque": [list(x) for x in ar.CATEGORIES_MARQUE], "departements": [list(x) for x in ar.DEPARTEMENTS],
            "structures": [[x.get(k) for k in champs] for x in ref["structures"]], "champs": list(champs),
            "marques": [[x["nom"], x["pays"], x["categories"], x.get("groupe")] for x in ref["marques"]]}


def donnees_calendrier():
    from noyau.calendrier import regles as cr
    from noyau.organisation import regles as orr
    return {"disciplines": [list(x) for x in cr.DISCIPLINES], "famille": cr.FAMILLE, "familles": list(cr.FAMILLES),
            "niveaux": [list(x) for x in cr.NIVEAUX], "regions": {k: list(v) for k, v in cr.REGIONS.items()},
            "departements": cr.NOMS_DEPARTEMENTS, "statutsInscription": [list(x) for x in orr.STATUTS],
            "statutsEvenement": [list(x) for x in orr.STATUTS_EVENEMENT]}


def bloc(nom):
    contenu = {"NUTRITION": donnees, "MATERIEL": donnees_materiel, "FRACTIONNE": donnees_fractionne,
               "CLUB": donnees_club, "ANNUAIRE": donnees_annuaire,
               "CALENDRIER": donnees_calendrier}[nom]()
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
