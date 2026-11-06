"""
Accès aux données de l'agenda du club (étape 4.2) : séries hebdomadaires,
séances (issues d'une série ou ponctuelles), appel des présences et
assiduité. Les règles (vacances, fériés, bilans) sont dans
noyau/club/agenda.py.
"""

from datetime import date, timedelta

from noyau.donnees import base, club as dclub, personnes as dper
from noyau.club import agenda as ag, categories as cat

ErreurAgenda = ag.ErreurAgenda
CHAMPS_SERIE = ("groupe_id", "titre", "type", "jour_semaine", "heure_debut", "heure_fin", "lieu", "entraineur_id",
                "date_debut", "date_fin", "sauf_vacances", "sauf_feries", "notes")
CHAMPS_SEANCE = ("groupe_id", "titre", "type", "date", "heure_debut", "heure_fin", "lieu", "entraineur_id", "contenu",
                 "notes")


def _iso(d):
    return ag._jour(d).isoformat()


def zone_du_club(club_id):
    l = base.lire_un("SELECT zone_vacances FROM clubs WHERE id=?", (club_id,))
    return (l[0] if l and l[0] in ag.ZONES else "B")


# ------------------------------------------------------------------ séries

def _verifier_serie(v):
    v["titre"] = (v.get("titre") or "").strip()
    if not v["titre"]:
        raise ErreurAgenda("Donne un titre à la série (par exemple « Entraînement piste »).")
    if v.get("type") and v["type"] not in ag.LIBELLE_TYPE:
        raise ErreurAgenda("Type de séance inconnu.")
    v["heure_debut"] = ag.verifier_heure(v.get("heure_debut"))
    v["heure_fin"] = ag.verifier_heure(v.get("heure_fin"))
    if v["heure_debut"] and v["heure_fin"] and v["heure_fin"] <= v["heure_debut"]:
        raise ErreurAgenda("L'heure de fin doit être après l'heure de début.")
    v["type"] = v.get("type") or "entrainement"
    if v.get("jour_semaine") is None:
        raise ErreurAgenda("Choisis le jour de la semaine.")
    if not v.get("date_debut") or not v.get("date_fin"):
        raise ErreurAgenda("Donne la date de début et de fin de la série.")
    v["date_debut"], v["date_fin"] = _iso(v["date_debut"]), _iso(v["date_fin"])
    v["sauf_vacances"] = 1 if v.get("sauf_vacances") else 0
    v["sauf_feries"] = 1 if v.get("sauf_feries", True) else 0
    return v


def series(club_id):
    cles = ("id",) + CHAMPS_SERIE + ("groupe", "entraineur", "nb_seances")
    return [dict(zip(cles, l)) for l in base.lire_tous(
        f"SELECT s.id, {', '.join('s.' + c for c in CHAMPS_SERIE)}, g.nom, "
        "(SELECT p.prenom || ' ' || p.nom FROM personnes p WHERE p.id = s.entraineur_id), "
        "(SELECT COUNT(*) FROM seances_club x WHERE x.serie_id = s.id) "
        "FROM series_club s LEFT JOIN groupes g ON g.id = s.groupe_id WHERE s.club_id=? "
        "ORDER BY s.jour_semaine, s.heure_debut, s.titre", (club_id,))]


def serie(serie_id):
    l = base.lire_un("SELECT club_id FROM series_club WHERE id=?", (serie_id,))
    return next((s for s in series(l[0]) if s["id"] == serie_id), None) if l else None


def apercu_serie(club_id, champs):
    """(dates, écartées) que la série créerait, sans rien écrire."""
    v = _verifier_serie({k: champs.get(k) for k in CHAMPS_SERIE})
    return ag.dates_serie(v["jour_semaine"], v["date_debut"], v["date_fin"], zone_du_club(club_id),
                          v["sauf_vacances"], v["sauf_feries"])


def enregistrer_serie(club_id, champs, serie_id=None, aujourdhui=None):
    """Crée ou modifie une série et ses séances. En modification, les séances à venir sans appel sont
    recréées avec les nouveaux réglages ; les séances passées ou déjà appelées restent.
    Renvoie {serie_id, creees, ecartees: [(date, raison)], gardees}."""
    v = _verifier_serie({k: champs.get(k) for k in CHAMPS_SERIE})
    dates, ecartees = ag.dates_serie(v["jour_semaine"], v["date_debut"], v["date_fin"], zone_du_club(club_id),
                                     v["sauf_vacances"], v["sauf_feries"])
    auj = _iso(aujourdhui or date.today())
    with base.transaction() as cur:
        modification = serie_id is not None
        if not modification:
            serie_id = base.inserer("series_club", {"club_id": club_id, **v}, cur)
            existantes = set()
        else:
            cur.execute(f"UPDATE series_club SET {', '.join(c + '=?' for c in v)} WHERE id=?",
                        tuple(v.values()) + (serie_id,))
            # à venir, sans appel : on les refait ; le reste est gardé tel quel
            cur.execute("DELETE FROM seances_club WHERE serie_id=? AND date>=? AND appel_fait=0 "
                        "AND id NOT IN (SELECT seance_id FROM presences_club)", (serie_id, auj))
            existantes = {r[0] for r in cur.execute("SELECT date FROM seances_club WHERE serie_id=?", (serie_id,))}
        creees = 0
        for d in dates:
            iso = d.isoformat()
            if iso in existantes or (modification and iso < auj):
                continue
            base.inserer("seances_club", {"club_id": club_id, "serie_id": serie_id, "groupe_id": v.get("groupe_id"),
                                          "titre": v["titre"], "type": v.get("type") or "entrainement", "date": iso,
                                          "heure_debut": v["heure_debut"], "heure_fin": v["heure_fin"],
                                          "lieu": v.get("lieu"), "entraineur_id": v.get("entraineur_id")}, cur)
            creees += 1
    return {"serie_id": serie_id, "creees": creees, "ecartees": ecartees, "gardees": len(existantes)}


def supprimer_serie(serie_id, aujourdhui=None):
    """Supprime la série et ses séances à venir sans appel ; les séances passées ou appelées restent
    dans l'agenda (sans série). Renvoie le nombre de séances supprimées."""
    auj = _iso(aujourdhui or date.today())
    with base.transaction() as cur:
        cur.execute("DELETE FROM seances_club WHERE serie_id=? AND date>=? AND appel_fait=0 "
                    "AND id NOT IN (SELECT seance_id FROM presences_club)", (serie_id, auj))
        n = cur.rowcount
        cur.execute("UPDATE seances_club SET serie_id=NULL WHERE serie_id=?", (serie_id,))
        cur.execute("DELETE FROM series_club WHERE id=?", (serie_id,))
    return n


# ------------------------------------------------------------------ séances

_COLS = ("s.id", "s.uuid", "s.serie_id", "s.groupe_id", "s.titre", "s.type", "s.date", "s.heure_debut", "s.heure_fin",
         "s.lieu", "s.entraineur_id", "s.contenu", "s.annulee", "s.motif_annulation", "s.appel_fait", "s.notes", "g.nom",
         "(SELECT p.prenom || ' ' || p.nom FROM personnes p WHERE p.id = s.entraineur_id)",
         "(SELECT COUNT(*) FROM presences_club x WHERE x.seance_id = s.id AND x.statut IN ('present', 'retard'))",
         "(SELECT COUNT(*) FROM presences_club x WHERE x.seance_id = s.id)")
_CLES = ("id", "uuid", "serie_id", "groupe_id", "titre", "type", "date", "heure_debut", "heure_fin", "lieu",
         "entraineur_id", "contenu", "annulee", "motif_annulation", "appel_fait", "notes", "groupe", "entraineur",
         "presents", "pointes")


def _completer(s):
    s["taux"] = round(100 * s["presents"] / s["pointes"]) if s["pointes"] else None
    s["ferie"] = ag.ferie(s["date"])
    return s


def seances(club_id, debut=None, fin=None, groupe_id=None, avec_annulees=True):
    sql = (f"SELECT {', '.join(_COLS)} FROM seances_club s LEFT JOIN groupes g ON g.id = s.groupe_id "
           "WHERE s.club_id=?")
    p = [club_id]
    if debut:
        sql += " AND s.date>=?"
        p.append(_iso(debut))
    if fin:
        sql += " AND s.date<=?"
        p.append(_iso(fin))
    if groupe_id is not None:
        sql += " AND s.groupe_id=?"
        p.append(groupe_id)
    if not avec_annulees:
        sql += " AND s.annulee=0"
    sql += " ORDER BY s.date, s.heure_debut, s.titre"
    return [_completer(dict(zip(_CLES, l))) for l in base.lire_tous(sql, tuple(p))]


def seance(seance_id):
    l = base.lire_un(f"SELECT {', '.join(_COLS)} FROM seances_club s LEFT JOIN groupes g ON g.id = s.groupe_id "
                     "WHERE s.id=?", (seance_id,))
    return _completer(dict(zip(_CLES, l))) if l else None


def enregistrer_seance(club_id, champs, seance_id=None):
    v = {k: champs.get(k) for k in CHAMPS_SEANCE if k in champs}
    if "titre" in v or seance_id is None:
        v["titre"] = (v.get("titre") or "").strip()
        if not v["titre"]:
            raise ErreurAgenda("Donne un titre à la séance.")
    if seance_id is None and not v.get("date"):
        raise ErreurAgenda("Donne la date de la séance.")
    if v.get("date"):
        v["date"] = _iso(v["date"])
    if v.get("type") and v["type"] not in ag.LIBELLE_TYPE:
        raise ErreurAgenda("Type de séance inconnu.")
    for k in ("heure_debut", "heure_fin"):
        if k in v:
            v[k] = ag.verifier_heure(v[k])
    if v.get("heure_debut") and v.get("heure_fin") and v["heure_fin"] <= v["heure_debut"]:
        raise ErreurAgenda("L'heure de fin doit être après l'heure de début.")
    if seance_id is None:
        return base.inserer("seances_club", {"club_id": club_id, "type": v.pop("type", None) or "entrainement", **v})
    if v:
        base.ecrire(f"UPDATE seances_club SET {', '.join(c + '=?' for c in v)} WHERE id=?",
                    tuple(v.values()) + (seance_id,))
    return seance_id


def annuler_seance(seance_id, motif=""):
    base.ecrire("UPDATE seances_club SET annulee=1, motif_annulation=? WHERE id=?", ((motif or "").strip() or None,
                                                                                     seance_id))


def retablir_seance(seance_id):
    base.ecrire("UPDATE seances_club SET annulee=0, motif_annulation=NULL WHERE id=?", (seance_id,))


def supprimer_seance(seance_id):
    base.ecrire("DELETE FROM seances_club WHERE id=?", (seance_id,))


def dupliquer_seance(seance_id, nouvelle_date):
    s = seance(seance_id)
    if not s:
        raise ErreurAgenda("Séance introuvable.")
    club_id = base.lire_un("SELECT club_id FROM seances_club WHERE id=?", (seance_id,))[0]
    return enregistrer_seance(club_id, {**{k: s[k] for k in CHAMPS_SEANCE}, "date": nouvelle_date})


def prochaines(club_id, n=5, aujourdhui=None):
    auj = aujourdhui or date.today()
    return [s for s in seances(club_id, auj, auj + timedelta(days=60)) if not s["annulee"]][:n]


def sans_appel(club_id, aujourdhui=None, depuis_jours=60):
    """Séances passées (et non annulées) dont l'appel n'est pas fait."""
    auj = aujourdhui or date.today()
    return [s for s in seances(club_id, auj - timedelta(days=depuis_jours), auj - timedelta(days=1))
            if not s["annulee"] and not s["appel_fait"] and s["type"] != "reunion"]


# ------------------------------------------------------------------ appel

def attendus(seance_id):
    """Ids des personnes attendues : les membres du groupe (ou tous les adhérents, sans groupe) qui ont une
    adhésion non annulée pour la saison de la séance."""
    l = base.lire_un("SELECT club_id, groupe_id, date FROM seances_club WHERE id=?", (seance_id,))
    if not l:
        return []
    club_id, groupe_id, jour = l
    saison = cat.saison_de(jour)
    sql = ("SELECT a.personne_id FROM adhesions a WHERE a.club_id=? AND a.saison=? AND a.statut != 'annulee'")
    p = [club_id, saison]
    if groupe_id:
        sql += " AND a.personne_id IN (SELECT personne_id FROM groupes_membres WHERE groupe_id=?)"
        p.append(groupe_id)
    return [r[0] for r in base.lire_tous(sql, tuple(p))]


def appel(seance_id):
    """La feuille d'appel : [{personne_id, nom, prenom, categorie, statut, note, attendu, mineur,
    contact_urgence_tel}] — les attendus puis les autres personnes déjà pointées (invités)."""
    l = base.lire_un("SELECT date FROM seances_club WHERE id=?", (seance_id,))
    if not l:
        return []
    saison = cat.saison_de(l[0])
    att = set(attendus(seance_id))
    pointes = {r[0]: (r[1], r[2]) for r in base.lire_tous(
        "SELECT personne_id, statut, note FROM presences_club WHERE seance_id=?", (seance_id,))}
    ids = att | set(pointes)
    if not ids:
        return []
    marque = ",".join("?" * len(ids))
    res = []
    for pid, nom, prenom, naiss, tel in base.lire_tous(
            f"SELECT id, nom, prenom, date_naissance, contact_urgence_tel FROM personnes WHERE id IN ({marque}) "
            "ORDER BY nom COLLATE NOCASE, prenom COLLATE NOCASE", tuple(ids)):
        st, note = pointes.get(pid, (None, None))
        res.append({"personne_id": pid, "nom": nom, "prenom": prenom, "categorie": cat.categorie(naiss, saison),
                    "statut": st, "note": note, "attendu": pid in att, "mineur": dper.est_mineur(naiss),
                    "contact_urgence_tel": tel})
    return res


def enregistrer_appel(seance_id, statuts, marquer=True):
    """statuts : {personne_id: statut | (statut, note) | None}. None retire la ligne. L'appel est marqué fait
    (sauf marquer=False : ajout d'un invité en cours d'appel)."""
    with base.transaction() as cur:
        for pid, v in statuts.items():
            st, note = (v if isinstance(v, tuple) else (v, None))
            if st is None:
                cur.execute("DELETE FROM presences_club WHERE seance_id=? AND personne_id=?", (seance_id, pid))
                continue
            if st not in ag.LIBELLE_PRESENCE:
                raise ErreurAgenda(f"Statut de présence inconnu : {st}.")
            cur.execute("INSERT INTO presences_club (seance_id, personne_id, statut, note) VALUES (?, ?, ?, ?) "
                        "ON CONFLICT(seance_id, personne_id) DO UPDATE SET statut=excluded.statut, note=excluded.note",
                        (seance_id, pid, st, (note or "").strip() or None))
        if marquer:
            cur.execute("UPDATE seances_club SET appel_fait=1 WHERE id=?", (seance_id,))
    return bilan(seance_id)


def bilan(seance_id):
    st = {r[0]: r[1] for r in base.lire_tous("SELECT personne_id, statut FROM presences_club WHERE seance_id=?",
                                             (seance_id,))}
    return ag.bilan_appel(st, attendus(seance_id))


# ------------------------------------------------------------------ assiduité

def lignes_assiduite(club_id, debut, fin, groupe_id=None):
    """[(personne_id, date, statut ou None)] : pour chaque séance appelée de la période, chaque attendu
    (statut None s'il n'a pas été pointé) et chaque personne pointée."""
    res = []
    for s in seances(club_id, debut, fin, groupe_id, avec_annulees=False):
        if not s["appel_fait"]:
            continue
        st = {r[0]: r[1] for r in base.lire_tous("SELECT personne_id, statut FROM presences_club WHERE seance_id=?",
                                                 (s["id"],))}
        for pid in set(attendus(s["id"])) | set(st):
            res.append((pid, s["date"], st.get(pid)))
    return res


def assiduite(club_id, debut, fin, groupe_id=None):
    """{personne_id: {..., nom, prenom}} sur la période (voir noyau/club/agenda.assiduite)."""
    a = ag.assiduite(lignes_assiduite(club_id, debut, fin, groupe_id))
    if a:
        marque = ",".join("?" * len(a))
        for pid, nom, prenom in base.lire_tous(f"SELECT id, nom, prenom FROM personnes WHERE id IN ({marque})",
                                               tuple(a)):
            a[pid].update(nom=nom, prenom=prenom)
    return a


def par_groupe(club_id, debut, fin, aujourdhui=None):
    """[{groupe, seances, appelees, presents_moyens, taux}] sur la période, jusqu'à aujourd'hui."""
    res = {}
    fin = min(ag._jour(fin), ag._jour(aujourdhui or date.today()))
    for s in seances(club_id, debut, fin, avec_annulees=False):
        g = res.setdefault(s["groupe"] or "Tout le club", {"groupe": s["groupe"] or "Tout le club", "seances": 0,
                                                           "appelees": 0, "presents": 0, "pointes": 0})
        g["seances"] += 1
        if s["appel_fait"]:
            g["appelees"] += 1
            g["presents"] += s["presents"]
            g["pointes"] += s["pointes"]
    for g in res.values():
        g["presents_moyens"] = round(g["presents"] / g["appelees"], 1) if g["appelees"] else None
        g["taux"] = round(100 * g["presents"] / g["pointes"]) if g["pointes"] else None
    return sorted(res.values(), key=lambda g: g["groupe"])


def export_presences_csv(club_id, debut, fin, groupe_id=None):
    """Tableau (CSV ; point-virgule, UTF-8 avec BOM) : une ligne par adhérent, une colonne par séance."""
    ss = [s for s in seances(club_id, debut, fin, groupe_id, avec_annulees=False) if s["appel_fait"]]
    lettres = {"present": "P", "retard": "R", "excuse": "E", "absent": "A"}
    personnes, grille = {}, {}
    for s in ss:
        for ligne in appel(s["id"]):
            personnes[ligne["personne_id"]] = (ligne["nom"], ligne["prenom"])
            grille[(ligne["personne_id"], s["id"])] = lettres.get(ligne["statut"], "")
    assid = ag.assiduite(lignes_assiduite(club_id, debut, fin, groupe_id))
    entete = ["Nom", "Prénom"] + [f"{ag._jour(s['date']).strftime('%d/%m')} {s['titre']}" for s in ss] + ["Taux"]
    lignes = [";".join(entete)]
    for pid, (nom, prenom) in sorted(personnes.items(), key=lambda x: (x[1][0].lower(), x[1][1].lower())):
        t = assid.get(pid, {}).get("taux")
        lignes.append(";".join([nom, prenom] + [grille.get((pid, s["id"]), "") for s in ss]
                               + [f"{t} %" if t is not None else ""]))
    lignes.append("")
    lignes.append("P = présent ; R = en retard ; E = excusé ; A = absent")
    return "﻿" + "\n".join(lignes) + "\n"


def export_ics(club_id, debut, fin, groupe_id=None):
    c = dclub.club_principal() or {}
    return ag.ics(seances(club_id, debut, fin, groupe_id), c.get("nom") or "Club")
