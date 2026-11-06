"""
Kids, l'école d'athlé et de trail (chantier D), sans Qt ni SQL.

Un carnet de progression en quatre niveaux, chacun avec ses compétences
(courir, monter, descendre, s'orienter, sécurité et nature, esprit
d'équipe), validées par l'encadrant. Des badges récompensent un niveau
terminé, un domaine maîtrisé et l'assiduité. Aucun classement permanent :
chaque enfant ne se compare qu'à lui-même.

Les distances et dénivelés de référence sont ceux de la réglementation FFA
des courses hors stade (noyau/organisation/regles.py).
"""

from noyau.club import categories as cat

NIVEAUX = (("decouverte", "Découverte", "🌱"), ("explorateur", "Explorateur", "🧭"), ("montagnard", "Montagnard", "⛰️"),
           ("jeune_traileur", "Jeune traileur", "🏔️"))
LIBELLE_NIVEAU = {c: l for c, l, _i in NIVEAUX}
ICONE_NIVEAU = {c: i for c, _l, i in NIVEAUX}
ORDRE_NIVEAU = {c: k for k, (c, _l, _i) in enumerate(NIVEAUX)}
DOMAINES = (("courir", "Courir"), ("monter", "Monter"), ("descendre", "Descendre"), ("orienter", "S'orienter"),
            ("nature", "Sécurité et nature"), ("equipe", "Esprit d'équipe"))
LIBELLE_DOMAINE = dict(DOMAINES)
# niveau conseillé selon la catégorie FFA (l'encadrant peut faire passer un enfant au niveau suivant)
NIVEAU_DE_CATEGORIE = {"BB": "decouverte", "EA": "decouverte", "PO": "explorateur", "BE": "montagnard", "MI": "jeune_traileur"}
CATEGORIES_KIDS = ("BB", "EA", "PO", "BE", "MI")

COMPETENCES = (
    # Découverte (éveil athlétique, 7-9 ans)
    ("dec_courir_10", "decouverte", "courir", "Courir 10 minutes sans s'arrêter, en parlant"),
    ("dec_relais", "decouverte", "courir", "Faire un relais en passant le témoin"),
    ("dec_monter", "decouverte", "monter", "Monter une petite côte en marchant vite, sans s'arrêter"),
    ("dec_descendre", "decouverte", "descendre", "Descendre un chemin en regardant ses pieds et devant"),
    ("dec_balisage", "decouverte", "orienter", "Reconnaître le balisage et suivre les flèches"),
    ("dec_boire", "decouverte", "nature", "Boire pendant l'effort et garder ses déchets"),
    ("dec_attendre", "decouverte", "equipe", "Attendre le groupe au point de regroupement"),
    # Explorateur (poussins, 10-11 ans)
    ("exp_courir_20", "explorateur", "courir", "Courir 20 minutes à allure régulière"),
    ("exp_1500", "explorateur", "courir", "Finir un parcours nature de 1,5 km (repère FFA poussins)"),
    ("exp_marche_active", "explorateur", "monter", "Passer de la course à la marche active dans une montée"),
    ("exp_appuis", "explorateur", "descendre", "Descendre en petits appuis rapides sur terrain caillouteux"),
    ("exp_carte", "explorateur", "orienter", "Situer le départ et l'arrivée sur une carte simple"),
    ("exp_sac", "explorateur", "nature", "Préparer son sac : gourde, coupe-vent, en-cas"),
    ("exp_encourager", "explorateur", "equipe", "Encourager et aider un camarade en difficulté"),
    # Montagnard (benjamins, 12-13 ans)
    ("mon_40", "montagnard", "courir", "Courir 40 minutes en gérant son allure"),
    ("mon_3km", "montagnard", "courir", "Finir un trail de 3 km et 150 m D+ (repère FFA benjamins)"),
    ("mon_batons", "montagnard", "monter", "Monter une côte raide en poussant sur les cuisses"),
    ("mon_technique", "montagnard", "descendre", "Descendre un passage technique en sécurité"),
    ("mon_orientation", "montagnard", "orienter", "Suivre un itinéraire sur carte avec un adulte"),
    ("mon_meteo", "montagnard", "nature", "Adapter sa tenue à la météo et au froid"),
    ("mon_serre_file", "montagnard", "equipe", "Tenir le rôle de serre-file d'un petit groupe"),
    # Jeune traileur (minimes, 14-15 ans)
    ("jt_60", "jeune_traileur", "courir", "Courir 1 h en endurance, cardio ou sensations"),
    ("jt_5km", "jeune_traileur", "courir", "Finir un trail de 5 km et 250 m D+ (repère FFA minimes)"),
    ("jt_cote", "jeune_traileur", "monter", "Enchaîner des côtes en fractionné sans perdre la technique"),
    ("jt_descente", "jeune_traileur", "descendre", "Descendre vite et relâché sur sentier"),
    ("jt_seul", "jeune_traileur", "orienter", "Lire le profil d'une course et repérer ravitos et montées"),
    ("jt_alerte", "jeune_traileur", "nature", "Savoir donner l'alerte (15, 112) et protéger un blessé"),
    ("jt_benevole", "jeune_traileur", "equipe", "Aider comme bénévole sur une course du club"),
)

PALIERS_PRESENCE = (10, 25, 50, 100)


def niveau_conseille(date_naissance, saison=None):
    c = cat.categorie(date_naissance, saison)
    return NIVEAU_DE_CATEGORIE.get(c["code"]) if c else None


def est_kid(date_naissance, saison=None):
    c = cat.categorie(date_naissance, saison)
    return bool(c and c["code"] in CATEGORIES_KIDS)


def progression(competences, validees):
    """competences [{id, niveau, domaine}], validees {competence_id}. Renvoie {niveau: {total, faites, pct}}."""
    res = {}
    for n, _l, _i in NIVEAUX:
        l = [c for c in competences if c["niveau"] == n]
        f = sum(1 for c in l if c["id"] in validees)
        res[n] = {"total": len(l), "faites": f, "pct": round(100 * f / len(l)) if l else 0}
    return res


def niveau_atteint(prog):
    """Le plus haut niveau terminé, ou None."""
    fini = [n for n, _l, _i in NIVEAUX if prog[n]["total"] and prog[n]["faites"] == prog[n]["total"]]
    return fini[-1] if fini else None


def badges_dus(competences, validees, nb_presences=0, nb_courses=0):
    """Codes des badges mérités : un par niveau terminé, un par domaine maîtrisé sur les niveaux commencés,
    assiduité (10, 25, 50, 100 présences), première course."""
    codes = []
    prog = progression(competences, validees)
    for n, _l, _i in NIVEAUX:
        if prog[n]["total"] and prog[n]["faites"] == prog[n]["total"]:
            codes.append(f"niveau_{n}")
    commences = {c["niveau"] for c in competences if c["id"] in validees}
    for d, _l in DOMAINES:
        l = [c for c in competences if c["domaine"] == d and c["niveau"] in commences]
        if len(l) >= 2 and all(c["id"] in validees for c in l):
            codes.append(f"domaine_{d}")
    codes += [f"presences_{p}" for p in PALIERS_PRESENCE if nb_presences >= p]
    if nb_courses >= 1:
        codes.append("premiere_course")
    return codes


def libelle_badge(code):
    if code.startswith("niveau_"):
        n = code[7:]
        return f"{ICONE_NIVEAU.get(n, '')} {LIBELLE_NIVEAU.get(n, n)} terminé"
    if code.startswith("domaine_"):
        return {"courir": "🏃 Coureur", "monter": "🧗 Grimpeur", "descendre": "🐐 Chamois de la descente",
                "orienter": "🗺️ Orienteur", "nature": "🌿 Ami de la nature", "equipe": "🤝 Équipier"}.get(code[8:], code)
    if code.startswith("presences_"):
        return f"⭐ {code[10:]} entraînements"
    if code == "premiere_course":
        return "🎽 Première course"
    return code


def reperes_ffa(code_categorie):
    """Distances maximales en compétition pour la catégorie (réglementation FFA hors stade)."""
    from noyau.organisation import regles as R
    t = R.TRAIL_JEUNES.get(code_categorie)
    r = R.DISTANCE_MAX_ROUTE.get(code_categorie)
    l = []
    if code_categorie in R.TROP_JEUNES:
        l.append("pas de compétition hors stade (animations seulement)")
    if t:
        l.append(f"trail : {t[0]:g} km et {t[1]} m D+ au plus".replace(".", ","))
    if r:
        l.append(f"route : {r:g} km au plus".replace(".", ","))
    if code_categorie == "PO" and not r:
        l.append("route : 1,5 km au plus")
    return l
