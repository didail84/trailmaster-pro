"""
Accès aux données des Actualités du trail (chantier F) : les flux (ceux
livrés avec Trail Hub et les tiens), les articles reçus, les coureurs connus
et les articles qui les citent.

Trail Hub ne garde que le titre, la date, un court extrait et le lien ; le
fichier robots.txt de chaque site est respecté avant de lire son flux. Tes
corrections (flux mis en pause, fiche de coureur modifiée, notes) ne sont
jamais écrasées par une mise à jour de la référence.
"""

import json
import urllib.request
import urllib.robotparser
from datetime import datetime, timedelta
from urllib.parse import urlsplit

from noyau.actualites import regles as R
from noyau.donnees import base

ErreurActualites = R.ErreurActualites
AGENT = "TrailHubCenter/1.0 (lecteur RSS personnel ; titre, date, extrait et lien seulement)"
CLE_VERSION = "actualites_reference_version"
DELAI_RELECTURE_H = 6
GARDER_JOURS = 120
COL_SOURCE = ("id", "cle_reference", "nom", "url", "site", "langue", "zone", "actif", "derniere_maj", "nb_articles",
              "erreur", "modifie")
COL_COUREUR = ("id", "cle_reference", "prenom", "nom", "pays", "sexe", "palmares_json", "sources_json", "alias_json",
               "suivi", "mes_notes", "modifie", "verifie_le")


# ------------------------------------------------------------------ référence

def version_reference():
    l = base.lire_un("SELECT valeur FROM parametres_app WHERE cle=?", (CLE_VERSION,))
    return l[0] if l else None


def synchroniser(reference=None, forcer=False):
    """Ajoute ou met à jour les flux et coureurs livrés (sauf ceux que tu as modifiés ou supprimés)."""
    ref = reference or R.lire_reference()
    if not forcer and version_reference() == ref["version"]:
        return {"ajoutees": 0, "mises_a_jour": 0}
    ajout = maj = 0
    with base.transaction() as cur:
        retires = set(json.loads((cur.execute("SELECT valeur FROM parametres_app WHERE cle='actualites_retires'")
                                  .fetchone() or ["[]"])[0]))
        deja = {r[0]: (r[1], r[2]) for r in cur.execute(
            "SELECT cle_reference, id, modifie FROM actualites_sources WHERE cle_reference IS NOT NULL")}
        for s in ref["sources"]:
            v = {k: s.get(k) for k in ("nom", "url", "site", "langue", "zone")}
            if s["cle"] in retires:
                continue
            if s["cle"] not in deja:
                base.inserer("actualites_sources", {"cle_reference": s["cle"], **v, "actif": 1}, cur)
                ajout += 1
            elif not deja[s["cle"]][1]:
                cur.execute("UPDATE actualites_sources SET nom=?, url=?, site=?, langue=?, zone=? WHERE id=?",
                            (*v.values(), deja[s["cle"]][0]))
                maj += 1
        deja = {r[0]: (r[1], r[2]) for r in cur.execute(
            "SELECT cle_reference, id, modifie FROM coureurs_connus WHERE cle_reference IS NOT NULL")}
        for c in ref["coureurs"]:
            if c["cle"] in retires:
                continue
            v = {"prenom": c.get("prenom"), "nom": c["nom"], "pays": c.get("pays"), "sexe": c.get("sexe"),
                 "palmares_json": json.dumps(c.get("palmares") or [], ensure_ascii=False),
                 "sources_json": json.dumps(c.get("sources") or []),
                 "alias_json": json.dumps(c.get("alias") or [], ensure_ascii=False), "verifie_le": ref.get("verifie_le")}
            if c["cle"] not in deja:
                base.inserer("coureurs_connus", {"cle_reference": c["cle"], **v}, cur)
                ajout += 1
            elif not deja[c["cle"]][1]:
                cur.execute(f"UPDATE coureurs_connus SET {', '.join(k + '=?' for k in v)} WHERE id=?",
                            (*v.values(), deja[c["cle"]][0]))
                maj += 1
        cur.execute("INSERT INTO parametres_app (cle, valeur) VALUES (?, ?) ON CONFLICT(cle) DO UPDATE SET "
                    "valeur=excluded.valeur", (CLE_VERSION, ref["version"]))
    if ajout or maj:
        relier_tous()
    return {"ajoutees": ajout, "mises_a_jour": maj}


def _synchroniser_sans_erreur():
    try:
        synchroniser()
    except (OSError, ValueError, KeyError):
        pass


def _retirer_reference(cle):
    if not cle:
        return
    l = base.lire_un("SELECT valeur FROM parametres_app WHERE cle='actualites_retires'")
    r = set(json.loads(l[0])) if l else set()
    r.add(cle)
    base.ecrire("INSERT INTO parametres_app (cle, valeur) VALUES ('actualites_retires', ?) ON CONFLICT(cle) DO UPDATE "
                "SET valeur=excluded.valeur", (json.dumps(sorted(r)),))


# ------------------------------------------------------------------ sources

def sources():
    _synchroniser_sans_erreur()
    return [dict(zip(COL_SOURCE, l)) for l in base.lire_tous(
        f"SELECT {', '.join(COL_SOURCE)} FROM actualites_sources ORDER BY zone, nom COLLATE NOCASE")]


def source(source_id):
    l = base.lire_un(f"SELECT {', '.join(COL_SOURCE)} FROM actualites_sources WHERE id=?", (source_id,))
    return dict(zip(COL_SOURCE, l)) if l else None


def enregistrer_source(champs, source_id=None):
    nom, url = (champs.get("nom") or "").strip(), (champs.get("url") or "").strip()
    zone = champs.get("zone") or "france"
    if not nom:
        raise ErreurActualites("Donne un nom au flux (par exemple le nom du site).")
    if not url.startswith(("http://", "https://")):
        raise ErreurActualites("L'adresse du flux doit commencer par https:// (elle finit souvent par /feed/ ou .xml).")
    if zone not in R.LIBELLE_ZONE:
        raise ErreurActualites("Zone inconnue.")
    v = {"nom": nom, "url": url, "site": champs.get("site") or None, "langue": champs.get("langue") or None,
         "zone": zone, "actif": 1 if champs.get("actif", True) else 0}
    if source_id is None:
        return base.inserer("actualites_sources", v)
    base.ecrire("UPDATE actualites_sources SET nom=?, url=?, site=?, langue=?, zone=?, actif=?, modifie=1 WHERE id=?",
                (*v.values(), source_id))
    return source_id


def activer_source(source_id, actif=True):
    base.ecrire("UPDATE actualites_sources SET actif=?, modifie=1 WHERE id=?", (1 if actif else 0, source_id))


def supprimer_source(source_id):
    """Supprime le flux et ses articles (sauf les favoris, gardés sans source). Un flux livré ne revient pas."""
    s = source(source_id)
    if not s:
        return
    with base.transaction() as cur:
        cur.execute("UPDATE actualites SET source_id=NULL WHERE source_id=? AND favori=1", (source_id,))
        cur.execute("DELETE FROM actualites_sources WHERE id=?", (source_id,))
    _retirer_reference(s["cle_reference"])


def a_relire(maintenant=None, delai_h=DELAI_RELECTURE_H):
    m = maintenant or datetime.now()
    res = []
    for s in sources():
        if not s["actif"]:
            continue
        try:
            vieux = not s["derniere_maj"] or m - datetime.fromisoformat(s["derniere_maj"]) > timedelta(hours=delai_h)
        except ValueError:
            vieux = True
        if vieux:
            res.append(s)
    return res


def autorise_par_robots(url, delai=10):
    """Le fichier robots.txt du site permet-il de lire ce flux ? (absent = oui ; illisible = oui)."""
    p = urlsplit(url)
    rp = urllib.robotparser.RobotFileParser()
    try:
        req = urllib.request.Request(f"{p.scheme}://{p.netloc}/robots.txt", headers={"User-Agent": AGENT})
        with urllib.request.urlopen(req, timeout=delai) as r:
            rp.parse(r.read(500_000).decode("utf-8", "replace").splitlines())
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            return False
        return True
    except Exception:
        return True
    return rp.can_fetch("TrailHubCenter", url)


def telecharger(url, delai=20):
    """Contenu d'un flux (réseau ; à appeler hors de l'écran, dans un fil de travail)."""
    if not autorise_par_robots(url):
        raise ErreurActualites("le site interdit la lecture automatique de ce flux (robots.txt) : flux mis en pause")
    req = urllib.request.Request(url, headers={"User-Agent": AGENT,
                                               "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml"})
    with urllib.request.urlopen(req, timeout=delai) as r:
        if r.length and r.length > 5_000_000:
            raise ErreurActualites("Le flux est trop gros (plus de 5 Mo).")
        return r.read(5_000_001)


def appliquer_flux(source_id, contenu=None, erreur=None, maintenant=None):
    """Enregistre le résultat d'une lecture. Renvoie {nouveaux, erreur}."""
    m = (maintenant or datetime.now()).isoformat(timespec="seconds")
    if erreur:
        pause = "robots.txt" in str(erreur)
        base.ecrire("UPDATE actualites_sources SET erreur=?, derniere_maj=?" + (", actif=0" if pause else "")
                    + " WHERE id=?", (str(erreur)[:300], m, source_id))
        return {"nouveaux": 0, "erreur": str(erreur)}
    try:
        _titre, arts = R.lire_flux(contenu)
    except ErreurActualites as e:
        base.ecrire("UPDATE actualites_sources SET erreur=?, derniere_maj=? WHERE id=?", (str(e)[:300], m, source_id))
        return {"nouveaux": 0, "erreur": str(e)}
    cs = coureurs()
    n = 0
    with base.transaction() as cur:
        for a in arts:
            if cur.execute("SELECT 1 FROM actualites WHERE source_id=? AND guid=?", (source_id, a["guid"])).fetchone():
                continue
            aid = base.inserer("actualites", {"source_id": source_id, "guid": a["guid"], "titre": a["titre"],
                                              "lien": a["lien"], "date": a["date"] or m, "extrait": a["extrait"],
                                              "trail": 1 if R.parle_de_trail(a) else 0, "recu_le": m}, cur)
            for cid in R.coureurs_cites(cs, a):
                cur.execute("INSERT OR IGNORE INTO actualites_coureurs (actualite_id, coureur_id) VALUES (?, ?)", (aid, cid))
            n += 1
        cur.execute("UPDATE actualites_sources SET erreur=NULL, derniere_maj=?, nb_articles="
                    "(SELECT COUNT(*) FROM actualites WHERE source_id=?) WHERE id=?", (m, source_id, source_id))
    purger()
    return {"nouveaux": n, "erreur": None}


def relire(source_id):
    s = source(source_id)
    try:
        contenu = telecharger(s["url"])
    except Exception as e:
        return appliquer_flux(source_id, erreur=f"lecture impossible : {e}")
    return appliquer_flux(source_id, contenu)


def purger(garder_jours=GARDER_JOURS, aujourdhui=None):
    """Oublie les articles de plus de 4 mois, sauf tes favoris."""
    limite = ((aujourdhui or datetime.now()) - timedelta(days=garder_jours)).isoformat(timespec="seconds")
    return base.ecrire_compte("DELETE FROM actualites WHERE favori=0 AND COALESCE(date, recu_le) < ?", (limite,))


# ------------------------------------------------------------------ articles

_COL_ART = ("a.id", "a.source_id", "s.nom", "s.zone", "a.titre", "a.lien", "a.date", "a.extrait", "a.trail", "a.lu",
            "a.favori", "a.masque")
_CLE_ART = ("id", "source_id", "source", "zone", "titre", "lien", "date", "extrait", "trail", "lu", "favori", "masque")


def articles(zone=None, source_id=None, coureur_id=None, recherche=None, non_lus=False, favoris=False,
             trail_seulement=False, suivis=False, avec_masques=False, limite=300):
    sql = (f"SELECT {', '.join(_COL_ART)} FROM actualites a LEFT JOIN actualites_sources s ON s.id = a.source_id WHERE 1=1")
    par = []
    if not avec_masques:
        sql += " AND a.masque=0"
    if zone:
        sql += " AND s.zone=?"
        par.append(zone)
    if source_id:
        sql += " AND a.source_id=?"
        par.append(source_id)
    if coureur_id:
        sql += " AND a.id IN (SELECT actualite_id FROM actualites_coureurs WHERE coureur_id=?)"
        par.append(coureur_id)
    if suivis:
        sql += (" AND a.id IN (SELECT x.actualite_id FROM actualites_coureurs x JOIN coureurs_connus c ON c.id = x.coureur_id "
                "WHERE c.suivi=1)")
    if non_lus:
        sql += " AND a.lu=0"
    if favoris:
        sql += " AND a.favori=1"
    if trail_seulement:
        sql += " AND a.trail=1"
    if recherche:
        sql += " AND (a.titre LIKE ? OR a.extrait LIKE ?)"
        par += [f"%{recherche}%"] * 2
    sql += " ORDER BY a.date DESC, a.id DESC LIMIT ?"
    par.append(int(limite))
    res = [dict(zip(_CLE_ART, l)) for l in base.lire_tous(sql, tuple(par))]
    if res:
        ids = [r["id"] for r in res]
        cites = {}
        for aid, nom in base.lire_tous(
                "SELECT x.actualite_id, TRIM(COALESCE(c.prenom, '') || ' ' || c.nom) FROM actualites_coureurs x "
                f"JOIN coureurs_connus c ON c.id = x.coureur_id WHERE x.actualite_id IN ({','.join('?' * len(ids))})",
                tuple(ids)):
            cites.setdefault(aid, []).append(nom)
        for r in res:
            r["coureurs"] = sorted(cites.get(r["id"], []))
    return res


def marquer_lu(ids, lu=True):
    for i in ([ids] if isinstance(ids, int) else ids):
        base.ecrire("UPDATE actualites SET lu=? WHERE id=?", (1 if lu else 0, i))


def tout_marquer_lu():
    return base.ecrire_compte("UPDATE actualites SET lu=1 WHERE lu=0", ())


def definir_favori(article_id, favori=True):
    base.ecrire("UPDATE actualites SET favori=? WHERE id=?", (1 if favori else 0, article_id))


def masquer(article_id, masque=True):
    base.ecrire("UPDATE actualites SET masque=? WHERE id=?", (1 if masque else 0, article_id))


# ------------------------------------------------------------------ coureurs connus

def _coureur(l):
    c = dict(zip(COL_COUREUR, l))
    c["palmares"] = json.loads(c.pop("palmares_json") or "[]")
    c["sources"] = json.loads(c.pop("sources_json") or "[]")
    c["alias"] = json.loads(c.pop("alias_json") or "[]")
    c["nom_complet"] = f"{c['prenom'] or ''} {c['nom']}".strip()
    c["pays_nom"] = R.PAYS.get(c["pays"] or "", c["pays"] or "")
    c["reference"] = bool(c["cle_reference"])
    return c


def coureurs(pays=None, suivis=False):
    sql = f"SELECT {', '.join(COL_COUREUR)} FROM coureurs_connus WHERE 1=1"
    par = []
    if pays == "FRA":
        sql += " AND pays='FRA'"
    elif pays == "etranger":
        sql += " AND COALESCE(pays, '') != 'FRA'"
    if suivis:
        sql += " AND suivi=1"
    res = [_coureur(l) for l in base.lire_tous(sql + " ORDER BY nom COLLATE NOCASE, prenom", tuple(par))]
    nb = dict(base.lire_tous("SELECT coureur_id, COUNT(*) FROM actualites_coureurs x JOIN actualites a ON a.id = "
                             "x.actualite_id WHERE a.masque=0 GROUP BY coureur_id"))
    for c in res:
        c["nb_articles"] = nb.get(c["id"], 0)
    return res


def coureur(coureur_id):
    l = base.lire_un(f"SELECT {', '.join(COL_COUREUR)} FROM coureurs_connus WHERE id=?", (coureur_id,))
    return _coureur(l) if l else None


def enregistrer_coureur(champs, coureur_id=None):
    nom = (champs.get("nom") or "").strip()
    if not nom:
        raise ErreurActualites("Le nom du coureur est obligatoire.")
    lst = lambda k: [x.strip() for x in (champs.get(k) if isinstance(champs.get(k), list)
                                         else str(champs.get(k) or "").splitlines()) if x.strip()]
    sources_ = lst("sources")
    if any(not s.startswith(("http://", "https://")) for s in sources_):
        raise ErreurActualites("Chaque source du palmarès doit être une adresse https:// (une par ligne).")
    v = {"prenom": (champs.get("prenom") or "").strip() or None, "nom": nom,
         "pays": (champs.get("pays") or "").strip().upper()[:3] or None, "sexe": champs.get("sexe") or None,
         "palmares_json": json.dumps(lst("palmares"), ensure_ascii=False), "sources_json": json.dumps(sources_),
         "alias_json": json.dumps(lst("alias"), ensure_ascii=False), "mes_notes": champs.get("mes_notes") or None}
    if coureur_id is None:
        coureur_id = base.inserer("coureurs_connus", {**v, "suivi": 1 if champs.get("suivi") else 0})
    else:
        base.ecrire(f"UPDATE coureurs_connus SET {', '.join(k + '=?' for k in v)}, modifie=1 WHERE id=?",
                    (*v.values(), coureur_id))
    relier(coureur_id)
    return coureur_id


def suivre(coureur_id, suivi=True):
    base.ecrire("UPDATE coureurs_connus SET suivi=? WHERE id=?", (1 if suivi else 0, coureur_id))


def supprimer_coureur(coureur_id):
    c = coureur(coureur_id)
    if c:
        base.ecrire("DELETE FROM coureurs_connus WHERE id=?", (coureur_id,))
        _retirer_reference(c["cle_reference"])


def relier(coureur_id):
    """Retrouve les articles déjà reçus qui citent ce coureur (après ajout ou correction de sa fiche)."""
    c = coureur(coureur_id)
    if not c:
        return 0
    n = 0
    with base.transaction() as cur:
        cur.execute("DELETE FROM actualites_coureurs WHERE coureur_id=?", (coureur_id,))
        for aid, t, e in cur.execute("SELECT id, titre, extrait FROM actualites").fetchall():
            if R.cite(c, f"{t} {e or ''}"):
                cur.execute("INSERT OR IGNORE INTO actualites_coureurs (actualite_id, coureur_id) VALUES (?, ?)",
                            (aid, coureur_id))
                n += 1
    return n


def relier_tous():
    return sum(relier(c[0]) for c in base.lire_tous("SELECT id FROM coureurs_connus"))


# ------------------------------------------------------------------ vue d'ensemble

def tableau(n=8):
    """Pour le tableau de bord et la page Claude : derniers articles, non lus, articles des coureurs suivis."""
    _synchroniser_sans_erreur()
    non_lus = base.lire_un("SELECT COUNT(*) FROM actualites WHERE lu=0 AND masque=0")[0]
    return {"non_lus": non_lus, "derniers": articles(limite=n),
            "suivis": articles(suivis=True, limite=n),
            "coureurs_suivis": [c["nom_complet"] for c in coureurs(suivis=True)],
            "sources": len([s for s in sources() if s["actif"]])}
