"""
Fiche Personne unique et rôles (étape 2.2, bloc 1 du Master Plan).

Une personne n'existe qu'une fois dans Trail Hub Center, quel que soit
le nombre de modules qui la connaissent : coureur, licencié, enfant,
parent, entraîneur, bénévole, organisateur. Chaque module lit la même
fiche ; seul le noyau l'écrit (ce module).

Le profil sportif (FC, VMA, poids…) reste dans la table `athletes` :
c'est le rôle « coureur » de la personne. Les deux sont liés par
athletes.personne_id, et la base garde le nom, le sexe et la photo
identiques des deux côtés (déclencheurs de la migration 2).
"""

import re
import unicodedata
from datetime import date, datetime

from noyau.donnees import base

ROLES = (
    ("coureur", "Coureur"),
    ("licencie", "Licencié"),
    ("enfant", "Enfant"),
    ("parent", "Parent"),
    ("entraineur", "Entraîneur"),
    ("benevole", "Bénévole"),
    ("organisateur", "Organisateur"),
)
LIBELLE_ROLE = dict(ROLES)
CODES_ROLES = tuple(c for c, _ in ROLES)

CHAMPS = ("nom", "prenom", "date_naissance", "sexe", "email", "telephone",
          "adresse", "code_postal", "ville", "photo_path", "notes")

_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class ErreurPersonne(Exception):
    """Message lisible par l'utilisateur ; rien n'a été modifié."""


# ------------------------------------------------------------------
# Outils
# ------------------------------------------------------------------

def normaliser_date(texte):
    """« 1984-03-12 », « 12/03/1984 » ou « 12-03-1984 » → « 1984-03-12 » ; vide → None."""
    if texte is None or str(texte).strip() == "":
        return None
    t = str(texte).strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y"):
        try:
            d = datetime.strptime(t, fmt).date()
        except ValueError:
            continue
        if d > date.today() or d.year < 1900:
            raise ErreurPersonne(f"La date de naissance {t} n'est pas plausible.")
        return d.isoformat()
    raise ErreurPersonne(f"Date de naissance non reconnue : {t}. Écris-la comme 12/03/1984.")


def age(date_naissance, au=None):
    """Âge en années révolues, ou None si la date est inconnue."""
    if not date_naissance:
        return None
    try:
        n = datetime.strptime(str(date_naissance)[:10], "%Y-%m-%d").date()
    except ValueError:
        return None
    au = au or date.today()
    return au.year - n.year - ((au.month, au.day) < (n.month, n.day))


def est_mineur(date_naissance, au=None):
    a = age(date_naissance, au)
    return a is not None and a < 18


def _cle_nom(texte):
    """Nom comparable : sans accents, sans majuscules, espaces et tirets unifiés."""
    t = unicodedata.normalize("NFKD", texte or "")
    t = "".join(c for c in t if not unicodedata.combining(c)).lower()
    return re.sub(r"[\s\-']+", " ", t).strip()


def _nettoyer(champs):
    propres = {}
    for k, v in champs.items():
        if k not in CHAMPS:
            raise ErreurPersonne(f"Champ inconnu : {k}")
        v = v.strip() if isinstance(v, str) else v
        propres[k] = v if v not in ("",) else None
    if "nom" in propres and not propres["nom"]:
        raise ErreurPersonne("Le nom est obligatoire.")
    if "prenom" in propres:
        propres["prenom"] = propres["prenom"] or ""
    if "date_naissance" in propres:
        propres["date_naissance"] = normaliser_date(propres["date_naissance"])
    if propres.get("email") and not _EMAIL.match(propres["email"]):
        raise ErreurPersonne(f"Adresse e-mail non valable : {propres['email']}")
    return propres


def _verifier_roles(roles):
    roles = list(dict.fromkeys(roles or ()))
    inconnus = [r for r in roles if r not in CODES_ROLES]
    if inconnus:
        raise ErreurPersonne(f"Rôle inconnu : {', '.join(inconnus)}")
    return roles


# ------------------------------------------------------------------
# Lecture
# ------------------------------------------------------------------

def roles(personne_id, cur=None):
    """Codes des rôles de la personne, dans l'ordre de ROLES."""
    presents = {r for (r,) in base.lire_tous(
        "SELECT role FROM personnes_roles WHERE personne_id=?", (personne_id,), cur)}
    return [c for c in CODES_ROLES if c in presents]


def athlete_de_la_personne(personne_id, cur=None):
    ligne = base.lire_un("SELECT id FROM athletes WHERE personne_id=?", (personne_id,), cur)
    return ligne[0] if ligne else None


def personne_de_l_athlete(athlete_id, cur=None):
    ligne = base.lire_un("SELECT personne_id FROM athletes WHERE id=?", (athlete_id,), cur)
    return ligne[0] if ligne else None


def lister(role=None, recherche=""):
    """Personnes triées par nom : liste de dicts {id, nom, prenom, date_naissance,
    age, ville, roles, athlete_id}. `role` filtre sur un rôle, `recherche`
    sur le nom, le prénom, la ville ou l'e-mail (sans tenir compte des accents)."""
    lignes = base.lire_tous("""
        SELECT p.id, p.nom, p.prenom, p.date_naissance, p.ville, p.email,
               (SELECT group_concat(r.role) FROM personnes_roles r WHERE r.personne_id = p.id),
               (SELECT a.id FROM athletes a WHERE a.personne_id = p.id)
        FROM personnes p
        ORDER BY p.nom COLLATE NOCASE, p.prenom COLLATE NOCASE, p.id
    """)
    cle = _cle_nom(recherche)
    resultat = []
    for pid, nom, prenom, naissance, ville, email, liste_roles, athlete_id in lignes:
        les_roles = [c for c in CODES_ROLES if c in (liste_roles or "").split(",")]
        if role and role not in les_roles:
            continue
        if cle and cle not in _cle_nom(f"{nom} {prenom} {prenom} {nom} {ville or ''} {email or ''}"):
            continue
        resultat.append({"id": pid, "nom": nom, "prenom": prenom, "date_naissance": naissance,
                         "age": age(naissance), "ville": ville, "roles": les_roles, "athlete_id": athlete_id})
    return resultat


def fiche(personne_id):
    """Toute la fiche (dict) ou None : champs, uuid, rôles, profil coureur,
    parents et enfants liés."""
    colonnes = ("id", "uuid") + CHAMPS + ("date_creation",)
    ligne = base.lire_un(f"SELECT {', '.join(colonnes)} FROM personnes WHERE id=?", (personne_id,))
    if not ligne:
        return None
    f = dict(zip(colonnes, ligne))
    f["roles"] = roles(personne_id)
    f["athlete_id"] = athlete_de_la_personne(personne_id)
    f["age"] = age(f["date_naissance"])
    f["mineur"] = est_mineur(f["date_naissance"])
    f["parents"] = [{"id": i, "nom": n, "prenom": p} for i, n, p in base.lire_tous(
        "SELECT p.id, p.nom, p.prenom FROM personnes_liens l JOIN personnes p ON p.id = l.parent_id "
        "WHERE l.enfant_id=? ORDER BY p.nom, p.prenom", (personne_id,))]
    f["enfants"] = [{"id": i, "nom": n, "prenom": p} for i, n, p in base.lire_tous(
        "SELECT p.id, p.nom, p.prenom FROM personnes_liens l JOIN personnes p ON p.id = l.enfant_id "
        "WHERE l.parent_id=? ORDER BY p.nom, p.prenom", (personne_id,))]
    return f


def doublons_possibles(nom, prenom, date_naissance=None, sauf=None):
    """Personnes qui portent déjà ce nom et ce prénom (accents et
    majuscules ignorés) — et, si les deux dates sont connues, la même
    date de naissance. Sert à prévenir avant de créer un doublon."""
    cle = (_cle_nom(nom), _cle_nom(prenom))
    naissance = normaliser_date(date_naissance) if date_naissance else None
    res = []
    for p in lister():
        if p["id"] == sauf or (_cle_nom(p["nom"]), _cle_nom(p["prenom"])) != cle:
            continue
        if naissance and p["date_naissance"] and p["date_naissance"] != naissance:
            continue
        res.append(p)
    return res


def compter_par_role():
    """{code_role: nombre de personnes} pour tous les rôles (0 compris)."""
    d = dict.fromkeys(CODES_ROLES, 0)
    for r, n in base.lire_tous("SELECT role, COUNT(*) FROM personnes_roles GROUP BY role"):
        d[r] = n
    return d


# ------------------------------------------------------------------
# Écriture
# ------------------------------------------------------------------

def _creer_profil_coureur(personne_id, cur):
    nom, prenom, sexe = base.lire_un("SELECT nom, prenom, sexe FROM personnes WHERE id=?", (personne_id,), cur)
    return base.ecrire("INSERT INTO athletes (nom, prenom, sexe, personne_id) VALUES (?,?,?,?)",
                       (nom, prenom or "", sexe, personne_id), cur)


def creer(champs, les_roles=()):
    """Crée la fiche avec ses rôles ; renvoie son id. Le rôle « coureur »
    crée aussi le profil sportif (écran Athlètes), vide au départ."""
    propres = _nettoyer(champs)
    if not propres.get("nom"):
        raise ErreurPersonne("Le nom est obligatoire.")
    propres.setdefault("prenom", "")
    les_roles = _verifier_roles(les_roles)
    with base.transaction() as cur:
        pid = base.inserer("personnes", propres, cur)
        for r in les_roles:
            if r == "coureur":
                _creer_profil_coureur(pid, cur)      # le déclencheur ajoute le rôle
            else:
                cur.execute("INSERT OR IGNORE INTO personnes_roles (personne_id, role, depuis) VALUES (?,?,date('now'))",
                            (pid, r))
    return pid


def modifier(personne_id, champs):
    """Met à jour les champs donnés ; le nom, le prénom, le sexe et la photo
    suivent sur le profil coureur s'il existe."""
    propres = _nettoyer(champs)
    if not propres:
        return
    with base.transaction() as cur:
        if not base.lire_un("SELECT 1 FROM personnes WHERE id=?", (personne_id,), cur):
            raise ErreurPersonne("Cette personne n'existe plus.")
        cols = base.verifier_colonnes(list(propres))
        cur.execute(f"UPDATE personnes SET {', '.join(c + '=?' for c in cols)} WHERE id=?",
                    tuple(propres.values()) + (personne_id,))
        communs = {k: propres[k] for k in ("nom", "prenom", "sexe", "photo_path") if k in propres}
        athlete_id = athlete_de_la_personne(personne_id, cur)
        if athlete_id and communs:
            existantes = {r[1] for r in cur.execute("PRAGMA table_info(athletes)")}
            communs = {k: v for k, v in communs.items() if k in existantes}
            if communs:
                cur.execute(f"UPDATE athletes SET {', '.join(c + '=?' for c in communs)} WHERE id=?",
                            tuple(communs.values()) + (athlete_id,))


def definir_roles(personne_id, les_roles):
    """Remplace les rôles de la personne par `les_roles`.
    Ajouter « coureur » crée le profil sportif. Retirer « coureur » est
    refusé tant que le profil existe : il porte les sorties, il se
    supprime depuis l'écran Athlètes."""
    voulus = set(_verifier_roles(les_roles))
    with base.transaction() as cur:
        actuels = set(roles(personne_id, cur))
        athlete_id = athlete_de_la_personne(personne_id, cur)
        if "coureur" in actuels - voulus and athlete_id:
            raise ErreurPersonne(
                "Le rôle Coureur porte le profil sportif et les sorties de cette personne. "
                "Pour le retirer, supprime son profil dans l'écran Athlètes.")
        for r in actuels - voulus:
            cur.execute("DELETE FROM personnes_roles WHERE personne_id=? AND role=?", (personne_id, r))
        for r in voulus - actuels:
            if r == "coureur" and not athlete_id:
                _creer_profil_coureur(personne_id, cur)
            else:
                cur.execute("INSERT OR IGNORE INTO personnes_roles (personne_id, role, depuis) VALUES (?,?,date('now'))",
                            (personne_id, r))


def lier_parent(parent_id, enfant_id):
    """Relie un parent à un enfant (sert plus tard à l'accord parental et à l'espace parents)."""
    if parent_id == enfant_id:
        raise ErreurPersonne("Une personne ne peut pas être son propre parent.")
    with base.transaction() as cur:
        if base.lire_un("SELECT 1 FROM personnes_liens WHERE parent_id=? AND enfant_id=?", (enfant_id, parent_id), cur):
            raise ErreurPersonne("Ce lien existe déjà dans l'autre sens.")
        cur.execute("INSERT OR IGNORE INTO personnes_liens (parent_id, enfant_id) VALUES (?,?)", (parent_id, enfant_id))
        for pid, r in ((parent_id, "parent"), (enfant_id, "enfant")):
            cur.execute("INSERT OR IGNORE INTO personnes_roles (personne_id, role, depuis) VALUES (?,?,date('now'))", (pid, r))


def delier_parent(parent_id, enfant_id):
    base.ecrire("DELETE FROM personnes_liens WHERE parent_id=? AND enfant_id=?", (parent_id, enfant_id))


def supprimer(personne_id):
    """Supprime la fiche, ses rôles et ses liens. Refusé si elle a un
    profil coureur (il se supprime dans l'écran Athlètes, avec ses sorties)."""
    with base.transaction() as cur:
        if athlete_de_la_personne(personne_id, cur):
            raise ErreurPersonne("Cette personne a un profil coureur : supprime-le d'abord dans l'écran Athlètes.")
        cur.execute("DELETE FROM personnes WHERE id=?", (personne_id,))


# ------------------------------------------------------------------
# Index de performance (étape 2.4) : ITRA, UTMB, Betrail…
# ------------------------------------------------------------------

ORGANISMES_INDEX = ("ITRA", "UTMB Index", "Betrail", "Autre")


def index_de(personne_id):
    """Index de la personne, le plus récent d'abord : dicts {id, uuid, organisme, categorie, valeur, date_releve, source}."""
    cles = ("id", "uuid", "organisme", "categorie", "valeur", "date_releve", "source")
    return [dict(zip(cles, l)) for l in base.lire_tous(
        f"SELECT {', '.join(cles)} FROM index_performance WHERE personne_id=? "
        "ORDER BY date_releve DESC, organisme, id DESC", (personne_id,))]


def ajouter_index(personne_id, organisme, valeur, date_releve, categorie="Général", source="Saisie"):
    organisme = (organisme or "").strip()
    if not organisme:
        raise ErreurPersonne("Choisis l'organisme de l'index (ITRA, UTMB Index, Betrail…).")
    try:
        valeur = float(str(valeur).replace(",", "."))
    except ValueError:
        raise ErreurPersonne(f"Valeur d'index non valable : {valeur}") from None
    if not 0 <= valeur <= 1500:
        raise ErreurPersonne(f"Valeur d'index non plausible : {valeur}")
    jour = normaliser_date_releve(date_releve)
    if base.lire_un("SELECT 1 FROM index_performance WHERE personne_id=? AND organisme=? AND categorie=? AND date_releve=?",
                    (personne_id, organisme, categorie or "Général", jour)):
        raise ErreurPersonne(f"Un index {organisme} existe déjà à la date du {jour}.")
    return base.ecrire("INSERT INTO index_performance (personne_id, organisme, categorie, valeur, date_releve, source) "
                       "VALUES (?,?,?,?,?,?)", (personne_id, organisme, categorie or "Général", valeur, jour, source))


def supprimer_index(index_id):
    base.ecrire("DELETE FROM index_performance WHERE id=?", (index_id,))


def normaliser_date_releve(texte):
    """Date d'un relevé (pas de borne d'âge) : « 05/11/2026 » → « 2026-11-05 »."""
    t = str(texte or "").strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y"):
        try:
            d = datetime.strptime(t[:10], fmt).date()
        except ValueError:
            continue
        if d > date.today():
            raise ErreurPersonne(f"La date {t} est dans le futur.")
        return d.isoformat()
    raise ErreurPersonne(f"Date non reconnue : {t or '(vide)'}. Écris-la comme 05/11/2026.")
