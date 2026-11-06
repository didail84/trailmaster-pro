"""
Accès aux données de la logistique d'une course (étape 4.6) : contexte de
la course, démarches et rétroplanning, bénévoles, postes et affectations,
ravitaillements, matériel, partenaires (reçus des dons) et budget.
Les règles sont dans noyau/organisation/logistique.py.
"""

import json
import re
from datetime import date

from noyau.donnees import base, organisation as dor, personnes as dper
from noyau.organisation import logistique as L
from noyau.club import imports as imp


class ErreurLogistique(Exception):
    """Message lisible ; rien n'a été modifié."""


def _iso(d):
    if not d:
        return None
    try:
        return date.fromisoformat(str(d)[:10]).isoformat()
    except ValueError:
        v = imp.normaliser_date(str(d))
        if not v:
            raise ErreurLogistique(f"Date illisible : {d}.")
        return v


def _heure(h):
    if not h:
        return None
    m = re.fullmatch(r"\s*(\d{1,2})\s*[:hH]\s*(\d{2})?\s*", str(h))
    if not m or int(m.group(1)) > 23 or int(m.group(2) or 0) > 59:
        raise ErreurLogistique(f"Heure illisible : {h} (exemple : 07:30).")
    return f"{int(m.group(1)):02d}:{int(m.group(2) or 0):02d}"


def _ev(evenement_id):
    ev = dor.evenement(evenement_id)
    if not ev:
        raise ErreurLogistique("Événement introuvable.")
    return ev


def _lignes(sql, cles, params=()):
    return [dict(zip(cles, l)) for l in base.lire_tous(sql, params)]


# ------------------------------------------------------------------ contexte

def contexte(evenement_id):
    ev = _ev(evenement_id)
    brut = base.lire_un("SELECT contexte_json FROM evenements WHERE id=?", (evenement_id,))[0]
    try:
        brut = json.loads(brut) if brut else {}
    except ValueError:
        brut = {}
    return L.contexte(brut, ev, dor.epreuves(evenement_id))


def enregistrer_contexte(evenement_id, champs):
    """Complète le contexte enregistré (les réponses absentes de `champs` sont gardées)."""
    _ev(evenement_id)
    brut = base.lire_un("SELECT contexte_json FROM evenements WHERE id=?", (evenement_id,))[0]
    try:
        v = json.loads(brut) if brut else {}
    except ValueError:
        v = {}
    v.update({k: champs[k] for k in L.CONTEXTE_DEFAUT if k in champs})
    for k in ("communes", "departements", "participants", "spectateurs", "carrefours"):
        if k in v:
            try:
                v[k] = max(0, int(v[k] or 0))
            except (TypeError, ValueError):
                raise ErreurLogistique(f"Nombre illisible pour « {k} ».")
    base.ecrire("UPDATE evenements SET contexte_json=? WHERE id=?", (json.dumps(v, ensure_ascii=False), evenement_id))
    return contexte(evenement_id)


# ------------------------------------------------------------------ démarches

CHAMPS_DEMARCHE = ("code", "titre", "categorie", "autorite", "pieces", "echeance", "statut", "date_envoi", "date_reponse",
                   "reference", "notes", "manuelle")


def generer_demarches(evenement_id):
    """Crée les démarches qui s'appliquent (sans toucher au suivi de celles qui existent) ; met à jour leur
    échéance ; celles qui ne s'appliquent plus passent « sans objet » (ou sont retirées si rien n'a été suivi).
    Renvoie {ajoutees, mises_a_jour, retirees}."""
    ev = _ev(evenement_id)
    ctx = contexte(evenement_id)
    voulues = {d["code"]: d for d in L.demarches_pour(ev["date_debut"], ctx)}
    existantes = {d["code"]: d for d in demarches(evenement_id, brut=True) if d["code"]}
    aj = maj = ret = 0
    with base.transaction() as cur:
        for code, d in voulues.items():
            if code in existantes:
                x = existantes[code]
                champs = {"titre": d["titre"], "categorie": d["categorie"], "autorite": d["autorite"],
                          "pieces": d["pieces"], "echeance": d["echeance"]}
                if x["statut"] == "sans_objet" and not x.get("date_envoi"):
                    champs["statut"] = "a_faire"
                if any(x.get(k) != v for k, v in champs.items()):
                    base.ecrire(f"UPDATE orga_demarches SET {', '.join(k + '=?' for k in champs)} WHERE id=?",
                                tuple(champs.values()) + (x["id"],), cur)
                    maj += 1
            else:
                base.inserer("orga_demarches", {"evenement_id": evenement_id, "code": code, "titre": d["titre"],
                                                "categorie": d["categorie"], "autorite": d["autorite"],
                                                "pieces": d["pieces"], "echeance": d["echeance"]}, cur)
                aj += 1
        for code, x in existantes.items():
            if code in voulues or x["manuelle"]:
                continue
            if x["statut"] == "a_faire" and not x.get("notes") and not x.get("date_envoi"):
                base.ecrire("DELETE FROM orga_demarches WHERE id=?", (x["id"],), cur)
                ret += 1
            elif x["statut"] != "sans_objet":
                base.ecrire("UPDATE orga_demarches SET statut='sans_objet' WHERE id=?", (x["id"],), cur)
                ret += 1
    return {"ajoutees": aj, "mises_a_jour": maj, "retirees": ret}


def demarches(evenement_id, brut=False, aujourdhui=None):
    res = _lignes(f"SELECT id, {', '.join(CHAMPS_DEMARCHE)} FROM orga_demarches WHERE evenement_id=? "
                  "ORDER BY echeance IS NULL, echeance, id", ("id",) + CHAMPS_DEMARCHE, (evenement_id,))
    if brut:
        return res
    ev = _ev(evenement_id)
    conseils = {d["code"]: d["note"] for d in L.demarches_pour(ev["date_debut"], contexte(evenement_id))}
    for d in res:
        d["conseil"] = conseils.get(d["code"], "")
        d["etat"] = L.etat_demarche(d, aujourdhui)
        d["jalon"] = L.jalon(d["echeance"], ev["date_debut"]) if d["echeance"] else ""
    return res


def enregistrer_demarche(evenement_id, champs, demarche_id=None):
    v = {k: champs[k] for k in CHAMPS_DEMARCHE if k in champs and k not in ("code", "manuelle")}
    if "titre" in v or demarche_id is None:
        v["titre"] = (v.get("titre") or "").strip()
        if not v["titre"]:
            raise ErreurLogistique("Donne un intitulé à la démarche.")
    if v.get("statut") and v["statut"] not in L.LIBELLE_STATUT:
        raise ErreurLogistique("Statut inconnu.")
    for k in ("echeance", "date_envoi", "date_reponse"):
        if k in v:
            v[k] = _iso(v[k])
    if demarche_id is None:
        v.update({"evenement_id": evenement_id, "manuelle": 1})
        return base.inserer("orga_demarches", v)
    if v:
        base.ecrire(f"UPDATE orga_demarches SET {', '.join(k + '=?' for k in v)} WHERE id=?", tuple(v.values()) + (demarche_id,))
    return demarche_id


def changer_statut_demarches(ids, statut, jour=None):
    if statut not in L.LIBELLE_STATUT:
        raise ErreurLogistique("Statut inconnu.")
    j = _iso(jour) or date.today().isoformat()
    for i in ids:
        if statut == "envoye":
            base.ecrire("UPDATE orga_demarches SET statut=?, date_envoi=COALESCE(date_envoi, ?) WHERE id=?", (statut, j, i))
        elif statut in ("accorde", "refuse"):
            base.ecrire("UPDATE orga_demarches SET statut=?, date_reponse=? WHERE id=?", (statut, j, i))
        else:
            base.ecrire("UPDATE orga_demarches SET statut=? WHERE id=?", (statut, i))


def supprimer_demarche(demarche_id):
    """Une démarche ajoutée à la main est supprimée ; une démarche réglementaire passe « sans objet »."""
    r = base.lire_un("SELECT manuelle FROM orga_demarches WHERE id=?", (demarche_id,))
    if not r:
        return
    if r[0]:
        base.ecrire("DELETE FROM orga_demarches WHERE id=?", (demarche_id,))
    else:
        base.ecrire("UPDATE orga_demarches SET statut='sans_objet' WHERE id=?", (demarche_id,))


# ------------------------------------------------------------------ bénévoles

CHAMPS_BENEVOLE = ("personne_id", "nom", "prenom", "telephone", "email", "date_naissance", "permis", "secouriste",
                   "taille_tshirt", "disponibilites", "competences", "source", "statut", "notes")
STATUTS_BENEVOLE = (("confirme", "Confirmé"), ("a_confirmer", "À confirmer"), ("desiste", "Désisté"))
LIBELLE_STATUT_BENEVOLE = dict(STATUTS_BENEVOLE)


def benevoles(evenement_id):
    return _lignes(f"SELECT id, {', '.join(CHAMPS_BENEVOLE)} FROM benevoles WHERE evenement_id=? "
                   "ORDER BY nom COLLATE NOCASE, prenom COLLATE NOCASE", ("id",) + CHAMPS_BENEVOLE, (evenement_id,))


def enregistrer_benevole(evenement_id, champs, benevole_id=None):
    v = {k: champs[k] for k in CHAMPS_BENEVOLE if k in champs}
    if "nom" in v or benevole_id is None:
        v["nom"] = (v.get("nom") or "").strip()
        if not v["nom"]:
            raise ErreurLogistique("Donne le nom du bénévole.")
    if "date_naissance" in v:
        v["date_naissance"] = _iso(v["date_naissance"])
    if v.get("statut") and v["statut"] not in LIBELLE_STATUT_BENEVOLE:
        raise ErreurLogistique("Statut inconnu.")
    for k in ("permis", "secouriste"):
        if k in v:
            v[k] = 1 if v[k] else 0
    if benevole_id is None:
        v["evenement_id"] = evenement_id
        return base.inserer("benevoles", v)
    if v:
        base.ecrire(f"UPDATE benevoles SET {', '.join(k + '=?' for k in v)} WHERE id=?", tuple(v.values()) + (benevole_id,))
    return benevole_id


def supprimer_benevole(benevole_id):
    base.ecrire("DELETE FROM benevoles WHERE id=?", (benevole_id,))


def ajouter_personnes(evenement_id, personne_ids):
    """Bénévoles venant des fiches Personnes (adhérents du club) ; sans doublon. Leur ajoute le rôle Bénévole.
    Renvoie le nombre ajouté."""
    deja = {b["personne_id"] for b in benevoles(evenement_id) if b["personne_id"]}
    n = 0
    for pid in personne_ids:
        if pid in deja:
            continue
        p = dper.fiche(pid)
        if not p:
            continue
        enregistrer_benevole(evenement_id, {"personne_id": pid, "nom": p["nom"], "prenom": p.get("prenom"),
                                            "telephone": p.get("telephone"), "email": p.get("email"),
                                            "date_naissance": p.get("date_naissance"), "source": "Club"})
        r = dper.roles(pid)
        if "benevole" not in r:
            dper.definir_roles(pid, list(r) + ["benevole"])
        n += 1
    return n


SYNONYMES_BENEVOLE = {
    "nom": ("nom", "nom de famille", "last name"), "prenom": ("prenom", "first name"),
    "telephone": ("telephone", "tel", "portable", "mobile", "numero de telephone"),
    "email": ("email", "e-mail", "mail", "adresse email", "courriel"),
    "date_naissance": ("date de naissance", "naissance", "ne le"),
    "permis": ("permis", "permis de conduire", "permis b"), "secouriste": ("secouriste", "psc1", "pse"),
    "taille_tshirt": ("taille", "taille t-shirt", "taille tshirt", "t-shirt"),
    "disponibilites": ("disponibilites", "disponibilite", "creneaux", "horaires"),
    "competences": ("poste souhaite", "postes souhaites", "competences", "souhait"),
}


def _norm(t):
    import unicodedata
    t = unicodedata.normalize("NFKD", str(t or "")).encode("ascii", "ignore").decode().lower()
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9@.\- ]", " ", t)).strip()


def _oui(t):
    return _norm(t) in ("oui", "o", "x", "1", "yes", "vrai", "true", "b")


def importer_benevoles(evenement_id, contenu, nom_fichier="benevoles.csv"):
    """Fichier ou tableau collé (formulaire HelloAsso, Google Forms, CSV). Sans doublon (nom et prénom).
    Renvoie {ajoutes, deja, ignores}."""
    if isinstance(contenu, str):
        contenu = contenu.encode("utf-8")
    lignes = imp.lire_tableau(contenu, nom_fichier)
    lignes = [l for l in lignes if any(str(x).strip() for x in l)]
    if len(lignes) < 2:
        raise ErreurLogistique("Il faut une ligne de titres puis au moins un bénévole.")
    entetes = [_norm(x) for x in lignes[0]]
    col = {}
    for champ, syn in SYNONYMES_BENEVOLE.items():
        for i, e in enumerate(entetes):
            if e in syn and champ not in col:
                col[champ] = i
    if "nom" not in col:
        raise ErreurLogistique("Colonne « Nom » introuvable.")
    deja = {_norm(f"{b['nom']} {b.get('prenom') or ''}") for b in benevoles(evenement_id)}
    aj = dj = ig = 0
    for l in lignes[1:]:
        val = lambda k: (l[col[k]].strip() if k in col and col[k] < len(l) else "")
        nom = val("nom")
        if not nom:
            ig += 1
            continue
        cle = _norm(f"{nom} {val('prenom')}")
        if cle in deja:
            dj += 1
            continue
        enregistrer_benevole(evenement_id, {
            "nom": nom, "prenom": val("prenom") or None, "telephone": val("telephone") or None, "email": val("email") or None,
            "date_naissance": imp.normaliser_date(val("date_naissance")) if val("date_naissance") else None,
            "permis": _oui(val("permis")), "secouriste": _oui(val("secouriste")), "taille_tshirt": val("taille_tshirt") or None,
            "disponibilites": val("disponibilites") or None, "competences": val("competences") or None, "source": "Import"})
        deja.add(cle)
        aj += 1
    return {"ajoutes": aj, "deja": dj, "ignores": ig}


# ------------------------------------------------------------------ postes et affectations

CHAMPS_POSTE = ("nom", "type", "lieu", "km", "jour", "heure_debut", "heure_fin", "besoin", "responsable_id",
                "ravitaillement_id", "consignes")


def postes(evenement_id):
    res = _lignes(f"SELECT id, {', '.join(CHAMPS_POSTE)} FROM orga_postes WHERE evenement_id=? "
                  "ORDER BY COALESCE(jour, ''), COALESCE(heure_debut, ''), nom COLLATE NOCASE", ("id",) + CHAMPS_POSTE,
                  (evenement_id,))
    aff = affectations(evenement_id)
    bv = {b["id"]: b for b in benevoles(evenement_id)}
    for p in res:
        p["benevoles"] = [bv[b] for pid, b in aff if pid == p["id"] and b in bv]
        p["libelle_type"] = L.LIBELLE_POSTE.get(p["type"], p["type"] or "")
    return res


def enregistrer_poste(evenement_id, champs, poste_id=None):
    v = {k: champs[k] for k in CHAMPS_POSTE if k in champs}
    if "nom" in v or poste_id is None:
        v["nom"] = (v.get("nom") or "").strip()
        if not v["nom"]:
            raise ErreurLogistique("Donne un nom au poste.")
    if v.get("type") and v["type"] not in L.LIBELLE_POSTE:
        raise ErreurLogistique("Type de poste inconnu.")
    for k in ("heure_debut", "heure_fin"):
        if k in v:
            v[k] = _heure(v[k])
    if "jour" in v:
        v["jour"] = _iso(v["jour"])
    if "besoin" in v:
        v["besoin"] = max(0, int(v["besoin"] or 0))
    if poste_id is None:
        v["evenement_id"] = evenement_id
        return base.inserer("orga_postes", v)
    if v:
        base.ecrire(f"UPDATE orga_postes SET {', '.join(k + '=?' for k in v)} WHERE id=?", tuple(v.values()) + (poste_id,))
    return poste_id


def supprimer_poste(poste_id):
    base.ecrire("DELETE FROM orga_postes WHERE id=?", (poste_id,))


def affectations(evenement_id):
    return [tuple(l) for l in base.lire_tous(
        "SELECT a.poste_id, a.benevole_id FROM orga_affectations a JOIN orga_postes p ON p.id = a.poste_id "
        "WHERE p.evenement_id=? ORDER BY a.id", (evenement_id,))]


def affecter(poste_id, benevole_id):
    """Sans doublon ; renvoie True si l'affectation est nouvelle."""
    if base.lire_un("SELECT 1 FROM orga_affectations WHERE poste_id=? AND benevole_id=?", (poste_id, benevole_id)):
        return False
    base.inserer("orga_affectations", {"poste_id": poste_id, "benevole_id": benevole_id})
    return True


def desaffecter(poste_id, benevole_id):
    base.ecrire("DELETE FROM orga_affectations WHERE poste_id=? AND benevole_id=?", (poste_id, benevole_id))


def creer_postes_suggeres(evenement_id):
    """Postes types (retrait, départ, chrono, PC, ravitaillements, serre-files, balisage, signaleurs, parking,
    buvette) ; ceux qui existent déjà (même nom) ne sont pas recréés. Renvoie le nombre créé."""
    ev = _ev(evenement_id)
    ctx = contexte(evenement_id)
    eps = dor.epreuves(evenement_id)
    rav = ravitaillements(evenement_id)
    noms = {p["nom"].lower() for p in postes(evenement_id)}
    inscrits = dor.chiffres(evenement_id)["total"]["inscrits"]
    n = 0
    veille = (date.fromisoformat(ev["date_debut"]).toordinal() - 1)
    for p in L.postes_suggeres(eps, rav, ctx, inscrits):
        if p["nom"].lower() in noms:
            continue
        jour = date.fromordinal(veille).isoformat() if p.pop("jour_veille", False) else ev["date_debut"]
        enregistrer_poste(evenement_id, {**p, "jour": jour})
        n += 1
    return n


def controle(evenement_id):
    ev = _ev(evenement_id)
    ps = postes(evenement_id)
    for p in ps:
        p["jour"] = p.get("jour") or ev["date_debut"]
    bvs = [b for b in benevoles(evenement_id) if b["statut"] != "desiste"]
    return L.controle_benevoles(ps, bvs, affectations(evenement_id), ev["date_debut"], contexte(evenement_id)["voie_publique"])


def planning_benevole(evenement_id, benevole_id):
    return [p for p in postes(evenement_id) if any(b["id"] == benevole_id for b in p["benevoles"])]


def signaleurs(evenement_id):
    """Pour la préfecture : [{nom, prenom, date_naissance, telephone, permis, poste, lieu, horaires}]."""
    res = []
    for p in postes(evenement_id):
        if p["type"] != "signaleur":
            continue
        for b in p["benevoles"]:
            res.append({**b, "poste": p["nom"], "lieu": p.get("lieu") or "", "km": p.get("km"),
                        "horaires": f"{p.get('heure_debut') or ''} - {p.get('heure_fin') or ''}".strip(" -")})
    return res


# ------------------------------------------------------------------ ravitaillements

CHAMPS_RAVITO = ("nom", "km", "type", "epreuves_json", "ouverture", "barriere_horaire", "lieu", "acces", "eau_seule", "notes")


def _coureurs_par_epreuve(evenement_id):
    """Coureurs attendus par épreuve : le quota, ou les inscrits (non annulés) s'ils sont plus nombreux."""
    ch = {}
    for i in dor.inscriptions(evenement_id):
        if i["statut"] not in ("annulee", "liste_attente"):
            ch[i["epreuve_id"]] = ch.get(i["epreuve_id"], 0) + 1
    return {e["id"]: max(ch.get(e["id"], 0), int(e.get("quota") or 0)) for e in dor.epreuves(evenement_id)}


def ravitaillements(evenement_id, avec_quantites=True):
    res = _lignes(f"SELECT id, {', '.join(CHAMPS_RAVITO)} FROM ravitaillements WHERE evenement_id=? ORDER BY km, nom",
                  ("id",) + CHAMPS_RAVITO, (evenement_id,))
    if not res:
        return res
    ev = _ev(evenement_id)
    ctx = contexte(evenement_id)
    par = _coureurs_par_epreuve(evenement_id)
    noms = {e["id"]: e["nom"] for e in dor.epreuves(evenement_id)}
    ete = date.fromisoformat(ev["date_debut"]).month in (6, 7, 8, 9)
    postes_rav = {}
    for p in base.lire_tous("SELECT p.ravitaillement_id, COUNT(a.id) FROM orga_postes p LEFT JOIN orga_affectations a "
                            "ON a.poste_id = p.id WHERE p.evenement_id=? AND p.ravitaillement_id IS NOT NULL "
                            "GROUP BY p.ravitaillement_id", (evenement_id,)):
        postes_rav[p[0]] = p[1]
    for r in res:
        try:
            ids = json.loads(r["epreuves_json"]) if r["epreuves_json"] else []
        except ValueError:
            ids = []
        r["epreuve_ids"] = [i for i in ids if i in par] or list(par)
        r["epreuves"] = [noms[i] for i in r["epreuve_ids"]]
        r["coureurs"] = sum(par[i] for i in r["epreuve_ids"])
        r["benevoles"] = postes_rav.get(r["id"], 0)
        r["libelle_type"] = L.LIBELLE_RAVITO.get(r["type"], r["type"] or "")
        if avec_quantites:
            r["quantites"] = L.quantites_ravito(r["type"], r["coureurs"], r["km"], ete, ctx["gobelets_fournis"],
                                                r["benevoles"])
    return res


def enregistrer_ravitaillement(evenement_id, champs, ravito_id=None):
    v = {k: champs[k] for k in CHAMPS_RAVITO if k in champs}
    if "epreuve_ids" in champs:
        v["epreuves_json"] = json.dumps([int(i) for i in champs["epreuve_ids"] or []])
    if "nom" in v or ravito_id is None:
        v["nom"] = (v.get("nom") or "").strip()
        if not v["nom"]:
            raise ErreurLogistique("Donne un nom au ravitaillement.")
    if v.get("type") and v["type"] not in L.LIBELLE_RAVITO:
        raise ErreurLogistique("Type de ravitaillement inconnu.")
    for k in ("ouverture", "barriere_horaire"):
        if k in v:
            v[k] = _heure(v[k])
    if v.get("km") is not None:
        v["km"] = float(v["km"])
    if ravito_id is None:
        v["evenement_id"] = evenement_id
        return base.inserer("ravitaillements", v)
    if v:
        base.ecrire(f"UPDATE ravitaillements SET {', '.join(k + '=?' for k in v)} WHERE id=?", tuple(v.values()) + (ravito_id,))
    return ravito_id


def supprimer_ravitaillement(ravito_id):
    base.ecrire("UPDATE orga_postes SET ravitaillement_id=NULL WHERE ravitaillement_id=?", (ravito_id,))
    base.ecrire("UPDATE orga_materiel SET ravitaillement_id=NULL WHERE ravitaillement_id=?", (ravito_id,))
    base.ecrire("DELETE FROM ravitaillements WHERE id=?", (ravito_id,))


def liste_de_courses(evenement_id):
    return L.liste_de_courses(ravitaillements(evenement_id))


# ------------------------------------------------------------------ matériel

CHAMPS_MATERIEL = ("article", "categorie", "quantite", "disponible", "unite", "fournisseur", "cout", "lieu",
                   "ravitaillement_id", "poste_id", "statut", "rendu", "notes")


def materiel(evenement_id):
    res = _lignes(f"SELECT id, {', '.join(CHAMPS_MATERIEL)} FROM orga_materiel WHERE evenement_id=? "
                  "ORDER BY categorie, article COLLATE NOCASE", ("id",) + CHAMPS_MATERIEL, (evenement_id,))
    for m in res:
        m["manque"] = max(0, int(m["quantite"] or 0) - int(m["disponible"] or 0))
    return res


def enregistrer_materiel(evenement_id, champs, materiel_id=None):
    v = {k: champs[k] for k in CHAMPS_MATERIEL if k in champs}
    if "article" in v or materiel_id is None:
        v["article"] = (v.get("article") or "").strip()
        if not v["article"]:
            raise ErreurLogistique("Donne le nom de l'article.")
    if v.get("statut") and v["statut"] not in L.LIBELLE_STATUT_MATERIEL:
        raise ErreurLogistique("Statut inconnu.")
    for k in ("quantite", "disponible"):
        if k in v:
            v[k] = max(0, int(v[k] or 0))
    if v.get("statut") == "rendu":
        v["rendu"] = 1
    if materiel_id is None:
        v["evenement_id"] = evenement_id
        return base.inserer("orga_materiel", v)
    if v:
        base.ecrire(f"UPDATE orga_materiel SET {', '.join(k + '=?' for k in v)} WHERE id=?", tuple(v.values()) + (materiel_id,))
    return materiel_id


def supprimer_materiel(materiel_id):
    base.ecrire("DELETE FROM orga_materiel WHERE id=?", (materiel_id,))


def changer_statut_materiel(ids, statut):
    if statut not in L.LIBELLE_STATUT_MATERIEL:
        raise ErreurLogistique("Statut inconnu.")
    for i in ids:
        base.ecrire("UPDATE orga_materiel SET statut=?, rendu=CASE WHEN ?='rendu' THEN 1 ELSE rendu END WHERE id=?",
                    (statut, statut, i))


def ajouter_materiel_suggere(evenement_id):
    """Liste type ; les articles déjà présents (même nom) ne sont pas ajoutés. Renvoie le nombre ajouté."""
    ctx = contexte(evenement_id)
    deja = {m["article"].lower() for m in materiel(evenement_id)}
    nb_ben = len(benevoles(evenement_id))
    n = 0
    for art, cat, q, u in L.materiel_suggere(dor.epreuves(evenement_id), ravitaillements(evenement_id), ctx, nb_ben):
        if art.lower() in deja:
            continue
        enregistrer_materiel(evenement_id, {"article": art, "categorie": cat, "quantite": q, "unite": u})
        n += 1
    return n


def bilan_materiel(evenement_id):
    ms = materiel(evenement_id)
    return {"articles": len(ms), "manquants": sum(1 for m in ms if m["manque"]),
            "a_trouver": sum(1 for m in ms if m["statut"] in ("a_trouver", "demande")),
            "a_rendre": sum(1 for m in ms if m.get("fournisseur") and not m["rendu"]),
            "cout": round(sum(float(m["cout"] or 0) for m in ms), 2)}


# ------------------------------------------------------------------ partenaires

CHAMPS_PARTENAIRE = ("nom", "type", "particulier", "contact", "email", "telephone", "adresse", "siren", "montant",
                     "valeur_nature", "description_nature", "contreparties", "statut", "date_contact", "date_relance",
                     "date_versement", "mode_versement", "recu_numero", "notes")


def partenaires(evenement_id):
    res = _lignes(f"SELECT id, {', '.join(CHAMPS_PARTENAIRE)} FROM partenaires WHERE evenement_id=? "
                  "ORDER BY statut = 'refus', nom COLLATE NOCASE", ("id",) + CHAMPS_PARTENAIRE, (evenement_id,))
    auj = date.today().isoformat()
    for p in res:
        p["a_relancer"] = bool(p["date_relance"] and p["date_relance"] <= auj and p["statut"] in ("contacte", "relance"))
        p["recu_possible"] = p["type"] in ("mecenat", "nature") and p["statut"] == "verse"
    return res


def partenaire(partenaire_id):
    r = _lignes(f"SELECT id, evenement_id, {', '.join(CHAMPS_PARTENAIRE)} FROM partenaires WHERE id=?",
                ("id", "evenement_id") + CHAMPS_PARTENAIRE, (partenaire_id,))
    return r[0] if r else None


def enregistrer_partenaire(evenement_id, champs, partenaire_id=None):
    v = {k: champs[k] for k in CHAMPS_PARTENAIRE if k in champs and k != "recu_numero"}
    if "nom" in v or partenaire_id is None:
        v["nom"] = (v.get("nom") or "").strip()
        if not v["nom"]:
            raise ErreurLogistique("Donne le nom du partenaire.")
    if v.get("type") and v["type"] not in L.LIBELLE_PARTENAIRE:
        raise ErreurLogistique("Type de partenaire inconnu.")
    if v.get("statut") and v["statut"] not in L.LIBELLE_STATUT_PARTENAIRE:
        raise ErreurLogistique("Statut inconnu.")
    for k in ("date_contact", "date_relance", "date_versement"):
        if k in v:
            v[k] = _iso(v[k])
    if "particulier" in v:
        v["particulier"] = 1 if v["particulier"] else 0
    if partenaire_id is None:
        v["evenement_id"] = evenement_id
        return base.inserer("partenaires", v)
    if v:
        base.ecrire(f"UPDATE partenaires SET {', '.join(k + '=?' for k in v)} WHERE id=?", tuple(v.values()) + (partenaire_id,))
    return partenaire_id


def supprimer_partenaire(partenaire_id):
    base.ecrire("DELETE FROM partenaires WHERE id=?", (partenaire_id,))


def emettre_recu(partenaire_id):
    """Numéro de reçu de don (mécénat versé) : attribué une seule fois, à la suite de l'année. Renvoie le partenaire."""
    p = partenaire(partenaire_id)
    if not p:
        raise ErreurLogistique("Partenaire introuvable.")
    if p["type"] not in ("mecenat", "nature"):
        raise ErreurLogistique("Un reçu fiscal ne se fait que pour un don (mécénat) ; le parrainage se facture.")
    if p["statut"] != "verse":
        raise ErreurLogistique("Le don doit être reçu (statut « Versé / reçu ») avant le reçu fiscal.")
    if not p["recu_numero"]:
        annee = (p["date_versement"] or date.today().isoformat())[:4]
        n = base.lire_un("SELECT COUNT(*) FROM partenaires WHERE recu_numero LIKE ?", (f"DON-{annee}-%",))[0]
        p["recu_numero"] = L.numero_recu(int(annee), n + 1)
        base.ecrire("UPDATE partenaires SET recu_numero=? WHERE id=?", (p["recu_numero"], partenaire_id))
    return p


# ------------------------------------------------------------------ budget

CHAMPS_BUDGET = ("sens", "categorie", "libelle", "prevu", "realise", "par_coureur", "notes")


def lignes_budget(evenement_id):
    return _lignes(f"SELECT id, {', '.join(CHAMPS_BUDGET)} FROM budget_lignes WHERE evenement_id=? "
                   "ORDER BY sens DESC, categorie, libelle", ("id",) + CHAMPS_BUDGET, (evenement_id,))


def enregistrer_ligne_budget(evenement_id, champs, ligne_id=None):
    v = {k: champs[k] for k in CHAMPS_BUDGET if k in champs}
    if (ligne_id is None or "sens" in v) and v.get("sens") not in ("recette", "depense"):
        raise ErreurLogistique("Recette ou dépense ?")
    if "libelle" in v or ligne_id is None:
        v["libelle"] = (v.get("libelle") or "").strip()
        if not v["libelle"]:
            raise ErreurLogistique("Donne un libellé.")
    if "par_coureur" in v:
        v["par_coureur"] = 1 if v["par_coureur"] else 0
    if ligne_id is None:
        v["evenement_id"] = evenement_id
        return base.inserer("budget_lignes", v)
    if v:
        base.ecrire(f"UPDATE budget_lignes SET {', '.join(k + '=?' for k in v)} WHERE id=?", tuple(v.values()) + (ligne_id,))
    return ligne_id


def supprimer_ligne_budget(ligne_id):
    base.ecrire("DELETE FROM budget_lignes WHERE id=?", (ligne_id,))


def tarif_moyen(evenement_id):
    ins = [i for i in dor.inscriptions(evenement_id) if i["statut"] != "annulee" and i.get("montant")]
    if ins:
        return round(sum(float(i["montant"]) for i in ins) / len(ins), 2)
    eps = [e for e in dor.epreuves(evenement_id) if e.get("tarif")]
    if not eps:
        return 0
    poids = [(float(e["tarif"]), int(e.get("quota") or 1)) for e in eps]
    return round(sum(t * q for t, q in poids) / sum(q for _t, q in poids), 2)


def bilan(evenement_id):
    ch = dor.chiffres(evenement_id)["total"]
    ctx = contexte(evenement_id)
    attendus = sum(_coureurs_par_epreuve(evenement_id).values()) or ctx["participants"] or ch["inscrits"]
    tm = tarif_moyen(evenement_id)
    b = L.bilan_budget(lignes_budget(evenement_id), ch["recette"], partenaires(evenement_id), attendus,
                       round(attendus * tm, 2))
    b["tarif_moyen"] = tm
    b["attendus"] = attendus
    b["seuil"] = L.seuil_rentabilite(b["fixe"], b["variable_par_coureur"], b["tarif_moyen"], b["autres_recettes"])
    b["inscrits"] = ch["inscrits"]
    return b


# ------------------------------------------------------------------ vue d'ensemble

def tableau(evenement_id, aujourdhui=None):
    """Chiffres de la logistique pour le tableau de bord et la page Claude."""
    ds = demarches(evenement_id, aujourdhui=aujourdhui)
    ctl = controle(evenement_id)
    rav = ravitaillements(evenement_id)
    ctx = contexte(evenement_id)
    ps = partenaires(evenement_id)
    b = bilan(evenement_id)
    return {"demarches": L.bilan_demarches(ds, aujourdhui), "en_retard": [d for d in ds if d["etat"] == "en retard"],
            "prochaines": [d for d in ds if d["etat"] in ("bientôt", "à venir")][:5],
            "benevoles": len([x for x in benevoles(evenement_id) if x["statut"] != "desiste"]),
            "besoin": ctl["besoin"], "pourvus": ctl["pourvus"], "manques": ctl["manques"], "conflits": ctl["conflits"],
            "alertes": ctl["alertes"], "ravitaillements": len(rav), "materiel": bilan_materiel(evenement_id),
            "partenaires": {"total": len(ps), "accords": sum(1 for p in ps if p["statut"] in ("accord", "verse")),
                            "a_relancer": sum(1 for p in ps if p["a_relancer"]),
                            "montant": round(sum(float(p["montant"] or 0) + float(p["valeur_nature"] or 0) for p in ps
                                                 if p["statut"] in ("accord", "verse")), 2)},
            "budget": {k: b[k] for k in ("recettes_prevues", "depenses_prevues", "solde_prevu", "recettes_realisees",
                                         "depenses_realisees", "solde_realise", "seuil", "tarif_moyen")},
            "dps": L.dps(ctx["spectateurs"], ctx["dps_activite"], ctx["dps_environnement"], ctx["dps_delai"])}
