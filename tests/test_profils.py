"""Étape 4.3 : profils des licenciés, résultats sans doublon, classements extérieurs, diplômes, séances partagées."""
import sqlite3
from datetime import date, timedelta

import pytest

from noyau.club import profils as P

CLASSEMENT = ("Clt\tDossard\tNom\tPrénom\tTemps\tCat.\tClt Cat\tClub\n"
              "1\t12\tDURAND\tPierre\t1:52:10\tSEH\t1\tUAC\n"
              "7\t5\tMARTIN\tLucas\t2:05:30\tM1H\t2\tVentoux Trail Athlé\n"
              "ABD\t8\tROUX\tChloé\tABD\tM2F\t\tVentoux Trail Athlé\n"
              "9\t9\tFAURE\tLéa\t2:10:00\tSEF\t3\tVentoux Trail Athlé\n")


def test_temps_et_records():
    assert P.lire_temps("1:23:45") == 5025 and P.lire_temps("1h23") == 4980 and P.lire_temps("38'40") == 2320
    assert P.lire_temps("2h05m10s") == 7510 and P.lire_temps("ABD") is None
    assert P.texte_temps(5025) == "1:23:45" and P.texte_temps(2292.4, True) == "38:12.4"
    assert P.distance_route(21.1) == "Semi-marathon" and P.distance_route(12) is None
    rs = [{"course": "10 km A", "date": "2026-05-01", "distance_km": 10, "temps_s": 2400},
          {"course": "10 km B", "date": "2026-09-01", "distance_km": 10.05, "temps_s": 2350},
          {"course": "Trail X", "date": "2026-06-01", "distance_km": 25, "denivele_m": 1200, "temps_s": 14400,
           "classement_categorie": 2},
          {"course": "Ultra", "date": "2026-07-01", "distance_km": 100, "denivele_m": 5000, "statut": "abandon"}]
    r = P.records(rs)
    assert r["route"][0]["course"] == "10 km B" and r["route"][0]["allure"] == "3:54/km"
    assert r["trail"][0]["code"] == "trail_court" and r["trail"][0]["vitesse_ke"] == 9.25      # 37 km-effort en 4 h
    assert r["plus_longue"]["course"] == "Trail X"                       # l'abandon ne compte pas
    b = P.bilan(rs)
    assert b == {"courses": 4, "classees": 3, "abandons": 1, "km": 45.0, "dplus": 1200, "podiums": 1,
                 "victoires_categorie": 0}


def test_classement_exterieur():
    lignes, n = P.lire_classement(CLASSEMENT)
    assert n == 3 and [l["statut"] for l in lignes] == ["classe", "classe", "abandon", "classe"]
    assert lignes[1]["temps_s"] == 7530 and lignes[1]["rang_categorie"] == 2 and lignes[1]["sexe"] == "H"
    adh = [{"personne_id": 1, "nom": "Martin", "prenom": "Lucas", "date_naissance": "1985-03-12"},
           {"personne_id": 2, "nom": "Roux", "prenom": "Chloé", "date_naissance": None},
           {"personne_id": 3, "nom": "Faure", "prenom": "Léa", "date_naissance": "2000-01-01"},
           {"personne_id": 4, "nom": "Faure", "prenom": "Léa", "date_naissance": "1990-01-01"}]
    paires = P.associer(lignes, adh)
    assert [a["personne_id"] for _l, a in paires] == [1, 2]              # deux Léa Faure : pas devinée
    assert P.separer_nom("MARTIN Lucas") == ("MARTIN", "Lucas") and P.separer_nom("Lucas MARTIN") == ("MARTIN", "Lucas")
    assert P.etat_diplome({"date_validite": (date.today() - timedelta(days=1)).isoformat()}) == "expiré"
    assert P.etat_diplome({"date_validite": (date.today() + timedelta(days=30)).isoformat()}) == "bientôt"
    assert P.etat_diplome({"date_validite": None}) == "sans date"


def _club():
    from noyau.donnees import club as dclub
    from noyau.club import imports as imp
    cid = dclub.club_id_ou_creer()
    dclub.enregistrer_club({"nom": "Ventoux Trail Athlé"}, cid)
    dclub.importer(cid, "2026-2027", imp.analyser(imp.lire_tableau(
        "Nom;Prénom;Date de naissance;Numéro de licence;Formule\nMARTIN;Lucas;12/03/1985;111;competition\n"
        "ROUX;Chloé;22/11/1978;222;running\n"))["lignes"])
    return cid, {a["nom"]: a["personne_id"] for a in dclub.adhesions(cid, "2026-2027")}


def test_resultats_sans_doublon(base_vide):
    from noyau.donnees import profils as dpro
    import data.database as db
    cid, adh = _club()
    c = sqlite3.connect(db.CHEMIN_BDD)
    c.execute("UPDATE athletes SET personne_id=? WHERE id=1", (adh["MARTIN"],))
    c.commit()
    r1 = dpro.enregistrer_resultat(adh["MARTIN"], {"date": "2026-10-04", "course": "10 km de Carpentras",
                                                   "distance_km": 10, "temps_s": "38:40", "classement_general": 12})
    r2 = dpro.enregistrer_resultat(adh["MARTIN"], {"date": "2026-10-04", "course": "10 km de Carpentras",
                                                   "distance_km": 10, "temps_s": "38:30"})
    assert r1 == (r2[0], True) and r2[1] is False
    assert len(dpro.resultats(adh["MARTIN"])) == 1 and dpro.resultats(adh["MARTIN"])[0]["temps_s"] == 2310
    # recopié une seule fois dans les résultats du coureur
    assert c.execute("SELECT COUNT(*), MAX(temps) FROM resultats_courses WHERE athlete_id=1").fetchone() == (1, "38:30")
    with pytest.raises(dpro.ErreurProfil):
        dpro.enregistrer_resultat(adh["MARTIN"], {"date": "2026-10-04", "course": " "})
    # import d'un classement extérieur, deux fois : pas de doublon
    lignes, n = P.lire_classement(CLASSEMENT)
    course = {"course": "Trail des Collines", "date": "2026-11-15", "distance_km": 25, "denivele_m": 900}
    r = dpro.importer_classement(cid, "2026-2027", course, lignes, n)
    assert r["associes"] == 2 and r["ajoutes"] == 2 and r["non_trouves"] == ["Léa FAURE"]
    assert dpro.importer_classement(cid, "2026-2027", course, lignes, n)["mis_a_jour"] == 2
    roux = dpro.resultats(adh["ROUX"])
    assert len(roux) == 1 and roux[0]["statut"] == "abandon"
    p = dpro.profil(adh["MARTIN"], cid, "2026-2027")
    assert p["bilan_saison"]["courses"] == 2 and p["records"]["route"][0]["distance"] == "10 km"
    assert p["categorie"]["code"] == "M1" and p["athlete_id"] == 1
    assert len(dpro.resultats_du_club(cid, "2026-09-01")) == 3


def test_entraineurs_et_seances(base_vide):
    from noyau.donnees import profils as dpro, club as dclub, agenda_club as dag, personnes as dper
    import data.database as db
    cid, adh = _club()
    with pytest.raises(dpro.ErreurProfil):
        dpro.enregistrer_diplome(adh["ROUX"], {"intitule": ""})
    dpro.enregistrer_diplome(adh["ROUX"], {"intitule": "Entraîneur Running",
                                           "date_validite": (date.today() + timedelta(days=20)).isoformat()})
    assert "entraineur" in dper.roles(adh["ROUX"])
    e = dpro.entraineurs(cid)
    assert len(e) == 1 and e[0]["alertes"] == ["Entraîneur Running : bientôt"]
    g = dclub.enregistrer_groupe(cid, {"nom": "Adultes", "entraineur_id": adh["ROUX"]})
    dclub.definir_groupes(adh["MARTIN"], [g], cid)
    with pytest.raises(dpro.ErreurProfil):
        dpro.enregistrer_modele(cid, {"titre": "x", "fractionne_code": "inconnu"})
    m = dpro.enregistrer_modele(cid, {"titre": "30/30 du mardi", "fractionne_code": "30_30", "contenu": "Échauffement 20 min",
                                      "auteur_id": adh["ROUX"]})
    assert "Fractionné : 30/30" in dpro.texte_modele(dpro.modele(m)) and "% VMA 15" in dpro.texte_modele(dpro.modele(m), 15)
    jour = (date.today() + timedelta(days=3)).isoformat()
    s = dpro.planifier(m, cid, jour, g, "18:30")
    assert dag.seance(s)["entraineur_id"] == adh["ROUX"] and dpro.modeles(cid)[0]["fois"] == 1
    assert dpro.entraineurs(cid)[0]["prochaines"][0]["id"] == s
    # dans une séance déjà prévue, pas de nouvelle séance
    autre = dag.enregistrer_seance(cid, {"titre": "Piste", "date": jour, "groupe_id": g})
    assert dpro.planifier(m, cid, jour, g, seance_id=autre) == autre and "30/30" in dag.seance(autre)["contenu"]
    # envoi aux coureurs : Martin a un profil coureur avec une VMA
    c = sqlite3.connect(db.CHEMIN_BDD)
    c.execute("UPDATE athletes SET personne_id=?, vma=16 WHERE id=1", (adh["MARTIN"],))
    c.commit()
    assert dpro.envoyer_aux_coureurs(s) == 1 and dpro.envoyer_aux_coureurs(s) == 0
    nom, etapes, notes = c.execute("SELECT nom, etapes_json, notes FROM seances_structurees WHERE athlete_id=1").fetchone()
    assert nom == "30/30 du mardi" and "Effort" in etapes and "VMA 16" in notes
    dpro.supprimer_modele(m)
    assert dag.seance(s) is not None


def test_ecrans(base_vide):
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    from noyau.donnees import profils as dpro
    cid, adh = _club()
    dpro.enregistrer_resultat(adh["MARTIN"], {"date": "2026-10-04", "course": "10 km de Carpentras", "distance_km": 10,
                                              "temps_s": 2310})
    from interface.club import ClubFenetre
    from interface.club_profils import DialogueImportClassement
    f = ClubFenetre(1)
    assert f.tabs.count() == 11
    l = f.licencies
    l.combo_saison.setCurrentIndex(max(0, l.combo_saison.findData("2026-2027")))
    l.choisir(adh["MARTIN"])
    assert "Lucas" in l.fiche.text() and "10 km" in l.fiche.text() and l.table.rowCount() == 1
    d = DialogueImportClassement(l, cid, "2026-2027")
    d.texte.setPlainText(CLASSEMENT)
    d._apercu()
    assert "Adhérents retrouvés : 2" in d.label.text()
    d.course.setText("Trail des Collines")
    d.accept()
    assert d.resultat["ajoutes"] == 2
    f.seances.actualiser()
    f.entraineurs.actualiser()
    f.close()
