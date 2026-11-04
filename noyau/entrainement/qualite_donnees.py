"""
Contrôle de la qualité des données (v104) : repère ce qui fausse les analyses —
sorties sans fréquence cardiaque, valeurs aberrantes, doublons probables,
trous de santé — et répare ce qui peut l'être sans rien inventer (la FC d'une
sortie est recalculée depuis sa trace quand la trace la contient).
"""

import json
import statistics
from datetime import date, timedelta

from data.database import connexion

TYPES_COURSE = ("Trail", "Course")


def _course_filtre():
    return "type IN ('Trail','Course') AND distance>=3 AND duree>0"


def _moyenne_fc_trace(points):
    fcs = [p[4] for p in points if len(p) > 4 and p[4] and 30 < p[4] < 240]
    if len(fcs) < 30:
        return None
    return round(statistics.mean(fcs)), max(fcs)


def _traces_par_activite(cur, ids=None):
    cur.execute("SELECT activite_id, trace_json FROM parcours_gpx WHERE activite_id IS NOT NULL AND trace_json IS NOT NULL")
    res = {}
    for aid, tj in cur.fetchall():
        if ids is not None and aid not in ids:
            continue
        res[aid] = tj
    return res


def controler(athlete_id):
    """{problemes: [{code, gravite, texte, nb, details:[...]}], score, nb_sorties}."""
    conn = connexion()
    cur = conn.cursor()
    cur.execute(f"SELECT id, date, nom, type, distance, duree, frequence_cardiaque_moyenne, "
                f"frequence_cardiaque_max FROM activites WHERE athlete_id=? AND {_course_filtre()} ORDER BY date",
                (athlete_id,))
    sorties = cur.fetchall()
    cur.execute("SELECT fc_max FROM athletes WHERE id=?", (athlete_id,))
    r = cur.fetchone()
    fc_max_ath = r[0] if r and r[0] else 190
    traces = _traces_par_activite(cur)
    problemes = []

    sans_fc = [s for s in sorties if not s[6]]
    recuperables = []
    for s in sans_fc:
        tj = traces.get(s[0])
        if tj:
            try:
                if _moyenne_fc_trace(json.loads(tj)):
                    recuperables.append(s)
            except (ValueError, TypeError):
                pass
    if sans_fc:
        problemes.append({
            "code": "fc_absente", "gravite": "attention" if len(sans_fc) > 3 else "info",
            "texte": f"{len(sans_fc)} sortie(s) de course sans fréquence cardiaque "
                     f"({len(recuperables)} récupérable(s) depuis leur trace).",
            "nb": len(sans_fc), "recuperables": len(recuperables),
            "details": [f"{str(s[1])[:10]} · {s[2] or s[3]} · {s[4]:.1f} km" for s in sans_fc[-12:]]})

    aberr = []
    for s in sorties:
        fcm, fcx = s[6], s[7]
        if (fcm and (fcm < 40 or fcm > fc_max_ath + 10)) or (fcx and fcx > 230):
            aberr.append(f"{str(s[1])[:10]} · FC moy {fcm} / max {fcx}")
        elif s[4] and s[5]:
            allure = s[5] / 60 / s[4]
            if allure < 3.0 or allure > 15:
                aberr.append(f"{str(s[1])[:10]} · allure {allure:.1f} min/km (GPS ou durée douteux)")
    if aberr:
        problemes.append({"code": "aberrantes", "gravite": "attention",
                          "texte": f"{len(aberr)} valeur(s) aberrante(s) (FC ou allure).",
                          "nb": len(aberr), "details": aberr[-12:]})

    sans_trace = [s for s in sorties if s[0] not in traces]
    if sans_trace:
        problemes.append({"code": "sans_trace", "gravite": "info",
                          "texte": f"{len(sans_trace)} sortie(s) sans trace GPS : pas d'analyse de pente, de montées ni de découplage.",
                          "nb": len(sans_trace),
                          "details": [f"{str(s[1])[:10]} · {s[2] or s[3]}" for s in sans_trace[-12:]]})

    doublons = []
    for a, b in zip(sorties, sorties[1:]):
        if str(a[1])[:10] == str(b[1])[:10] and a[4] and b[4] and a[5] and b[5] \
                and abs(a[4] - b[4]) / max(a[4], b[4]) < 0.02 and abs(a[5] - b[5]) / max(a[5], b[5]) < 0.05:
            doublons.append(f"{str(a[1])[:10]} · {a[4]:.1f} km · {a[2] or ''} / {b[2] or ''}")
    if doublons:
        problemes.append({"code": "doublons", "gravite": "attention",
                          "texte": f"{len(doublons)} doublon(s) probable(s) : ils gonflent la charge et les totaux.",
                          "nb": len(doublons), "details": doublons[-12:]})

    debut = (date.today() - timedelta(days=30)).isoformat()
    try:
        cur.execute("SELECT date, hrv_nuit_ms, fc_repos FROM recuperation_quotidienne WHERE athlete_id=? AND date>=?",
                    (athlete_id, debut))
        lignes = cur.fetchall()
    except Exception:
        lignes = []
    jours_hrv = {str(d)[:10] for d, h, f in lignes if h}
    jours_fc = {str(d)[:10] for d, h, f in lignes if f}
    if len(jours_hrv) < 20 or len(jours_fc) < 20:
        problemes.append({
            "code": "sante_trous", "gravite": "info",
            "texte": f"Santé des 30 derniers jours : HRV sur {len(jours_hrv)} jours, FC de repos sur {len(jours_fc)} jours. "
                     "Les bandes normales et alertes sont moins fiables sous 20 jours.",
            "nb": 30 - min(len(jours_hrv), len(jours_fc)), "details": []})
    conn.close()

    penalite = sum({"critique": 25, "attention": 10, "info": 4}[p["gravite"]] for p in problemes)
    return {"problemes": problemes, "score": max(0, 100 - penalite), "nb_sorties": len(sorties)}


def reparer_fc(athlete_id):
    """Recalcule la FC moyenne / max des sorties sans FC depuis leur trace.
    Retourne le nombre de sorties réparées."""
    conn = connexion()
    cur = conn.cursor()
    cur.execute(f"SELECT id FROM activites WHERE athlete_id=? AND {_course_filtre()} "
                "AND (frequence_cardiaque_moyenne IS NULL OR frequence_cardiaque_moyenne=0)", (athlete_id,))
    ids = {r[0] for r in cur.fetchall()}
    n = 0
    for aid, tj in _traces_par_activite(cur, ids).items():
        try:
            res = _moyenne_fc_trace(json.loads(tj))
        except (ValueError, TypeError):
            continue
        if res:
            cur.execute("UPDATE activites SET frequence_cardiaque_moyenne=?, frequence_cardiaque_max=COALESCE(NULLIF(frequence_cardiaque_max,0),?) WHERE id=?",
                        (res[0], res[1], aid))
            n += 1
    conn.commit()
    conn.close()
    return n
