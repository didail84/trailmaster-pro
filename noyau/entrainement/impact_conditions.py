"""
Impact des conditions sur ta performance (v104) : à partir de tes propres sorties,
mesure comment l'efficacité (indice km-effort/h ÷ FC) varie avec la température et
le sommeil de la nuit, et résume la répartition d'intensité (polarisation).

Corrélation ≠ causalité : peu de sorties par classe = tendance seulement ; le
tableau affiche toujours le nombre de sorties et masque les classes de moins de 3.
"""

import statistics
from datetime import date, timedelta

import noyau.entrainement.metriques as met
from data.database import connexion

MIN_PAR_CLASSE = 3
CLASSES_TEMP = [("< 10 °C", -99, 10), ("10–18 °C", 10, 18), ("18–25 °C", 18, 25), ("≥ 25 °C", 25, 99)]
CLASSES_SOMMEIL = [("< 6 h", 0, 6), ("6–7 h", 6, 7), ("7–8 h", 7, 8), ("≥ 8 h", 8, 99)]


def _indice(dist, duree, dp, fc):
    from noyau.ia.analyse_technique import _indice_efficacite
    return _indice_efficacite(dist, duree, dp, fc)


def _sorties_efficacite(athlete_id, jours=365):
    debut = date.today() - timedelta(days=jours)
    conn = connexion()
    cur = conn.cursor()
    cur.execute("SELECT activite_id, temperature FROM meteo_sorties WHERE athlete_id=?", (athlete_id,))
    meteo = dict(cur.fetchall())
    conn.close()
    res = []
    for a in met.activites_periode(athlete_id, debut, None, types=("Trail", "Course")):
        if a["distance"] < 5 or not a["fc_moy"] or a["duree"] <= 0:
            continue
        ind = _indice(a["distance"], a["duree"], a["denivele"], a["fc_moy"])
        if not ind:
            continue
        temp = a["temperature"] if a["temperature"] is not None else meteo.get(a["id"])
        res.append({"jour": a["jour"], "indice": ind, "temperature": temp})
    return res


def _par_classe(valeurs, classes, reference):
    """valeurs : [(x, indice)] -> lignes {classe, n, indice, ecart_pct}."""
    lignes = []
    for nom, bas, haut in classes:
        v = [i for x, i in valeurs if x is not None and bas <= x < haut]
        if len(v) >= MIN_PAR_CLASSE:
            m = statistics.median(v)
            lignes.append({"classe": nom, "n": len(v), "indice": round(m, 2),
                           "ecart_pct": round((m / reference - 1) * 100, 1) if reference else None})
        else:
            lignes.append({"classe": nom, "n": len(v), "indice": None, "ecart_pct": None})
    return lignes


def impact_temperature(athlete_id, jours=365):
    sorties = _sorties_efficacite(athlete_id, jours)
    if len(sorties) < 6:
        return None
    ref = statistics.median(s["indice"] for s in sorties)
    return {"reference": round(ref, 2), "nb": len(sorties),
            "lignes": _par_classe([(s["temperature"], s["indice"]) for s in sorties], CLASSES_TEMP, ref)}


def impact_sommeil(athlete_id, jours=365):
    sorties = _sorties_efficacite(athlete_id, jours)
    if len(sorties) < 6:
        return None
    sommeil = met.serie_sommeil(athlete_id, jours + 5)
    vals = []
    for s in sorties:
        h = sommeil.get(s["jour"])
        vals.append((h["heures"] if h and h["origine"] != "estime" else None, s["indice"]))
    ref = statistics.median(s["indice"] for s in sorties)
    return {"reference": round(ref, 2), "nb": sum(1 for x, _ in vals if x is not None),
            "lignes": _par_classe(vals, CLASSES_SOMMEIL, ref)}


def polarisation(athlete_id, jours=42):
    """Répartition du temps par zone de FC (somme des sorties) + modèle dominant."""
    debut = date.today() - timedelta(days=jours)
    z = [0.0] * 5
    nb = 0
    for a in met.activites_periode(athlete_id, debut, None, types=("Trail", "Course", "Randonnée")):
        zs = [a["z1"], a["z2"], a["z3"], a["z4"], a["z5"]]
        if any(zs):
            for i, v in enumerate(zs):
                z[i] += v or 0
            nb += 1
    total = sum(z)
    if total <= 0:
        return None
    pct = [round(v / total * 100, 1) for v in z]
    bas, moyen, haut = pct[0] + pct[1], pct[2], pct[3] + pct[4]
    if bas >= 75 and haut >= moyen:
        modele = "polarisé"
        lecture = "Beaucoup de facile, un peu de très dur, peu de zone moyenne : la répartition la plus efficace pour progresser."
    elif bas >= 70 and moyen > haut:
        modele = "pyramidal"
        lecture = "Surtout facile, un peu de zone 3, peu de très dur : solide. Ajoute une séance vraiment dure si tu veux plus de vitesse."
    elif moyen >= 25:
        modele = "zone grise"
        lecture = "Trop de temps en zone 3 : ni assez facile pour récupérer, ni assez dur pour stimuler. Ralentis les sorties faciles."
    elif bas < 60:
        modele = "intense"
        lecture = "Plus de 40 % du temps au-dessus de la zone 2 : risque de fatigue. Remets du volume facile."
    else:
        modele = "mixte"
        lecture = "Répartition intermédiaire."
    return {"pct": pct, "bas": round(bas, 1), "moyen": round(moyen, 1), "haut": round(haut, 1),
            "modele": modele, "lecture": lecture, "nb_sorties": nb, "jours": jours}
