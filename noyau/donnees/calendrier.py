"""
Accès aux données du calendrier des courses : les sources (flux .ics que tu
as donnés, collages, imports, ton organisation), les courses et leurs
épreuves, la fusion des doublons, l'envoi d'une course vers « Courses à
venir » ou vers l'agenda du club.

Une course que tu as corrigée n'est plus modifiée par ses sources ; tes
notes, favoris et courses masquées sont gardés.
"""

import json
import urllib.request
from datetime import date, datetime, timedelta

from noyau.donnees import base
from noyau.calendrier import regles as R

ErreurCalendrier = R.ErreurCalendrier
TYPES_SOURCE = (("ics", "Flux .ics (relu tout seul)"), ("collage", "Tableau collé"), ("fichier", "Fichier importé"),
                ("saisie", "Saisie"), ("organisation", "Mon organisation"))
LIBELLE_SOURCE = dict(TYPES_SOURCE)
CHAMPS = ("nom", "date_debut", "date_fin", "commune", "code_postal", "departement", "discipline", "niveau",
          "organisateur", "site", "inscription_url", "statut", "notes")
COLONNES = ("id", "uuid", "cle") + CHAMPS + ("source_id", "source", "ref_externe", "evenement_id", "mes_notes", "favori",
                                             "masque", "modifie", "vu_le")
AGENT = "TrailHubCenter/1.0 (calendrier personnel ; lecture d'un flux .ics donne par l'utilisateur)"
DELAI_RELECTURE_H = 12


# ------------------------------------------------------------------ sources

def sources():
    return [dict(zip(("id", "nom", "type", "url", "actif", "derniere_maj", "nb_courses", "erreur", "notes"), l))
            for l in base.lire_tous("SELECT id, nom, type, url, actif, derniere_maj, nb_courses, erreur, notes "
                                    "FROM calendrier_sources ORDER BY type, nom COLLATE NOCASE")]


def source(source_id):
    return next((s for s in sources() if s["id"] == source_id), None)


def enregistrer_source(champs, source_id=None):
    nom = (champs.get("nom") or "").strip()
    typ = champs.get("type") or "ics"
    url = (champs.get("url") or "").strip() or None
    if not nom:
        raise ErreurCalendrier("Donne un nom à la source (par exemple « Comité du Vaucluse »).")
    if typ not in LIBELLE_SOURCE:
        raise ErreurCalendrier("Type de source inconnu.")
    if typ == "ics":
        if not url:
            raise ErreurCalendrier("Colle l'adresse du flux (elle se termine souvent par .ics).")
        if url.startswith("webcal://"):
            url = "https://" + url[len("webcal://"):]
        if not url.startswith(("http://", "https://")):
            raise ErreurCalendrier("L'adresse du flux doit commencer par https://")
    if source_id is None:
        return base.inserer("calendrier_sources", {"nom": nom, "type": typ, "url": url, "actif": 1,
                                                   "notes": champs.get("notes")})
    base.ecrire("UPDATE calendrier_sources SET nom=?, type=?, url=?, actif=?, notes=? WHERE id=?",
                (nom, typ, url, 1 if champs.get("actif", True) else 0, champs.get("notes"), source_id))
    return source_id


def source_de_type(typ, nom):
    """Source unique pour les collages, imports, saisies ou ton organisation (créée au besoin)."""
    l = base.lire_un("SELECT id FROM calendrier_sources WHERE type=? AND nom=?", (typ, nom))
    return l[0] if l else base.inserer("calendrier_sources", {"nom": nom, "type": typ, "actif": 1})


def supprimer_source(source_id, avec_courses=False):
    """Supprime la source ; ses courses restent (sans source) sauf si avec_courses, et sauf celles que tu as
    corrigées, notées ou mises en favori."""
    with base.transaction() as cur:
        if avec_courses:
            cur.execute("DELETE FROM calendrier_courses WHERE source_id=? AND modifie=0 AND favori=0 "
                        "AND (mes_notes IS NULL OR mes_notes='')", (source_id,))
        cur.execute("DELETE FROM calendrier_sources WHERE id=?", (source_id,))


def a_relire(maintenant=None, delai_h=DELAI_RELECTURE_H):
    """Sources .ics actives à relire (jamais lues ou lues il y a plus de `delai_h` heures)."""
    m = maintenant or datetime.now()
    res = []
    for s in sources():
        if s["type"] != "ics" or not s["actif"] or not s["url"]:
            continue
        try:
            vieux = not s["derniere_maj"] or m - datetime.fromisoformat(s["derniere_maj"]) > timedelta(hours=delai_h)
        except ValueError:
            vieux = True
        if vieux:
            res.append(s)
    return res


def telecharger(url, delai=20):
    """Contenu d'un flux .ics (réseau ; à appeler hors de l'écran, dans un fil de travail)."""
    req = urllib.request.Request(url, headers={"User-Agent": AGENT, "Accept": "text/calendar, text/plain, */*"})
    with urllib.request.urlopen(req, timeout=delai) as r:
        if r.length and r.length > 20_000_000:
            raise ErreurCalendrier("Le flux est trop gros (plus de 20 Mo).")
        return r.read(20_000_001)


def appliquer_flux(source_id, contenu=None, erreur=None):
    """Enregistre le résultat de la lecture d'un flux .ics (contenu ou message d'erreur)."""
    maintenant = datetime.now().isoformat(timespec="seconds")
    if erreur:
        base.ecrire("UPDATE calendrier_sources SET erreur=?, derniere_maj=? WHERE id=?", (str(erreur)[:300], maintenant,
                                                                                       source_id))
        return {"ajoutees": 0, "mises_a_jour": 0, "erreurs": [str(erreur)]}
    courses, erreurs = R.lire_ics(contenu)
    s = source(source_id)
    r = enregistrer_courses(courses, source_id, s["nom"] if s else "Flux .ics")
    base.ecrire("UPDATE calendrier_sources SET erreur=?, derniere_maj=?, nb_courses=? WHERE id=?",
                ("; ".join(erreurs[:3]) or None, maintenant, len(courses), source_id))
    r["erreurs"] = erreurs
    return r


def relire(source_id):
    """Lecture complète d'un flux (réseau compris) — pour les tests et le bouton « Relire maintenant »."""
    s = source(source_id)
    try:
        contenu = telecharger(s["url"])
    except Exception as e:                       # réseau, adresse, serveur : on garde le message, rien n'est perdu
        return appliquer_flux(source_id, erreur=f"lecture impossible : {e}")
    return appliquer_flux(source_id, contenu)


def importer_texte(texte, nom_source, type_source="collage", annee_defaut=None):
    """Tableau collé, CSV ou contenu .ics importé. Renvoie {ajoutees, mises_a_jour, ignorees, erreurs}."""
    t = texte.decode("utf-8", "replace") if isinstance(texte, bytes) else texte
    if "BEGIN:VCALENDAR" in t[:2000]:
        courses, erreurs = R.lire_ics(t)
    else:
        courses, erreurs = R.lire_tableau(t, annee_defaut)
    sid = source_de_type(type_source, nom_source)
    r = enregistrer_courses(courses, sid, nom_source)
    base.ecrire("UPDATE calendrier_sources SET derniere_maj=?, nb_courses=nb_courses+? WHERE id=?",
                (datetime.now().isoformat(timespec="seconds"), r["ajoutees"], sid))
    r["erreurs"] = erreurs
    return r


# ------------------------------------------------------------------ courses

def _completer(c, epreuves):
    c["epreuves"] = epreuves.get(c["id"], [])
    c["famille"] = R.FAMILLE.get(c["discipline"], "Autre")
    c["region"] = R.REGION_DU_DEPARTEMENT.get(c["departement"])
    return c


def _epreuves(ids=None):
    sql = "SELECT id, course_id, nom, distance_km, denivele_m, discipline, heure_depart, prix FROM calendrier_epreuves"
    res = {}
    for l in base.lire_tous(sql + " ORDER BY distance_km DESC"):
        e = dict(zip(("id", "course_id", "nom", "distance_km", "denivele_m", "discipline", "heure_depart", "prix"), l))
        e["km_effort"] = R.km_effort(e["distance_km"], e["denivele_m"])
        res.setdefault(e["course_id"], []).append(e)
    return res


def courses(debut=None, fin=None, avec_masquees=False):
    sql = f"SELECT {', '.join(COLONNES)} FROM calendrier_courses WHERE 1=1"
    p = []
    if not avec_masquees:
        sql += " AND masque=0"
    if debut:
        sql += " AND COALESCE(date_fin, date_debut) >= ?"
        p.append(str(debut)[:10])
    if fin:
        sql += " AND date_debut <= ?"
        p.append(str(fin)[:10])
    sql += " ORDER BY date_debut, nom COLLATE NOCASE"
    eps = _epreuves()
    return [_completer(dict(zip(COLONNES, l)), eps) for l in base.lire_tous(sql, tuple(p))]


def course(course_id):
    l = base.lire_un(f"SELECT {', '.join(COLONNES)} FROM calendrier_courses WHERE id=?", (course_id,))
    return _completer(dict(zip(COLONNES, l)), _epreuves()) if l else None


def _ecrire_epreuves(cur, course_id, epreuves):
    cur.execute("DELETE FROM calendrier_epreuves WHERE course_id=?", (course_id,))
    for e in epreuves:
        base.inserer("calendrier_epreuves", {"course_id": course_id, "nom": e.get("nom"),
                                             "distance_km": e.get("distance_km"), "denivele_m": e.get("denivele_m"),
                                             "discipline": e.get("discipline"), "heure_depart": e.get("heure_depart"),
                                             "prix": e.get("prix")}, cur)


def enregistrer_courses(lues, source_id=None, nom_source=None):
    """Ajoute ou met à jour des courses lues. Doublon = même date, noms proches, même département ; une course
    corrigée par toi n'est pas modifiée. Renvoie {ajoutees, mises_a_jour, ignorees}."""
    ajout = maj = ign = 0
    with base.transaction() as cur:
        existantes = [dict(zip(("id", "nom", "date_debut", "departement", "modifie", "ref_externe", "source_id"), r))
                      for r in cur.execute("SELECT id, nom, date_debut, departement, modifie, ref_externe, source_id "
                                           "FROM calendrier_courses")]
        for c in lues:
            c = R.normaliser(dict(c))
            meme = next((e for e in existantes if c.get("ref_externe") and e["ref_externe"] == c["ref_externe"]
                         and e["source_id"] == source_id), None) or next((e for e in existantes if R.meme_course(e, c)),
                                                                         None)
            v = {k: c.get(k) for k in CHAMPS}
            v["statut"] = v["statut"] or "prevue"
            if meme is None:
                cid = base.inserer("calendrier_courses", {**v, "cle": c["cle"], "source_id": source_id,
                                                          "source": nom_source, "ref_externe": c.get("ref_externe")}, cur)
                _ecrire_epreuves(cur, cid, c["epreuves"])
                existantes.append({"id": cid, "nom": c["nom"], "date_debut": c["date_debut"],
                                   "departement": c.get("departement"), "modifie": 0, "ref_externe": c.get("ref_externe"),
                                   "source_id": source_id})
                ajout += 1
            elif meme["modifie"]:
                ign += 1
            else:
                # on complète sans effacer : une valeur vide de la source ne remplace pas une valeur connue
                pleins = {k: x for k, x in v.items() if x not in (None, "") and k != "nom"}
                if c["date_debut"] == meme["date_debut"] and meme.get("source_id") == source_id:
                    pleins["statut"] = v["statut"]
                if pleins:
                    cur.execute(f"UPDATE calendrier_courses SET {', '.join(k + '=?' for k in pleins)} WHERE id=?",
                                tuple(pleins.values()) + (meme["id"],))
                if c["epreuves"]:
                    deja = cur.execute("SELECT COUNT(*) FROM calendrier_epreuves WHERE course_id=?",
                                       (meme["id"],)).fetchone()[0]
                    if len(c["epreuves"]) >= deja:
                        _ecrire_epreuves(cur, meme["id"], c["epreuves"])
                maj += 1
    return {"ajoutees": ajout, "mises_a_jour": maj, "ignorees": ign}


def enregistrer_course(champs, course_id=None):
    """Saisie ou correction d'une course (et de ses épreuves)."""
    c = R.normaliser({k: champs.get(k) for k in CHAMPS + ("epreuves",) if k in champs})
    v = {k: c.get(k) for k in CHAMPS}
    v["statut"] = v["statut"] or "prevue"
    with base.transaction() as cur:
        if course_id is None:
            sid = source_de_type("saisie", "Saisie")
            course_id = base.inserer("calendrier_courses", {**v, "cle": c["cle"], "source_id": sid, "source": "Saisie",
                                                            "mes_notes": champs.get("mes_notes"), "modifie": 1}, cur)
        else:
            cur.execute(f"UPDATE calendrier_courses SET {', '.join(k + '=?' for k in v)}, mes_notes=?, modifie=1 "
                        "WHERE id=?", tuple(v.values()) + (champs.get("mes_notes"), course_id))
        _ecrire_epreuves(cur, course_id, c["epreuves"])
    return course_id


def definir_favori(course_id, favori=True):
    base.ecrire("UPDATE calendrier_courses SET favori=? WHERE id=?", (1 if favori else 0, course_id))


def masquer(course_id, masque=True):
    base.ecrire("UPDATE calendrier_courses SET masque=? WHERE id=?", (1 if masque else 0, course_id))


def supprimer_course(course_id):
    base.ecrire("DELETE FROM calendrier_courses WHERE id=?", (course_id,))


def chiffres(debut=None):
    cs = courses(debut or date.today())
    par = {}
    for c in cs:
        par[c["famille"]] = par.get(c["famille"], 0) + 1
    return {"total": len(cs), "par_famille": par, "favoris": sum(1 for c in cs if c["favori"]),
            "sources": len([s for s in sources() if s["type"] == "ics"])}


# ------------------------------------------------------------------ vers les autres modules

TERRAIN = {"route": "Route", "cross": "Cross", "stade": "Piste"}


def envoyer_vers_mes_courses(course_id, athlete_id, epreuve_id=None):
    """Ajoute la course (et l'épreuve choisie) à « Courses à venir » de l'athlète ; renvoie l'id créé.
    Ne crée pas de doublon (même nom et même date)."""
    c = course(course_id)
    if not c:
        raise ErreurCalendrier("Course introuvable.")
    e = next((x for x in c["epreuves"] if x["id"] == epreuve_id), None) or (c["epreuves"][0] if len(c["epreuves"]) == 1
                                                                           else None)
    nom = c["nom"] + (f" — {e['nom']}" if e and e.get("nom") and len(c["epreuves"]) > 1 else "")
    deja = base.lire_un("SELECT id FROM courses_calendrier WHERE athlete_id=? AND date=? AND nom=?",
                        (athlete_id, c["date_debut"], nom))
    if deja:
        return deja[0]
    lieu = " ".join(x for x in (c.get("commune"), f"({c['departement']})" if c.get("departement") else None) if x)
    return base.inserer("courses_calendrier", {
        "athlete_id": athlete_id, "nom": nom, "date": c["date_debut"], "lieu": lieu or None, "region": c.get("region"),
        "distance_km": e.get("distance_km") if e else None, "denivele_m": e.get("denivele_m") if e else None,
        "type_terrain": TERRAIN.get(c["discipline"], "Trail" if c["famille"] in ("Trail", "Montagne") else None),
        "lien": c.get("inscription_url") or c.get("site"), "source": "Calendrier des courses",
        "notes": c.get("mes_notes")})


def proposer_au_club(course_id, club_id, groupe_id=None):
    """Ajoute la course à l'agenda du club (séance de type compétition) ; renvoie l'id de la séance."""
    from noyau.donnees import agenda_club as dag
    c = course(course_id)
    if not c:
        raise ErreurCalendrier("Course introuvable.")
    deja = base.lire_un("SELECT id FROM seances_club WHERE club_id=? AND date=? AND titre=?",
                        (club_id, c["date_debut"], c["nom"]))
    if deja:
        return deja[0]
    distances = ", ".join(f"{e['distance_km']:g} km" + (f" / {e['denivele_m']} m D+" if e.get("denivele_m") else "")
                          for e in c["epreuves"] if e.get("distance_km"))
    return dag.enregistrer_seance(club_id, {"titre": c["nom"], "type": "competition", "date": c["date_debut"],
                                            "groupe_id": groupe_id, "lieu": c.get("commune"),
                                            "contenu": "\n".join(x for x in (distances, c.get("site")) if x) or None})


def export_ics(liste):
    return R.vers_ics(liste)
