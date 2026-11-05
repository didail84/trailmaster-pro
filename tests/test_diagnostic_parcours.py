"""Étape 3.2 : diagnostic de difficulté d'un tracé et comparaison de deux tracés."""
import json
import sqlite3

from conftest import DEG_LAT_PAR_M
from noyau.traces import diagnostic_parcours as dg


def trace_profil(segments, pas_m=25.0):
    """Trace nord-sud ; segments = [(longueur_m, pente)] enchaînés."""
    pts, d, alt = [[45.0, 6.0, 500.0]], 0.0, 500.0
    for longueur, pente in segments:
        for _ in range(int(longueur / pas_m)):
            d += pas_m
            alt += pente * pas_m
            pts.append([45.0 + d * DEG_LAT_PAR_M, 6.0, alt])
    return pts


def test_categories_itra_et_terrain():
    assert dg.categorie_itra(10) == "XXS"
    assert dg.categorie_itra(44.9) == "XS"
    assert dg.categorie_itra(80) == "M"
    assert dg.categorie_itra(250) == "XXL"
    assert dg.terrain(10) == "Roulant"
    assert dg.terrain(40) == "Montagneux"


def test_plat_sans_montee():
    d = dg.diagnostiquer(trace_profil([(10000, 0.0)]), "Plat")
    assert abs(d["distance_km"] - 10) < 0.1
    assert d["dplus_m"] < 5
    assert d["montees"] == []
    plat = next(r for r in d["repartition_pentes"] if r["code"] == "plat")
    assert plat["pct"] > 95
    assert d["categorie_itra"] == "XXS"
    assert d["note_technicite"] < 0.5


def test_montee_detectee_et_bornee():
    # 3 km plat, 2 km à 20 %, 3 km plat : la montée commence au km 3 et fait 400 m
    d = dg.diagnostiquer(trace_profil([(3000, 0.0), (2000, 0.20), (3000, 0.0)]))
    assert len(d["montees"]) == 1
    m = d["montees"][0]
    assert 2.7 <= m["km_debut"] <= 3.3
    assert 360 <= m["gain_m"] <= 410
    assert 17 <= m["pente_pct"] <= 21
    raide = next(r for r in d["repartition_pentes"] if r["code"] == "montee_raide")
    assert 18 <= raide["pct"] <= 32
    assert d["pente_max_1km_pct"] >= 17
    assert abs(sum(r["pct"] for r in d["repartition_pentes"]) - 100) < 1.5


def test_quarts_et_placement_du_denivele():
    fin = dg.diagnostiquer(trace_profil([(6000, 0.0), (2000, 0.12)]))
    assert fin["part_dplus_seconde_moitie_pct"] >= 90
    assert fin["quarts"][-1]["dplus"] > fin["quarts"][0]["dplus"]
    debut = dg.diagnostiquer(trace_profil([(2000, 0.12), (6000, 0.0)]))
    assert debut["part_dplus_seconde_moitie_pct"] <= 10
    assert fin["placement_denivele"] != debut["placement_denivele"]
    assert len(fin["quarts"]) == 4


def test_descente_raide_et_technicite():
    d = dg.diagnostiquer(trace_profil([(2000, 0.30), (2000, -0.25)]))
    assert d["descentes"] and d["descentes"][0]["perte_m"] > 400
    assert d["note_technicite"] > 2
    assert any("25 %" in t for t in d["technicite"])


def test_trace_sans_altitude():
    pts = [[45.0 + i * 0.0002, 6.0] for i in range(200)]
    assert dg.diagnostiquer(pts) is None
    assert dg.diagnostiquer([]) is None


def test_comparaison():
    a = dg.diagnostiquer(trace_profil([(10000, 0.0)]), "Roulant")
    b = dg.diagnostiquer(trace_profil([(4000, 0.0), (3000, 0.18), (3000, -0.18)]), "Montagne")
    c = dg.comparer(a, b)
    mesures = [l[0] for l in c["lignes"]]
    assert "Km-effort" in mesures and "Catégorie ITRA" in mesures
    assert all(len(l) == 4 for l in c["lignes"])
    assert c["phrases"] and any("Montagne" in p for p in c["phrases"])
    assert isinstance(dg.resume(b), str) and "ITRA" in dg.resume(b)


def test_ecran_diagnostic(base_vide, qapp=None):
    """L'écran s'ouvre, lit un parcours de la bibliothèque et compare."""
    import data.database as db
    from PySide6.QtWidgets import QApplication
    import shiboken6
    app = QApplication.instance() or QApplication([])
    c = sqlite3.connect(db.CHEMIN_BDD)
    for nom, segs in (("Boucle plate", [(10000, 0.0)]), ("Grosse bosse", [(3000, 0.0), (3000, 0.2), (3000, -0.2)])):
        c.execute("INSERT INTO parcours_gpx (athlete_id, nom, distance_km, trace_json) VALUES (1, ?, 10, ?)",
                  (nom, json.dumps(trace_profil(segs))))
    c.commit()
    c.close()
    from interface.diagnostic_parcours import DiagnosticParcours
    e = DiagnosticParcours(1)
    ca, cb = e._combos["A"], e._combos["B"]
    assert ca.count() == 3
    ca.setCurrentIndex(1)
    assert e._diags["A"] is not None
    assert e.cartes["itra"].valeur.text() in ("XXS", "XS")
    cb.setCurrentIndex(2)
    assert e._diags["B"] is not None
    assert e.table_cmp.rowCount() > 3
    assert not e.cadre_comparaison.isHidden()
    cb.setCurrentIndex(0)
    assert e.cadre_comparaison.isHidden()
    app.processEvents()
    shiboken6.delete(e)
