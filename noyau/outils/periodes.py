"""
Découpage du temps en points de courbe : par jour, par semaine ou par mois.

Sert aux courbes d'évolution (VMA, VO2max, efficacité, distance…) pour
que chacune puisse se lire jour par jour, semaine par semaine (lundi →
dimanche) ou mois par mois, avec la même règle de calcul à chaque point.
"""

from datetime import date, timedelta

PAS = ("jour", "semaine", "mois")
LIBELLE_PAS = {"jour": "Jour", "semaine": "Semaine", "mois": "Mois"}
NB_PAR_DEFAUT = {"jour": 90, "semaine": 52, "mois": 24}
# Choix de durée proposés dans les écrans, pour chaque pas : (libellé, nombre de points)
DUREES = {
    "jour": (("30 jours", 30), ("90 jours", 90), ("6 mois", 182)),
    "semaine": (("12 semaines", 12), ("26 semaines", 26), ("52 semaines", 52)),
    "mois": (("12 mois", 12), ("24 mois", 24)),
}


def libelle_duree(pas, nb):
    unite = {"jour": "jours", "semaine": "semaines", "mois": "mois"}[pas]
    return f"{nb} {unite}"


def periodes(fin, pas="mois", nb=None):
    """[(libellé, début, fin)] du plus ancien au plus récent ; `fin` (date) est
    le dernier jour pris en compte (la dernière période s'arrête à cette date).
    jour : « 05/11 » ; semaine : lundi « 03/11 » (lundi → dimanche) ; mois : « 11/26 »."""
    if pas not in PAS:
        raise ValueError(f"Pas inconnu : {pas}")
    nb = nb or NB_PAR_DEFAUT[pas]
    if isinstance(fin, str):
        fin = date.fromisoformat(fin[:10])
    res = []
    if pas == "jour":
        for i in range(nb - 1, -1, -1):
            j = fin - timedelta(days=i)
            res.append((j.strftime("%d/%m"), j, j))
    elif pas == "semaine":
        lundi = fin - timedelta(days=fin.weekday())
        for i in range(nb - 1, -1, -1):
            debut = lundi - timedelta(weeks=i)
            res.append((debut.strftime("%d/%m"), debut, min(debut + timedelta(days=6), fin)))
    else:
        for i in range(nb - 1, -1, -1):
            annee, mois = fin.year, fin.month - i
            while mois < 1:
                mois += 12
                annee -= 1
            premier = date(annee, mois, 1)
            dernier = (premier.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
            res.append((f"{mois:02d}/{str(annee)[2:]}", premier, min(dernier, fin)))
    return res


def remplir_trous(points):
    """Coupe le début sans valeur et reporte la dernière valeur connue dans les trous."""
    pts = list(points)
    while pts and pts[0][1] is None:
        pts.pop(0)
    dernier, rempli = None, []
    for l, v in pts:
        if v is None:
            v = dernier
        else:
            dernier = v
        rempli.append((l, v))
    return rempli
