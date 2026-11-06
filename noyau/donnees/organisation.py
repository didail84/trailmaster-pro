"""
Accès aux données de l'organisation (étape 4.4) : événements, épreuves,
inscriptions (saisie, import Njuko ou CSV, adhérents du club), dossards,
publication de l'événement dans le calendrier des courses.
Les règles (âge et distance, santé, tarifs) sont dans
noyau/organisation/regles.py.
"""

import csv
import io
import re
from datetime import date

from noyau.donnees import base, club as dclub
from noyau.organisation import regles as R
from noyau.club import categories as cat, imports as imp


class ErreurOrganisation(Exception):
    """Message lisible ; rien n'a été modifié."""


CHAMPS_EVENEMENT = ("club_id", "nom", "date_debut", "date_fin", "commune", "code_postal", "lieu", "site", "contact_email",
                    "description", "statut", "declaration_ffa", "ouverture_inscriptions", "cloture_inscriptions",
                    "date_tarif_tardif", "pps_validite_mois", "autorisation_parentale", "notes")
CHAMPS_EPREUVE = ("nom", "discipline", "distance_km", "denivele_m", "date", "heure_depart", "quota", "tarif",
                  "tarif_licencie", "tarif_tardif", "dossard_debut", "dossard_fin", "categorie_min", "competitive", "notes",
                  "depart_reel")
CHAMPS_INSCRIPTION = ("epreuve_id", "personne_id", "nom", "prenom", "sexe", "date_naissance", "nationalite", "email",
                      "telephone", "club", "justificatif", "numero_licence", "type_licence", "federation", "pps_date",
                      "certificat_date", "questionnaire_mineur", "autorisation_parentale", "justificatif_valide",
                      "contact_urgence_nom", "contact_urgence_tel", "taille_tshirt", "statut", "dossard", "montant",
                      "montant_paye", "paiement_mode", "date_inscription", "source", "ref_externe", "dossard_retire",
                      "notes")


def _iso(d):
    if not d:
        return None
    try:
        return date.fromisoformat(str(d)[:10]).isoformat()
    except ValueError:
        v = imp.normaliser_date(str(d))
        if not v:
            raise ErreurOrganisation(f"Date illisible : {d}.")
        return v


# ------------------------------------------------------------------ événements

def evenements():
    cles = ("id",) + CHAMPS_EVENEMENT
    res = [dict(zip(cles, l)) for l in base.lire_tous(
        f"SELECT id, {', '.join(CHAMPS_EVENEMENT)} FROM evenements ORDER BY date_debut DESC")]
    for e in res:
        e["nb_inscrits"] = base.lire_un("SELECT COUNT(*) FROM inscriptions i JOIN epreuves p ON p.id = i.epreuve_id "
                                        "WHERE p.evenement_id=? AND i.statut != 'annulee'", (e["id"],))[0]
    return res


def evenement(evenement_id):
    return next((e for e in evenements() if e["id"] == evenement_id), None)


def enregistrer_evenement(champs, evenement_id=None):
    v = {k: champs.get(k) for k in CHAMPS_EVENEMENT if k in champs}
    if "nom" in v or evenement_id is None:
        v["nom"] = (v.get("nom") or "").strip()
        if not v["nom"]:
            raise ErreurOrganisation("Donne un nom à l'événement.")
    if evenement_id is None and not v.get("date_debut"):
        raise ErreurOrganisation("Donne la date de l'événement.")
    for k in ("date_debut", "date_fin", "ouverture_inscriptions", "cloture_inscriptions", "date_tarif_tardif"):
        if k in v:
            v[k] = _iso(v[k])
    if v.get("statut") and v["statut"] not in R.LIBELLE_STATUT_EVENEMENT:
        raise ErreurOrganisation("Statut inconnu.")
    if v.get("code_postal") and not re.fullmatch(r"\d{5}", str(v["code_postal"]).strip()):
        raise ErreurOrganisation("Code postal illisible.")
    if evenement_id is None:
        v.setdefault("club_id", (dclub.club_principal() or {}).get("id"))
        return base.inserer("evenements", {"statut": v.pop("statut", None) or "brouillon", **v})
    if v:
        base.ecrire(f"UPDATE evenements SET {', '.join(k + '=?' for k in v)} WHERE id=?", tuple(v.values()) + (evenement_id,))
    return evenement_id


def supprimer_evenement(evenement_id):
    base.ecrire("DELETE FROM evenements WHERE id=?", (evenement_id,))


# ------------------------------------------------------------------ épreuves

def epreuves(evenement_id):
    cles = ("id", "evenement_id") + CHAMPS_EPREUVE
    res = [dict(zip(cles, l)) for l in base.lire_tous(
        f"SELECT id, evenement_id, {', '.join(CHAMPS_EPREUVE)} FROM epreuves WHERE evenement_id=? "
        "ORDER BY COALESCE(date, ''), heure_depart, distance_km DESC", (evenement_id,))]
    for e in res:
        e["km_effort"] = R.km_effort(e["distance_km"], e["denivele_m"])
        e["nb_inscrits"] = base.lire_un("SELECT COUNT(*) FROM inscriptions WHERE epreuve_id=? AND statut != 'annulee'",
                                        (e["id"],))[0]
    return res


def epreuve(epreuve_id):
    l = base.lire_un("SELECT evenement_id FROM epreuves WHERE id=?", (epreuve_id,))
    return next((e for e in epreuves(l[0]) if e["id"] == epreuve_id), None) if l else None


def enregistrer_epreuve(evenement_id, champs, epreuve_id=None):
    v = {k: champs.get(k) for k in CHAMPS_EPREUVE if k in champs}
    if "nom" in v or epreuve_id is None:
        v["nom"] = (v.get("nom") or "").strip()
        if not v["nom"]:
            raise ErreurOrganisation("Donne un nom à l'épreuve (par exemple « Trail 25 km »).")
    if v.get("discipline") and v["discipline"] not in R.LIBELLE_DISCIPLINE:
        raise ErreurOrganisation("Discipline inconnue.")
    if "date" in v:
        v["date"] = _iso(v["date"])
    for k in ("distance_km", "tarif", "tarif_licencie", "tarif_tardif"):
        if v.get(k) is not None and float(v[k]) < 0:
            raise ErreurOrganisation("Les distances et les tarifs ne peuvent pas être négatifs.")
    a, b = v.get("dossard_debut"), v.get("dossard_fin")
    if a and b and int(b) < int(a):
        raise ErreurOrganisation("La plage de dossards est à l'envers.")
    if epreuve_id is None:
        return base.inserer("epreuves", {"evenement_id": evenement_id, "discipline": v.pop("discipline", None) or "trail",
                                         **v})
    if v:
        base.ecrire(f"UPDATE epreuves SET {', '.join(k + '=?' for k in v)} WHERE id=?", tuple(v.values()) + (epreuve_id,))
    return epreuve_id


def supprimer_epreuve(epreuve_id):
    if base.lire_un("SELECT 1 FROM inscriptions WHERE epreuve_id=? AND statut != 'annulee'", (epreuve_id,)):
        raise ErreurOrganisation("Cette épreuve a des inscrits : annule-les ou déplace-les d'abord.")
    base.ecrire("DELETE FROM epreuves WHERE id=?", (epreuve_id,))


# ------------------------------------------------------------------ inscriptions

def _evenement_de_l_epreuve(epreuve_id):
    l = base.lire_un("SELECT evenement_id FROM epreuves WHERE id=?", (epreuve_id,))
    return evenement(l[0]) if l else None


def inscriptions(evenement_id, epreuve_id=None):
    cles = ("id",) + CHAMPS_INSCRIPTION + ("epreuve",)
    sql = (f"SELECT i.id, {', '.join('i.' + c for c in CHAMPS_INSCRIPTION)}, p.nom FROM inscriptions i "
           "JOIN epreuves p ON p.id = i.epreuve_id WHERE p.evenement_id=?")
    par = [evenement_id]
    if epreuve_id:
        sql += " AND i.epreuve_id=?"
        par.append(epreuve_id)
    sql += " ORDER BY i.nom COLLATE NOCASE, i.prenom COLLATE NOCASE"
    ev = evenement(evenement_id)
    eps = {e["id"]: e for e in epreuves(evenement_id)}
    res = []
    for l in base.lire_tous(sql, tuple(par)):
        i = dict(zip(cles, l))
        i["dossier"] = R.dossier(i, eps[i["epreuve_id"]], ev)
        res.append(i)
    return res


def inscription(inscription_id):
    l = base.lire_un("SELECT p.evenement_id FROM inscriptions i JOIN epreuves p ON p.id = i.epreuve_id WHERE i.id=?",
                     (inscription_id,))
    return next((i for i in inscriptions(l[0]) if i["id"] == inscription_id), None) if l else None


def _preparer(v, epreuve_id):
    if "nom" in v:
        v["nom"] = (v.get("nom") or "").strip()
        if not v["nom"]:
            raise ErreurOrganisation("Le nom est obligatoire.")
    for k in ("date_naissance", "pps_date", "certificat_date", "date_inscription"):
        if v.get(k):
            v[k] = _iso(v[k])
    if v.get("statut") and v["statut"] not in R.LIBELLE_STATUT:
        raise ErreurOrganisation("Statut inconnu.")
    if v.get("justificatif") and v["justificatif"] not in R.LIBELLE_JUSTIFICATIF:
        raise ErreurOrganisation("Justificatif inconnu.")
    if v.get("numero_licence"):
        v["numero_licence"] = "".join(str(v["numero_licence"]).split())
    if v.get("dossard"):
        ev = _evenement_de_l_epreuve(epreuve_id)
        l = base.lire_un("SELECT i.id FROM inscriptions i JOIN epreuves p ON p.id = i.epreuve_id WHERE p.evenement_id=? "
                         "AND i.dossard=? AND i.statut != 'annulee'", (ev["id"], int(v["dossard"])))
        if l and l[0] != v.get("_id"):
            raise ErreurOrganisation(f"Le dossard {v['dossard']} est déjà attribué.")
    v.pop("_id", None)
    return v


def enregistrer_inscription(champs, inscription_id=None):
    """Crée ou modifie une inscription. Le montant est calculé selon le tarif de l'épreuve s'il n'est pas donné."""
    v = {k: champs.get(k) for k in CHAMPS_INSCRIPTION if k in champs}
    epreuve_id = v.get("epreuve_id") or (base.lire_un("SELECT epreuve_id FROM inscriptions WHERE id=?",
                                                      (inscription_id,)) or [None])[0]
    if not epreuve_id:
        raise ErreurOrganisation("Choisis l'épreuve.")
    v = _preparer({**v, "_id": inscription_id}, epreuve_id)
    if inscription_id is None:
        e, ev = epreuve(epreuve_id), _evenement_de_l_epreuve(epreuve_id)
        if v.get("montant") is None:
            v["montant"] = R.tarif(e, v.get("justificatif") == "licence_ffa", v.get("date_inscription"),
                                   ev.get("date_tarif_tardif"))
        v.setdefault("date_inscription", date.today().isoformat())
        if not v.get("statut"):
            plein = e.get("quota") and e["nb_inscrits"] >= e["quota"]
            v["statut"] = "liste_attente" if plein else "en_attente"
        if base.lire_un("SELECT 1 FROM inscriptions WHERE epreuve_id=? AND nom=? COLLATE NOCASE AND "
                        "COALESCE(prenom,'')=? COLLATE NOCASE AND COALESCE(date_naissance,'')=? AND statut != 'annulee'",
                        (epreuve_id, v["nom"], v.get("prenom") or "", v.get("date_naissance") or "")):
            raise ErreurOrganisation(f"{v.get('prenom') or ''} {v['nom']} est déjà inscrit(e) à cette épreuve.")
        return base.inserer("inscriptions", v)
    if v:
        base.ecrire(f"UPDATE inscriptions SET {', '.join(k + '=?' for k in v)} WHERE id=?", tuple(v.values()) +
                    (inscription_id,))
    return inscription_id


def changer_statut(inscription_ids, statut):
    if statut not in R.LIBELLE_STATUT:
        raise ErreurOrganisation("Statut inconnu.")
    for i in inscription_ids:
        base.ecrire("UPDATE inscriptions SET statut=?" + (", dossard=NULL" if statut == "annulee" else "") + " WHERE id=?",
                    (statut, i))


def enregistrer_paiement(inscription_id, montant, mode=None):
    i = inscription(inscription_id)
    if not i:
        raise ErreurOrganisation("Inscription introuvable.")
    if montant is None or montant <= 0:
        raise ErreurOrganisation("Le montant doit être positif.")
    base.ecrire("UPDATE inscriptions SET montant_paye=?, paiement_mode=? WHERE id=?",
                (round((i["montant_paye"] or 0) + montant, 2), mode or i["paiement_mode"], inscription_id))


def marquer_retrait(inscription_id, retire=True):
    base.ecrire("UPDATE inscriptions SET dossard_retire=? WHERE id=?", (1 if retire else 0, inscription_id))


def supprimer_inscription(inscription_id):
    base.ecrire("DELETE FROM inscriptions WHERE id=?", (inscription_id,))


def valider_complets(evenement_id):
    """Passe en « Validée » les inscriptions en attente dont le dossier est complet. Renvoie le nombre."""
    ids = [i["id"] for i in inscriptions(evenement_id) if i["statut"] == "en_attente" and i["dossier"]["complet"]]
    changer_statut(ids, "validee")
    return len(ids)


# ------------------------------------------------------------------ dossards

def attribuer_dossards(evenement_id, epreuve_id=None, ordre="nom"):
    """Donne un numéro libre de la plage de l'épreuve à chaque inscription validée sans dossard.
    ordre : « nom » ou « inscription ». Renvoie {attribues, sans_place: [épreuves dont la plage est pleine]}."""
    eps = [e for e in epreuves(evenement_id) if epreuve_id is None or e["id"] == epreuve_id]
    croisees = R.chevauchements(epreuves(evenement_id))
    if croisees:
        raise ErreurOrganisation("Plages de dossards qui se chevauchent : " +
                                 ", ".join(f"{a} et {b}" for a, b in croisees) + ".")
    pris = {r[0] for r in base.lire_tous("SELECT i.dossard FROM inscriptions i JOIN epreuves p ON p.id = i.epreuve_id "
                                         "WHERE p.evenement_id=? AND i.dossard IS NOT NULL AND i.statut != 'annulee'",
                                         (evenement_id,))}
    n, pleines = 0, []
    with base.transaction() as cur:
        for e in eps:
            if not e.get("dossard_debut") or not e.get("dossard_fin"):
                pleines.append(f"{e['nom']} (pas de plage de dossards)")
                continue
            tri = "i.nom COLLATE NOCASE, i.prenom COLLATE NOCASE" if ordre == "nom" else "i.date_inscription, i.id"
            a_faire = [r[0] for r in cur.execute(f"SELECT i.id FROM inscriptions i WHERE i.epreuve_id=? AND "
                                                 f"i.statut='validee' AND i.dossard IS NULL ORDER BY {tri}", (e["id"],))]
            libres = R.numeros_libres(e["dossard_debut"], e["dossard_fin"], pris)
            for iid in a_faire:
                num = next(libres, None)
                if num is None:
                    pleines.append(e["nom"])
                    break
                cur.execute("UPDATE inscriptions SET dossard=? WHERE id=?", (num, iid))
                pris.add(num)
                n += 1
    return {"attribues": n, "sans_place": pleines}


def retirer_dossards(evenement_id, epreuve_id=None):
    sql = ("UPDATE inscriptions SET dossard=NULL WHERE dossard_retire=0 AND dossard IS NOT NULL AND epreuve_id IN "
           "(SELECT id FROM epreuves WHERE evenement_id=?)")
    p = [evenement_id]
    if epreuve_id:
        sql += " AND epreuve_id=?"
        p.append(epreuve_id)
    return base.ecrire_compte(sql, tuple(p))


# ------------------------------------------------------------------ import Njuko, CSV

SYNONYMES = {
    "nom": ("nom", "nom de famille", "last name", "participant nom"),
    "prenom": ("prenom", "first name", "participant prenom"),
    "sexe": ("sexe", "genre", "civilite"),
    "date_naissance": ("date de naissance", "naissance", "ne le", "date naissance", "birth date"),
    "nationalite": ("nationalite", "pays"),
    "email": ("email", "e-mail", "mail", "adresse email"),
    "telephone": ("telephone", "portable", "tel", "mobile"),
    "club": ("club", "club / association", "association", "equipe"),
    "numero_licence": ("numero de licence", "n° licence", "licence", "numero licence", "n° de licence"),
    "epreuve": ("epreuve", "course", "formule", "parcours", "distance", "billet", "tarif"),
    "montant": ("montant", "prix", "montant paye", "total", "montant total"),
    "pps": ("pps", "numero pps", "pass prevention sante", "n° pps"),
    "certificat": ("certificat", "certificat medical", "date du certificat"),
    "contact_urgence_nom": ("contact d'urgence", "personne a prevenir", "nom contact urgence"),
    "contact_urgence_tel": ("telephone d'urgence", "tel urgence", "telephone contact urgence"),
    "taille_tshirt": ("taille", "taille t-shirt", "taille tee-shirt", "t-shirt"),
    "statut_commande": ("statut", "etat", "statut de la commande"),
    "ref": ("numero de commande", "reference", "id", "n° dossier", "numero d'inscription"),
}


def analyser_import(contenu, nom_fichier, evenement_id):
    """Lit un export Njuko, HelloAsso ou un tableau d'inscrits. Renvoie {lignes: [{inscription, epreuve_id,
    erreurs}], colonnes, epreuves_inconnues}."""
    lignes = imp.lire_tableau(contenu, nom_fichier)
    if not lignes:
        return {"lignes": [], "colonnes": {}, "epreuves_inconnues": []}
    debut = next((k for k, l in enumerate(lignes[:10]) if any(imp._cle(c).startswith("nom") for c in l)), 0)
    entetes = [imp._cle(c) for c in lignes[debut]]
    corr = {}
    for champ, noms in SYNONYMES.items():
        for i, c in enumerate(entetes):
            if i not in corr.values() and (c in noms or any(c.startswith(n) for n in noms if len(n) > 4)):
                corr[champ] = i
                break
    eps = epreuves(evenement_id)
    res, inconnues = [], set()
    for l in lignes[debut + 1:]:
        def v(k):
            i = corr.get(k)
            return l[i].strip() if i is not None and i < len(l) else ""
        if not v("nom"):
            continue
        st = imp._cle(v("statut_commande"))
        if st and any(m in st for m in ("rembours", "annul", "refus", "echou")):
            continue
        erreurs = []
        e = _epreuve_correspondante(v("epreuve"), eps)
        if e is None:
            if len(eps) == 1:
                e = eps[0]
            else:
                inconnues.add(v("epreuve") or "(vide)")
                erreurs.append(f"épreuve inconnue : {v('epreuve') or '(vide)'}")
        naiss = imp.normaliser_date(v("date_naissance")) if v("date_naissance") else None
        if v("date_naissance") and not naiss:
            erreurs.append(f"date de naissance illisible ({v('date_naissance')})")
        lic = re.sub(r"\s", "", v("numero_licence"))
        i = {"nom": v("nom"), "prenom": v("prenom"), "sexe": imp.sexe_depuis(v("sexe")), "date_naissance": naiss,
             "nationalite": v("nationalite") or None, "email": v("email") or None, "telephone": v("telephone") or None,
             "club": v("club") or None, "numero_licence": lic or None,
             "justificatif": "licence_ffa" if lic else ("pps" if v("pps") else ("certificat" if v("certificat") else None)),
             "pps_date": None, "contact_urgence_nom": v("contact_urgence_nom") or None,
             "contact_urgence_tel": v("contact_urgence_tel") or None, "taille_tshirt": v("taille_tshirt") or None,
             "montant": imp.montant(v("montant")), "ref_externe": v("ref") or None}
        if i["montant"]:
            i["montant_paye"] = i["montant"]
        if v("pps"):
            i["notes"] = f"PPS : {v('pps')}"
        res.append({"inscription": i, "epreuve_id": e["id"] if e else None, "erreurs": erreurs})
    return {"lignes": res, "colonnes": {k: lignes[debut][i] for k, i in corr.items()},
            "epreuves_inconnues": sorted(inconnues)}


def _epreuve_correspondante(texte, eps):
    t = imp._cle(texte)
    if not t:
        return None
    for e in eps:
        if imp._cle(e["nom"]) == t:
            return e
    nums = re.findall(r"\d+(?:[.,]\d+)?", t)
    for e in eps:
        if nums and e.get("distance_km") and any(abs(float(n.replace(",", ".")) - e["distance_km"]) < 0.6 for n in nums):
            return e
    for e in eps:
        if imp._cle(e["nom"]) in t or t in imp._cle(e["nom"]):
            return e
    return None


def importer(lignes, source="import"):
    """Ajoute les inscriptions analysées (sans doublon : même épreuve, nom, prénom et naissance ; ou même
    référence de commande). Renvoie {ajoutees, deja, erreurs}."""
    ajout, deja, erreurs = 0, 0, []
    for l in lignes:
        if not l["epreuve_id"]:
            erreurs.append(f"{l['inscription']['prenom']} {l['inscription']['nom']} : épreuve inconnue")
            continue
        i = l["inscription"]
        if i.get("ref_externe") and base.lire_un("SELECT 1 FROM inscriptions WHERE ref_externe=? AND epreuve_id=?",
                                                 (i["ref_externe"], l["epreuve_id"])):
            deja += 1
            continue
        try:
            enregistrer_inscription({**i, "epreuve_id": l["epreuve_id"], "source": source})
            ajout += 1
        except ErreurOrganisation as e:
            if "déjà inscrit" in str(e):
                deja += 1
            else:
                erreurs.append(f"{i['prenom']} {i['nom']} : {e}")
    return {"ajoutees": ajout, "deja": deja, "erreurs": erreurs}


def inscrire_adherents(epreuve_id, personne_ids, saison=None):
    """Inscrit des adhérents du club : identité, licence et contact d'urgence repris de leur fiche."""
    ev = _evenement_de_l_epreuve(epreuve_id)
    saison = saison or cat.saison_de(ev["date_debut"])
    club = dclub.club_principal() or {}
    n, erreurs = 0, []
    adh = {a["personne_id"]: a for a in dclub.adhesions(club.get("id"), saison)} if club else {}
    from noyau.donnees import personnes as dper
    for pid in personne_ids:
        p = dper.fiche(pid)
        a = adh.get(pid, {})
        lic = a.get("numero_licence")
        try:
            enregistrer_inscription({"epreuve_id": epreuve_id, "personne_id": pid, "nom": p["nom"], "prenom": p["prenom"],
                                     "sexe": p.get("sexe"), "date_naissance": p.get("date_naissance"), "email": p.get("email"),
                                     "telephone": p.get("telephone"), "club": club.get("nom"),
                                     "justificatif": "licence_ffa" if lic else None, "numero_licence": lic,
                                     "type_licence": a.get("type_licence"), "justificatif_valide": 1 if lic else 0,
                                     "autorisation_parentale": a.get("autorisation_parentale") or 0,
                                     "contact_urgence_nom": p.get("contact_urgence_nom"),
                                     "contact_urgence_tel": p.get("contact_urgence_tel"), "source": "club"})
            n += 1
        except ErreurOrganisation as e:
            erreurs.append(f"{p['prenom']} {p['nom']} : {e}")
    return {"ajoutees": n, "erreurs": erreurs}


# ------------------------------------------------------------------ exports, chiffres, calendrier

def export_csv(liste, pour="depart"):
    """Liste de départ (dossard, identité, catégorie, club, épreuve) ou liste complète ; CSV ; UTF-8 avec BOM."""
    out = io.StringIO()
    w = csv.writer(out, delimiter=";")
    if pour == "depart":
        w.writerow(["Dossard", "Nom", "Prénom", "Sexe", "Catégorie", "Naissance", "Club", "Licence", "Épreuve"])
        for i in sorted(liste, key=lambda x: (x.get("dossard") or 10 ** 9, x["nom"].lower())):
            c = i["dossier"]["categorie"]
            w.writerow([i.get("dossard") or "", i["nom"], i.get("prenom") or "", i.get("sexe") or "",
                        f"{c['code']}{(i.get('sexe') or '')[:1]}" if c else "", i.get("date_naissance") or "",
                        i.get("club") or "", i.get("numero_licence") or "", i["epreuve"]])
    else:
        w.writerow(["Épreuve", "Statut", "Dossard", "Nom", "Prénom", "Sexe", "Naissance", "Catégorie", "Club", "E-mail",
                    "Téléphone", "Justificatif", "N° licence", "Montant", "Payé", "Dossier", "À prévenir", "Tél. à prévenir"])
        for i in liste:
            c = i["dossier"]["categorie"]
            w.writerow([i["epreuve"], R.LIBELLE_STATUT.get(i["statut"], ""), i.get("dossard") or "", i["nom"],
                        i.get("prenom") or "", i.get("sexe") or "", i.get("date_naissance") or "", c["code"] if c else "",
                        i.get("club") or "", i.get("email") or "", i.get("telephone") or "",
                        R.LIBELLE_JUSTIFICATIF.get(i.get("justificatif"), ""), i.get("numero_licence") or "",
                        i.get("montant") or "", i.get("montant_paye") or "",
                        "complet" if i["dossier"]["complet"] else ", ".join(i["dossier"]["manques"]),
                        i.get("contact_urgence_nom") or "", i.get("contact_urgence_tel") or ""])
    return "﻿" + out.getvalue()


def chiffres(evenement_id):
    return R.chiffres(inscriptions(evenement_id), epreuves(evenement_id))


def publier_dans_le_calendrier(evenement_id):
    """Ajoute ou met à jour l'événement dans le calendrier des courses (source « Mon organisation »)."""
    from noyau.donnees import calendrier as dcal
    ev = evenement(evenement_id)
    if not ev:
        raise ErreurOrganisation("Événement introuvable.")
    eps = epreuves(evenement_id)
    disc = {"route": "route", "cross": "cross", "montagne": "montagne", "marche_nordique": "marche_nordique"}
    sid = dcal.source_de_type("organisation", "Mon organisation")
    courses = [{"nom": ev["nom"], "date_debut": ev["date_debut"], "date_fin": ev["date_fin"], "commune": ev["commune"],
                "code_postal": ev["code_postal"], "site": ev["site"], "organisateur": (dclub.club_principal() or {}).get("nom"),
                "statut": "annulee" if ev["statut"] == "annule" else "prevue", "ref_externe": f"evenement-{evenement_id}",
                "epreuves": [{"nom": e["nom"], "distance_km": e["distance_km"], "denivele_m": e["denivele_m"],
                              "heure_depart": e["heure_depart"], "prix": e["tarif"],
                              "discipline": disc.get(e["discipline"])} for e in eps if e["discipline"] != "randonnee"]}]
    r = dcal.enregistrer_courses(courses, sid, "Mon organisation")
    l = base.lire_un("SELECT id FROM calendrier_courses WHERE ref_externe=?", (f"evenement-{evenement_id}",))
    if l:
        base.ecrire("UPDATE calendrier_courses SET evenement_id=? WHERE id=?", (evenement_id, l[0]))
    base.ecrire("UPDATE calendrier_sources SET nb_courses=(SELECT COUNT(*) FROM calendrier_courses WHERE source_id=?), "
                "derniere_maj=datetime('now', 'localtime') WHERE id=?", (sid, sid))
    return r
