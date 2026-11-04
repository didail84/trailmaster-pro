"""Tests v104 : qualité des données, meilleurs efforts / vitesse critique, conditions,
polarisation, lien Aujourd'hui <-> coach, regroupement des onglets."""
import json
import os
import sqlite3
from datetime import date, timedelta

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import data.database as db

DEG_M = 1 / 111195.0


def trace(duree_s=2400, vitesse=3.33, rapide=None, fc=150, avec_fc=True):
    """Trace plate 1 point/s ; `rapide` = (debut_s, fin_s, vitesse)."""
    pts, lat, t = [], 44.0, 0
    for i in range(duree_s):
        v = rapide[2] if rapide and rapide[0] <= i < rapide[1] else vitesse
        lat += v * DEG_M
        pts.append([lat, 5.0, 300.0, i, fc if avec_fc else None, 80])
    return pts


@pytest.fixture
def base(tmp_path, monkeypatch):
    chemin = tmp_path / "t.db"
    monkeypatch.setattr(db, "CHEMIN_BDD", chemin)
    db.creer_base_de_donnees()
    c = sqlite3.connect(chemin)
    c.execute("INSERT INTO athletes (id, nom, prenom, age, fc_max, fc_repos) VALUES (1,'T','C',40,185,50)")
    ids = []
    for k in range(24):
        j = date.today() - timedelta(days=3 * (24 - k))
        fc = None if k in (5, 9) else 150 + (k % 3)
        temp = 8 if k % 4 == 0 else 14 if k % 4 == 1 else 21 if k % 4 == 2 else 27
        cur = c.execute(
            "INSERT INTO activites (athlete_id,date,nom,type,distance,denivele,duree,frequence_cardiaque_moyenne,"
            "frequence_cardiaque_max,temperature_moyenne,temps_zone_1,temps_zone_2,temps_zone_3,temps_zone_4,temps_zone_5) "
            "VALUES (1,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (j.isoformat() + " 07:00:00", f"S{k}", "Trail", 10.0, 300, 3600 - k * 10, fc, 175, temp,
             2400, 900, 200, 80, 20))
        ids.append(cur.lastrowid)
    # traces : sortie 5 (sans FC en base) avec FC dans la trace ; sortie 23 avec effort rapide
    c.execute("INSERT INTO parcours_gpx (athlete_id,nom,distance_km,denivele_positif,denivele_negatif,trace_json,activite_id)"
              " VALUES (1,'t5',8,0,0,?,?)", (json.dumps(trace(2400, fc=160)), ids[5]))
    c.execute("INSERT INTO parcours_gpx (athlete_id,nom,distance_km,denivele_positif,denivele_negatif,trace_json,activite_id)"
              " VALUES (1,'t23',9,0,0,?,?)",
              (json.dumps(trace(3000, 3.0, rapide=(600, 900, 4.5))), ids[23]))
    c.commit()
    c.close()
    return ids


def test_qualite_et_reparation(base):
    from data import qualite_donnees as qd
    r = qd.controler(1)
    fc = next(p for p in r["problemes"] if p["code"] == "fc_absente")
    assert fc["nb"] == 2 and fc["recuperables"] == 1
    assert qd.reparer_fc(1) == 1
    conn = sqlite3.connect(db.CHEMIN_BDD)
    assert conn.execute("SELECT frequence_cardiaque_moyenne FROM activites WHERE id=?", (base[5],)).fetchone()[0] == 160
    conn.close()
    fc2 = next(p for p in qd.controler(1)["problemes"] if p["code"] == "fc_absente")
    assert fc2["nb"] == 1 and 0 <= qd.controler(1)["score"] <= 100


def test_meilleurs_efforts_et_cs(base):
    from data import meilleurs_efforts as me
    ef = {e["duree_s"]: e for e in me.meilleurs_par_duree(1)}
    assert 4.3 * 3.6 < ef[300]["vitesse_kmh"] < 4.6 * 3.6 + 0.5      # le bloc rapide de 5 min
    assert ef[60]["vitesse_kmh"] >= ef[1800]["vitesse_kmh"]           # plus court = plus vite
    # CS sur des efforts synthétiques exactement linéaires : d = 4 m/s * t + 200 m
    synth = [{"duree_s": t, "distance_m": 4.0 * t + 200} for t in (180, 300, 600, 1200, 1800)]
    cs = me.vitesse_critique(synth)
    assert abs(cs["cs_kmh"] - 14.4) < 0.01 and cs["d_prime_m"] == 200
    assert me.vitesse_critique(synth[:2]) is None


def test_conditions_et_polarisation(base):
    from data import impact_conditions as ic
    t = ic.impact_temperature(1)
    assert t and len(t["lignes"]) == 4 and all(x["n"] >= 3 for x in t["lignes"])
    p = ic.polarisation(1)
    assert p and abs(sum(p["pct"]) - 100) < 0.5 and p["bas"] > 70
    assert p["modele"] in ("polarisé", "pyramidal")


def test_ecart_avec_plan():
    from data.coach_du_jour import ecart_avec_plan
    seance = {"nom": "Fractionné 10x1'", "type": "Fractionné", "statut": "Prévue"}
    rouge = {"niveau": "rouge", "raisons": ["Jambes très fatiguées (8/10)."]}
    assert "alléger" in ecart_avec_plan(rouge, seance)
    assert ecart_avec_plan({"niveau": "vert", "raisons": []}, seance) is None
    assert ecart_avec_plan(rouge, {"nom": "Footing", "type": "Endurance", "statut": "Prévue"}) is None
    assert ecart_avec_plan(rouge, {**seance, "statut": "Faite"}) is None


def test_aujourdhui_contient_coach(base):
    import data.metriques as met
    d = met.donnees_aujourdhui(1)
    assert d["coach"] and d["coach"]["niveau"] in ("vert", "orange", "rouge")


def test_note_coach_sur_seance(base):
    from interface.ajustement_matinal import noter_conseil_coach
    conn = sqlite3.connect(db.CHEMIN_BDD)
    conn.execute("INSERT INTO suivi_corporel (athlete_id,date,fatigue_jambes) VALUES (1,?,9)", (date.today().isoformat(),))
    conn.execute("INSERT INTO seances_structurees (athlete_id,nom,type_seance,date_prevue,statut,etapes_json) "
                 "VALUES (1,'VMA 8x2','Fractionné',?, 'Prévue','[]')", (date.today().isoformat(),))
    conn.commit(); conn.close()
    msg = noter_conseil_coach(1)
    assert msg and "alléger" in msg
    assert noter_conseil_coach(1) is None          # une seule fois
    conn = sqlite3.connect(db.CHEMIN_BDD)
    assert conn.execute("SELECT commentaire_replanification FROM seances_structurees").fetchone()[0].startswith("🎯")
    conn.close()


def test_ecrans_et_groupes(base):
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    from interface.analyses_et_forme import AnalysesEtForme
    from interface.analyses_avancees import MeilleursEfforts, ControleDonnees, ConditionsIntensite
    f = AnalysesEtForme(athlete_id_initial=1)
    assert f.tabs.count() == 6
    f.selectionner_onglet((2, 4))
    assert f.tabs.currentIndex() == 2 and f.ecrans[2].tabs.currentIndex() == 4
    assert f.ecrans[2].tabs.count() == 6
    c = ControleDonnees(1)
    assert "fréquence" in c.texte.text()
    k = ConditionsIntensite(1)
    assert k.table_t.rowCount() == 4 and k.table_p.rowCount() == 5
    m = MeilleursEfforts(1)
    from data import meilleurs_efforts as me
    ef = me.meilleurs_par_duree(1)
    m._afficher(ef, me.vitesse_critique(ef))
    assert m.table.rowCount() == len(ef) and m.courbe.series
    from interface.performance_et_bilans import BilansObjectifs
    assert BilansObjectifs(athlete_id_initial=1).tabs.count() == 5
