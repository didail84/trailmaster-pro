"""
Courbes des estimations VMA / VO2max / efficacité cardiaque — « estimation basse ».

Ces chiffres sont calculés sur des sorties réelles, presque jamais des efforts
maximaux : ils SOUS-ESTIMENT donc la valeur physiologique vraie (la formule de
Daniels suppose un effort proche du maximum). Seule la tendance est fiable :
une courbe qui monte = tu progresses, quel que soit le niveau absolu.
"""

from datetime import date, timedelta
from statistics import mean, median

from data.database import connexion
from noyau.entrainement.vma import _efforts_course, FENETRE_JOURS, NB_MEILLEURS
from noyau.entrainement.vo2max import estimer_vo2max

MENTION = "estimation basse"
NOTE = (
    "Estimation basse : calculée sur tes sorties réelles (rarement des efforts maximaux), "
    "donc inférieure à ta vraie valeur. Seule la tendance (hausse / baisse) est fiable, "
    "pas le niveau absolu."
)
FENETRE_EFFICACITE_JOURS = 60
DISTANCE_MIN_EFFICACITE_KM = 5.0


def _fins_de_mois(derniere, nb_mois):
    """[(label MM/AA, date ISO de fin)] pour les nb_mois derniers mois."""
    fin_dt = date.fromisoformat(derniere)
    res = []
    for i in range(nb_mois - 1, -1, -1):
        annee, mois = fin_dt.year, fin_dt.month - i
        while mois < 1:
            mois += 12
            annee -= 1
        premier = date(annee, mois, 1)
        dernier = (premier.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
        res.append((f"{mois:02d}/{str(annee)[2:]}", min(dernier, fin_dt).isoformat()))
    return res


def _vo2_efforts(efforts):
    """Ajoute à chaque effort son VO2max estimé (distance à plat équivalente)."""
    sortie = []
    for e in efforts:
        dp = min(e["dp"] or 0, 60 * e["km"])
        vo2 = estimer_vo2max(e["km"] + dp / 125, e["duree"])
        if vo2:
            sortie.append({"date": e["date"], "vo2": vo2})
    return sortie


def _moy_meilleurs(valeurs_datees, fin_iso, cle, jours=FENETRE_JOURS):
    debut = (date.fromisoformat(fin_iso) - timedelta(days=jours)).isoformat()
    v = sorted((x[cle] for x in valeurs_datees if debut <= x["date"] <= fin_iso), reverse=True)
    return round(mean(v[:NB_MEILLEURS]), 1) if v else None


def _efficacites(athlete_id):
    conn = connexion()
    cur = conn.cursor()
    cur.execute(
        "SELECT date, distance, duree, denivele, frequence_cardiaque_moyenne FROM activites "
        "WHERE athlete_id=? AND type IN ('Trail','Course') AND distance>=? AND duree>0 "
        "AND frequence_cardiaque_moyenne>0 ORDER BY date",
        (athlete_id, DISTANCE_MIN_EFFICACITE_KM),
    )
    lignes = cur.fetchall()
    conn.close()
    res = []
    for d, di, du, de, fc in lignes:
        km_effort = di + (de or 0) / 100.0
        res.append({"date": str(d)[:10], "ef": km_effort / (du / 3600.0) / fc * 100.0})
    return res


def serie_estimations(athlete_id, nb_mois=24):
    """{"vma": [(label, v|None)], "vo2max": [...], "efficacite": [...]} (points mensuels,
    dernière valeur reportée en cas de trou, début coupé au premier point connu).
    Retourne None s'il n'y a aucune sortie exploitable."""
    efforts = _efforts_course(athlete_id)
    if not efforts:
        return None
    vo2 = _vo2_efforts(efforts)
    effs = _efficacites(athlete_id)
    mois = _fins_de_mois(efforts[-1]["date"], nb_mois)

    def construire(calc):
        pts = [(l, calc(fin)) for l, fin in mois]
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

    def ef(fin):
        debut = (date.fromisoformat(fin) - timedelta(days=FENETRE_EFFICACITE_JOURS)).isoformat()
        v = [x["ef"] for x in effs if debut <= x["date"] <= fin]
        return round(median(v), 2) if len(v) >= 2 else None

    return {
        "vma": construire(lambda f: _moy_meilleurs(efforts, f, "vma")),
        "vo2max": construire(lambda f: _moy_meilleurs(vo2, f, "vo2")),
        "efficacite": construire(ef),
    }


def evolution_pct(serie):
    """Variation en % entre le premier et le dernier point connu, ou None."""
    v = [x[1] for x in serie if x[1] is not None]
    if len(v) < 2 or not v[0]:
        return None
    return round((v[-1] / v[0] - 1) * 100, 1)


def definitions_courbes(series):
    """Séries prêtes pour CourbeMultiLignes, une par grandeur (échelles différentes
    → un graphique chacune, jamais deux axes) : [(titre, [serie_courbe])]."""
    modeles = [
        ("vma", "VMA", "km/h", "#42A5F5"),
        ("vo2max", "VO₂max", "ml/kg/min", "#66BB6A"),
        ("efficacite", "Indice d'efficacité cardiaque", "", "#F9A825"),
    ]
    sortie = []
    for cle, nom, unite, couleur in modeles:
        pts = series.get(cle) or []
        evo = evolution_pct(pts)
        titre = f"{nom} — {MENTION}"
        if evo is not None:
            titre += f" · {evo:+.1f} % sur la période"
        u = f" ({unite})" if unite else ""
        sortie.append((titre, [{"nom": f"{nom}{u} — {MENTION}", "couleur": couleur,
                                "valeurs": list(pts)}]))
    return sortie
