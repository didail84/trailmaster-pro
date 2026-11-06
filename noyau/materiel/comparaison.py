"""
Comparaison du matériel exigé par une course avec ce que tu possèdes
(étape 3.4, bloc 13).

Pour chaque ligne de la liste : ✅ tu l'as, ⚠️ à vérifier (caractéristique
non renseignée, matériel « à surveiller », batterie pas contrôlée depuis
longtemps), ❌ il te manque (absent, pas en nombre suffisant, ou pas aux
exigences : pas assez d'eau, veste pas assez imperméable…). Plus le poids
du sac obligatoire et la liste de ce qu'il reste à acheter ou emprunter.
"""

from datetime import date, timedelta

from noyau.materiel.equipements import EQUIPEMENTS, CARACTERISTIQUES, LIBELLE_NIVEAU, libelle_valeur, sans_accents

STATUTS = (("ok", "Je l'ai", "✅"), ("verifier", "À vérifier", "⚠️"), ("manque", "Il me manque", "❌"),
           ("manuel", "À cocher toi-même", "☐"))
LIBELLE_STATUT = {c: l for c, l, _i in STATUTS}
ICONE_STATUT = {c: i for c, _l, i in STATUTS}
A_CONTROLER = {"frontale", "frontale_secours", "piles", "telephone", "batterie_externe"}
CONTROLE_JOURS = 180


def _fr(v, d=1):
    t = f"{v:.{d}f}".replace(".", ",")
    return t[:-2] if t.endswith(",0") else t


def _carac(item, cle):
    c = item.get("caracteristiques") or {}
    v = c.get(cle)
    try:
        return None if v in (None, "") else float(v)
    except (TypeError, ValueError):
        return None


def _qte(item):
    try:
        return max(1, int(item.get("quantite") or 1))
    except (TypeError, ValueError):
        return 1


def candidats(code, inventaire):
    actifs = [i for i in inventaire if (i.get("statut") or "Actif") != "Retiré"]
    if code == "frontale_secours":
        frontales = [i for i in actifs if i.get("equipement") == "frontale"]
        # une deuxième frontale (ou une frontale en 2 exemplaires) sert de lampe de secours
        surplus = []
        if frontales:
            reste = sum(_qte(i) for i in frontales) - 1
            if reste > 0:
                surplus = [dict(frontales[-1], quantite=reste)]
        return [i for i in actifs if i.get("equipement") == "frontale_secours"] + surplus
    return [i for i in actifs if i.get("equipement") == code]


def _reserve_avec_mes_produits(req, produits):
    """La réserve alimentaire composée avec tes produits de course favoris ou validés (Nutrition)."""
    from noyau.nutrition.catalogue import par_portion
    kcal_min = req.get("valeur_min") or 800
    utiles = [p for p in produits if (par_portion(p, "energie_kcal") or 0) > 0]
    if not utiles:
        return None
    compte, total, poids, i = {}, 0.0, 0.0, 0
    while total < kcal_min and i < 60:
        p = utiles[i % len(utiles)]
        compte[p["id"]] = compte.get(p["id"], 0) + 1
        total += par_portion(p, "energie_kcal")
        poids += p.get("portion") or 0
        i += 1
    noms = {p["id"]: p["nom"] for p in utiles}
    texte = " + ".join(f"{n} × {noms[k]}" for k, n in compte.items())
    return {"statut": "ok", "detail": f"À prendre parmi tes produits de course : {texte} (≈ {total:.0f} kcal).",
            "objets": [noms[k] for k in compte], "poids_g": round(poids), "poids_connu": True}


def evaluer(req, inventaire, date_course=None, produits_nutrition=None):
    """Une ligne de la liste → {statut, detail, objets: [noms], poids_g, poids_connu}."""
    code = req.get("equipement")
    if code == "reserve_alimentaire" and produits_nutrition and not candidats(code, inventaire):
        r = _reserve_avec_mes_produits(req, produits_nutrition)
        if r:
            return r
    if not code or code not in EQUIPEMENTS:
        if req.get("dans_le_sac"):
            return {"statut": "ok", "detail": "Coché comme prêt.", "objets": [], "poids_g": 0, "poids_connu": False}
        return {"statut": "manuel", "detail": "Pas reconnu dans ton équipement : coche-le quand il est dans le sac.",
                "objets": [], "poids_g": 0, "poids_connu": False}
    e = EQUIPEMENTS[code]
    cands = candidats(code, inventaire)
    besoin = max(1, int(req.get("quantite") or 1))
    possede = sum(_qte(i) for i in cands)
    objets = [i.get("nom") for i in cands]
    poids_items = cands
    if not cands:
        return {"statut": "manque", "detail": f"Aucun « {e['nom'].lower()} » dans ton équipement.", "objets": [],
                "poids_g": 0, "poids_connu": False}
    if possede < besoin:
        return {"statut": "manque", "detail": f"Il en faut {besoin}, tu en as {possede}.", "objets": objets,
                "poids_g": 0, "poids_connu": False}
    statut, details = "ok", []
    carac = e["carac"]
    vmin = req.get("valeur_min")
    if carac and vmin:
        lib, unite, cumul = CARACTERISTIQUES[carac]
        valeurs = [(_carac(i, carac), i) for i in cands]
        connues = [(v, i) for v, i in valeurs if v is not None]
        if cumul:
            total = sum(v * _qte(i) for v, i in connues)
            if total >= vmin:
                details.append(f"{_fr(total)} {unite} au total pour {libelle_valeur(code, vmin)} demandés.")
            elif len(connues) < len(valeurs):
                statut = "verifier"
                details.append(f"{lib} de certains objets à renseigner ({_fr(total)} {unite} connus sur "
                               f"{libelle_valeur(code, vmin)}).")
            else:
                statut = "manque"
                details.append(f"{_fr(total)} {unite} seulement pour {libelle_valeur(code, vmin)} demandés.")
        else:
            if not connues:
                statut = "verifier"
                details.append(f"{lib} à renseigner : {libelle_valeur(code, vmin)} demandés.")
            else:
                meilleur, objet = max(connues, key=lambda x: x[0])
                poids_items = [objet]
                if meilleur >= vmin:
                    details.append(f"{objet.get('nom')} : {libelle_valeur(code, meilleur)} "
                                   f"(il faut {libelle_valeur(code, vmin)}).")
                else:
                    statut = "manque"
                    details.append(f"{objet.get('nom')} : {libelle_valeur(code, meilleur)}, il faut "
                                   f"{libelle_valeur(code, vmin)}.")
    if code == "veste_impermeable":
        texte = sans_accents(req.get("libelle"))
        for cle, mot, lib in (("coutures_etanches", "couture", "coutures étanches"), ("capuche", "capuche", "capuche")):
            if mot in texte:
                vals = [(i.get("caracteristiques") or {}).get(cle) for i in poids_items]
                if any(v is True for v in vals):
                    continue
                if all(v is False for v in vals):
                    statut = "manque"
                    details.append(f"Ta veste n'a pas de {lib}.")
                elif statut == "ok":
                    statut = "verifier"
                    details.append(f"Vérifie : {lib}.")
    surveiller = [i for i in poids_items if (i.get("statut") or "") == "À surveiller"]
    if surveiller and statut == "ok":
        statut = "verifier"
        details.append(f"{surveiller[0].get('nom')} est « à surveiller ».")
    if code in A_CONTROLER and statut == "ok":
        ref = date_course or date.today()
        vieux = []
        for i in poids_items:
            c = i.get("controle_le")
            try:
                d = date.fromisoformat(str(c)[:10]) if c else None
            except ValueError:
                d = None
            if d is not None and ref - d > timedelta(days=CONTROLE_JOURS):
                vieux.append(i.get("nom"))
        if vieux:
            statut = "verifier"
            details.append(f"Batterie ou piles de « {vieux[0]} » contrôlées il y a plus de 6 mois.")
    if not details:
        details.append(", ".join(o for o in objets if o) + ".")
    poids = [i.get("poids_g") for i in poids_items]
    connus = [float(p) * _qte(i) for p, i in zip(poids, poids_items) if p not in (None, "")]
    return {"statut": statut, "detail": " ".join(details), "objets": objets,
            "poids_g": round(sum(connus)), "poids_connu": len(connus) == len(poids_items)}


def comparer(liste, inventaire, date_course=None, produits_nutrition=None):
    """liste : lignes de materiel_obligatoire (ou d'un repère) ; inventaire : ton matériel.
    Renvoie {lignes: [{**req, **evaluation}], compte: {niveau: {statut: n}}, pret_pct, manquants,
    a_verifier, poids_g, poids_incomplet, resume}.
    produits_nutrition : tes produits de course favoris ou validés ; ils servent de réserve alimentaire
    quand ton équipement n'en a pas."""
    if isinstance(date_course, str):
        try:
            date_course = date.fromisoformat(date_course[:10])
        except ValueError:
            date_course = None
    lignes = [{**r, **evaluer(r, inventaire, date_course, produits_nutrition)} for r in liste]
    compte = {}
    for l in lignes:
        compte.setdefault(l["niveau"], {}).setdefault(l["statut"], 0)
        compte[l["niveau"]][l["statut"]] += 1
    oblig = [l for l in lignes if l["niveau"] == "obligatoire"]
    ok = sum(1 for l in oblig if l["statut"] == "ok")
    pret = round(100 * ok / len(oblig)) if oblig else None
    manquants = [l for l in lignes if l["statut"] == "manque" and l["niveau"] in ("obligatoire", "meteo")]
    a_verifier = [l for l in lignes if l["statut"] in ("verifier", "manuel") and l["niveau"] == "obligatoire"]
    poids = sum(l["poids_g"] for l in oblig)
    incomplet = sum(1 for l in oblig if l["statut"] != "manque" and l.get("equipement") and not l["poids_connu"])
    if not oblig:
        resume = "Aucun matériel obligatoire dans la liste."
    elif ok == len(oblig):
        resume = f"Tout le matériel obligatoire est prêt ({len(oblig)} éléments)."
    else:
        m = sum(1 for l in oblig if l["statut"] == "manque")
        v = len(oblig) - ok - m
        morceaux = []
        if m:
            morceaux.append(f"{m} élément{'s' if m > 1 else ''} manquant{'s' if m > 1 else ''}")
        if v:
            morceaux.append(f"{v} à vérifier")
        resume = f"{ok} sur {len(oblig)} prêts : " + " et ".join(morceaux) + "."
    return {"lignes": lignes, "compte": compte, "pret_pct": pret, "manquants": manquants, "a_verifier": a_verifier,
            "poids_g": poids, "poids_incomplet": incomplet, "resume": resume}


def texte_liste_de_courses(comparaison, nom_course=""):
    """Texte à copier : ce qu'il manque, par niveau, avec l'exigence."""
    lignes = [f"À prévoir pour {nom_course} :" if nom_course else "À prévoir :"]
    for niv in ("obligatoire", "meteo"):
        items = [l for l in comparaison["manquants"] if l["niveau"] == niv]
        if items:
            lignes.append(f"{LIBELLE_NIVEAU[niv]} :")
            for l in items:
                code = l.get("equipement")
                nom = EQUIPEMENTS[code]["nom"] if code else l["libelle"]
                exig = libelle_valeur(code, l.get("valeur_min"))
                lignes.append(f"- {nom}" + (f" ({exig} minimum)" if exig else "") + f" — {l['detail']}")
    if len(lignes) == 1:
        lignes.append("Rien : tout est prêt.")
    return "\n".join(lignes)
