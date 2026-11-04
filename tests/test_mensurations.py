"""Tests v107 : mensurations (tour de taille…) saisies avec le poids, import CSV."""
import os
import sqlite3

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import data.database as db


@pytest.fixture
def base(tmp_path, monkeypatch):
    chemin = tmp_path / "t.db"
    monkeypatch.setattr(db, "CHEMIN_BDD", chemin)
    db.creer_base_de_donnees()
    conn = sqlite3.connect(chemin)
    conn.execute("INSERT INTO athletes (nom, prenom) VALUES ('T', 'C')")
    conn.commit()
    aid = conn.execute("SELECT id FROM athletes").fetchone()[0]
    conn.close()
    return chemin, aid


def test_colonnes_migrees(base):
    chemin, _ = base
    cols = [c[1] for c in sqlite3.connect(chemin).execute("PRAGMA table_info(suivi_corporel)")]
    for c in ("tour_taille_cm", "tour_hanches_cm", "tour_poitrine_cm", "tour_cuisse_cm",
              "tour_bras_cm", "masse_grasse_pct"):
        assert c in cols


def test_import_csv_avec_taille(base, tmp_path):
    chemin, aid = base
    f = tmp_path / "s.csv"
    f.write_text("Date;Moment;Poids (kg);Tour de taille (cm);Tour de cuisse (cm);Masse grasse (%);Commentaires\n"
                 "29/10/2026;matin;84,4;98;55,5;;Première mesure\n"
                 "05/11/2026;matin;84,0;96,5;;18,2;\n", encoding="utf-8")
    from data.import_suivi_excel import importer_fichier
    assert importer_fichier(aid, str(f))["ajoutes"] == 2
    from data.mensurations import resume_mesures, serie_mesure
    r = resume_mesures(aid)
    assert r["tour_taille_cm"]["derniere"] == 96.5 and r["tour_taille_cm"]["ecart"] == -1.5
    assert r["tour_cuisse_cm"]["derniere"] == 55.5 and r["masse_grasse_pct"]["derniere"] == 18.2
    assert serie_mesure(aid, "tour_taille_cm") == [("2026-10-29", 98.0), ("2026-11-05", 96.5)]
    # réimport : rien de dupliqué
    assert importer_fichier(aid, str(f))["ajoutes"] == 0


def test_import_complete_taille_sur_releve_existant(base, tmp_path):
    chemin, aid = base
    conn = sqlite3.connect(chemin)
    conn.execute("INSERT INTO suivi_corporel (athlete_id,date,moment,poids_kg) VALUES (?,?,?,?)",
                 (aid, "2026-10-29", "matin", 84.4))
    conn.commit(); conn.close()
    f = tmp_path / "s.csv"
    f.write_text("Date;Poids (kg);Tour de taille (cm)\n29/10/2026;84,4;98\n", encoding="utf-8")
    from data.import_suivi_excel import importer_fichier
    b = importer_fichier(aid, str(f))
    assert b["completes"] == 1
    from data.mensurations import resume_mesures
    assert resume_mesures(aid)["tour_taille_cm"]["derniere"] == 98.0


def test_ecran_saisie_manuelle(base, qapp=None):
    chemin, aid = base
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    from interface.poids_fatigue import PoidsFatigue
    e = PoidsFatigue(athlete_id_initial=aid)
    for nom in ("tour_taille_cm", "tour_hanches_cm", "masse_grasse_pct"):
        assert nom in e.widgets_champs
    e.widgets_champs["tour_taille_cm"].setValue(97.5)
    e.widgets_champs["poids_kg"].setValue(84.0)
    e.ajouter_ligne()
    from data.mensurations import resume_mesures
    assert resume_mesures(aid)["tour_taille_cm"]["derniere"] == 97.5
    assert "97,5" in e._cartes["taille"][0].text()
    e.close()


def test_dossier_ia_inclut_mensurations(base):
    chemin, aid = base
    conn = sqlite3.connect(chemin)
    conn.execute("INSERT INTO suivi_corporel (athlete_id,date,moment,poids_kg,tour_taille_cm) VALUES (?,?,?,?,?)",
                 (aid, "2026-10-29", "matin", 84.4, 98))
    conn.commit(); conn.close()
    from data.analyse_ecran import dossier_poids
    assert dossier_poids(aid)["mensurations"]["Tour de taille"]["derniere"] == 98.0
