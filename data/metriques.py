"""
Calculs de la v98 — santé, charge et performance. Aucun widget ici : que
des fonctions qui lisent la base et renvoient des listes / dictionnaires,
pour pouvoir les tester sans interface et les réutiliser dans plusieurs
écrans (Aujourd'hui, Analyses, Rapport PDF, page téléphone…).

Règle de fond : jamais de valeur inventée. Quand une donnée manque (pas
de montre ce jour-là, pas de météo, pas de FC…), la fonction le dit
(`None`, liste vide ou champ « manque ») au lieu de combler avec une
estimation cachée.
"""

import json
import math
import statistics
from datetime import date, datetime, timedelta

from data.database import connexion, obtenir_parametre, definir_parametre


# ======================================================================
# OUTILS COMMUNS
# ======================================================================

def _jour(texte):
    """'2026-10-19 07:55:39' / '2026-10-19' -> date, sinon None."""
    if not texte:
        return None
    try:
        return date.fromisoformat(str(texte)[:10])
    except ValueError:
        return None


def _datetime(texte):
    if not texte:
        return None
    t = str(texte).replace("T", " ")[:19]
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(t, fmt)
        except ValueError:
            continue
    return None


def lundi_de(jour):
    return jour - timedelta(days=jour.weekday())


def _athlete(athlete_id):
    conn = connexion()
    cur = conn.cursor()
    cur.execute("SELECT fc_repos, fc_max, sexe, poids, vma, taille, age FROM athletes WHERE id=?", (athlete_id,))
    r = cur.fetchone()
    conn.close()
    if not r:
        return {}
    return dict(zip(("fc_repos", "fc_max", "sexe", "poids", "vma", "taille", "age"), r))


def activites_periode(athlete_id, depuis, jusqu_a=None, types=None):
    """Sorties (dicts) entre deux dates incluses, de la plus ancienne à
    la plus récente. `types` : liste de types à garder (None = tous)."""
    jusqu_a = jusqu_a or date.today()
    conn = connexion()
    cur = conn.cursor()
    cur.execute(
        "SELECT id, date, nom, type, distance, denivele, denivele_negatif, duree, "
        "frequence_cardiaque_moyenne, frequence_cardiaque_max, vitesse_moyenne, allure_moyenne, "
        "cadence_moyenne, temperature_moyenne, temps_zone_1, temps_zone_2, temps_zone_3, "
        "temps_zone_4, temps_zone_5 FROM activites WHERE athlete_id=? AND date>=? AND date<? "
        "ORDER BY date",
        (athlete_id, depuis.isoformat(), (jusqu_a + timedelta(days=1)).isoformat()),
    )
    cles = ("id", "date", "nom", "type", "distance", "denivele", "denivele_negatif", "duree",
            "fc_moy", "fc_max", "vitesse", "allure", "cadence", "temperature",
            "z1", "z2", "z3", "z4", "z5")
    lignes = []
    for r in cur.fetchall():
        d = dict(zip(cles, r))
        d["jour"] = _jour(d["date"])
        d["distance"] = d["distance"] or 0
        d["denivele"] = d["denivele"] or 0
        d["duree"] = d["duree"] or 0
        if types and d["type"] not in types:
            continue
        lignes.append(d)
    conn.close()
    return lignes


def trace_de_activite(activite_id):
    """Points [lat, lon, alt, t, fc, (cad)] de la sortie, ou []."""
    conn = connexion()
    cur = conn.cursor()
    cur.execute("SELECT trace_json FROM parcours_gpx WHERE activite_id=? AND trace_json IS NOT NULL LIMIT 1",
                (activite_id,))
    r = cur.fetchone()
    conn.close()
    if not r:
        return []
    try:
        pts = json.loads(r[0])
    except (ValueError, TypeError):
        return []
    return pts if isinstance(pts, list) else []


def charges_par_jour(athlete_id, nb_jours):
    """[(date, charge)] du plus ancien au plus récent (coach.py)."""
    from interface.coach import obtenir_charges_journalieres
    return obtenir_charges_journalieres(athlete_id, nb_jours=nb_jours)


def _mediane(valeurs):
    valeurs = [v for v in valeurs if v is not None]
    return statistics.median(valeurs) if valeurs else None


def _moyenne(valeurs):
    valeurs = [v for v in valeurs if v is not None]
    return sum(valeurs) / len(valeurs) if valeurs else None


# ======================================================================
# S2 — DETTE DE SOMMEIL
# ======================================================================

def serie_sommeil(athlete_id, nb_jours=60):
    """{date: {'heures': h, 'origine': 'montre'|'saisie'|'estime'}} —
    la montre prime sur la saisie ; les lignes remplies automatiquement
    d'après le rythme habituel sont marquées « estime »."""
    fin = date.today()
    debut = (fin - timedelta(days=nb_jours)).isoformat()
    res = {}
    conn = connexion()
    cur = conn.cursor()
    try:
        cur.execute("SELECT date, duree_heures, notes FROM sommeil WHERE athlete_id=? AND date>=? AND duree_heures IS NOT NULL",
                    (athlete_id, debut))
        for d, h, notes in cur.fetchall():
            j = _jour(d)
            if j:
                estime = (notes or "").startswith("Rempli automatiquement")
                res[j] = {"heures": float(h), "origine": "estime" if estime else "saisie"}
    except Exception:
        pass
    try:
        cur.execute("SELECT date, sommeil_duree_h FROM recuperation_quotidienne WHERE athlete_id=? AND date>=? "
                    "AND sommeil_duree_h IS NOT NULL", (athlete_id, debut))
        for d, h in cur.fetchall():
            j = _jour(d)
            if j:
                res[j] = {"heures": float(h), "origine": "montre"}
    except Exception:
        pass
    conn.close()
    return res


def dette_sommeil(athlete_id, nb_jours=14, objectif=None):
    """Dette = somme (objectif − dormi) sur les `nb_jours` derniers jours
    mesurés ; les nuits longues effacent les courtes (plancher à 0)."""
    from interface.coach import obtenir_objectif_sommeil_heures
    objectif = objectif or obtenir_objectif_sommeil_heures()
    serie = serie_sommeil(athlete_id, nb_jours + 30)
    limite = date.today() - timedelta(days=nb_jours - 1)
    jours = sorted(j for j in serie if j >= limite)
    cumul, courbe = 0.0, []
    for j in jours:
        cumul = max(0.0, cumul + objectif - serie[j]["heures"])
        courbe.append((j, round(cumul, 1)))
    mesures = [serie[j]["heures"] for j in jours]
    origines = [serie[j]["origine"] for j in jours]
    dette = courbe[-1][1] if courbe else None
    niveau = None
    if dette is not None:
        niveau = "ok" if dette < 3 else "attention" if dette < 7 else "forte"
    return {
        "objectif": objectif, "dette_h": dette, "niveau": niveau, "courbe": courbe,
        "moyenne_h": round(_moyenne(mesures), 1) if mesures else None,
        "nb_jours": len(jours), "nb_estimes": origines.count("estime"),
        "serie": [(j, serie[j]["heures"]) for j in jours],
    }


# ======================================================================
# S3 — HRV AVEC BANDE NORMALE ; S4 — FC DE REPOS
# ======================================================================

def _serie_recup(athlete_id, colonne, nb_jours):
    debut = (date.today() - timedelta(days=nb_jours)).isoformat()
    conn = connexion()
    cur = conn.cursor()
    res = {}
    try:
        cur.execute(f"SELECT date, {colonne} FROM recuperation_quotidienne WHERE athlete_id=? AND date>=? "
                    f"AND {colonne} IS NOT NULL ORDER BY date", (athlete_id, debut))
        for d, v in cur.fetchall():
            j = _jour(d)
            if j:
                res[j] = float(v)
    except Exception:
        pass
    if colonne == "hrv_nuit_ms":  # repli : signaux importés depuis un .FIT
        try:
            cur.execute("SELECT date, hrv_ms FROM signaux_recuperation WHERE athlete_id=? AND date>=? "
                        "AND hrv_ms IS NOT NULL ORDER BY date", (athlete_id, debut))
            for d, v in cur.fetchall():
                j = _jour(d)
                if j and j not in res:
                    res[j] = float(v)
        except Exception:
            pass
    conn.close()
    return res


def hrv_avec_bande(athlete_id, nb_jours=90):
    """HRV de nuit + bande « normale » = moyenne mobile 28 j ± 1 écart-type
    (calculée sur les jours mesurés AVANT chaque jour). Statut d'après la
    moyenne des 7 derniers jours mesurés."""
    serie = _serie_recup(athlete_id, "hrv_nuit_ms", nb_jours + 28)
    jours = sorted(serie)
    points = []
    for j in jours:
        if j < date.today() - timedelta(days=nb_jours):
            continue
        ref = [serie[k] for k in jours if j - timedelta(days=28) <= k < j]
        if len(ref) >= 7:
            m = statistics.mean(ref)
            sd = statistics.pstdev(ref)
            sd = max(sd, m * 0.05)
            points.append((j, serie[j], m - sd, m + sd))
        else:
            points.append((j, serie[j], None, None))
    statut, moy7, bande = None, None, None
    mesures = [serie[j] for j in jours[-7:]]
    if mesures:
        moy7 = statistics.mean(mesures)
        dernier = next((p for p in reversed(points) if p[2] is not None), None)
        if dernier:
            bande = (dernier[2], dernier[3])
            statut = "basse" if moy7 < bande[0] else "haute" if moy7 > bande[1] else "equilibree"
    return {"points": points, "moyenne_7j": moy7, "bande": bande, "statut": statut,
            "nb_mesures": len(serie)}


def fc_repos_et_alerte(athlete_id, nb_jours=90):
    """FC de repos quotidienne, base habituelle (médiane 30 j avant les 3
    derniers jours) et alerte si les 3 derniers jours dépassent la base."""
    serie = _serie_recup(athlete_id, "fc_repos", nb_jours + 30)
    jours = sorted(serie)
    points = [(j, serie[j]) for j in jours if j >= date.today() - timedelta(days=nb_jours)]
    recents = jours[-3:]
    base = None
    ecart, niveau = None, None
    if recents:
        avant = [serie[j] for j in jours if j < recents[0] and j >= recents[0] - timedelta(days=30)]
        if len(avant) >= 5:
            base = statistics.median(avant)
            ecart = statistics.mean(serie[j] for j in recents) - base
            niveau = "alerte" if ecart >= 5 else "attention" if ecart >= 3 else "ok"
    return {"points": points, "base": base, "ecart": ecart, "niveau": niveau,
            "derniere": serie[jours[-1]] if jours else None, "nb_mesures": len(serie)}


# ======================================================================
# S5 — MONOTONIE & CONTRAINTE ; S6 — HAUSSE DE CHARGE PAR SEMAINE
# ======================================================================

def charges_hebdo(athlete_id, nb_semaines=12):
    """Semaines (lundi→dimanche) avec charge totale, charges par jour,
    distance et D+. La semaine en cours est marquée `partielle`."""
    aujourd_hui = date.today()
    debut = lundi_de(aujourd_hui) - timedelta(weeks=nb_semaines - 1)
    nb_jours = (aujourd_hui - debut).days + 1
    par_jour = dict(charges_par_jour(athlete_id, nb_jours))
    sorties = activites_periode(athlete_id, debut, aujourd_hui)
    semaines = []
    for i in range(nb_semaines):
        lundi = debut + timedelta(weeks=i)
        jours = [lundi + timedelta(days=k) for k in range(7)]
        valides = [j for j in jours if j <= aujourd_hui]
        charges = [par_jour.get(j, 0.0) for j in valides]
        s_sem = [s for s in sorties if s["jour"] and lundi <= s["jour"] < lundi + timedelta(days=7)]
        semaines.append({
            "lundi": lundi, "charges": charges, "charge": round(sum(charges), 1),
            "partielle": len(valides) < 7,
            "distance": round(sum(s["distance"] for s in s_sem), 1),
            "denivele": sum(s["denivele"] for s in s_sem),
            "duree_h": round(sum(s["duree"] for s in s_sem) / 3600, 2),
            "nb_sorties": len(s_sem),
        })
    return semaines


def monotonie_contrainte(athlete_id, nb_semaines=12):
    """Foster : monotonie = charge moyenne / écart-type sur 7 jours ;
    contrainte = charge de la semaine × monotonie."""
    res = []
    for s in charges_hebdo(athlete_id, nb_semaines):
        c = s["charges"]
        mono = strain = None
        if len(c) >= 4 and s["charge"] > 0:
            sd = statistics.pstdev(c)
            if sd > 0:
                mono = round(statistics.mean(c) / sd, 2)
                strain = round(s["charge"] * mono, 0)
        niveau = None
        if mono is not None:
            niveau = "elevee" if mono >= 2.0 else "moyenne" if mono >= 1.5 else "bonne"
        res.append({"lundi": s["lundi"], "monotonie": mono, "contrainte": strain,
                    "charge": s["charge"], "niveau": niveau, "partielle": s["partielle"]})
    ref = [r["contrainte"] for r in res if r["contrainte"] and not r["partielle"]]
    mediane = statistics.median(ref) if ref else None
    for r in res:
        r["contrainte_haute"] = bool(mediane and r["contrainte"] and r["contrainte"] > 1.5 * mediane)
    return res


def hausse_charge_hebdo(athlete_id, nb_semaines=12):
    """Variation de la charge d'une semaine à l'autre. Seule une semaine
    complète est comparée (la semaine en cours est signalée à part)."""
    sem = charges_hebdo(athlete_id, nb_semaines)
    res = []
    for i, s in enumerate(sem):
        pct = None
        if i > 0 and sem[i - 1]["charge"] >= 30 and not s["partielle"]:
            pct = round((s["charge"] - sem[i - 1]["charge"]) / sem[i - 1]["charge"] * 100)
        niveau = None
        if pct is not None:
            niveau = "forte" if pct > 25 else "attention" if pct > 10 else "baisse" if pct < -25 else "ok"
        res.append({**s, "variation_pct": pct, "niveau": niveau})
    return res


# ======================================================================
# S7 — POIDS LISSÉ ET OBJECTIF
# ======================================================================

def poids_serie(athlete_id, nb_jours=365):
    debut = (date.today() - timedelta(days=nb_jours)).isoformat()
    conn = connexion()
    cur = conn.cursor()
    cur.execute("SELECT date, poids_kg FROM suivi_corporel WHERE athlete_id=? AND date>=? AND poids_kg IS NOT NULL "
                "ORDER BY date", (athlete_id, debut))
    pts = [(_jour(d), float(p)) for d, p in cur.fetchall() if _jour(d)]
    conn.close()
    return pts


def objectif_poids(athlete_id):
    v = obtenir_parametre(f"poids_objectif_{athlete_id}")
    try:
        return float(v) if v else None
    except (TypeError, ValueError):
        return None


def definir_objectif_poids(athlete_id, kg):
    definir_parametre(f"poids_objectif_{athlete_id}", "" if kg is None else str(kg))


def poids_lisse(athlete_id, nb_jours=365, tau_jours=7.0):
    """Moyenne exponentielle (constante de temps 7 jours, adaptée aux
    pesées irrégulières) + tendance en kg/semaine sur 28 jours."""
    pts = poids_serie(athlete_id, nb_jours)
    lisses, s, precedent = [], None, None
    for j, p in pts:
        if s is None:
            s = p
        else:
            dt = max(1, (j - precedent).days)
            s = s + (1 - math.exp(-dt / tau_jours)) * (p - s)
        precedent = j
        lisses.append((j, round(s, 2)))
    tendance = None
    recents = [(j, v) for j, v in lisses if j >= date.today() - timedelta(days=28)]
    if len(recents) >= 3 and (recents[-1][0] - recents[0][0]).days >= 7:
        x0 = recents[0][0]
        xs = [(j - x0).days for j, _ in recents]
        ys = [v for _, v in recents]
        mx, my = statistics.mean(xs), statistics.mean(ys)
        den = sum((x - mx) ** 2 for x in xs)
        if den:
            tendance = round(sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / den * 7, 2)
    obj = objectif_poids(athlete_id)
    eta_sem = None
    if obj is not None and lisses and tendance:
        reste = obj - lisses[-1][1]
        if reste * tendance > 0:
            eta_sem = round(reste / tendance)
    return {"brut": pts, "lisse": lisses, "tendance_kg_sem": tendance, "objectif": obj,
            "actuel": lisses[-1][1] if lisses else None, "semaines_restantes": eta_sem}


# ======================================================================
# S8 — RESSENTI EN 3 CLICS
# ======================================================================

LIBELLES_RESSENTI = {
    "effort": ("Effort", {1: "Facile", 2: "Correct", 3: "Dur"}),
    "jambes": ("Jambes", {1: "Légères", 2: "Normales", 3: "Lourdes"}),
    "humeur": ("Humeur", {1: "Bof", 2: "Bien", 3: "Super"}),
}


def enregistrer_ressenti(activite_id, athlete_id, effort=None, jambes=None, humeur=None):
    conn = connexion()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO ressentis_sorties (activite_id, athlete_id, effort, jambes, humeur) VALUES (?,?,?,?,?) "
        "ON CONFLICT(activite_id) DO UPDATE SET effort=excluded.effort, jambes=excluded.jambes, "
        "humeur=excluded.humeur, date_saisie=CURRENT_TIMESTAMP",
        (activite_id, athlete_id, effort, jambes, humeur),
    )
    conn.commit()
    conn.close()


def ressenti_de_sortie(activite_id):
    conn = connexion()
    cur = conn.cursor()
    cur.execute("SELECT effort, jambes, humeur FROM ressentis_sorties WHERE activite_id=?", (activite_id,))
    r = cur.fetchone()
    conn.close()
    return dict(zip(("effort", "jambes", "humeur"), r)) if r else None


def derniere_sortie_sans_ressenti(athlete_id, jours=3):
    """Dernière sortie des `jours` derniers jours pour laquelle aucun
    ressenti n'a été saisi (None sinon)."""
    depuis = (date.today() - timedelta(days=jours)).isoformat()
    conn = connexion()
    cur = conn.cursor()
    cur.execute(
        "SELECT a.id, a.date, a.nom, a.type, a.distance FROM activites a "
        "LEFT JOIN ressentis_sorties r ON r.activite_id=a.id "
        "WHERE a.athlete_id=? AND a.date>=? AND r.activite_id IS NULL AND a.duree>600 "
        "ORDER BY a.date DESC LIMIT 1", (athlete_id, depuis))
    r = cur.fetchone()
    conn.close()
    return dict(zip(("id", "date", "nom", "type", "distance"), r)) if r else None


def ressentis_recents(athlete_id, nb_jours=60):
    depuis = (date.today() - timedelta(days=nb_jours)).isoformat()
    conn = connexion()
    cur = conn.cursor()
    cur.execute(
        "SELECT a.date, a.nom, r.effort, r.jambes, r.humeur FROM ressentis_sorties r "
        "JOIN activites a ON a.id=r.activite_id WHERE r.athlete_id=? AND a.date>=? ORDER BY a.date",
        (athlete_id, depuis))
    res = [dict(zip(("date", "nom", "effort", "jambes", "humeur"), r)) for r in cur.fetchall()]
    conn.close()
    return res


# ======================================================================
# S10 — ACCLIMATATION À LA CHALEUR (et P10, météo & performance)
# ======================================================================

SEUIL_CHALEUR_C = 22.0


def meteo_des_sorties(athlete_id, depuis, jusqu_a=None):
    """{activite_id: température °C} — météo enregistrée, sinon
    température moyenne de la sortie (montre)."""
    jusqu_a = jusqu_a or date.today()
    res = {}
    for s in activites_periode(athlete_id, depuis, jusqu_a):
        if s["temperature"] is not None:
            res[s["id"]] = float(s["temperature"])
    conn = connexion()
    cur = conn.cursor()
    cur.execute(
        "SELECT m.activite_id, m.temperature FROM meteo_sorties m JOIN activites a ON a.id=m.activite_id "
        "WHERE m.athlete_id=? AND a.date>=? AND m.temperature IS NOT NULL", (athlete_id, depuis.isoformat()))
    for i, t in cur.fetchall():
        res[i] = float(t)
    conn.close()
    return res


def acclimatation_chaleur(athlete_id, nb_jours=14):
    depuis = date.today() - timedelta(days=nb_jours)
    sorties = activites_periode(athlete_id, depuis)
    temps = meteo_des_sorties(athlete_id, depuis)
    avec_temp = [s for s in sorties if s["id"] in temps]
    chaudes = [s for s in avec_temp if temps[s["id"]] >= SEUIL_CHALEUR_C and s["duree"] >= 30 * 60]
    n = len(chaudes)
    if not avec_temp:
        niveau = None
    else:
        niveau = "acclimate" if n >= 6 else "en_cours" if n >= 3 else "faible"
    return {
        "nb_chaudes": n, "nb_avec_temperature": len(avec_temp), "nb_sorties": len(sorties),
        "niveau": niveau, "seuil": SEUIL_CHALEUR_C, "jours": nb_jours,
        "score": min(100, round(n / 6 * 100)) if avec_temp else None,
        "sorties_chaudes": [(s["jour"], s["nom"], temps[s["id"]]) for s in chaudes],
    }


def telecharger_meteo_sortie(activite_id):
    """Interroge Open-Meteo (archive horaire) pour le point de départ de
    la sortie. Renvoie (dict, erreur). Enregistre le résultat."""
    from interface.meteo import _requete_json
    conn = connexion()
    cur = conn.cursor()
    cur.execute("SELECT athlete_id, date FROM activites WHERE id=?", (activite_id,))
    r = cur.fetchone()
    conn.close()
    if not r:
        return None, "Sortie introuvable."
    athlete_id, d = r
    pts = trace_de_activite(activite_id)
    if not pts:
        return None, "Pas de trace GPS pour cette sortie."
    dt = _datetime(d)
    if dt is None:
        return None, "Date illisible."
    url = (f"https://archive-api.open-meteo.com/v1/archive?latitude={pts[0][0]}&longitude={pts[0][1]}"
           f"&start_date={dt.date()}&end_date={dt.date()}"
           "&hourly=temperature_2m,relative_humidity_2m,wind_speed_10m,precipitation&timezone=auto")
    contenu, erreur = _requete_json(url)
    if erreur:
        return None, erreur
    try:
        h = contenu["hourly"]
        i = min(max(dt.hour, 0), len(h["time"]) - 1)
        donnees = {"temperature": h["temperature_2m"][i], "humidite": h["relative_humidity_2m"][i],
                   "vent_kmh": h["wind_speed_10m"][i], "precipitation_mm": h["precipitation"][i]}
    except (KeyError, IndexError, TypeError):
        return None, "Réponse météo inattendue."
    conn = connexion()
    conn.execute(
        "INSERT INTO meteo_sorties (activite_id, athlete_id, temperature, humidite, vent_kmh, precipitation_mm, source) "
        "VALUES (?,?,?,?,?,?,'open-meteo') ON CONFLICT(activite_id) DO UPDATE SET temperature=excluded.temperature, "
        "humidite=excluded.humidite, vent_kmh=excluded.vent_kmh, precipitation_mm=excluded.precipitation_mm, "
        "date_maj=CURRENT_TIMESTAMP",
        (activite_id, athlete_id, donnees["temperature"], donnees["humidite"], donnees["vent_kmh"],
         donnees["precipitation_mm"]))
    conn.commit()
    conn.close()
    return donnees, None


def completer_meteo(athlete_id, nb_jours=60, limite=40, progression=None):
    """Complète la météo des sorties récentes qui n'en ont pas encore.
    Renvoie (nb_ok, nb_echecs, dernière_erreur)."""
    depuis = date.today() - timedelta(days=nb_jours)
    deja = meteo_des_sorties(athlete_id, depuis)
    a_faire = [s for s in reversed(activites_periode(athlete_id, depuis)) if s["id"] not in deja and s["duree"] > 600]
    ok = ko = 0
    derniere = None
    for n, s in enumerate(a_faire[:limite]):
        if progression:
            progression(n, min(limite, len(a_faire)))
        _d, err = telecharger_meteo_sortie(s["id"])
        if err:
            ko += 1
            derniere = err
            if ko >= 3 and ok == 0:
                break  # réseau absent : inutile d'insister
        else:
            ok += 1
    return ok, ko, derniere


# ======================================================================
# E4 — RÉPARTITION FACILE / DUR (80/20)
# ======================================================================

SEUIL_FACILE_PCT_FCMAX = 0.80


def _secondes_facile_dur(sortie, fc_max, trace=None):
    """(facile_s, dur_s, methode) pour une sortie. Priorité : temps par
    zone Garmin ; sinon trace avec FC point par point ; sinon FC moyenne."""
    if any(sortie.get(f"z{k}") for k in range(1, 6)):
        facile = (sortie.get("z1") or 0) + (sortie.get("z2") or 0)
        dur = sum(sortie.get(f"z{k}") or 0 for k in (3, 4, 5))
        return facile, dur, "zones"
    seuil = fc_max * SEUIL_FACILE_PCT_FCMAX
    pts = trace if trace is not None else trace_de_activite(sortie["id"])
    facile = dur = 0.0
    prec = None
    for p in pts:
        if len(p) >= 5 and p[3] is not None and p[4]:
            if prec is not None:
                dt = p[3] - prec[0]
                if 0 < dt <= 30:
                    if prec[1] < seuil:
                        facile += dt
                    else:
                        dur += dt
            prec = (p[3], p[4])
        else:
            prec = None
    if facile + dur > 0:
        return facile, dur, "trace"
    if sortie.get("fc_moy") and sortie.get("duree"):
        if sortie["fc_moy"] < seuil:
            return sortie["duree"], 0, "moyenne"
        return 0, sortie["duree"], "moyenne"
    return 0, 0, None


def repartition_facile_dur(athlete_id, nb_semaines=12):
    """Part de temps « facile » (< 80 % de FC max) par semaine et au
    total, sur les sorties de course/trail/rando/vélo."""
    fc_max = _athlete(athlete_id).get("fc_max") or 185
    debut = lundi_de(date.today()) - timedelta(weeks=nb_semaines - 1)
    sorties = activites_periode(athlete_id, debut)
    semaines = {debut + timedelta(weeks=i): [0.0, 0.0] for i in range(nb_semaines)}
    methodes = {}
    for s in sorties:
        if not s["jour"]:
            continue
        f, d, m = _secondes_facile_dur(s, fc_max)
        if m is None:
            continue
        methodes[m] = methodes.get(m, 0) + 1
        lundi = lundi_de(s["jour"])
        if lundi in semaines:
            semaines[lundi][0] += f
            semaines[lundi][1] += d
    liste = []
    tf = td = 0.0
    for lundi, (f, d) in sorted(semaines.items()):
        tot = f + d
        liste.append({"lundi": lundi, "facile_h": round(f / 3600, 2), "dur_h": round(d / 3600, 2),
                      "pct_facile": round(f / tot * 100) if tot else None})
        tf += f
        td += d
    total_pct = round(tf / (tf + td) * 100) if (tf + td) else None
    if total_pct is None:
        conseil = "Pas assez de données de fréquence cardiaque pour calculer la répartition."
    elif total_pct >= 75:
        conseil = "Très bonne répartition : l'essentiel de ton entraînement est facile, ce qui laisse la place aux séances dures."
    elif total_pct >= 65:
        conseil = "Correct, mais un peu trop de temps en zone moyenne. Ralentis les sorties faciles pour viser 80 %."
    else:
        conseil = "Trop de temps à allure soutenue : beaucoup de sorties « moyennement dures ». Ralentis les sorties faciles."
    return {"semaines": liste, "pct_facile": total_pct, "conseil": conseil, "methodes": methodes,
            "seuil_bpm": round(fc_max * SEUIL_FACILE_PCT_FCMAX)}


# ======================================================================
# P7 — TOTAUX ; P6 — COMPARER DEUX PÉRIODES
# ======================================================================

TYPES_COURSE = ("Trail", "Course")
MOIS_FR = ["janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.", "nov.", "déc."]


def _stats(sorties, charge=None):
    course = [s for s in sorties if s["type"] in TYPES_COURSE and s["distance"] >= 1 and s["duree"] > 0]
    dist_c = sum(s["distance"] for s in course)
    duree_c = sum(s["duree"] for s in course)
    fcs = [(s["fc_moy"], s["duree"]) for s in sorties if s["fc_moy"]]
    return {
        "sorties": len(sorties),
        "jours_actifs": len({s["jour"] for s in sorties if s["jour"]}),
        "distance": round(sum(s["distance"] for s in sorties), 1),
        "denivele": int(sum(s["denivele"] for s in sorties)),
        "duree_h": round(sum(s["duree"] for s in sorties) / 3600, 2),
        "charge": round(charge, 0) if charge is not None else None,
        "allure_course": round(duree_c / 60 / dist_c, 2) if dist_c else None,
        "fc_moy": round(sum(f * d for f, d in fcs) / sum(d for _, d in fcs)) if fcs else None,
        "plus_longue": round(max((s["distance"] for s in sorties), default=0), 1),
        "plus_gros_d": int(max((s["denivele"] for s in sorties), default=0)),
    }


def totaux_periode(athlete_id, debut, fin):
    sorties = activites_periode(athlete_id, debut, fin)
    jours = (date.today() - debut).days + 1
    par_jour = dict(charges_par_jour(athlete_id, max(jours, 1)))
    charge = sum(v for j, v in par_jour.items() if debut <= j <= fin)
    return _stats(sorties, charge)


def totaux(athlete_id, granularite="mois", nb_periodes=12):
    """Totaux par 'semaine', 'mois' ou 'annee' (la dernière période est
    la période en cours). Renvoie une liste du plus ancien au plus récent."""
    aujourd_hui = date.today()
    bornes = []
    if granularite == "semaine":
        premier = lundi_de(aujourd_hui) - timedelta(weeks=nb_periodes - 1)
        for i in range(nb_periodes):
            d = premier + timedelta(weeks=i)
            bornes.append((d, d + timedelta(days=6), f"{d.day:02d}/{d.month:02d}"))
    elif granularite == "annee":
        for i in range(nb_periodes):
            an = aujourd_hui.year - nb_periodes + 1 + i
            bornes.append((date(an, 1, 1), date(an, 12, 31), str(an)))
    else:
        for i in range(nb_periodes):
            m0 = aujourd_hui.year * 12 + aujourd_hui.month - 1 - (nb_periodes - 1 - i)
            an, mo = divmod(m0, 12)
            d = date(an, mo + 1, 1)
            f = (date(an + (mo + 1) // 12, (mo + 1) % 12 + 1, 1) - timedelta(days=1))
            bornes.append((d, f, f"{MOIS_FR[mo]} {str(an)[2:]}"))
    debut_global = bornes[0][0]
    sorties = activites_periode(athlete_id, debut_global, aujourd_hui)
    jours = (aujourd_hui - debut_global).days + 1
    par_jour = dict(charges_par_jour(athlete_id, max(jours, 1)))
    res = []
    for d, f, lib in bornes:
        sp = [s for s in sorties if s["jour"] and d <= s["jour"] <= f]
        charge = sum(v for j, v in par_jour.items() if d <= j <= f)
        res.append({"debut": d, "fin": f, "libelle": lib, "en_cours": d <= aujourd_hui <= f, **_stats(sp, charge)})
    return res


def comparer_periodes(athlete_id, a_debut, a_fin, b_debut, b_fin):
    """Deux périodes + écarts (b − a) et pourcentages."""
    a = totaux_periode(athlete_id, a_debut, a_fin)
    b = totaux_periode(athlete_id, b_debut, b_fin)
    ecarts = {}
    for k in ("sorties", "jours_actifs", "distance", "denivele", "duree_h", "charge", "allure_course", "fc_moy",
              "plus_longue", "plus_gros_d"):
        va, vb = a.get(k), b.get(k)
        if va is None or vb is None:
            ecarts[k] = (None, None)
        else:
            ecarts[k] = (round(vb - va, 2), round((vb - va) / va * 100) if va else None)
    return {"a": a, "b": b, "ecarts": ecarts}


def periodes_predefinies():
    """{libellé: (a_debut, a_fin, b_debut, b_fin)} — A = référence, B = à comparer."""
    t = date.today()
    lundi = lundi_de(t)
    m0 = date(t.year, t.month, 1)
    mois_prec_fin = m0 - timedelta(days=1)
    mois_prec_debut = date(mois_prec_fin.year, mois_prec_fin.month, 1)
    an = t.year
    return {
        "Ce mois-ci  vs  mois précédent": (mois_prec_debut, mois_prec_fin, m0, t),
        "4 dernières semaines  vs  4 semaines d'avant": (t - timedelta(days=55), t - timedelta(days=28),
                                                           t - timedelta(days=27), t),
        "Cette semaine  vs  semaine dernière": (lundi - timedelta(days=7), lundi - timedelta(days=1), lundi, t),
        "Cette année  vs  même période l'an dernier": (date(an - 1, 1, 1),
                                                       date(an - 1, t.month, min(t.day, 28)), date(an, 1, 1), t),
        "3 derniers mois  vs  3 mois d'avant": (t - timedelta(days=182), t - timedelta(days=92),
                                                 t - timedelta(days=91), t),
    }


# ======================================================================
# P8 — OBJECTIFS ANNUELS
# ======================================================================

METRIQUES_ANNUELLES = {
    "distance_km": ("Distance", "km", "distance"),
    "denivele_m": ("Dénivelé positif", "m", "denivele"),
    "duree_h": ("Temps d'entraînement", "h", "duree_h"),
    "sorties": ("Nombre de sorties", "", "sorties"),
}


def definir_objectif_annuel(athlete_id, annee, metrique, cible):
    conn = connexion()
    if cible is None or cible <= 0:
        conn.execute("DELETE FROM objectifs_annuels WHERE athlete_id=? AND annee=? AND metrique=?",
                     (athlete_id, annee, metrique))
    else:
        conn.execute("INSERT INTO objectifs_annuels (athlete_id, annee, metrique, cible) VALUES (?,?,?,?) "
                     "ON CONFLICT(athlete_id, annee, metrique) DO UPDATE SET cible=excluded.cible",
                     (athlete_id, annee, metrique, float(cible)))
    conn.commit()
    conn.close()


def progression_annuelle(athlete_id, annee=None):
    """Pour chaque objectif de l'année : réalisé, cible, attendu à ce jour
    (rythme régulier), projection fin d'année et statut."""
    annee = annee or date.today().year
    conn = connexion()
    cur = conn.cursor()
    cur.execute("SELECT metrique, cible FROM objectifs_annuels WHERE athlete_id=? AND annee=?", (athlete_id, annee))
    cibles = dict(cur.fetchall())
    conn.close()
    t = date.today()
    fin_an = date(annee, 12, 31)
    jusqu = min(t, fin_an)
    stats = totaux_periode(athlete_id, date(annee, 1, 1), jusqu)
    jours_ecoules = (jusqu - date(annee, 1, 1)).days + 1
    jours_annee = (fin_an - date(annee, 1, 1)).days + 1
    frac = min(1.0, jours_ecoules / jours_annee)
    res = []
    for cle, (libelle, unite, champ) in METRIQUES_ANNUELLES.items():
        realise = stats.get(champ) or 0
        cible = cibles.get(cle)
        if cible is None:
            res.append({"cle": cle, "libelle": libelle, "unite": unite, "realise": realise, "cible": None})
            continue
        attendu = cible * frac
        projection = realise / frac if frac > 0.02 else None
        ecart = (realise - attendu) / attendu * 100 if attendu else 0
        statut = "atteint" if realise >= cible else "avance" if ecart >= 5 else "retard" if ecart <= -10 else "rythme"
        res.append({"cle": cle, "libelle": libelle, "unite": unite, "realise": realise, "cible": cible,
                    "attendu": attendu, "projection": projection, "statut": statut,
                    "pct": realise / cible * 100, "ecart_pct": ecart})
    return res


# ======================================================================
# P10 — MÉTÉO ET PERFORMANCE
# ======================================================================

TRANCHES_TEMPERATURE = [(-30, 5, "< 5 °C"), (5, 10, "5–10 °C"), (10, 15, "10–15 °C"), (15, 20, "15–20 °C"),
                        (20, 25, "20–25 °C"), (25, 30, "25–30 °C"), (30, 60, "> 30 °C")]


def performance_selon_temperature(athlete_id, nb_jours=365):
    """Allure « à plat équivalent » (D+ converti en distance) et FC moyenne
    par tranche de température, sur les courses/trails ≥ 5 km."""
    depuis = date.today() - timedelta(days=nb_jours)
    temps = meteo_des_sorties(athlete_id, depuis)
    sorties = [s for s in activites_periode(athlete_id, depuis, types=TYPES_COURSE)
               if s["id"] in temps and s["distance"] >= 5 and s["duree"] > 0]
    res = []
    for bas, haut, lib in TRANCHES_TEMPERATURE:
        lot = [s for s in sorties if bas <= temps[s["id"]] < haut]
        if not lot:
            continue
        allures = [s["duree"] / 60 / (s["distance"] + min(s["denivele"], 60 * s["distance"]) / 125) for s in lot]
        fcs = [s["fc_moy"] for s in lot if s["fc_moy"]]
        res.append({"tranche": lib, "n": len(lot), "allure_eq": round(statistics.mean(allures), 2),
                    "fc_moy": round(statistics.mean(fcs)) if fcs else None})
    ref = next((r for r in res if r["tranche"] in ("10–15 °C", "15–20 °C")), None)
    for r in res:
        r["ecart_pct"] = round((r["allure_eq"] / ref["allure_eq"] - 1) * 100, 1) if ref else None
    return {"tranches": res, "nb_sorties_meteo": len(sorties), "nb_total": len(
        activites_periode(athlete_id, depuis, types=TYPES_COURSE))}


# ======================================================================
# E5 — SIMULATEUR DE CHARGE ; E6 — VOLUME CIBLE DE LA SEMAINE
# ======================================================================

INTENSITES = {"Facile": 0.55, "Modérée": 0.68, "Soutenue": 0.80, "Très dure": 0.90}


def charge_seance(athlete_id, duree_min, intensite="Modérée"):
    """Charge (TRIMP) d'une séance prévue, avec la même formule que les
    sorties réelles."""
    from interface.coach import calculer_charge_activite
    a = _athlete(athlete_id)
    fc_repos, fc_max = a.get("fc_repos") or 55, a.get("fc_max") or 185
    fc = fc_repos + INTENSITES.get(intensite, 0.68) * (fc_max - fc_repos)
    charge, _ = calculer_charge_activite({"type": "Trail", "duree": duree_min * 60,
                                          "frequence_cardiaque_moyenne": fc}, a)
    return charge


def simuler_charge(athlete_id, charges_prevues, nb_jours=14, historique=60):
    """charges_prevues : {date: charge}. Renvoie l'historique récent puis
    la projection jour par jour {date, fitness, fatigue, forme, prevu}."""
    from interface.coach import CONSTANTE_FITNESS_JOURS, CONSTANTE_FATIGUE_JOURS
    base = charges_par_jour(athlete_id, 200)
    fitness = fatigue = 0.0
    serie = []
    for j, c in base:
        fitness += (c - fitness) / CONSTANTE_FITNESS_JOURS
        fatigue += (c - fatigue) / CONSTANTE_FATIGUE_JOURS
        serie.append({"date": j, "fitness": fitness, "fatigue": fatigue, "forme": fitness - fatigue, "prevu": False})
    serie = serie[-historique:]
    j = date.today()
    for _ in range(nb_jours):
        j += timedelta(days=1)
        c = charges_prevues.get(j, 0.0)
        fitness += (c - fitness) / CONSTANTE_FITNESS_JOURS
        fatigue += (c - fatigue) / CONSTANTE_FATIGUE_JOURS
        serie.append({"date": j, "fitness": fitness, "fatigue": fatigue, "forme": fitness - fatigue, "prevu": True})
    return serie


def volume_cible_semaine(athlete_id):
    """Volume conseillé pour la semaine en cours d'après les 4 semaines
    complètes précédentes : +8 % en régime normal ; semaine allégée
    (−25 %) après 3 semaines de hausse d'affilée ; −10 % si hausse
    récente trop forte."""
    semaines = charges_hebdo(athlete_id, 8)
    completes = [s for s in semaines if not s["partielle"]]
    en_cours = semaines[-1] if semaines and semaines[-1]["lundi"] == lundi_de(date.today()) else None
    if len(completes) < 3 or not en_cours:
        return None
    ref = completes[-4:]
    moyenne = {k: statistics.mean(s[k] for s in ref) for k in ("charge", "distance", "denivele", "duree_h")}
    hausses = 0
    for a, b in zip(completes[-4:], completes[-3:]):
        if b["charge"] > a["charge"] * 1.03:
            hausses += 1
    derniere, avant = completes[-1], completes[-2]
    if hausses >= 3:
        coef, motif = 0.75, "Semaine allégée : trois semaines de hausse d'affilée, ton corps assimile mieux avec une semaine plus légère."
    elif avant["charge"] > 30 and derniere["charge"] > avant["charge"] * 1.25:
        coef, motif = 0.95, "Ta dernière semaine a beaucoup augmenté : on la consolide, sans monter davantage."
    elif moyenne["charge"] < 20:
        return None
    else:
        coef, motif = 1.08, "Progression douce : environ +8 % par rapport à ta moyenne des 4 dernières semaines."
    cible = {k: round(v * coef, 1 if k in ("distance", "duree_h") else 0) for k, v in moyenne.items()}
    fait = {k: en_cours[k] for k in ("charge", "distance", "denivele", "duree_h")}
    jours_restants = 7 - (date.today() - en_cours["lundi"]).days - 1
    return {"cible": cible, "fait": fait, "motif": motif, "coef": coef, "jours_restants": max(jours_restants, 0),
            "moyenne": moyenne,
            "pct": {k: (fait[k] / cible[k] * 100 if cible[k] else 0) for k in cible}}


# ======================================================================
# P4 — FORME POUR LA DISTANCE VISÉE (estimation indicative)
# ======================================================================

def courses_a_venir(athlete_id):
    """Courses futures du calendrier : [{nom, date, distance_km, denivele_m}]."""
    conn = connexion()
    cur = conn.cursor()
    cur.execute("SELECT nom, date, distance_km, denivele_m FROM courses_calendrier WHERE date>=? "
                "AND distance_km IS NOT NULL AND (athlete_id=? OR athlete_id IS NULL) ORDER BY date LIMIT 40",
                (date.today().isoformat(), athlete_id))
    res = [dict(zip(("nom", "date", "distance_km", "denivele_m"), r)) for r in cur.fetchall()]
    conn.close()
    return res


def forme_pour_distance(athlete_id, distance_km, denivele_m=0, date_course=None):
    """Compare l'entraînement des 8 dernières semaines à ce qu'une course
    de cette taille demande (repères classiques de préparation). C'est une
    estimation indicative, pas une prédiction de chrono."""
    effort = distance_km + (denivele_m or 0) / 100.0
    depuis = date.today() - timedelta(days=56)
    sorties = [s for s in activites_periode(athlete_id, depuis, types=("Trail", "Course", "Randonnée"))
               if s["distance"] >= 1]

    def eff(s):
        return (s["distance"] + s["denivele"] / 100.0) * (0.7 if s["type"] == "Randonnée" else 1.0)

    longue = max((eff(s) for s in sorties), default=0.0)
    cible_longue = max(8.0, min(0.6 * effort, 42.0))
    recent = [s for s in sorties if s["jour"] and s["jour"] >= date.today() - timedelta(days=28)]
    volume = sum(eff(s) for s in recent) / 4
    cible_volume = max(20.0, min(0.8 * effort, 100.0))
    dplus_sem = sum(s["denivele"] for s in recent) / 4
    cible_dplus = max(100.0, min(0.35 * (denivele_m or 0), 2000.0)) if denivele_m else None
    semaines_reg = 0
    for i in range(8):
        d0 = lundi_de(date.today()) - timedelta(weeks=i)
        if sum(1 for s in sorties if s["jour"] and d0 <= s["jour"] < d0 + timedelta(days=7)) >= 3:
            semaines_reg += 1
    criteres = [
        {"nom": "Sortie longue", "valeur": longue, "cible": cible_longue, "unite": "km-effort", "poids": 0.30},
        {"nom": "Volume hebdomadaire", "valeur": volume, "cible": cible_volume, "unite": "km-effort/sem.", "poids": 0.30},
        {"nom": "Régularité (≥ 3 sorties/sem.)", "valeur": semaines_reg, "cible": 6, "unite": "sem. sur 8", "poids": 0.25},
    ]
    if cible_dplus:
        criteres.append({"nom": "Dénivelé hebdomadaire", "valeur": dplus_sem, "cible": cible_dplus, "unite": "m D+/sem.", "poids": 0.15})
    else:
        criteres[0]["poids"], criteres[1]["poids"], criteres[2]["poids"] = 0.35, 0.35, 0.30
    poids_total = sum(c["poids"] for c in criteres)
    score = 0.0
    for c in criteres:
        c["ratio"] = min(1.0, c["valeur"] / c["cible"]) if c["cible"] else 1.0
        score += c["ratio"] * c["poids"] / poids_total
    score = round(score * 100)
    niveau = "loin" if score < 40 else "construction" if score < 65 else "bonne_voie" if score < 85 else "pret"
    pires = sorted(criteres, key=lambda c: c["ratio"])
    conseil = ""
    if niveau != "pret":
        c = pires[0]
        manque = c["cible"] - c["valeur"]
        conseil = f"Point à travailler en priorité : {c['nom'].lower()} (il manque environ {round(manque)} {c['unite']})."
    semaines = None
    if date_course:
        try:
            semaines = max(0, (date.fromisoformat(str(date_course)[:10]) - date.today()).days // 7)
        except ValueError:
            pass
    return {"score": score, "niveau": niveau, "criteres": criteres, "conseil": conseil, "effort_km": round(effort, 1),
            "semaines_restantes": semaines}


# ======================================================================
# S1 — DISPONIBILITÉ DU MATIN ; ÉCRAN « AUJOURD'HUI »
# ======================================================================

def disponibilite_matin(athlete_id):
    """Score 0-100 de disponibilité pour s'entraîner ce matin, combiné à
    partir de la fraîcheur (forme), de la dernière nuit, du HRV, de la FC de
    repos et d'une éventuelle blessure. Les signaux absents sont ignorés
    (leur poids est redistribué). Renvoie score, verdict, facteurs."""
    from interface.coach import calculer_serie_forme, _blessures_actives
    facteurs = []   # (clé, libellé, score 0-100, détail, poids)

    serie = calculer_serie_forme(athlete_id, 90)
    if serie:
        fr = serie[-1]["forme"]
        facteurs.append(("forme", "Fraîcheur", max(0, min(100, 50 + fr * 2)),
                         f"{fr:+.0f} (forme − fatigue)", 0.35))

    som = serie_sommeil(athlete_id, 5)
    if som:
        dernier = max(som)
        from interface.coach import obtenir_objectif_sommeil_heures
        obj = obtenir_objectif_sommeil_heures()
        h = som[dernier]["heures"]
        facteurs.append(("sommeil", "Dernière nuit", max(0, min(100, h / obj * 100)),
                         f"{h:.1f} h sur {obj:.1f} h visées", 0.25))

    h = hrv_avec_bande(athlete_id, 60)
    if h["statut"]:
        sc = {"equilibree": 100, "haute": 90, "basse": 40}[h["statut"]]
        lib = {"equilibree": "dans ta bande normale", "haute": "au-dessus de ta bande", "basse": "sous ta bande normale"}[h["statut"]]
        facteurs.append(("hrv", "HRV", sc, f"{round(h['moyenne_7j'])} ms, {lib}", 0.20))

    f = fc_repos_et_alerte(athlete_id, 60)
    if f["niveau"]:
        sc = {"ok": 100, "attention": 60, "alerte": 25}[f["niveau"]]
        facteurs.append(("fc_repos", "FC de repos", sc, f"{f['ecart']:+.1f} bpm vs ta base", 0.20))

    blessures = _blessures_actives(athlete_id)
    if blessures:
        facteurs.append(("blessure", "Blessure", 20, "une blessure est en cours", 0.20))

    if not facteurs:
        return {"score": None, "verdict": "Pas encore assez de données pour estimer ta disponibilité.", "facteurs": []}
    poids_total = sum(x[4] for x in facteurs)
    score = round(sum(x[2] * x[4] for x in facteurs) / poids_total)
    if blessures:
        score = min(score, 45)
    if score >= 75:
        verdict = "Prêt : tu peux faire une séance intense."
    elif score >= 55:
        verdict = "Séance normale possible."
    elif score >= 35:
        verdict = "Séance légère ou récupération conseillée."
    else:
        verdict = "Repos conseillé aujourd'hui."
    return {"score": score, "verdict": verdict,
            "facteurs": [{"cle": k, "libelle": l, "score": round(s), "detail": d} for k, l, s, d, _ in facteurs]}


def seance_du_jour(athlete_id):
    """Séance structurée prévue aujourd'hui (None sinon)."""
    conn = connexion()
    cur = conn.cursor()
    cur.execute("SELECT id, nom, type_seance, statut, commentaire_replanification FROM seances_structurees "
                "WHERE athlete_id=? AND substr(date_prevue,1,10)=? ORDER BY id LIMIT 1",
                (athlete_id, date.today().isoformat()))
    r = cur.fetchone()
    conn.close()
    return dict(zip(("id", "nom", "type", "statut", "commentaire"), r)) if r else None


def donnees_aujourdhui(athlete_id):
    """Tout ce que l'écran « Aujourd'hui » affiche, calculé hors interface."""
    from interface.coach import generer_alertes, calculer_acwr
    res = {"athlete_id": athlete_id}
    res["dispo"] = disponibilite_matin(athlete_id)
    res["seance"] = seance_du_jour(athlete_id)
    res["volume"] = volume_cible_semaine(athlete_id)
    try:
        res["acwr"] = calculer_acwr(athlete_id)
    except Exception:
        res["acwr"] = None
    res["alertes"] = [a for a in generer_alertes(athlete_id) if a["niveau"] in ("critique", "attention")][:3]
    res["sans_ressenti"] = derniere_sortie_sans_ressenti(athlete_id)
    courses = courses_a_venir(athlete_id)
    res["course"] = courses[0] if courses else None
    recentes = activites_periode(athlete_id, date.today() - timedelta(days=30))
    res["derniere"] = recentes[-1] if recentes else None
    res["semaine"] = totaux_periode(athlete_id, lundi_de(date.today()), date.today())
    return res
