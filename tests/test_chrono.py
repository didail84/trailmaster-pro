"""Étape 4.5 : chrono (départs, passages, doublons), classements, publication sur les profils sans doublon."""
import pytest

from noyau.organisation import chrono as C


def test_heures_et_controle():
    assert C.lire_heure("10:42:17", "2027-04-11") == "2027-04-11T10:42:17.000"
    assert C.lire_heure("10h42'17.4", "2027-04-11") == "2027-04-11T10:42:17.400"
    assert C.lire_heure("2027-04-12 01:05:00", "2027-04-11") == "2027-04-12T01:05:00.000"
    assert C.lire_heure("25:61:00", "2027-04-11") is None
    assert C.secondes_entre("2027-04-11T08:30:00", "2027-04-11T10:42:17.4") == 7937.4
    ps = [{"id": 1, "dossard": 3, "heure": "2027-04-11T10:00:00"}, {"id": 2, "dossard": 3, "heure": "2027-04-11T10:05:00"},
          {"id": 3, "dossard": 99, "heure": "2027-04-11T10:06:00"}, {"id": 4, "dossard": None, "heure": "2027-04-11T10:07:00"},
          {"id": 5, "dossard": 4, "heure": "2027-04-11T10:08:00", "annule": 1}]
    c = C.controler_passages(ps, {3, 4})
    assert c["retenus"][3]["id"] == 1 and [p["id"] for p in c["doublons"]] == [2]
    assert [p["id"] for p in c["inconnus"]] == [3] and len(c["sans_dossard"]) == 1 and 4 not in c["retenus"]
    assert C.categorie_course("1985-03-12", "H", "2027-04-11") == "M1H" and C.categorie_course(None, "F", "x") == "?F"


def test_classement():
    e = {"id": 1, "distance_km": 25, "depart_reel": "2027-04-11T08:30:00"}
    ins = [{"id": 1, "dossard": 1, "nom": "A", "sexe": "H", "date_naissance": "1985-01-01"},
           {"id": 2, "dossard": 2, "nom": "B", "sexe": "F", "date_naissance": "1990-01-01"},
           {"id": 3, "dossard": 3, "nom": "C", "sexe": "H", "date_naissance": "1986-01-01"},
           {"id": 4, "dossard": 4, "nom": "D", "sexe": "H", "date_naissance": "1990-01-01", "statut_course": "abandon"},
           {"id": 5, "dossard": 5, "nom": "E", "sexe": "F", "date_naissance": "1990-01-01"},
           {"id": 6, "dossard": 6, "nom": "F", "sexe": "H", "date_naissance": "2000-01-01", "temps_corrige_s": 9000}]
    p = {1: {"heure": "2027-04-11T10:40:00"}, 2: {"heure": "2027-04-11T10:30:00"}, 3: {"heure": "2027-04-11T10:40:00"},
         4: {"heure": "2027-04-11T10:20:00"}}
    l = C.classement(e, ins, p, "2027-04-11")
    assert [x["nom"] for x in l] == ["B", "A", "C", "F", "D"]               # E pas arrivé ; D abandon à la fin
    assert [x["rang"] for x in l[:4]] == [1, 2, 2, 4]                       # ex æquo
    assert l[0]["temps"] == "2:00:00" and l[1]["ecart"] == "+10:00" and l[0]["vitesse"] == 12.5
    assert l[0]["allure"] == "4:48/km" and l[1]["rang_sexe"] == 1 and l[2]["rang_categorie"] == 2      # A et C en M1H
    assert l[3]["temps_s"] == 9000 and l[4]["temps"] == "ABD" and l[4]["rang"] is None
    assert [x["nom"] for x in C.filtrer(l, "sexe", "F")] == ["B"]
    pod = C.podiums(l)
    assert [x["nom"] for x in pod["scratch"]] == ["B", "A", "C"] and [x["nom"] for x in pod["categories"]["M1H"]] == ["A", "C"]


def test_fichier():
    lus, err = C.lire_fichier(b"Dossard;Heure\n12;10:42:17\n13;10:43:01.5\nx;10:00:00\n", "chrono.csv", "2027-04-11")
    assert lus == [{"dossard": 12, "heure": "2027-04-11T10:42:17.000"}, {"dossard": 13, "heure": "2027-04-11T10:43:01.500"}]
    assert len(err) == 1
    lus, _e = C.lire_fichier(b"12;2:12:10\n", "temps.csv", "2027-04-11", "temps")
    assert lus == [{"dossard": 12, "temps_s": 7930}]


def _evenement():
    from noyau.donnees import organisation as dor, club as dclub
    from noyau.club import imports as imp
    cid = dclub.club_id_ou_creer()
    dclub.importer(cid, "2026-2027", imp.analyser(imp.lire_tableau(
        "Nom;Prénom;Date de naissance;Numéro de licence;Formule\nMARTIN;Lucas;12/03/1985;111;competition\n"))["lignes"])
    ev = dor.enregistrer_evenement({"nom": "Trail des Dentelles", "date_debut": "2027-04-11", "commune": "Gigondas"})
    e1 = dor.enregistrer_epreuve(ev, {"nom": "Trail 25 km", "discipline": "trail", "distance_km": 25, "denivele_m": 1200,
                                      "heure_depart": "08:30", "dossard_debut": 1, "dossard_fin": 100})
    pid = dclub.adhesions(cid, "2026-2027")[0]["personne_id"]
    dor.inscrire_adherents(e1, [pid])
    for nom, pre, sx, dn in (("Roux", "Chloé", "F", "1978-11-22"), ("Blanc", "Hugo", "H", "1995-01-01")):
        dor.enregistrer_inscription({"epreuve_id": e1, "nom": nom, "prenom": pre, "sexe": sx, "date_naissance": dn})
    dor.changer_statut([i["id"] for i in dor.inscriptions(ev)], "validee")
    dor.attribuer_dossards(ev)
    return ev, e1, pid, {i["nom"]: i["dossard"] for i in dor.inscriptions(ev)}


def test_base(base_vide):
    from noyau.donnees import chrono as dch, profils as dpro, organisation as dor
    ev, e1, pid, ds = _evenement()
    assert dch.etat(ev)["epreuves"][0]["en_course"] == 3
    dch.donner_depart(e1, "2027-04-11T08:31:00.000")
    assert dor.epreuves(ev)[0]["depart_reel"] == "2027-04-11T08:31:00.000"
    assert dch.ajouter_passage(ev, ds["MARTIN"], "2027-04-11T11:02:10.000")["avertissement"] is None
    assert "double top" in dch.ajouter_passage(ev, ds["MARTIN"], "2027-04-11T11:02:12.000")["avertissement"]
    assert "inconnu" in dch.ajouter_passage(ev, 99, "2027-04-11T11:03:00.000")["avertissement"]
    r = dch.importer_fichier(ev, C.lire_fichier(f"{ds['Roux']};11:40:00\n{ds['Roux']};11:40:00\n".encode(), "c.csv",
                                                "2027-04-11")[0])
    assert r["passages"] == 1
    dch.definir_statut([i["id"] for i in dor.inscriptions(ev) if i["nom"] == "Blanc"], "abandon")
    l = dch.classement(ev, e1)
    assert [x["nom"] for x in l] == ["MARTIN", "Roux", "Blanc"] and l[0]["temps"] == "2:31:10" and l[2]["temps"] == "ABD"
    et = dch.etat(ev)
    assert et["epreuves"][0]["arrives"] == 2 and et["epreuves"][0]["hors_course"] == 1 and len(et["inconnus"]) == 1
    dch.corriger_temps(l[1]["id"], 9000)                                 # Roux corrigée : elle passe devant
    l2 = dch.classement(ev, e1)
    assert [x["nom"] for x in l2[:2]] == ["Roux", "MARTIN"] and l2[0]["temps_s"] == 9000
    dch.corriger_temps(l[1]["id"], None)
    assert dch.export_csv(dch.classement(ev, e1)).lstrip("﻿").startswith("Clt;Dossard;Nom")
    # publication sur les profils : une fois, mise à jour ensuite
    r = dch.publier_sur_profils(ev)
    assert r == {"publies": 1, "mis_a_jour": 0, "sans_profil": 2}
    assert dch.publier_sur_profils(ev) == {"publies": 0, "mis_a_jour": 1, "sans_profil": 2}
    res = dpro.resultats(pid)
    assert len(res) == 1 and res[0]["classement_general"] == 1 and res[0]["nb_classes"] == 2 and res[0]["source"] == \
        "Chrono du club"
    with pytest.raises(dch.ErreurChrono):
        dch.definir_statut([1], "inconnu")


def test_ecrans(base_vide, tmp_path):
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    from noyau.donnees import chrono as dch
    ev, e1, pid, ds = _evenement()
    dch.donner_depart(e1, "2027-04-11T08:30:00.000")
    from interface.organisation import OrganisationFenetre
    f = OrganisationFenetre(1)
    assert f.tabs.count() == 11
    c = f.chrono
    c.heure_manuelle.setText("10:42:17")
    c.saisie.setText(str(ds["MARTIN"]))
    c._top_arrivee()
    assert "MARTIN" in c.retour.text() and c.table.rowCount() == 1
    fichier = tmp_path / "chrono.csv"
    fichier.write_text(f"Dossard;Heure\n{ds['Roux']};11:00:00\n", encoding="utf-8")
    assert c.importer_fichier(str(fichier), "heure", confirmer=False)["passages"] == 1
    k = f.classements
    k.rafraichir()
    assert k.table.rowCount() == 2 and "Lucas" in k.texte_podiums()
    from interface.club_pdf import rendre_classement
    pdf = tmp_path / "classement.pdf"
    rendre_classement(pdf, None, "Trail 25 km", k._lignes)
    assert pdf.read_bytes()[:4] == b"%PDF"
    f.close()
