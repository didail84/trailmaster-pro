"""
Accès aux données du matériel obligatoire (étape 3.4) : ton équipement
(table materiel, avec ses nouvelles colonnes : équipement reconnu, poids,
quantité, caractéristiques, contrôle des batteries) et la liste du
règlement de chaque course (table materiel_obligatoire).
"""

import json
from datetime import date

from noyau.donnees import base
from noyau.materiel.equipements import EQUIPEMENTS, LIBELLE_NIVEAU, reconnaitre

COLONNES_EQUIPEMENT = ("id", "nom", "type", "statut", "equipement", "poids_g", "quantite", "caracteristiques",
                       "controle_le", "notes", "date_achat", "marque", "magasin")
CHAMPS_MODIFIABLES = ("nom", "type", "statut", "equipement", "poids_g", "quantite", "caracteristiques",
                      "controle_le", "notes", "marque", "magasin")
COLONNES_LISTE = ("id", "course_id", "ordre", "libelle", "equipement", "niveau", "quantite", "valeur_min",
                  "precision", "dans_le_sac")
# Type de la table materiel proposé pour chaque famille d'équipement (écran Matériel)
TYPE_PAR_FAMILLE = {"Vêtements": "Vêtement", "Lumière": "Autre", "Sécurité": "Autre", "Hydratation": "Autre",
                    "Nutrition": "Autre", "Soins": "Autre", "Divers": "Autre"}
TYPE_PAR_CODE = {"sac": "Sac à dos", "batons": "Bâtons", "gps_trace": "Montre GPS"}


class ErreurEquipement(Exception):
    """Message lisible ; rien n'a été modifié."""


def _equipement(l):
    d = dict(zip(COLONNES_EQUIPEMENT, l))
    try:
        d["caracteristiques"] = json.loads(d["caracteristiques"]) if d["caracteristiques"] else {}
    except ValueError:
        d["caracteristiques"] = {}
    return d


def equipements(athlete_id, avec_retires=False):
    """Tout ton matériel (y compris chaussures et sacs saisis dans l'écran Matériel)."""
    if athlete_id is None:
        return []
    sql = f"SELECT {', '.join(COLONNES_EQUIPEMENT)} FROM materiel WHERE athlete_id=?"
    if not avec_retires:
        sql += " AND COALESCE(statut, 'Actif') != 'Retiré'"
    sql += " ORDER BY COALESCE(equipement, 'zzz'), nom COLLATE NOCASE"
    return [_equipement(l) for l in base.lire_tous(sql, (athlete_id,))]


def equipement(materiel_id):
    l = base.lire_un(f"SELECT {', '.join(COLONNES_EQUIPEMENT)} FROM materiel WHERE id=?", (materiel_id,))
    return _equipement(l) if l else None


def _preparer(champs):
    champs = {k: champs[k] for k in CHAMPS_MODIFIABLES if k in champs}
    if "nom" in champs:
        champs["nom"] = (champs["nom"] or "").strip()
        if not champs["nom"]:
            raise ErreurEquipement("Donne un nom à ce matériel.")
    if champs.get("equipement") and champs["equipement"] not in EQUIPEMENTS:
        raise ErreurEquipement("Équipement inconnu.")
    if champs.get("poids_g") is not None and champs["poids_g"] < 0:
        raise ErreurEquipement("Le poids ne peut pas être négatif.")
    if "quantite" in champs:
        champs["quantite"] = max(1, int(champs["quantite"] or 1))
    if "caracteristiques" in champs:
        c = {k: v for k, v in (champs["caracteristiques"] or {}).items() if v not in (None, "")}
        champs["caracteristiques"] = json.dumps(c, ensure_ascii=False) if c else None
    return champs


def creer_equipement(athlete_id, champs):
    champs = _preparer(champs)
    if not champs.get("nom"):
        raise ErreurEquipement("Donne un nom à ce matériel.")
    code = champs.get("equipement")
    champs.setdefault("type", TYPE_PAR_CODE.get(code) or TYPE_PAR_FAMILLE.get(EQUIPEMENTS[code]["famille"], "Autre")
                      if code else "Autre")
    champs.setdefault("statut", "Actif")
    return base.inserer("materiel", {"athlete_id": athlete_id, **champs})


def modifier_equipement(materiel_id, champs):
    champs = _preparer(champs)
    if not champs:
        return
    base.verifier_colonnes(list(champs))
    base.ecrire(f"UPDATE materiel SET {', '.join(c + '=?' for c in champs)} WHERE id=?",
                tuple(champs.values()) + (materiel_id,))


def supprimer_equipement(materiel_id):
    base.ecrire("DELETE FROM materiel WHERE id=?", (materiel_id,))


def batteries_controlees(materiel_ids, jour=None):
    jour = jour or date.today().isoformat()
    with base.transaction() as cur:
        for i in materiel_ids:
            base.ecrire("UPDATE materiel SET controle_le=? WHERE id=?", (jour, i), cur)


def relier_automatiquement(athlete_id):
    """Reconnaît l'équipement des objets qui n'en ont pas encore, d'après leur nom (« Frontale Petzl » →
    lampe frontale). Renvoie le nombre d'objets reliés. Les chaussures ne sont jamais reliées."""
    n = 0
    with base.transaction() as cur:
        for i in equipements(athlete_id):
            if i["equipement"] or (i["type"] or "") == "Chaussures":
                continue
            code = reconnaitre(i["nom"])
            if code:
                base.ecrire("UPDATE materiel SET equipement=? WHERE id=?", (code, i["id"]), cur)
                n += 1
    return n


# ------------------------------------------------------------------
# Liste du règlement d'une course
# ------------------------------------------------------------------

def liste_de_la_course(course_id):
    if course_id is None:
        return []
    return [dict(zip(COLONNES_LISTE, l)) for l in base.lire_tous(
        f"SELECT {', '.join(COLONNES_LISTE)} FROM materiel_obligatoire WHERE course_id=? ORDER BY ordre, id",
        (course_id,))]


def enregistrer_liste(athlete_id, course_id, lignes, source="Règlement officiel"):
    """Remplace la liste de la course par `lignes` ([{libelle, equipement, niveau, quantite, valeur_min,
    precision, dans_le_sac}]) et note la date de vérification du règlement."""
    if course_id is None:
        raise ErreurEquipement("Choisis d'abord une course enregistrée.")
    propres = []
    for l in lignes:
        lib = (l.get("libelle") or "").strip()
        if not lib:
            continue
        if l.get("niveau") not in LIBELLE_NIVEAU:
            raise ErreurEquipement(f"Niveau inconnu pour « {lib} ».")
        if l.get("equipement") and l["equipement"] not in EQUIPEMENTS:
            raise ErreurEquipement(f"Équipement inconnu pour « {lib} ».")
        propres.append(l)
    with base.transaction() as cur:
        base.ecrire("DELETE FROM materiel_obligatoire WHERE course_id=?", (course_id,), cur)
        for k, l in enumerate(propres):
            base.inserer("materiel_obligatoire", {
                "athlete_id": athlete_id, "course_id": course_id, "ordre": k, "libelle": l["libelle"].strip()[:240],
                "equipement": l.get("equipement"), "niveau": l["niveau"], "quantite": max(1, int(l.get("quantite") or 1)),
                "valeur_min": l.get("valeur_min"), "precision": l.get("precision") or "",
                "dans_le_sac": 1 if l.get("dans_le_sac") else 0}, cur)
        base.ecrire("UPDATE courses_calendrier SET reglement_verifie_le=?, reglement_source=? WHERE id=?",
                    (date.today().isoformat() if propres else None, source if propres else None, course_id), cur)


def cocher_sac(ligne_id, dans_le_sac=True):
    base.ecrire("UPDATE materiel_obligatoire SET dans_le_sac=? WHERE id=?", (1 if dans_le_sac else 0, ligne_id))


def vider_sac(course_id):
    base.ecrire("UPDATE materiel_obligatoire SET dans_le_sac=0 WHERE course_id=?", (course_id,))


def infos_reglement(course_id):
    """(date de vérification, source) du règlement enregistré pour la course, ou (None, None)."""
    l = base.lire_un("SELECT reglement_verifie_le, reglement_source FROM courses_calendrier WHERE id=?", (course_id,))
    return (l[0], l[1]) if l else (None, None)


def courses(athlete_id):
    """[{id, nom, date, distance_km, denivele_m, type_terrain, lien, nb_lignes}] du calendrier."""
    if athlete_id is None:
        return []
    lignes = base.lire_tous(
        "SELECT c.id, c.nom, c.date, c.distance_km, c.denivele_m, c.type_terrain, c.lien, c.reglement_verifie_le, "
        "(SELECT COUNT(*) FROM materiel_obligatoire m WHERE m.course_id = c.id) "
        "FROM courses_calendrier c WHERE c.athlete_id=? ORDER BY COALESCE(c.date, '9999')", (athlete_id,))
    cles = ("id", "nom", "date", "distance_km", "denivele_m", "type_terrain", "lien", "reglement_verifie_le",
            "nb_lignes")
    return [dict(zip(cles, l)) for l in lignes]
