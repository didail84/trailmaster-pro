"""
Coach du jour (v103) — décide de la séance du jour à partir de signaux déjà
mesurés : jambes et RPE saisis, fraîcheur (TSB), HRV, FC de repos, sommeil,
blessure. Aucune IA : règles simples, chiffrées et expliquées.

Sortie : un niveau (vert / orange / rouge), la consigne, la séance structurée
(étapes au format de l'écran Séances, donc exportable sur la montre) et une
routine de renfort / mobilité adaptée. Ce sont des repères d'entraînement,
pas un avis médical : en cas de douleur, on consulte.
"""

from datetime import date, timedelta

from data.database import connexion

VERT, ORANGE, ROUGE = "vert", "orange", "rouge"


# ---------------------------------------------------------------- signaux
def derniers_releves(athlete_id, jour=None):
    """(fatigue_jambes, fatigue_generale, date) du relevé le plus récent
    des 2 derniers jours, sinon (None, None, None)."""
    jour = jour or date.today()
    conn = connexion()
    cur = conn.cursor()
    cur.execute(
        "SELECT date, fatigue_jambes, fatigue_generale FROM suivi_corporel "
        "WHERE athlete_id=? AND date<=? ORDER BY date DESC, id DESC LIMIT 1",
        (athlete_id, jour.isoformat() + " 23:59:59"),
    )
    r = cur.fetchone()
    conn.close()
    if not r:
        return None, None, None
    d = str(r[0])[:10]
    try:
        if (jour - date.fromisoformat(d)).days > 2:
            return None, None, None
    except ValueError:
        return None, None, None
    return r[1], r[2], d


def _tsb(athlete_id):
    try:
        from noyau.entrainement.coach import calculer_serie_forme
        serie = calculer_serie_forme(athlete_id, 120)
        return serie[-1]["forme"] if serie else None
    except Exception:
        return None


def _hrv_fc_sommeil(athlete_id):
    hrv = fc = dette = None
    try:
        import noyau.entrainement.metriques as met
        hrv = met.hrv_avec_bande(athlete_id, 60).get("statut")
        fc = met.fc_repos_et_alerte(athlete_id, 60).get("niveau")
        dette = met.dette_sommeil(athlete_id, 7).get("dette_h")
    except Exception:
        pass
    return hrv, fc, dette


def _blessure(athlete_id):
    try:
        from noyau.entrainement.coach import _blessures_actives
        return bool(_blessures_actives(athlete_id))
    except Exception:
        return False


# --------------------------------------------------------------- décision
def evaluer(jambes=None, rpe=None, tsb=None, hrv=None, fc_repos=None,
            dette_sommeil_h=None, blessure=False):
    """Fonction pure. Retourne (niveau, points, raisons).
    jambes / rpe : 1 à 10 (10 = très fatigué / très dur)."""
    pts, raisons = 0, []
    if blessure:
        return ROUGE, 99, ["Blessure active : pas de séance de course sans avis adapté."]
    if jambes is not None:
        if jambes >= 7:
            pts += 3; raisons.append(f"Jambes très fatiguées ({jambes}/10).")
        elif jambes >= 5:
            pts += 2; raisons.append(f"Jambes fatiguées ({jambes}/10).")
        elif jambes >= 4:
            pts += 1; raisons.append(f"Jambes un peu lourdes ({jambes}/10).")
        else:
            raisons.append(f"Jambes fraîches ({jambes}/10).")
    if rpe is not None:
        if rpe >= 8:
            pts += 2; raisons.append(f"Dernière sortie très dure (RPE {rpe}/10).")
        elif rpe >= 6:
            pts += 1; raisons.append(f"Dernière sortie soutenue (RPE {rpe}/10).")
        else:
            raisons.append(f"Dernière sortie facile (RPE {rpe}/10).")
    if tsb is not None:
        if tsb <= -25:
            pts += 3; raisons.append(f"Fraîcheur très basse (TSB {tsb:+.0f}).")
        elif tsb <= -15:
            pts += 1; raisons.append(f"Fraîcheur basse (TSB {tsb:+.0f}).")
        elif tsb >= 5:
            raisons.append(f"Bien frais (TSB {tsb:+.0f}).")
    if hrv == "basse":
        pts += 2; raisons.append("HRV de nuit sous ta bande normale.")
    if fc_repos == "alerte":
        pts += 2; raisons.append("FC de repos nettement au-dessus de ta base.")
    elif fc_repos == "attention":
        pts += 1; raisons.append("FC de repos un peu au-dessus de ta base.")
    if dette_sommeil_h is not None and dette_sommeil_h >= 5:
        pts += 1; raisons.append(f"Dette de sommeil de {dette_sommeil_h:.0f} h sur 7 jours.")
    niveau = ROUGE if pts >= 6 else ORANGE if pts >= 3 else VERT
    return niveau, pts, raisons


def _allure(vitesse_kmh):
    sec = int(round(3600 / vitesse_kmh))
    return f"{sec // 60}:{sec % 60:02d}"


def construire_seance(niveau, vma_kmh=None, fc_max=None, tsb=None, jambes=None):
    """(titre, consigne, etapes). Étapes au format de l'écran Séances."""
    def zone(i):
        if not fc_max:
            return None
        from noyau.ia.analyse_technique import zones_fc
        z = zones_fc(fc_max)[i]
        return round((z[1] + z[2]) / 2)

    def etape(type_, minutes, pct_vma, fc_zone):
        return {"type": type_, "mode": "duree", "valeur": minutes,
                "allure_cible": _allure(vma_kmh * pct_vma) if vma_kmh else None,
                "fc_cible": zone(fc_zone) if not vma_kmh or pct_vma is None else None}

    if niveau == ROUGE:
        return ("Repos ou marche active",
                "Repos complet, ou 20–30 min de marche / vélo très facile sans objectif. "
                "On repart quand les jambes et la HRV reviennent.", [])
    if niveau == ORANGE:
        return ("Footing de récupération",
                "30–40 min en aisance respiratoire, FC en zone 1–2, aucune allure à tenir. "
                "Reporte la séance de qualité d'un jour ou deux.",
                [etape("Échauffement", 5, 0.55, 0),
                 etape("Effort", 25, 0.62, 1),
                 etape("Retour au calme", 5, 0.55, 0)])
    # vert : qualité si bien frais, sinon endurance
    if (tsb is None or tsb >= -10) and (jambes is None or jambes <= 3):
        return ("Séance de qualité : 5 × 4 min au seuil",
                "Échauffement 15 min, 5 × 4 min à ~88 % VMA (récup 2 min trot), retour au calme 10 min. "
                "Si les 2 dernières répétitions dérivent de plus de 5 bpm, arrête là.",
                [etape("Échauffement", 15, 0.62, 1)]
                + [e for _ in range(5)
                   for e in (etape("Effort", 4, 0.88, 3), etape("Récupération", 2, 0.55, 1))]
                + [etape("Retour au calme", 10, 0.58, 0)])
    return ("Endurance fondamentale",
            "50–70 min en zone 2, allure confortable, relances libres sur le terrain. "
            "Pas d'intensité : tu es en forme mais pas assez frais pour de la qualité.",
            [etape("Échauffement", 5, 0.58, 0), etape("Effort", 50, 0.68, 1),
             etape("Retour au calme", 5, 0.58, 0)])


ROUTINES = {
    VERT: ["Renfort 10 min : 2 × 12 squats, fentes, montées de banc, mollets (sur une marche), gainage 3 × 40 s.",
           "Mobilité 5 min : hanches, chevilles, ischios."],
    ORANGE: ["Mobilité 10 min : hanches, quadriceps, mollets, fessiers au rouleau.",
             "Pas de renfort lourd aujourd'hui : gainage léger seulement."],
    ROUGE: ["Mobilité douce 10 min, étirements sans douleur, marche.",
            "Pas de renforcement. Priorité au sommeil."],
}


def coach_du_jour(athlete_id, jour=None, jambes=None, rpe=None):
    """Décision complète. jambes : saisi à l'écran, sinon lu dans le suivi corporel ;
    rpe : saisi à l'écran (la RPE d'une sortie n'est pas stockée en base)."""
    jour = jour or date.today()
    j_base, g_base, d_rel = derniers_releves(athlete_id, jour)
    jambes = jambes if jambes is not None else j_base
    tsb = _tsb(athlete_id)
    hrv, fc, dette = _hrv_fc_sommeil(athlete_id)
    niveau, pts, raisons = evaluer(jambes, rpe, tsb, hrv, fc, dette, _blessure(athlete_id))

    vma = fc_max = None
    try:
        from noyau.entrainement.vma import calculer_vma
        v = calculer_vma(athlete_id)
        vma = v["actuelle"] if v else None
    except Exception:
        pass
    conn = connexion()
    cur = conn.cursor()
    cur.execute("SELECT fc_max FROM athletes WHERE id=?", (athlete_id,))
    r = cur.fetchone()
    conn.close()
    fc_max = r[0] if r and r[0] else None

    titre, consigne, etapes = construire_seance(niveau, vma, fc_max, tsb, jambes)
    signaux = sum(x is not None for x in (jambes, rpe, tsb)) + sum(bool(x) for x in (hrv, fc))
    return {
        "niveau": niveau, "points": pts, "raisons": raisons, "titre": titre,
        "consigne": consigne, "etapes": etapes, "routine": ROUTINES[niveau],
        "vma_utilisee": vma, "nb_signaux": signaux,
        "avertissement": ("Peu de signaux disponibles : saisis tes jambes et ta RPE pour une décision fiable."
                          if signaux < 2 else ""),
    }


MOTS_INTENSES = ("fraction", "seuil", "interval", "vma", "côte", "cote", "tempo", "qualité", "qualite",
                 "allure spécifique", "allure specifique", "pyramide", "cavalier")


def ecart_avec_plan(coach, seance):
    """Message si la séance PRÉVUE est intense alors que le coach conseille d'alléger ;
    None sinon. coach : résultat de coach_du_jour ; seance : dict (nom, type, statut)."""
    if not coach or not seance or (seance.get("statut") or "") not in ("", "Prévue"):
        return None
    if coach.get("niveau") not in (ORANGE, ROUGE):
        return None
    texte = f"{seance.get('nom') or ''} {seance.get('type') or ''}".lower()
    if not any(m in texte for m in MOTS_INTENSES):
        return None
    action = "repos ou marche" if coach["niveau"] == ROUGE else "un footing de récupération"
    return (f"Le coach du jour conseille d'alléger ({'; '.join(coach['raisons'][:2])}) : "
            f"remplace la séance prévue par {action}.")
