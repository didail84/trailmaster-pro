"""
Score « Prêt à courir » (0 à 100), calculé chaque matin.

Il part de la disponibilité du matin (fraîcheur, dernière nuit, VFC, FC
de repos, blessure : metriques.disponibilite_matin) et y ajoute :
  - la charge de la semaine (rapport aiguë / chronique : calcul local, ou
    celui de Garmin reçu par les connecteurs Claude s'il est plus récent) ;
  - le ressenti du matin (jambes et fatigue générale sur 10, écran
    « Poids & récupération ») ;
  - l'agenda du jour (Google Agenda via les connecteurs : journée chargée).

Un signal absent est ignoré et son poids redistribué. Le résultat donne
aussi une phrase de conseil, sans jargon.
"""

from datetime import date, timedelta

from data.database import connexion

POIDS = {"dispo": 0.50, "charge": 0.20, "ressenti": 0.20, "agenda": 0.10}


def _score_acwr(r):
    """1,0 = 100 ; on perd des points en s'éloignant de la zone conseillée (0,8 à 1,3)."""
    if r is None:
        return None
    if 0.8 <= r <= 1.3:
        return round(100 - abs(r - 1.05) * 40)
    if r > 1.3:
        return max(10, round(80 - (r - 1.3) * 200))
    return max(40, round(90 - (0.8 - r) * 120))


def charge_du_jour(athlete_id):
    """(acwr, source) : connecteurs (Garmin) si reçu ces 2 derniers jours, sinon calcul local."""
    try:
        conn = connexion()
        try:
            l = conn.execute("SELECT date, acwr, source FROM connecteurs_charge WHERE athlete_id=? "
                             "ORDER BY date DESC, id DESC LIMIT 1", (athlete_id,)).fetchone()
        finally:
            conn.close()
        if l and l[1] is not None and l[0] >= (date.today() - timedelta(days=2)).isoformat():
            return float(l[1]), l[2] or "Garmin"
    except Exception:
        pass
    try:
        from noyau.entrainement.coach import calculer_acwr
        a = calculer_acwr(athlete_id) or {}
        if a.get("acwr") is not None:
            return float(a["acwr"]), "calcul du logiciel"
    except Exception:
        pass
    return None, None


def ressenti_du_matin(athlete_id, jour=None):
    """(jambes, generale) sur 10 saisis aujourd'hui (ou hier soir), sinon (None, None)."""
    jour = jour or date.today()
    conn = connexion()
    try:
        l = conn.execute("SELECT fatigue_jambes, fatigue_generale FROM suivi_corporel WHERE athlete_id=? "
                         "AND date>=? ORDER BY date DESC, id DESC LIMIT 1",
                         (athlete_id, (jour - timedelta(days=1)).isoformat())).fetchone()
    finally:
        conn.close()
    return (l[0], l[1]) if l else (None, None)


def calculer(athlete_id, jour=None):
    from noyau.entrainement.metriques import disponibilite_matin
    from noyau.sante.rythme_vie import contexte_fatigue_vie
    jour = jour or date.today()
    facteurs = []     # (cle, libelle, score, detail, poids)

    d = disponibilite_matin(athlete_id)
    if d.get("score") is not None:
        facteurs.append(("dispo", "Récupération", d["score"], d.get("verdict", ""), POIDS["dispo"]))

    acwr, source = charge_du_jour(athlete_id)
    sc = _score_acwr(acwr)
    if sc is not None:
        zone = "zone conseillée" if 0.8 <= acwr <= 1.3 else ("au-dessus de la zone" if acwr > 1.3 else "en baisse")
        facteurs.append(("charge", "Charge 7 j / 42 j", sc, f"{acwr:.2f}".replace(".", ",") + f" ({zone}, {source})",
                         POIDS["charge"]))

    jambes, generale = ressenti_du_matin(athlete_id, jour)
    vals = [v for v in (jambes, generale) if v is not None]
    if vals:
        moy = sum(vals) / len(vals)          # 0 = en pleine forme, 10 = épuisé
        detail = " · ".join(t for t in (f"jambes {jambes}/10" if jambes is not None else "",
                                        f"générale {generale}/10" if generale is not None else "") if t)
        facteurs.append(("ressenti", "Ressenti du matin", round(max(0, 100 - moy * 10)), detail, POIDS["ressenti"]))

    try:
        vie = contexte_fatigue_vie(jour)
    except Exception:
        vie = {}
    h = vie.get("agenda_heures") or 0
    if h:
        bonus = vie.get("agenda_bonus") or 0
        facteurs.append(("agenda", "Agenda du jour", 100 - bonus * 30,
                         f"{str(round(h, 1)).replace('.', ',')} h d'engagements", POIDS["agenda"]))

    if not facteurs:
        return {"score": None, "verdict": "Pas encore assez de données",
                "conseil": "Importe tes sorties et ta récupération (Garmin, Strava ou connecteurs Claude) "
                           "ou note ton ressenti du matin.", "facteurs": []}
    total = sum(f[4] for f in facteurs)
    score = round(sum(f[2] * f[4] for f in facteurs) / total)
    if any(k == "dispo" for k, *_ in facteurs) and d.get("score") is not None and d["score"] <= 45:
        score = min(score, d["score"] + 10)        # une blessure ou une nuit très courte plafonne
    verdict, conseil = verdict_et_conseil(score, acwr, jambes, h)
    return {"score": score, "verdict": verdict, "conseil": conseil, "acwr": acwr, "source_charge": source,
            "facteurs": [{"cle": k, "libelle": l, "score": s, "detail": det} for k, l, s, det, _p in facteurs]}


def verdict_et_conseil(score, acwr=None, jambes=None, heures_agenda=0):
    if score >= 75:
        verdict, conseil = "Prêt à courir", "Tu peux faire la séance prévue, même intense."
    elif score >= 55:
        verdict, conseil = "Séance normale possible", "Fais la séance prévue sans chercher à aller plus vite."
    elif score >= 35:
        verdict, conseil = "Récupération en cours", "Footing court en zone 2 ou repos."
    else:
        verdict, conseil = "Repos conseillé", "Ton corps a besoin d'une journée sans course."
    raisons = []
    if acwr is not None and acwr > 1.3:
        raisons.append("charge élevée")
    if jambes is not None and jambes >= 7:
        raisons.append("jambes lourdes")
    if heures_agenda and heures_agenda >= 9:
        raisons.append("journée chargée")
    if raisons and score < 75:
        conseil = conseil[:-1] + " (" + ", ".join(raisons) + ")."
    return verdict, conseil
