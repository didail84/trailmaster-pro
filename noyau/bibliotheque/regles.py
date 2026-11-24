"""
Règles de la bibliothèque trail (sans Qt) : lecture de la liste livrée avec
le logiciel (data/bibliotheque/reference.json), filtres, recherche, lien pour
trouver un livre, et ce que le coureur en a fait (à lire, lu).

Chaque livre est rattaché aux modules du logiciel qu'il éclaire (codes de
noyau/modules.py) et aux écrans du menu où l'on s'en sert : un écran peut
ainsi proposer « les livres pour aller plus loin ».

Titres, auteurs, éditeurs et années ont été vérifiés auprès de libraires et
d'éditeurs avant d'être livrés ; une case vide veut dire « pas vérifiée »,
jamais « inventée ».
"""

import json
import unicodedata
from pathlib import Path
from urllib.parse import quote_plus

from data.database import obtenir_parametre, definir_parametre

FICHIER_REFERENCE = Path(__file__).resolve().parents[2] / "data" / "bibliotheque" / "reference.json"
CLE_STATUTS = "bibliotheque_statuts"

LANGUES = (("fr", "Français"), ("en", "Anglais"), ("es", "Espagnol"))
NOM_LANGUE = dict(LANGUES)
STATUTS = (("a_lire", "★ À lire"), ("lu", "✓ Lu"))
LIBELLE_STATUT = dict(STATUTS)

_cache = None


def lire_reference(chemin=None):
    global _cache
    if chemin:
        return json.loads(Path(chemin).read_text(encoding="utf-8"))
    if _cache is None:
        _cache = json.loads(FICHIER_REFERENCE.read_text(encoding="utf-8"))
    return _cache


def themes(ref=None):
    """[(code, nom)] dans l'ordre de la liste."""
    return [(t["code"], t["nom"]) for t in (ref or lire_reference())["themes"]]


def nom_theme(code, ref=None):
    return dict(themes(ref)).get(code, code or "")


def _sans_accents(t):
    t = unicodedata.normalize("NFKD", str(t or "").lower())
    return "".join(c for c in t if not unicodedata.combining(c))


def auteurs(livre):
    a = livre.get("auteurs") or []
    return a[0] if len(a) == 1 else ", ".join(a[:-1]) + " et " + a[-1] if a else ""


def lisible_en_francais(livre):
    """Vrai si le livre est en français ou a une traduction française connue."""
    return livre.get("langue") == "fr" or bool(livre.get("titre_fr"))


def titre_affiche(livre):
    """Le titre français quand il existe, sinon le titre d'origine."""
    return livre.get("titre_fr") or livre["titre"]


def reference_courte(livre):
    """« Éditeur, année » de l'édition d'origine, puis l'édition française si elle existe
    (le titre français est déjà le titre affiché)."""
    morceaux = []
    orig = ", ".join(str(x) for x in (livre.get("editeur"), livre.get("annee")) if x)
    if orig:
        morceaux.append(orig)
    if livre.get("titre_fr") and livre.get("langue") != "fr":
        fr = ", ".join(str(x) for x in (livre.get("editeur_fr"), livre.get("annee_fr")) if x)
        morceaux.append("traduit en français" + (f" ({fr})" if fr else ""))
    return " · ".join(morceaux)


def lien(livre):
    """Le document en ligne pour un texte officiel, sinon une recherche du livre (titre et auteur) sur Open Library."""
    if livre.get("lien", "").startswith("https://"):
        return livre["lien"]
    auteur = (livre.get("auteurs") or [""])[0]
    return "https://openlibrary.org/search?q=" + quote_plus(f"{livre['titre']} {auteur}".strip())


def livres(theme=None, module=None, langue=None, en_francais=False, recherche=None, statut=None,
           statuts=None, ref=None):
    """Les livres qui passent les filtres, dans l'ordre de la liste.

    langue : langue d'origine ; en_francais : en français ou traduit ;
    statut : « a_lire », « lu » ou « aucun » (ni l'un ni l'autre)."""
    statuts = statuts if statuts is not None else {}
    mots = _sans_accents(recherche).split() if recherche else []
    r = []
    for l in (ref or lire_reference())["livres"]:
        if theme and l["theme"] != theme:
            continue
        if module and module not in l.get("modules", []):
            continue
        if langue and l.get("langue") != langue:
            continue
        if en_francais and not lisible_en_francais(l):
            continue
        s = statuts.get(l["id"])
        if statut == "aucun" and s:
            continue
        if statut and statut != "aucun" and s != statut:
            continue
        if mots:
            texte = _sans_accents(" ".join([l["titre"], l.get("titre_fr", ""), " ".join(l.get("auteurs", [])),
                                            l.get("editeur", ""), l.get("pourquoi", ""), nom_theme(l["theme"], ref),
                                            " ".join(l.get("ecrans", []))]))
            if not all(m in texte for m in mots):
                continue
        r.append(l)
    return r


def livres_pour_ecran(libelle_ecran, ref=None):
    """Les livres rattachés à un écran du menu (« Fractionné », « Alimentation »…)."""
    cle = _sans_accents(libelle_ecran)
    return [l for l in (ref or lire_reference())["livres"] if any(_sans_accents(e) == cle for e in l.get("ecrans", []))]


# ------------------------------------------------------------------
# Ce que le coureur en a fait (gardé dans les réglages du logiciel)
# ------------------------------------------------------------------

def lire_statuts():
    try:
        d = json.loads(obtenir_parametre(CLE_STATUTS) or "{}")
    except (ValueError, TypeError):
        return {}
    return {k: v for k, v in d.items() if v in LIBELLE_STATUT} if isinstance(d, dict) else {}


def definir_statut(livre_id, statut):
    """statut : « a_lire », « lu » ou None pour l'enlever."""
    if statut is not None and statut not in LIBELLE_STATUT:
        raise ValueError(f"Statut inconnu : {statut}")
    d = lire_statuts()
    if statut:
        d[livre_id] = statut
    else:
        d.pop(livre_id, None)
    definir_parametre(CLE_STATUTS, json.dumps(d, ensure_ascii=False, sort_keys=True))
    return d


def resume(statuts=None, ref=None):
    ref = ref or lire_reference()
    statuts = statuts if statuts is not None else lire_statuts()
    ls = ref["livres"]
    return {"livres": len(ls), "en_francais": sum(1 for l in ls if lisible_en_francais(l)),
            "a_lire": sum(1 for l in ls if statuts.get(l["id"]) == "a_lire"),
            "lus": sum(1 for l in ls if statuts.get(l["id"]) == "lu")}
