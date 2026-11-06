"""
Analyse transversale (chantier E), sans Qt ni SQL.

- Prévu ou réel : chaque résultat de course comparé au temps prévu par le
  roadbook (Stratégie) ; l'écart médian donne un facteur qui corrige les
  estimations suivantes (borné, et seulement si tu l'appliques).
- Bilans du club d'une saison à l'autre : effectif, nouveaux, fidélité,
  femmes et hommes, jeunes, présences, résultats.
- Bilans d'un événement : inscrits, partants, arrivés, abandons, taux de
  finishers, incidents, bénévoles, budget ; comparaison des éditions.
"""

import re
import statistics
import unicodedata

MIN_COURSES_CORRECTION = 2


def lire_temps(t):
    """« 3:12:05 », « 3h12 », « 45:10 » → secondes, ou None."""
    if t in (None, ""):
        return None
    if isinstance(t, (int, float)):
        return float(t)
    t = str(t).strip().lower().replace(" ", "")
    m = re.fullmatch(r"(\d+)h(\d{1,2})?(?:m(?:in)?)?(\d{1,2})?s?", t)
    if m:
        return int(m.group(1)) * 3600 + int(m.group(2) or 0) * 60 + int(m.group(3) or 0)
    p = t.split(":")
    try:
        if len(p) == 3:
            return int(p[0]) * 3600 + int(p[1]) * 60 + float(p[2])
        if len(p) == 2:
            return int(p[0]) * 60 + float(p[1])
    except ValueError:
        return None
    return None


def texte_duree(s):
    if s is None:
        return ""
    s = int(round(s))
    return f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}"


def _norm(t):
    t = unicodedata.normalize("NFKD", str(t or "").lower()).encode("ascii", "ignore").decode()
    t = re.sub(r"\b\d+([.,]\d+)?\s*(km|k)\b", " ", t)
    return set(w for w in re.findall(r"[a-z]{3,}", t) if w not in {"trail", "des", "les", "course", "the", "edition"})


def meme_course(nom_a, date_a, nom_b, date_b):
    """Même jour et au moins un mot commun du nom (hors mots génériques), ou même jour si un nom est vide."""
    if not date_a or not date_b or str(date_a)[:10] != str(date_b)[:10]:
        return False
    a, b = _norm(nom_a), _norm(nom_b)
    return not a or not b or bool(a & b)


def prevu_reel(resultats, previsions):
    """resultats [{id, nom, date, temps}], previsions [{id, nom, date, prevu_s, prudent_s, ambitieux_s}].
    Renvoie (lignes, synthese) ; lignes : {resultat, course, date, reel_s, prevu_s, ecart_s, ecart_pct, scenario}."""
    lignes = []
    for r in resultats:
        reel = lire_temps(r.get("temps"))
        if not reel:
            continue
        p = next((x for x in previsions if meme_course(r["nom"], r["date"], x["nom"], x["date"]) and x.get("prevu_s")), None)
        if not p:
            continue
        ecart = reel - p["prevu_s"]
        sc = "réaliste"
        if p.get("prudent_s") and reel > p["prudent_s"]:
            sc = "plus lent que prudent"
        elif p.get("ambitieux_s") and reel < p["ambitieux_s"]:
            sc = "plus rapide qu'ambitieux"
        elif p.get("prudent_s") and reel > p["prevu_s"]:
            sc = "entre réaliste et prudent"
        elif p.get("ambitieux_s") and reel < p["prevu_s"]:
            sc = "entre ambitieux et réaliste"
        lignes.append({"resultat_id": r["id"], "roadbook_id": p["id"], "course": r["nom"], "date": str(r["date"])[:10],
                       "reel_s": reel, "prevu_s": p["prevu_s"], "ecart_s": ecart,
                       "ecart_pct": round(100 * ecart / p["prevu_s"], 1), "scenario": sc})
    lignes.sort(key=lambda l: l["date"], reverse=True)
    return lignes, synthese(lignes)


def synthese(lignes):
    """Facteur conseillé = médiane des rapports réel / prévu (bornée entre 0,85 et 1,2), dès 2 courses."""
    if not lignes:
        return {"courses": 0, "facteur": None, "texte": "Pas encore de course avec un roadbook et un résultat le même jour."}
    ratios = [l["reel_s"] / l["prevu_s"] for l in lignes]
    med = statistics.median(ratios)
    f = round(min(1.2, max(0.85, med)), 3) if len(lignes) >= MIN_COURSES_CORRECTION else None
    sens = "plus lent" if med > 1 else "plus rapide"
    t = (f"Sur {len(lignes)} course(s), tu as couru en médiane {abs(med - 1) * 100:.0f} % {sens} que prévu."
         + (f" Facteur de correction conseillé : {f:g}.".replace(".", ",", 1) if f else " Il faut au moins 2 courses pour corriger les estimations."))
    return {"courses": len(lignes), "mediane": round(med, 3), "facteur": f, "texte": t,
            "dans_la_fourchette": sum(1 for l in lignes if not l["scenario"].startswith("plus")), }


def evolution(par_saison):
    """par_saison {saison: valeur} → [(saison, valeur, écart avec la saison précédente)] dans l'ordre."""
    res, prec = [], None
    for s in sorted(par_saison):
        v = par_saison[s]
        res.append((s, v, None if prec is None or v is None else round(v - prec, 1)))
        prec = v
    return res


def bilan_evenement(inscrits, partants, arrives, abandons, incidents, benevoles_besoin, benevoles_pourvus,
                    recettes, depenses):
    return {"inscrits": inscrits, "partants": partants, "arrives": arrives, "abandons": abandons,
            "taux_finishers": round(100 * arrives / partants) if partants else None,
            "taux_abandon": round(100 * abandons / partants) if partants else None,
            "incidents": incidents, "benevoles": f"{benevoles_pourvus}/{benevoles_besoin}" if benevoles_besoin else "",
            "solde": round(recettes - depenses, 2), "recette_par_coureur": round(recettes / inscrits, 2) if inscrits else None}


def nom_de_base(nom):
    """« Trail des Dentelles 2027 » et « Trail des Dentelles » : même course (éditions)."""
    return re.sub(r"\s*(\(\w+\)|\b(19|20)\d{2}\b|\b\d+(e|ème|eme)\s+edition\b)", "", str(nom or ""), flags=re.I).strip().lower()
