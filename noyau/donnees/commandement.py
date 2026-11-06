"""
Accès aux données du jour de course (étape 6) : points de contrôle et
pointages, situation des coureurs, incidents (dont ceux envoyés plus tard
par un téléphone sans réseau, sans doublon), présence des bénévoles à leur
poste, positions des coureurs et page publique de suivi (Trail Live).
Les règles sont dans noyau/organisation/commandement.py.
"""

import json
import secrets
from datetime import datetime

from noyau.donnees import base, organisation as dor, chrono as dch
from noyau.organisation import commandement as K


class ErreurCommandement(Exception):
    """Message lisible ; rien n'a été modifié."""


def _heure(h):
    if not h:
        return None
    from noyau.donnees.logistique import _heure as hl, ErreurLogistique
    try:
        return hl(h)
    except ErreurLogistique as e:
        raise ErreurCommandement(str(e))


# ------------------------------------------------------------------ points de contrôle

CHAMPS_POINT = ("nom", "type", "km", "epreuves_json", "barriere_horaire", "lat", "lon", "ravitaillement_id", "poste_id", "notes")


def points(evenement_id):
    res = [dict(zip(("id",) + CHAMPS_POINT, l)) for l in base.lire_tous(
        f"SELECT id, {', '.join(CHAMPS_POINT)} FROM points_controle WHERE evenement_id=? ORDER BY km, id", (evenement_id,))]
    for p in res:
        try:
            p["epreuve_ids"] = json.loads(p["epreuves_json"]) if p["epreuves_json"] else []
        except ValueError:
            p["epreuve_ids"] = []
        p["cle"] = K.cle_point(p["id"])
        p["libelle_type"] = K.LIBELLE_POINT.get(p["type"], "")
    return res


def point(point_id):
    l = base.lire_un("SELECT evenement_id FROM points_controle WHERE id=?", (point_id,))
    return next((p for p in points(l[0]) if p["id"] == point_id), None) if l else None


def enregistrer_point(evenement_id, champs, point_id=None):
    v = {k: champs[k] for k in CHAMPS_POINT if k in champs}
    if "epreuve_ids" in champs:
        v["epreuves_json"] = json.dumps([int(i) for i in champs["epreuve_ids"] or []])
    if "nom" in v or point_id is None:
        v["nom"] = (v.get("nom") or "").strip()
        if not v["nom"]:
            raise ErreurCommandement("Donne un nom au point de contrôle.")
    if v.get("type") and v["type"] not in K.LIBELLE_POINT:
        raise ErreurCommandement("Type de point inconnu.")
    if "barriere_horaire" in v:
        v["barriere_horaire"] = _heure(v["barriere_horaire"])
    for k in ("lat", "lon"):
        if v.get(k) in ("", 0):
            v[k] = None
    if point_id is None:
        v["evenement_id"] = evenement_id
        return base.inserer("points_controle", v)
    if v:
        base.ecrire(f"UPDATE points_controle SET {', '.join(k + '=?' for k in v)} WHERE id=?", tuple(v.values()) + (point_id,))
    return point_id


def supprimer_point(point_id):
    base.ecrire("DELETE FROM points_controle WHERE id=?", (point_id,))


def creer_points_depuis_ravitaillements(evenement_id):
    """Un point de contrôle par ravitaillement (hors arrivée), avec sa barrière horaire ; sans doublon."""
    from noyau.donnees import logistique as dl
    deja = {p["ravitaillement_id"] for p in points(evenement_id) if p["ravitaillement_id"]}
    n = 0
    for r in dl.ravitaillements(evenement_id, avec_quantites=False):
        if r["id"] in deja or r["type"] == "arrivee":
            continue
        enregistrer_point(evenement_id, {"nom": r["nom"], "type": "ravito", "km": r["km"], "ravitaillement_id": r["id"],
                                         "barriere_horaire": r.get("barriere_horaire"),
                                         "epreuve_ids": json.loads(r["epreuves_json"]) if r.get("epreuves_json") else []})
        n += 1
    return n


def pointer(evenement_id, point_id, dossard, heure_iso=None, source="saisie"):
    """Passage d'un coureur à un point de contrôle (même contrôle des doubles tops que l'arrivée)."""
    if point_id in (None, "", "arrivee"):
        return dch.ajouter_passage(evenement_id, dossard, heure_iso, source)
    if not point(int(point_id)):
        raise ErreurCommandement("Point de contrôle inconnu.")
    return dch.ajouter_passage(evenement_id, dossard, heure_iso, source, K.cle_point(int(point_id)))


# ------------------------------------------------------------------ situation des coureurs

def _inscrits(evenement_id):
    extra = {r[0]: (r[1], r[2]) for r in base.lire_tous(
        "SELECT i.id, i.statut_course, i.temps_corrige_s FROM inscriptions i JOIN epreuves p ON p.id = i.epreuve_id "
        "WHERE p.evenement_id=?", (evenement_id,))}
    res = []
    for i in dor.inscriptions(evenement_id):
        if i["statut"] in ("annulee", "liste_attente") or not i.get("dossard"):
            continue
        i["statut_course"], i["temps_corrige_s"] = extra.get(i["id"], (None, None))
        res.append(i)
    return res


def situation(evenement_id, maintenant=None):
    ev = dor.evenement(evenement_id)
    eps = [{**e, "date": e.get("date") or ev["date_debut"]} for e in dor.epreuves(evenement_id)]
    return K.situation(_inscrits(evenement_id), eps, points(evenement_id), dch.passages(evenement_id), maintenant)


# ------------------------------------------------------------------ incidents

CHAMPS_INCIDENT = ("numero", "horodatage", "recu_le", "type", "gravite", "dossard", "point_id", "km", "lat", "lon",
                   "description", "signale_par", "compte_id", "statut", "pris_par", "suivi_json", "clos_le", "cle_client")


def incidents(evenement_id, ouverts_seulement=False):
    sql = f"SELECT id, {', '.join(CHAMPS_INCIDENT)} FROM incidents WHERE evenement_id=?"
    if ouverts_seulement:
        sql += " AND statut != 'clos'"
    res = [dict(zip(("id",) + CHAMPS_INCIDENT, l)) for l in base.lire_tous(sql + " ORDER BY "
           "CASE gravite WHEN 'urgent' THEN 0 WHEN 'moyen' THEN 1 ELSE 2 END, statut = 'clos', horodatage DESC", (evenement_id,))]
    pts = {p["id"]: p["nom"] for p in points(evenement_id)}
    noms = {i["dossard"]: f"{i.get('prenom') or ''} {i['nom']}".strip() for i in dor.inscriptions(evenement_id) if i.get("dossard")}
    for i in res:
        try:
            i["suivi"] = json.loads(i["suivi_json"]) if i["suivi_json"] else []
        except ValueError:
            i["suivi"] = []
        i["point"] = pts.get(i["point_id"], "")
        i["coureur"] = noms.get(i["dossard"], "")
        i["libelle_type"] = K.LIBELLE_INCIDENT.get(i["type"], i["type"])
        i["libelle_gravite"] = K.LIBELLE_GRAVITE.get(i["gravite"], i["gravite"])
    return res


def signaler(evenement_id, champs, signale_par=None, compte_id=None):
    """Nouvel incident. cle_client : identifiant créé par le téléphone, pour qu'un incident envoyé plusieurs fois
    (réseau qui revient) ne soit enregistré qu'une fois. Renvoie (id, créé)."""
    cle = (champs.get("cle_client") or "").strip() or None
    if cle:
        l = base.lire_un("SELECT id FROM incidents WHERE cle_client=?", (cle,))
        if l:
            return l[0], False
    t = champs.get("type") or "autre"
    g = champs.get("gravite") or "moyen"
    if t not in K.LIBELLE_INCIDENT or g not in K.LIBELLE_GRAVITE:
        raise ErreurCommandement("Type ou gravité inconnu.")
    desc = (champs.get("description") or "").strip()
    if not desc and not champs.get("dossard"):
        raise ErreurCommandement("Décris l'incident (ou donne au moins le dossard).")
    h = champs.get("horodatage") or datetime.now().isoformat(timespec="seconds")
    try:
        datetime.fromisoformat(h)
    except ValueError:
        h = datetime.now().isoformat(timespec="seconds")
    pid = int(champs["point_id"]) if str(champs.get("point_id") or "").isdigit() else None
    km = champs.get("km")
    if km in ("", None) and pid:
        p = point(pid)
        km = p["km"] if p else None
    with base.transaction() as cur:
        n = (base.lire_un("SELECT COALESCE(MAX(numero), 0) FROM incidents WHERE evenement_id=?", (evenement_id,), cur)[0] or 0) + 1
        iid = base.inserer("incidents", {
            "evenement_id": evenement_id, "numero": n, "horodatage": h, "recu_le": datetime.now().isoformat(timespec="seconds"),
            "type": t, "gravite": g, "dossard": int(champs["dossard"]) if str(champs.get("dossard") or "").strip().isdigit() else None,
            "point_id": pid, "km": float(str(km).replace(",", ".")) if km not in ("", None) else None,
            "lat": champs.get("lat") or None, "lon": champs.get("lon") or None, "description": desc[:2000] or None,
            "signale_par": signale_par or champs.get("signale_par"), "compte_id": compte_id, "statut": "ouvert",
            "cle_client": cle}, cur)
    return iid, True


def _suivi(incident_id, texte, par):
    l = base.lire_un("SELECT suivi_json FROM incidents WHERE id=?", (incident_id,))
    if not l:
        raise ErreurCommandement("Incident introuvable.")
    s = json.loads(l[0]) if l[0] else []
    s.append({"heure": datetime.now().isoformat(timespec="seconds"), "par": par or "", "texte": (texte or "").strip()})
    return json.dumps(s, ensure_ascii=False)


def prendre_en_charge(incident_id, par, texte=None):
    base.ecrire("UPDATE incidents SET statut='pris_en_charge', pris_par=?, suivi_json=? WHERE id=?",
                (par, _suivi(incident_id, texte or "pris en charge", par), incident_id))


def ajouter_suivi(incident_id, texte, par=None):
    if not (texte or "").strip():
        raise ErreurCommandement("Écris ce qui a été fait.")
    base.ecrire("UPDATE incidents SET suivi_json=? WHERE id=?", (_suivi(incident_id, texte, par), incident_id))


def clore(incident_id, par=None, texte=None):
    base.ecrire("UPDATE incidents SET statut='clos', clos_le=?, suivi_json=? WHERE id=?",
                (datetime.now().isoformat(timespec="seconds"), _suivi(incident_id, texte or "clos", par), incident_id))


def rouvrir(incident_id, par=None):
    base.ecrire("UPDATE incidents SET statut='ouvert', clos_le=NULL, suivi_json=? WHERE id=?",
                (_suivi(incident_id, "rouvert", par), incident_id))


def marquer_abandon(evenement_id, dossard):
    """Abandon déclaré par un incident ou un bénévole : le statut de course de l'inscription passe à abandon."""
    i = next((x for x in dor.inscriptions(evenement_id) if x.get("dossard") == int(dossard)), None)
    if not i:
        raise ErreurCommandement(f"Dossard {dossard} inconnu.")
    dch.definir_statut([i["id"]], "abandon")
    return i["id"]


# ------------------------------------------------------------------ présence des bénévoles

def marquer_present(poste_id, benevole_id, present=True):
    n = base.ecrire_compte("UPDATE orga_affectations SET present=?, present_le=? WHERE poste_id=? AND benevole_id=?",
                           (1 if present else 0, datetime.now().isoformat(timespec="seconds") if present else None,
                            poste_id, benevole_id))
    if not n:
        raise ErreurCommandement("Ce bénévole n'est pas affecté à ce poste.")


def presences(evenement_id):
    """Par poste : {poste_id, poste, besoin, affectes, presents, heure_debut, absents: [noms]}."""
    res = []
    for p in base.lire_tous("SELECT id, nom, besoin, heure_debut, heure_fin, type FROM orga_postes WHERE evenement_id=? "
                            "ORDER BY heure_debut, nom", (evenement_id,)):
        aff = base.lire_tous("SELECT b.prenom, b.nom, a.present FROM orga_affectations a JOIN benevoles b ON b.id = a.benevole_id "
                             "WHERE a.poste_id=?", (p[0],))
        res.append({"poste_id": p[0], "poste": p[1], "besoin": p[2] or 0, "heure_debut": p[3], "heure_fin": p[4], "type": p[5],
                    "affectes": len(aff), "presents": sum(1 for a in aff if a[2]),
                    "absents": [f"{a[0] or ''} {a[1]}".strip() for a in aff if not a[2]]})
    return res


# ------------------------------------------------------------------ positions (Trail Live)

def ajouter_positions(evenement_id, positions, source="fichier"):
    """positions : [(dossard, heure ISO, lat, lon)] ; sans doublon. Renvoie le nombre ajouté."""
    n = 0
    with base.transaction() as cur:
        for d, h, la, lo in positions:
            if not (-90 <= la <= 90 and -180 <= lo <= 180):
                continue
            n += base.ecrire_compte("INSERT OR IGNORE INTO positions_live (evenement_id, dossard, horodatage, lat, lon, source) "
                                    "VALUES (?, ?, ?, ?, ?, ?)", (evenement_id, d, h, la, lo, source), cur)
    return n


def importer_positions(evenement_id, contenu, nom_fichier="positions.csv", dossard=None):
    try:
        lus = K.lire_positions(contenu, nom_fichier, dossard)
    except ValueError as e:
        raise ErreurCommandement(str(e))
    if not lus:
        raise ErreurCommandement("Aucune position lue (attendu : dossard;heure;latitude;longitude, ou un GPX).")
    return {"lues": len(lus), "ajoutees": ajouter_positions(evenement_id, lus)}


def dernieres_positions(evenement_id):
    return {r[0]: {"dossard": r[0], "heure": r[1], "lat": r[2], "lon": r[3]} for r in base.lire_tous(
        "SELECT p.dossard, p.horodatage, p.lat, p.lon FROM positions_live p JOIN (SELECT dossard, MAX(horodatage) AS h "
        "FROM positions_live WHERE evenement_id=? GROUP BY dossard) m ON m.dossard = p.dossard AND m.h = p.horodatage "
        "WHERE p.evenement_id=?", (evenement_id, evenement_id))}


# ------------------------------------------------------------------ page publique

def activer_live(evenement_id, avec_noms=True, telephone_pc=None):
    l = base.lire_un("SELECT live_jeton FROM evenements WHERE id=?", (evenement_id,))
    if l is None:
        raise ErreurCommandement("Événement introuvable.")
    j = l[0] or secrets.token_urlsafe(12)
    base.ecrire("UPDATE evenements SET live_jeton=?, live_noms=?, pc_telephone=COALESCE(?, pc_telephone) WHERE id=?",
                (j, 1 if avec_noms else 0, telephone_pc, evenement_id))
    return j


def desactiver_live(evenement_id):
    base.ecrire("UPDATE evenements SET live_jeton=NULL WHERE id=?", (evenement_id,))


def reglages_live(evenement_id):
    l = base.lire_un("SELECT live_jeton, live_noms, pc_telephone FROM evenements WHERE id=?", (evenement_id,))
    return {"jeton": l[0], "noms": bool(l[1]), "pc_telephone": l[2]} if l else None


def evenement_du_jeton(jeton):
    if not jeton:
        return None
    l = base.lire_un("SELECT id FROM evenements WHERE live_jeton=?", (jeton,))
    return l[0] if l else None


def suivi_public(evenement_id, recherche="", maintenant=None):
    """Ce que voient les proches : dossard, nom (si l'organisateur le permet), épreuve, dernier point passé,
    heure, arrivée estimée ; jamais de position GPS sans consentement « géolocalisation » du coureur."""
    from noyau.donnees import comptes as dco
    r = reglages_live(evenement_id)
    lignes = situation(evenement_id, maintenant)
    pos = dernieres_positions(evenement_id)
    ins = {i["dossard"]: i for i in _inscrits(evenement_id)}
    q = (recherche or "").strip().lower()
    res = []
    for l in lignes:
        i = ins.get(l["dossard"], {})
        nom = l["nom"] if r and r["noms"] else ""
        if q and q not in f"{l['dossard']} {nom}".lower():
            continue
        p = pos.get(l["dossard"])
        if p and not (i.get("personne_id") and dco.a_consenti(i["personne_id"], "geolocalisation")):
            p = None
        res.append({"dossard": l["dossard"], "nom": nom, "epreuve": l["epreuve"], "etat": l["etat"] if l["etat"] not in
                    ("à chercher", "hors délai") else "en course", "dernier": l["dernier"],
                    "heure": l["dernier_heure"][11:16] if l["dernier_heure"] else "", "km": l["km"],
                    "arrivee_estimee": (l["projection"] or "")[11:16], "temps": K.texte_temps(l["temps"]),
                    "position": p})
    return res


# ------------------------------------------------------------------ tableau de commandement

def tableau(evenement_id, maintenant=None):
    lignes = situation(evenement_id, maintenant)
    inc = incidents(evenement_id)
    pr = presences(evenement_id)
    return {"bilan": K.bilan(lignes), "alertes": [l for l in lignes if l["alerte"]],
            "incidents_ouverts": [i for i in inc if i["statut"] != "clos"],
            "urgents": sum(1 for i in inc if i["statut"] != "clos" and i["gravite"] == "urgent"),
            "postes": pr, "benevoles_presents": sum(p["presents"] for p in pr),
            "benevoles_attendus": sum(p["affectes"] for p in pr), "points": points(evenement_id)}
