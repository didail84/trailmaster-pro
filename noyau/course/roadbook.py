"""
Roadbook course (v108) — préparer UNE course précise à partir de son tracé.

Ce module ne refait aucun calcul qui existe déjà : il assemble
  - le découpage en segments et le calcul de pente   (interface/pacing_segments)
  - la prédiction de chrono selon le VO₂max           (data/predictions_course)
  - le plan glucides / eau / sodium et le menu        (data/ravitaillement)
  - la liste de matériel obligatoire / conseillé      (data/reference_materiel_course)
et il y ajoute ce qui manquait : les points de passage (ravitaillements, barrières
horaires), l'heure de passage estimée et la marge sur chaque barrière, la
nourriture à emporter par tronçon, la checklist cochable et son enregistrement.

100 % local, aucun accès réseau. Les temps sont des ESTIMATIONS : à garder en
réserve plutôt qu'à suivre à la seconde.
"""

import json
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta

from data.database import connexion
from noyau.traces.gpx_utils import _distance_haversine_km, parser_gpx
from noyau.course.pacing_segments import decouper_par_segments, calculer_pacing

TYPES_POINT = ("Ravitaillement", "Barrière horaire", "Repère")
MARGE_SERREE_MIN = 30          # sous 30 min de marge : « serré »
LONGUEUR_SEGMENT_KM = 0.5
MAX_POINTS_TRACE = 1500        # trace conservée en base (allégée)


# ----------------------------------------------------------------------
# TRACE
# ----------------------------------------------------------------------
def _allonger(points, maxi=MAX_POINTS_TRACE):
    if len(points) <= maxi:
        return points
    pas = len(points) / maxi
    sortie = [points[int(i * pas)] for i in range(maxi)]
    if sortie[-1] is not points[-1]:
        sortie.append(points[-1])
    return sortie


def profil(points):
    """[(km_cumule, altitude_m)] pour chaque point de la trace."""
    out, km = [], 0.0
    for i, p in enumerate(points):
        if i:
            km += _distance_haversine_km(points[i - 1][0], points[i - 1][1], p[0], p[1])
        out.append((km, float(p[2] or 0.0)))
    return out


def lire_waypoints(chemin_gpx):
    """[(nom, lat, lon)] des points d'intérêt (<wpt>) d'un GPX, s'il y en a."""
    try:
        racine = ET.parse(chemin_gpx).getroot()
    except Exception:
        return []
    res = []
    for e in racine.iter():
        if e.tag.split("}")[-1] != "wpt":
            continue
        nom = ""
        for s in e:
            if s.tag.split("}")[-1] == "name" and s.text:
                nom = s.text.strip()
        try:
            res.append((nom or "Point", float(e.attrib["lat"]), float(e.attrib["lon"])))
        except (KeyError, ValueError):
            continue
    return res


def km_du_point(points, lat, lon):
    """Km (le long de la trace) du point de la trace le plus proche de (lat, lon)."""
    prof = profil(points)
    meilleur, km_m = None, 0.0
    for (km, _alt), p in zip(prof, points):
        d = _distance_haversine_km(lat, lon, p[0], p[1])
        if meilleur is None or d < meilleur:
            meilleur, km_m = d, km
    return km_m


def charger_gpx(chemin):
    """-> dict {points, distance_km, denivele_m, denivele_neg_m, waypoints:[(nom, km)]}."""
    t = parser_gpx(chemin)
    pts = t["points"]
    if len(pts) < 2:
        raise ValueError("Le fichier GPX ne contient pas de tracé exploitable.")
    wp = [(nom, round(km_du_point(pts, la, lo), 1)) for nom, la, lo in lire_waypoints(chemin)]
    return {
        "points": [list(p[:3]) for p in _allonger(pts)],
        "distance_km": round(t["distance_km"], 2),
        "denivele_m": int(t["denivele_positif"]),
        "denivele_neg_m": int(t["denivele_negatif"]),
        "waypoints": sorted(wp, key=lambda x: x[1]),
    }


def trace_depuis_parcours(parcours_id):
    """Reprend un parcours déjà importé dans « Parcours GPX »."""
    conn = connexion()
    cur = conn.cursor()
    cur.execute("SELECT nom, distance_km, denivele_positif, denivele_negatif, trace_json "
                "FROM parcours_gpx WHERE id=?", (parcours_id,))
    r = cur.fetchone()
    conn.close()
    if not r or not r[4]:
        raise ValueError("Parcours introuvable ou sans tracé.")
    pts = json.loads(r[4])
    return {"nom": r[0], "points": [list(p[:3]) for p in _allonger(pts)],
            "distance_km": round(r[1] or profil(pts)[-1][0], 2),
            "denivele_m": int(r[2] or 0), "denivele_neg_m": int(r[3] or 0), "waypoints": []}


# ----------------------------------------------------------------------
# TEMPS DE PASSAGE
# ----------------------------------------------------------------------
def _segments(points, methode="minetti"):
    """Segments (pacing_segments) calculés à allure plat = 1 min/km : le temps réel
    est ce temps × l'allure plat, car le calcul est proportionnel."""
    seg = decouper_par_segments(points, LONGUEUR_SEGMENT_KM)
    seg1, _ = calculer_pacing(seg, 1.0, methode)
    return seg1


def secondes_par_allure_unitaire(points, methode="minetti"):
    seg = _segments(points, methode)
    return seg[-1]["temps_cumule_s"] if seg else 0


def allure_plat_pour_duree(points, duree_s, methode="minetti"):
    """Allure « plat » (min/km) qui donne exactement `duree_s` sur ce tracé."""
    unit = secondes_par_allure_unitaire(points, methode)
    return (duree_s / unit) if unit else None


def duree_depuis_vo2max(athlete_id, distance_km, denivele_m):
    """Durée prédite (s) via le VO₂max estimé (estimation basse), ou None."""
    try:
        from noyau.course.predictions_course import predire, vo2max_de_reference
        vo2 = vo2max_de_reference(athlete_id)
        return predire(vo2, distance_km, denivele_m) if vo2 else None
    except Exception:
        return None


def temps_au_km(points, allure_plat_min_km, methode="minetti"):
    """Fonction km -> secondes écoulées depuis le départ (interpolation linéaire)."""
    seg = decouper_par_segments(points, LONGUEUR_SEGMENT_KM)
    seg, _ = calculer_pacing(seg, allure_plat_min_km, methode)
    bornes = [(0.0, 0.0)]
    km = 0.0
    for s in seg:
        km += s["distance_km"]
        bornes.append((km, float(s["temps_cumule_s"])))

    def f(x):
        if x <= 0:
            return 0.0
        if x >= bornes[-1][0]:
            return bornes[-1][1]
        for (k0, t0), (k1, t1) in zip(bornes, bornes[1:]):
            if k0 <= x <= k1:
                return t0 + (t1 - t0) * ((x - k0) / (k1 - k0) if k1 > k0 else 0)
        return bornes[-1][1]

    f.total_km = bornes[-1][0]
    f.total_s = bornes[-1][1]
    return f


def denivele_entre(profil_pts, km_a, km_b):
    """(D+, D-) en mètres entre deux km."""
    dp = dn = 0.0
    prec = None
    for km, alt in profil_pts:
        if km < km_a:
            prec = alt
            continue
        if km > km_b:
            break
        if prec is not None:
            d = alt - prec
            if d > 0.5:
                dp += d
            elif d < -0.5:
                dn += -d
        prec = alt
    return round(dp), round(dn)


def _hhmm(texte):
    """« 14:30 » / « 14h30 » -> (h, m) ou None."""
    if not texte:
        return None
    t = str(texte).strip().lower().replace("h", ":").replace(" ", "")
    if t.endswith(":"):
        t += "00"
    try:
        h, m = t.split(":")[:2]
        h, m = int(h), int(m or 0)
    except ValueError:
        return None
    return (h, m) if 0 <= h < 48 and 0 <= m < 60 else None


def texte_heure(dt):
    return dt.strftime("%H:%M") if dt else "—"


def texte_duree(s):
    if s is None:
        return "—"
    h, r = divmod(int(round(s)), 3600)
    return f"{h}h{r // 60:02d}"


def calculer_passages(points, points_course, depart_hhmm, allure_plat_min_km, jour=None,
                      methode="minetti"):
    """Heure de passage estimée, tronçon et marge de chaque point.

    points_course : [{"nom","km","type","barriere"}] (barriere = « HH:MM » ou vide).
    depart_hhmm   : « 07:00 ». `jour` : date (datetime.date) du départ, sinon aujourd'hui.
    Une barrière qui tombe avant l'heure de départ est comptée le lendemain.
    Retourne la liste triée par km, avec le départ et l'arrivée ajoutés si absents."""
    f = temps_au_km(points, allure_plat_min_km, methode)
    prof = profil(points)
    dist = f.total_km
    h0 = _hhmm(depart_hhmm) or (0, 0)
    base = datetime.combine(jour or datetime.now().date(), datetime.min.time())
    depart = base + timedelta(hours=h0[0], minutes=h0[1])

    pts = [dict(p) for p in points_course]
    if not any(abs(p["km"]) < 0.05 for p in pts):
        pts.append({"nom": "Départ", "km": 0.0, "type": "Repère", "barriere": ""})
    if not any(abs(p["km"] - dist) < 0.3 for p in pts):
        pts.append({"nom": "Arrivée", "km": round(dist, 1), "type": "Repère", "barriere": ""})
    pts.sort(key=lambda p: p["km"])

    out, prec = [], None
    for p in pts:
        km = max(0.0, min(float(p["km"]), dist))
        t = f(km)
        passage = depart + timedelta(seconds=t)
        ligne = {"nom": p["nom"], "km": round(km, 1), "type": p.get("type", "Repère"),
                 "temps_s": round(t), "passage": passage, "barriere_txt": p.get("barriere", "") or "",
                 "barriere": None, "marge_min": None, "statut": None,
                 "troncon_km": 0.0, "troncon_s": 0, "troncon_dplus": 0, "troncon_dmoins": 0}
        hb = _hhmm(p.get("barriere"))
        if hb:
            b = base + timedelta(hours=hb[0], minutes=hb[1])
            while b < depart:
                b += timedelta(days=1)
            ligne["barriere"] = b
            marge = (b - passage).total_seconds() / 60.0
            ligne["marge_min"] = int(round(marge))
            ligne["statut"] = ("depasse" if marge < 0 else "serre" if marge < MARGE_SERREE_MIN else "ok")
        if prec is not None:
            ligne["troncon_km"] = round(km - prec["km"], 1)
            ligne["troncon_s"] = round(t - prec["temps_s"])
            ligne["troncon_dplus"], ligne["troncon_dmoins"] = denivele_entre(prof, prec["km"], km)
        out.append(ligne)
        prec = ligne
    return out


def temps_limite_theorique(passages):
    """Pire marge rencontrée (min) et nom du point, ou (None, None)."""
    marges = [(p["marge_min"], p["nom"]) for p in passages if p["marge_min"] is not None]
    return min(marges) if marges else (None, None)


# ----------------------------------------------------------------------
# NUTRITION PAR TRONÇON (réutilise data/ravitaillement)
# ----------------------------------------------------------------------
def nutrition_par_troncon(passages, temperature_c=15, poids_kg=70, intensite="modere",
                          grand_transpirateur=False):
    """Pour chaque point (sauf le départ) : ce qu'il faut manger / boire sur le tronçon
    qui s'y termine. Les débits (g/h, ml/h, mg/h) viennent du plan de ravitaillement
    de la durée TOTALE, comme dans le Coach du jour."""
    from noyau.course.ravitaillement import plan_ravitaillement, menu_exemple, texte_menu
    if len(passages) < 2:
        return None, []
    duree_h = passages[-1]["temps_s"] / 3600.0
    plan = plan_ravitaillement(duree_h, temperature_c, poids_kg, intensite, grand_transpirateur)
    if not plan:
        return None, []
    g_h, eau_h, na_h = plan["glucides_g_h"], plan["eau_ml_h"], plan["sodium_mg_h"]
    lignes = []
    for p in passages[1:]:
        h = p["troncon_s"] / 3600.0
        if h <= 0:
            continue
        heures, restant, n = [], h, 1
        while restant > 1e-9:
            part = min(1.0, restant)
            heures.append({"heure": n, "duree_h": round(part, 2),
                           "glucides_g": int(round(g_h * part)),
                           "eau_ml": int(round(eau_h * part / 50.0) * 50),
                           "sodium_mg": int(round(na_h * part / 50.0) * 50)})
            restant -= part
            n += 1
        menu = menu_exemple({"heures": heures, "glucides_g_h": g_h})
        total_g = sum(m["glucides_g"] for m in menu)
        total_eau = sum(x["eau_ml"] for x in heures)
        # Tronçon de plus d'une heure : le même menu, à répéter chaque heure (plus lisible).
        if len(menu) == 1:
            texte = texte_menu(menu[0])
        else:
            texte = f"Chaque heure (≈ {len(menu)} h sur ce tronçon) : {texte_menu(menu[0])}"
        lignes.append({"nom": p["nom"], "km": p["km"], "troncon_s": p["troncon_s"],
                       "glucides_g": total_g, "eau_ml": total_eau,
                       "texte": texte or "eau à volonté"})
    return plan, lignes


# ----------------------------------------------------------------------
# CHECKLIST
# ----------------------------------------------------------------------
def construire_checklist(distance_km, denivele_m, nocturne=False, altitude=False, saison=None,
                         plan=None, existante=None):
    """Liste [{texte, section, raison, coche}] : matériel obligatoire / conseillé
    (data/reference_materiel_course), nutrition à emporter (plan), + éléments perso
    déjà présents dans `existante`. Les cases déjà cochées le restent."""
    from noyau.course.reference_materiel_course import calculer_materiel
    r = calculer_materiel(distance_km, denivele_m, nocturne, altitude, saison)
    coche = {(e["section"], e["texte"]): e.get("coche", False) for e in (existante or [])}
    items = []

    def ajout(section, texte, raison=""):
        items.append({"texte": texte, "section": section, "raison": raison,
                      "coche": coche.get((section, texte), False)})

    for nom, raison in r["obligatoire"]:
        ajout("Obligatoire", nom, raison)
    for nom, raison in r["conseille"]:
        ajout("Conseillé", nom, raison)
    if plan:
        rp = plan["repere_pratique"]
        tot = plan["totaux"]
        if rp["gels"]:
            ajout("Nutrition", f"{rp['gels']} gels", "Repère du plan de ravitaillement ; à tester avant.")
        if rp["barres"]:
            ajout("Nutrition", f"{rp['barres']} barres", "Repère du plan de ravitaillement.")
        if rp["boisson_effort_ml"]:
            ajout("Nutrition", f"Boisson d'effort ({rp['boisson_effort_ml']} ml au total)",
                  "À répartir sur les ravitaillements.")
        ajout("Nutrition", f"Électrolytes (≈ {tot['sodium_mg']} mg de sodium sur la course)")
    for e in (existante or []):
        if e["section"] == "Perso":
            ajout("Perso", e["texte"], e.get("raison", ""))
    return items


# ----------------------------------------------------------------------
# ENREGISTREMENT
# ----------------------------------------------------------------------
def creer_table():
    conn = connexion()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS roadbooks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            athlete_id INTEGER,
            nom TEXT NOT NULL,
            date_course TEXT,
            depart TEXT,
            mode_niveau TEXT,
            allure_plat TEXT,
            temps_vise TEXT,
            temperature_c REAL,
            poids_kg REAL,
            intensite TEXT,
            nocturne INTEGER DEFAULT 0,
            altitude INTEGER DEFAULT 0,
            distance_km REAL,
            denivele_m INTEGER,
            trace_json TEXT,
            points_json TEXT,
            checklist_json TEXT,
            date_modif TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()


CHAMPS_TEXTE = ("nom", "date_course", "depart", "mode_niveau", "allure_plat", "temps_vise", "intensite")
CHAMPS_NOMBRE = ("temperature_c", "poids_kg", "distance_km", "denivele_m")


def enregistrer(athlete_id, rb, rb_id=None):
    """rb : dict {nom, date_course, depart, mode_niveau, allure_plat, temps_vise,
    temperature_c, poids_kg, intensite, nocturne, altitude, distance_km, denivele_m,
    trace (liste de points), points (liste de dicts), checklist (liste de dicts)}.
    Retourne l'id."""
    creer_table()
    valeurs = [rb.get(c) for c in CHAMPS_TEXTE + CHAMPS_NOMBRE]
    valeurs += [1 if rb.get("nocturne") else 0, 1 if rb.get("altitude") else 0,
                json.dumps(rb.get("trace") or []), json.dumps(rb.get("points") or [], ensure_ascii=False),
                json.dumps(rb.get("checklist") or [], ensure_ascii=False)]
    cols = list(CHAMPS_TEXTE + CHAMPS_NOMBRE) + ["nocturne", "altitude", "trace_json", "points_json",
                                                  "checklist_json"]
    conn = connexion()
    cur = conn.cursor()
    if rb_id:
        sets = ", ".join(f"{c}=?" for c in cols) + ", date_modif=CURRENT_TIMESTAMP"
        cur.execute(f"UPDATE roadbooks SET {sets} WHERE id=?", (*valeurs, rb_id))
    else:
        cur.execute(f"INSERT INTO roadbooks (athlete_id, {', '.join(cols)}) VALUES (?, {', '.join('?' * len(cols))})",
                    (athlete_id, *valeurs))
        rb_id = cur.lastrowid
    conn.commit()
    conn.close()
    return rb_id


def lister(athlete_id):
    creer_table()
    conn = connexion()
    cur = conn.cursor()
    cur.execute("SELECT id, nom, date_course, distance_km, denivele_m FROM roadbooks "
                "WHERE athlete_id=? ORDER BY COALESCE(date_course,'9999'), id", (athlete_id,))
    r = cur.fetchall()
    conn.close()
    return r


def charger(rb_id):
    creer_table()
    conn = connexion()
    cur = conn.cursor()
    cur.execute("SELECT id, athlete_id, " + ", ".join(CHAMPS_TEXTE + CHAMPS_NOMBRE)
                + ", nocturne, altitude, trace_json, points_json, checklist_json FROM roadbooks WHERE id=?",
                (rb_id,))
    r = cur.fetchone()
    conn.close()
    if not r:
        return None
    noms = ["id", "athlete_id", *CHAMPS_TEXTE, *CHAMPS_NOMBRE, "nocturne", "altitude"]
    d = dict(zip(noms, r[:len(noms)]))
    d["trace"] = json.loads(r[len(noms)] or "[]")
    d["points"] = json.loads(r[len(noms) + 1] or "[]")
    d["checklist"] = json.loads(r[len(noms) + 2] or "[]")
    d["nocturne"], d["altitude"] = bool(d["nocturne"]), bool(d["altitude"])
    return d


def supprimer(rb_id):
    conn = connexion()
    conn.execute("DELETE FROM roadbooks WHERE id=?", (rb_id,))
    conn.commit()
    conn.close()
