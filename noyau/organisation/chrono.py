"""
Chrono et classements (étape 4.5), sans base ni Qt : temps de course depuis
le départ réel de chaque épreuve, contrôle des passages (doublons, dossards
inconnus, arrivées avant le départ), classements scratch, par sexe et par
catégorie FFA, écarts, vitesses, statuts (abandon, disqualifié, non
partant), lecture d'un fichier de chronométrage.
"""

import re
from datetime import datetime, timedelta

from noyau.club import categories as cat, imports as imp
from noyau.club.profils import lire_temps, texte_temps

STATUTS_COURSE = (("classe", "Classé"), ("abandon", "Abandon"), ("disqualifie", "Disqualifié"),
                  ("non_partant", "Non partant"))
LIBELLE_STATUT_COURSE = dict(STATUTS_COURSE)
ABREGE = {"abandon": "ABD", "disqualifie": "DSQ", "non_partant": "NP"}
DOUBLON_SECONDES = 5               # deux arrivées du même dossard à moins de 5 s : la seconde est un double « top »


class ErreurChrono(Exception):
    """Message lisible ; rien n'a été modifié."""


def lire_heure(texte, jour):
    """Heure de passage ISO depuis « 10:42:17 », « 10:42:17.4 », « 10h42'17 » ou « 2027-04-11 10:42:17 »."""
    t = str(texte or "").strip().replace(",", ".")
    m = re.fullmatch(r"(\d{4}-\d{2}-\d{2})[T ](\d{1,2}):(\d{2}):(\d{2}(?:\.\d+)?)", t)
    if m:
        jour, t = m[1], f"{m[2]}:{m[3]}:{m[4]}"
    m = re.fullmatch(r"(\d{1,2})\s*[:h]\s*(\d{2})\s*[:'m]\s*(\d{2}(?:\.\d+)?)\s*(?:s|\")?", t)
    if not m:
        return None
    h, mi, s = int(m[1]), int(m[2]), float(m[3])
    if h > 47 or mi > 59 or s >= 60:
        return None
    base_ = datetime.fromisoformat(str(jour)[:10])
    return (base_ + timedelta(hours=h, minutes=mi, seconds=s)).isoformat(timespec="milliseconds")


def secondes_entre(debut, fin):
    return (datetime.fromisoformat(fin) - datetime.fromisoformat(debut)).total_seconds()


def controler_passages(passages, dossards_connus):
    """passages : [{id, dossard, heure, annule}] d'arrivée, dans l'ordre. Renvoie {retenus: {dossard: passage},
    doublons: [passage], inconnus: [passage], sans_dossard: [passage]} (le premier passage de chaque dossard
    est retenu)."""
    retenus, doublons, inconnus, sans = {}, [], [], []
    for p in sorted((p for p in passages if not p.get("annule")), key=lambda p: (p["heure"], p.get("id") or 0)):
        d = p.get("dossard")
        if not d:
            sans.append(p)
        elif d not in dossards_connus:
            inconnus.append(p)
        elif d in retenus:
            doublons.append(p)
        else:
            retenus[d] = p
    return {"retenus": retenus, "doublons": doublons, "inconnus": inconnus, "sans_dossard": sans}


def categorie_course(date_naissance, sexe, jour):
    """« SEH », « M1F », « JUH »… (code FFA + sexe) ; « ? » si la date de naissance manque."""
    c = cat.categorie(date_naissance, cat.saison_de(jour)) if date_naissance else None
    return (c["code"] if c else "?") + ((sexe or "")[:1] if (sexe or "")[:1] in "FH" else "")


def classement(epreuve, inscrits, passages, jour):
    """Classement d'une épreuve. epreuve : {id, distance_km, depart_reel ou heure_depart} ; inscrits : [{id,
    dossard, nom, prenom, sexe, date_naissance, club, statut_course, temps_corrige_s}] ; passages : passages
    d'arrivée retenus {dossard: passage}. Renvoie [{rang, rang_sexe, rang_categorie, categorie, temps_s, temps,
    ecart, vitesse, allure, statut, ...inscrit}] : les classés d'abord, puis ABD, DSQ, NP."""
    depart = epreuve.get("depart_reel") or (f"{str(jour)[:10]}T{epreuve['heure_depart']}:00" if epreuve.get("heure_depart")
                                            else None)
    lignes = []
    for i in inscrits:
        st = i.get("statut_course")
        t = i.get("temps_corrige_s")
        p = passages.get(i.get("dossard")) if i.get("dossard") else None
        if t is None and p and depart:
            t = secondes_entre(depart, p["heure"])
            if t <= 0:
                t = None
        if st in ("abandon", "disqualifie", "non_partant"):
            t_classe = None
        elif t is not None:
            st, t_classe = "classe", round(t, 1)
        else:
            continue                                     # pas encore arrivé : n'apparaît pas
        lignes.append({**i, "statut": st, "temps_s": t_classe,
                       "categorie": categorie_course(i.get("date_naissance"), i.get("sexe"), jour)})
    classes = sorted((l for l in lignes if l["statut"] == "classe"), key=lambda l: (l["temps_s"], l["nom"].lower()))
    premier = classes[0]["temps_s"] if classes else None
    rang_prec, temps_prec = 0, None
    par_sexe, par_cat = {}, {}
    for k, l in enumerate(classes, 1):
        l["rang"] = rang_prec if l["temps_s"] == temps_prec else k           # ex æquo : même rang
        rang_prec, temps_prec = l["rang"], l["temps_s"]
        s = (l.get("sexe") or "?")[:1]
        par_sexe[s] = par_sexe.get(s, 0) + 1
        l["rang_sexe"] = par_sexe[s]
        par_cat[l["categorie"]] = par_cat.get(l["categorie"], 0) + 1
        l["rang_categorie"] = par_cat[l["categorie"]]
        l["temps"] = texte_temps(l["temps_s"])
        l["ecart"] = ("+" + texte_temps(l["temps_s"] - premier)) if premier is not None and k > 1 else ""
        d = epreuve.get("distance_km")
        l["vitesse"] = round(d / (l["temps_s"] / 3600), 2) if d else None
        l["allure"] = (f"{int(l['temps_s'] / d // 60)}:{int(round(l['temps_s'] / d % 60)):02d}/km" if d else None)
    autres = sorted((l for l in lignes if l["statut"] != "classe"),
                    key=lambda l: (["abandon", "disqualifie", "non_partant"].index(l["statut"]), l["nom"].lower()))
    for l in autres:
        l.update(rang=None, rang_sexe=None, rang_categorie=None, temps=ABREGE[l["statut"]], ecart="", vitesse=None,
                 allure=None)
    return classes + autres


def filtrer(lignes, vue="scratch", valeur=None):
    """vue : scratch, sexe (valeur F ou H) ou categorie (valeur : code, ex. M1H)."""
    if vue == "sexe":
        return [l for l in lignes if (l.get("sexe") or "")[:1] == valeur]
    if vue == "categorie":
        return [l for l in lignes if l.get("categorie") == valeur]
    return lignes


def podiums(lignes, n=3):
    """{scratch: [...], F: [...], H: [...], categories: {code: [...]}} : les n premiers de chaque classement."""
    classes = [l for l in lignes if l["statut"] == "classe"]
    cats = {}
    for l in classes:
        cats.setdefault(l["categorie"], [])
        if len(cats[l["categorie"]]) < n:
            cats[l["categorie"]].append(l)
    ordre = lambda c: (cat.ORDRE.get(c[:-1] if c[-1:] in "FH" else c, 99), c[-1:])
    return {"scratch": classes[:n], "F": [l for l in classes if (l.get("sexe") or "")[:1] == "F"][:n],
            "H": [l for l in classes if (l.get("sexe") or "")[:1] == "H"][:n],
            "categories": dict(sorted(cats.items(), key=lambda x: ordre(x[0])))}


def lire_fichier(contenu, nom_fichier, jour, mode="heure"):
    """Fichier d'un appareil ou d'un logiciel de chrono : une ligne par passage, avec le dossard et une heure
    (mode « heure ») ou un temps de course (mode « temps »). Renvoie (passages [{dossard, heure|temps_s}],
    erreurs)."""
    lignes = imp.lire_tableau(contenu, nom_fichier)
    if not lignes:
        return [], []
    entete = [imp._cle(c) for c in lignes[0]]
    i_dos = next((i for i, c in enumerate(entete) if c in ("dossard", "dos", "bib", "numero", "n°", "num")), None)
    i_val = next((i for i, c in enumerate(entete) if c in ("heure", "temps", "time", "chrono", "passage", "arrivee")), None)
    debut = 1 if i_dos is not None or i_val is not None else 0
    i_dos = 0 if i_dos is None else i_dos
    i_val = 1 if i_val is None else i_val
    res, erreurs = [], []
    for n, l in enumerate(lignes[debut:], debut + 1):
        if len(l) <= max(i_dos, i_val):
            continue
        d = re.sub(r"\D", "", l[i_dos])
        if not d:
            erreurs.append(f"ligne {n} : dossard illisible ({l[i_dos]})")
            continue
        if mode == "temps":
            t = lire_temps(l[i_val])
            if t is None:
                erreurs.append(f"ligne {n} : temps illisible ({l[i_val]})")
                continue
            res.append({"dossard": int(d), "temps_s": t})
        else:
            h = lire_heure(l[i_val], jour)
            if h is None:
                erreurs.append(f"ligne {n} : heure illisible ({l[i_val]})")
                continue
            res.append({"dossard": int(d), "heure": h})
    return res, erreurs
