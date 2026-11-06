"""
Catalogue des équipements de trail qu'un règlement de course peut exiger,
et lecture automatique d'une liste de matériel collée depuis le règlement.

Chaque équipement a un code stable (enregistré dans la base), un nom, une
famille, les mots qui le font reconnaître dans un règlement, et au plus une
caractéristique chiffrée qu'un règlement peut imposer (volume d'eau,
colonne d'eau d'une veste, lumens, calories…).

Les exemples chiffrés des conseils reprennent des exigences courantes des
grands ultras (par exemple la liste des courses UTMB World Series :
gobelet de 15 cl, couverture de survie de 1,40 × 2 m, bande élastique
adhésive de 100 × 6 cm, veste à 10 000 mm de colonne d'eau, 800 kcal) :
chaque course fixe les siennes, le règlement officiel fait foi.
"""

import re
import unicodedata

FAMILLES = ("Sécurité", "Hydratation", "Lumière", "Vêtements", "Nutrition", "Soins", "Divers")

# caractéristique : (clé, libellé, unité, cumul) — cumul=True : les quantités s'additionnent (eau)
CARACTERISTIQUES = {
    "volume_l": ("Contenance", "L", True),
    "volume_cl": ("Contenance", "cl", False),
    "colonne_eau_mm": ("Colonne d'eau", "mm", False),
    "lumens": ("Puissance", "lumens", False),
    "kcal": ("Énergie", "kcal", True),
    "poids_couche_g": ("Poids du vêtement", "g", False),
}

# code: (nom, famille, mots-clés (sans accents, minuscules), caractéristique ou None, conseil)
_BRUT = {
    "telephone": ("Téléphone portable", "Sécurité",
                  ("telephone", "portable", "smartphone", "mobile", "gsm"), None,
                  "Chargé, numéros de l'organisation enregistrés, numéro non masqué."),
    "batterie_externe": ("Batterie externe", "Lumière", ("batterie externe", "power bank", "powerbank"), None,
                         "Chargée la veille, avec son câble."),
    "gobelet": ("Gobelet personnel", "Hydratation", ("gobelet", "tasse", "ecocup", "eco-cup", "eco cup"), "volume_cl",
                "Souvent 15 cl minimum ; une flasque à bouchon ne compte pas toujours."),
    "reserve_eau": ("Réserve d'eau", "Hydratation",
                    ("reserve d'eau", "reserve en eau", "eau", "flasque", "bidon", "poche a eau", "gourde", "hydratation",
                     "boisson"), "volume_l",
                    "Additionne tes flasques et ta poche à eau."),
    "couverture_survie": ("Couverture de survie", "Sécurité", ("couverture de survie", "couverture survie",
                                                               "sac de survie", "couverture"), None,
                          "Souvent 1,40 m × 2 m minimum, ou sac de survie."),
    "sifflet": ("Sifflet", "Sécurité", ("sifflet",), None, "Beaucoup de sacs de trail en ont un sur la sangle."),
    "frontale": ("Lampe frontale", "Lumière", ("lampe frontale", "frontale", "lampe", "eclairage"), "lumens",
                 "200 lumens ou plus conseillés pour la lampe principale."),
    "frontale_secours": ("Seconde lampe", "Lumière",
                         ("deux lampes", "2 lampes", "deuxieme lampe", "seconde lampe", "2e lampe", "lampe de secours",
                          "lampe de rechange", "deux frontales", "2 frontales"), None,
                         "Une petite frontale légère suffit souvent."),
    "piles": ("Piles ou batterie de rechange", "Lumière", ("piles", "pile de rechange", "batterie de rechange",
                                                           "accus", "batteries de rechange"), None,
              "Pour la frontale principale."),
    "veste_impermeable": ("Veste imperméable à capuche", "Vêtements",
                          ("veste impermeable", "veste de pluie", "veste", "impermeable", "gore-tex", "goretex",
                           "coupe-pluie"), "colonne_eau_mm",
                          "Coutures étanches et capuche ; souvent 10 000 mm de colonne d'eau minimum sur les ultras."),
    "coupe_vent": ("Coupe-vent", "Vêtements", ("coupe-vent", "coupe vent", "veste dwr", "deperlante"), None,
                   "Veste légère déperlante."),
    "surpantalon": ("Surpantalon imperméable", "Vêtements", ("surpantalon", "sur-pantalon", "pantalon impermeable"),
                    None, "Exigé sur certaines courses par mauvais temps."),
    "pantalon_long": ("Pantalon ou collant long", "Vêtements",
                      ("pantalon", "collant", "legging", "jambieres", "jambes couvertes", "corsaire", "jambes"), None,
                      "Les jambes doivent souvent être entièrement couvertes (collant + chaussettes hautes)."),
    "couche_chaude": ("Couche chaude à manches longues", "Vêtements",
                      ("deuxieme couche", "seconde couche", "2e couche", "couche chaude", "manches longues",
                       "vetement chaud", "maillot chaud", "polaire", "doudoune", "troisieme couche", "sous-vetement chaud"),
                      "poids_couche_g",
                      "Hors coton ; souvent 180 g minimum (ou 110 g avec un coupe-vent)."),
    "bonnet": ("Bonnet ou tour de cou", "Vêtements", ("bonnet", "buff", "tour de cou", "tubulaire", "bandeau",
                                                       "protection de la tete", "couvre-chef chaud"), None,
               "Couvrant la tête et les oreilles."),
    "casquette": ("Casquette ou bandana", "Vêtements", ("casquette", "bandana", "chapeau", "saharien", "visiere"), None,
                  "Pour le soleil ; un bonnet saharien couvre aussi la nuque."),
    "gants": ("Gants", "Vêtements", ("gants", "gant"), None, "Doigts longs, chauds."),
    "gants_impermeables": ("Surgants imperméables", "Vêtements", ("surgants", "sur-gants", "gants impermeables"), None,
                           "Par temps froid et humide."),
    "lunettes": ("Lunettes de soleil", "Vêtements", ("lunettes",), None, "Indispensables sur neige ou en altitude."),
    "creme_solaire": ("Crème solaire", "Soins", ("creme solaire", "protection solaire", "ecran solaire"), None,
                      "Indice 50 conseillé."),
    "reserve_alimentaire": ("Réserve alimentaire", "Nutrition",
                            ("reserve alimentaire", "nourriture", "alimentaire", "barres", "gels", "ravitaillement personnel",
                             "kcal", "calories"), "kcal",
                            "Souvent 800 kcal conseillées (2 gels + 2 barres, par exemple)."),
    "bande_elastique": ("Bande élastique adhésive", "Soins", ("bande elastique", "bande adhesive", "bandage", "strapping",
                                                             "elastoplast"), None,
                        "Souvent 100 × 6 cm minimum, pour un strapping."),
    "trousse_secours": ("Trousse de premiers secours", "Soins", ("trousse", "premiers secours", "pansements",
                                                                 "compresses", "pharmacie"), None,
                        "Pansements, compresses, désinfectant."),
    "piece_identite": ("Pièce d'identité", "Divers", ("piece d'identite", "carte d'identite", "passeport", "identite"),
                       None, "Ou permis de conduire."),
    "argent": ("Argent ou carte bancaire", "Divers", ("argent", "monnaie", "euros", "carte bancaire"), None,
               "Pour un retour en navette ou un abandon."),
    "batons": ("Bâtons", "Divers", ("batons", "baton"), None, "À garder jusqu'à l'arrivée si tu pars avec."),
    "crampons": ("Chaînes ou crampons légers", "Divers", ("crampons", "chaines", "microspikes", "chaussures a neige"),
                 None, "Si neige ou verglas."),
    "reflechissant": ("Élément réfléchissant", "Sécurité", ("reflechissant", "gilet jaune", "haute visibilite", "fluo",
                                                            "led arriere", "lumiere rouge"), None,
                      "Gilet, brassard ou bande d'environ 5 cm, pour les portions de route de nuit."),
    "sac": ("Sac ou ceinture de trail", "Divers", ("sac a dos", "sac de trail", "sac", "ceinture porte"), None,
            "Pour porter tout le matériel obligatoire du départ à l'arrivée."),
    "gps_trace": ("Montre ou téléphone avec la trace", "Divers", ("trace gpx", "trace gps", "gps", "carte", "roadbook",
                                                                   "topo"), None, "Trace chargée avant le départ."),
    "dossard": ("Dossard et porte-dossard", "Divers", ("dossard", "porte-dossard"), None, "Visible devant, en entier."),
}
EQUIPEMENTS = {code: {"code": code, "nom": v[0], "famille": v[1], "mots": v[2], "carac": v[3], "conseil": v[4]}
               for code, v in _BRUT.items()}
NIVEAUX = (("obligatoire", "Obligatoire"), ("meteo", "Selon la météo"), ("conseille", "Conseillé"))
LIBELLE_NIVEAU = dict(NIVEAUX)


def sans_accents(texte):
    t = unicodedata.normalize("NFD", (texte or "").lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return t.replace("’", "'").replace("œ", "oe")


# Mots-clés triés du plus long au plus court : « couverture de survie » passe avant « couverture »,
# « veste impermeable » avant « veste », « deux lampes » avant « lampe ».
_MOTS = sorted(((m, code) for code, e in EQUIPEMENTS.items() for m in e["mots"]), key=lambda x: -len(x[0]))
# un mot court ne doit pas être reconnu au milieu d'un autre (« eau » dans « bateau », « sac » dans « sachet »)
def _motif(mot):
    # chaque mot accepte son pluriel : « lampes frontales », « gants », « bâtons »
    parties = [re.escape(x) + r"(?:s|x)?" for x in mot.split(" ")]
    return re.compile(r"(?<![a-z])" + r" ".join(parties) + r"(?![a-z])")


_MOTIFS = [(_motif(m), code) for m, code in _MOTS]
# équipements qui accompagnent souvent un autre sur la même ligne (« lampe frontale + piles »,
# « trousse de secours avec bande élastique ») : ils donnent une ligne à part
COMPAGNONS = {"piles", "frontale_secours", "batterie_externe", "sifflet", "couverture_survie", "bande_elastique"}
_DEUX_LAMPES = re.compile(r"(deux|2)\s+(lampes|frontales)")


def codes_dans(texte):
    """Tous les équipements reconnus dans `texte`, dans l'ordre où ils apparaissent ; un passage du texte
    ne compte qu'une fois, pour son mot-clé le plus long."""
    t = sans_accents(texte)
    pris, trouves = [], []
    for motif, code in _MOTIFS:          # du plus long au plus court
        for m in motif.finditer(t):
            if any(m.start() < f and m.end() > d for d, f in pris):
                continue
            pris.append((m.start(), m.end()))
            trouves.append((m.start(), code))
    ordre = []
    for _pos, code in sorted(trouves):
        if code not in ordre:
            ordre.append(code)
    if _DEUX_LAMPES.search(t):              # « deux lampes frontales » = frontale + seconde lampe
        if "frontale" not in ordre:
            ordre.insert(ordre.index("frontale_secours") if "frontale_secours" in ordre else 0, "frontale")
        if "frontale_secours" not in ordre:
            ordre.insert(ordre.index("frontale") + 1, "frontale_secours")
    return ordre


def reconnaitre(texte):
    """Code de l'équipement principal décrit par `texte` (ou None)."""
    codes = codes_dans(texte)
    return codes[0] if codes else None


_NOMBRES = {"un": 1, "une": 1, "deux": 2, "trois": 3, "quatre": 4}


def _nombre(t):
    return float(t.replace(" ", "").replace(" ", "").replace(",", "."))


def valeur_chiffree(texte, carac):
    """Lit la valeur minimale d'une caractéristique dans `texte` (ex. « 1,5 L » → 1.5)."""
    t = sans_accents(texte).replace(" ", " ")
    n = r"(\d+(?:[  ]\d{3})*(?:[.,]\d+)?)"
    if carac == "volume_l":
        m = re.search(n + r"\s*(l|litres?|cl|ml)\b", t)
        if m:
            v = _nombre(m.group(1))
            return v / 100 if m.group(2) == "cl" else v / 1000 if m.group(2) == "ml" else v
    if carac == "volume_cl":
        m = re.search(n + r"\s*(cl|ml|l)\b", t)
        if m:
            v = _nombre(m.group(1))
            return v / 10 if m.group(2) == "ml" else v * 100 if m.group(2) == "l" else v
    if carac == "colonne_eau_mm":
        m = re.search(n + r"\s*(mm|schmerber)", t)
        if m:
            return _nombre(m.group(1))
    if carac == "lumens":
        m = re.search(n + r"\s*(lumens?|lm)\b", t)
        if m:
            return _nombre(m.group(1))
    if carac == "kcal":
        m = re.search(n + r"\s*(kcal|calories|kilocalories)", t)
        if m:
            return _nombre(m.group(1))
    if carac == "poids_couche_g":
        m = re.search(n + r"\s*(g|grammes)\b", t)
        if m:
            return _nombre(m.group(1))
    return None


def quantite(texte, code):
    t = sans_accents(texte)
    if code in ("frontale", "frontale_secours") and _DEUX_LAMPES.search(t):
        return 1          # deux lampes = une « frontale » + une « seconde lampe »
    m = re.match(r"\s*(\d+|un|une|deux|trois|quatre)\s+(?!\s*(l|litres?|cl|ml|mm|m|cm|g|kg|kcal|lumens?|x)\b)", t)
    if m:
        v = m.group(1)
        return int(v) if v.isdigit() else _NOMBRES[v]
    return 1


def _niveau_de_titre(t):
    if re.search(r"conseill|recommand|facultati|optionn", t):
        return "conseille"
    if re.search(r"meteo|temps (froid|chaud)|grand froid|forte chaleur|selon les conditions|kit (chaud|froid)", t):
        return "meteo"
    if re.search(r"obligatoire|exige|imperati", t):
        return "obligatoire"
    return None


def analyser_reglement(texte):
    """Découpe une liste de matériel collée depuis un règlement en lignes reconnues.
    Renvoie [{libelle, equipement (code|None), niveau, quantite, valeur_min, precision}].
    Une ligne qui annonce une rubrique (« Matériel conseillé : ») change le niveau des suivantes.
    Les doublons d'un même équipement au même niveau sont fusionnés (la valeur la plus exigeante est gardée)."""
    niveau = "obligatoire"
    res = []
    # une puce ou un point-virgule séparent aussi des éléments écrits sur une seule ligne
    morceaux = []
    for ligne in (texte or "").replace("\r", "\n").split("\n"):
        morceaux += [m for m in re.split(r"\s*(?:;|•|·|▪|◦|•| - )\s*", ligne)]
    for brut in morceaux:
        libelle = re.sub(r"^\s*(?:[-–—*>]+|\d+[.)](?!\d))?\s*", "", brut).strip(" :.,\t")
        if not libelle:
            continue
        libelle = libelle[0].upper() + libelle[1:]
        t = sans_accents(libelle)
        titre = _niveau_de_titre(t)
        code = reconnaitre(libelle)
        est_titre = titre is not None and (libelle.endswith(":") or brut.rstrip().endswith(":") or len(t) < 40
                                           and not code)
        if est_titre and (not code or brut.rstrip().endswith(":")):
            niveau = titre
            continue
        niv = niveau
        if re.search(r"\b(si|en cas de|par temps)\b", t) and niv == "obligatoire":
            niv = "meteo"
        codes = codes_dans(libelle)
        principaux = [c for c in codes if c not in COMPAGNONS] or codes[:1]
        lignes = ([principaux[0]] if principaux else [None]) + [c for c in codes if c in COMPAGNONS
                                                                and c not in principaux[:1]]
        for k, c in enumerate(lignes):
            carac = EQUIPEMENTS[c]["carac"] if c else None
            res.append({"libelle": libelle[:160] if k == 0 else EQUIPEMENTS[c]["nom"],
                        "equipement": c, "niveau": niv, "quantite": quantite(libelle, c) if k == 0 else 1,
                        "valeur_min": valeur_chiffree(libelle, carac) if carac else None,
                        "precision": "" if k == 0 else f"D'après : « {libelle[:200]} »"})
    fusion, ordre = {}, []
    for it in res:
        cle = (it["equipement"], it["niveau"]) if it["equipement"] else (it["libelle"].lower(), it["niveau"])
        if cle in fusion:
            f = fusion[cle]
            f["quantite"] = max(f["quantite"], it["quantite"])
            if it["valeur_min"] is not None:
                f["valeur_min"] = max(f["valeur_min"] or 0, it["valeur_min"])
            if it["libelle"] not in f["libelle"]:
                f["libelle"] = (f["libelle"] + " ; " + it["libelle"])[:240]
        else:
            fusion[cle] = dict(it)
            ordre.append(cle)
    # un même équipement à la fois obligatoire et conseillé : on garde l'obligatoire
    obligatoires = {c for (c, n) in fusion if n == "obligatoire" and c in EQUIPEMENTS}
    # (« selon la météo » reste : c'est souvent une exigence plus forte, comme 2 L d'eau par temps chaud)
    return [fusion[c] for c in ordre if not (c[0] in obligatoires and c[1] == "conseille")]


def repere_standard(distance_km, denivele_m=0, nocturne=False, altitude=False, saison=None):
    """La liste repère de reference_materiel_course, reconnue équipement par équipement."""
    from noyau.course.reference_materiel_course import calculer_materiel
    r = calculer_materiel(distance_km, denivele_m, nocturne, altitude, saison)
    items = []
    for niveau, cle in (("obligatoire", "obligatoire"), ("conseille", "conseille")):
        for nom, raison in r[cle]:
            codes = codes_dans(nom) or [None]
            if "frontale_secours" in codes:          # « Deuxième lampe frontale (ou piles…) » : une seule ligne
                codes = ["frontale_secours"]
            for k, code in enumerate(codes):
                carac = EQUIPEMENTS[code]["carac"] if code else None
                items.append({"libelle": nom if k == 0 else EQUIPEMENTS[code]["nom"], "equipement": code,
                              "niveau": niveau, "quantite": 1,
                              "valeur_min": valeur_chiffree(nom, carac) if carac else None,
                              "precision": raison})
    # « Deuxième réserve d'eau » / paliers d'eau : une seule ligne, la plus exigeante
    fusion, ordre = {}, []
    for it in items:
        cle = (it["equipement"] or it["libelle"], it["niveau"])
        if cle in fusion:
            if it["valeur_min"]:
                fusion[cle]["valeur_min"] = max(fusion[cle]["valeur_min"] or 0, it["valeur_min"])
            continue
        fusion[cle] = it
        ordre.append(cle)
    oblig = {c for c, n in fusion if n == "obligatoire"}
    return [fusion[c] for c in ordre if not (c[1] == "conseille" and c[0] in oblig)]


def libelle_valeur(code, valeur):
    if valeur is None or not code or not EQUIPEMENTS[code]["carac"]:
        return ""
    _lib, unite, _c = CARACTERISTIQUES[EQUIPEMENTS[code]["carac"]]
    t = f"{valeur:,.2f}".rstrip("0").rstrip(".").replace(",", " ").replace(".", ",")
    return f"{t} {unite}"
