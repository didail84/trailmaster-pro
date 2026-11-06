"""
Appels du logiciel de bureau vers le serveur (étape 5) : « module.fonction(arguments) » des modules de
noyau/donnees, exécutés sur le serveur au nom d'un compte.

- Seuls les modules de DOMAINES et leurs fonctions publiques sont appelables.
- Chaque appel est vérifié : domaine du module, lecture ou écriture, et
  associations ou événements touchés (retrouvés à partir des arguments :
  club_id, evenement_id, adhesion_id, inscription_id…).
- Les listes (associations, événements, personnes) sont réduites à ce que
  le compte a le droit de voir.
- Chaque écriture et chaque refus vont au journal des accès.
"""

import base64
import importlib
import inspect
import json

from noyau.donnees import base, comptes as dco
from noyau.serveur import droits as D

MODULES = {m: f"noyau.donnees.{m}" for m in ("club", "agenda_club", "profils", "personnes", "organisation", "chrono",
                                              "logistique", "calendrier", "annuaire", "kids", "analyse",
                                              "commandement", "comptes", "photos")}


# fonctions gardées sur le poste de chaque personne (son association et sa section du moment)
LOCALES = {"club": {"club_courant_id", "choisir_club", "section_courante", "choisir_section", "club_principal",
                    "club_id_ou_creer"},
           "personnes": {"normaliser_date", "age", "est_mineur", "normaliser_date_releve"},   # calculs sans base
           "comptes": {"authentifier", "session", "deconnecter", "journaliser", "purger_sessions"},
           "photos": {"telecharger_lien", "racine"}}          # le lien se télécharge sur ce poste, puis s'importe


class Refus(Exception):
    """Appel refusé (droits) : message lisible."""


# --------------------------------------------------------------- JSON

def encoder(v):
    if isinstance(v, (bytes, bytearray)):
        return {"__octets__": base64.b64encode(bytes(v)).decode()}
    if isinstance(v, dict):
        if v and all(isinstance(k, int) and not isinstance(k, bool) for k in v):     # {personne_id: …} garde ses clés
            return {"__cles_entieres__": [[k, encoder(x)] for k, x in v.items()]}
        return {str(k): encoder(x) for k, x in v.items()}
    if isinstance(v, (list, tuple, set)):
        return [encoder(x) for x in v]
    if hasattr(v, "isoformat"):
        return v.isoformat()
    return v


def decoder(v):
    if isinstance(v, dict):
        if set(v) == {"__octets__"}:
            return base64.b64decode(v["__octets__"])
        if set(v) == {"__cles_entieres__"}:
            return {int(k): decoder(x) for k, x in v["__cles_entieres__"]}
        return {k: decoder(x) for k, x in v.items()}
    if isinstance(v, list):
        return [decoder(x) for x in v]
    return v


def vers_json(v):
    return json.dumps(encoder(v), ensure_ascii=False, default=str)


# --------------------------------------------------------------- cibles d'un appel

# argument -> requête qui donne (club_id) ou (evenement_id)
CLUB = {"adhesion_id": "SELECT club_id FROM adhesions WHERE id=?", "groupe_id": "SELECT club_id FROM groupes WHERE id=?",
        "seance_id": "SELECT club_id FROM seances_club WHERE id=?", "serie_id": "SELECT club_id FROM series_club WHERE id=?",
        "section_id": "SELECT club_id FROM sections WHERE id=?", "tarif_id": "SELECT club_id FROM tarifs_cotisation WHERE id=?",
        "modele_id": "SELECT club_id FROM seances_modeles WHERE id=?"}
EVENEMENT = {"epreuve_id": "SELECT evenement_id FROM epreuves WHERE id=?",
             "inscription_id": "SELECT p.evenement_id FROM inscriptions i JOIN epreuves p ON p.id = i.epreuve_id WHERE i.id=?",
             "passage_id": "SELECT evenement_id FROM chrono_passages WHERE id=?",
             "demarche_id": "SELECT evenement_id FROM orga_demarches WHERE id=?",
             "benevole_id": "SELECT evenement_id FROM benevoles WHERE id=?",
             "poste_id": "SELECT evenement_id FROM orga_postes WHERE id=?",
             "ravito_id": "SELECT evenement_id FROM ravitaillements WHERE id=?",
             "materiel_id": "SELECT evenement_id FROM orga_materiel WHERE id=?",
             "partenaire_id": "SELECT evenement_id FROM partenaires WHERE id=?",
             "ligne_id": "SELECT evenement_id FROM budget_lignes WHERE id=?",
             "point_id": "SELECT evenement_id FROM points_controle WHERE id=?",
             "incident_id": "SELECT evenement_id FROM incidents WHERE id=?",
             "photo_id": "SELECT evenement_id FROM photos_course WHERE id=?"}
LISTES = {"inscription_ids": "inscription_id", "ids": None, "personne_ids": "personne_id", "photo_ids": "photo_id"}


def _un(sql, v):
    try:
        r = base.lire_un(sql, (v,))
    except Exception:
        return None
    return r[0] if r else None


def liens_personne(personne_id):
    """Associations et événements où la personne apparaît (adhésion, inscription, bénévole)."""
    clubs = {r[0] for r in base.lire_tous("SELECT DISTINCT club_id FROM adhesions WHERE personne_id=?", (personne_id,))}
    evs = {r[0] for r in base.lire_tous("SELECT DISTINCT p.evenement_id FROM inscriptions i JOIN epreuves p "
                                        "ON p.id = i.epreuve_id WHERE i.personne_id=?", (personne_id,))}
    try:
        evs |= {r[0] for r in base.lire_tous("SELECT DISTINCT evenement_id FROM benevoles WHERE personne_id=?", (personne_id,))}
    except Exception:
        pass
    return clubs, evs


def cibles(fonction, arguments):
    """(clubs, événements, personnes) touchés par l'appel, d'après le nom des paramètres."""
    clubs, evs, pers = set(), set(), set()
    for nom, v in arguments.items():
        if v is None:
            continue
        valeurs = v if isinstance(v, (list, tuple, set)) else [v]
        cle = LISTES.get(nom, nom) if isinstance(v, (list, tuple, set)) else nom
        for x in valeurs:
            if not isinstance(x, int):
                continue
            if cle == "club_id":
                clubs.add(x)
            elif cle == "evenement_id":
                evs.add(x)
            elif cle == "personne_id":
                pers.add(x)
            elif cle in CLUB:
                c = _un(CLUB[cle], x)
                if c is not None:
                    clubs.add(c)
            elif cle in EVENEMENT:
                e = _un(EVENEMENT[cle], x)
                if e is not None:
                    evs.add(e)
    return clubs, evs, pers


def _clubs_des_evenements(evs):
    return {e: _un("SELECT club_id FROM evenements WHERE id=?", e) for e in evs}


def verifier(compte, module, fonction, arguments):
    """Lève Refus si le compte n'a pas le droit ; renvoie True sinon."""
    if module not in MODULES:
        raise Refus(f"Module « {module} » non disponible sur le serveur.")
    domaine = D.DOMAINES[module]
    ecriture = not D.est_lecture(fonction)
    roles = compte["roles"]
    clubs, evs, pers = cibles(fonction, arguments)
    scopes_c, scopes_e = D.clubs_de(roles), D.evenements_de(roles)
    if scopes_c is not None:                     # pas administrateur : une personne doit être liée à son périmètre
        for p in pers:
            c, e = liens_personne(p)
            if (c or e) and not (c & scopes_c or e & (scopes_e or set())
                                 or any(_clubs_des_evenements(e).get(x) in scopes_c for x in e)):
                raise Refus("Cette personne n'appartient pas à tes associations ni à tes événements.")
    if not D.autorise(roles, domaine, ecriture, clubs, evs, _clubs_des_evenements(evs)):
        raise Refus(f"Ton compte n'a pas le droit de {'modifier' if ecriture else 'consulter'} ceci "
                    f"({domaine}).")
    return True


# --------------------------------------------------------------- filtres des listes

def _filtrer(compte, module, fonction, resultat):
    roles = compte["roles"]
    sc, se = D.clubs_de(roles), D.evenements_de(roles)
    if sc is None:
        return resultat
    se = se or set()
    if module == "club" and fonction == "clubs":
        return [c for c in resultat if c["id"] in sc]
    if module == "organisation" and fonction == "evenements":
        return [e for e in resultat if e["id"] in se or e.get("club_id") in sc]
    if module == "personnes" and fonction == "lister":
        garde = []
        for p in resultat:
            c, e = liens_personne(p["id"])
            if c & sc or e & se:
                garde.append(p)
        return garde
    return resultat


# --------------------------------------------------------------- exécution

def fonctions_publiques(module):
    m = importlib.import_module(MODULES[module])
    return {n: f for n, f in vars(m).items() if inspect.isfunction(f) and not n.startswith("_")
            and f.__module__ == m.__name__ and n not in LOCALES.get(module, set())}


def executer(compte, module, fonction, args=(), kwargs=None, adresse=None, contexte=None):
    """Exécute l'appel pour ce compte. `contexte` : {"club_id", "sections"} choisis sur le poste de la personne.
    Renvoie {"ok": résultat} ou {"erreur": {"type", "message"}} (jamais d'exception vers le réseau)."""
    from noyau.donnees import club as dclub
    contexte = contexte or {}
    sc = D.clubs_de(compte["roles"])
    cid = contexte.get("club_id")
    dclub.contexte_appel.club_id = cid if isinstance(cid, int) and (sc is None or cid in sc) else None
    dclub.contexte_appel.sections = {str(k): v for k, v in (contexte.get("sections") or {}).items()}
    try:
        return _executer(compte, module, fonction, args, kwargs, adresse)
    finally:
        dclub.contexte_appel.club_id = None
        dclub.contexte_appel.sections = None


def _executer(compte, module, fonction, args, kwargs, adresse):
    kwargs = decoder(kwargs or {})
    args = decoder(list(args or []))
    ident = compte.get("identifiant")
    try:
        if module not in MODULES:
            raise Refus(f"Module « {module} » non disponible sur le serveur.")
        fns = fonctions_publiques(module)
        if fonction not in fns:
            raise Refus(f"Fonction « {module}.{fonction} » inconnue.")
        f = fns[fonction]
        try:
            lies = inspect.signature(f).bind(*args, **kwargs)
        except TypeError as e:
            raise Refus(f"Arguments invalides pour {module}.{fonction} : {e}")
        lies.apply_defaults()
        verifier(compte, module, fonction, dict(lies.arguments))
        r = f(*lies.args, **lies.kwargs)
        r = _filtrer(compte, module, fonction, r)
        if not D.est_lecture(fonction):
            dco.journaliser(compte.get("id"), ident, "ecriture", f"{module}.{fonction}",
                            detail=json.dumps(encoder({k: v for k, v in lies.arguments.items()
                                                       if not isinstance(v, (bytes, bytearray))}), ensure_ascii=False,
                                              default=str)[:500], adresse=adresse)
        return {"ok": encoder(r)}
    except Refus as e:
        dco.journaliser(compte.get("id"), ident, "refus", f"{module}.{fonction}", detail=str(e), adresse=adresse, reussi=False)
        return {"erreur": {"type": "Refus", "message": str(e)}}
    except Exception as e:                      # erreurs lisibles du noyau (ErreurClub…) ou imprévues
        nom = type(e).__name__
        lisible = nom.startswith("Erreur") or isinstance(e, ValueError)
        if not lisible:
            dco.journaliser(compte.get("id"), ident, "erreur", f"{module}.{fonction}", detail=f"{nom}: {e}",
                            adresse=adresse, reussi=False)
        return {"erreur": {"type": nom if lisible else "ErreurServeur",
                           "message": str(e) if lisible else "Erreur sur le serveur (détail dans son journal)."}}
