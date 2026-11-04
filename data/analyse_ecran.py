"""
Analyse IA des écrans (v106) : tableau de bord, sommeil, poids, VMA / VO2max, meilleurs
efforts, conditions, courbes, courses.

Principe : le logiciel CALCULE les chiffres (dossier), l'IA ne fait que les LIRE. Le dossier
ne contient que des valeurs mesurées ou calculées localement ; l'IA a l'interdiction d'en
inventer. Le résultat est mis en cache tant que le dossier ne change pas (aucun nouvel
appel, donc aucune consommation de quota). Sans clé IA : résumé calculé en local.
"""

import hashlib
import json
import statistics
from datetime import date, timedelta

import noyau.entrainement.metriques as met
from data.database import connexion

VERSION_PROMPT = "v106-1"

FORMAT_REPONSE = (
    "FORMAT (Markdown, 180 mots maximum) :\n"
    "**Lecture** : 2 ou 3 phrases chiffrées sur ce que montrent les données.\n"
    "**Cause probable** : 1 ou 2 phrases, avec le niveau de certitude (les corrélations ne prouvent rien).\n"
    "**À faire** : 1 à 3 actions concrètes et chiffrées (durée, allure, bpm, kg, heures de sommeil).\n"
)

INSTRUCTIONS = {
    "aujourdhui": "Synthèse du jour de l'athlète : état de forme, ce qui prime aujourd'hui (alerte, fatigue, séance prévue "
                  "contre décision du coach du jour), puis la priorité de la journée.",
    "sommeil": "Sommeil, HRV de nuit et FC de repos : dette, tendance, lien avec la fatigue et la charge, "
               "et ce qu'il faut faire ce soir et les prochains jours.",
    "poids": "Poids (pesées du matin) et état des jambes : tendance lissée (pas un relevé isolé : l'eau et le glycogène "
             "font varier de 0,5 à 1 kg), rythme vers l'objectif s'il existe, lien avec jambes et fatigue.",
    "vma": "VMA et VO2max ESTIMÉS (« estimation basse » : tes sorties sont rarement des efforts maximaux, les valeurs "
           "vraies sont plus hautes). Dis si la tendance est réelle ou du bruit, compare avec le profil, et donne "
           "les allures à viser.",
    "efforts": "Meilleurs efforts par durée et vitesse critique (estimation basse) : repère le point faible (court/vitesse "
               "ou long/endurance) et la séance type qui le travaille.",
    "conditions": "Effet de la température et du sommeil sur l'efficacité (indice km-effort/h ÷ FC × 100) et répartition "
                  "de l'intensité (polarisation). Ne conclus que sur les classes d'au moins 3 sorties.",
    "courbe": "Courbes affichées à l'écran : explique ce qu'elles montrent (tendance, variation, valeurs extrêmes) et ce "
              "que l'athlète doit en faire.",
    "courses": "Préparation à la prochaine course : écart entre la préparation actuelle et ce que la course demande, chrono "
               "prédit (estimation basse), et les 3 priorités des semaines restantes.",
}


# ------------------------------------------------------------------ outils
def _nettoyer(x, profondeur=0):
    if isinstance(x, dict):
        return {str(k): _nettoyer(v, profondeur + 1) for k, v in x.items() if v is not None}
    if isinstance(x, (list, tuple)):
        return [_nettoyer(v, profondeur + 1) for v in list(x)[-30:]]
    if isinstance(x, float):
        return round(x, 2)
    if isinstance(x, (int, str, bool)):
        return x
    if isinstance(x, date):
        return x.isoformat()
    return str(x)


def stats_serie(valeurs):
    """Résumé chiffré d'une courbe (None ignorés)."""
    v = [float(x) for x in valeurs if x is not None]
    if not v:
        return None
    res = {"nb_points": len(v), "premier": round(v[0], 2), "dernier": round(v[-1], 2),
           "min": round(min(v), 2), "max": round(max(v), 2), "moyenne": round(statistics.mean(v), 2),
           "derniers": [round(x, 2) for x in v[-5:]]}
    if v[0]:
        res["variation_pct"] = round((v[-1] / v[0] - 1) * 100, 1)
    return res


def _moyennes_7j(points):
    """points [(date, valeur)] -> (moyenne 7 derniers jours, moyenne des 7 jours d'avant)."""
    if not points:
        return None, None
    fin = points[-1][0]
    a = [v for d, v in points if fin - timedelta(days=6) <= d <= fin]
    b = [v for d, v in points if fin - timedelta(days=13) <= d < fin - timedelta(days=6)]
    return (round(statistics.mean(a), 2) if a else None, round(statistics.mean(b), 2) if b else None)


def _forme(a):
    try:
        from noyau.entrainement.coach import calculer_serie_forme
        s = calculer_serie_forme(a, 60)
        if s:
            return {k: s[-1][k] for k in ("fitness", "fatigue", "forme")}
    except Exception:
        pass
    return None


# ----------------------------------------------------------------- dossiers
def dossier_sommeil(a):
    d = {}
    try:
        ds = met.dette_sommeil(a, 14)
        d["sommeil"] = {"objectif_h": ds["objectif"], "dette_h": ds["dette_h"], "niveau": ds["niveau"],
                        "moyenne_h": ds["moyenne_h"], "nb_nuits": ds["nb_jours"],
                        "dernieres_nuits_h": [h for _, h in ds["serie"][-7:]]}
        hv = met.hrv_avec_bande(a, 60)
        d["hrv"] = {"statut": hv["statut"], "moyenne_7j_ms": hv["moyenne_7j"], "bande_ms": hv["bande"],
                    "nb_mesures": hv["nb_mesures"]}
        fc = met.fc_repos_et_alerte(a, 60)
        d["fc_repos"] = {"derniere": fc["derniere"], "base": fc["base"], "ecart_bpm": fc["ecart"], "niveau": fc["niveau"]}
    except Exception:
        pass
    d["forme"] = _forme(a)
    return _nettoyer(d)


def dossier_poids(a):
    pts = met.poids_serie(a, 90)
    d = {"nb_pesees_matin": len(pts)}
    if pts:
        d["poids"] = stats_serie([p for _, p in pts])
        m7, m7p = _moyennes_7j(pts)
        d["moyenne_7j_kg"], d["moyenne_7j_precedents_kg"] = m7, m7p
    try:
        d["objectif_kg"] = met.objectif_poids(a)
        d["poids_depart_kg"] = met.poids_depart(a)
    except Exception:
        pass
    try:
        from noyau.sante.mensurations import resume_mesures
        m = resume_mesures(a)
        if m:
            d["mensurations"] = {v["libelle"]: {"derniere": v["derniere"], "unite": v["unite"],
                                                "ecart_depuis_premiere": v["ecart"], "nb_releves": v["nb"]}
                                 for v in m.values()}
    except Exception:
        pass
    conn = connexion()
    cur = conn.cursor()
    cur.execute("SELECT date, fatigue_jambes, fatigue_generale, etat_jambes FROM suivi_corporel WHERE athlete_id=? "
                "ORDER BY date DESC, id DESC LIMIT 14", (a,))
    d["releves_recents"] = [{"date": str(r[0])[:10], "fatigue_jambes": r[1], "fatigue_generale": r[2], "jambes": r[3]}
                            for r in cur.fetchall()]
    conn.close()
    d["forme"] = _forme(a)
    return _nettoyer(d)


def dossier_vma(a):
    d = {}
    try:
        from noyau.entrainement.vma import calculer_vma
        v = calculer_vma(a)
        if v:
            d["vma_estimee_kmh"] = v["actuelle"]
            d["date_reference"] = v["date_reference"]
            d["record_90j"] = v["record"]
            d["nb_efforts"] = v["nb_efforts"]
            d["efforts_retenus"] = [{"date": e["date"], "km": e["km"], "dplus": e["dp"], "vma": e["vma"]}
                                    for e in v["meilleurs"]]
        from noyau.entrainement.estimations_basses import serie_estimations, evolution_pct
        s = serie_estimations(a)
        if s:
            for cle in ("vma", "vo2max", "efficacite"):
                d["serie_" + cle] = stats_serie([x[1] for x in s[cle]])
    except Exception:
        pass
    conn = connexion()
    cur = conn.cursor()
    cur.execute("SELECT vma FROM athletes WHERE id=?", (a,))
    r = cur.fetchone()
    conn.close()
    if r and r[0]:
        d["vma_du_profil_kmh"] = r[0]
    d["mention"] = "VMA et VO2max sont des estimations basses (efforts non maximaux)."
    return _nettoyer(d)


def dossier_efforts(efforts, cs):
    d = {"mention": "Estimation basse : sorties non maximales, vitesses corrigées de la pente (plat équivalent)."}
    d["meilleurs_efforts"] = [{"duree_min": round(e["duree_s"] / 60, 1), "vitesse_kmh": round(e["vitesse_kmh"], 1),
                               "date": e["date"]} for e in (efforts or [])]
    if cs:
        d["vitesse_critique_kmh"], d["reserve_Dprime_m"], d["r2"] = cs["cs_kmh"], cs["d_prime_m"], cs["r2"]
    return _nettoyer(d)


def dossier_conditions(a):
    from noyau.entrainement import impact_conditions as ic
    d = {"temperature": ic.impact_temperature(a), "sommeil_nuit": ic.impact_sommeil(a),
         "polarisation_6_semaines": ic.polarisation(a)}
    return _nettoyer(d)


def dossier_courses(a):
    d = {"forme": _forme(a), "courses_a_venir": []}
    vo2 = None
    try:
        from noyau.course import predictions_course as pc
        vo2 = pc.vo2max_de_reference(a)
        d["vo2max_estime"] = vo2
    except Exception:
        pass
    for c in met.courses_a_venir(a)[:3]:
        fiche = dict(c)
        try:
            f = met.forme_pour_distance(a, c["distance_km"], c["denivele_m"] or 0, c["date"])
            fiche["preparation"] = {k: f[k] for k in ("score", "niveau", "conseil", "semaines_restantes")}
            fiche["criteres"] = [{k: x[k] for k in ("nom", "valeur", "cible", "unite")} for x in f["criteres"]]
            if vo2:
                from noyau.course import predictions_course as pc
                t = pc.predire(vo2, c["distance_km"], c["denivele_m"] or 0)
                fiche["chrono_predit_estimation_basse"] = pc.texte_duree(t) if t else None
        except Exception:
            pass
        d["courses_a_venir"].append(fiche)
    return _nettoyer(d)


def dossier_aujourdhui(a):
    try:
        j = met.donnees_aujourdhui(a)
    except Exception:
        j = {}
    d = {"date": date.today().isoformat(), "disponibilite_matin": j.get("dispo"), "seance_prevue": j.get("seance"),
         "volume_semaine": j.get("volume"), "acwr": j.get("acwr"), "course_visee": j.get("course"),
         "alertes": [{k: al.get(k) for k in ("niveau", "titre", "message") if k in al} for al in j.get("alertes") or []]}
    co = j.get("coach")
    if co:
        d["coach_du_jour"] = {"niveau": co["niveau"], "seance": co["titre"], "raisons": co["raisons"]}
    d["ecart_coach_et_plan"] = j.get("ecart_coach")
    d["forme"] = _forme(a)
    d.update({k: v for k, v in dossier_sommeil(a).items() if k in ("sommeil", "hrv", "fc_repos")})
    pts = met.poids_serie(a, 30)
    if pts:
        m7, m7p = _moyennes_7j(pts)
        d["poids_moyenne_7j_kg"], d["poids_moyenne_7j_precedents_kg"] = m7, m7p
    return _nettoyer(d)


def dossier_courbes_widgets(ecran):
    """Dossier générique : cartes de chiffres et courbes visibles sur un écran."""
    from PySide6.QtWidgets import QTableWidget
    from interface.courbe_multiligne import CourbeMultiLignes
    d = {}
    cartes = {}
    for cle, c in (getattr(ecran, "cartes", None) or {}).items():
        try:
            cartes[cle] = {"valeur": c.valeur.text(), "detail": _sans_html(c.detail.text())}
        except Exception:
            pass
    if cartes:
        d["chiffres_affiches"] = cartes
    courbes = []
    for cb in ecran.findChildren(CourbeMultiLignes):
        for s in cb.series or []:
            vals = [v[1] if isinstance(v, (tuple, list)) else v for v in s.get("valeurs", [])]
            st = stats_serie(vals)
            if st:
                courbes.append({"courbe": s.get("nom", ""), **st})
    if courbes:
        d["courbes"] = courbes
    tables = []
    for t in ecran.findChildren(QTableWidget):
        if t.rowCount() and t.columnCount():
            en_tetes = [t.horizontalHeaderItem(i).text() if t.horizontalHeaderItem(i) else "" for i in range(t.columnCount())]
            lignes = []
            for r in range(min(t.rowCount(), 12)):
                lignes.append({en_tetes[c]: (t.item(r, c).text() if t.item(r, c) else "") for c in range(t.columnCount())})
            tables.append(lignes)
    if tables:
        d["tableaux"] = tables[:3]
    return d


def _sans_html(texte):
    import re
    return re.sub(r"<[^>]+>", "", texte or "").strip()


# ------------------------------------------------------------------ analyse
def _empreinte(sujet, dossier):
    brut = json.dumps([VERSION_PROMPT, sujet, dossier], sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha1(brut.encode("utf-8")).hexdigest()


def en_cache(athlete_id, sujet, dossier):
    conn = connexion()
    cur = conn.cursor()
    cur.execute("SELECT contenu FROM analyses_ecran WHERE athlete_id=? AND sujet=? AND empreinte=? ORDER BY id DESC LIMIT 1",
                (athlete_id, sujet, _empreinte(sujet, dossier)))
    r = cur.fetchone()
    conn.close()
    return r[0] if r else None


def _enregistrer(athlete_id, sujet, dossier, texte):
    conn = connexion()
    cur = conn.cursor()
    cur.execute("INSERT INTO analyses_ecran (athlete_id, sujet, empreinte, contenu) VALUES (?,?,?,?)",
                (athlete_id, sujet, _empreinte(sujet, dossier), texte))
    cur.execute("DELETE FROM analyses_ecran WHERE athlete_id=? AND sujet=? AND id NOT IN "
                "(SELECT id FROM analyses_ecran WHERE athlete_id=? AND sujet=? ORDER BY id DESC LIMIT 5)",
                (athlete_id, sujet, athlete_id, sujet))
    conn.commit()
    conn.close()


def construire_prompt(sujet, dossier):
    from noyau.ia.ia_coach import CONSIGNES_COMMUNES
    instruction = INSTRUCTIONS.get(sujet, INSTRUCTIONS["courbe"])
    return ("Tu es un entraîneur de trail et de course à pied, précis et technique.\n"
            f"MISSION : {instruction}\n\n{CONSIGNES_COMMUNES}\n{FORMAT_REPONSE}\n"
            "DONNÉES (JSON, calculées par le logiciel) :\n"
            + json.dumps(dossier, ensure_ascii=False, default=str))


def resume_local(sujet, dossier):
    """Résumé sans IA : les chiffres clés du dossier, une ligne par bloc."""
    lignes = []

    def scalaire(v):
        return not isinstance(v, (dict, list))

    def libelle(k):
        return str(k).replace("_", " ")

    def ligne(nom, d):
        return f"- {nom} : " + " · ".join(f"{libelle(k)} {v}" for k, v in d.items() if scalaire(v))

    def parcourir(obj, nom=""):
        if isinstance(obj, dict):
            plats = {k: v for k, v in obj.items() if scalaire(v) and k != "mention"}
            if nom and plats:
                lignes.append(ligne(nom, plats))
            elif plats:
                for k, v in plats.items():
                    lignes.append(f"- {libelle(k)} : {v}")
            for k, v in obj.items():
                if k == "mention" or scalaire(v):
                    continue
                parcourir(v, libelle(k))
        elif isinstance(obj, list):
            if obj and all(scalaire(x) for x in obj):
                lignes.append(f"- {nom} : {', '.join(str(x) for x in obj[-6:])}")
            else:
                for x in obj[:3]:
                    parcourir(x, nom)

    parcourir(dossier)
    return "**Chiffres clés** (résumé local, sans IA)\n" + "\n".join(lignes[:16])


def cle_ia_disponible():
    try:
        from noyau.ia.ia_coach import cle_api_configuree, cle_api_groq_configuree
        return bool(cle_api_configuree() or cle_api_groq_configuree())
    except Exception:
        return False


def analyser(athlete_id, sujet, dossier, forcer=False, appeler=None):
    """Retourne (texte, source) avec source = 'cache' | 'ia' | 'local'.
    Peut lever ErreurAnalyseIA si l'appel IA échoue."""
    if not dossier:
        return "Pas assez de données pour analyser cet écran.", "local"
    if not forcer:
        c = en_cache(athlete_id, sujet, dossier)
        if c:
            return c, "cache"
    if appeler is None and not cle_ia_disponible():
        return resume_local(sujet, dossier), "local"
    if appeler is None:
        from noyau.ia.ia_coach import _appeler_ia as appeler
    texte = (appeler(construire_prompt(sujet, dossier)) or "").strip()
    if not texte:
        return resume_local(sujet, dossier), "local"
    _enregistrer(athlete_id, sujet, dossier, texte)
    return texte, "ia"
