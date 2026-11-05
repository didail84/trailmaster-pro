"""Étape 3 — stratégie de course : temps appris, trois scénarios, sacs d'assistance, bracelet."""
import sqlite3
from datetime import date, datetime, timedelta

import pytest

from noyau.course import strategie as S
from noyau.course import roadbook as rbk
from noyau.course.estimation_temps_course import estimer_temps_course
from tests.conftest import ligne_droite


def trace_vallonnee(km=30):
    """Aller-retour plat puis bosse : ~1 point tous les 50 m."""
    n = int(km * 1000 / 50)
    pts = ligne_droite(44.0, 5.0, n, 50)
    for i, p in enumerate(pts):
        p[2] = 300 + 400 * max(0.0, 1 - abs(i - n / 2) / (n / 4))
    return [tuple(p) for p in pts]


POINTS = [
    {"nom": "Ravito 1", "km": 8, "type": "Ravitaillement", "barriere": ""},
    {"nom": "Base de vie", "km": 15, "type": "Assistance", "barriere": "11:30"},
    {"nom": "Ravito 2", "km": 22, "type": "Ravitaillement", "barriere": ""},
    {"nom": "Col", "km": 26, "type": "Assistance", "barriere": ""},
]


def test_facteurs():
    assert S.facteurs_scenarios() == S.FACTEURS_PAR_DEFAUT
    f = S.facteurs_scenarios(0.9, 1.1)
    assert f["ambitieux"] == 0.9 and f["prudent"] == 1.1 and f["realiste"] == 1.0
    f = S.facteurs_scenarios(0.5, 2.0)                    # dispersion énorme : bornée
    assert f["ambitieux"] == S.BORNES["ambitieux"][0] and f["prudent"] == S.BORNES["prudent"][1]
    f = S.facteurs_scenarios(0.99, 1.01)                  # sorties très régulières : écart minimal gardé
    assert f["ambitieux"] == S.BORNES["ambitieux"][1] and f["prudent"] == S.BORNES["prudent"][0]


def test_trois_scenarios_et_barrieres():
    trace = trace_vallonnee()
    jour = date(2026, 12, 14)
    sc = S.calculer_scenarios(trace, POINTS, "07:00", 4 * 3600, jour)
    assert list(sc) == ["prudent", "realiste", "ambitieux"]
    assert abs(sc["realiste"]["temps_s"] - 4 * 3600) < 120
    assert sc["ambitieux"]["temps_s"] < sc["realiste"]["temps_s"] < sc["prudent"]["temps_s"]
    for code in sc:
        heures = [p["passage"] for p in sc[code]["passages"]]
        assert heures == sorted(heures) and heures[0] == datetime(2026, 12, 14, 7, 0)
    # barrière de 11:30 au km 15 : large en ambitieux, plus serrée en prudent
    marges = {c: next(p["marge_min"] for p in sc[c]["passages"] if p["nom"] == "Base de vie") for c in sc}
    assert marges["ambitieux"] > marges["realiste"] > marges["prudent"]
    etat, phrase = S.verdict_barrieres(sc)
    assert etat in ("ok", "serre", "depasse") and "Base de vie" in phrase
    sc_dur = S.calculer_scenarios(trace, POINTS, "07:00", 9 * 3600, jour)
    assert S.verdict_barrieres(sc_dur)[0] == "depasse"


def test_sacs_d_assistance():
    trace = trace_vallonnee()
    sc = S.calculer_scenarios(trace, POINTS, "16:00", 4 * 3600, date(2026, 12, 14))
    _plan, nutri = rbk.nutrition_par_troncon(sc["realiste"]["passages"], 6)
    sacs = S.sacs_assistance(sc, nutri, 6)
    assert [s["nom"] for s in sacs] == ["Base de vie", "Col"]
    base, col = sacs
    assert base["jusqua"] == "Col" and base["ravitos"] == ["Ravito 2"] and col["jusqua"] == "Arrivée"
    assert base["heures"]["ambitieux"] < base["heures"]["realiste"] < base["heures"]["prudent"]
    assert base["glucides_g"] > 0 and base["eau_ml"] > 0
    attendu = sum(n["glucides_g"] for n in nutri if n["nom"] in ("Ravito 2", "Col"))
    assert base["glucides_g"] == attendu
    texte = " ".join(base["lignes"])
    assert "Frontale" in texte and "Couche chaude" in texte          # départ 16 h, décembre, 6 °C
    sc_matin = S.calculer_scenarios(trace, POINTS, "08:00", 3 * 3600, date(2026, 6, 14))
    _p, n2 = rbk.nutrition_par_troncon(sc_matin["realiste"]["passages"], 20)
    assert not any("Frontale" in l for s in S.sacs_assistance(sc_matin, n2, 20) for l in s["lignes"])
    assert S.sacs_assistance(S.calculer_scenarios(trace, POINTS[:1], "08:00", 3 * 3600), n2) == []


def test_bracelet():
    sc = S.calculer_scenarios(trace_vallonnee(), POINTS, "07:00", 4 * 3600, date(2026, 12, 14))
    lignes = S.lignes_bracelet(sc)
    assert [l["nom"] for l in lignes] == ["Départ", "Ravito 1", "Base de vie", "Ravito 2", "Col", "Arrivée"]
    assert lignes[0]["realiste"] == "07:00" and lignes[2]["barriere"] == "11:30"
    assert lignes[-1]["suite_dplus"] is None and lignes[0]["suite_km"] == 8.0


def test_dispersion_apprise(base_vide):
    c = sqlite3.connect(base_vide)
    auj = date.today()
    for i in range(30):
        km = 8 + i % 12
        dp = 100 * (i % 6)
        duree = (km * 360 + dp * 0.9) * (0.92 + (i % 5) * 0.04)      # ± 8 % autour d'un modèle simple
        c.execute("INSERT INTO activites (athlete_id, date, type, distance, denivele, duree) VALUES (1,?,?,?,?,?)",
                  ((auj - timedelta(days=3 * i + 1)).isoformat(), "Trail", km, dp, duree))
    c.commit()
    c.close()
    est = estimer_temps_course(1, 20, 600)
    assert est["ratio_bas"] < 1 < est["ratio_haut"] and est["nb_sorties_dispersion"] >= 5
    d = S.duree_apprise(1, 20, 600)
    assert d["secondes"] == est["secondes"] and d["facteurs"]["ambitieux"] < 1 < d["facteurs"]["prudent"]
    assert S.duree_apprise(None, 20, 600) is None
