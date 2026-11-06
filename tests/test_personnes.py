"""Étape 2.2 — fiche Personne unique et rôles."""
import sqlite3

import pytest

import data.database as db
from data import migrations as mig
from noyau.donnees import personnes as P


@pytest.fixture
def base(tmp_path, monkeypatch):
    chemin = tmp_path / "t.db"
    monkeypatch.setattr(db, "CHEMIN_BDD", chemin)
    db.creer_base_de_donnees()
    return chemin


def brut(chemin, sql, params=()):
    c = sqlite3.connect(chemin)
    c.execute("PRAGMA foreign_keys = ON")
    try:
        r = c.execute(sql, params).fetchall()
        c.commit()
        return r
    finally:
        c.close()


def test_roles_identiques_dans_la_migration_et_le_noyau():
    assert P.ROLES == mig.ROLES


def test_conversion_d_une_base_v108(tmp_path, monkeypatch):
    chemin = tmp_path / "trailmaster.db"
    monkeypatch.setattr(db, "CHEMIN_BDD", chemin)
    monkeypatch.setattr(mig, "appliquer_migrations", lambda *a, **k: None)
    db.creer_base_de_donnees()           # schéma v108, sans migration
    monkeypatch.undo()
    monkeypatch.setattr(db, "CHEMIN_BDD", chemin)
    brut(chemin, "INSERT INTO athletes (id, nom, prenom, sexe) VALUES (18, 'Beltran', 'Didier', 'H'), (19, 'Autre', 'Coureur', 'F')")
    bilan = mig.appliquer_migrations(chemin)
    assert bilan["appliquees"] == [1, 2, 3, 4, 5, 6, 7, 8, 9]
    personnes = P.lister()
    assert [(p["nom"], p["roles"], p["athlete_id"]) for p in personnes] == [
        ("Autre", ["coureur"], 19), ("Beltran", ["coureur"], 18)]
    f = P.fiche(P.personne_de_l_athlete(18))
    assert f["prenom"] == "Didier" and f["sexe"] == "H" and len(f["uuid"]) == 36
    mig.appliquer_migrations(chemin)       # deuxième passage : aucune fiche en double
    assert len(P.lister()) == 2


def test_un_athlete_cree_ailleurs_recoit_sa_fiche(base):
    aid = db.ajouter_athlete("Martin", "Julie", 35, "F", 165, 55, 50, 185, 170, 14, 50, "Confirmé")
    pid = P.personne_de_l_athlete(aid)
    assert pid and P.roles(pid) == ["coureur"]
    assert brut(base, "SELECT MAX(id) FROM athletes")[0][0] == aid   # l'id renvoyé reste celui de l'athlète
    brut(base, "UPDATE athletes SET nom='Martin-Durand', prenom='Julie' WHERE id=?", (aid,))
    assert P.fiche(pid)["nom"] == "Martin-Durand"


def test_creer_modifier_et_roles(base):
    pid = P.creer({"nom": "Rey", "prenom": "Paul", "date_naissance": "02/03/1980", "email": "paul@exemple.fr"},
                  ["benevole", "coureur"])
    f = P.fiche(pid)
    assert f["roles"] == ["coureur", "benevole"] and f["athlete_id"] and f["date_naissance"] == "1980-03-02"
    P.modifier(pid, {"prenom": "Paul-Henri", "sexe": "H"})
    assert brut(base, "SELECT prenom, sexe FROM athletes WHERE id=?", (f["athlete_id"],)) == [("Paul-Henri", "H")]
    P.definir_roles(pid, ["coureur", "organisateur"])
    assert P.roles(pid) == ["coureur", "organisateur"]
    with pytest.raises(P.ErreurPersonne):
        P.definir_roles(pid, ["organisateur"])        # le profil coureur porte les sorties
    with pytest.raises(P.ErreurPersonne):
        P.supprimer(pid)
    assert P.roles(pid) == ["coureur", "organisateur"]  # rien n'a bougé


def test_controles_de_saisie(base):
    for champs in ({"nom": ""}, {"nom": "A", "email": "pas-un-mail"}, {"nom": "A", "date_naissance": "31/02/2000"},
                   {"nom": "A", "date_naissance": "01/01/2099"}, {"nom": "A", "inconnu": 1}):
        with pytest.raises(P.ErreurPersonne):
            P.creer(champs)
    with pytest.raises(P.ErreurPersonne):
        P.creer({"nom": "A"}, ["astronaute"])
    assert P.lister() == []


def test_doublons_possibles_sans_accents_ni_majuscules(base):
    P.creer({"nom": "Bélanger", "prenom": "Élodie", "date_naissance": "1990-04-01"})
    assert len(P.doublons_possibles("BELANGER", "elodie")) == 1
    assert len(P.doublons_possibles("belanger", "Elodie", "1990-04-01")) == 1
    assert P.doublons_possibles("Belanger", "Elodie", "1991-04-01") == []
    assert len(P.lister(recherche="elod")) == 1


def test_parents_enfants_et_mineurs(base):
    parent = P.creer({"nom": "Beltran", "prenom": "Didier"}, ["coureur"])
    enfant = P.creer({"nom": "Beltran", "prenom": "Petit", "date_naissance": "2016-06-01"})
    P.lier_parent(parent, enfant)
    f = P.fiche(enfant)
    assert f["mineur"] and f["roles"] == ["enfant"] and f["parents"][0]["id"] == parent
    assert "parent" in P.roles(parent) and P.fiche(parent)["enfants"][0]["id"] == enfant
    with pytest.raises(P.ErreurPersonne):
        P.lier_parent(enfant, parent)
    with pytest.raises(P.ErreurPersonne):
        P.lier_parent(parent, parent)
    assert [p["prenom"] for p in P.lister("enfant")] == ["Petit"]
    P.supprimer(enfant)
    assert P.fiche(parent)["enfants"] == []


def test_supprimer_l_athlete_nettoie_la_fiche(base):
    aid = db.ajouter_athlete("Seul", "Coureur", None, None, None, None, None, None, None, None, None, None)
    pid = P.personne_de_l_athlete(aid)
    brut(base, "DELETE FROM athletes WHERE id=?", (aid,))
    assert P.fiche(pid) is None                      # plus aucun rôle : fiche retirée
    aid = db.ajouter_athlete("Double", "Role", None, None, None, None, None, None, None, None, None, None)
    pid = P.personne_de_l_athlete(aid)
    P.definir_roles(pid, ["coureur", "benevole"])
    brut(base, "DELETE FROM athletes WHERE id=?", (aid,))
    assert P.fiche(pid)["roles"] == ["benevole"]     # la personne reste bénévole


def test_age():
    from datetime import date
    assert P.age("2016-06-01", date(2026, 5, 31)) == 9
    assert P.age("2016-06-01", date(2026, 6, 1)) == 10
    assert P.age(None) is None and not P.est_mineur(None)
