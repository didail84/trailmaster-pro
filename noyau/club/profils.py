"""
Profils des licenciés (étape 4.3), sans base ni Qt : temps de course,
records (route sur les distances officielles, trail en vitesse
km-effort), bilan d'une saison, lecture d'un classement de course
extérieure et rapprochement avec les adhérents, diplômes d'entraîneur.
"""

import csv
import io
import re
from datetime import date, timedelta

from noyau.club import imports as imp
from noyau.calendrier.regles import classer, km_effort, LIBELLE_DISCIPLINE

STATUTS_RESULTAT = (("classe", "Classé"), ("abandon", "Abandon"), ("disqualifie", "Disqualifié"),
                    ("non_partant", "Non partant"))
LIBELLE_STATUT_RESULTAT = dict(STATUTS_RESULTAT)
DISTANCES_ROUTE = ((5, "5 km"), (10, "10 km"), (15, "15 km"), (21.0975, "Semi-marathon"), (42.195, "Marathon"),
                   (100, "100 km"))
TOLERANCE_ROUTE = 0.015
FAMILLES_TRAIL = ("trail_decouverte", "trail_court", "trail_long", "ultra_trail")
ALERTE_DIPLOME_JOURS = 90


class ErreurProfil(Exception):
    """Message lisible ; rien n'a été modifié."""


def lire_temps(texte):
    """Secondes depuis « 1:23:45 », « 1:23:45.6 », « 83:45 », « 1h23'45 », « 1h23 », « 45'30'' », « 2h05m10s »."""
    t = str(texte or "").strip().lower().replace(",", ".").replace("’", "'").replace("''", '"')
    if not t:
        return None
    m = re.fullmatch(r"(?:(\d+):)?(\d{1,2}):(\d{2}(?:\.\d+)?)", t)
    if m:
        return int(m[1] or 0) * 3600 + int(m[2]) * 60 + float(m[3])
    m = re.fullmatch(r"(\d+)\s*h\s*(\d{1,2})", t)          # « 1h23 » = 1 h 23 min
    if m:
        return int(m[1]) * 3600 + int(m[2]) * 60
    m = re.fullmatch(r"(?:(\d+)\s*h)?\s*(?:(\d{1,2})\s*(?:min|mn|m|'))?\s*(?:(\d{1,2}(?:\.\d+)?)\s*(?:s|\"|sec)?)?", t)
    if m and any(m.groups()) and ("h" in t or "'" in t or "m" in t or "s" in t):
        return int(m[1] or 0) * 3600 + int(m[2] or 0) * 60 + float(m[3] or 0)
    return None


def texte_temps(secondes, dixiemes=False):
    if secondes is None:
        return ""
    s = round(float(secondes), 1 if dixiemes else 0)
    h, reste = divmod(int(s), 3600)
    m, sec = divmod(reste, 60)
    frac = f".{int(round((s - int(s)) * 10))}" if dixiemes else ""
    return f"{h}:{m:02d}:{sec:02d}{frac}" if h else f"{m}:{sec:02d}{frac}"


def allure(secondes, distance_km):
    if not secondes or not distance_km:
        return None
    a = secondes / distance_km
    return f"{int(a // 60)}:{int(round(a % 60)):02d}/km"


def distance_route(distance_km):
    """Libellé de la distance officielle la plus proche (5 km… 100 km) à 1,5 % près, sinon None."""
    if not distance_km:
        return None
    for d, lib in DISTANCES_ROUTE:
        if abs(distance_km - d) <= d * TOLERANCE_ROUTE:
            return lib
    return None


def discipline_de(r):
    return r.get("discipline") or classer(f"{r.get('course') or ''} {r.get('epreuve') or ''}", r.get("distance_km"),
                                          r.get("denivele_m"))


def records(resultats):
    """{route: [{distance, temps_s, allure, course, date}], trail: [{discipline, vitesse_ke, ...}],
    plus_longue, plus_gros_dplus} sur les résultats classés avec un temps."""
    classes = [r for r in resultats if r.get("statut", "classe") == "classe" and r.get("temps_s")]
    route, trail = {}, {}
    for r in classes:
        disc = discipline_de(r)
        lib = distance_route(r.get("distance_km")) if disc == "route" else None
        if lib and (lib not in route or r["temps_s"] < route[lib]["temps_s"]):
            route[lib] = {"distance": lib, "temps_s": r["temps_s"], "temps": texte_temps(r["temps_s"]),
                          "allure": allure(r["temps_s"], r["distance_km"]), "course": r["course"], "date": r["date"]}
        if disc in FAMILLES_TRAIL and r.get("distance_km"):
            ke = km_effort(r["distance_km"], r.get("denivele_m"))
            v = round(ke / (r["temps_s"] / 3600), 2)
            if disc not in trail or v > trail[disc]["vitesse_ke"]:
                trail[disc] = {"discipline": LIBELLE_DISCIPLINE[disc], "code": disc, "vitesse_ke": v, "km_effort": ke,
                               "temps": texte_temps(r["temps_s"]), "course": r["course"], "date": r["date"],
                               "distance_km": r["distance_km"], "denivele_m": r.get("denivele_m")}
    ordre_route = [lib for _d, lib in DISTANCES_ROUTE]
    avec_distance = [r for r in resultats if r.get("distance_km") and r.get("statut", "classe") == "classe"]
    return {"route": [route[k] for k in ordre_route if k in route],
            "trail": [trail[k] for k in FAMILLES_TRAIL if k in trail],
            "plus_longue": max(avec_distance, key=lambda r: r["distance_km"], default=None),
            "plus_gros_dplus": max((r for r in avec_distance if r.get("denivele_m")), key=lambda r: r["denivele_m"],
                                   default=None)}


def bilan(resultats, debut=None, fin=None):
    """Bilan d'une période : courses, km, D+, podiums (scratch, sexe ou catégorie), abandons."""
    rs = [r for r in resultats if (not debut or str(r["date"]) >= str(debut)) and (not fin or str(r["date"]) <= str(fin))]
    classes = [r for r in rs if r.get("statut", "classe") == "classe"]
    podium = lambda r: any((r.get(k) or 99) <= 3 for k in ("classement_general", "classement_sexe", "classement_categorie"))
    return {"courses": len(rs), "classees": len(classes), "abandons": sum(1 for r in rs if r.get("statut") == "abandon"),
            "km": round(sum(r.get("distance_km") or 0 for r in classes), 1),
            "dplus": int(sum(r.get("denivele_m") or 0 for r in classes)), "podiums": sum(1 for r in classes if podium(r)),
            "victoires_categorie": sum(1 for r in classes if r.get("classement_categorie") == 1)}


# ------------------------------------------------------------------ classement d'une course extérieure

COLONNES_CLASSEMENT = {
    "rang": ("clt", "class", "classement", "rang", "place", "pl", "position", "scratch", "general"),
    "nom": ("nom", "nom de famille", "last name"),
    "prenom": ("prenom", "first name"),
    "nom_complet": ("nom prenom", "nom et prenom", "coureur", "participant", "athlete", "concurrent", "nom - prenom"),
    "temps": ("temps", "temps officiel", "temps reel", "chrono", "temps net", "temps final", "time", "perf"),
    "categorie": ("cat", "categorie", "cat."),
    "rang_categorie": ("clt cat", "class cat", "classement categorie", "rang cat", "pl cat", "clt/cat", "cat. clt"),
    "sexe": ("sexe", "s", "genre"),
    "rang_sexe": ("clt sexe", "class sexe", "classement sexe", "rang sexe"),
    "club": ("club", "equipe", "club / ville"),
    "naissance": ("annee", "ne en", "annee de naissance", "naissance", "date de naissance", "an"),
    "dossard": ("dossard", "dos", "bib", "n°"),
}


def lire_classement(contenu, nom_fichier=""):
    """Lignes d'un classement (CSV, Excel ou texte collé avec tabulations) : [{rang, nom, prenom, nom_complet,
    temps_s, statut, categorie, rang_categorie, sexe, rang_sexe, club, annee, dossard}], et le nombre de classés."""
    if isinstance(contenu, str) and "\t" in contenu[:3000] and not nom_fichier:
        lignes = [l.split("\t") for l in contenu.splitlines() if l.strip()]
    else:
        lignes = imp.lire_tableau(contenu, nom_fichier)
    if not lignes:
        return [], 0
    debut = next((k for k, l in enumerate(lignes[:15]) if any(imp._cle(c) in COLONNES_CLASSEMENT["temps"] for c in l)), 0)
    entetes = [imp._cle(c).strip(". ") for c in lignes[debut]]
    corr = {}
    for champ in ("rang_categorie", "rang_sexe", "nom_complet", "rang", "nom", "prenom", "temps", "categorie", "sexe", "club",
                  "naissance", "dossard"):
        for i, c in enumerate(entetes):
            if i not in corr.values() and c in COLONNES_CLASSEMENT[champ]:
                corr[champ] = i
                break
    res = []
    for l in lignes[debut + 1:]:
        def v(k):
            i = corr.get(k)
            return l[i].strip() if i is not None and i < len(l) else ""
        nom, prenom = v("nom"), v("prenom")
        if not nom and v("nom_complet"):
            nom, prenom = separer_nom(v("nom_complet"))
        if not nom:
            continue
        brut = v("temps")
        t = lire_temps(brut)
        st = imp._cle(brut + " " + v("rang"))
        statut = ("abandon" if re.search(r"\b(abd|abandon|dnf)\b", st) else "disqualifie" if re.search(r"\b(dsq|disq)", st)
                  else "non_partant" if re.search(r"\b(dns|np|non partant)\b", st) else "classe" if t else None)
        if statut is None:
            continue
        an = re.search(r"(19|20)\d{2}", v("naissance"))
        entier = lambda x: int(re.match(r"\d+", x)[0]) if re.match(r"\d+", x or "") else None
        cat_txt = v("categorie")
        res.append({"rang": entier(v("rang")) if statut == "classe" else None, "nom": nom, "prenom": prenom,
                    "temps_s": t if statut == "classe" else None, "statut": statut, "categorie": cat_txt or None,
                    "rang_categorie": entier(v("rang_categorie")), "sexe": imp.sexe_depuis(v("sexe")) or
                    (("F" if cat_txt.upper().endswith("F") else "H" if cat_txt.upper().endswith(("H", "M")) else None)
                     if len(cat_txt) <= 4 else None), "rang_sexe": entier(v("rang_sexe")), "club": v("club") or None,
                    "annee": int(an[0]) if an else None, "dossard": entier(v("dossard"))})
    return res, sum(1 for r in res if r["statut"] == "classe")


def separer_nom(texte):
    """« MARTIN Lucas » ou « Lucas MARTIN » → (nom, prénom) : le nom est la partie en majuscules."""
    mots = texte.split()
    maj = [m for m in mots if m.isupper() and len(m) > 1]
    if maj and len(maj) < len(mots):
        return " ".join(maj), " ".join(m for m in mots if m not in maj)
    return (mots[0], " ".join(mots[1:])) if len(mots) > 1 else (texte, "")


def _cle_personne(nom, prenom):
    return f"{imp._cle(nom)}|{imp._cle(prenom)}"


def associer(lignes, adherents):
    """[(ligne, adherent)] des lignes qui correspondent à un adhérent : même nom et prénom (accents et
    majuscules ignorés, nom et prénom inversés acceptés) et, si l'année est connue des deux côtés, même année
    de naissance. Un nom porté par deux adhérents sans année pour départager n'est pas associé."""
    index = {}
    for a in adherents:
        for k in (_cle_personne(a["nom"], a["prenom"]), _cle_personne(a["prenom"], a["nom"])):
            index.setdefault(k, []).append(a)
    res = []
    for l in lignes:
        cands = index.get(_cle_personne(l["nom"], l["prenom"]), [])
        if l.get("annee"):
            cands = [a for a in cands if not a.get("date_naissance") or int(str(a["date_naissance"])[:4]) == l["annee"]]
        uniques = {a["personne_id"]: a for a in cands}
        if len(uniques) == 1:
            res.append((l, next(iter(uniques.values()))))
    return res


# ------------------------------------------------------------------ diplômes

def etat_diplome(d, aujourdhui=None):
    """« valide », « bientôt » (moins de 90 jours), « expiré » ou « sans date »."""
    if not d.get("date_validite"):
        return "sans date"
    auj = aujourdhui or date.today()
    fin = date.fromisoformat(str(d["date_validite"])[:10])
    if fin < auj:
        return "expiré"
    if fin <= auj + timedelta(days=ALERTE_DIPLOME_JOURS):
        return "bientôt"
    return "valide"


def cle_resultat(personne_id, jour, course, epreuve=None, distance_km=None):
    """Clé de doublon d'un résultat saisi ou importé (une même course n'entre qu'une fois sur le profil)."""
    return f"ext|{personne_id}|{str(jour)[:10]}|{imp._cle(course)}|{imp._cle(epreuve or '')}|{distance_km or ''}"
