"""Annuaire trail : base de référence PACA, fiches à soi, favoris, import, lien avec le matériel."""
import json

import pytest

from noyau.annuaire import regles as R


def test_reference_coherente():
    ref = R.lire_reference()
    s, m = ref["structures"], ref["marques"]
    assert len(s) >= 120 and len(m) >= 100
    assert len({x["cle"] for x in s + m}) == len(s) + len(m)                 # clés uniques
    for x in s:
        assert x["type"] in R.LIBELLE_TYPE and x["source"]
        assert x["departement"] in R.NOM_DEPARTEMENT                        # région PACA
        assert not x["code_postal"] or R.departement_de(x["code_postal"]) == x["departement"]
        if x["type"] != "magasin":
            assert x["adresse"] is None                                    # clubs : la commune seulement
        else:
            assert x["categorie"] in R.LIBELLE_CATEGORIE_MAGASIN
    for x in m:
        assert x["categories"] and all(c in R.LIBELLE_CATEGORIE_MARQUE for c in x["categories"]) and x["pays"]
    types = {x["type"] for x in s}
    assert {"club_athle", "club_trail", "ecole_trail", "section_trail", "magasin"} <= types


def test_regles():
    assert R.departement_de("84200") == "84" and R.departement_de("20100") == "2A" and R.departement_de("x") is None
    f = R.verifier({"type": "magasin", "nom": " Run ", "code_postal": "84 200", "site": "exemple.fr"})
    assert f["nom"] == "Run" and f["departement"] == "84" and f["site"] == "https://exemple.fr"
    with pytest.raises(R.ErreurAnnuaire):
        R.verifier({"type": "marque", "nom": "X", "categories": "skis"})
    with pytest.raises(R.ErreurAnnuaire):
        R.verifier({"type": "club_athle", "nom": ""})
    fiches = [{"type": "club_trail", "nom": "Sablet Terre de Trail", "commune": "Sablet", "departement": "84"},
              {"type": "magasin", "nom": "Run", "commune": "Gap", "departement": "05", "categorie": "specialiste",
               "favori": 1},
              {"type": "marque", "nom": "Petzl", "pays": "France", "categories": ["frontales"]}]
    assert [f["nom"] for f in R.filtrer(fiches, recherche="terre sablet")] == ["Sablet Terre de Trail"]
    assert [f["nom"] for f in R.filtrer(fiches, categorie="frontales")] == ["Petzl"]
    assert [f["nom"] for f in R.filtrer(fiches, favoris=True)] == ["Run"]
    assert [f["nom"] for f in R.filtrer(fiches, departement="84")] == ["Sablet Terre de Trail"]
    assert "Petzl+trail+running" in R.recherche_web(fiches[2])
    lues, err = R.lire_csv("type;nom;commune;code_postal\ntrail;Mon club;Bédoin;84410\nmagasin;;Apt;84400\n")
    assert lues[0]["type"] == "club_trail" and lues[0]["departement"] == "84" and len(err) == 1
    texte = R.vers_csv(fiches)
    assert texte.startswith("﻿type;nom") and "Petzl" in texte


def test_base(base_vide):
    from noyau.donnees import annuaire as dan
    r = dan.synchroniser()
    ref = R.lire_reference()
    assert r["ajoutees"] == len(ref["structures"]) + len(ref["marques"])
    assert dan.synchroniser()["ajoutees"] == 0                                # déjà à jour
    # une fiche de référence corrigée n'est plus écrasée
    f = next(x for x in dan.fiches(("club_trail",)) if x["nom"] == "Sablet Terre de Trail")
    dan.enregistrer({**f, "site": "https://sablet.example", "mes_notes": "sortie le dimanche"}, f["id"])
    dan.definir_favori(f["id"])
    ref2 = json.loads(json.dumps(ref))
    ref2["version"] = "test"
    for x in ref2["structures"]:
        if x["nom"] == "Sablet Terre de Trail":
            x["site"] = "https://autre.example"
        if x["nom"] == "Union Athlétique Orangeoise":
            x["notes"] = "mise à jour"
    r = dan.synchroniser(ref2)
    g = dan.fiche(f["id"])
    assert g["site"] == "https://sablet.example" and g["favori"] and g["mes_notes"] == "sortie le dimanche"
    assert next(x for x in dan.fiches() if x["nom"] == "Union Athlétique Orangeoise")["notes"] == "mise à jour"
    # retirer : masquée (référence) ou supprimée (fiche à soi)
    dan.supprimer(f["id"])
    assert dan.fiche(f["id"])["masque"] and f["id"] not in {x["id"] for x in dan.fiches()}
    dan.synchroniser(ref2, forcer=True)
    assert dan.fiche(f["id"])["masque"]                                     # ne revient pas
    assert dan.reafficher_masquees() == 1
    mien = dan.enregistrer({"type": "magasin", "nom": "Trail Shop Ventoux", "commune": "Bédoin", "code_postal": "84410",
                            "categorie": "specialiste"})
    with pytest.raises(dan.ErreurAnnuaire):
        dan.enregistrer({"type": "magasin", "nom": "trail shop ventoux", "commune": "BÉDOIN".lower().capitalize()})
    dan.supprimer(mien)
    assert dan.fiche(mien) is None
    # import : ajoute, complète les vides, jamais de doublon
    lues, _e = R.lire_csv("type;nom;commune;code_postal;site\nclub_trail;Nouveau Trail Club;Apt;84400;nt.example\n"
                          "club_athle;Union Athlétique Orangeoise;Orange;84100;uao.example\n")
    assert dan.importer(lues) == {"ajoutees": 1, "completees": 1}
    assert next(x for x in dan.fiches() if x["nom"] == "Union Athlétique Orangeoise")["site"] == "https://uao.example"
    # suggestions pour le matériel
    assert dan.noms_de_marques("frontales")[0] in {"Petzl", "Black Diamond", "Fenix", "Ledlenser", "Lupine", "Nitecore",
                                                   "Silva"}
    assert "Terre de Running Luberon" in dan.noms_de_magasins()
    assert dan.chiffres()["marque"]["?"] == len(ref["marques"])


def test_materiel_marque_magasin(base_vide):
    from noyau.donnees import equipement as deq, annuaire as dan
    mid = deq.creer_equipement(1, {"nom": "Frontale", "equipement": "frontale", "marque": "Petzl",
                                   "magasin": "Terre de Running Luberon"})
    e = deq.equipement(mid)
    assert e["marque"] == "Petzl" and e["magasin"] == "Terre de Running Luberon"
    assert dan.materiel_par_marque(1) == {"Petzl": 1}


def test_ecrans(base_vide):
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    from interface.annuaire import AnnuaireFenetre, DialogueFiche
    f = AnnuaireFenetre(1)
    assert f.tabs.count() == 3
    c = f.clubs
    total = c.table.rowCount()
    c.f_dep.setCurrentIndex(c.f_dep.findData("84"))
    assert 0 < c.table.rowCount() < total
    c.recherche.setText("sablet")
    assert c.table.rowCount() == 1
    c.table.selectRow(0)
    assert "Sablet" in c.label_detail.text() and "Chercher sur le web" in c.label_detail.text()
    m = f.magasins
    m.f_cat.setCurrentIndex(m.f_cat.findData("specialiste"))
    assert all(x["categorie"] == "specialiste" for x in m._vues) and m._vues
    d = DialogueFiche(f, "marque")
    d.nom.setText("Marque Test")
    d.cases["chaussures"].setChecked(True)
    d.accept()
    f.marques.actualiser()
    f.marques.recherche.setText("marque test")
    assert f.marques.table.rowCount() == 1
    f.close()
    from interface.materiel_course import DialogueEquipement
    e = DialogueEquipement(None, None, "frontale")
    assert e.marque.completer() is not None and e.marque.completer().model().rowCount() > 100
    e.marque.setText("Petzl")
    assert e.valeurs()["marque"] == "Petzl"
