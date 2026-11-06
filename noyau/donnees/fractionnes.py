"""
Accès aux données du fractionné (étape 3.5) : tes séances perso
(table fractionnes) et les fractionnés faits pendant une sortie, avec le
temps de chaque répétition (table fractionnes_realises).
"""

import json
from datetime import datetime, date

from noyau.donnees import base
from noyau.entrainement import fractionne as fr

COLONNES_REALISE = ("id", "activite_id", "date", "modele", "nom", "format", "terrain", "vma_ref", "structure_json",
                    "repetitions_json", "rpe", "source", "notes")


class ErreurFractionne(Exception):
    """Message lisible ; rien n'a été modifié."""


def _maintenant():
    return datetime.now().isoformat(timespec="seconds")


# ------------------------------------------------------------------
# Séances : bibliothèque + séances perso
# ------------------------------------------------------------------

def seances_perso(athlete_id):
    if athlete_id is None:
        return []
    res = []
    for id_, nom, fmt, terrain, sj, notes in base.lire_tous(
            "SELECT id, nom, format, terrain, structure_json, notes FROM fractionnes WHERE athlete_id=? "
            "ORDER BY nom COLLATE NOCASE", (athlete_id,)):
        try:
            s = json.loads(sj)
        except ValueError:
            continue
        s.update({"code": f"perso:{id_}", "nom": nom, "format": fmt, "terrain": terrain, "perso": True,
                  "notes": notes or ""})
        res.append(s)
    return res


def seances_disponibles(athlete_id, fmt=None, terrain=None):
    """Tes séances perso puis la bibliothèque, filtrées par format (court/long) et terrain (plat/côte)."""
    toutes = seances_perso(athlete_id) + [dict(s) for s in fr.BIBLIOTHEQUE]
    return [s for s in toutes if (fmt is None or s["format"] == fmt) and (terrain is None or s["terrain"] == terrain)]


def seance(code, athlete_id=None):
    if code and str(code).startswith("perso:"):
        return next((s for s in seances_perso(athlete_id) if s["code"] == code), None)
    m = fr.modele(code)
    return dict(m) if m else None


def _structure_propre(structure):
    err = fr.verifier_structure(structure)
    if err:
        raise ErreurFractionne(err)
    cles = ("nom", "format", "terrain", "echauffement_min", "retour_calme_min", "blocs", "objectif", "description")
    return {k: structure.get(k) for k in cles}


def enregistrer_perso(athlete_id, structure, perso_id=None):
    s = _structure_propre(structure)
    texte = json.dumps(s, ensure_ascii=False)
    if perso_id is None:
        return base.inserer("fractionnes", {"athlete_id": athlete_id, "nom": s["nom"].strip(), "format": s["format"],
                                            "terrain": s["terrain"], "structure_json": texte,
                                            "notes": structure.get("notes") or "", "date_creation": _maintenant()})
    base.ecrire("UPDATE fractionnes SET nom=?, format=?, terrain=?, structure_json=?, notes=? WHERE id=?",
                (s["nom"].strip(), s["format"], s["terrain"], texte, structure.get("notes") or "", perso_id))
    return perso_id


def supprimer_perso(perso_id):
    base.ecrire("DELETE FROM fractionnes WHERE id=?", (perso_id,))


# ------------------------------------------------------------------
# Fractionnés faits
# ------------------------------------------------------------------

def _realise(l):
    d = dict(zip(COLONNES_REALISE, l))
    try:
        d["structure"] = json.loads(d.pop("structure_json"))
    except ValueError:
        d["structure"] = None
    try:
        d["repetitions"] = json.loads(d.pop("repetitions_json") or "[]")
    except ValueError:
        d["repetitions"] = []
    return d


def realises(athlete_id, activite_id=None, depuis=None):
    """Fractionnés faits, du plus récent au plus ancien (ceux d'une sortie si activite_id est donné)."""
    if athlete_id is None and activite_id is None:
        return []
    sql = f"SELECT {', '.join(COLONNES_REALISE)} FROM fractionnes_realises WHERE "
    if activite_id is not None:
        sql += "activite_id=?"
        params = [activite_id]
    else:
        sql += "athlete_id=?"
        params = [athlete_id]
    if depuis:
        sql += " AND date >= ?"
        params.append(depuis)
    sql += " ORDER BY date DESC, id DESC"
    return [r for r in (_realise(l) for l in base.lire_tous(sql, tuple(params))) if r["structure"]]


def realise(realise_id):
    l = base.lire_un(f"SELECT {', '.join(COLONNES_REALISE)} FROM fractionnes_realises WHERE id=?", (realise_id,))
    return _realise(l) if l else None


def enregistrer_realise(athlete_id, structure, repetitions, date_iso=None, activite_id=None, vma_ref=None,
                        rpe=None, notes="", source="saisie", code=None, realise_id=None):
    """Enregistre (ou met à jour) un fractionné fait. repetitions : [{numero, temps_s?, distance_m?, dplus_m?, fc?}]."""
    s = _structure_propre(structure)
    nums = {r["numero"] for r in fr.repetitions(s)}
    propres = []
    for r in repetitions:
        if r.get("numero") not in nums:
            continue
        if not r.get("temps_s") and not r.get("distance_m"):
            continue
        for cle in ("temps_s", "distance_m"):
            if r.get(cle) is not None and r[cle] <= 0:
                raise ErreurFractionne("Un temps ou une distance doit être positif.")
        propres.append({k: r.get(k) for k in ("numero", "temps_s", "distance_m", "dplus_m", "fc", "debut_s")
                        if r.get(k) is not None})
    if rpe is not None and not 1 <= int(rpe) <= 10:
        raise ErreurFractionne("La difficulté ressentie se note de 1 à 10.")
    date_iso = (date_iso or date.today().isoformat())[:10]
    champs = {"athlete_id": athlete_id, "activite_id": activite_id, "date": date_iso, "modele": code,
              "nom": s["nom"], "format": s["format"], "terrain": s["terrain"], "vma_ref": vma_ref,
              "structure_json": json.dumps(s, ensure_ascii=False),
              "repetitions_json": json.dumps(propres, ensure_ascii=False), "rpe": int(rpe) if rpe else None,
              "source": source, "notes": notes or ""}
    if realise_id is None:
        champs["date_saisie"] = _maintenant()
        return base.inserer("fractionnes_realises", champs)
    del champs["athlete_id"]
    base.ecrire(f"UPDATE fractionnes_realises SET {', '.join(c + '=?' for c in champs)} WHERE id=?",
                tuple(champs.values()) + (realise_id,))
    return realise_id


def supprimer_realise(realise_id):
    base.ecrire("DELETE FROM fractionnes_realises WHERE id=?", (realise_id,))


# ------------------------------------------------------------------
# Autour : VMA de référence, sorties à relier, trace
# ------------------------------------------------------------------

def vma_de_reference(athlete_id):
    """(vma km/h, source) : la VMA de ta fiche si elle est renseignée, sinon celle estimée sur tes sorties,
    sinon (None, None)."""
    if athlete_id is None:
        return None, None
    l = base.lire_un("SELECT vma FROM athletes WHERE id=?", (athlete_id,))
    if l and l[0]:
        return float(l[0]), "de ta fiche"
    try:
        from noyau.entrainement.vma import calculer_vma
        r = calculer_vma(athlete_id, "mois", 3)
    except Exception:
        r = None
    if r and r.get("actuelle"):
        return round(float(r["actuelle"]), 1), "estimée sur tes sorties"
    return None, None


def sorties_recentes(athlete_id, limite=60):
    """[(id, date, nom, type, distance_km, duree_s, a_une_trace)] les plus récentes d'abord."""
    if athlete_id is None:
        return []
    return base.lire_tous(
        "SELECT a.id, a.date, a.nom, a.type, a.distance, a.duree, "
        "EXISTS(SELECT 1 FROM parcours_gpx p WHERE p.activite_id = a.id AND p.trace_json IS NOT NULL) "
        "FROM activites a WHERE a.athlete_id=? ORDER BY a.date DESC, a.id DESC LIMIT ?", (athlete_id, limite))


def sortie(activite_id):
    """(id, date, nom, type, distance_km, duree_s) ou None."""
    return base.lire_un("SELECT id, date, nom, type, distance, duree FROM activites WHERE id=?", (activite_id,))


def points_de_la_sortie(activite_id):
    from noyau.donnees import parcours as dparc
    texte = dparc.trace_de_l_activite(activite_id) if activite_id else None
    try:
        return json.loads(texte) if texte else []
    except ValueError:
        return []
