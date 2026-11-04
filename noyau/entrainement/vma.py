"""
Estimation de la VMA (vitesse maximale aérobie) à partir des sorties
enregistrées, et suivi de l'évolution par circuit.

Méthode — pour chaque sortie Trail/Course d'au moins 3 km :
  1. Le dénivelé est converti en distance équivalente à plat :
     distance équivalente = km + D+ / 125  (125 m de D+ ≈ 1 km d'effort).
  2. On en déduit le VO2max de l'effort (formule de Daniels & Gilbert,
     la même que le reste du logiciel : interface/vo2max.py).
  3. La VMA est la vitesse à laquelle le coût en oxygène atteint ce
     VO2max (on résout la formule de Daniels pour la vitesse).

Une sortie tranquille donne une VMA trop basse (la formule suppose un
effort proche du maximum). La VMA du moment est donc la moyenne des
3 meilleures estimations des 90 derniers jours, pas la moyenne de toutes
les sorties. Les séances de fractionné/côtes prévues au planning ne sont
pas utilisées à part : si elles sont faites, elles apparaissent comme
sorties et tirent naturellement l'estimation vers le haut.

Le suivi par circuit regroupe les sorties qui portent le même nom
(« Saumane-de-Vaucluse Trail »...) et compare chrono, allure, vitesse,
distance et D+ dans le temps. Les noms génériques de l'application de
montre (« Morning Trail Run », « Course à pied le midi »...) ne sont pas
des circuits et sont ignorés.
"""

import math
import re
from datetime import date, timedelta
from statistics import mean, median

from data.database import connexion
from noyau.entrainement.vo2max import estimer_vo2max

FENETRE_JOURS = 90
NB_MEILLEURS = 3
DISTANCE_MIN_KM = 3.0
TYPES_COURSE = ("Trail", "Course")

_NOMS_GENERIQUES = re.compile(
    r"^(course à pied (le |dans |en )|morning |afternoon |lunch |evening |night )",
    re.IGNORECASE,
)


def vitesse_vma_depuis_vo2max(vo2max):
    """Vitesse (km/h) à laquelle le coût en oxygène de Daniels égale
    le VO2max donné."""
    a, b, c = 0.000104, 0.182258, -4.60 - vo2max
    delta = b * b - 4 * a * c
    if delta <= 0:
        return None
    v_m_min = (-b + math.sqrt(delta)) / (2 * a)
    return round(v_m_min * 0.06, 2)


def vma_depuis_effort(distance_km, denivele_m, duree_s):
    """VMA estimée (km/h) pour une sortie, ou None si inexploitable."""
    if not distance_km or distance_km < DISTANCE_MIN_KM or not duree_s or duree_s <= 0:
        return None
    denivele = min(denivele_m or 0, 60 * distance_km)  # coupe les D+ aberrants
    distance_eq = distance_km + denivele / 125
    allure_eq = duree_s / 60 / distance_eq
    if not 3.5 <= allure_eq <= 9:  # sous 3:30 /km : GPS ou durée erronés
        return None
    vo2 = estimer_vo2max(distance_eq, duree_s)
    if not vo2:
        return None
    return vitesse_vma_depuis_vo2max(vo2)


def allure_texte(vitesse_kmh):
    """Vitesse km/h -> « 4:52 /km »."""
    if not vitesse_kmh or vitesse_kmh <= 0:
        return "—"
    sec = int(round(3600 / vitesse_kmh))
    return f"{sec // 60}:{sec % 60:02d} /km"


def duree_texte(duree_s):
    if duree_s is None:
        return "—"
    duree_s = int(round(duree_s))
    h, reste = divmod(duree_s, 3600)
    m, s = divmod(reste, 60)
    return f"{h}h{m:02d}'{s:02d}" if h else f"{m}'{s:02d}"


def _efforts_course(athlete_id):
    conn = connexion()
    cur = conn.cursor()
    cur.execute(
        "SELECT date, nom, type, distance, denivele, duree FROM activites "
        "WHERE athlete_id=? AND type IN ('Trail','Course') AND distance >= ? AND duree > 0 "
        "ORDER BY date",
        (athlete_id, DISTANCE_MIN_KM),
    )
    lignes = cur.fetchall()
    conn.close()
    efforts = []
    for d, nom, t, dist, dp, duree in lignes:
        vma = vma_depuis_effort(dist, dp, duree)
        if vma:
            efforts.append({"date": str(d)[:10], "nom": nom or "", "type": t,
                            "km": dist, "dp": dp or 0, "duree": duree, "vma": vma})
    return efforts


def _vma_fenetre(efforts, fin_iso, jours=FENETRE_JOURS):
    debut = (date.fromisoformat(fin_iso) - timedelta(days=jours)).isoformat()
    valeurs = sorted(
        (e["vma"] for e in efforts if debut <= e["date"] <= fin_iso), reverse=True
    )
    if not valeurs:
        return None
    return round(mean(valeurs[:NB_MEILLEURS]), 1)


def calculer_vma(athlete_id):
    """Retourne un dict :
    - actuelle : VMA estimée à la date de la dernière sortie (km/h)
    - date_reference : cette date (ISO)
    - meilleurs : les NB_MEILLEURS meilleurs efforts de la fenêtre
    - record : meilleure VMA (moyenne des 3 meilleures) sur une fenêtre
      de 90 jours, toutes périodes confondues, avec sa date
    - serie : [(label_mois, vma_ou_None)] sur 24 mois
    - nb_efforts : nombre de sorties exploitables
    ou None s'il n'y a aucune sortie exploitable."""

    efforts = _efforts_course(athlete_id)
    if not efforts:
        return None

    derniere = efforts[-1]["date"]
    ref = derniere
    actuelle = _vma_fenetre(efforts, ref)

    debut = (date.fromisoformat(ref) - timedelta(days=FENETRE_JOURS)).isoformat()
    meilleurs = sorted(
        (e for e in efforts if debut <= e["date"] <= ref), key=lambda e: -e["vma"]
    )[:NB_MEILLEURS]

    # Record : on teste chaque fin de mois.
    record = None
    jour = date.fromisoformat(efforts[0]["date"]).replace(day=1)
    fin = date.fromisoformat(ref)
    while jour <= fin:
        suivant = (jour.replace(day=28) + timedelta(days=4)).replace(day=1)
        fin_mois = min(suivant - timedelta(days=1), fin).isoformat()
        v = _vma_fenetre(efforts, fin_mois)
        if v is not None and (record is None or v > record[0]):
            record = (v, fin_mois)
        jour = suivant

    # Série mensuelle sur 24 mois
    serie = []
    fin_dt = date.fromisoformat(ref)
    for i in range(23, -1, -1):
        annee = fin_dt.year
        mois = fin_dt.month - i
        while mois < 1:
            mois += 12
            annee -= 1
        premier = date(annee, mois, 1)
        dernier = (premier.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
        fin_mois = min(dernier, fin_dt).isoformat()
        serie.append((f"{mois:02d}/{str(annee)[2:]}", _vma_fenetre(efforts, fin_mois)))
    while serie and serie[0][1] is None:
        serie.pop(0)
    derniere_valeur = None
    remplie = []
    for label, v in serie:
        if v is None:
            v = derniere_valeur
        else:
            derniere_valeur = v
        remplie.append((label, v))

    return {
        "actuelle": actuelle,
        "date_reference": ref,
        "meilleurs": meilleurs,
        "record": record,
        "serie": remplie,
        "nb_efforts": len(efforts),
    }


def allures_reference(vma_kmh):
    """Allures conseillées à partir de la VMA : [(libellé, % VMA, allure)]."""
    return [
        (nom, pct, allure_texte(vma_kmh * pct / 100))
        for nom, pct in (
            ("Endurance fondamentale", 65),
            ("Allure marathon", 75),
            ("Seuil", 85),
            ("Allure 10 km", 90),
            ("VMA", 100),
        )
    ]


def _regression_pente(points):
    """Pente (unité/an) d'une régression linéaire sur [(jours, valeur)]."""
    n = len(points)
    if n < 3:
        return None
    mx = sum(p[0] for p in points) / n
    my = sum(p[1] for p in points) / n
    den = sum((p[0] - mx) ** 2 for p in points)
    if den == 0:
        return None
    return sum((p[0] - mx) * (p[1] - my) for p in points) / den * 365.25


def lister_circuits(athlete_id, nb_min=3):
    """Circuits (sorties de même nom, au moins nb_min fois), triés par
    nombre de passages. Seules les sorties dont la distance est à ±15 %
    de la distance médiane du circuit sont comparées (les parcours
    raccourcis ou prolongés ne faussent pas le chrono)."""

    conn = connexion()
    cur = conn.cursor()
    cur.execute(
        "SELECT date, nom, distance, denivele, duree, frequence_cardiaque_moyenne "
        "FROM activites WHERE athlete_id=? AND type IN ('Trail','Course') "
        "AND distance >= ? AND duree > 0 ORDER BY date",
        (athlete_id, DISTANCE_MIN_KM),
    )
    lignes = cur.fetchall()
    conn.close()

    groupes = {}
    for d, nom, dist, dp, duree, fc in lignes:
        nom = (nom or "").strip()
        if not nom or _NOMS_GENERIQUES.match(nom):
            continue
        groupes.setdefault(nom, []).append(
            {"date": str(d)[:10], "km": dist, "dp": dp or 0, "duree": duree, "fc": fc or 0}
        )

    circuits = []
    for nom, passages in groupes.items():
        med = median(p["km"] for p in passages)
        passages = [p for p in passages if 0.85 * med <= p["km"] <= 1.15 * med]
        if len(passages) < nb_min:
            continue
        for p in passages:
            p["allure_min_km"] = p["duree"] / 60 / p["km"]
            p["vitesse"] = p["km"] / (p["duree"] / 3600)
            p["vma"] = vma_depuis_effort(p["km"], p["dp"], p["duree"])

        chronos = [p["duree"] for p in passages]
        recents = chronos[-3:]
        avant = chronos[-6:-3]
        evol_recente = None
        if len(avant) == 3:
            evol_recente = (mean(recents) - mean(avant)) / mean(avant) * 100
        evol_totale = None
        if len(passages) >= 6:
            evol_totale = (mean(chronos[-3:]) - mean(chronos[:3])) / mean(chronos[:3]) * 100

        base = date.fromisoformat(passages[0]["date"])
        pente = _regression_pente(
            [((date.fromisoformat(p["date"]) - base).days, p["allure_min_km"]) for p in passages]
        )

        circuits.append({
            "nom": nom,
            "passages": passages,
            "nb": len(passages),
            "km": mean(p["km"] for p in passages),
            "dp": mean(p["dp"] for p in passages),
            "chrono_moyen": mean(chronos),
            "chrono_meilleur": min(chronos),
            "chrono_dernier": chronos[-1],
            "allure_moyenne": mean(p["allure_min_km"] for p in passages),
            "vitesse_moyenne": mean(p["vitesse"] for p in passages),
            "evol_recente_pct": evol_recente,   # < 0 : plus rapide
            "evol_totale_pct": evol_totale,
            "pente_allure_an": pente,            # min/km par an, < 0 : plus rapide
            "premiere": passages[0]["date"],
            "derniere": passages[-1]["date"],
        })

    circuits.sort(key=lambda c: (-c["nb"], c["nom"]))
    return circuits


def texte_evolution(pct):
    if pct is None:
        return "—"
    if abs(pct) < 1:
        return "= stable"
    return f"{'▼' if pct < 0 else '▲'} {abs(pct):.1f}".replace(".", ",") + f" % {'plus rapide' if pct < 0 else 'plus lent'}"
