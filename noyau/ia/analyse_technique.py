"""
Dossier TECHNIQUE envoyé à l'IA (v101) — aucun widget, aucun appel Internet.

L'IA n'invente rien : tout ce qu'elle commente est calculé ici, en local, à
partir de la trace GPS/FC et de la base. Chaque bloc est facultatif : si une
donnée manque (pas de trace, pas de FC, pas de HRV…), le bloc est simplement
absent, et la consigne donnée à l'IA lui demande de le dire plutôt que de
combler. Les valeurs ESTIMÉES (zones en % de la FC max, VMA, VO₂max, allure
ajustée à la pente) sont marquées comme telles.

Deux dossiers :
  - dossier_sortie(...)   : une séance (allure ajustée, découplage, VAM, zones
                            de FC, durabilité, comparaison avec des sorties
                            similaires, charge/fraîcheur au jour J, récupération)
  - dossier_periode(...)  : une semaine / un mois / une année (volume en
                            km-effort, répartition d'intensité, tendances
                            d'efficacité, charge, monotonie, VMA/VO₂, récupération)
"""

import statistics
from datetime import date, datetime, timedelta

from data.database import connexion

# Zones de FC comme sur les montres Garmin : % de la FC max.
BORNES_ZONES_PCT = (0.50, 0.60, 0.70, 0.80, 0.90, 1.00)
NOMS_ZONES = ("Z1 récupération", "Z2 endurance", "Z3 tempo", "Z4 seuil", "Z5 VO2max")
TYPES_COURSE = ("Trail", "Course")


# ----------------------------------------------------------------------
# Petits outils
# ----------------------------------------------------------------------

def _txt_allure(min_km):
    """5.7 -> '5:42' (min/km)."""
    if not min_km or min_km <= 0 or min_km > 40:
        return None
    m = int(min_km)
    s = int(round((min_km - m) * 60))
    if s == 60:
        m, s = m + 1, 0
    return f"{m}:{s:02d}"


def _arrondi(v, n=1):
    return None if v is None else round(float(v), n)


def _sans_vide(d):
    """Retire les clés None / vides pour garder un dossier compact."""
    return {k: v for k, v in d.items() if v not in (None, [], {}, "")}


def _essayer(fonction, *args, **kwargs):
    try:
        return fonction(*args, **kwargs)
    except Exception:
        return None


def _athlete(athlete_id):
    from noyau.entrainement import metriques as met
    return _essayer(met._athlete, athlete_id) or {}


def _jour(texte):
    try:
        return date.fromisoformat(str(texte)[:10])
    except (ValueError, TypeError):
        return None


def zones_fc(fc_max):
    """[(nom, bpm_bas, bpm_haut)] — estimation à partir de la FC max."""
    if not fc_max:
        return []
    b = [round(fc_max * p) for p in BORNES_ZONES_PCT]
    return [(NOMS_ZONES[i], b[i], b[i + 1]) for i in range(5)]


def _zone_de(fc, bornes):
    for i in range(4, -1, -1):
        if fc >= bornes[i][1]:
            return i
    return None


def temps_par_zone_trace(points, fc_max):
    """Secondes par zone (liste de 5) d'après la FC point par point, ou None."""
    if not fc_max:
        return None
    zs = zones_fc(fc_max)
    sec = [0.0] * 5
    prec = None
    total = 0.0
    for p in points:
        if len(p) >= 5 and p[3] is not None and p[4] and p[4] > 40:
            if prec is not None:
                dt = p[3] - prec[0]
                if 0 < dt <= 30:
                    z = _zone_de(prec[1], zs)
                    if z is not None:
                        sec[z] += dt
                        total += dt
            prec = (p[3], p[4])
        else:
            prec = None
    return sec if total >= 120 else None


def _bloc_zones(sec, fc_max, methode):
    total = sum(sec)
    if not total:
        return None
    zs = zones_fc(fc_max)
    zones = []
    for i, s in enumerate(sec):
        if zs:
            zones.append({"zone": NOMS_ZONES[i], "bpm": f"{zs[i][1]}-{zs[i][2]}",
                          "min": round(s / 60, 1), "pct": round(s / total * 100)})
        else:
            zones.append({"zone": NOMS_ZONES[i], "min": round(s / 60, 1), "pct": round(s / total * 100)})
    facile = (sec[0] + sec[1]) / total * 100
    dur = (sec[3] + sec[4]) / total * 100
    return {"methode": methode, "zones": zones, "pct_facile_Z1_Z2": round(facile),
            "pct_intense_Z4_Z5": round(dur)}


def _type_de_seance(sec, cv_gap_pct):
    """Intention probable de la séance, déduite des chiffres (pas devinée par l'IA)."""
    if not sec or not sum(sec):
        return None
    t = sum(sec)
    facile = (sec[0] + sec[1]) / t
    dur = (sec[3] + sec[4]) / t
    if cv_gap_pct is not None and cv_gap_pct > 18 and dur >= 0.15:
        return "fractionné / séance à intensité variable"
    if facile >= 0.75:
        return "endurance fondamentale"
    if dur >= 0.35:
        return "séance au seuil / allure soutenue"
    if dur >= 0.15:
        return "endurance avec passages soutenus"
    return "endurance active / tempo (zone 3 dominante)"


# ----------------------------------------------------------------------
# Bloc trace GPS (allure ajustée, découplage, VAM, durabilité, pentes)
# ----------------------------------------------------------------------

def _bloc_trace(activite_id, fc_max):
    from noyau.entrainement import metriques as met
    from noyau.traces import analyse_traces as at
    from noyau.traces.dynamique_course import calculer_decouplage_cardiaque, calculer_cadence_moyenne

    points = met.trace_de_activite(activite_id)
    if len(points) < 20:
        return None, None
    res = {}
    sec = temps_par_zone_trace(points, fc_max)
    cv = None

    analyse = _essayer(at.analyser_sortie, activite_id, points)
    if analyse:
        gap = analyse.get("gap")
        if gap:
            splits = gap.get("splits") or []
            gaps = [s["allure_ajustee"] for s in splits if s.get("allure_ajustee")]
            regul = None
            if len(gaps) >= 3:
                moy = statistics.mean(gaps)
                cv = statistics.pstdev(gaps) / moy * 100 if moy else None
                moitie = len(gaps) // 2
                a, b = statistics.mean(gaps[:moitie]), statistics.mean(gaps[moitie:])
                regul = {
                    "variabilite_allure_ajustee_pct": _arrondi(cv, 1),
                    "1re_moitie": _txt_allure(a), "2e_moitie": _txt_allure(b),
                    "profil": "split négatif (2e moitié plus rapide)" if b < a - 0.05 else
                              "split positif (2e moitié plus lente)" if b > a + 0.05 else "allure régulière",
                    "ecart_moitiés_s_km": round((b - a) * 60),
                }
            # Détail kilomètre par kilomètre (compressé au-delà de 20 km).
            pas = 1 if len(splits) <= 20 else 5
            detail = []
            for i in range(0, len(splits), pas):
                bloc = splits[i:i + pas]
                fcs = [s["fc"] for s in bloc if s.get("fc")]
                detail.append(_sans_vide({
                    "km": f"{bloc[0]['km']}" if pas == 1 else f"{bloc[0]['km']}-{bloc[-1]['km']}",
                    "allure": _txt_allure(statistics.mean(s["allure"] for s in bloc)),
                    "allure_ajustee": _txt_allure(statistics.mean(s["allure_ajustee"] for s in bloc)),
                    "d_plus_m": sum(s.get("d_plus") or 0 for s in bloc),
                    "fc": round(statistics.mean(fcs)) if fcs else None,
                }))
            res["allure_ajustee_pente"] = _sans_vide({
                "allure_reelle": _txt_allure(gap.get("allure")),
                "allure_ajustee_GAP": _txt_allure(gap.get("allure_ajustee")),
                "gain_du_a_la_pente_pct": gap.get("gain_pct"),
                "regularite": regul, "detail": detail,
            })
        mont = sorted(analyse.get("montees") or [], key=lambda m: -m.get("gain_m", 0))[:4]
        if mont:
            res["montees_principales"] = [_sans_vide({
                "km_debut": m["km_debut"], "gain_m": m["gain_m"], "pente_moy_pct": m["pente_pct"],
                "duree_min": round(m["duree_s"] / 60, 1) if m.get("duree_s") else None,
                "VAM_m_h": m.get("vam"), "categorie": m.get("categorie"),
            }) for m in mont]
            vams = [m["vam"] for m in analyse["montees"] if m.get("vam") and m.get("gain_m", 0) >= 80]
            if vams:
                res["VAM_moyenne_montees_>=80m"] = round(statistics.mean(vams))
        dur = analyse.get("durabilite")
        if dur:
            res["durabilite_efficacite_par_bloc_30min"] = {
                "baisse_finale_pct": dur["baisse_finale_pct"],
                "blocs_pct_vs_1er_bloc": [b["pct"] for b in dur["blocs"]],
            }
        eff = analyse.get("efficacite")
        if eff:
            res["efficacite_course"] = _sans_vide({
                "m_ajustes_par_battement": _arrondi(eff.get("m_par_battement"), 2),
                "fc_moyenne_utile": round(eff["fc_moy"]) if eff.get("fc_moy") else None,
            })
        pente = at.resume_pente(analyse["pente"]) if analyse.get("pente") else []
        if pente:
            res["repartition_par_pente"] = [_sans_vide({
                "classe": p["classe"], "part_distance_pct": p["part_distance_pct"],
                "allure": _txt_allure(1000 / (p["vitesse_kmh"] / 3.6) / 60) if p.get("vitesse_kmh") else None,
                "fc": p.get("fc"),
            }) for p in pente]

    dec = _essayer(calculer_decouplage_cardiaque, points)
    if dec:
        res["decouplage_cardiaque_Pa_Hr"] = {
            "pct": dec["decouplage_pct"], "FC_1re_moitie": dec["fc_premiere"], "FC_2e_moitie": dec["fc_seconde"],
            "vitesse_1re_kmh": dec["vitesse_premiere_kmh"], "vitesse_2e_kmh": dec["vitesse_seconde_kmh"],
        }
    cad = _essayer(calculer_cadence_moyenne, points)
    if cad:
        res["cadence_spm"] = cad["cadence_spm"]
    return res, sec


# ----------------------------------------------------------------------
# Contexte au jour J (charge, fraîcheur, récupération)
# ----------------------------------------------------------------------

def _charge_et_fraicheur(athlete_id, jour):
    """Fitness / fatigue / fraîcheur (TSB) le jour de la séance, charge des 7 et 28
    jours précédents et variation hebdomadaire — tout 'à la date', pas 'aujourd'hui'."""
    from noyau.entrainement.coach import calculer_serie_forme
    from noyau.entrainement import metriques as met

    ecart = (date.today() - jour).days
    res = {}
    serie = _essayer(calculer_serie_forme, athlete_id, max(60, ecart + 45)) or []
    point = next((s for s in serie if str(s["date"])[:10] == jour.isoformat()), None)
    if point:
        res["fitness_CTL"] = point["fitness"]
        res["fatigue_ATL"] = point["fatigue"]
        res["fraicheur_TSB"] = point["forme"]
    charges = dict(_essayer(met.charges_par_jour, athlete_id, ecart + 60) or [])
    def somme(a, b):  # jours [jour-a, jour-b] inclus
        return round(sum(charges.get(jour - timedelta(days=k), 0.0) for k in range(b, a + 1)), 1)
    c7, c7p, c28 = somme(7, 1), somme(14, 8), somme(28, 1)
    res["charge_7j_avant"] = c7
    res["charge_7j_precedents"] = c7p
    if c7p >= 30:
        res["variation_hebdo_pct"] = round((c7 - c7p) / c7p * 100)
    res["charge_moyenne_hebdo_28j"] = round(c28 / 4, 1)
    jours7 = [charges.get(jour - timedelta(days=k), 0.0) for k in range(1, 8)]
    if len(jours7) == 7 and statistics.pstdev(jours7) > 0 and c7 > 0:
        mono = statistics.mean(jours7) / statistics.pstdev(jours7)
        res["monotonie_7j"] = round(mono, 2)
        res["contrainte_7j"] = round(c7 * mono)
    return res


def _recuperation_a_la_date(athlete_id, jour):
    """HRV, FC de repos, sommeil, Body Battery vers le jour J (7 jours avant inclus)."""
    conn = connexion()
    cur = conn.cursor()
    cur.execute(
        "SELECT date, fc_repos, hrv_nuit_ms, hrv_statut, sommeil_duree_h, sommeil_score, "
        "sommeil_profond_min, sommeil_paradoxal_min, body_battery_max, stress_moyen "
        "FROM recuperation_quotidienne WHERE athlete_id=? AND date>=? AND date<=? ORDER BY date",
        (athlete_id, (jour - timedelta(days=40)).isoformat(), jour.isoformat()),
    )
    lignes = cur.fetchall()
    conn.close()
    if not lignes:
        return None
    def col(i, depuis):
        return [r[i] for r in lignes if r[i] is not None and r[0] >= depuis.isoformat()]
    d7, d3, d28 = jour - timedelta(days=7), jour - timedelta(days=2), jour - timedelta(days=35)
    res = {}
    hrv7 = col(2, d7)
    hrv_ref = [r[2] for r in lignes if r[2] is not None and r[0] < d7.isoformat()]
    if hrv7:
        res["HRV_nuit_moy_7j_ms"] = round(statistics.mean(hrv7))
        if len(hrv_ref) >= 7:
            m, sd = statistics.mean(hrv_ref), statistics.pstdev(hrv_ref)
            res["HRV_base_28j_ms"] = f"{round(m - sd)}-{round(m + sd)}"
            res["HRV_vs_base"] = "sous la bande" if statistics.mean(hrv7) < m - sd else \
                                 "au-dessus de la bande" if statistics.mean(hrv7) > m + sd else "dans la bande"
    fc3 = col(1, d3)
    fc_ref = [r[1] for r in lignes if r[1] is not None and r[0] < d3.isoformat()]
    if fc3:
        res["FC_repos_3j_bpm"] = round(statistics.mean(fc3), 1)
        if len(fc_ref) >= 5:
            res["FC_repos_ecart_vs_base_bpm"] = round(statistics.mean(fc3) - statistics.median(fc_ref), 1)
    som = col(4, d7)
    if som:
        res["sommeil_moy_7j_h"] = round(statistics.mean(som), 1)
        res["derniere_nuit_h"] = som[-1]
    sc = col(5, d7)
    if sc:
        res["score_sommeil_moy_7j"] = round(statistics.mean(sc))
    bb = col(8, d3)
    if bb:
        res["body_battery_max_moy_3j"] = round(statistics.mean(bb))
    st = col(9, d7)
    if st:
        res["stress_moy_7j"] = round(statistics.mean(st))
    return res or None


def _capacites(athlete_id, fc_max, fc_repos):
    """VMA, VO₂max récent et allures de référence (estimations)."""
    res = {}
    try:
        from noyau.entrainement.vma import calculer_vma, allure_texte
        v = calculer_vma(athlete_id)
        if v and v.get("actuelle"):
            vma = v["actuelle"]
            res["VMA_estimee_kmh"] = round(vma, 1)
            res["allures_de_reference_estimees"] = {
                "endurance_65%VMA": allure_texte(vma * 0.65), "marathon_75%": allure_texte(vma * 0.75),
                "seuil_85%": allure_texte(vma * 0.85), "10km_90%": allure_texte(vma * 0.90),
            }
    except Exception:
        pass
    try:
        from noyau.entrainement.vo2max import estimer_vo2max_recent
        v = estimer_vo2max_recent(athlete_id, 180)
        if v:
            res["VO2max_estime_6mois"] = v["vo2max"]
    except Exception:
        pass
    if fc_max:
        res["FC_max_bpm"] = fc_max
        res["zones_FC_estimees"] = {n: f"{b}-{h} bpm" for n, b, h in zones_fc(fc_max)}
    if fc_repos:
        res["FC_repos_athlete"] = fc_repos
    return res


def _poids_recent(athlete_id):
    try:
        from noyau.entrainement import metriques as met
        r = met.resume_poids_recuperation(athlete_id)
        if r.get("moy7") is None:
            return None
        return _sans_vide({"poids_moy_7j_kg": r["moy7"], "ecart_vs_7j_avant_kg": r.get("ecart7")})
    except Exception:
        return None


def _garmin_du_jour(athlete_id, jour):
    conn = connexion()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT readiness_score, readiness_niveau, statut_entrainement, vo2max FROM garmin_quotidien "
            "WHERE athlete_id=? AND date<=? AND date>=? AND (readiness_score IS NOT NULL OR statut_entrainement IS NOT NULL "
            "OR vo2max IS NOT NULL) ORDER BY date DESC LIMIT 1",
            (athlete_id, jour.isoformat(), (jour - timedelta(days=7)).isoformat()),
        )
        r = cur.fetchone()
    except Exception:
        return None
    finally:
        conn.close()
    if not r:
        return None
    return _sans_vide({"disponibilite_entrainement_montre": r[0], "niveau": r[1],
                       "statut_entrainement_montre": r[2], "VO2max_montre": r[3]})


# ----------------------------------------------------------------------
# Comparaison avec des sorties similaires
# ----------------------------------------------------------------------

def _indice_efficacite(distance_km, duree_s, denivele_m, fc):
    """Vitesse « plate équivalente » (km-effort/h) ÷ FC × 100 : plus c'est haut, plus
    on va vite pour un même coût cardiaque. Comparable entre sorties de même type."""
    if not (distance_km and duree_s and fc):
        return None
    km_effort = distance_km + (denivele_m or 0) / 100.0
    return km_effort / (duree_s / 3600.0) / fc * 100.0


def _comparaison_similaires(athlete_id, type_, jour, distance, duree, denivele, fc_moy):
    if type_ not in TYPES_COURSE or not distance:
        return None
    conn = connexion()
    cur = conn.cursor()
    cur.execute(
        "SELECT date, distance, duree, denivele, frequence_cardiaque_moyenne, allure_moyenne FROM activites "
        "WHERE athlete_id=? AND type=? AND distance BETWEEN ? AND ? AND date<? AND duree>0 "
        "ORDER BY date DESC LIMIT 40",
        (athlete_id, type_, distance * 0.7, distance * 1.3, jour.isoformat()),
    )
    lignes = cur.fetchall()
    conn.close()
    sim = []
    for d, di, du, de, fc, al in lignes:
        dj = _jour(d)
        if not dj or (jour - dj).days > 365:
            continue
        sim.append((dj, di, du, de or 0, fc, al))
        if len(sim) >= 6:
            break
    if len(sim) < 2:
        return None
    ef_ici = _indice_efficacite(distance, duree, denivele, fc_moy)
    efs = [e for e in (_indice_efficacite(di, du, de, fc) for _, di, du, de, fc, _ in sim) if e]
    res = {"nb_sorties_comparees": len(sim),
           "periode": f"{sim[-1][0].strftime('%d/%m/%Y')} au {sim[0][0].strftime('%d/%m/%Y')}"}
    vit = [di / (du / 3600.0) for _, di, du, _, _, _ in sim]
    ici = distance / (duree / 3600.0)
    res["vitesse_moy_ici_kmh"] = round(ici, 2)
    res["vitesse_moy_similaires_kmh"] = round(statistics.mean(vit), 2)
    fcs = [x[4] for x in sim if x[4]]
    if fc_moy and fcs:
        res["FC_ici"] = round(fc_moy)
        res["FC_similaires"] = round(statistics.mean(fcs))
    if ef_ici and efs:
        ref = statistics.mean(efs)
        res["indice_efficacite_ici"] = round(ef_ici, 2)
        res["indice_efficacite_similaires"] = round(ref, 2)
        res["efficacite_vs_similaires_pct"] = round((ef_ici / ref - 1) * 100, 1)
    return res


# ----------------------------------------------------------------------
# DOSSIER D'UNE SORTIE
# ----------------------------------------------------------------------

def dossier_sortie(activite_id, athlete_id):
    """Dossier technique d'une sortie. Toujours un dict (possiblement presque vide)."""
    conn = connexion()
    cur = conn.cursor()
    cur.execute(
        "SELECT date, type, distance, denivele, denivele_negatif, duree, vitesse_moyenne, "
        "frequence_cardiaque_moyenne, frequence_cardiaque_max, cadence_moyenne, temperature_moyenne, "
        "temps_zone_1, temps_zone_2, temps_zone_3, temps_zone_4, temps_zone_5, calories "
        "FROM activites WHERE id=? AND athlete_id=?", (activite_id, athlete_id))
    r = cur.fetchone()
    conn.close()
    if not r:
        return {}
    (date_t, type_, dist, dplus, dmoins, duree, vit, fc_moy, fc_max_act, cad, temp,
     z1, z2, z3, z4, z5, cal) = r
    dist, dplus, duree = dist or 0, dplus or 0, duree or 0
    jour = _jour(date_t) or date.today()
    ath = _athlete(athlete_id)
    fc_max = ath.get("fc_max") or fc_max_act
    dossier = {}

    # --- Effort global
    effort = {}
    if dist:
        effort["km_effort"] = round(dist + dplus / 100.0, 1)
        effort["D+_par_km"] = round(dplus / dist)
        effort["D+_en_pct_de_la_distance"] = round(dplus / (dist * 1000) * 100, 1)
    if duree and dplus:
        effort["D+_par_heure_m"] = round(dplus / (duree / 3600.0))
    if duree and dist:
        effort["vitesse_equivalente_plat_kmh"] = round((dist + dplus / 100.0) / (duree / 3600.0), 2)
    if temp is not None:
        effort["temperature_C"] = round(temp, 1)
    if fc_moy and fc_max:
        effort["FC_moyenne_pct_FCmax"] = round(fc_moy / fc_max * 100)
    if effort:
        dossier["effort"] = effort

    # --- Trace + zones
    trace, sec = (_essayer(_bloc_trace, activite_id, fc_max) or (None, None))
    methode_zones = "trace FC point par point"
    if sec is None and any((z1, z2, z3, z4, z5)):
        sec = [float(z or 0) for z in (z1, z2, z3, z4, z5)]
        methode_zones = "zones enregistrées par la montre"
    if sec:
        bz = _bloc_zones(sec, fc_max, methode_zones)
        if bz:
            dossier["zones_FC"] = bz
    if trace:
        dossier["trace"] = trace
        cv = (((trace.get("allure_ajustee_pente") or {}).get("regularite") or {})
              .get("variabilite_allure_ajustee_pct"))
    else:
        cv = None
        dossier["trace_absente"] = "pas de trace GPS exploitable : seules les valeurs globales sont disponibles"
    if sec:
        t = _type_de_seance(sec, cv)
        if t:
            dossier["nature_probable_de_la_seance"] = t

    comp = _essayer(_comparaison_similaires, athlete_id, type_, jour, dist, duree, dplus, fc_moy)
    if comp:
        dossier["comparaison_sorties_similaires"] = comp

    forme = _essayer(_charge_et_fraicheur, athlete_id, jour)
    if forme:
        dossier["charge_et_fraicheur_au_jour_J"] = forme
    rec = _essayer(_recuperation_a_la_date, athlete_id, jour)
    if rec:
        dossier["recuperation_avant_la_seance"] = rec
    g = _garmin_du_jour(athlete_id, jour)
    if g:
        dossier["indicateurs_montre"] = g
    cap = _capacites(athlete_id, ath.get("fc_max"), ath.get("fc_repos"))
    if cap:
        dossier["capacites_estimees"] = cap
    poids = _poids_recent(athlete_id)
    if poids:
        dossier["poids"] = poids
    return dossier


# ----------------------------------------------------------------------
# DOSSIER D'UNE PÉRIODE
# ----------------------------------------------------------------------

def _bloc_volume(sorties):
    course = [s for s in sorties if s["type"] in TYPES_COURSE and s["distance"] >= 1 and s["duree"] > 0]
    dist = sum(s["distance"] for s in sorties)
    dplus = sum(s["denivele"] for s in sorties)
    duree = sum(s["duree"] for s in sorties)
    res = {"sorties": len(sorties), "km": round(dist, 1), "D+_m": round(dplus),
           "heures": round(duree / 3600.0, 1), "km_effort": round(dist + dplus / 100.0, 1)}
    if course:
        dc = sum(s["distance"] for s in course)
        du = sum(s["duree"] for s in course)
        dp = sum(s["denivele"] for s in course)
        res["course_km"] = round(dc, 1)
        if dc and du:
            res["course_vitesse_equiv_plat_kmh"] = round((dc + dp / 100.0) / (du / 3600.0), 2)
        longues = [s for s in course if s["duree"] >= 7200 or s["distance"] >= 20]
        res["sorties_longues_>=2h_ou_20km"] = len(longues)
        if longues:
            res["plus_longue"] = f"{max(s['distance'] for s in longues):.1f} km"
    return res


def _tendance_efficacite(sorties):
    """Indice d'efficacité 1re moitié vs 2e moitié de la période (sorties de course avec FC)."""
    pts = []
    for s in sorties:
        if s["type"] in TYPES_COURSE and s["distance"] >= 5 and s["duree"] > 0 and s.get("fc_moy"):
            e = _indice_efficacite(s["distance"], s["duree"], s["denivele"], s["fc_moy"])
            if e:
                pts.append(e)
    if len(pts) < 4:
        return None
    m = len(pts) // 2
    a, b = statistics.mean(pts[:m]), statistics.mean(pts[m:])
    return {"nb_sorties": len(pts), "indice_1re_moitie": round(a, 2), "indice_2e_moitie": round(b, 2),
            "evolution_pct": round((b / a - 1) * 100, 1)}


def dossier_periode(athlete_id, debut, fin):
    """Dossier technique d'une période [debut, fin] (dates)."""
    from noyau.entrainement import metriques as met

    ath = _athlete(athlete_id)
    fc_max = ath.get("fc_max") or 185
    duree_j = (fin - debut).days + 1
    sorties = _essayer(met.activites_periode, athlete_id, debut, fin) or []
    prec_fin = debut - timedelta(days=1)
    prec_debut = prec_fin - timedelta(days=duree_j - 1)
    precedentes = _essayer(met.activites_periode, athlete_id, prec_debut, prec_fin) or []

    dossier = {"volume": _bloc_volume(sorties), "volume_periode_precedente": _bloc_volume(precedentes)}

    # Répartition d'intensité (temps facile / dur) sur la période.
    f = d = 0.0
    methodes = {}
    for s in sorties:
        a, b, m = _essayer(met._secondes_facile_dur, s, fc_max) or (0, 0, None)
        if m:
            methodes[m] = methodes.get(m, 0) + 1
            f, d = f + a, d + b
    if f + d > 0:
        dossier["repartition_intensite"] = {
            "pct_temps_facile_sous_80%FCmax": round(f / (f + d) * 100),
            "heures_faciles": round(f / 3600.0, 1), "heures_soutenues": round(d / 3600.0, 1),
            "seuil_facile_bpm": round(fc_max * 0.8), "reference": "≈ 80 % de temps facile visé (modèle polarisé)",
            "source": methodes,
        }
    # Zones agrégées (quand la montre enregistre le temps par zone).
    zsec = [sum((s.get(f"z{k}") or 0) for s in sorties) for k in range(1, 6)]
    if sum(zsec):
        bz = _bloc_zones(zsec, fc_max, "zones enregistrées par la montre")
        if bz:
            dossier["zones_FC_cumulees"] = bz

    eff = _tendance_efficacite(sorties)
    if eff:
        dossier["tendance_efficacite"] = eff

    # Semaine par semaine (8 dernières semaines finissant à `fin`).
    try:
        sem = met.charges_hebdo(athlete_id, 8)
        hausse = {s["lundi"]: s for s in met.hausse_charge_hebdo(athlete_id, 8)}
        mono = {s["lundi"]: s for s in met.monotonie_contrainte(athlete_id, 8)}
        dossier["semaines_recentes"] = [_sans_vide({
            "semaine_du": s["lundi"].strftime("%d/%m"), "sorties": s["nb_sorties"], "km": s["distance"],
            "D+_m": round(s["denivele"]), "heures": s["duree_h"], "charge": s["charge"],
            "variation_charge_pct": hausse.get(s["lundi"], {}).get("variation_pct"),
            "monotonie": mono.get(s["lundi"], {}).get("monotonie"),
            "en_cours": s["partielle"] or None,
        }) for s in sem]
    except Exception:
        pass

    forme = _essayer(_charge_et_fraicheur, athlete_id, min(fin, date.today()))
    if forme:
        dossier["charge_et_fraicheur_fin_de_periode"] = forme
    debut_forme = _essayer(_charge_et_fraicheur, athlete_id, debut)
    if debut_forme and forme:
        dossier["evolution_fitness_CTL"] = {"debut": debut_forme.get("fitness_CTL"), "fin": forme.get("fitness_CTL")}
    rec = _essayer(_recuperation_a_la_date, athlete_id, min(fin, date.today()))
    if rec:
        dossier["recuperation_fin_de_periode"] = rec

    # Meilleurs efforts de course de la période.
    course = [s for s in sorties if s["type"] in TYPES_COURSE and s["distance"] >= 5 and s["duree"] > 0]
    top = sorted(course, key=lambda s: -(s["distance"] + s["denivele"] / 100.0))[:3]
    if top:
        dossier["plus_gros_efforts"] = [_sans_vide({
            "date": s["date"][:10], "km": round(s["distance"], 1), "D+_m": round(s["denivele"]),
            "duree": f"{int(s['duree'] // 3600)}h{int(s['duree'] % 3600 // 60):02d}",
            "FC_moy": round(s["fc_moy"]) if s.get("fc_moy") else None,
        }) for s in top]

    cap = _capacites(athlete_id, ath.get("fc_max"), ath.get("fc_repos"))
    if cap:
        dossier["capacites_estimees"] = cap
    poids = _poids_recent(athlete_id)
    if poids:
        dossier["poids"] = poids
    try:
        courses = met.courses_a_venir(athlete_id)[:3]
        if courses:
            dossier["courses_a_venir"] = [{"nom": c["nom"], "date": str(c["date"]), "km": c.get("distance_km"),
                                           "D+_m": c.get("denivele_m")} for c in courses]
    except Exception:
        pass
    return dossier


# ----------------------------------------------------------------------
# LÉGENDE donnée à l'IA (définitions + repères d'interprétation)
# ----------------------------------------------------------------------

LEGENDE = """\
DÉFINITIONS (pour interpréter le JSON) :
- km_effort = distance + D+/100. vitesse_equivalente_plat = km_effort / durée.
- allure_ajustee_GAP = allure équivalente sur le plat (modèle de coût énergétique de Minetti) ; gain_du_a_la_pente_pct = surcoût de la pente.
- decouplage_cardiaque_Pa_Hr = baisse de l'efficacité (vitesse/FC) entre 1re et 2e moitié de la sortie. Repères : < 5 % très bon ; 5-8 % correct ; > 8 % limite aérobie ou fatigue/chaleur/déshydratation. Peu fiable si la sortie dure < 60 min ou si le terrain change beaucoup entre les moitiés.
- VAM_m_h = vitesse ascensionnelle (D+ par heure) dans une montée. Repères trail : 600-800 m/h endurance, 900-1100 soutenu, > 1200 très rapide.
- durabilite = efficacité par bloc de 30 min relative au 1er bloc : une baisse finale > 8-10 % signale un manque de résistance à la fatigue.
- efficacite_course = mètres équivalents-plat par battement ; indice_efficacite = km_effort/h ÷ FC × 100 (comparable entre sorties de même type).
- zones_FC : % FCmax (Z1 50-60, Z2 60-70, Z3 70-80, Z4 80-90, Z5 90-100). Modèle polarisé : ~80 % du temps en Z1-Z2.
- CTL = fitness (charge moyenne pondérée 42 j), ATL = fatigue (7 j), TSB = fraîcheur = CTL - ATL. Repères : TSB > +10 frais ; -10 à -25 zone d'entraînement productive ; < -30 risque de surcharge.
- monotonie_7j (Foster) : > 2 = semaine trop uniforme (risque) ; hausse hebdo de charge : > 10 % prudence, > 25 % risque.
- HRV_vs_base : sous la bande = récupération incomplète. FC_repos_ecart_vs_base_bpm : >= +3 attention, >= +5 alerte.
- ESTIMATIONS (à dire comme telles) : zones en % FCmax, VMA, VO2max, allures de référence, GAP, nature_probable_de_la_seance.
"""
