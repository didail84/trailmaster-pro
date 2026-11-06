"""
Saison et catégories d'âge de la Fédération française d'athlétisme.

La saison va du 1er septembre au 31 août. La catégorie dépend seulement de
l'année de naissance : c'est l'âge atteint pendant l'année civile où la
saison se termine. Saison 2025-2026 : Seniors nés de 1992 à 2003, Espoirs
2004-2006, Juniors 2007-2008, Cadets 2009-2010, Minimes 2011-2012,
Benjamins 2013-2014, Poussins 2015-2016, Éveil athlétique 2017-2019, Baby
athlé 2020 et après, Masters M0 1987-1991 … M10 1941 et avant (tableau de
la ligue d'Île-de-France, saison 2025-2026).
"""

from datetime import date

MOIS_DEBUT_SAISON = 9

# (âge minimal atteint dans l'année de fin de saison, code, libellé, code U)
_CATEGORIES = (
    (0, "BB", "Baby athlé", "U7"),
    (7, "EA", "Éveil athlétique", "U10"),
    (10, "PO", "Poussins", "U12"),
    (12, "BE", "Benjamins", "U14"),
    (14, "MI", "Minimes", "U16"),
    (16, "CA", "Cadets", "U18"),
    (18, "JU", "Juniors", "U20"),
    (20, "ES", "Espoirs", "U23"),
    (23, "SE", "Seniors", "SE"),
) + tuple((35 + 5 * k, f"M{k}", f"Masters {k}", "MA") for k in range(11))
CODES = tuple(c for _a, c, _l, _u in _CATEGORIES)
LIBELLE = {c: l for _a, c, l, _u in _CATEGORIES}
ORDRE = {c: i for i, c in enumerate(CODES)}

# Types de licences FFA (circulaire financière 2025-2026) et catégories qui y ont droit
TYPES_LICENCE = (
    ("decouverte", "Athlé Découverte", ("U7", "U10", "U12")),
    ("competition", "Athlé Compétition", ("U14", "U16", "U18", "U20", "U23", "SE", "MA")),
    ("running", "Athlé Running", ("U18", "U20", "U23", "SE", "MA")),
    ("sante", "Athlé Santé", ("U18", "U20", "U23", "SE", "MA")),
    ("entreprise", "Athlé Entreprise", ("U18", "U20", "U23", "SE", "MA")),
    ("encadrement", "Athlé Encadrement", ("U16", "U18", "U20", "U23", "SE", "MA")),
    ("adherent", "Adhérent sans licence", None),
)
LIBELLE_LICENCE = {c: l for c, l, _ in TYPES_LICENCE}
_CATS_LICENCE = {c: cats for c, _l, cats in TYPES_LICENCE}


def saison_de(jour=None):
    """« 2026-2027 » pour un jour donné (date ou ISO) ; aujourd'hui par défaut."""
    j = jour or date.today()
    if isinstance(j, str):
        j = date.fromisoformat(j[:10])
    debut = j.year if j.month >= MOIS_DEBUT_SAISON else j.year - 1
    return f"{debut}-{debut + 1}"


def annees(saison):
    debut = int(str(saison)[:4])
    return debut, debut + 1


def saison_precedente(saison):
    d, _f = annees(saison)
    return f"{d - 1}-{d}"


def saison_suivante(saison):
    d, f = annees(saison)
    return f"{f}-{f + 1}"


def bornes_saison(saison):
    d, f = annees(saison)
    return date(d, MOIS_DEBUT_SAISON, 1), date(f, 8, 31)


def annee_naissance(date_naissance):
    if not date_naissance:
        return None
    try:
        return int(str(date_naissance)[:4])
    except ValueError:
        return None


def categorie(date_naissance, saison=None):
    """{code, libelle, u, age} de la catégorie FFA pour la saison, ou None si la date est inconnue."""
    an = annee_naissance(date_naissance)
    if an is None:
        return None
    _d, fin = annees(saison or saison_de())
    age = fin - an
    choix = _CATEGORIES[0]
    for c in _CATEGORIES:
        if age >= c[0]:
            choix = c
    return {"code": choix[1], "libelle": choix[2], "u": choix[3], "age": age}


def annees_de_la_categorie(code, saison=None):
    """(première, dernière) année de naissance d'une catégorie pour la saison (None = sans limite)."""
    _d, fin = annees(saison or saison_de())
    i = ORDRE[code]
    age_min = _CATEGORIES[i][0]
    age_max = _CATEGORIES[i + 1][0] - 1 if i + 1 < len(_CATEGORIES) else None
    return (fin - age_max if age_max is not None else None, fin - age_min if age_min else None)


def licence_possible(type_licence, date_naissance, saison=None):
    """None si le type de licence convient à l'âge, sinon un message."""
    cats = _CATS_LICENCE.get(type_licence)
    if not cats:
        return None
    c = categorie(date_naissance, saison)
    if c is None or c["u"] in cats:
        return None
    return f"{LIBELLE_LICENCE[type_licence]} n'est pas prévue pour la catégorie {c['libelle']}."
