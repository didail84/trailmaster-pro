"""
Accès aux données de l'annuaire trail. Les fiches de référence (livrées avec
le logiciel) sont recopiées dans la table « annuaire » et mises à jour à
chaque nouvelle version, sauf celles que tu as corrigées. Tes notes, favoris
et fiches ajoutées ne sont jamais touchés.
"""

import json
from datetime import date

from noyau.donnees import base
from noyau.annuaire import regles as R

ErreurAnnuaire = R.ErreurAnnuaire
CHAMPS = ("type", "nom", "sigle", "enseigne", "categorie", "commune", "code_postal", "departement", "adresse", "site",
          "affiliation", "pays", "categories", "groupe", "source", "notes")
COLONNES = ("id", "cle_reference") + CHAMPS + ("mes_notes", "favori", "masque", "modifie", "verifie_le")
CLE_VERSION = "annuaire_reference"


def _fiche(l):
    f = dict(zip(COLONNES, l))
    try:
        f["categories"] = json.loads(f["categories"]) if f["categories"] else []
    except ValueError:
        f["categories"] = []
    f["reference"] = bool(f["cle_reference"])
    return f


def _valeurs(f):
    v = {k: f.get(k) for k in CHAMPS if k in f}
    if "categories" in v:
        v["categories"] = json.dumps(v["categories"] or [], ensure_ascii=False) if v["categories"] else None
    return v


def version_reference():
    l = base.lire_un("SELECT valeur FROM parametres_app WHERE cle=?", (CLE_VERSION,))
    return l[0] if l else None


def synchroniser(reference=None, forcer=False):
    """Recopie la référence dans la base si sa version a changé. Renvoie {ajoutees, mises_a_jour, version}."""
    ref = reference or R.lire_reference()
    if not forcer and version_reference() == ref["version"]:
        return {"ajoutees": 0, "mises_a_jour": 0, "version": ref["version"]}
    ajout = maj = 0
    with base.transaction() as cur:
        existantes = {r[0]: (r[1], r[2]) for r in cur.execute("SELECT cle_reference, id, modifie FROM annuaire "
                                                               "WHERE cle_reference IS NOT NULL")}
        for f in ref["structures"] + ref["marques"]:
            v = _valeurs(R.verifier({**f, "type": f.get("type") or "marque"}))
            v["departement"] = f.get("departement") or v.get("departement")
            if f["cle"] not in existantes:
                base.inserer("annuaire", {"cle_reference": f["cle"], **v}, cur)
                ajout += 1
            elif not existantes[f["cle"]][1]:
                cur.execute(f"UPDATE annuaire SET {', '.join(k + '=?' for k in v)} WHERE id=?",
                            tuple(v.values()) + (existantes[f["cle"]][0],))
                maj += 1
        cur.execute("INSERT INTO parametres_app (cle, valeur) VALUES (?, ?) ON CONFLICT(cle) DO UPDATE SET "
                    "valeur=excluded.valeur", (CLE_VERSION, ref["version"]))
    return {"ajoutees": ajout, "mises_a_jour": maj, "version": ref["version"]}


def _synchroniser_sans_erreur():
    try:
        synchroniser()
    except (OSError, ValueError, KeyError, R.ErreurAnnuaire):
        pass


def fiches(types=None, avec_masquees=False):
    sql = f"SELECT {', '.join(COLONNES)} FROM annuaire"
    cond, p = [], []
    if types:
        cond.append(f"type IN ({','.join('?' * len(types))})")
        p += list(types)
    if not avec_masquees:
        cond.append("masque=0")
    if cond:
        sql += " WHERE " + " AND ".join(cond)
    sql += " ORDER BY departement, nom COLLATE NOCASE"
    return [_fiche(l) for l in base.lire_tous(sql, tuple(p))]


def fiche(fiche_id):
    l = base.lire_un(f"SELECT {', '.join(COLONNES)} FROM annuaire WHERE id=?", (fiche_id,))
    return _fiche(l) if l else None


def enregistrer(champs, fiche_id=None):
    """Crée une fiche à toi, ou modifie une fiche (une fiche de référence modifiée n'est plus écrasée)."""
    f = R.verifier(champs)
    v = _valeurs(f)
    if fiche_id is None:
        if base.lire_un("SELECT 1 FROM annuaire WHERE type=? AND nom=? COLLATE NOCASE AND COALESCE(commune,'')=? "
                        "COLLATE NOCASE", (f["type"], f["nom"], f.get("commune") or "")):
            raise ErreurAnnuaire(f"« {f['nom']} » est déjà dans l'annuaire.")
        return base.inserer("annuaire", {**v, "source": v.get("source") or "Ajoutée par toi",
                                         "mes_notes": champs.get("mes_notes"), "favori": 1 if champs.get("favori") else 0})
    v["mes_notes"] = champs.get("mes_notes")
    base.ecrire(f"UPDATE annuaire SET {', '.join(k + '=?' for k in v)}, modifie=1 WHERE id=?",
                tuple(v.values()) + (fiche_id,))
    return fiche_id


def definir_favori(fiche_id, favori=True):
    base.ecrire("UPDATE annuaire SET favori=? WHERE id=?", (1 if favori else 0, fiche_id))


def noter(fiche_id, mes_notes):
    base.ecrire("UPDATE annuaire SET mes_notes=? WHERE id=?", ((mes_notes or "").strip() or None, fiche_id))


def marquer_verifiee(fiche_id, jour=None):
    base.ecrire("UPDATE annuaire SET verifie_le=? WHERE id=?", ((jour or date.today()).isoformat(), fiche_id))


def supprimer(fiche_id):
    """Une fiche à toi est supprimée ; une fiche de référence est masquée (elle ne reviendrait sinon à la
    prochaine mise à jour)."""
    l = base.lire_un("SELECT cle_reference FROM annuaire WHERE id=?", (fiche_id,))
    if not l:
        return
    if l[0]:
        base.ecrire("UPDATE annuaire SET masque=1 WHERE id=?", (fiche_id,))
    else:
        base.ecrire("DELETE FROM annuaire WHERE id=?", (fiche_id,))


def reafficher_masquees():
    return base.ecrire_compte("UPDATE annuaire SET masque=0 WHERE masque=1")


def importer(fiches_lues):
    """Ajoute les fiches d'un tableau (noyau/annuaire/regles.lire_csv). Les doublons (même type, nom et
    commune) sont complétés sans écraser. Renvoie {ajoutees, completees}."""
    ajout = comp = 0
    for f in fiches_lues:
        l = base.lire_un("SELECT id FROM annuaire WHERE type=? AND nom=? COLLATE NOCASE AND COALESCE(commune,'')=? "
                         "COLLATE NOCASE", (f["type"], f["nom"], f.get("commune") or ""))
        if l:
            v = {k: x for k, x in _valeurs(f).items() if x not in (None, "", "[]")}
            vides = [k for k in v if base.lire_un(f"SELECT 1 FROM annuaire WHERE id=? AND ({k} IS NULL OR {k}='')",
                                                  (l[0],))]
            if vides:
                base.ecrire(f"UPDATE annuaire SET {', '.join(k + '=?' for k in vides)} WHERE id=?",
                            tuple(v[k] for k in vides) + (l[0],))
                comp += 1
        else:
            base.inserer("annuaire", {**_valeurs(f), "source": "Import d'un tableau"})
            ajout += 1
    return {"ajoutees": ajout, "completees": comp}


def noms_de_marques(categorie=None):
    """Noms des marques pour compléter la saisie (matériel, produits de nutrition) : celles de la catégorie
    d'abord, puis les favorites, puis les autres."""
    _synchroniser_sans_erreur()
    ms = fiches(("marque",))
    ms.sort(key=lambda m: (bool(categorie) and categorie not in m["categories"], not m["favori"], m["nom"].lower()))
    return [m["nom"] for m in ms]


def noms_de_magasins():
    _synchroniser_sans_erreur()
    return [f"{m['nom']}" for m in sorted(fiches(("magasin",)), key=lambda m: (not m["favori"], m["nom"].lower()))]


def chiffres():
    res = {}
    for t, d, n in base.lire_tous("SELECT type, departement, COUNT(*) FROM annuaire WHERE masque=0 GROUP BY type, "
                                  "departement"):
        res.setdefault(t, {})[d or "?"] = n
    return res


def materiel_par_marque(athlete_id):
    """{marque: nombre d'objets de ton matériel} — pour l'onglet Marques."""
    return {r[0]: r[1] for r in base.lire_tous(
        "SELECT marque, COUNT(*) FROM materiel WHERE athlete_id=? AND marque IS NOT NULL AND marque != '' "
        "GROUP BY marque", (athlete_id,))} if athlete_id else {}
