"""Étape 3.5 : fractionné court ou long, à plat ou en côte."""
import json
import random
import sqlite3

import pytest

from conftest import DEG_LAT_PAR_M
from noyau.entrainement import fractionne as fr


def _trace(phases, pente=0.0, graine=1):
    """phases : [(vitesse m/s, durée s, effort?)] ; un point par seconde vers le nord."""
    rnd = random.Random(graine)
    pts, t, d, alt = [], 0, 0.0, 300.0
    for v, duree, effort in phases:
        for _ in range(int(duree)):
            t += 1
            d += v + rnd.uniform(-0.1, 0.1)
            if pente:
                alt += v * pente if effort else -v * pente * 1.2
            pts.append([45 + d * DEG_LAT_PAR_M, 6.0, alt, t, 170 if effort else 125])
    return pts


def test_bibliotheque_complete_et_valide():
    cats = {(s["format"], s["terrain"]) for s in fr.BIBLIOTHEQUE}
    assert cats == {("court", "plat"), ("long", "plat"), ("court", "cote"), ("long", "cote")}
    for s in fr.BIBLIOTHEQUE:
        assert fr.verifier_structure(s) is None, s["code"]
        c = fr.cibles(s, 15)
        assert c["lignes"] and c["duree_totale_s"] > c["temps_effort_s"] > 0
        assert fr.resume(s)
        assert fr.etapes_montre(s, 15)


def test_cibles_depuis_la_vma():
    s = fr.modele("10x400")
    c = fr.cibles(s, 15)
    assert len(c["lignes"]) == 10
    assert c["lignes"][0]["temps_s"] == 96.0 and c["lignes"][0]["allure"] == "4:00/km"
    assert c["distance_effort_m"] == 4000
    assert fr.temps_de_passage(15)[:4] == [(100, 24.0), (200, 48.0), (300, 72.0), (400, 96.0)]
    trente = fr.cibles(fr.modele("30_30"), 15)
    assert len(trente["lignes"]) == 20 and trente["lignes"][0]["distance_m"] == 125
    # en côte, la même intensité donne une vitesse plus lente, d'autant plus que la pente est raide
    cote = fr.cible_repetition(fr.modele("c5x3min")["blocs"][0], 15, "cote")
    assert cote["vitesse_kmh"] < cote["vitesse_plat_kmh"] == 13.5
    assert cote["dplus_m"] == round(cote["distance_m"] * 0.07)
    raide = fr.cible_repetition({**fr.modele("c5x3min")["blocs"][0], "pente_pct": 15}, 15, "cote")
    assert raide["vitesse_kmh"] < cote["vitesse_kmh"]
    assert fr.tableau_allures(15)[4][0] == 100


def test_deroule_et_montre():
    s = fr.modele("30_30")
    ph = fr.deroule(s, 15)
    assert ph[0]["phase"] == "echauffement" and ph[-1]["phase"] == "retour"
    efforts = [p for p in ph if p["phase"] == "effort"]
    assert len(efforts) == 20
    # entre les deux séries : la récupération longue (3 min)
    recups = [p["duree_s"] for p in ph if p["phase"] == "recup"]
    assert recups.count(180) == 1 and recups.count(30) == 18
    et = fr.etapes_montre(fr.modele("10x400"), 15)
    assert et[1] == {"type": "Effort", "mode": "distance", "valeur": 0.4, "allure_cible": "4:00", "fc_cible": None}
    cote = fr.etapes_montre(fr.modele("c10x30"), 15)
    assert all(e["allure_cible"] is None for e in cote)            # en côte : à la sensation
    from noyau.entrainement.export_fit_seance import encoder_seance
    assert encoder_seance("10x400", et)[8:12] == b".FIT"


def test_lecture_des_temps():
    assert fr.lire_temps("1:32") == 92
    assert fr.lire_temps("1'32") == 92
    assert fr.lire_temps("92,5") == 92.5
    assert fr.lire_temps("1:02:10") == 3730
    assert fr.lire_temps("") is None and fr.lire_temps("abc") is None and fr.lire_temps("-3") is None
    assert fr.texte_temps(45.25) == "45,2 s" or fr.texte_temps(45.25) == "45,3 s"
    assert fr.texte_temps(96) == "1:36" and fr.texte_temps(3730) == "1 h 02:10"
    assert fr.duree_courte(90) == "1 min 30" and fr.duree_courte(180) == "3 min"


def test_analyse_des_temps():
    s = fr.modele("10x400")
    regulier = [{"numero": i + 1, "temps_s": 96} for i in range(10)]
    a = fr.analyser(s, 15, regulier)
    assert a["verdict"] == "Dans la cible" and a["pct_vma_moyen"] == 100 and a["regularite_cv"] == 0
    rapide = fr.analyser(s, 15, [{"numero": i + 1, "temps_s": 88} for i in range(10)])
    assert rapide["verdict"] == "Plus vite que prévu" and any("sous-estimée" in c for c in rapide["conseils"])
    craque = fr.analyser(s, 15, [{"numero": i + 1, "temps_s": 92 + i * 1.5} for i in range(10)])
    assert craque["baisse_fin_pct"] < -5 and any("Baisse" in c for c in craque["conseils"])
    partiel = fr.analyser(s, 15, regulier[:6])
    assert any("6 répétitions sur 10" in c for c in partiel["conseils"])
    assert fr.analyser(s, 15, [])["nb"] == 0
    assert fr.estimer_vma(s, rapide) == pytest.approx(16.4, abs=0.1)
    # répétitions en durée : la distance parcourue
    t = fr.modele("30_30")
    d = fr.analyser(t, 15, [{"numero": i + 1, "distance_m": 125} for i in range(20)])
    assert d["nb"] == 20 and d["pct_vma_moyen"] == 100
    # en côte, le D+ réel corrige le % de VMA (même vitesse, pente plus forte = effort plus dur)
    c = fr.modele("c5x3min")
    faible = fr.analyser(c, 15, [{"numero": 1, "distance_m": 470, "dplus_m": 20}])
    fort = fr.analyser(c, 15, [{"numero": 1, "distance_m": 470, "dplus_m": 45}])
    assert fort["pct_vma_moyen"] > faible["pct_vma_moyen"]
    assert fort["lignes"][0]["vitesse_ascension_mh"] == 900


def test_detection_dans_la_trace():
    temps = [97, 95, 98, 94, 96, 98, 97, 99, 100, 101]
    ph = [(3, 600, False)]
    for x in temps:
        ph += [(400 / x, x, True), (2.2, 90, False)]
    ph += [(3, 600, False)]
    det = fr.detecter(_trace(ph), fr.modele("10x400"))
    assert [d["numero"] for d in det] == list(range(1, 11))
    for d, x in zip(det, temps):
        assert abs(d["temps_s"] - x) <= 3 and abs(d["distance_m"] - 400) <= 8 and d["fc"] >= 160
    # pyramide : les deux 400 m restent à leur place
    ph = [(3, 600, False)]
    for dist in (200, 400, 600, 800, 600, 400, 200):
        ph += [(4.3, dist / 4.3, True), (2.2, 90, False)]
    det = fr.detecter(_trace(ph, graine=2), fr.modele("pyramide"))
    debuts = [d["debut_s"] for d in det]
    assert debuts == sorted(debuts) and [round(d["distance_m"], -2) for d in det] == [200, 400, 600, 800, 600, 400, 200]
    # en côte : les montées, pas les descentes (plus rapides)
    ph = [(3, 600, False)]
    for _ in range(5):
        ph += [(2.6, 180, True), (3.4, 150, False)]
    det = fr.detecter(_trace(ph, 0.07, 3), fr.modele("c5x3min"))
    assert len(det) == 5 and all(d["dplus_m"] > 25 for d in det)
    assert fr.detecter([[45, 6, 300, 1]] * 5, fr.modele("10x400")) == []


def test_verification_des_seances():
    s = fr.modele("10x400")
    assert fr.verifier_structure({**s, "nom": " "})
    assert fr.verifier_structure({**s, "terrain": "sable"})
    mauvais = json.loads(json.dumps(s))
    mauvais["blocs"][0]["pct_vma"] = 200
    assert "130" in fr.verifier_structure(mauvais)


def test_base_seances_et_realises(base_vide):
    import data.database as db
    from noyau.donnees import fractionnes as dfr
    c = sqlite3.connect(db.CHEMIN_BDD)
    c.execute("UPDATE athletes SET vma=15.5 WHERE id=1")
    c.execute("INSERT INTO activites (id, athlete_id, date, nom, type, distance, duree) "
              "VALUES (7, 1, '2026-11-03 18:00:00', 'Piste', 'Course', 9, 3600)")
    c.commit()
    c.close()
    assert dfr.vma_de_reference(1) == (15.5, "de ta fiche")
    perso = json.loads(json.dumps(fr.modele("6x1000")))
    perso["nom"] = "Mes 8 × 1000"
    perso["blocs"][0]["repetitions"] = 8
    pid = dfr.enregistrer_perso(1, perso)
    seances = dfr.seances_disponibles(1)
    assert seances[0]["code"] == f"perso:{pid}" and len(seances) == len(fr.BIBLIOTHEQUE) + 1
    assert len(dfr.seances_disponibles(1, "court", "cote")) == 4
    with pytest.raises(dfr.ErreurFractionne):
        dfr.enregistrer_perso(1, {**perso, "blocs": []})
    s = dfr.seance(f"perso:{pid}", 1)
    rid = dfr.enregistrer_realise(1, s, [{"numero": i + 1, "temps_s": 240} for i in range(8)] + [{"numero": 99, "temps_s": 1}],
                                  "2026-11-03", 7, 15.5, 8, "vent", "saisie", s["code"])
    r = dfr.realise(rid)
    assert r["activite_id"] == 7 and len(r["repetitions"]) == 8 and r["rpe"] == 8
    assert dfr.realises(None, activite_id=7)[0]["id"] == rid
    with pytest.raises(dfr.ErreurFractionne):
        dfr.enregistrer_realise(1, s, [], rpe=12)
    # la séance perso supprimée : le fractionné fait garde sa copie
    dfr.supprimer_perso(pid)
    assert dfr.realise(rid)["structure"]["blocs"][0]["repetitions"] == 8
    dfr.enregistrer_realise(1, s, [{"numero": 1, "temps_s": 230}], realise_id=rid)
    assert len(dfr.realise(rid)["repetitions"]) == 1
    prog = fr.progression(dfr.realises(1) + [dict(dfr.realise(rid), id=999, date="2026-11-10")])
    assert list(prog) == ["Mes 8 × 1000"] and len(prog["Mes 8 × 1000"]) == 2
    # la sortie supprimée : le fractionné reste, sans lien
    from noyau.donnees import base
    base.ecrire("DELETE FROM activites WHERE id=7")
    assert dfr.realise(rid)["activite_id"] is None
    dfr.supprimer_realise(rid)
    assert dfr.realises(1) == []


def test_ecrans(base_vide):
    import shiboken6
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    import data.database as db
    from noyau.donnees import fractionnes as dfr
    c = sqlite3.connect(db.CHEMIN_BDD)
    ph = [(3, 300, False)]
    for _ in range(10):
        ph += [(400 / 96, 96, True), (2.2, 90, False)]
    c.execute("INSERT INTO activites (id, athlete_id, date, nom, type, distance, duree) "
              "VALUES (3, 1, '2026-11-03 18:00:00', 'Piste', 'Course', 7, 2200)")
    c.execute("INSERT INTO parcours_gpx (athlete_id, nom, trace_json, activite_id) VALUES (1, 'Piste', ?, 3)",
              (json.dumps(_trace(ph)),))
    c.commit()
    c.close()
    from interface.fractionne import FractionneFenetre, DialogueSaisieFractionne, SectionFractionnesSortie
    f = FractionneFenetre(1)
    assert f.bibliotheque.table.rowCount() == len(fr.BIBLIOTHEQUE)
    f.bibliotheque.f_terrain.setCurrentIndex(2)                     # en côte
    assert f.bibliotheque.table.rowCount() == 8
    # minuteur : démarrer, relever un temps sur piste, passer
    m = f.minuteur
    m.son.setChecked(False)
    m.charger("10x400", 15)
    m.sans_echauffement.setChecked(True)
    m._demarrer_pause()
    assert m._phases[m._i]["phase"] == "effort"
    m._fin_repetition()
    assert len(m._temps_reps) == 1 and m._phases[m._i]["phase"] == "recup"
    m._arreter()
    # saisie depuis la trace, comme dans le menu déroulant du suivi
    d = DialogueSaisieFractionne(None, 1, "10x400", 3)
    assert d.b_trace.isEnabled()
    det = fr.detecter(dfr.points_de_la_sortie(3), d._structure)
    d._charger_seance(det)
    assert len(d.valeurs_repetitions()) == 10
    d.accept()
    assert dfr.realises(1)[0]["activite_id"] == 3
    sec = SectionFractionnesSortie(3, 1)
    assert sec.table.rowCount() == 1 and sec.combo.count() == len(fr.BIBLIOTHEQUE)
    f.mes.actualiser()
    assert f.mes.table.rowCount() == 1 and f.mes.table_reps.rowCount() == 10
    app.processEvents()
    for w in (sec, d, f):
        shiboken6.delete(w)
