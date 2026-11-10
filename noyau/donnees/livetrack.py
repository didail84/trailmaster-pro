"""
Accès aux données de LiveTrack coach : les coureurs que suit un entraîneur, leurs suivis en direct (lien
Garmin LiveTrack, état, sortie rattachée) et les tests de configuration.

Le lien d'un suivi donne accès à la position du coureur pendant sa sortie : il est gardé sur cet ordinateur
seulement, et effacé automatiquement quelque temps après la fin du suivi (voir `purger_liens`).
Aucune requête vers Garmin ici : le logiciel ne lit pas la page LiveTrack.
"""

import json
from datetime import datetime, timedelta

from noyau.donnees import base
from noyau.livetrack import regles as R
from noyau.outils.evenements import emettre, DONNEES_MODIFIEES

ErreurLiveTrack = R.ErreurLiveTrack
DUREE_LIEN_APRES_FIN_JOURS = 30        # un lien de suivi terminé est effacé passé ce délai
LIEN_EFFACE = ""

COL_COUREUR = ("id", "athlete_id", "nom", "montre", "objectif", "notes", "actif", "cree_le")
COL_SUIVI = ("id", "coureur_id", "lien", "debut", "fin", "etat", "seance_id", "activite_id", "fc_visible", "notes")


def _maintenant():
    return datetime.now().isoformat(timespec="seconds")


def _iso(v, defaut=None):
    if v is None or v == "":
        return defaut
    if isinstance(v, datetime):
        return v.isoformat(timespec="seconds")
    try:
        return datetime.fromisoformat(str(v)[:19]).isoformat(timespec="seconds")
    except ValueError:
        raise ErreurLiveTrack(f"Date ou heure illisible : {v!r}.")


# ------------------------------------------------------------------ coureurs

def _coureur(l):
    return dict(zip(COL_COUREUR, l))


def athletes_disponibles():
    """[(id, « Prénom Nom »)] des profils coureurs du logiciel, pour relier une fiche à un profil."""
    return [(r[0], f"{r[2]} {r[1]}".strip()) for r in base.lire_tous(
        "SELECT id, nom, prenom FROM athletes ORDER BY prenom, nom")]


def coureurs(actifs=True):
    """Les coureurs suivis, avec le nombre de suivis et l'état du dernier."""
    sql = f"SELECT {', '.join(COL_COUREUR)} FROM livetrack_coureurs"
    if actifs:
        sql += " WHERE actif=1"
    res = []
    for l in base.lire_tous(sql + " ORDER BY nom COLLATE NOCASE"):
        c = _coureur(l)
        c["nb_suivis"] = base.lire_un("SELECT COUNT(*) FROM livetrack_suivis WHERE coureur_id=?", (c["id"],))[0]
        dernier = base.lire_un(f"SELECT {', '.join(COL_SUIVI)} FROM livetrack_suivis WHERE coureur_id=? "
                               "ORDER BY debut DESC, id DESC LIMIT 1", (c["id"],))
        c["dernier_suivi"] = dict(zip(COL_SUIVI, dernier)) if dernier else None
        c["etat"] = R.etat_affiche(c["dernier_suivi"])[0] if c["dernier_suivi"] else None
        res.append(c)
    return res


def coureur(coureur_id):
    l = base.lire_un(f"SELECT {', '.join(COL_COUREUR)} FROM livetrack_coureurs WHERE id=?", (coureur_id,))
    return _coureur(l) if l else None


def _champs_coureur(champs):
    nom = (champs.get("nom") or "").strip()
    if not nom:
        raise ErreurLiveTrack("Indique le nom du coureur.")
    return {"nom": nom, "athlete_id": champs.get("athlete_id") or None,
            "montre": (champs.get("montre") or "").strip() or None,
            "objectif": (champs.get("objectif") or "").strip() or None,
            "notes": (champs.get("notes") or "").strip() or None}


def creer_coureur(champs):
    v = _champs_coureur(champs)
    return base.inserer("livetrack_coureurs", {**v, "actif": 1, "cree_le": _maintenant()})


def modifier_coureur(coureur_id, champs):
    v = _champs_coureur(champs)
    if coureur(coureur_id) is None:
        raise ErreurLiveTrack("Coureur introuvable.")
    base.ecrire("UPDATE livetrack_coureurs SET nom=?, athlete_id=?, montre=?, objectif=?, notes=? WHERE id=?",
                (v["nom"], v["athlete_id"], v["montre"], v["objectif"], v["notes"], coureur_id))


def archiver_coureur(coureur_id, actif=False):
    """Masque un coureur de la liste sans perdre son historique (ou le remet)."""
    base.ecrire("UPDATE livetrack_coureurs SET actif=? WHERE id=?", (1 if actif else 0, coureur_id))


def supprimer_coureur(coureur_id):
    """Supprime le coureur, ses suivis et ses tests (la sortie rattachée, elle, reste dans l'historique)."""
    with base.transaction() as cur:
        cur.execute("DELETE FROM livetrack_tests WHERE coureur_id=?", (coureur_id,))
        cur.execute("DELETE FROM livetrack_suivis WHERE coureur_id=?", (coureur_id,))
        cur.execute("DELETE FROM livetrack_coureurs WHERE id=?", (coureur_id,))


# ------------------------------------------------------------------ suivis

def _suivi(l, cur=None):
    s = dict(zip(COL_SUIVI, l))
    s["etat_code"], s["etat_libelle"] = R.etat_affiche(s)
    s["duree"] = R.duree_suivi(s)
    s["lien_court"] = R.lien_masque(s["lien"]) if s["lien"] else "(lien effacé)"
    return s


def suivi(suivi_id):
    l = base.lire_un(f"SELECT {', '.join('s.' + c for c in COL_SUIVI)}, c.nom, c.athlete_id FROM livetrack_suivis s "
                     "JOIN livetrack_coureurs c ON c.id = s.coureur_id WHERE s.id=?", (suivi_id,))
    if not l:
        return None
    s = _suivi(l[:len(COL_SUIVI)])
    s["coureur_nom"], s["athlete_id"] = l[len(COL_SUIVI)], l[len(COL_SUIVI) + 1]
    return s


def suivis(coureur_id=None, etats=None, limite=300):
    """Les suivis, du plus récent au plus ancien, avec le nom du coureur et de la sortie rattachée.

    `etats` : codes d'état affichés (« en_cours », « termine », « annule », « expire »)."""
    sql = (f"SELECT {', '.join('s.' + c for c in COL_SUIVI)}, c.nom, c.athlete_id, a.nom, a.distance, a.duree "
           "FROM livetrack_suivis s JOIN livetrack_coureurs c ON c.id = s.coureur_id "
           "LEFT JOIN activites a ON a.id = s.activite_id")
    par = []
    if coureur_id:
        sql += " WHERE s.coureur_id=?"
        par.append(coureur_id)
    sql += " ORDER BY s.debut DESC, s.id DESC LIMIT ?"
    par.append(int(limite))
    n = len(COL_SUIVI)
    res = []
    for l in base.lire_tous(sql, tuple(par)):
        s = _suivi(l[:n])
        s["coureur_nom"], s["athlete_id"], s["sortie_nom"], s["sortie_km"], s["sortie_duree"] = l[n:n + 5]
        if etats and s["etat_code"] not in etats:
            continue
        res.append(s)
    return res


def suivis_en_cours():
    """Suivis en cours (non expirés), un par coureur au plus."""
    return suivis(etats=("en_cours",))


def ajouter_suivi(coureur_id, texte_lien, debut=None, seance_id=None, notes=None):
    """Enregistre le lien collé (le message entier du coureur convient). Renvoie l'id du suivi.

    Si le même lien est déjà en cours pour ce coureur, c'est lui qu'on renvoie ; un nouveau lien termine le suivi
    en cours précédent de ce coureur (un coureur n'a qu'une sortie en direct à la fois)."""
    if coureur(coureur_id) is None:
        raise ErreurLiveTrack("Choisis d'abord un coureur.")
    lien = R.valider_lien(texte_lien)
    deja = base.lire_un("SELECT id FROM livetrack_suivis WHERE coureur_id=? AND lien=? AND etat='en_cours'",
                        (coureur_id, lien))
    if deja:
        return deja[0]
    d = _iso(debut, _maintenant())
    with base.transaction() as cur:
        cur.execute("UPDATE livetrack_suivis SET etat='termine', fin=? WHERE coureur_id=? AND etat='en_cours'",
                    (d, coureur_id))
        return base.inserer("livetrack_suivis", {"coureur_id": coureur_id, "lien": lien, "debut": d, "etat": "en_cours",
                                                  "seance_id": seance_id, "notes": (notes or "").strip() or None}, cur)


def terminer_suivi(suivi_id, fin=None):
    base.ecrire("UPDATE livetrack_suivis SET etat='termine', fin=? WHERE id=?", (_iso(fin, _maintenant()), suivi_id))


def annuler_suivi(suivi_id):
    base.ecrire("UPDATE livetrack_suivis SET etat='annule', fin=COALESCE(fin, ?) WHERE id=?", (_maintenant(), suivi_id))


def reprendre_suivi(suivi_id):
    """Remet « en cours » un suivi terminé par erreur (le coureur est reparti, lien encore valable)."""
    s = suivi(suivi_id)
    if not s:
        raise ErreurLiveTrack("Suivi introuvable.")
    if not s["lien"]:
        raise ErreurLiveTrack("Le lien de ce suivi a été effacé : redemande un lien au coureur.")
    base.ecrire("UPDATE livetrack_suivis SET etat='en_cours', fin=NULL WHERE id=?", (suivi_id,))


def noter_suivi(suivi_id, notes):
    base.ecrire("UPDATE livetrack_suivis SET notes=? WHERE id=?", ((notes or "").strip() or None, suivi_id))


def definir_fc_visible(suivi_id, valeur):
    """La fréquence cardiaque s'est-elle vue sur la page ? 1 / 0 / None (pas vérifié)."""
    base.ecrire("UPDATE livetrack_suivis SET fc_visible=? WHERE id=?",
                (None if valeur is None else (1 if valeur else 0), suivi_id))


def supprimer_suivi(suivi_id):
    base.ecrire("DELETE FROM livetrack_suivis WHERE id=?", (suivi_id,))


def purger_liens(jours=DUREE_LIEN_APRES_FIN_JOURS, maintenant=None):
    """Efface les liens des suivis finis depuis plus de `jours` jours (ou jamais fermés et vieux d'autant).

    L'historique reste (date, durée, sortie rattachée, notes) ; seul le lien — qui ne sert plus — disparaît.
    Renvoie le nombre de liens effacés."""
    limite = ((maintenant or datetime.now()) - timedelta(days=jours)).isoformat(timespec="seconds")
    return base.ecrire_compte(
        "UPDATE livetrack_suivis SET lien=? WHERE lien<>? AND COALESCE(fin, debut) < ?", (LIEN_EFFACE, LIEN_EFFACE, limite))


def nb_liens_a_purger(jours=DUREE_LIEN_APRES_FIN_JOURS, maintenant=None):
    limite = ((maintenant or datetime.now()) - timedelta(days=jours)).isoformat(timespec="seconds")
    return base.lire_un("SELECT COUNT(*) FROM livetrack_suivis WHERE lien<>? AND COALESCE(fin, debut) < ?",
                        (LIEN_EFFACE, limite))[0]


# ------------------------------------------------------------------ sortie rattachée et analyse

def seances_prevues(athlete_id, autour=None):
    """Séances prévues du profil coureur lié, autour d'une date (la veille, le jour, le lendemain)."""
    if not athlete_id:
        return []
    j = (autour or datetime.now()).date()
    return [{"id": r[0], "nom": r[1], "date_prevue": r[2]} for r in base.lire_tous(
        "SELECT id, nom, date_prevue FROM seances_structurees WHERE athlete_id=? AND date_prevue BETWEEN ? AND ? "
        "ORDER BY date_prevue", (athlete_id, (j - timedelta(days=1)).isoformat(), (j + timedelta(days=1)).isoformat()))]


def choisir_seance(suivi_id, seance_id):
    base.ecrire("UPDATE livetrack_suivis SET seance_id=? WHERE id=?", (seance_id or None, suivi_id))


def activites_candidates(suivi_id):
    """Sorties du profil coureur lié qui peuvent être celle de ce suivi (pas déjà prises par un autre suivi)."""
    s = suivi(suivi_id)
    if not s or not s["athlete_id"]:
        return []
    lignes = base.lire_tous(
        "SELECT id, athlete_id, date, nom, type, distance, duree FROM activites WHERE athlete_id=? AND id NOT IN "
        "(SELECT activite_id FROM livetrack_suivis WHERE activite_id IS NOT NULL AND id<>?) "
        "ORDER BY date DESC LIMIT 200", (s["athlete_id"], suivi_id))
    acts = [dict(zip(("id", "athlete_id", "date", "nom", "type", "distance", "duree"), l)) for l in lignes]
    return R.activites_candidates(s, acts)


def rattacher_activite(suivi_id, activite_id):
    """Relie la sortie reçue (Garmin, Strava…) au suivi : il devient « terminé » et la sortie est analysée toute
    seule, comme n'importe quelle sortie (analyses automatiques)."""
    s = suivi(suivi_id)
    if not s:
        raise ErreurLiveTrack("Suivi introuvable.")
    if not base.lire_un("SELECT 1 FROM activites WHERE id=?", (activite_id,)):
        raise ErreurLiveTrack("Sortie introuvable.")
    pris = base.lire_un("SELECT id FROM livetrack_suivis WHERE activite_id=? AND id<>?", (activite_id, suivi_id))
    if pris:
        raise ErreurLiveTrack("Cette sortie est déjà rattachée à un autre suivi.")
    fin = s["fin"] or _maintenant()
    base.ecrire("UPDATE livetrack_suivis SET activite_id=?, etat=CASE WHEN etat='en_cours' THEN 'termine' ELSE etat END, "
                "fin=COALESCE(fin, ?) WHERE id=?", (activite_id, fin, suivi_id))
    emettre(DONNEES_MODIFIEES, athlete_id=s["athlete_id"])      # réveille les analyses automatiques


def detacher_activite(suivi_id):
    base.ecrire("UPDATE livetrack_suivis SET activite_id=NULL WHERE id=?", (suivi_id,))


def analyse_de_la_sortie(suivi_id):
    """Texte de l'analyse (la plus récente) de la sortie rattachée, ou None s'il n'y en a pas encore."""
    l = base.lire_un("SELECT a.contenu FROM analyses_ia a JOIN livetrack_suivis s ON s.activite_id = a.activite_id "
                     "WHERE s.id=? ORDER BY a.date_generation DESC, a.id DESC LIMIT 1", (suivi_id,))
    return l[0] if l and l[0] else None


# ------------------------------------------------------------------ fil de suivi

def suivi_de_activite(activite_id):
    """Le suivi en direct qui a été rattaché à cette sortie (pour le repère du fil d'activité), ou None."""
    l = base.lire_un(f"SELECT {', '.join('s.' + c for c in COL_SUIVI)}, c.nom FROM livetrack_suivis s "
                     "JOIN livetrack_coureurs c ON c.id = s.coureur_id WHERE s.activite_id=?", (activite_id,))
    if not l:
        return None
    s = _suivi(l[:len(COL_SUIVI)])
    s["coureur_nom"] = l[len(COL_SUIVI)]
    return s


def lignes_fil(limite=10):
    """Phrases du fil pour les derniers suivis : [(date, texte)], du plus récent au plus ancien."""
    return [(s["debut"], R.ligne_fil(s, s["coureur_nom"])) for s in suivis(limite=limite) if s["etat"] != "annule"]


# ------------------------------------------------------------------ tests de configuration

def enregistrer_test(coureur_id, resultats, note=None):
    """Garde le résultat d'un test (dict code → True/False/None). Si la fréquence cardiaque a été vue (ou non), le
    suivi en cours du coureur le retient. Renvoie (id du test, phrase de bilan)."""
    if coureur(coureur_id) is None:
        raise ErreurLiveTrack("Choisis d'abord un coureur.")
    propres = {c: (None if resultats.get(c) is None else bool(resultats.get(c))) for c in R.CODES_TEST}
    tid = base.inserer("livetrack_tests", {"coureur_id": coureur_id, "fait_le": _maintenant(),
                                           "resultats_json": json.dumps(propres), "note": (note or "").strip() or None})
    fc = R.fc_vue_par_le_test(propres)
    if fc is not None:
        base.ecrire("UPDATE livetrack_suivis SET fc_visible=? WHERE coureur_id=? AND etat='en_cours'", (fc, coureur_id))
    return tid, R.bilan_test(propres)


def tests(coureur_id, limite=20):
    res = []
    for l in base.lire_tous("SELECT id, fait_le, resultats_json, note FROM livetrack_tests WHERE coureur_id=? "
                            "ORDER BY fait_le DESC, id DESC LIMIT ?", (coureur_id, int(limite))):
        r = json.loads(l[2] or "{}")
        res.append({"id": l[0], "fait_le": l[1], "resultats": r, "note": l[3], "bilan": R.bilan_test(r)})
    return res


def dernier_test(coureur_id):
    t = tests(coureur_id, 1)
    return t[0] if t else None


# ------------------------------------------------------------------ export / import (sauvegarde en JSON)

def exporter():
    """Coureurs, suivis et tests en dictionnaire JSON (les liens effacés restent vides ; les identifiants du
    logiciel ne sortent pas : seuls les identifiants universels servent à refaire les liens à l'import)."""
    cs = []
    for l in base.lire_tous("SELECT id, uuid, nom, montre, objectif, notes, actif, cree_le, athlete_id "
                            "FROM livetrack_coureurs ORDER BY id"):
        ath = base.lire_un("SELECT prenom, nom FROM athletes WHERE id=?", (l[8],)) if l[8] else None
        cs.append({"uuid": l[1], "nom": l[2], "montre": l[3], "objectif": l[4], "notes": l[5], "actif": l[6],
                      "cree_le": l[7], "profil": f"{ath[0]} {ath[1]}".strip() if ath else None})
    sv = []
    for l in base.lire_tous("SELECT s.uuid, c.uuid, s.lien, s.debut, s.fin, s.etat, s.fc_visible, s.notes "
                            "FROM livetrack_suivis s JOIN livetrack_coureurs c ON c.id = s.coureur_id ORDER BY s.id"):
        sv.append({"uuid": l[0], "coureur": l[1], "lien": l[2], "debut": l[3], "fin": l[4], "etat": l[5],
                   "fc_visible": l[6], "notes": l[7]})
    ts = [{"uuid": l[0], "coureur": l[1], "fait_le": l[2], "resultats": json.loads(l[3] or "{}"), "note": l[4]}
          for l in base.lire_tous("SELECT t.uuid, c.uuid, t.fait_le, t.resultats_json, t.note FROM livetrack_tests t "
                                  "JOIN livetrack_coureurs c ON c.id = t.coureur_id ORDER BY t.id")]
    return {"logiciel": "Trail Hub Center", "module": "livetrack_coach", "version": 1, "exporte_le": _maintenant(),
            "coureurs": cs, "suivis": sv, "tests": ts}


def exporter_json():
    return json.dumps(exporter(), ensure_ascii=False, indent=1)


def importer(donnees):
    """Ajoute ce qui manque (rien n'est écrasé ni doublé : identifiant universel, sinon nom du coureur).
    Renvoie {coureurs, suivis, tests} ajoutés. Lève ErreurLiveTrack si ce n'est pas un export de ce module."""
    if isinstance(donnees, (str, bytes)):
        try:
            donnees = json.loads(donnees)
        except ValueError:
            raise ErreurLiveTrack("Ce fichier n'est pas un export LiveTrack coach (JSON illisible).")
    if not isinstance(donnees, dict) or donnees.get("module") != "livetrack_coach":
        raise ErreurLiveTrack("Ce fichier n'est pas un export LiveTrack coach.")
    ajoutes = {"coureurs": 0, "suivis": 0, "tests": 0}
    with base.transaction() as cur:
        par_uuid = {}
        for c in donnees.get("coureurs") or []:
            nom = (c.get("nom") or "").strip()
            if not nom:
                continue
            ex = cur.execute("SELECT id FROM livetrack_coureurs WHERE uuid=?", (c.get("uuid"),)).fetchone() if c.get("uuid") \
                else None
            ex = ex or cur.execute("SELECT id FROM livetrack_coureurs WHERE nom=? COLLATE NOCASE", (nom,)).fetchone()
            if ex:
                par_uuid[c.get("uuid")] = ex[0]
                continue
            ath = None
            if c.get("profil"):
                r = cur.execute("SELECT id FROM athletes WHERE (prenom || ' ' || nom)=? COLLATE NOCASE", (c["profil"],)).fetchone()
                ath = r[0] if r else None
            nouveau = base.inserer("livetrack_coureurs", {
                "nom": nom, "athlete_id": ath, "montre": c.get("montre"), "objectif": c.get("objectif"),
                "notes": c.get("notes"), "actif": 0 if c.get("actif") == 0 else 1,
                "cree_le": c.get("cree_le") or _maintenant()}, cur)
            par_uuid[c.get("uuid")] = nouveau
            ajoutes["coureurs"] += 1
        for s in donnees.get("suivis") or []:
            cid = par_uuid.get(s.get("coureur"))
            if not cid or not s.get("debut"):
                continue
            if s.get("uuid") and cur.execute("SELECT 1 FROM livetrack_suivis WHERE uuid=?", (s["uuid"],)).fetchone():
                continue
            if cur.execute("SELECT 1 FROM livetrack_suivis WHERE coureur_id=? AND debut=?", (cid, s["debut"])).fetchone():
                continue
            base.inserer("livetrack_suivis", {
                "coureur_id": cid, "lien": s.get("lien") or LIEN_EFFACE, "debut": s["debut"], "fin": s.get("fin"),
                "etat": s.get("etat") if s.get("etat") in R.LIBELLE_ETAT else "termine",
                "fc_visible": s.get("fc_visible"), "notes": s.get("notes")}, cur)
            ajoutes["suivis"] += 1
        for t in donnees.get("tests") or []:
            cid = par_uuid.get(t.get("coureur"))
            if not cid or not t.get("fait_le"):
                continue
            if cur.execute("SELECT 1 FROM livetrack_tests WHERE coureur_id=? AND fait_le=?", (cid, t["fait_le"])).fetchone():
                continue
            base.inserer("livetrack_tests", {"coureur_id": cid, "fait_le": t["fait_le"],
                                             "resultats_json": json.dumps(t.get("resultats") or {}), "note": t.get("note")}, cur)
            ajoutes["tests"] += 1
    return ajoutes
