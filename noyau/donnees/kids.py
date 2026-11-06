"""
Accès aux données de Kids (chantier D) : enfants de l'école d'athlé (adhérents des catégories baby à minimes),
carnet de progression (compétences validées), badges, équipement, vue des parents (leurs enfants seulement).
Les règles sont dans noyau/club/kids.py.
"""

from datetime import date

from noyau.donnees import base, club as dclub, personnes as dper
from noyau.club import kids as KI, categories as cat


class ErreurKids(Exception):
    """Message lisible ; rien n'a été modifié."""


def _assurer_referentiel():
    """Les compétences de base (créées au premier usage ; un club peut ensuite en ajouter)."""
    if base.lire_un("SELECT 1 FROM kids_competences WHERE club_id IS NULL LIMIT 1"):
        return
    with base.transaction() as cur:
        for k, (code, niveau, domaine, lib) in enumerate(KI.COMPETENCES):
            base.ecrire("INSERT OR IGNORE INTO kids_competences (code, niveau, domaine, libelle, ordre) VALUES (?,?,?,?,?)",
                        (code, niveau, domaine, lib, k), cur)


def competences(club_id=None):
    _assurer_referentiel()
    l = base.lire_tous("SELECT id, code, niveau, domaine, libelle, ordre, club_id FROM kids_competences WHERE actif=1 AND "
                       "(club_id IS NULL OR club_id=?) ORDER BY ordre, id", (club_id,))
    res = [dict(zip(("id", "code", "niveau", "domaine", "libelle", "ordre", "club_id"), x)) for x in l]
    return sorted(res, key=lambda c: (KI.ORDRE_NIVEAU.get(c["niveau"], 9), c["ordre"]))


def ajouter_competence(club_id, niveau, domaine, libelle):
    if niveau not in KI.LIBELLE_NIVEAU or domaine not in KI.LIBELLE_DOMAINE:
        raise ErreurKids("Niveau ou domaine inconnu.")
    libelle = (libelle or "").strip()
    if not libelle:
        raise ErreurKids("Écris la compétence.")
    import secrets
    code = f"club{club_id}_{secrets.token_hex(4)}"
    return base.inserer("kids_competences", {"code": code, "niveau": niveau, "domaine": domaine, "libelle": libelle,
                                             "ordre": 1000, "club_id": club_id})


def enfants(club_id, saison=None, section_id=None, groupe_id=None):
    """Adhérents des catégories baby à minimes, avec leur niveau conseillé et leur progression."""
    from noyau.donnees import comptes as dco
    saison = saison or cat.saison_de()
    comp = competences(club_id)
    res = []
    for a in dclub.adhesions(club_id, saison, groupe_id, section_id):
        if a["statut"] == "annulee" or not KI.est_kid(a["date_naissance"], saison):
            continue
        val = validees(a["personne_id"])
        prog = KI.progression(comp, val)
        res.append({**a, "accord_parental": bool(a["autorisation_parentale"]) or dco.a_consenti(a["personne_id"], "parental"),
                    "niveau_conseille": KI.niveau_conseille(a["date_naissance"], saison), "progression": prog,
                    "niveau_atteint": KI.niveau_atteint(prog), "nb_badges": len(badges(a["personne_id"]))})
    return res


def validees(personne_id):
    return {r[0] for r in base.lire_tous("SELECT competence_id FROM kids_validations WHERE personne_id=?", (personne_id,))}


def valider(personne_id, competence_id, par=None, jour=None, note=None):
    """Valide une compétence (une seule fois) puis met à jour les badges. Renvoie les badges gagnés à l'instant."""
    if not base.lire_un("SELECT 1 FROM kids_competences WHERE id=?", (competence_id,)):
        raise ErreurKids("Compétence inconnue.")
    base.ecrire("INSERT OR IGNORE INTO kids_validations (personne_id, competence_id, date, valide_par, note) "
                "VALUES (?,?,?,?,?)", (personne_id, competence_id, jour or date.today().isoformat(), par, note))
    return mettre_a_jour_badges(personne_id)


def retirer_validation(personne_id, competence_id):
    base.ecrire("DELETE FROM kids_validations WHERE personne_id=? AND competence_id=?", (personne_id, competence_id))
    # un badge gagné reste gagné : on ne retire jamais une récompense à un enfant


def _nb_presences(personne_id):
    return base.lire_un("SELECT COUNT(*) FROM presences_club WHERE personne_id=? AND statut IN ('present', 'retard')",
                        (personne_id,))[0]


def _nb_courses(personne_id):
    try:
        return base.lire_un("SELECT COUNT(*) FROM resultats_licencies WHERE personne_id=? AND statut='classe'",
                            (personne_id,))[0]
    except Exception:
        return 0


def mettre_a_jour_badges(personne_id):
    a = base.lire_un("SELECT club_id FROM adhesions WHERE personne_id=? ORDER BY saison DESC LIMIT 1", (personne_id,))
    dus = KI.badges_dus(competences(a[0] if a else None), validees(personne_id), _nb_presences(personne_id),
                        _nb_courses(personne_id))
    deja = {b["code"] for b in badges(personne_id)}
    nouveaux = [c for c in dus if c not in deja]
    for c in nouveaux:
        base.ecrire("INSERT OR IGNORE INTO kids_badges (personne_id, code, date) VALUES (?,?,?)",
                    (personne_id, c, date.today().isoformat()))
    return [KI.libelle_badge(c) for c in nouveaux]


def badges(personne_id):
    return [{"code": r[0], "date": r[1], "libelle": KI.libelle_badge(r[0])} for r in base.lire_tous(
        "SELECT code, date FROM kids_badges WHERE personne_id=? ORDER BY date, id", (personne_id,))]


CHAMPS_EQUIPEMENT = ("taille_vetement", "taille_tshirt", "pointure", "sac", "gourde", "frontale", "veste", "notes")


def equipement(personne_id):
    l = base.lire_un(f"SELECT {', '.join(CHAMPS_EQUIPEMENT)}, maj FROM kids_equipement WHERE personne_id=?", (personne_id,))
    return dict(zip(CHAMPS_EQUIPEMENT + ("maj",), l)) if l else {k: None for k in CHAMPS_EQUIPEMENT + ("maj",)}


def enregistrer_equipement(personne_id, champs):
    v = {k: champs.get(k) for k in CHAMPS_EQUIPEMENT if k in champs}
    for k in ("gourde", "frontale", "veste"):
        if k in v:
            v[k] = 1 if v[k] else 0
    v["maj"] = date.today().isoformat()
    cols = ", ".join(v)
    base.ecrire(f"INSERT INTO kids_equipement (personne_id, {cols}) VALUES (?, {', '.join('?' * len(v))}) "
                f"ON CONFLICT(personne_id) DO UPDATE SET {', '.join(k + '=excluded.' + k for k in v)}",
                (personne_id,) + tuple(v.values()))


def carnet(personne_id, club_id=None, saison=None):
    """Tout le carnet d'un enfant : fiche, catégorie, niveaux et compétences (validées ou non), badges, équipement,
    repères FFA, présences de la saison, consentements (accord parental, image)."""
    from noyau.donnees import comptes as dco
    f = dper.fiche(personne_id)
    if not f:
        raise ErreurKids("Enfant introuvable.")
    saison = saison or cat.saison_de()
    c = cat.categorie(f["date_naissance"], saison)
    comp = competences(club_id)
    val = {r[0]: (r[1], r[2]) for r in base.lire_tous("SELECT competence_id, date, valide_par FROM kids_validations "
                                                     "WHERE personne_id=?", (personne_id,))}
    niveaux = []
    prog = KI.progression(comp, set(val))
    for n, lib, ic in KI.NIVEAUX:
        niveaux.append({"code": n, "libelle": lib, "icone": ic, **prog[n],
                        "competences": [{**x, "validee": x["id"] in val, "date": val.get(x["id"], (None, None))[0],
                                         "par": val.get(x["id"], (None, None))[1],
                                         "libelle_domaine": KI.LIBELLE_DOMAINE[x["domaine"]]}
                                        for x in comp if x["niveau"] == n]})
    return {"personne": {k: f.get(k) for k in ("id", "nom", "prenom", "date_naissance", "sexe")}, "categorie": c,
            "niveau_conseille": KI.niveau_conseille(f["date_naissance"], saison), "niveau_atteint": KI.niveau_atteint(prog),
            "niveaux": niveaux, "badges": badges(personne_id), "equipement": equipement(personne_id),
            "reperes": KI.reperes_ffa(c["code"]) if c else [], "presences": _nb_presences(personne_id),
            "parents": f.get("parents") or [],
            "accord_parental": dco.a_consenti(personne_id, "parental"), "droit_image": dco.a_consenti(personne_id, "image")}


def enfants_du_parent(parent_personne_id):
    """Les enfants liés à ce parent (fiche Personne), seulement eux."""
    return [r[0] for r in base.lire_tous("SELECT enfant_id FROM personnes_liens WHERE parent_id=?", (parent_personne_id,))]


def seances_de_l_enfant(personne_id, jours=21):
    """Prochaines séances de ses groupes (pour les parents)."""
    from datetime import timedelta
    from noyau.donnees import agenda_club as dag
    groupes = set(dclub.groupes_de(personne_id))
    a = base.lire_un("SELECT club_id FROM adhesions WHERE personne_id=? ORDER BY saison DESC LIMIT 1", (personne_id,))
    if not a:
        return []
    auj = date.today()
    return [s for s in dag.seances(a[0], auj, auj + timedelta(days=jours), avec_annulees=True)
            if not s.get("groupe_id") or s["groupe_id"] in groupes]


def bilan_club(club_id, saison=None):
    """Pour le tableau du club et la page Claude : enfants par niveau conseillé et atteint, badges de la saison."""
    es = enfants(club_id, saison)
    par_niveau = {n: 0 for n, _l, _i in KI.NIVEAUX}
    atteints = {n: 0 for n, _l, _i in KI.NIVEAUX}
    for e in es:
        if e["niveau_conseille"]:
            par_niveau[e["niveau_conseille"]] += 1
        if e["niveau_atteint"]:
            atteints[e["niveau_atteint"]] += 1
    d0, _d1 = cat.bornes_saison(saison or cat.saison_de())
    ids = [e["personne_id"] for e in es]
    nb_b = 0
    if ids:
        nb_b = base.lire_un(f"SELECT COUNT(*) FROM kids_badges WHERE date >= ? AND personne_id IN ({','.join('?' * len(ids))})",
                            (d0.isoformat(), *ids))[0]
    return {"enfants": len(es), "par_niveau": par_niveau, "atteints": atteints, "badges_saison": nb_b,
            "sans_accord": sum(1 for e in es if not e["accord_parental"])}
