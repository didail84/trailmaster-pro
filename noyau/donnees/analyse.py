"""
Accès aux données de l'Analyse (chantier E) : prévu ou réel de tes courses,
bilans du club par saison, bilans des événements et de leurs éditions.
Lecture seule, sauf le facteur de correction que tu choisis d'appliquer.
"""

from noyau.analyse import bilans as B
from noyau.club import categories as cat, kids as K
from noyau.donnees import base

# ------------------------------------------------------------------ prévu ou réel


def _prevision(rb_id):
    """Temps prévu d'un roadbook, selon la méthode choisie dans le roadbook."""
    from noyau.course import roadbook as rbk, strategie as strat
    from noyau.entrainement.conformite import parser_allure
    d = rbk.charger(rb_id)
    if not d:
        return None
    trace, mode = d.get("trace") or [], d.get("mode_niveau") or "allure"
    s, facteurs = None, dict(strat.FACTEURS_PAR_DEFAUT)
    try:
        if mode == "temps":
            t = str(d.get("temps_vise") or "")
            if t.count(":") == 2:
                s = B.lire_temps(t)
            else:                        # dans le roadbook, « 6:30 » veut dire 6 h 30 (comme à la saisie)
                h = rbk._hhmm(t)
                s = h[0] * 3600 + h[1] * 60 if h else float(t.replace(",", ".")) * 3600 if t else None
        elif mode == "appris":
            from noyau.course.estimation_temps_course import estimer_temps_course
            est = estimer_temps_course(d["athlete_id"], d.get("distance_km"), d.get("denivele_m"), d.get("date_course"))
            s = est and est["secondes"]
        elif mode == "vo2max":
            s = rbk.duree_depuis_vo2max(d["athlete_id"], d.get("distance_km"), d.get("denivele_m"))
        if not s and len(trace) >= 2:
            al = parser_allure(d.get("allure_plat") or "")
            if al:
                s = rbk.temps_au_km(trace, al).total_s
    except (TypeError, ValueError, ZeroDivisionError):
        s = None
    if not s:
        return None
    return {"id": d["id"], "nom": d["nom"], "date": d.get("date_course"), "methode": mode, "prevu_s": s,
            "prudent_s": s * facteurs["prudent"], "ambitieux_s": s * facteurs["ambitieux"]}


def prevu_reel(athlete_id):
    """Tes courses qui ont un roadbook et un résultat le même jour. Renvoie (lignes, synthese)."""
    from noyau.course import roadbook as rbk
    rbk.creer_table()
    res = [{"id": l[0], "nom": l[1], "date": l[2], "temps": l[3]} for l in base.lire_tous(
        "SELECT id, nom_course, date, temps FROM resultats_courses WHERE athlete_id=? ORDER BY date DESC", (athlete_id,))]
    dates = {str(r["date"])[:10] for r in res}
    prev = []
    for rb in rbk.lister(athlete_id):
        if rb[2] and str(rb[2])[:10] in dates:
            p = _prevision(rb[0])
            if p:
                prev.append(p)
    lignes, syn = B.prevu_reel(res, prev)
    for l in lignes:
        l["methode"] = next((p["methode"] for p in prev if p["id"] == l["roadbook_id"]), "")
    syn["applique"] = facteur_applique(athlete_id)
    return lignes, syn


def facteur_applique(athlete_id):
    from data.database import obtenir_parametre
    try:
        v = obtenir_parametre(f"correction_prevision_{athlete_id}")
        return float(v) if v not in (None, "") else None
    except (TypeError, ValueError):
        return None


def appliquer_correction(athlete_id, facteur):
    """Les temps « appris » de la Stratégie seront multipliés par ce facteur ; None pour l'enlever."""
    from data.database import definir_parametre
    if facteur is not None and not 0.7 <= float(facteur) <= 1.4:
        raise ValueError("Facteur hors des bornes raisonnables (0,7 à 1,4).")
    definir_parametre(f"correction_prevision_{athlete_id}", "" if facteur is None else str(round(float(facteur), 3)))


# ------------------------------------------------------------------ bilans du club

def bilan_saison(club_id, saison, section_id=None):
    from noyau.donnees import club as dclub
    adh = [a for a in dclub.adhesions(club_id, saison, section_id=section_id) if a["statut"] != "annulee"]
    prec = {a["personne_id"] for a in dclub.adhesions(club_id, cat.saison_precedente(saison), section_id=section_id)
            if a["statut"] != "annulee"}
    ids = {a["personne_id"] for a in adh}
    debut, fin = cat.bornes_saison(saison)
    sql_s = ("SELECT s.id, (SELECT COUNT(*) FROM presences_club x WHERE x.seance_id = s.id AND x.statut IN "
             "('present', 'retard')) FROM seances_club s WHERE s.club_id=? AND s.annulee=0 AND s.appel_fait=1 "
             "AND s.date BETWEEN ? AND ?")
    par = [club_id, debut.isoformat(), fin.isoformat()]
    if section_id:
        sql_s += " AND (s.groupe_id IS NULL OR s.groupe_id IN (SELECT id FROM groupes WHERE section_id=?))"
        par.append(section_id)
    seances = base.lire_tous(sql_s, tuple(par))
    res = []
    if ids:
        marque = ",".join("?" * len(ids))
        res = base.lire_tous(
            f"SELECT personne_id, course, date, distance_km, denivele_m, statut, classement_categorie, classement_sexe "
            f"FROM resultats_licencies WHERE personne_id IN ({marque}) AND date BETWEEN ? AND ?",
            tuple(ids) + (debut.isoformat(), fin.isoformat()))
    classes = [r for r in res if r[5] in (None, "classe")]
    return {
        "saison": saison, "adherents": len(adh),
        "nouveaux": len(ids - prec), "renouveles": len(ids & prec),
        "fidelisation": round(100 * len(ids & prec) / len(prec)) if prec else None,
        "partis": len(prec - ids),
        "femmes": sum(1 for a in adh if (a.get("sexe") or "").upper().startswith("F")),
        "hommes": sum(1 for a in adh if (a.get("sexe") or "").upper().startswith(("H", "M"))),
        "jeunes": sum(1 for a in adh if a["categorie"] and a["categorie"]["code"] in K.CATEGORIES_KIDS),
        "cotisations": round(sum(float(a.get("montant_paye") or 0) for a in adh), 2),
        "reste_a_payer": round(sum(float(a.get("reste") or 0) for a in adh), 2),
        "seances": len(seances),
        "presence_moyenne": round(sum(n for _i, n in seances) / len(seances), 1) if seances else None,
        "resultats": len(res), "coureurs_en_course": len({r[0] for r in res}),
        "courses": len({(r[1], str(r[2])[:10]) for r in res}),
        "podiums": sum(1 for r in classes if (r[6] and r[6] <= 3) or (r[7] and r[7] <= 3)),
        "km_course": round(sum(float(r[3] or 0) for r in classes)), "dplus_course": int(sum(r[4] or 0 for r in classes)),
    }


def bilans_club(club_id, section_id=None):
    """Une ligne par saison (de la plus ancienne à la plus récente) et l'évolution des grands chiffres."""
    from noyau.donnees import club as dclub
    lignes = [bilan_saison(club_id, s, section_id) for s in sorted(dclub.saisons(club_id))]
    lignes = [l for l in lignes if l["adherents"] or l["seances"] or l["resultats"]]
    evo = {k: B.evolution({l["saison"]: l[k] for l in lignes}) for k in ("adherents", "presence_moyenne", "resultats")}
    return lignes, evo


# ------------------------------------------------------------------ bilans des événements

def bilan_evenement(evenement_id):
    from noyau.donnees import organisation as dor, chrono as dch, commandement as dcm, logistique as dlo
    ev = dor.evenement(evenement_id)
    if not ev:
        return None
    ch = dor.chiffres(evenement_id)["total"]
    try:
        et = dch.etat(evenement_id)["epreuves"]
    except Exception:          # événement sans épreuve ni chrono
        et = []
    partants = sum(e["partants"] for e in et)
    abandons = sum(1 for i in dch._avec_chrono(evenement_id) if i.get("statut_course") == "abandon")
    non_partants = sum(1 for i in dch._avec_chrono(evenement_id) if i.get("statut_course") == "non_partant")
    arrives = sum(e["arrives"] for e in et)
    try:
        ctl = dlo.controle(evenement_id)
        besoin, pourvus = ctl["besoin"], ctl["pourvus"]
    except Exception:
        besoin = pourvus = 0
    try:
        b = dlo.bilan(evenement_id)
        rec = b["recettes_realisees"] or b["recettes_prevues"]
        dep = b["depenses_realisees"] or b["depenses_prevues"]
    except Exception:
        rec = dep = 0
    inc = dcm.incidents(evenement_id)
    r = B.bilan_evenement(ch["inscrits"], max(0, partants - non_partants), arrives, abandons, len(inc), besoin, pourvus,
                          float(rec or 0), float(dep or 0))
    r.update({"id": ev["id"], "nom": ev["nom"], "date": ev["date_debut"], "commune": ev.get("commune") or "",
              "graves": sum(1 for i in inc if i.get("gravite") == "urgent"),
              "edition": B.nom_de_base(ev["nom"]), "recettes": round(float(rec or 0), 2),
              "depenses": round(float(dep or 0), 2)})
    return r


def bilans_evenements():
    """Tous les événements, du plus récent au plus ancien, et les éditions d'une même course regroupées."""
    from noyau.donnees import organisation as dor
    lignes = [b for b in (bilan_evenement(e["id"]) for e in dor.evenements()) if b]
    lignes.sort(key=lambda l: str(l["date"]), reverse=True)
    editions = {}
    for l in lignes:
        editions.setdefault(l["edition"], []).append(l)
    comp = {k: sorted(v, key=lambda l: str(l["date"])) for k, v in editions.items() if len(v) >= 2}
    return lignes, comp


def tableau(athlete_id=None, club_id=None):
    """Résumé pour le tableau de bord et la page Claude."""
    out = {}
    if athlete_id is not None:
        l, s = prevu_reel(athlete_id)
        out["prevu_reel"] = {"courses": s["courses"], "texte": s["texte"], "facteur": s["facteur"],
                             "dernieres": [{k: x[k] for k in ("course", "date", "reel_s", "prevu_s", "ecart_pct", "scenario")}
                                           for x in l[:5]]}
    if club_id:
        lc, _e = bilans_club(club_id)
        out["club"] = lc[-3:]
    le, _c = bilans_evenements()
    out["evenements"] = le[:5]
    return out
