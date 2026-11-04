"""Tests des courbes « estimation basse » (v102)."""
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
    for k in range(40):  # une sortie tous les 12 jours, de plus en plus rapide
        j = date.today() - timedelta(days=12 * (40 - k))
        duree = 5400 - k * 20
        c.execute(
            "INSERT INTO activites (athlete_id,date,nom,type,distance,denivele,duree,"
            "frequence_cardiaque_moyenne,frequence_cardiaque_max) VALUES (1,?,?,?,?,?,?,?,?)",
            (j.isoformat() + " 07:30:00", f"S{k}", "Trail", 10.0, 300, duree, 150, 172))
    c.commit()
    c.close()


def test_series_et_mention(base):
    from interface import estimations_basses as eb
    s = eb.serie_estimations(1)
    assert s and all(s[c] for c in ("vma", "vo2max", "efficacite"))
    assert eb.evolution_pct(s["vma"]) > 0 and eb.evolution_pct(s["vo2max"]) > 0
    defs = eb.definitions_courbes(s)
    assert len(defs) == 3
    for titre, ser in defs:
        assert "estimation basse" in titre and "estimation basse" in ser[0]["nom"]


def test_sans_sortie(base):
    from interface import estimations_basses as eb
    assert eb.serie_estimations(99) is None


def test_ecran_vma(base):
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    from interface.vma import VMACircuits
    e = VMACircuits()
    e.combo_athlete.setCurrentIndex(1)
    e.actualiser()
    assert all("estimation basse" in t.text() for t in e.titres_estim)
    assert all(c.series and c.series[0]["valeurs"] for c in e.courbes_estim)
