"""
Tests de l'écran « Poids & récupération » (v100) : migration de la colonne
moment, import sans doublon, chiffres des cartes, séance de la veille.

Lancer depuis le dossier du projet :  python3 -m pytest tests
Chaque test travaille sur une base temporaire : la vraie base n'est jamais touchée.
"""

import os
import sqlite3
from datetime import date

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import data.database as db


@pytest.fixture
def base(tmp_path, monkeypatch):
    chemin = tmp_path / "test.db"
    monkeypatch.setattr(db, "CHEMIN_BDD", chemin)
    db.creer_base_de_donnees()
    conn = sqlite3.connect(chemin)
    conn.execute("INSERT INTO athletes (nom, prenom) VALUES ('Test', 'Coureur')")
    conn.commit()
    athlete_id = conn.execute("SELECT id FROM athletes").fetchone()[0]
    conn.close()
    return chemin, athlete_id


def _ecrire_csv(chemin, lignes):
    entete = "Date;Moment;Poids (kg);État des jambes;Fatigue jambes (/10);Fatigue générale (RPE /10);Commentaires"
    chemin.write_text("\n".join([entete] + lignes) + "\n", encoding="utf-8")
    return chemin


def test_migration_moment_depuis_les_notes(tmp_path, monkeypatch):
    """Une base d'avant v100 (sans colonne moment) reçoit le moment déduit
    des notes, et les 0 du formulaire deviennent « non renseigné »."""
    chemin = tmp_path / "ancienne.db"
    conn = sqlite3.connect(chemin)
    conn.execute("CREATE TABLE suivi_corporel (id INTEGER PRIMARY KEY AUTOINCREMENT, athlete_id INTEGER, "
                 "date TEXT NOT NULL, poids_kg REAL, etat_jambes TEXT, fatigue_jambes INTEGER, "
                 "fatigue_generale INTEGER, notes TEXT)")
    conn.executemany("INSERT INTO suivi_corporel (athlete_id, date, poids_kg, fatigue_generale, notes) VALUES (1,?,?,?,?)", [
        ("2026-10-08", 86.8, 5, "Mauvaise nuit"),
        ("2026-10-08", 85.9, 0, "Soir"),
        ("2026-10-11", 0, 6, "Après trail — Jambes : Jambes lourdes"),
    ])
    conn.commit()
    conn.close()
    monkeypatch.setattr(db, "CHEMIN_BDD", chemin)
    db.creer_base_de_donnees()
    conn = sqlite3.connect(chemin)
    lignes = conn.execute("SELECT moment, poids_kg, fatigue_generale FROM suivi_corporel ORDER BY id").fetchall()
    conn.close()
    assert lignes == [("matin", 86.8, 5), ("soir", 85.9, None), ("après séance", None, 6)]


def test_import_sans_doublon_et_moments_distincts(base, tmp_path):
    from data.import_suivi_excel import importer_fichier
    _, athlete_id = base
    f = _ecrire_csv(tmp_path / "suivi.csv", [
        "18/10/2026;matin;86,0;Normales;;3;Avant trail",
        "18/10/2026;après séance;84,9;Tirent un peu;;6;Après trail",
        "19/10/2026;matin;86,5;Quadriceps tirent beaucoup;;4;",
        "22/10/2026;matin;84,7;;5;4;",
        "Septembre 2026 (date inconnue);;89,9;;;;",
    ])
    bilan = importer_fichier(athlete_id, f)
    assert (bilan["ajoutes"], bilan["sans_date"]) == (4, 1)

    # Deuxième import du même fichier : rien d'ajouté, rien d'écrasé.
    bilan2 = importer_fichier(athlete_id, f)
    assert bilan2["ajoutes"] == 0 and bilan2["completes"] == 0 and bilan2["inchanges"] == 4

    conn = db.connexion()
    lignes = conn.execute("SELECT date, moment, poids_kg, etat_jambes, fatigue_jambes, fatigue_generale "
                          "FROM suivi_corporel ORDER BY date, id").fetchall()
    conn.close()
    assert lignes[0] == ("2026-10-18", "matin", 86.0, "Normales", None, 3)
    assert lignes[1] == ("2026-10-18", "après séance", 84.9, "Fatiguées", None, 6)
    assert lignes[3] == ("2026-10-22", "matin", 84.7, None, 5, 4)


def test_import_complete_les_cases_vides(base, tmp_path):
    from data.import_suivi_excel import importer_fichier
    _, athlete_id = base
    importer_fichier(athlete_id, _ecrire_csv(tmp_path / "a.csv", ["22/10/2026;matin;84,7;;;;"]))
    bilan = importer_fichier(athlete_id, _ecrire_csv(tmp_path / "b.csv", ["22/10/2026;matin;99,0;;5;4;"]))
    assert bilan["completes"] == 1
    conn = db.connexion()
    ligne = conn.execute("SELECT poids_kg, fatigue_jambes, fatigue_generale FROM suivi_corporel").fetchone()
    conn.close()
    assert ligne == (84.7, 5, 4)   # le poids déjà saisi n'est pas écrasé


def test_resume_n_utilise_que_le_matin(base, tmp_path):
    import data.metriques as met
    from data.import_suivi_excel import importer_fichier
    _, athlete_id = base
    importer_fichier(athlete_id, _ecrire_csv(tmp_path / "s.csv", [
        "09/10/2026;matin;86,0;;;3;",
        "12/10/2026;matin;85,0;;;3;",
        "16/10/2026;matin;86,0;;;3;",
        "18/10/2026;après séance;80,0;;;6;",
        "21/10/2026;matin;85,0;Normales;;4;",
        "22/10/2026;matin;84,0;;5;4;",
    ]))
    met.definir_poids_depart(athlete_id, 90)
    met.definir_objectif_poids(athlete_id, 76)
    r = met.resume_poids_recuperation(athlete_id)
    assert r["dernier_poids"] == 84.0 and r["dernier_date"] == date(2026, 10, 22)
    assert r["moy7"] == 85.0          # 16, 21 et 22/10 (le 80 kg d'après sortie est ignoré)
    assert r["moy7_prec"] == 85.5     # 09 et 12/10
    assert r["ecart7"] == -0.5
    assert r["perte"] == 6.0 and r["reste"] == 8.0
    assert r["fatigue"] == 4 and r["jambes_note"] == 5
    assert [p for _, p in met.poids_serie(athlete_id, 3650)] == [86.0, 85.0, 86.0, 85.0, 84.0]


def test_seance_de_la_veille(base):
    import data.metriques as met
    _, athlete_id = base
    conn = db.connexion()
    conn.execute("INSERT INTO activites (athlete_id, date, nom, type, distance, denivele) "
                 "VALUES (?, '2026-10-18T09:00:00', 'Trail du dimanche', 'Trail', 12.21, 644)", (athlete_id,))
    conn.execute("INSERT INTO musculation_suivi (athlete_id, date, exercice) VALUES (?, '2026-10-19', 'Vélo')",
                 (athlete_id,))
    conn.commit()
    conn.close()
    assert met.seances_du_jour(athlete_id, date(2026, 10, 18)) == "Trail 12,2 km D+644"
    assert met.seances_du_jour(athlete_id, date(2026, 10, 19)) == "Salle"
    assert met.seances_du_jour(athlete_id, date(2026, 10, 20)) == ""


def test_ecran_poids_recuperation(base, tmp_path):
    """L'écran s'ouvre, remplit ses cartes et ne garde aucun 0 saisi par défaut."""
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication
    import data.metriques as met
    from data.import_suivi_excel import importer_fichier
    from interface.poids_fatigue import PoidsFatigue

    _, athlete_id = base
    app = QApplication.instance() or QApplication([])
    importer_fichier(athlete_id, _ecrire_csv(tmp_path / "s.csv", [
        "21/10/2026;matin;85,5;Normales;;4;",
        "22/10/2026;matin;84,7;;5;4;",
    ]))
    met.definir_poids_depart(athlete_id, 90)
    met.definir_objectif_poids(athlete_id, 76)
    ecran = PoidsFatigue(athlete_id_initial=athlete_id)
    texte = {cle: v.text() for cle, (v, _) in ecran._cartes.items()}
    assert texte["poids"] == "84,7 kg"
    assert texte["moy7"] == "85,1 kg"
    assert texte["perte"] == "−5,3 kg"
    assert texte["objectif"] == "8,7 kg"
    assert texte["fatigue"] == "4 / 10" and texte["jambes"] == "5 / 10"
    assert ecran.table.rowCount() == 2

    # Saisie d'un relevé avec seulement le poids : fatigues et état restent vides.
    ecran.widgets_champs["poids_kg"].setValue(84.2)
    ecran.ajouter_ligne()
    conn = db.connexion()
    ligne = conn.execute("SELECT moment, etat_jambes, fatigue_jambes, fatigue_generale FROM suivi_corporel "
                         "WHERE poids_kg=84.2").fetchone()
    conn.close()
    assert ligne == ("matin", None, None, None)
    ecran.close()
    app.processEvents()
