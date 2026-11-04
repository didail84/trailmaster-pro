"""Étape 1.4b — accès aux données des séances, plans, segments et de la
musculation (noyau/donnees). Chaque fonction est comparée à la requête
d'origine des écrans de la v108."""
import json
import sqlite3

import pytest

import data.database as db
from noyau.donnees import seances as dseance, plans as dplan, segments as dseg, musculation as dmus


@pytest.fixture
def base(tmp_path, monkeypatch):
    chemin = tmp_path / "t.db"
    monkeypatch.setattr(db, "CHEMIN_BDD", chemin)
    db.creer_base_de_donnees()
    c = sqlite3.connect(chemin)
    c.execute("INSERT INTO athletes (id, nom, prenom) VALUES (1, 'T', 'C'), (2, 'U', 'D')")
    c.execute("INSERT INTO activites (id, athlete_id, date, nom, type, distance) "
              "VALUES (10, 1, '2026-10-20 07:00:00', 'Sortie', 'Trail', 12)")
    c.execute("INSERT INTO parcours_gpx (id, athlete_id, nom, distance_km, activite_id) VALUES (5, 1, 'Boucle', 9.5, 10)")
    c.commit()
    c.close()
    return chemin


def brut(chemin, sql, params=()):
    c = sqlite3.connect(chemin)
    try:
        return c.execute(sql, params).fetchall()
    finally:
        c.close()


ETAPES = json.dumps([{"type": "Effort", "mode": "distance", "valeur": 8}])


# ------------------------------------------------------------------
# Séances
# ------------------------------------------------------------------

def test_seance_creer_lire_lister(base):
    sid = dseance.creer({"athlete_id": 1, "nom": "Seuil", "type_seance": "Fractionné",
                         "date_prevue": "2026-11-10", "etapes_json": ETAPES, "parcours_id": 5})
    assert dseance.valeurs(sid, "nom", "statut", "parcours_id") == ("Seuil", "Prévue", 5)
    ligne = dseance.lister_avec_parcours(1)[0]
    assert ligne[0] == sid and ligne[8:10] == ("Boucle", 9.5) and len(ligne) == 11
    assert dseance.lister_avec_parcours(None) == dseance.lister_avec_parcours(1)
    assert dseance.lister_avec_parcours(2) == []


def test_seance_entre_dates_et_deplacement(base):
    sid = dseance.creer({"athlete_id": 1, "nom": "A", "date_prevue": "2026-11-10"})
    assert dseance.entre_dates(1, "2026-11-01", "2026-11-30z") == brut(
        base, "SELECT id, nom, type_seance, date_prevue, statut FROM seances_structurees "
        "WHERE athlete_id=? AND date_prevue>=? AND date_prevue<=?", (1, "2026-11-01", "2026-11-30z"))
    assert dseance.deplacer(sid, "2026-11-12") is True
    assert dseance.valeurs(sid, "date_prevue") == ("2026-11-12",)
    dseance.marquer_realisee(sid, 10, 87)
    assert dseance.valeurs(sid, "statut", "activite_id", "score_conformite") == ("Réalisée", 10, 87)
    # une séance réalisée ne se déplace plus
    assert dseance.deplacer(sid, "2026-11-20") is False
    assert dseance.deplacer(99999, "2026-11-20") is False
    dseance.supprimer(sid)
    assert dseance.valeurs(sid, "nom") is None


# ------------------------------------------------------------------
# Plans
# ------------------------------------------------------------------

def test_plan_avec_ses_seances(base):
    liste = [{"athlete_id": 1, "nom": f"S1 — séance {i}", "type_seance": "Endurance fondamentale",
              "date_prevue": f"2026-11-1{i}", "etapes_json": ETAPES} for i in range(4)]
    pid = dplan.creer_avec_seances({"athlete_id": 1, "nom": "Plan test", "distance_cible": "10 km",
                                    "niveau": "Intermédiaire", "nb_semaines": 8, "date_debut": "2026-11-09"}, liste)
    assert dplan.lister(1) == brut(base, "SELECT id, nom, distance_cible, niveau, nb_semaines, date_debut "
                                         "FROM plans_entrainement WHERE athlete_id=? ORDER BY date_creation DESC", (1,))
    assert dplan.lister(None) == dplan.lister(1) and dplan.lister(2) == []
    assert dplan.avancement(pid) == (4, 0)
    dseance.marquer_realisee(brut(base, "SELECT id FROM seances_structurees WHERE plan_id=?", (pid,))[0][0], 10, 90)
    assert dplan.avancement(pid) == (4, 1)
    assert dplan.avancement(9999) == (0, None)
    assert all(s[0] == "Prévue" or s[0] == "Réalisée" for s in brut(base, "SELECT statut FROM seances_structurees"))
    rid = dplan.enregistrer_rapport_bloc(pid, 1, "Bloc 1", "Bilan")
    assert brut(base, "SELECT plan_id, nom_bloc, contenu FROM rapports_bloc WHERE id=?", (rid,)) == [(pid, "Bloc 1", "Bilan")]
    dplan.supprimer(pid)
    assert dplan.lister(1) == [] and brut(base, "SELECT COUNT(*) FROM seances_structurees")[0][0] == 0


def test_supprimer_un_plan_avec_son_historique(base):
    """v108 : impossible de supprimer un plan ayant un rapport de bloc, une
    replanification ou une séance comparée (la base refusait, l'écran plantait)."""
    pid = dplan.creer_avec_seances({"athlete_id": 1, "nom": "Plan"},
                                   [{"athlete_id": 1, "nom": "S1", "date_prevue": "2026-11-10"}])
    sid = brut(base, "SELECT id FROM seances_structurees WHERE plan_id=?", (pid,))[0][0]
    c = sqlite3.connect(base)
    c.execute("INSERT INTO rapports_bloc (plan_id, athlete_id, nom_bloc) VALUES (?, 1, 'Bloc 1')", (pid,))
    c.execute("INSERT INTO replanifications (plan_id, athlete_id, niveau_ajustement) VALUES (?, 1, 'stable')", (pid,))
    c.execute("INSERT INTO comparaisons_courses (athlete_id, seance_id, activite_id) VALUES (1, ?, 10)", (sid,))
    c.commit()
    c.close()
    dplan.supprimer(pid)
    for table in ("plans_entrainement", "seances_structurees", "rapports_bloc", "replanifications", "comparaisons_courses"):
        assert brut(base, f"SELECT COUNT(*) FROM {table}")[0][0] == 0, table


def test_supprimer_une_seance_comparee(base):
    sid = dseance.creer({"athlete_id": 1, "nom": "Comparée", "date_prevue": "2026-11-10"})
    c = sqlite3.connect(base)
    c.execute("INSERT INTO comparaisons_courses (athlete_id, seance_id, activite_id) VALUES (1, ?, 10)", (sid,))
    c.commit()
    c.close()
    dseance.supprimer(sid)
    assert dseance.valeurs(sid, "nom") is None
    assert brut(base, "SELECT COUNT(*) FROM comparaisons_courses")[0][0] == 0


def test_plan_tout_ou_rien(base):
    mauvaise = [{"athlete_id": 1, "nom": "ok", "date_prevue": "2026-11-10"},
                {"athlete_id": 1, "colonne_inexistante": 1}]
    with pytest.raises(sqlite3.OperationalError):
        dplan.creer_avec_seances({"athlete_id": 1, "nom": "Cassé"}, mauvaise)
    assert dplan.lister(1) == [] and brut(base, "SELECT COUNT(*) FROM seances_structurees")[0][0] == 0


# ------------------------------------------------------------------
# Segments
# ------------------------------------------------------------------

def test_segments_et_passages(base):
    ref = [[44.0, 5.0], [44.001, 5.0]]
    seg = dseg.creer({"athlete_id": 1, "nom": "Côte", "distance_km": 1.2, "denivele_positif": 90,
                      "points_reference_json": json.dumps(ref), "parcours_origine_id": 5})
    assert dseg.lister(1) == [(seg, "Côte", 1.2, 90)]
    assert dseg.points_reference(seg) == ref
    assert dseg.resume_passages(seg) == (0, None)
    for duree, date in ((420, "2026-10-01"), (395, "2026-10-08"), (None, "2026-10-15")):
        dseg.ajouter_passage(seg, 5, 10, date, duree)
    assert dseg.parcours_deja_trouves(seg) == {5}
    assert dseg.resume_passages(seg) == (3, 395)
    assert dseg.classement(seg) == [("2026-10-08", 395), ("2026-10-01", 420)]  # sans les passages non chronométrés
    assert dseg.passages_de_l_activite(10) == [("Côte", 1.2, 420), ("Côte", 1.2, 395), ("Côte", 1.2, None)]
    dseg.supprimer(seg)
    assert dseg.lister(1) == [] and brut(base, "SELECT COUNT(*) FROM segments_efforts")[0][0] == 0


# ------------------------------------------------------------------
# Musculation et mobilité
# ------------------------------------------------------------------

def test_musculation(base):
    a = dmus.ajouter_suivi({"athlete_id": 1, "date": "2026-11-02", "type_seance": "Renforcement — Jambes",
                            "exercice": "Squat", "charge_kg": 45, "series": 4, "rpe": 7})
    dmus.ajouter_suivi({"athlete_id": 1, "date": "2026-11-04", "type_seance": "Cardio machine",
                        "appareil": "Rameur", "duree_min": 20})
    assert a and len(dmus.suivi(1)) == 2 and dmus.suivi(1)[0][0] == "2026-11-04"
    assert len(dmus.suivi(1)[0]) == 17
    assert dmus.suivi_par_jour_entre(1, "2026-11-01", "2026-11-03") == [
        ("2026-11-02", "Squat", 45, 4, None, 7, None, "Renforcement — Jambes", None)]
    c = sqlite3.connect(base)
    c.execute("INSERT INTO musculation_exercices (athlete_id, groupe_seance, exercice) VALUES (1,'B','Fente'),(1,'A','Squat')")
    c.execute("INSERT INTO planning_mobilite (athlete_id, jour, duree) VALUES (1,'Lundi',15)")
    c.execute("INSERT INTO mobilite_exercices (athlete_id, categorie, exercice) VALUES (1,'Dos','Chat'),(1,'Cheville','Cercle')")
    c.commit()
    c.close()
    assert [e[1] for e in dmus.exercices(1)] == ["Squat", "Fente"]
    assert dmus.planning_mobilite(1) == [("Lundi", "15", None, None, None, None)]  # durée en texte
    assert [e[0] for e in dmus.exercices_mobilite(1)] == ["Cheville", "Dos"]
    assert dmus.suivi(2) == [] and dmus.exercices(2) == []
