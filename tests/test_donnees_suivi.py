"""Étape 1.4c — accès aux données de santé, blessures, soins, courses,
résultats, objectifs et de l'écran de liste commun (noyau/donnees)."""
import sqlite3

import pytest

import data.database as db
from noyau.donnees import sante as dsante, blessures as dbles, courses as dcourse, listes as dliste
from noyau.donnees import activites as dact


@pytest.fixture
def base(tmp_path, monkeypatch):
    chemin = tmp_path / "t.db"
    monkeypatch.setattr(db, "CHEMIN_BDD", chemin)
    db.creer_base_de_donnees()
    c = sqlite3.connect(chemin)
    c.execute("INSERT INTO athletes (id, nom, prenom) VALUES (1, 'T', 'C'), (2, 'U', 'D')")
    c.execute("INSERT INTO activites (id, athlete_id, date, type, distance) VALUES (10, 1, '2026-10-20 07:00:00', 'Trail', 12)")
    c.execute("INSERT INTO musculation_suivi (id, athlete_id, date, exercice, groupe_musculaire) "
              "VALUES (20, 1, '2026-10-18', 'Squat', 'Jambes')")
    lignes = [  # (date, poids, jambes, fatigue jambes, fatigue générale, moment)
        ("2026-10-01", 88.0, "Normales", 3, 4, "matin"),
        ("2026-10-02", 0, "", 0, 5, None),
        ("2026-10-02", 87.6, "Fatiguées", None, None, "après séance"),
        ("2026-10-03", 87.4, "Normales", 2, 3, ""),
    ]
    for d, p, j, fj, fg, m in lignes:
        c.execute("INSERT INTO suivi_corporel (athlete_id, date, poids_kg, etat_jambes, fatigue_jambes, "
                  "fatigue_generale, moment, notes) VALUES (1,?,?,?,?,?,?,'n')", (d, p, j, fj, fg, m))
    c.commit()
    c.close()
    return chemin


def brut(chemin, sql, params=()):
    c = sqlite3.connect(chemin)
    try:
        return c.execute(sql, params).fetchall()
    finally:
        c.close()


# ------------------------------------------------------------------
# Santé
# ------------------------------------------------------------------

def test_poids_et_releves(base):
    assert dsante.dernier_poids(1) == (87.4, "2026-10-03")
    assert dsante.dernier_poids(2) is None
    assert dsante.releve(2) == (1, "2026-10-02", "matin", 0)            # moment vide → « matin »
    assert dsante.poids_du_matin_precedent(1, "2026-10-03") == (88.0,)  # ignore le 0 et l'après-séance
    assert dsante.poids_du_matin_precedent(1, "2026-10-01") is None
    # un moment vide ('') ne compte comme « matin » qu'après le nettoyage fait à l'ouverture de l'écran
    assert [r[0] for r in dsante.fatigue_du_matin(1)] == ["2026-10-01", "2026-10-02"]
    dsante.nettoyer_cases_vides(("poids_kg", "fatigue_jambes", "fatigue_generale"))
    assert [r[0] for r in dsante.fatigue_du_matin(1)] == ["2026-10-01", "2026-10-02", "2026-10-03"]
    assert len(dsante.releves_entre(1, "2026-10-02", "2026-10-02z")) == 2
    assert len(dsante.releves_complets(1)) == 4 and len(dsante.releves_complets(1)[0]) == 6


def test_nettoyer_les_cases_vides(base):
    dsante.nettoyer_cases_vides(("poids_kg", "fatigue_jambes", "fatigue_generale"))
    assert brut(base, "SELECT poids_kg, etat_jambes, fatigue_jambes, moment FROM suivi_corporel WHERE id=2") == [
        (None, None, None, "matin")]
    assert brut(base, "SELECT moment FROM suivi_corporel WHERE id=4") == [("matin",)]
    with pytest.raises(ValueError):
        dsante.nettoyer_cases_vides(["poids_kg=1; DROP TABLE x"])


def test_sommeil_recuperation_garmin(base):
    c = sqlite3.connect(base)
    c.execute("INSERT INTO sommeil (athlete_id, date, heure_coucher, heure_lever, duree_heures) VALUES "
              "(1,'2026-10-01','22:30','05:15',6.75), (2,'2026-10-01','23:00','07:00',8)")
    c.execute("INSERT INTO recuperation_quotidienne (athlete_id, date, fc_repos, hrv_nuit_ms) VALUES "
              "(1,'2026-10-01',52,48), (1,'2026-10-02',51,50)")
    c.execute("INSERT INTO garmin_quotidien (athlete_id, date, pas, vo2max) VALUES (1,'2026-10-02',9000,44)")
    c.commit()
    c.close()
    assert dsante.sommeil_entre(1, "2026-10-01", "2026-10-31") == [("2026-10-01", "22:30", "05:15", 6.75)]
    assert len(dsante.sommeil_entre(None, "2026-10-01", "2026-10-31")) == 2
    assert dsante.recuperation_entre(1, ["date", "fc_repos"], "2026-10-01", "2026-10-31") == [
        ("2026-10-01", 52), ("2026-10-02", 51)]
    recente = dsante.sante_garmin_recente(1, 14)
    assert recente[0][0] == "2026-10-02" and recente[0][9] == 9000 and recente[1][9] is None


# ------------------------------------------------------------------
# Blessures et soins
# ------------------------------------------------------------------

def test_blessures(base):
    b1 = dbles.ajouter({"athlete_id": 1, "date_debut": "2026-10-10", "zone_corporelle": "Genou",
                        "type_blessure": "Tendinite", "statut": "En cours", "musculation_suivi_id": 20})
    b2 = dbles.ajouter({"athlete_id": 1, "date_debut": "2026-09-01", "date_fin": "2026-09-10",
                        "zone_corporelle": "Mollet", "statut": "Guérie"})
    assert dbles.origine(b1) == (None, None, None, "2026-10-18", "Squat", "Jambes")
    dbles.lier_a_une_sortie(b1, 10)
    assert dbles.origine(b1)[:3] == ("2026-10-20 07:00:00", "Trail", 12) and dbles.origine(b1)[3] is None
    assert [r[0] for r in dbles.de_l_athlete(1)] == [b1, b2]
    assert len(dbles.pour_journal(1)) == 2
    assert dbles.en_cours(1) == [("Genou", "Tendinite")]
    assert [r[0] for r in dbles.pour_liaison(1, 1)] == [b1]
    assert dbles.valeurs(b2, "athlete_id") == (1,)


def test_soins(base):
    b = dbles.ajouter({"athlete_id": 1, "date_debut": "2026-10-10", "zone_corporelle": "Genou", "type_blessure": "Entorse"})
    c = sqlite3.connect(base)
    c.execute("INSERT INTO soins (id, athlete_id, date, type_soin, motif) VALUES (7, 1, '2026-10-12', 'Kiné', 'Entretien')")
    c.commit()
    c.close()
    assert dbles.blessure_du_soin(7) == (None, None, None)
    dbles.lier_soin_a_une_blessure(7, b)
    assert dbles.blessure_du_soin(7) == ("Genou", "Entorse", "2026-10-10")
    assert dbles.soin_valeurs(7, "motif", "athlete_id") == ("Blessure", 1)


# ------------------------------------------------------------------
# Courses, résultats, objectifs
# ------------------------------------------------------------------

def test_courses_resultats_objectifs(base):
    c = sqlite3.connect(base)
    c.execute("INSERT INTO courses_calendrier (id, athlete_id, nom, date, distance_km, denivele_m, type_terrain) "
              "VALUES (1,1,'Ocres','2026-12-14',24,900,'Technique'), (2,1,'Ventoux',NULL,46,2600,'Montagne'), "
              "(3,2,'Autre','2026-11-30',10,100,'Route')")
    c.execute("INSERT INTO resultats_courses (id, athlete_id, nom_course, date, classement_general) "
              "VALUES (1,1,'Saumane','2026-10-12','45/210'), (2,1,'Carpentras','2026-09-01','80/300')")
    c.execute("INSERT INTO objectifs (id, athlete_id, titre, date_cible, type_objectif, statut) "
              "VALUES (1,1,'Finir Saumane','2026-10-12','Course','En cours')")
    c.commit()
    c.close()
    assert dcourse.course(1, "nom", "distance_km") == ("Ocres", 24)
    assert [r[1] for r in dcourse.courses_par_date(1)] == ["Ventoux", "Ocres"]   # NULL d'abord (tri SQL)
    assert len(dcourse.courses_par_date(None)) == 3
    assert [r[1] for r in dcourse.courses_pour_roadbook(1)] == ["Ocres", "Ventoux"]  # sans date en dernier
    assert dcourse.sortie_du_resultat(1) is None
    dcourse.lier_resultat_a_une_sortie(1, 10)
    assert dcourse.sortie_du_resultat(1) == ("2026-10-20 07:00:00", 12)
    assert [r[1] for r in dcourse.resultats_pour_liaison(1, 50)] == ["Saumane", "Carpentras"]
    assert dcourse.resultat_de_l_objectif(1) is None
    dcourse.marquer_objectif_atteint(1, 1)
    assert dcourse.resultat_de_l_objectif(1) == ("Saumane", "2026-10-12", "45/210")
    assert dcourse.objectif(1, "statut") == ("Atteint",)


# ------------------------------------------------------------------
# Écran de liste commun et historique des imports
# ------------------------------------------------------------------

def test_listes_generiques(base):
    i = dliste.ajouter("materiel", 1, ["nom", "type", "km_actuels"], ["Kiprun", "Chaussures", 120])
    dliste.ajouter("materiel", 2, ["nom", "type", "km_actuels"], ["Sac", "Sac", 0])
    assert dliste.lister("materiel", ["nom", "km_actuels"], "id DESC", 1) == [(i, "Kiprun", 120)]
    assert [r[1] for r in dliste.lister("materiel", ["nom"], "id DESC")] == ["Sac", "Kiprun"]
    tri_poids = "date DESC, CASE COALESCE(moment, 'matin') WHEN 'matin' THEN 0 WHEN 'après séance' THEN 1 ELSE 2 END DESC"
    assert len(dliste.lister("suivi_corporel", ["date", "moment"], tri_poids, 1)) == 4
    assert dliste.valeurs("materiel", i, "athlete_id") == (1,)
    dliste.supprimer("materiel", i)
    assert dliste.valeurs("materiel", i, "nom") is None
    for mauvais in ("materiel; DROP TABLE x", "Materiel"):
        with pytest.raises(ValueError):
            dliste.lister(mauvais, ["nom"], "id")


def test_historique_des_imports(base):
    dact.noter_import("strava.csv", "Strava", 3, 2, 1, 0)
    assert brut(base, "SELECT fichier, source, total, nouvelles, doublons, erreurs FROM importations") == [
        ("strava.csv", "Strava", 3, 2, 1, 0)]
