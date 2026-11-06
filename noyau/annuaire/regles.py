"""
Règles de l'annuaire trail (sans base ni Qt) : types de fiches, catégories
de magasins et de marques, départements, filtres, lecture de la référence
livrée avec le logiciel (data/annuaire/reference.json) et d'un tableau à
importer.
"""

import csv
import io
import json
import re
import unicodedata
from pathlib import Path
from urllib.parse import quote_plus

FICHIER_REFERENCE = Path(__file__).resolve().parents[2] / "data" / "annuaire" / "reference.json"

TYPES = (("club_athle", "Club d'athlétisme"), ("club_running", "Club de running"), ("club_trail", "Club de trail"),
         ("section_trail", "Section trail d'un club"), ("ecole_trail", "École de trail"),
         ("organisateur", "Organisateur de courses"), ("magasin", "Magasin"), ("marque", "Marque"))
LIBELLE_TYPE = dict(TYPES)
TYPES_CLUBS = ("club_athle", "club_running", "club_trail", "section_trail", "ecole_trail", "organisateur")
CATEGORIES_MAGASIN = (("specialiste", "Spécialiste running et trail"), ("outdoor", "Outdoor et montagne"),
                      ("generaliste", "Grande surface de sport (rayon running)"))
LIBELLE_CATEGORIE_MAGASIN = dict(CATEGORIES_MAGASIN)
CATEGORIES_MARQUE = (("chaussures", "Chaussures"), ("textile", "Textile"), ("sacs", "Sacs et gilets"),
                     ("batons", "Bâtons"), ("frontales", "Frontales"), ("montres", "Montres GPS"),
                     ("nutrition", "Nutrition"), ("accessoires", "Accessoires (chaussettes, lunettes, semelles…)"))
LIBELLE_CATEGORIE_MARQUE = dict(CATEGORIES_MARQUE)
# catégorie de marque proposée pour chaque famille d'équipement du module Matériel
CATEGORIE_POUR_EQUIPEMENT = {"frontale": "frontales", "frontale_secours": "frontales", "sac": "sacs", "batons": "batons",
                             "gps_trace": "montres", "reserve_alimentaire": "nutrition"}
DEPARTEMENTS = (("04", "Alpes-de-Haute-Provence"), ("05", "Hautes-Alpes"), ("06", "Alpes-Maritimes"),
                ("13", "Bouches-du-Rhône"), ("83", "Var"), ("84", "Vaucluse"))
NOM_DEPARTEMENT = dict(DEPARTEMENTS)
AFFILIATIONS = ("FFA", "FFCAM", "FFME", "FFTri", "UFOLEP", "FSGT", "Aucune", "Inconnue")


class ErreurAnnuaire(Exception):
    """Message lisible ; rien n'a été modifié."""


def sans_accents(t):
    t = unicodedata.normalize("NFD", str(t or "").lower())
    return "".join(c for c in t if unicodedata.category(c) != "Mn")


def cle(*morceaux):
    return re.sub(r"[^a-z0-9]+", "-", sans_accents(" ".join(str(m or "") for m in morceaux))).strip("-")


def departement_de(code_postal):
    """« 84 » pour 84200 ; « 2A »/« 2B » pour la Corse ; None si illisible."""
    cp = re.sub(r"\s", "", str(code_postal or ""))
    if not re.fullmatch(r"\d{5}", cp):
        return None
    if cp.startswith("20"):
        return "2A" if int(cp) < 20200 else "2B"
    if cp.startswith("97"):
        return cp[:3]
    return cp[:2]


def verifier(fiche):
    """Nettoie une fiche (dict) et lève ErreurAnnuaire si elle est inutilisable."""
    f = {k: (v.strip() if isinstance(v, str) else v) for k, v in fiche.items()}
    if not f.get("nom"):
        raise ErreurAnnuaire("Donne un nom à la fiche.")
    if f.get("type") not in LIBELLE_TYPE:
        raise ErreurAnnuaire("Type de fiche inconnu.")
    if f.get("code_postal"):
        f["code_postal"] = re.sub(r"\s", "", f["code_postal"])
        if not re.fullmatch(r"\d{5}", f["code_postal"]):
            raise ErreurAnnuaire(f"Code postal illisible : {fiche['code_postal']}.")
        f["departement"] = departement_de(f["code_postal"])
    if f.get("site") and not re.match(r"https?://", f["site"]):
        f["site"] = "https://" + f["site"]
    if f["type"] == "magasin" and f.get("categorie") and f["categorie"] not in LIBELLE_CATEGORIE_MAGASIN:
        raise ErreurAnnuaire("Catégorie de magasin inconnue.")
    if f["type"] == "marque":
        cats = f.get("categories") or []
        if isinstance(cats, str):
            cats = [c.strip() for c in cats.split(",") if c.strip()]
        inconnues = [c for c in cats if c not in LIBELLE_CATEGORIE_MARQUE]
        if inconnues:
            raise ErreurAnnuaire(f"Catégorie de marque inconnue : {', '.join(inconnues)}.")
        f["categories"] = cats
    for k in ("sigle", "enseigne", "commune", "adresse", "site", "notes", "pays", "groupe", "affiliation"):
        if k in f and not f[k]:
            f[k] = None
    return f


def lire_reference(chemin=None):
    """La référence livrée : {version, zone, avertissement, structures: [...], marques: [...]}."""
    d = json.loads(Path(chemin or FICHIER_REFERENCE).read_text(encoding="utf-8"))
    for m in d["marques"]:
        m.setdefault("type", "marque")
    return d


def recherche_web(fiche):
    """Lien de recherche pour trouver le site, les horaires ou la page d'une fiche."""
    morceaux = [fiche.get("nom")]
    if fiche.get("type") == "marque":
        morceaux.append("trail running")
    elif fiche.get("commune"):
        morceaux.append(fiche["commune"])
    return "https://www.google.com/search?q=" + quote_plus(" ".join(m for m in morceaux if m))


def filtrer(fiches, types=None, departement=None, categorie=None, recherche="", favoris=False):
    """Filtre des fiches (dicts). categorie : celle d'un magasin, ou une catégorie de produits d'une marque."""
    q = sans_accents(recherche).split()
    res = []
    for f in fiches:
        if types and f["type"] not in types:
            continue
        if departement and f.get("departement") != departement:
            continue
        if categorie:
            if f["type"] == "magasin":
                if f.get("categorie") != categorie:
                    continue
            elif f["type"] == "marque":
                if categorie not in (f.get("categories") or []):
                    continue
            else:
                continue
        if favoris and not f.get("favori"):
            continue
        if q:
            texte = sans_accents(" ".join(str(f.get(k) or "") for k in ("nom", "sigle", "enseigne", "commune", "pays",
                                                                          "groupe", "mes_notes", "notes")))
            if not all(m in texte for m in q):
                continue
        res.append(f)
    return res


COLONNES_CSV = ("type", "nom", "sigle", "enseigne", "categorie", "commune", "code_postal", "adresse", "site", "affiliation",
                "pays", "categories", "notes")
SYNONYMES_TYPE = {"club": "club_athle", "athle": "club_athle", "athletisme": "club_athle", "running": "club_running",
                  "trail": "club_trail", "ecole": "ecole_trail", "ecole de trail": "ecole_trail", "section": "section_trail",
                  "section trail": "section_trail", "organisateur": "organisateur", "magasin": "magasin", "marque": "marque"}


def lire_csv(texte):
    """Lignes d'un tableau CSV (; ou ,) avec au moins les colonnes type et nom. Renvoie (fiches, erreurs)."""
    if isinstance(texte, bytes):
        for enc in ("utf-8-sig", "cp1252"):
            try:
                texte = texte.decode(enc)
                break
            except UnicodeDecodeError:
                continue
    sep = ";" if texte[:2000].count(";") >= texte[:2000].count(",") else ","
    lignes = list(csv.DictReader(io.StringIO(texte), delimiter=sep))
    fiches, erreurs = [], []
    for i, l in enumerate(lignes, 2):
        l = {sans_accents(k).strip().replace(" ", "_"): (v or "").strip() for k, v in l.items() if k}
        t = sans_accents(l.get("type", ""))
        l["type"] = t if t in LIBELLE_TYPE else SYNONYMES_TYPE.get(t, t)
        try:
            fiches.append(verifier({k: l.get(k) for k in COLONNES_CSV}))
        except ErreurAnnuaire as e:
            erreurs.append(f"ligne {i} : {e}")
    return fiches, erreurs


def vers_csv(fiches):
    out = io.StringIO()
    w = csv.writer(out, delimiter=";")
    w.writerow(COLONNES_CSV + ("source", "mes_notes", "favori"))
    for f in fiches:
        w.writerow([", ".join(f.get(k) or []) if k == "categories" else (f.get(k) or "") for k in COLONNES_CSV]
                   + [f.get("source") or "", f.get("mes_notes") or "", "oui" if f.get("favori") else ""])
    return "﻿" + out.getvalue()
