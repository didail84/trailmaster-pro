"""Tests v108 : Roadbook course (temps de passage, barrières, nutrition, checklist, PDF, écran)."""
import math
import os
import sqlite3
from datetime import date

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import data.database as db
import data.roadbook as rb


def _gpx(chemin, km=30.0, avec_wpt=True):
    """GPX synthétique : ligne est-ouest, montée puis descente (≈ 900 m de D+)."""
    n = int(km * 20)
    pts = []
    for i in range(n + 1):
        d = km * i / n
        lon = 6.0 + d / (111.32 * math.cos(math.radians(45.0)))
        alt = 400 + 450 * math.sin(math.pi * d / km) ** 2 + 20 * math.sin(d * 3)
        pts.append(f'<trkpt lat="45.0" lon="{lon:.6f}"><ele>{alt:.1f}</ele></trkpt>')
    wpt = ""
    if avec_wpt:
        lon15 = 6.0 + 15 / (111.32 * math.cos(math.radians(45.0)))
        wpt = f'<wpt lat="45.0" lon="{lon15:.6f}"><name>Ravito du col</name></wpt>'
    open(chemin, "w").write('<?xml version="1.0"?><gpx version="1.1" creator="t" '
                            'xmlns="http://www.topografix.com/GPX/1/1">' + wpt
                            + '<trk><trkseg>' + "".join(pts) + '</trkseg></trk></gpx>')


@pytest.fixture
def base(tmp_path, monkeypatch):
    chemin = tmp_path / "t.db"
    monkeypatch.setattr(db, "CHEMIN_BDD", chemin)
    db.creer_base_de_donnees()
    c = sqlite3.connect(chemin)
    c.execute("INSERT INTO athletes (nom, prenom) VALUES ('T', 'C')")
    c.commit()
    aid = c.execute("SELECT id FROM athletes").fetchone()[0]
    c.close()
    return chemin, aid


@pytest.fixture
def gpx(tmp_path):
    f = tmp_path / "course.gpx"
    _gpx(str(f))
    return str(f)


def test_charger_gpx_et_waypoints(gpx):
    t = rb.charger_gpx(gpx)
    assert 29.5 < t["distance_km"] < 30.5
    assert t["denivele_m"] > 300
    assert t["waypoints"] and t["waypoints"][0][0] == "Ravito du col"
    assert 14.5 < t["waypoints"][0][1] < 15.5


def test_allure_calibree_donne_la_duree_voulue(gpx):
    t = rb.charger_gpx(gpx)
    al = rb.allure_plat_pour_duree(t["points"], 4 * 3600)
    f = rb.temps_au_km(t["points"], al)
    assert abs(f.total_s - 4 * 3600) < 90          # arrondis des segments
    assert f(15) < f.total_s and f(0) == 0


def test_passages_marges_et_statuts(gpx):
    t = rb.charger_gpx(gpx)
    al = rb.allure_plat_pour_duree(t["points"], 4 * 3600)
    pts = [{"nom": "R1", "km": 10, "type": "Ravitaillement", "barriere": "14:00"},   # large
           {"nom": "R2", "km": 20, "type": "Ravitaillement", "barriere": "08:15"},   # trop juste/dépassée
           {"nom": "B", "km": 25, "type": "Barrière horaire", "barriere": ""}]
    ps = rb.calculer_passages(t["points"], pts, "07:00", al, date(2026, 11, 7))
    noms = [p["nom"] for p in ps]
    assert noms[0] == "Départ" and noms[-1] == "Arrivée"
    r1 = next(p for p in ps if p["nom"] == "R1")
    r2 = next(p for p in ps if p["nom"] == "R2")
    assert r1["statut"] == "ok" and r1["marge_min"] > 60
    assert r2["statut"] == "depasse" and r2["marge_min"] < 0
    assert ps[-1]["passage"].hour in (10, 11)
    assert sum(p["troncon_s"] for p in ps) == ps[-1]["temps_s"]
    pire, nom = rb.temps_limite_theorique(ps)
    assert nom == "R2" and pire < 0


def test_barriere_apres_minuit(gpx):
    t = rb.charger_gpx(gpx)
    al = rb.allure_plat_pour_duree(t["points"], 3 * 3600)
    ps = rb.calculer_passages(t["points"], [{"nom": "Fin", "km": 30, "type": "Barrière horaire", "barriere": "02:00"}],
                              "22:00", al, date(2026, 11, 7))
    fin = next(p for p in ps if p["nom"] == "Fin")
    assert fin["marge_min"] is not None and 50 < fin["marge_min"] < 70     # 02:00 = lendemain, ≈ 1 h de marge


def test_serre_sous_30_minutes(gpx):
    t = rb.charger_gpx(gpx)
    al = rb.allure_plat_pour_duree(t["points"], 4 * 3600)
    f = rb.temps_au_km(t["points"], al)
    h = 7 * 3600 + f(20) + 15 * 60                      # barrière 15 min après le passage
    barriere = f"{int(h // 3600):02d}:{int(h % 3600 // 60):02d}"
    ps = rb.calculer_passages(t["points"], [{"nom": "X", "km": 20, "type": "Barrière horaire", "barriere": barriere}],
                              "07:00", al, date(2026, 11, 7))
    x = next(p for p in ps if p["nom"] == "X")
    assert x["statut"] == "serre" and 5 <= x["marge_min"] <= 25


def test_nutrition_par_troncon_reutilise_le_plan(gpx):
    t = rb.charger_gpx(gpx)
    al = rb.allure_plat_pour_duree(t["points"], 4 * 3600)
    ps = rb.calculer_passages(t["points"], [{"nom": "R1", "km": 10, "type": "Ravitaillement", "barriere": ""},
                                            {"nom": "R2", "km": 20, "type": "Ravitaillement", "barriere": ""}],
                              "07:00", al, date(2026, 11, 7))
    plan, lignes = rb.nutrition_par_troncon(ps, 15, 70, "modere")
    from data.ravitaillement import plan_ravitaillement
    ref = plan_ravitaillement(ps[-1]["temps_s"] / 3600.0, 15, 70, "modere")
    assert plan["glucides_g_h"] == ref["glucides_g_h"]
    assert len(lignes) == 3 and all(l["texte"] for l in lignes)
    total_g = sum(l["glucides_g"] for l in lignes)
    assert abs(total_g - ref["totaux"]["glucides_g"]) < 0.2 * ref["totaux"]["glucides_g"] + 15


def test_checklist_garde_les_cases_cochees(gpx):
    from data.ravitaillement import plan_ravitaillement
    plan = plan_ravitaillement(4.0, 15, 70, "modere")
    liste = rb.construire_checklist(30, 900, False, False, None, plan)
    sections = {i["section"] for i in liste}
    assert {"Obligatoire", "Conseillé", "Nutrition"} <= sections
    liste[0]["coche"] = True
    liste.append({"texte": "Bâtons", "section": "Perso", "raison": "", "coche": True})
    nouvelle = rb.construire_checklist(30, 900, True, False, None, plan, liste)      # + nuit
    assert nouvelle[0]["coche"] is True
    assert any(i["texte"] == "Bâtons" and i["coche"] for i in nouvelle)
    assert len(nouvelle) >= len(liste) - 1


def test_enregistrement_aller_retour(base, gpx):
    chemin, aid = base
    t = rb.charger_gpx(gpx)
    rid = rb.enregistrer(aid, {"nom": "Ma course", "date_course": "2026-11-07", "depart": "07:00",
                               "mode_niveau": "temps", "allure_plat": "6:00", "temps_vise": "4:00",
                               "temperature_c": 12.0, "poids_kg": 70.0, "intensite": "modere",
                               "nocturne": True, "distance_km": t["distance_km"], "denivele_m": t["denivele_m"],
                               "trace": t["points"], "points": [{"nom": "R1", "km": 10, "type": "Ravitaillement",
                                                                  "barriere": "14:00"}],
                               "checklist": [{"texte": "Bâtons", "section": "Perso", "raison": "", "coche": True}]})
    assert [r[1] for r in rb.lister(aid)] == ["Ma course"]
    d = rb.charger(rid)
    assert d["nocturne"] is True and d["points"][0]["barriere"] == "14:00" and len(d["trace"]) > 100
    rb.enregistrer(aid, {**d, "nom": "Renommée"}, rid)
    assert rb.lister(aid)[0][1] == "Renommée" and len(rb.lister(aid)) == 1
    rb.supprimer(rid)
    assert rb.lister(aid) == []


def test_fiche_pdf(base, gpx, tmp_path):
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    from interface.roadbook_fiche import rendre_fiche_pdf
    t = rb.charger_gpx(gpx)
    al = rb.allure_plat_pour_duree(t["points"], 4 * 3600)
    pts = [{"nom": f"Ravito {i}", "km": 5 * i, "type": "Ravitaillement", "barriere": "12:00" if i == 3 else ""}
           for i in range(1, 6)]
    ps = rb.calculer_passages(t["points"], pts, "07:00", al, date(2026, 11, 7))
    plan, nutri = rb.nutrition_par_troncon(ps)
    liste = rb.construire_checklist(30, 900, True, True, "Hiver", plan)
    sortie = tmp_path / "fiche.pdf"
    pages = rendre_fiche_pdf(str(sortie), {"nom": "Trail test", "date_course": "07/11/2026", "depart": "07:00",
                                           "distance_km": 30, "denivele_m": 900, "temps_total_s": ps[-1]["temps_s"]},
                             ps, rb.profil(t["points"]), nutri, liste)
    assert sortie.read_bytes()[:4] == b"%PDF" and sortie.stat().st_size > 5000
    assert pages >= 2


def test_ecran_complet(base, gpx, monkeypatch, tmp_path):
    chemin, aid = base
    from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *a, **k: (gpx, ""))
    sortie = tmp_path / "x.pdf"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: (str(sortie), ""))
    from interface.roadbook import RoadbookCourse
    e = RoadbookCourse(athlete_id_initial=aid)
    e.combo_mode.setCurrentIndex(e.combo_mode.findData("temps"))
    e.champ_temps.setText("4:00")
    e._charger_gpx()
    assert e._trace and e._points                                # point du GPX repris
    e._ravitos_reguliers()
    assert any(p["type"] == "Ravitaillement" for p in e._points)
    assert e.table.rowCount() >= 3
    assert e.table_nutri.rowCount() >= 2
    assert e.liste_check.count() > 5
    e._points[0]["barriere"] = "07:30"
    e._recalculer()
    assert "⚠️" in e.label_marges.text()
    e._points[0]["barriere"] = "20:00"
    e._recalculer()
    assert "✅" in e.label_marges.text()
    e.champ_perso.setText("Bâtons")
    e._ajouter_perso()
    e.champ_nom.setText("Trail du test")
    e._enregistrer()
    assert [r[1] for r in rb.lister(aid)] == ["Trail du test"]
    e._exporter_pdf()
    assert sortie.exists()
    # recharge depuis la liste
    e2 = RoadbookCourse(athlete_id_initial=aid)
    e2.combo_rb.setCurrentIndex(1)
    assert e2.champ_nom.text() == "Trail du test" and e2._points and any(
        i["texte"] == "Bâtons" for i in e2._checklist)
    e.close(); e2.close()


def test_depuis_courses_a_venir(base):
    chemin, aid = base
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    from interface.roadbook import RoadbookCourse
    e = RoadbookCourse(athlete_id_initial=aid, course_preselectionnee={
        "nom": "Trail du Mont", "date": "2026-11-15", "distance_km": 42, "denivele_m": 2200})
    assert e.champ_nom.text() == "Trail du Mont" and e._distance == 42
    assert any(i["section"] == "Obligatoire" for i in e._checklist)
    e.close()
