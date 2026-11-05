"""Étape 2.4 — passeport coureur : export, contrôle et import sans doublon."""
import json
import shutil
import sqlite3
from datetime import date, timedelta

import pytest

import data.database as db
from noyau import passeport as PP
from noyau.donnees import personnes as P


@pytest.fixture
def base(tmp_path, monkeypatch):
    chemin = tmp_path / "a.db"
    monkeypatch.setattr(db, "CHEMIN_BDD", chemin)
    db.creer_base_de_donnees()
    pid = P.creer({"nom": "Beltran", "prenom": "Didier", "date_naissance": "1980-05-01", "email": "d@exemple.fr"},
                  ["coureur", "licencie"])
    aid = P.fiche(pid)["athlete_id"]
    c = sqlite3.connect(chemin)
    c.execute("UPDATE athletes SET taille=178, poids=80, fc_max=185, vma=13.2 WHERE id=?", (aid,))
    c.execute("INSERT INTO resultats_courses (athlete_id, nom_course, date, distance, temps, classement_general) "
              "VALUES (?, 'Trail des Ocres', '2026-04-12', 24, '2:55:10', '84/310'), "
              "(?, 'Ventoux Trail', '2026-06-20', 46, '6:40:00', '120/500')", (aid, aid))
    futur = (date.today() + timedelta(days=40)).isoformat()
    c.execute("INSERT INTO courses_calendrier (athlete_id, nom, date, distance_km) VALUES (?, 'Saintélyon', ?, 78), "
              "(?, 'Vieille course', '2020-01-01', 10)", (aid, futur, aid))
    c.execute("INSERT INTO objectifs (athlete_id, titre, date_cible, statut) VALUES (?, 'Finir la Saintélyon', ?, 'En cours')", (aid, futur))
    c.execute("INSERT INTO activites (athlete_id, date, nom, distance) VALUES (?, '2026-10-01 07:00:00', 'Sortie', 10)", (aid,))
    c.commit()
    c.close()
    P.ajouter_index(pid, "ITRA", 512, "2026-10-01")
    P.ajouter_index(pid, "UTMB Index", 498, "01/10/2026")
    return chemin, pid, aid


def autre_base(tmp_path, monkeypatch, nom="b.db"):
    chemin = tmp_path / nom
    monkeypatch.setattr(db, "CHEMIN_BDD", chemin)
    db.creer_base_de_donnees()
    return chemin


def test_export_contenu_et_confidentialite(base):
    _, pid, _ = base
    p = PP.exporter(pid)
    assert p["format"] == PP.FORMAT and p["version_format"] == 1
    assert p["personne"]["nom"] == "Beltran" and "email" not in p["personne"]        # coordonnées : non par défaut
    assert p["roles"] == ["coureur", "licencie"]
    assert p["profil_coureur"]["vma"] == 13.2 and len(p["profil_coureur"]["uuid"]) == 36
    assert [r["nom_course"] for r in p["resultats"]] == ["Trail des Ocres", "Ventoux Trail"]
    assert {i["organisme"]: i["valeur"] for i in p["index"]} == {"ITRA": 512, "UTMB Index": 498}
    assert "courses_a_venir" not in p and "objectifs" not in p and "sorties" not in json.dumps(p)
    tout = PP.exporter(pid, {"courses": True, "objectifs": True, "contact": True})
    assert [c["nom"] for c in tout["courses_a_venir"]] == ["Saintélyon"]            # les courses passées restent
    assert tout["personne"]["email"] == "d@exemple.fr" and len(tout["objectifs"]) == 1
    assert PP.nom_de_fichier(p).startswith("passeport_didier_beltran_")


def test_aller_retour_vers_un_autre_ordinateur(base, tmp_path, monkeypatch):
    _, pid, _ = base
    p = PP.exporter(pid, {"courses": True, "objectifs": True})
    fichier = tmp_path / PP.nom_de_fichier(p)
    PP.ecrire_fichier(fichier, p)
    autre_base(tmp_path, monkeypatch)
    lu = PP.lire_fichier(fichier)
    ap = PP.apercu(lu)
    assert ap["etat"] == "nouvelle" and ap["a_ajouter"] == 2 + 2 + 1 + 1
    r = PP.importer(lu)
    assert r["cree"] and r["ajouts"] == {"resultats": 2, "courses_a_venir": 1, "objectifs": 1, "index": 2}
    f = P.fiche(r["personne_id"])
    assert f["uuid"] == p["personne"]["uuid"] and f["roles"] == ["coureur", "licencie"]   # même identité partout
    c = sqlite3.connect(db.CHEMIN_BDD)
    assert c.execute("SELECT uuid, vma, taille FROM athletes").fetchall() == [(p["profil_coureur"]["uuid"], 13.2, 178)]
    assert sorted(u for (u,) in c.execute("SELECT uuid FROM resultats_courses")) == sorted(x["uuid"] for x in p["resultats"])
    c.close()
    # deuxième import du même fichier : rien en double
    r2 = PP.importer(lu)
    assert not r2["cree"] and sum(r2["ajouts"].values()) == 0 and r2["deja"]["resultats"] == 2
    assert len(P.lister()) == 1


def test_rapprochement_par_nom_sans_doublon(base, tmp_path, monkeypatch):
    _, pid, _ = base
    p = PP.exporter(pid)
    autre_base(tmp_path, monkeypatch)
    # sur l'ordinateur du club, Didier existe déjà (autre identifiant) avec un résultat commun
    pid2 = P.creer({"nom": "BELTRAN", "prenom": "didier"}, ["coureur", "benevole"])
    aid2 = P.fiche(pid2)["athlete_id"]
    c = sqlite3.connect(db.CHEMIN_BDD)
    c.execute("UPDATE athletes SET vma=14 WHERE id=?", (aid2,))
    c.execute("INSERT INTO resultats_courses (athlete_id, nom_course, date) VALUES (?, 'trail des ocres', '2026-04-12')", (aid2,))
    c.commit()
    c.close()
    assert PP.apercu(p)["etat"] == "nom"
    r = PP.importer(p)
    assert r["personne_id"] == pid2 and r["ajouts"]["resultats"] == 1 and r["deja"]["resultats"] == 1
    f = P.fiche(pid2)
    assert f["date_naissance"] == "1980-05-01"                 # case vide complétée
    assert set(f["roles"]) == {"coureur", "licencie", "benevole"}
    c = sqlite3.connect(db.CHEMIN_BDD)
    assert c.execute("SELECT vma, taille FROM athletes WHERE id=?", (aid2,)).fetchone() == (14, 178)  # VMA locale gardée
    c.close()
    PP.importer(p, remplacer_profil=True)
    c = sqlite3.connect(db.CHEMIN_BDD)
    assert c.execute("SELECT vma FROM athletes WHERE id=?", (aid2,)).fetchone() == (13.2,)
    c.close()


def test_homonymes_il_faut_choisir(base, tmp_path, monkeypatch):
    _, pid, _ = base
    p = PP.exporter(pid)
    p["personne"].pop("date_naissance")
    autre_base(tmp_path, monkeypatch)
    a = P.creer({"nom": "Beltran", "prenom": "Didier", "date_naissance": "1980-05-01"})
    P.creer({"nom": "Beltran", "prenom": "Didier", "date_naissance": "2012-02-02"})
    ap = PP.apercu(p)
    assert ap["etat"] == "ambigu" and len(ap["candidats"]) == 2
    with pytest.raises(PP.ErreurPasseport):
        PP.importer(p)
    assert PP.importer(p, personne_id=a)["personne_id"] == a


def test_fichiers_refuses(tmp_path, base):
    for contenu, attendu in (("pas du json", "illisible"), ('{"format": "autre"}', "pas un passeport"),
                             (json.dumps({"format": PP.FORMAT, "version_format": 99, "personne": {"nom": "A"}}), "plus récente"),
                             (json.dumps({"format": PP.FORMAT, "version_format": 1, "personne": {}}), "nom"),
                             (json.dumps({"format": PP.FORMAT, "version_format": 1, "personne": {"nom": "A"}, "resultats": "x"}), "abîmée")):
        f = tmp_path / "x.json"
        f.write_text(contenu, encoding="utf-8")
        with pytest.raises(PP.ErreurPasseport) as e:
            PP.lire_fichier(f)
        assert attendu in str(e.value)


def test_une_erreur_n_importe_rien(base, tmp_path, monkeypatch):
    _, pid, _ = base
    p = PP.exporter(pid)
    p["personne"]["email"] = "pas-un-mail"
    autre_base(tmp_path, monkeypatch)
    with pytest.raises(PP.ErreurPasseport) as e:
        PP.importer(p)
    assert "e-mail" in str(e.value)
    assert P.lister() == []


def test_index_saisie(base):
    _, pid, _ = base
    assert [i["organisme"] for i in P.index_de(pid)] == ["ITRA", "UTMB Index"] or len(P.index_de(pid)) == 2
    for args in (("", 500, "2026-01-01"), ("ITRA", "abc", "2026-01-01"), ("ITRA", 5000, "2026-01-01"),
                 ("ITRA", 500, "01/01/2099"), ("ITRA", 500, "hier"), ("ITRA", 400, "2026-10-01")):
        with pytest.raises(P.ErreurPersonne):
            P.ajouter_index(pid, *args)
    i = P.ajouter_index(pid, "Betrail", "61,5", "05/10/2026")
    assert P.index_de(pid)[0]["valeur"] == 61.5
    P.supprimer_index(i)
    assert len(P.index_de(pid)) == 2
