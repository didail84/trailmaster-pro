"""
Défis en famille : un objectif commun (kilomètres ou nombre de sorties)
sur une période, avec chacun sa part.

La part d'un participant = ses sorties enregistrées dans le logiciel s'il
est relié à un coureur (course, trail, marche, randonnée, vélo compté au
tiers), plus ce qui a été noté à la main (balade des enfants, vélo…).
Badges à 25, 50, 75 et 100 % de l'objectif commun.
"""

from datetime import date, datetime

from noyau.donnees import base

MESURES = {"km": "kilomètres", "sorties": "sorties"}
ICONES = ("montagne", "etoile", "soleil", "fusee", "tortue", "coeur")
BADGES = [(25, "Premiers pas"), (50, "Mi-chemin"), (75, "Dernière montée"), (100, "Sommet atteint")]
TYPES_COMPTES = {"Course": 1.0, "Trail": 1.0, "Randonnée": 1.0, "Marche": 1.0, "Vélo": 1 / 3, "VTT": 1 / 3}


class ErreurDefi(Exception):
    pass


def creer(nom, objectif, debut, fin, mesure="km", icone="montagne", participants=()):
    nom = (nom or "").strip()
    if not nom:
        raise ErreurDefi("Donne un nom au défi.")
    try:
        objectif = float(objectif)
    except (TypeError, ValueError):
        raise ErreurDefi("L'objectif doit être un nombre.")
    if objectif <= 0:
        raise ErreurDefi("L'objectif doit être positif.")
    if not debut or not fin:
        raise ErreurDefi("Indique le début et la fin du défi.")
    if mesure not in MESURES:
        raise ErreurDefi("Mesure inconnue.")
    if str(fin)[:10] < str(debut)[:10]:
        raise ErreurDefi("La fin doit être après le début.")
    with base.transaction() as cur:
        cur.execute("INSERT INTO defis_famille (nom, mesure, objectif, debut, fin, icone, cree_le) VALUES (?,?,?,?,?,?,?)",
                    (nom, mesure, objectif, str(debut)[:10], str(fin)[:10], icone if icone in ICONES else "montagne",
                     datetime.now().isoformat(timespec="seconds")))
        defi_id = cur.lastrowid
    for p in participants:
        ajouter_participant(defi_id, **p) if isinstance(p, dict) else ajouter_participant(defi_id, p)
    return defi_id


def ajouter_participant(defi_id, prenom, athlete_id=None, personne_id=None):
    prenom = (prenom or "").strip()
    if not prenom:
        raise ErreurDefi("Indique le prénom.")
    base.ecrire("INSERT OR IGNORE INTO defis_participants (defi_id, prenom, athlete_id, personne_id) VALUES (?,?,?,?)",
                (defi_id, prenom, athlete_id, personne_id))
    l = base.lire_un("SELECT id FROM defis_participants WHERE defi_id=? AND prenom=?", (defi_id, prenom))
    return l[0]


def noter(participant_id, valeur, jour=None, note=None):
    try:
        valeur = float(valeur)
    except (TypeError, ValueError):
        raise ErreurDefi("La valeur doit être un nombre.")
    if valeur <= 0:
        raise ErreurDefi("La valeur doit être positive.")
    base.ecrire("INSERT INTO defis_saisies (participant_id, date, valeur, note) VALUES (?,?,?,?)",
                (participant_id, str(jour or date.today())[:10], valeur, (note or "")[:200] or None))


def supprimer(defi_id):
    base.ecrire("DELETE FROM defis_saisies WHERE participant_id IN (SELECT id FROM defis_participants WHERE defi_id=?)",
                (defi_id,))
    base.ecrire("DELETE FROM defis_participants WHERE defi_id=?", (defi_id,))
    base.ecrire("DELETE FROM defis_famille WHERE id=?", (defi_id,))


def _part_activites(athlete_id, debut, fin, mesure):
    if not athlete_id:
        return 0.0
    lignes = base.lire_tous("SELECT type, distance FROM activites WHERE athlete_id=? AND substr(date,1,10)>=? "
                            "AND substr(date,1,10)<=?", (athlete_id, debut, fin))
    if mesure == "sorties":
        return float(sum(1 for t, _d in lignes if t in TYPES_COMPTES))
    return sum((d or 0) * TYPES_COMPTES.get(t, 0) for t, d in lignes)


def etat(defi_id):
    d = base.lire_un("SELECT id, nom, mesure, objectif, debut, fin, icone FROM defis_famille WHERE id=?", (defi_id,))
    if not d:
        return None
    defi = dict(zip(("id", "nom", "mesure", "objectif", "debut", "fin", "icone"), d))
    parts = []
    for pid, prenom, aid in base.lire_tous("SELECT id, prenom, athlete_id FROM defis_participants WHERE defi_id=? "
                                           "ORDER BY id", (defi_id,)):
        auto = _part_activites(aid, defi["debut"], defi["fin"], defi["mesure"])
        main = base.lire_un("SELECT ifnull(sum(valeur),0) FROM defis_saisies WHERE participant_id=? AND date>=? "
                            "AND date<=?", (pid, defi["debut"], defi["fin"]))[0]
        parts.append({"id": pid, "prenom": prenom, "athlete_id": aid, "auto": round(auto, 1),
                      "main": round(main, 1), "total": round(auto + main, 1)})
    total = round(sum(p["total"] for p in parts), 1)
    pct = min(100, round(100 * total / defi["objectif"])) if defi["objectif"] else 0
    aujourd = date.today().isoformat()
    jours_restants = (date.fromisoformat(defi["fin"]) - date.today()).days if defi["fin"] >= aujourd else 0
    defi.update(participants=sorted(parts, key=lambda p: -p["total"]), total=total, pct=pct,
                badges=[{"seuil": s, "nom": n, "obtenu": pct >= s} for s, n in BADGES],
                jours_restants=jours_restants, termine=defi["fin"] < aujourd,
                reste=max(0, round(defi["objectif"] - total, 1)))
    return defi


def lister(en_cours_seulement=False):
    sql = "SELECT id FROM defis_famille"
    params = ()
    if en_cours_seulement:
        sql += " WHERE fin>=?"
        params = (date.today().isoformat(),)
    return [etat(i) for (i,) in base.lire_tous(sql + " ORDER BY fin DESC, id DESC", params)]
