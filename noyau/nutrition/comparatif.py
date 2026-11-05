"""
Comparatif de 2 à 4 produits de course (étape 3.3) : critères d'effort
(glucides par portion, densité, sodium, caféine, prix pour 60 g de
glucides, ta tolérance) ET Nutri-Score, avec des phrases de synthèse.
"""

from noyau.nutrition.catalogue import par_portion, sodium_mg_portion, nutriscore_de, prix_pour_60g, libelle_portion


def _fr(v, d=0, unite=""):
    if v is None:
        return "—"
    t = f"{v:.{d}f}".replace(".", ",")
    return t + (f" {unite}" if unite else "")


def comparer(produits, verdicts=None):
    """produits : 2 à 4 dicts (catalogue). Renvoie {"colonnes": [noms], "lignes": [(critère, [valeurs])],
    "nutriscores": [lettre|None], "phrases": [...]}."""
    verdicts = verdicts or {}
    ps = list(produits)[:4]
    ns = [nutriscore_de(p) for p in ps]
    g = [par_portion(p, "glucides_g") for p in ps]
    kcal = [par_portion(p, "energie_kcal") for p in ps]
    na = [sodium_mg_portion(p) for p in ps]
    caf = [p.get("cafeine_mg") or 0 for p in ps]
    prix60 = [prix_pour_60g(p) for p in ps]
    fibres = [par_portion(p, "fibres_g") for p in ps]
    prot = [par_portion(p, "proteines_g") for p in ps]
    densite = [p.get("glucides_g") for p in ps]
    tol = [verdicts.get(p.get("id"), {}).get("libelle", "Jamais testé") if not p.get("generique") else "—"
           for p in ps]

    def lettre_ns(r):
        if r.get("lettre") is None:
            return "—"
        t = r["lettre"]
        if r.get("officiel") and r["officiel"] != t:
            t += f" (étiquette : {r['officiel']})"
        return t

    lignes = [
        ("Catégorie", [p.get("categorie") or "—" for p in ps]),
        ("Portion", [libelle_portion(p) for p in ps]),
        ("Glucides par portion", [_fr(v, 0, "g") for v in g]),
        ("Énergie par portion", [_fr(v, 0, "kcal") for v in kcal]),
        ("Glucides pour 100 g ou 100 ml", [_fr(v, 0, "g") for v in densite]),
        ("Sodium par portion", [_fr(v, 0, "mg") for v in na]),
        ("Caféine", [_fr(v, 0, "mg") if v >= 5 else "non" for v in caf]),
        ("Rapport glucose:fructose", [p.get("glucose_fructose") or "—" for p in ps]),
        ("Fibres par portion", [_fr(v, 1, "g") for v in fibres]),
        ("Protéines par portion", [_fr(v, 1, "g") for v in prot]),
        ("Prix par portion", [_fr(p.get("prix_portion"), 2, "€") for p in ps]),
        ("Prix pour 60 g de glucides (≈ 1 h)", [_fr(v, 2, "€") for v in prix60]),
        ("Ma tolérance", tol),
        ("Nutri-Score (au quotidien)", [lettre_ns(r) for r in ns]),
    ]
    noms = [p.get("nom") for p in ps]
    phrases = []

    def meilleur(valeurs, plus_grand=True):
        idx = [i for i, v in enumerate(valeurs) if v is not None]
        if len(idx) < 2:
            return None
        i = max(idx, key=lambda k: valeurs[k]) if plus_grand else min(idx, key=lambda k: valeurs[k])
        autres = [valeurs[k] for k in idx if k != i]
        return i, autres

    m = meilleur(g)
    if m and g[m[0]] - max(m[1]) >= 3:
        phrases.append(f"« {noms[m[0]]} » apporte le plus de glucides par portion ({_fr(g[m[0]], 0)} g) : "
                       "moins de prises pour le même apport.")
    m = meilleur(prix60, plus_grand=False)
    if m:
        ecart = (max(m[1]) / prix60[m[0]] - 1) * 100 if prix60[m[0]] else 0
        phrases.append(f"« {noms[m[0]]} » est le moins cher pour 60 g de glucides ({_fr(prix60[m[0]], 2)} €)"
                       + (f", jusqu'à {ecart:.0f} % moins cher que les autres." if ecart >= 10 else "."))
    elif sum(1 for v in prix60 if v is not None) < 2:
        phrases.append("Renseigne le prix par portion des produits pour comparer leur coût à l'heure de course.")
    m = meilleur(na)
    if m and na[m[0]] >= 100 and na[m[0]] - max(m[1]) >= 80:
        phrases.append(f"« {noms[m[0]]} » est le plus salé ({_fr(na[m[0]], 0)} mg de sodium) : utile par temps chaud.")
    for i, p in enumerate(ps):
        if caf[i] >= 20:
            phrases.append(f"« {noms[i]} » contient {caf[i]:.0f} mg de caféine : plutôt en seconde moitié de course "
                           "ou la nuit, après l'avoir testé. L'EFSA (Autorité européenne de sécurité des aliments) "
                           "situe la limite sans risque d'un adulte en bonne santé à 200 mg d'un coup et 400 mg sur la journée.")
        if (fibres[i] or 0) > 3:
            phrases.append(f"« {noms[i]} » a {_fr(fibres[i], 1)} g de fibres par portion : mieux en début d'effort "
                           "ou à allure tranquille.")
    for i, p in enumerate(ps):
        code = verdicts.get(p.get("id"), {}).get("code")
        if code == "eviter":
            phrases.append(f"Attention : « {noms[i]} » t'a déjà posé des problèmes digestifs.")
        elif code == "valide":
            phrases.append(f"« {noms[i]} » est validé par tes essais : c'est un choix sûr pour la course.")
    lettres = [r.get("lettre") for r in ns]
    if any(l in ("D", "E") for l in lettres if l):
        phrases.append("Nutri-Score : les produits d'effort sucrés sont classés D ou E, c'est normal. La lettre compte "
                       "pour ce que tu manges au quotidien (en-cas, récupération), pas pour un ravitaillement.")
    connus = [(i, l) for i, l in enumerate(lettres) if l]
    if len(connus) >= 2 and len({l for _, l in connus}) > 1 and min(l for _, l in connus) in ("A", "B"):
        i, l = min(connus, key=lambda x: x[1])
        phrases.append(f"Au quotidien, « {noms[i]} » est le meilleur choix nutritionnel (Nutri-Score {l}).")
    return {"colonnes": noms, "lignes": lignes, "nutriscores": lettres, "phrases": phrases}
