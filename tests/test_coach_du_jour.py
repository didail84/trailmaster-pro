"""Tests v103 : coach du jour, envoi Garmin, prédictions, allure par pente, ravitaillement."""
import os
import sqlite3
from datetime import date, timedelta

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import data.database as db


@pytest.fixture
def base(tmp_path, monkeypatch):
    chemin = tmp_path / "t.db"
    monkeypatch.setattr(db, "CHEMIN_BDD", chemin)
    db.creer_base_de_donnees()
    c = sqlite3.connect(chemin)
    c.execute("INSERT INTO athletes (id, nom, prenom, age, fc_max, fc_repos) VALUES (1,'T','C',40,185,50)")
    for k in range(30):
        j = date.today() - timedelta(days=12 * (30 - k) // 3 + 1)
        c.execute("INSERT INTO activites (athlete_id,date,nom,type,distance,denivele,duree,"
                  "frequence_cardiaque_moyenne,frequence_cardiaque_max) VALUES (1,?,?,?,?,?,?,?,?)",
                  (j.isoformat() + " 07:30:00", f"S{k}", "Trail", 10.0, 300, 4800 - k * 15, 150, 172))
    c.execute("INSERT INTO suivi_corporel (athlete_id,date,poids_kg,fatigue_jambes,fatigue_generale) "
              "VALUES (1,?,84.8,2,3)", (date.today().isoformat(),))
    c.commit()
    c.close()


def test_evaluer_niveaux():
    from data.coach_du_jour import evaluer
    assert evaluer(2, 3, tsb=5)[0] == "vert"
    assert evaluer(5, 7, tsb=-16)[0] == "orange"
    assert evaluer(8, 8, tsb=-30, hrv="basse")[0] == "rouge"
    assert evaluer(1, 1, blessure=True)[0] == "rouge"


def test_coach_du_jour_jambes_2_rpe_3(base):
    from data.coach_du_jour import coach_du_jour
    d = coach_du_jour(1, jambes=None, rpe=3)      # jambes lues dans le suivi (2/10)
    assert d["niveau"] == "vert" and d["etapes"]
    assert any("Jambes fraîches (2/10)" in r for r in d["raisons"])
    assert d["etapes"][0]["allure_cible"] and ":" in d["etapes"][0]["allure_cible"]


def test_repos_sans_etapes(base):
    from data.coach_du_jour import coach_du_jour
    d = coach_du_jour(1, jambes=9, rpe=9)
    assert d["niveau"] in ("orange", "rouge")
    if d["niveau"] == "rouge":
        assert d["etapes"] == []


def test_json_garmin_repetitions():
    from data.garmin_connect import construire_seance_garmin
    etapes = ([{"type": "Échauffement", "mode": "duree", "valeur": 10, "allure_cible": None, "fc_cible": None}]
              + [e for _ in range(4) for e in (
                  {"type": "Effort", "mode": "duree", "valeur": 4, "allure_cible": "4:30", "fc_cible": None},
                  {"type": "Récupération", "mode": "duree", "valeur": 2, "allure_cible": None, "fc_cible": 120})]
              + [{"type": "Retour au calme", "mode": "distance", "valeur": 1.5, "allure_cible": None, "fc_cible": None}])
    w = construire_seance_garmin("Test", etapes)
    pas = w["workoutSegments"][0]["workoutSteps"]
    assert [p["type"] for p in pas] == ["ExecutableStepDTO", "RepeatGroupDTO", "ExecutableStepDTO"]
    groupe = pas[1]
    assert groupe["numberOfIterations"] == 4 and len(groupe["workoutSteps"]) == 2
    effort = groupe["workoutSteps"][0]
    assert effort["targetType"]["workoutTargetTypeKey"] == "pace.zone"
    assert abs(effort["targetValueOne"] - 1000 / 270 * 0.97) < 0.01
    assert groupe["workoutSteps"][1]["targetType"]["workoutTargetTypeKey"] == "heart.rate.zone"
    assert pas[2]["endConditionValue"] == 1500 and pas[0]["endConditionValue"] == 600


def test_envoi_garmin_client_simule():
    from data.garmin_connect import envoyer_seance

    class Faux:
        def __init__(self): self.recu = None
        def upload_workout(self, w): self.recu = w; return {"workoutId": 42}
        def schedule_workout(self, i, d): self.prog = (i, d)
    g = Faux()
    txt = envoyer_seance("S", [{"type": "Effort", "mode": "duree", "valeur": 20}], "2026-10-24", g)
    assert g.recu["workoutName"] == "S" and g.prog == (42, "2026-10-24") and "envoyée" in txt


def test_predictions_coherentes():
    from data import predictions_course as p
    t10, tsemi = p.predire(50, 10), p.predire(50, 21.0975)
    assert 2300 < t10 < 3000 and t10 * 2 < tsemi            # plus long qu'un double 10 km
    assert p.predire(50, 10, 500) > t10                      # le D+ ralentit
    assert p.predire(55, 10) < t10                           # meilleur VO2max, plus rapide
    # aller-retour : le VO2max re-estimé sur la durée prédite redonne la valeur de départ
    from interface.vo2max import estimer_vo2max
    assert abs(estimer_vo2max(10, t10) - 50) < 0.2


def test_pacing_minetti_vs_simple():
    from interface.pacing_segments import calculer_pacing
    segs = [{"distance_km": 1, "denivele_positif": 0, "denivele_negatif": 0, "pente_moyenne_pct": 0.0},
            {"distance_km": 1, "denivele_positif": 100, "denivele_negatif": 0, "pente_moyenne_pct": 10.0},
            {"distance_km": 1, "denivele_positif": 0, "denivele_negatif": 50, "pente_moyenne_pct": -5.0}]
    m, _ = calculer_pacing(segs, 6.0)
    s, _ = calculer_pacing(segs, 6.0, "simple")
    assert m[0]["allure_cible_min_km"] == 6.0
    assert m[1]["allure_cible_min_km"] > s[1]["allure_cible_min_km"] > 6.0
    assert m[2]["allure_cible_min_km"] < 6.0


def test_ravitaillement():
    from data.ravitaillement import plan_ravitaillement
    p = plan_ravitaillement(3.5, 28, 80, "modere")
    assert p["glucides_g_h"] == 65 and p["eau_ml_h"] >= 750 and p["sodium_mg_h"] == 750
    assert len(p["heures"]) == 4 and p["heures"][-1]["duree_h"] == 0.5
    assert plan_ravitaillement(0.75)["glucides_g_h"] == 0
    assert plan_ravitaillement(0) is None


def test_ecran(base):
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    from interface.coach_du_jour import CoachDuJour
    e = CoachDuJour()
    e.spin_rpe.setValue(3)
    e.decider()
    assert e.decision and e.etiquette_niveau.text().startswith("🟢")
    assert e.table_pred.rowCount() == 4 and e.table_ravito.rowCount() >= 3
    e._predire_parcours()
    assert "estimation basse" in e.resultat_parcours.text()


def test_menu_exemple_atteint_la_cible():
    from data.ravitaillement import plan_ravitaillement, menu_exemple, texte_menu
    p = plan_ravitaillement(4, 15, 80, "modere")
    m = menu_exemple(p)
    assert len(m) == 4
    for ligne, h in zip(m, p["heures"]):
        assert abs(ligne["glucides_g"] - h["glucides_g"]) <= 20         # proche de la cible
        assert ligne["items"] and "boisson" in texte_menu(ligne)
    assert len({x for l in m for x in l["items"]}) >= 3                  # de la variété
    assert menu_exemple(plan_ravitaillement(0.75)) [0]["items"] == []    # < 1 h : pas de glucides
    assert menu_exemple(None) == []
