"""
Jour de course (étape 6), sans Qt ni SQL : où en est chaque coureur, qui
n'a pas été vu au point suivant alors qu'il y était attendu, barrières
horaires dépassées, projection de l'heure d'arrivée, bilan pour le
tableau de commandement, carte schématique (SVG, sans Internet).

Les heures attendues viennent de l'allure du coureur depuis le départ
(en km-effort), ou d'une allure de 9 min par km-effort avant son premier
pointage. Ce sont des repères pour le PC course, pas des certitudes.
"""

import html
import math
from datetime import datetime, timedelta

TYPES_POINT = (("pointage", "Point de contrôle"), ("ravito", "Ravitaillement"), ("signaleur", "Poste de signaleur"),
               ("secours", "Poste de secours"))
LIBELLE_POINT = dict(TYPES_POINT)
TYPES_INCIDENT = (("blessure", "Blessure"), ("malaise", "Malaise"), ("perdu", "Coureur perdu ou égaré"),
                  ("abandon", "Abandon"), ("balisage", "Balisage"), ("materiel", "Matériel"), ("securite", "Sécurité, route"),
                  ("autre", "Autre"))
LIBELLE_INCIDENT = dict(TYPES_INCIDENT)
GRAVITES = (("info", "Pour information"), ("moyen", "À traiter"), ("urgent", "Urgent"))
LIBELLE_GRAVITE = dict(GRAVITES)
STATUTS_INCIDENT = (("ouvert", "Ouvert"), ("pris_en_charge", "Pris en charge"), ("clos", "Clos"))
LIBELLE_STATUT_INCIDENT = dict(STATUTS_INCIDENT)
ALLURE_DEFAUT = 540            # secondes par km-effort avant le premier pointage
MARGE_RETARD = 0.25            # 25 % de plus que l'heure attendue…
MARGE_MIN = 20 * 60            # … et au moins 20 minutes


def _dt(iso):
    return datetime.fromisoformat(iso) if iso else None


def _hhmm(dt):
    return dt.strftime("%H:%M") if dt else ""


def cle_point(point_id):
    return f"pc{point_id}"


def km_effort(e):
    return float(e.get("distance_km") or 0) + float(e.get("denivele_m") or 0) / 100


def points_de(epreuve_id, points):
    """Les points de contrôle de l'épreuve, dans l'ordre (aucune épreuve cochée = toutes)."""
    l = [p for p in points if not p.get("epreuve_ids") or epreuve_id in p["epreuve_ids"]]
    return sorted(l, key=lambda p: (p.get("km") or 0, p["id"]))


def _barriere(jour, h):
    if not h:
        return None
    try:
        hh, mm = h.split(":")[:2]
        return datetime.fromisoformat(jour[:10]).replace(hour=int(hh), minute=int(mm))
    except (ValueError, AttributeError):
        return None


def situation(inscrits, epreuves, points, passages, maintenant=None):
    """inscrits [{id, dossard, nom, prenom, epreuve_id, statut_course, temps_corrige_s}], epreuves [{id, nom,
    distance_km, denivele_m, depart_reel, date}], points [{id, nom, km, epreuve_ids, barriere_horaire}],
    passages [{dossard, heure, point}] (non annulés). Renvoie une ligne par coureur : {inscription_id, dossard, nom,
    epreuve, etat, dernier, dernier_heure, km, prochain, attendu, alerte, projection, temps}."""
    m = maintenant or datetime.now()
    eps = {e["id"]: e for e in epreuves}
    vus = {}
    for p in sorted(passages, key=lambda x: x["heure"]):
        if p.get("dossard") is None:
            continue
        vus.setdefault(p["dossard"], {}).setdefault(p["point"], p["heure"])
    res = []
    for i in inscrits:
        if not i.get("dossard"):
            continue
        e = eps.get(i["epreuve_id"])
        if not e:
            continue
        depart = _dt(e.get("depart_reel"))
        pts = points_de(e["id"], points)
        mes = vus.get(i["dossard"], {})
        ke_tot = km_effort(e) or 1
        km_tot = float(e.get("distance_km") or 0) or 1
        ke = lambda km: (km or 0) * ke_tot / km_tot
        l = {"inscription_id": i["id"], "dossard": i["dossard"], "nom": f"{i.get('prenom') or ''} {i['nom']}".strip(),
             "epreuve": e["nom"], "epreuve_id": e["id"], "etat": "", "dernier": "", "dernier_heure": None, "km": 0,
             "prochain": "", "attendu": None, "alerte": None, "projection": None, "temps": None}
        st = i.get("statut_course")
        if st in ("abandon", "disqualifie", "non_partant"):
            l["etat"] = {"abandon": "abandon", "disqualifie": "disqualifié", "non_partant": "non partant"}[st]
            res.append(l)
            continue
        if "arrivee" in mes or i.get("temps_corrige_s"):
            l.update(etat="arrivé", dernier="Arrivée", km=km_tot)
            if "arrivee" in mes:
                l["dernier_heure"] = mes["arrivee"]
                if depart:
                    l["temps"] = int((_dt(mes["arrivee"]) - depart).total_seconds())
            if i.get("temps_corrige_s"):
                l["temps"] = int(i["temps_corrige_s"])
            res.append(l)
            continue
        if not depart:
            l["etat"] = "pas parti"
            res.append(l)
            continue
        passes = [(p, mes[cle_point(p["id"])]) for p in pts if cle_point(p["id"]) in mes]
        dernier = max(passes, key=lambda x: (x[0].get("km") or 0)) if passes else None
        if dernier:
            p, h = dernier
            ecoule = (_dt(h) - depart).total_seconds()
            allure = ecoule / ke(p.get("km")) if ke(p.get("km")) > 0 else ALLURE_DEFAUT
            l.update(dernier=p["nom"], dernier_heure=h, km=p.get("km") or 0)
            base_km, base_h = p.get("km") or 0, _dt(h)
        else:
            allure, base_km, base_h = ALLURE_DEFAUT, 0, depart
            l["dernier"] = "Départ"
            l["dernier_heure"] = e.get("depart_reel")
        suivants = [p for p in pts if (p.get("km") or 0) > base_km]
        prochain = suivants[0] if suivants else None
        km_suiv = prochain.get("km") if prochain else km_tot
        attendu = base_h + timedelta(seconds=allure * max(0.0, ke(km_suiv) - ke(base_km)))
        l["prochain"] = prochain["nom"] if prochain else "Arrivée"
        l["attendu"] = attendu.isoformat(timespec="seconds")
        l["projection"] = (base_h + timedelta(seconds=allure * max(0.0, ke(km_tot) - ke(base_km)))).isoformat(timespec="seconds")
        l["etat"] = "en course"
        marge = max(MARGE_MIN, MARGE_RETARD * (attendu - base_h).total_seconds())
        if m > attendu + timedelta(seconds=marge):
            l["alerte"] = f"pas vu à « {l['prochain']} » (attendu vers {_hhmm(attendu)})"
            l["etat"] = "à chercher"
        b = _barriere(e.get("date") or e.get("depart_reel") or m.isoformat(), prochain.get("barriere_horaire")) if prochain else None
        if b and m > b:
            l["alerte"] = f"barrière de {_hhmm(b)} à « {prochain['nom']} » dépassée"
            l["etat"] = "hors délai"
        res.append(l)
    ordre = {"à chercher": 0, "hors délai": 1, "en course": 2, "pas parti": 3, "arrivé": 4, "abandon": 5, "disqualifié": 6,
             "non partant": 7}
    return sorted(res, key=lambda x: (ordre.get(x["etat"], 9), -(x["km"] or 0), x["dossard"]))


def bilan(lignes):
    c = {}
    for l in lignes:
        c[l["etat"]] = c.get(l["etat"], 0) + 1
    return {"total": len(lignes), "en_course": c.get("en course", 0) + c.get("à chercher", 0) + c.get("hors délai", 0),
            "a_chercher": c.get("à chercher", 0), "hors_delai": c.get("hors délai", 0), "arrives": c.get("arrivé", 0),
            "abandons": c.get("abandon", 0) + c.get("disqualifié", 0), "non_partis": c.get("non partant", 0) + c.get("pas parti", 0)}


def texte_temps(s):
    if s is None:
        return ""
    s = int(s)
    return f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}"


# ------------------------------------------------------------------ carte schématique

def svg_carte(points, coureurs=(), incidents=(), largeur=900, hauteur=320, km_total=None, sombre=False):
    """Carte sans fond de carte (aucune connexion) : avec des coordonnées, les points à leur place (projection
    simple) ; sinon le parcours en ligne, du départ à l'arrivée, les points à leur kilomètre. coureurs :
    [{dossard, km, lat?, lon?, etat}] ; incidents : [{numero, km, lat?, lon?, gravite}]."""
    fond, texte, trait = ("#1b201d", "#e8ece9", "#66bb6a") if sombre else ("#ffffff", "#1d2320", "#2e7d32")
    geo = [p for p in points if p.get("lat") is not None and p.get("lon") is not None]
    e = lambda v: html.escape(str(v))
    marge = 40
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {largeur} {hauteur}" width="{largeur}" height="{hauteur}" '
           f'font-family="Helvetica, Arial, sans-serif" font-size="12"><rect x="0" y="0" width="{largeur}" height="{hauteur}" fill="{fond}"/>']
    couleur = {"à chercher": "#e65100", "hors délai": "#c62828", "en course": "#1976d2", "arrivé": "#2e7d32"}
    if len(geo) >= 2:
        lats = [p["lat"] for p in geo] + [c["lat"] for c in coureurs if c.get("lat") is not None]
        lons = [p["lon"] for p in geo] + [c["lon"] for c in coureurs if c.get("lon") is not None]
        la0, la1, lo0, lo1 = min(lats), max(lats), min(lons), max(lons)
        k = math.cos(math.radians((la0 + la1) / 2))
        dx, dy = max((lo1 - lo0) * k, 1e-6), max(la1 - la0, 1e-6)
        ech = min((largeur - 2 * marge) / dx, (hauteur - 2 * marge) / dy)
        xy = lambda la, lo: (marge + (lo - lo0) * k * ech, hauteur - marge - (la - la0) * ech)
        ordre = sorted(geo, key=lambda p: p.get("km") or 0)
        out.append('<polyline fill="none" stroke="%s" stroke-width="3" stroke-dasharray="6 4" points="%s"/>'
                   % (trait, " ".join("%.1f,%.1f" % xy(p["lat"], p["lon"]) for p in ordre)))
        for p in ordre:
            x, y = xy(p["lat"], p["lon"])
            out.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="7" fill="{trait}"/><text x="{x + 10:.1f}" y="{y - 8:.1f}" '
                       f'fill="{texte}">{e(p["nom"])}</text>')
        for c in coureurs:
            if c.get("lat") is not None:
                x, y = xy(c["lat"], c["lon"])
                out.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4" fill="{couleur.get(c.get("etat"), "#1976d2")}"><title>'
                           f'{e(c["dossard"])}</title></circle>')
        for i in incidents:
            if i.get("lat") is not None:
                x, y = xy(i["lat"], i["lon"])
                out.append(f'<text x="{x:.1f}" y="{y:.1f}" font-size="18" text-anchor="middle" fill="#e65100">⚠</text>')
    else:
        kt = km_total or max([p.get("km") or 0 for p in points] + [c.get("km") or 0 for c in coureurs] + [1])
        y0 = hauteur / 2
        X = lambda km: marge + (largeur - 2 * marge) * min(1, max(0, (km or 0) / kt))
        out.append(f'<line x1="{marge}" y1="{y0}" x2="{largeur - marge}" y2="{y0}" stroke="{trait}" stroke-width="4"/>')
        out.append(f'<text x="{marge}" y="{y0 + 34}" fill="{texte}">Départ</text><text x="{largeur - marge}" y="{y0 + 34}" '
                   f'text-anchor="end" fill="{texte}">Arrivée · {kt:g} km</text>')
        for n, p in enumerate(sorted(points, key=lambda p: p.get("km") or 0)):
            x = X(p.get("km"))
            dy = -26 if n % 2 == 0 else 46
            out.append(f'<circle cx="{x:.1f}" cy="{y0}" r="8" fill="{trait}"/><text x="{x:.1f}" y="{y0 + dy}" text-anchor="middle" '
                       f'fill="{texte}">{e(p["nom"])} · km {p.get("km") or 0:g}</text>')
        par_km = {}
        for c in coureurs:
            if c.get("etat") in ("en course", "à chercher", "hors délai"):
                k = round(c.get("km") or 0, 1)
                par_km.setdefault(k, []).append(c)
        for k, cs in par_km.items():
            x = X(k)
            for j, c in enumerate(cs[:12]):
                out.append(f'<circle cx="{x:.1f}" cy="{y0 - 14 - j * 9}" r="4" fill="{couleur.get(c["etat"], "#1976d2")}">'
                           f'<title>{e(c["dossard"])}</title></circle>')
            if len(cs) > 12:
                out.append(f'<text x="{x + 8:.1f}" y="{y0 - 14 - 12 * 9}" fill="{texte}">+{len(cs) - 12}</text>')
        for i in incidents:
            if i.get("km") is not None:
                out.append(f'<text x="{X(i["km"]):.1f}" y="{y0 + 70}" font-size="18" text-anchor="middle" fill="#e65100">⚠</text>'
                           f'<text x="{X(i["km"]):.1f}" y="{y0 + 86}" font-size="10" text-anchor="middle" fill="{texte}">'
                           f'n°{e(i.get("numero") or "")}</text>')
    out.append("</svg>")
    return "".join(out)


def lire_positions(contenu, nom_fichier="positions.csv", dossard=None):
    """Positions des coureurs : CSV « dossard;heure;lat;lon » (export d'un traceur) ou GPX d'un coureur (dossard
    donné). Renvoie [(dossard, heure ISO, lat, lon)]."""
    import re
    texte = contenu.decode("utf-8", "replace") if isinstance(contenu, bytes) else contenu
    res = []
    if nom_fichier.lower().endswith(".gpx") or "<gpx" in texte[:500]:
        if dossard is None:
            raise ValueError("Pour un GPX, indique le dossard du coureur.")
        for m in re.finditer(r'<trkpt[^>]*lat="([-0-9.]+)"[^>]*lon="([-0-9.]+)"[^>]*>(.*?)</trkpt>', texte, re.S):
            t = re.search(r"<time>([^<]+)</time>", m.group(3))
            if t:
                h = t.group(1).replace("Z", "+00:00")
                try:
                    d = datetime.fromisoformat(h)
                    if d.tzinfo:
                        d = d.astimezone().replace(tzinfo=None)
                    res.append((int(dossard), d.isoformat(timespec="seconds"), float(m.group(1)), float(m.group(2))))
                except ValueError:
                    continue
        return res
    for l in texte.splitlines():
        sep = ";" if ";" in l else ("\t" if "\t" in l else ",")
        champs = [x.strip() for x in l.split(sep)]
        if len(champs) < 4 or not champs[0].isdigit():
            continue
        try:
            h = datetime.fromisoformat(champs[1].replace("Z", "+00:00").replace(" ", "T"))
            if h.tzinfo:
                h = h.astimezone().replace(tzinfo=None)
            res.append((int(champs[0]), h.isoformat(timespec="seconds"), float(champs[2].replace(",", ".")),
                        float(champs[3].replace(",", "."))))
        except ValueError:
            continue
    return res
