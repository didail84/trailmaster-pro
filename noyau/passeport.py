"""
Passeport coureur (étape 2.4, bloc 4 du Master Plan).

Un fichier JSON lisible qui transporte une personne d'un ordinateur à
l'autre, ou d'un club à un coureur : sa fiche, son profil sportif, ses
résultats de courses, ses index (ITRA, UTMB, Betrail…) et, au choix, ses
courses à venir et ses objectifs. Les sorties et leurs traces n'y sont
pas : elles voyagent avec la sauvegarde complète (.db).

Zéro doublon à l'import : chaque élément porte son identifiant universel
(UUID) ; ce qui est déjà présent (même UUID, ou même course à la même
date, même index à la même date…) est reconnu et laissé tel quel. Une
personne inconnue par son UUID est rapprochée par nom, prénom et date de
naissance avant d'en créer une nouvelle. Tout l'import se fait en une
seule opération : en cas d'erreur, rien n'est modifié.

Aucun widget ici : l'écran Personnes s'en sert.
"""

import json
from datetime import date, datetime
from pathlib import Path

from noyau.donnees import base
from noyau.donnees import personnes as dpers
from noyau.donnees.personnes import _cle_nom

FORMAT = "trail-hub-center/passeport-coureur"
VERSION_FORMAT = 1
TAILLE_MAX = 10 * 1024 * 1024

CHAMPS_IDENTITE = ("nom", "prenom", "date_naissance", "sexe")
CHAMPS_CONTACT = ("email", "telephone", "adresse", "code_postal", "ville")
CHAMPS_PROFIL = ("age", "sexe", "taille", "poids", "fc_repos", "fc_max", "fc_seuil", "vma", "vo2max", "niveau")
CHAMPS_RESULTAT = ("nom_course", "date", "distance", "denivele", "temps", "classement_general",
                   "classement_categorie", "objectif_atteint", "notes")
CHAMPS_COURSE = ("nom", "date", "lieu", "region", "distance_km", "denivele_m", "type_terrain", "lien", "notes")
CHAMPS_OBJECTIF = ("titre", "description", "date_cible", "type_objectif", "statut", "priorite")
CHAMPS_INDEX = ("organisme", "categorie", "valeur", "date_releve", "source")

CONTENU_PAR_DEFAUT = {"profil": True, "resultats": True, "index": True,
                      "courses": False, "objectifs": False, "contact": False}
LIBELLES_CONTENU = {
    "profil": "Profil sportif (âge, taille, poids, FC, VMA, VO2max)",
    "resultats": "Résultats de courses",
    "index": "Index de performance (ITRA, UTMB, Betrail…)",
    "courses": "Courses à venir",
    "objectifs": "Objectifs",
    "contact": "Coordonnées (e-mail, téléphone, adresse)",
}


class ErreurPasseport(Exception):
    """Message lisible par l'utilisateur ; rien n'a été modifié."""


def _version_logiciel():
    try:
        return (Path(__file__).resolve().parent.parent / "VERSION").read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def _lignes(sql, params, colonnes, cur=None):
    return [dict(zip(colonnes, l)) for l in base.lire_tous(sql, params, cur)]


# ------------------------------------------------------------------
# Export
# ------------------------------------------------------------------

def exporter(personne_id, contenu=None):
    """Le passeport (dict) de la personne. `contenu` : {clé: bool} parmi CONTENU_PAR_DEFAUT."""
    choix = {**CONTENU_PAR_DEFAUT, **(contenu or {})}
    f = dpers.fiche(personne_id)
    if f is None:
        raise ErreurPasseport("Cette personne n'existe pas.")
    personne = {"uuid": f["uuid"], **{k: f[k] for k in CHAMPS_IDENTITE}}
    if choix["contact"]:
        personne.update({k: f[k] for k in CHAMPS_CONTACT})
    p = {
        "format": FORMAT, "version_format": VERSION_FORMAT,
        "cree_le": datetime.now().isoformat(timespec="seconds"),
        "logiciel": f"Trail Hub Center {_version_logiciel()}".strip(),
        "contenu": [k for k, v in choix.items() if v],
        "personne": {k: v for k, v in personne.items() if v not in (None, "")},
        "roles": f["roles"],
    }
    if choix["index"]:
        p["index"] = [{k: i[k] for k in ("uuid",) + CHAMPS_INDEX} for i in dpers.index_de(personne_id)]
    athlete_id = f["athlete_id"]
    if athlete_id:
        if choix["profil"]:
            ligne = base.lire_un(f"SELECT uuid, {', '.join(CHAMPS_PROFIL)} FROM athletes WHERE id=?", (athlete_id,))
            p["profil_coureur"] = {k: v for k, v in zip(("uuid",) + CHAMPS_PROFIL, ligne) if v not in (None, "")}
        if choix["resultats"]:
            p["resultats"] = _lignes(
                f"SELECT uuid, {', '.join(CHAMPS_RESULTAT)} FROM resultats_courses WHERE athlete_id=? ORDER BY date, id",
                (athlete_id,), ("uuid",) + CHAMPS_RESULTAT)
        if choix["courses"]:
            p["courses_a_venir"] = [c for c in _lignes(
                f"SELECT uuid, {', '.join(CHAMPS_COURSE)} FROM courses_calendrier WHERE athlete_id=? ORDER BY date, id",
                (athlete_id,), ("uuid",) + CHAMPS_COURSE)
                if not c["date"] or str(c["date"])[:10] >= date.today().isoformat()]
        if choix["objectifs"]:
            p["objectifs"] = _lignes(
                f"SELECT uuid, {', '.join(CHAMPS_OBJECTIF)} FROM objectifs WHERE athlete_id=? ORDER BY date_cible, id",
                (athlete_id,), ("uuid",) + CHAMPS_OBJECTIF)
    for cle in ("resultats", "courses_a_venir", "objectifs", "index"):
        if cle in p:
            p[cle] = [{k: v for k, v in e.items() if v not in (None, "")} for e in p[cle]]
    return p


def nom_de_fichier(passeport):
    per = passeport.get("personne", {})
    morceaux = "_".join(_cle_nom(x).replace(" ", "-") for x in (per.get("prenom"), per.get("nom")) if x)
    return f"passeport_{morceaux or 'coureur'}_{date.today().isoformat()}.json"


def ecrire_fichier(chemin, passeport):
    Path(chemin).write_text(json.dumps(passeport, ensure_ascii=False, indent=2), encoding="utf-8")


# ------------------------------------------------------------------
# Lecture et contrôle
# ------------------------------------------------------------------

def valider(p):
    """Contrôle la forme d'un passeport ; lève ErreurPasseport avec un message clair."""
    if not isinstance(p, dict) or p.get("format") != FORMAT:
        raise ErreurPasseport("Ce fichier n'est pas un passeport coureur Trail Hub Center.")
    v = p.get("version_format")
    if not isinstance(v, int) or v < 1:
        raise ErreurPasseport("Version du passeport illisible.")
    if v > VERSION_FORMAT:
        raise ErreurPasseport("Ce passeport a été créé par une version plus récente de Trail Hub Center : "
                              "mets le logiciel à jour pour l'importer.")
    per = p.get("personne")
    if not isinstance(per, dict) or not str(per.get("nom") or "").strip():
        raise ErreurPasseport("Le passeport ne contient pas de nom de personne.")
    for cle in ("resultats", "courses_a_venir", "objectifs", "index", "roles"):
        if cle in p and not isinstance(p[cle], list):
            raise ErreurPasseport(f"La partie « {cle} » du passeport est abîmée.")
    for cle in ("resultats", "courses_a_venir", "objectifs", "index"):
        if any(not isinstance(e, dict) for e in p.get(cle, [])):
            raise ErreurPasseport(f"La partie « {cle} » du passeport est abîmée.")
    if "profil_coureur" in p and not isinstance(p["profil_coureur"], dict):
        raise ErreurPasseport("Le profil coureur du passeport est abîmé.")
    return p


def lire_fichier(chemin):
    chemin = Path(chemin)
    try:
        if chemin.stat().st_size > TAILLE_MAX:
            raise ErreurPasseport("Fichier trop gros pour un passeport (plus de 10 Mo).")
        p = json.loads(chemin.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError) as e:
        raise ErreurPasseport(f"Fichier illisible : {e}") from None
    return valider(p)


# ------------------------------------------------------------------
# Import (aperçu puis application)
# ------------------------------------------------------------------

def _trouver_personne(per, cur):
    """('uuid'|'nom'|'nouvelle'|'ambigu', id ou None, [candidats])."""
    u = per.get("uuid")
    if u:
        l = base.lire_un("SELECT id FROM personnes WHERE uuid=?", (u,), cur)
        if l:
            return "uuid", l[0], []
    cle = (_cle_nom(per.get("nom")), _cle_nom(per.get("prenom")))
    naissance = str(per.get("date_naissance") or "")[:10] or None
    candidats = []
    for pid, nom, prenom, dn in base.lire_tous("SELECT id, nom, prenom, date_naissance FROM personnes", (), cur):
        if (_cle_nom(nom), _cle_nom(prenom)) != cle:
            continue
        if naissance and dn and dn != naissance:
            continue
        candidats.append(pid)
    if len(candidats) == 1:
        return "nom", candidats[0], candidats
    if candidats:
        return "ambigu", None, candidats
    return "nouvelle", None, []


def _uuid_libre(table, u, cur):
    return bool(u) and not base.lire_un(f"SELECT 1 FROM {table} WHERE uuid=?", (u,), cur)


def _deja(table, u, cur):
    return bool(u) and bool(base.lire_un(f"SELECT 1 FROM {table} WHERE uuid=?", (u,), cur))


def _elements_existants(athlete_id, personne_id, cur):
    ex = {"resultats": set(), "courses_a_venir": set(), "objectifs": set(), "index": set()}
    if athlete_id:
        ex["resultats"] = {(str(d or "")[:10], _cle_nom(n)) for n, d in base.lire_tous(
            "SELECT nom_course, date FROM resultats_courses WHERE athlete_id=?", (athlete_id,), cur)}
        ex["courses_a_venir"] = {(str(d or "")[:10], _cle_nom(n)) for n, d in base.lire_tous(
            "SELECT nom, date FROM courses_calendrier WHERE athlete_id=?", (athlete_id,), cur)}
        ex["objectifs"] = {(str(d or "")[:10], _cle_nom(t)) for t, d in base.lire_tous(
            "SELECT titre, date_cible FROM objectifs WHERE athlete_id=?", (athlete_id,), cur)}
    if personne_id:
        ex["index"] = {(o, c or "Général", str(d)[:10]) for o, c, d in base.lire_tous(
            "SELECT organisme, categorie, date_releve FROM index_performance WHERE personne_id=?", (personne_id,), cur)}
    return ex


TABLE_DE = {"resultats": "resultats_courses", "courses_a_venir": "courses_calendrier",
            "objectifs": "objectifs", "index": "index_performance"}


def _cle_element(partie, e):
    if partie == "resultats":
        return str(e.get("date") or "")[:10], _cle_nom(e.get("nom_course"))
    if partie == "courses_a_venir":
        return str(e.get("date") or "")[:10], _cle_nom(e.get("nom"))
    if partie == "objectifs":
        return str(e.get("date_cible") or "")[:10], _cle_nom(e.get("titre"))
    return e.get("organisme"), e.get("categorie") or "Général", str(e.get("date_releve") or "")[:10]


def _valide(partie, e):
    if partie == "resultats":
        return bool(str(e.get("nom_course") or "").strip())
    if partie == "courses_a_venir":
        return bool(str(e.get("nom") or "").strip())
    if partie == "objectifs":
        return bool(str(e.get("titre") or "").strip())
    try:
        float(e.get("valeur"))
    except (TypeError, ValueError):
        return False
    return bool(e.get("organisme")) and bool(e.get("date_releve"))


def _bilan(p, cur, personne_id=None):
    """Ce que l'import ferait, sans rien écrire."""
    if personne_id is not None:
        etat, cible, candidats = "choisie", personne_id, []
    else:
        etat, cible, candidats = _trouver_personne(p["personne"], cur)
    athlete_id = dpers.athlete_de_la_personne(cible, cur) if cible else None
    existants = _elements_existants(athlete_id, cible, cur)
    parties = {}
    for partie in ("resultats", "courses_a_venir", "objectifs", "index"):
        nouveaux, deja, ignores = [], 0, 0
        vus = set(existants[partie])
        for e in p.get(partie, []):
            if not _valide(partie, e):
                ignores += 1
                continue
            k = _cle_element(partie, e)
            if _deja(TABLE_DE[partie], e.get("uuid"), cur) or k in vus:
                deja += 1
                continue
            vus.add(k)
            nouveaux.append(e)
        parties[partie] = {"nouveaux": nouveaux, "deja": deja, "ignores": ignores}
    return {"personne": {"etat": etat, "id": cible, "candidats": candidats, "athlete_id": athlete_id},
            "parties": parties}


def apercu(passeport, personne_id=None):
    """Résumé lisible de l'import, sans rien modifier."""
    p = valider(passeport)
    conn = base.connexion()
    try:
        b = _bilan(p, conn.cursor(), personne_id)
    finally:
        conn.close()
    per = p["personne"]
    nom = f"{per.get('prenom') or ''} {per['nom']}".strip()
    etat = b["personne"]["etat"]
    libelle = {
        "uuid": f"{nom} : déjà connu(e) ici (même identifiant) — sa fiche est complétée.",
        "nom": f"{nom} : une fiche au même nom existe déjà — elle est complétée, pas dupliquée.",
        "choisie": f"{nom} : rattaché(e) à la fiche que tu as choisie.",
        "nouvelle": f"{nom} : nouvelle personne, sa fiche sera créée.",
        "ambigu": f"{nom} : plusieurs fiches portent ce nom — choisis laquelle compléter.",
    }[etat]
    lignes = [libelle]
    noms = {"resultats": "résultat(s)", "courses_a_venir": "course(s) à venir", "objectifs": "objectif(s)", "index": "index"}
    for partie, d in b["parties"].items():
        if d["nouveaux"] or d["deja"] or d["ignores"]:
            t = f"{len(d['nouveaux'])} {noms[partie]} à ajouter"
            if d["deja"]:
                t += f", {d['deja']} déjà présent(s)"
            if d["ignores"]:
                t += f", {d['ignores']} illisible(s) ignoré(s)"
            lignes.append(t)
    if p.get("profil_coureur"):
        lignes.append("Profil sportif : " + ("les cases vides du profil existant sont complétées."
                                             if b["personne"]["athlete_id"] else "un profil coureur est créé."))
    return {"etat": etat, "candidats": b["personne"]["candidats"], "lignes": lignes,
            "a_ajouter": sum(len(d["nouveaux"]) for d in b["parties"].values())}


def importer(passeport, personne_id=None, remplacer_profil=False):
    try:
        return _importer(passeport, personne_id, remplacer_profil)
    except dpers.ErreurPersonne as e:
        raise ErreurPasseport(f"Passeport refusé : {e}") from None


def _importer(passeport, personne_id=None, remplacer_profil=False):
    """Applique le passeport en une seule opération. `personne_id` force la fiche à
    compléter (cas ambigu). Renvoie {personne_id, athlete_id, cree, ajouts: {partie: n}, deja: {partie: n}}."""
    p = valider(passeport)
    per = p["personne"]
    with base.transaction() as cur:
        b = _bilan(p, cur, personne_id)
        etat = b["personne"]["etat"]
        if etat == "ambigu":
            raise ErreurPasseport("Plusieurs fiches portent ce nom : choisis laquelle compléter.")
        pid = b["personne"]["id"]
        cree = pid is None
        if cree:
            champs = {k: per.get(k) for k in CHAMPS_IDENTITE + CHAMPS_CONTACT if per.get(k) not in (None, "")}
            champs = dpers._nettoyer(champs)
            champs.setdefault("prenom", "")
            if _uuid_libre("personnes", per.get("uuid"), cur):
                champs["uuid"] = per["uuid"]
            pid = base.inserer("personnes", champs, cur)
        else:
            # complète seulement les cases vides de la fiche existante
            actuel = dict(zip(CHAMPS_IDENTITE + CHAMPS_CONTACT, base.lire_un(
                f"SELECT {', '.join(CHAMPS_IDENTITE + CHAMPS_CONTACT)} FROM personnes WHERE id=?", (pid,), cur)))
            manquants = {k: per[k] for k in CHAMPS_IDENTITE + CHAMPS_CONTACT
                         if per.get(k) not in (None, "") and actuel.get(k) in (None, "")}
            if manquants:
                manquants = dpers._nettoyer(manquants)
                cur.execute(f"UPDATE personnes SET {', '.join(k + '=?' for k in manquants)} WHERE id=?",
                            tuple(manquants.values()) + (pid,))

        for r in p.get("roles", []):
            if r in dpers.CODES_ROLES and r != "coureur":
                cur.execute("INSERT OR IGNORE INTO personnes_roles (personne_id, role, depuis) VALUES (?,?,date('now'))", (pid, r))

        athlete_id = dpers.athlete_de_la_personne(pid, cur)
        besoin_coureur = bool(p.get("profil_coureur") or "coureur" in p.get("roles", [])
                              or any(b["parties"][k]["nouveaux"] for k in ("resultats", "courses_a_venir", "objectifs")))
        profil = {k: v for k, v in (p.get("profil_coureur") or {}).items() if k in CHAMPS_PROFIL and v not in (None, "")}
        if besoin_coureur and not athlete_id:
            nom, prenom, sexe = base.lire_un("SELECT nom, prenom, sexe FROM personnes WHERE id=?", (pid,), cur)
            champs = {"nom": nom, "prenom": prenom or "", "personne_id": pid, **profil}
            champs.setdefault("sexe", sexe)
            u = (p.get("profil_coureur") or {}).get("uuid")
            if _uuid_libre("athletes", u, cur):
                champs["uuid"] = u
            athlete_id = base.inserer("athletes", champs, cur)
        elif athlete_id and profil:
            actuel = dict(zip(CHAMPS_PROFIL, base.lire_un(
                f"SELECT {', '.join(CHAMPS_PROFIL)} FROM athletes WHERE id=?", (athlete_id,), cur)))
            maj = {k: v for k, v in profil.items() if remplacer_profil or actuel.get(k) in (None, "", 0)}
            if maj:
                cur.execute(f"UPDATE athletes SET {', '.join(k + '=?' for k in maj)} WHERE id=?",
                            tuple(maj.values()) + (athlete_id,))

        ajouts = {}
        for partie, d in b["parties"].items():
            table = TABLE_DE[partie]
            champs_partie = {"resultats": CHAMPS_RESULTAT, "courses_a_venir": CHAMPS_COURSE,
                             "objectifs": CHAMPS_OBJECTIF, "index": CHAMPS_INDEX}[partie]
            n = 0
            for e in d["nouveaux"]:
                champs = {k: e[k] for k in champs_partie if e.get(k) not in (None, "")}
                if partie == "index":
                    champs["personne_id"] = pid
                    champs["valeur"] = float(champs["valeur"])
                    champs.setdefault("categorie", "Général")
                    champs.setdefault("source", "Passeport")
                else:
                    champs["athlete_id"] = athlete_id
                if _uuid_libre(table, e.get("uuid"), cur):
                    champs["uuid"] = e["uuid"]
                base.inserer(table, champs, cur)
                n += 1
            ajouts[partie] = n
    from noyau.outils.evenements import emettre, DONNEES_MODIFIEES
    emettre(DONNEES_MODIFIEES)
    return {"personne_id": pid, "athlete_id": athlete_id, "cree": cree, "ajouts": ajouts,
            "deja": {k: v["deja"] for k, v in b["parties"].items()}}
