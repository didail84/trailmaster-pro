"""Étape 4.4 : événement, épreuves, inscriptions contrôlées (réglementation FFA 2025-2026), dossards."""
import pytest

from noyau.organisation import regles as R

EV = {"date_debut": "2027-04-11", "pps_validite_mois": 3, "autorisation_parentale": 1}
TRAIL25 = {"id": 1, "nom": "Trail 25 km", "discipline": "trail", "distance_km": 25, "denivele_m": 1200, "competitive": 1}
ROUTE10 = {"id": 2, "nom": "10 km", "discipline": "route", "distance_km": 10, "denivele_m": 0, "competitive": 1}


def _i(**k):
    i = {"nom": "X", "date_naissance": "1985-03-12", "justificatif": "licence_ffa", "numero_licence": "123",
         "type_licence": "competition", "justificatif_valide": 1, "contact_urgence_tel": "06", "montant": 25,
         "montant_paye": 25}
    i.update(k)
    return i


def test_age_et_distance():
    # route : cadets 15 km au plus, minimes 5 km
    assert R.controle_age(ROUTE10, "2010-06-01", "2027-04-11")[0] == []              # cadet (U18)
    assert "5 km au plus" in R.controle_age(ROUTE10, "2012-06-01", "2027-04-11")[0][0]  # minime
    # trail : cadets et juniors limités en km-effort (37 ici), plus de 950 m D+ : juniors au minimum
    m, _a = R.controle_age(TRAIL25, "2009-01-01", "2027-04-11")                    # junior : 25 km-effort
    assert "25 km-effort" in m[0]
    m, _a = R.controle_age(TRAIL25, "2010-06-01", "2027-04-11")                    # cadet
    assert any("15 km-effort" in x for x in m) and any("juniors au minimum" in x for x in m)
    assert R.controle_age(TRAIL25, "2006-06-01", "2027-04-11")[0] == []              # espoir
    petit = {"discipline": "trail", "distance_km": 3, "denivele_m": 150, "competitive": 1}
    assert R.controle_age(petit, "2014-03-01", "2027-04-11")[0] == []                # benjamin : 3 km, 150 m
    assert R.controle_age({**petit, "distance_km": 4}, "2014-03-01", "2027-04-11")[0]
    assert R.controle_age(ROUTE10, None, "2027-04-11")[0] == ["date de naissance"]
    assert R.controle_age({**ROUTE10, "categorie_min": "SE"}, "2005-01-01", "2027-04-11")[0]


def test_sante():
    assert R.controle_sante(_i(), "2027-04-11")[0] == []
    assert "non acceptée" in R.controle_sante(_i(type_licence="sante"), "2027-04-11")[0][0]
    assert R.controle_sante(_i(justificatif="pps", pps_date="2027-02-01"), "2027-04-11")[0] == []
    assert "3 mois" in R.controle_sante(_i(justificatif="pps", pps_date="2026-12-01"), "2027-04-11")[0][0]
    assert "majeurs" in R.controle_sante(_i(justificatif="pps", pps_date="2027-03-01", date_naissance="2012-01-01"),
                                         "2027-04-11")[0][0]
    assert R.controle_sante(_i(justificatif="questionnaire_mineur", questionnaire_mineur=1, date_naissance="2012-01-01"),
                            "2027-04-11")[0] == []
    assert "six mois" in R.controle_sante(_i(justificatif="certificat", certificat_date="2026-08-01",
                                             date_naissance="2012-01-01"), "2027-04-11")[0][0]
    assert R.controle_sante(_i(justificatif=None), "2027-04-11")[0]


def test_dossier_tarif_dossards():
    d = R.dossier(_i(date_naissance="2012-01-01", justificatif="questionnaire_mineur", questionnaire_mineur=1), ROUTE10, EV)
    assert d["mineur"] and "autorisation parentale" in d["manques"] and d["categorie"]["code"] == "MI"
    assert R.dossier(_i(), TRAIL25, EV)["complet"]
    assert "paiement" in R.dossier(_i(montant_paye=10), TRAIL25, EV)["manques"][0]
    rando = {"discipline": "randonnee", "competitive": 0, "distance_km": 10}
    assert R.dossier(_i(justificatif=None, date_naissance=None), rando, EV)["complet"]
    e = {"tarif": 28, "tarif_licencie": 25, "tarif_tardif": 33}
    assert R.tarif(e) == 28 and R.tarif(e, True, "2027-03-01") == 25
    assert R.tarif(e, True, "2027-04-02", "2027-04-01") == 33
    assert R.chevauchements([{"nom": "a", "dossard_debut": 1, "dossard_fin": 400},
                             {"nom": "b", "dossard_debut": 300, "dossard_fin": 500}]) == [("a", "b")]


def test_base(base_vide, tmp_path):
    from noyau.donnees import organisation as dor, calendrier as dcal
    ev = dor.enregistrer_evenement({"nom": "Trail des Dentelles", "date_debut": "2027-04-11", "commune": "Gigondas",
                                    "code_postal": "84190", "date_tarif_tardif": "2027-04-01"})
    with pytest.raises(dor.ErreurOrganisation):
        dor.enregistrer_evenement({"nom": " ", "date_debut": "2027-04-11"})
    e1 = dor.enregistrer_epreuve(ev, {"nom": "Trail 25 km", "discipline": "trail", "distance_km": 25, "denivele_m": 1200,
                                      "tarif": 28, "tarif_licencie": 25, "dossard_debut": 1, "dossard_fin": 2, "quota": 2})
    e2 = dor.enregistrer_epreuve(ev, {"nom": "Trail 12 km", "discipline": "trail", "distance_km": 12, "denivele_m": 450,
                                      "tarif": 15, "dossard_debut": 500, "dossard_fin": 799})
    a = dor.enregistrer_inscription({"epreuve_id": e1, "nom": "Martin", "prenom": "Lucas", "date_naissance": "1985-03-12",
                                     "justificatif": "licence_ffa", "numero_licence": "123", "type_licence": "competition",
                                     "justificatif_valide": 1, "contact_urgence_tel": "06", "montant_paye": 25,
                                     "date_inscription": "2027-03-01"})
    assert dor.inscription(a)["montant"] == 25                               # tarif licencié
    with pytest.raises(dor.ErreurOrganisation):
        dor.enregistrer_inscription({"epreuve_id": e1, "nom": "martin", "prenom": "lucas", "date_naissance": "1985-03-12"})
    b = dor.enregistrer_inscription({"epreuve_id": e1, "nom": "Roux", "prenom": "Chloé", "date_naissance": "1978-11-22",
                                     "justificatif": "pps", "pps_date": "2027-03-01", "montant_paye": 28,
                                     "contact_urgence_tel": "07", "date_inscription": "2027-03-02"})
    c = dor.enregistrer_inscription({"epreuve_id": e1, "nom": "Blanc", "prenom": "Hugo", "date_naissance": "1990-01-01"})
    assert dor.inscription(c)["statut"] == "liste_attente"                    # quota de 2 atteint
    assert dor.valider_complets(ev) == 2
    r = dor.attribuer_dossards(ev)
    assert r["attribues"] == 2 and sorted(i["dossard"] for i in dor.inscriptions(ev) if i["dossard"]) == [1, 2]
    with pytest.raises(dor.ErreurOrganisation):
        dor.enregistrer_inscription({"dossard": 1}, c)
    dor.marquer_retrait(a)
    assert dor.retirer_dossards(ev) == 1 and dor.inscription(a)["dossard"] == 1
    dor.enregistrer_paiement(c, 28, "Espèces")
    assert dor.inscription(c)["montant_paye"] == 28
    ch = dor.chiffres(ev)
    assert ch["total"]["inscrits"] == 3 and ch["total"]["valides"] == 2 and ch["epreuves"][0]["places"] == -1
    # import Njuko : épreuve par nom ou distance, commandes annulées écartées, pas de doublon
    csv = ("Nom;Prénom;Sexe;Date de naissance;Épreuve;N° licence;Montant;Numéro de commande;Statut\n"
           "Durand;Emma;F;05/07/1990;Trail 12 km;;15;N1;Payé\nGiraud;Paul;M;14/02/1960;12 km;456;15;N2;Payé\n"
           "Faure;Léa;F;30/06/1990;Trail 12 km;;15;N3;Remboursé\nX;Y;M;01/01/1990;Marathon;;0;N4;Payé\n")
    an = dor.analyser_import(csv.encode(), "njuko.csv", ev)
    assert len(an["lignes"]) == 3 and an["epreuves_inconnues"] == ["Marathon"]
    assert dor.importer(an["lignes"], "njuko")["ajoutees"] == 2
    assert dor.importer(an["lignes"], "njuko")["deja"] == 2
    giraud = next(i for i in dor.inscriptions(ev) if i["nom"] == "Giraud")
    assert giraud["justificatif"] == "licence_ffa" and giraud["epreuve_id"] == e2
    # adhérents du club
    from noyau.donnees import club as dclub
    from noyau.club import imports as imp
    cid = dclub.club_id_ou_creer()
    dclub.importer(cid, "2026-2027", imp.analyser(imp.lire_tableau(
        "Nom;Prénom;Date de naissance;Numéro de licence;Formule\nARNAUD;Camille;03/01/1986;999;competition\n"))["lignes"])
    pid = dclub.adhesions(cid, "2026-2027")[0]["personne_id"]
    assert dor.inscrire_adherents(e2, [pid])["ajoutees"] == 1
    arnaud = next(i for i in dor.inscriptions(ev) if i["nom"] == "ARNAUD")
    assert arnaud["numero_licence"] == "999" and arnaud["type_licence"] == "competition"
    # exports et calendrier
    assert dor.export_csv(dor.inscriptions(ev)).lstrip("﻿").startswith("Dossard;Nom")
    assert "Tél. à prévenir" in dor.export_csv(dor.inscriptions(ev), "complet")
    r = dor.publier_dans_le_calendrier(ev)
    assert r["ajoutees"] == 1 and dor.publier_dans_le_calendrier(ev)["ajoutees"] == 0
    cal = next(x for x in dcal.courses() if x["nom"] == "Trail des Dentelles")
    assert len(cal["epreuves"]) == 2 and cal["source"] == "Mon organisation"
    with pytest.raises(dor.ErreurOrganisation):
        dor.supprimer_epreuve(e1)
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    from interface.club_pdf import rendre_retrait_dossards
    pdf = tmp_path / "retrait.pdf"
    rendre_retrait_dossards(pdf, dor.evenement(ev), [i for i in dor.inscriptions(ev) if i["statut"] == "validee"])
    assert pdf.read_bytes()[:4] == b"%PDF"


def test_ecrans(base_vide, tmp_path):
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    from noyau.donnees import organisation as dor
    ev = dor.enregistrer_evenement({"nom": "Trail test", "date_debut": "2030-04-11"})
    e1 = dor.enregistrer_epreuve(ev, {"nom": "Trail 12 km", "discipline": "trail", "distance_km": 12, "denivele_m": 400,
                                      "tarif": 15, "dossard_debut": 1, "dossard_fin": 100})
    from interface.organisation import OrganisationFenetre, DialogueInscription
    f = OrganisationFenetre(1)
    assert f.tabs.count() == 11 and f.evenement_id == ev
    fichier = tmp_path / "njuko.csv"
    fichier.write_text("Nom;Prénom;Date de naissance;Épreuve;Montant\nDurand;Emma;05/07/1990;Trail 12 km;15\n",
                       encoding="utf-8")
    r = f.inscriptions.importer_fichier(str(fichier), confirmer=False)
    assert r["ajoutees"] == 1 and f.inscriptions.table.rowCount() == 1
    d = DialogueInscription(f, ev, dor.inscriptions(ev)[0])
    assert "Il manque" in d.label.text()
    d.justif.setCurrentIndex(d.justif.findData("pps"))
    d.c_pps.setChecked(True)
    d.close()
    f.choisir(ev)
    assert f.tableau.cartes["inscrits"].valeur.text() == "1"
    assert f.evenement_ecran.table.rowCount() == 1
    f.close()
