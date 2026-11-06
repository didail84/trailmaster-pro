"""
Comptes du mode serveur (étape 5) : identifiants, mots de passe (empreintes
seulement), rôles par association ou par événement, sessions, journal des
accès, consentements (accord parental, droit à l'image, géolocalisation).
Les règles des droits sont dans noyau/serveur/droits.py.
"""

from datetime import datetime, timedelta

from noyau.donnees import base
from noyau.serveur import droits as D, mots_de_passe as M

ESSAIS_MAX = 5
BLOCAGE_MINUTES = 15
DUREE_SESSION = {"web": timedelta(hours=12), "bureau": timedelta(days=30)}
TYPES_CONSENTEMENT = (("donnees", "Traitement des données personnelles"), ("parental", "Accord parental (mineur)"),
                      ("image", "Droit à l'image"), ("geolocalisation", "Géolocalisation (suivi en direct)"),
                      ("contact", "Contact par e-mail ou SMS"))
LIBELLE_CONSENTEMENT = dict(TYPES_CONSENTEMENT)


class ErreurCompte(Exception):
    """Message lisible ; rien n'a été modifié."""


def _maintenant():
    return datetime.now().isoformat(timespec="seconds")


# ------------------------------------------------------------------ comptes

CHAMPS = ("identifiant", "nom_affiche", "personne_id", "actif", "doit_changer", "echecs", "bloque_jusqua", "cree_le",
          "derniere_connexion")


def comptes():
    res = [dict(zip(("id",) + CHAMPS, l)) for l in base.lire_tous(
        f"SELECT id, {', '.join(CHAMPS)} FROM comptes ORDER BY identifiant COLLATE NOCASE")]
    for c in res:
        c["roles"] = roles(c["id"])
    return res


def compte(compte_id):
    l = base.lire_un(f"SELECT id, {', '.join(CHAMPS)} FROM comptes WHERE id=?", (compte_id,))
    if not l:
        return None
    c = dict(zip(("id",) + CHAMPS, l))
    c["roles"] = roles(compte_id)
    return c


def _identifiant(t):
    t = (t or "").strip()
    if not t or len(t) > 60 or any(c.isspace() for c in t):
        raise ErreurCompte("Identifiant : sans espace, 60 caractères au plus (ex. prenom.nom).")
    return t


def creer_compte(identifiant, nom_affiche=None, personne_id=None, mot_de_passe=None):
    """Crée le compte ; sans mot de passe donné, en fabrique un provisoire. Renvoie (compte_id, mot de passe
    provisoire ou None)."""
    ident = _identifiant(identifiant)
    if base.lire_un("SELECT 1 FROM comptes WHERE identifiant=? COLLATE NOCASE", (ident,)):
        raise ErreurCompte(f"L'identifiant « {ident} » existe déjà.")
    provisoire = None
    if mot_de_passe:
        try:
            M.verifier_solidite(mot_de_passe, ident)
        except M.ErreurMotDePasse as e:
            raise ErreurCompte(str(e))
    else:
        provisoire = mot_de_passe = M.mot_de_passe_provisoire()
    cid = base.inserer("comptes", {"identifiant": ident, "nom_affiche": nom_affiche or ident, "personne_id": personne_id,
                                   "mot_de_passe": M.hacher(mot_de_passe), "doit_changer": 1 if provisoire else 0,
                                   "cree_le": _maintenant()})
    return cid, provisoire


def modifier_compte(compte_id, champs):
    v = {k: champs[k] for k in ("nom_affiche", "personne_id", "actif") if k in champs}
    if "actif" in v:
        v["actif"] = 1 if v["actif"] else 0
    if v:
        base.ecrire(f"UPDATE comptes SET {', '.join(k + '=?' for k in v)} WHERE id=?", tuple(v.values()) + (compte_id,))
    if v.get("actif") == 0:
        fermer_sessions(compte_id)


def supprimer_compte(compte_id):
    if _est_dernier_admin(compte_id):
        raise ErreurCompte("C'est le dernier administrateur : crée d'abord un autre administrateur.")
    base.ecrire("DELETE FROM comptes WHERE id=?", (compte_id,))


def changer_mot_de_passe(compte_id, nouveau, ancien=None):
    l = base.lire_un("SELECT identifiant, mot_de_passe FROM comptes WHERE id=?", (compte_id,))
    if not l:
        raise ErreurCompte("Compte introuvable.")
    if ancien is not None and not M.verifier(ancien, l[1]):
        raise ErreurCompte("L'ancien mot de passe ne correspond pas.")
    try:
        M.verifier_solidite(nouveau, l[0])
    except M.ErreurMotDePasse as e:
        raise ErreurCompte(str(e))
    base.ecrire("UPDATE comptes SET mot_de_passe=?, doit_changer=0, echecs=0, bloque_jusqua=NULL WHERE id=?",
                (M.hacher(nouveau), compte_id))


def reinitialiser_mot_de_passe(compte_id):
    """Nouveau mot de passe provisoire (à changer à la connexion) ; ferme les sessions. Renvoie le mot de passe."""
    m = M.mot_de_passe_provisoire()
    base.ecrire("UPDATE comptes SET mot_de_passe=?, doit_changer=1, echecs=0, bloque_jusqua=NULL WHERE id=?",
                (M.hacher(m), compte_id))
    fermer_sessions(compte_id)
    return m


# ------------------------------------------------------------------ rôles

def roles(compte_id):
    return [dict(zip(("id", "role", "club_id", "evenement_id", "club", "evenement"), l)) for l in base.lire_tous(
        "SELECT r.id, r.role, r.club_id, r.evenement_id, (SELECT nom FROM clubs WHERE id = r.club_id), "
        "(SELECT nom FROM evenements WHERE id = r.evenement_id) FROM comptes_roles r WHERE r.compte_id=? ORDER BY r.id",
        (compte_id,))]


def ajouter_role(compte_id, role, club_id=None, evenement_id=None):
    if role not in D.LIBELLE_ROLE:
        raise ErreurCompte("Rôle inconnu.")
    portee = D.PORTEE[role]
    if portee == "club" and not club_id:
        raise ErreurCompte(f"Le rôle « {D.LIBELLE_ROLE[role]} » se donne pour une association.")
    if portee == "evenement" and not evenement_id:
        raise ErreurCompte(f"Le rôle « {D.LIBELLE_ROLE[role]} » se donne pour un événement.")
    if portee is None:
        club_id = evenement_id = None
    elif portee == "club":
        evenement_id = None
    else:
        club_id = None
    if base.lire_un("SELECT 1 FROM comptes_roles WHERE compte_id=? AND role=? AND club_id IS ? AND evenement_id IS ?",
                    (compte_id, role, club_id, evenement_id)):
        return None
    return base.inserer("comptes_roles", {"compte_id": compte_id, "role": role, "club_id": club_id,
                                          "evenement_id": evenement_id})


def retirer_role(role_id):
    l = base.lire_un("SELECT compte_id, role FROM comptes_roles WHERE id=?", (role_id,))
    if l and l[1] == "admin" and _est_dernier_admin(l[0]):
        raise ErreurCompte("C'est le dernier administrateur : crée d'abord un autre administrateur.")
    base.ecrire("DELETE FROM comptes_roles WHERE id=?", (role_id,))


def _est_dernier_admin(compte_id):
    admins = {r[0] for r in base.lire_tous("SELECT DISTINCT r.compte_id FROM comptes_roles r JOIN comptes c "
                                           "ON c.id = r.compte_id WHERE r.role='admin' AND c.actif=1")}
    return admins == {compte_id}


def a_un_admin():
    return bool(base.lire_un("SELECT 1 FROM comptes_roles r JOIN comptes c ON c.id = r.compte_id "
                             "WHERE r.role='admin' AND c.actif=1"))


# ------------------------------------------------------------------ connexion et sessions

def authentifier(identifiant, mot_de_passe, adresse=None, type_session="web", appareil=None):
    """Renvoie (jeton, compte) ; lève ErreurCompte (message volontairement vague). Bloque le compte
    15 minutes après 5 essais manqués. Tout est écrit au journal."""
    ident = (identifiant or "").strip()
    l = base.lire_un("SELECT id, mot_de_passe, actif, echecs, bloque_jusqua FROM comptes WHERE identifiant=? COLLATE NOCASE",
                     (ident,))
    maintenant = datetime.now()
    if not l:
        M.verifier(mot_de_passe, M.hacher("x", 1000))             # même durée de réponse, compte connu ou non
        journaliser(None, ident, "connexion", detail="identifiant inconnu", adresse=adresse, reussi=False)
        raise ErreurCompte("Identifiant ou mot de passe incorrect.")
    cid, h, actif, echecs, bloque = l
    if bloque and datetime.fromisoformat(bloque) > maintenant:
        journaliser(cid, ident, "connexion", detail="compte bloqué", adresse=adresse, reussi=False)
        raise ErreurCompte(f"Trop d'essais : réessaie après {datetime.fromisoformat(bloque).strftime('%H:%M')}.")
    if not actif:
        journaliser(cid, ident, "connexion", detail="compte désactivé", adresse=adresse, reussi=False)
        raise ErreurCompte("Ce compte est désactivé.")
    if not M.verifier(mot_de_passe, h):
        echecs = (echecs or 0) + 1
        bloque = (maintenant + timedelta(minutes=BLOCAGE_MINUTES)).isoformat(timespec="seconds") if echecs >= ESSAIS_MAX else None
        base.ecrire("UPDATE comptes SET echecs=?, bloque_jusqua=? WHERE id=?", (0 if bloque else echecs, bloque, cid))
        journaliser(cid, ident, "connexion", detail="mot de passe incorrect" + (" ; compte bloqué 15 min" if bloque else ""),
                    adresse=adresse, reussi=False)
        raise ErreurCompte("Identifiant ou mot de passe incorrect.")
    j = M.jeton()
    base.inserer("sessions_serveur", {"compte_id": cid, "jeton_hash": M.empreinte_jeton(j), "type": type_session,
                                      "cree_le": maintenant.isoformat(timespec="seconds"),
                                      "expire_le": (maintenant + DUREE_SESSION.get(type_session, DUREE_SESSION["web"]))
                                      .isoformat(timespec="seconds"), "adresse": adresse, "appareil": (appareil or "")[:120]})
    base.ecrire("UPDATE comptes SET echecs=0, bloque_jusqua=NULL, derniere_connexion=? WHERE id=?",
                (maintenant.isoformat(timespec="seconds"), cid))
    journaliser(cid, ident, "connexion", detail=type_session, adresse=adresse)
    return j, compte(cid)


def session(jeton):
    """Le compte (avec ses rôles) d'un jeton valide, ou None."""
    if not jeton:
        return None
    l = base.lire_un("SELECT s.id, s.compte_id, s.expire_le, c.actif FROM sessions_serveur s JOIN comptes c "
                     "ON c.id = s.compte_id WHERE s.jeton_hash=?", (M.empreinte_jeton(jeton),))
    if not l or not l[3] or datetime.fromisoformat(l[2]) < datetime.now():
        return None
    base.ecrire("UPDATE sessions_serveur SET vu_le=? WHERE id=?", (_maintenant(), l[0]))
    return compte(l[1])


def deconnecter(jeton):
    base.ecrire("DELETE FROM sessions_serveur WHERE jeton_hash=?", (M.empreinte_jeton(jeton),))


def fermer_sessions(compte_id):
    base.ecrire("DELETE FROM sessions_serveur WHERE compte_id=?", (compte_id,))


def sessions_ouvertes():
    return [dict(zip(("id", "identifiant", "type", "cree_le", "vu_le", "adresse", "appareil"), l)) for l in base.lire_tous(
        "SELECT s.id, c.identifiant, s.type, s.cree_le, s.vu_le, s.adresse, s.appareil FROM sessions_serveur s "
        "JOIN comptes c ON c.id = s.compte_id WHERE s.expire_le > ? ORDER BY s.vu_le DESC", (_maintenant(),))]


def purger_sessions():
    return base.ecrire_compte("DELETE FROM sessions_serveur WHERE expire_le <= ?", (_maintenant(),))


# ------------------------------------------------------------------ journal

def journaliser(compte_id, identifiant, action, objet=None, detail=None, adresse=None, reussi=True):
    base.inserer("journal_acces", {"horodatage": datetime.now().isoformat(timespec="milliseconds"), "compte_id": compte_id,
                                   "identifiant": identifiant, "action": action, "objet": objet,
                                   "detail": (detail or "")[:500] or None, "adresse": adresse,
                                   "reussi": 1 if reussi else 0})


def journal(limite=500, compte_id=None, seulement_refus=False, depuis=None):
    sql = "SELECT horodatage, identifiant, action, objet, detail, adresse, reussi FROM journal_acces WHERE 1=1"
    p = []
    if compte_id:
        sql += " AND compte_id=?"
        p.append(compte_id)
    if seulement_refus:
        sql += " AND reussi=0"
    if depuis:
        sql += " AND horodatage >= ?"
        p.append(depuis)
    return [dict(zip(("horodatage", "identifiant", "action", "objet", "detail", "adresse", "reussi"), l))
            for l in base.lire_tous(sql + " ORDER BY id DESC LIMIT ?", tuple(p) + (int(limite),))]


def purger_journal(jours=365):
    """Le journal est gardé un an (durée de conservation à indiquer dans le registre des traitements)."""
    limite = (datetime.now() - timedelta(days=jours)).isoformat()
    return base.ecrire_compte("DELETE FROM journal_acces WHERE horodatage < ?", (limite,))


# ------------------------------------------------------------------ consentements

def consentements(personne_id=None, club_id=None):
    sql = ("SELECT c.id, c.personne_id, p.nom, p.prenom, c.type, c.donne, c.donne_par_id, c.donne_par_nom, c.date, "
           "c.club_id, c.preuve, c.retire_le, c.notes FROM consentements c JOIN personnes p ON p.id = c.personne_id WHERE 1=1")
    par = []
    if personne_id:
        sql += " AND c.personne_id=?"
        par.append(personne_id)
    if club_id:
        sql += " AND (c.club_id=? OR c.club_id IS NULL)"
        par.append(club_id)
    cles = ("id", "personne_id", "nom", "prenom", "type", "donne", "donne_par_id", "donne_par_nom", "date", "club_id",
            "preuve", "retire_le", "notes")
    return [dict(zip(cles, l)) for l in base.lire_tous(sql + " ORDER BY c.date DESC, c.id DESC", tuple(par))]


def enregistrer_consentement(personne_id, type_, donne=True, donne_par_id=None, donne_par_nom=None, jour=None,
                             club_id=None, preuve=None, notes=None):
    if type_ not in LIBELLE_CONSENTEMENT:
        raise ErreurCompte("Type de consentement inconnu.")
    return base.inserer("consentements", {"personne_id": personne_id, "type": type_, "donne": 1 if donne else 0,
                                          "donne_par_id": donne_par_id, "donne_par_nom": donne_par_nom,
                                          "date": jour or datetime.now().date().isoformat(), "club_id": club_id,
                                          "preuve": preuve, "notes": notes})


def retirer_consentement(consentement_id, jour=None):
    base.ecrire("UPDATE consentements SET retire_le=? WHERE id=?",
                (jour or datetime.now().date().isoformat(), consentement_id))


def a_consenti(personne_id, type_, club_id=None):
    """Le dernier consentement de ce type (non retiré) est-il un oui ?"""
    for c in consentements(personne_id, club_id):
        if c["type"] == type_:
            return bool(c["donne"]) and not c["retire_le"]
    return False
