"""Étape 8 : mise en service (contrôles, recette, répétition générale) et données personnelles (RGPD)."""
import json
from datetime import date

import pytest


def test_recette(base_vide):
    from noyau import recette as RE
    from noyau.donnees import organisation as dor, chrono as dch
    c = {x["code"]: x for x in RE.controles()}
    assert c["base"]["etat"] == "ok" and c["sauvegarde"]["etat"] == "attention" and c["serveur"]["etat"] == "info"
    assert len(RE.recette()) == len(RE.RECETTE) and RE.avancement()[1] == {"total": len(RE.RECETTE), "faits": 0, "problemes": 0}
    RE.noter("e5_nas", "fait", "NAS OMV 7", "Didier")
    RE.noter("photos", "probleme", "dossards pliés mal lus")
    RE.noter("kids", "sans_objet")
    av, t = RE.avancement()
    assert t == {"total": len(RE.RECETTE) - 1, "faits": 1, "problemes": 1} and av["5 · Serveur"]["faits"] == 1
    assert next(x for x in RE.recette() if x["code"] == "e5_nas")["note"] == "NAS OMV 7"
    with pytest.raises(ValueError):
        RE.noter("inconnu", "fait")
    ev = RE.creer_repetition()
    assert RE.creer_repetition() == ev and RE.repetition() == ev
    ins = dor.inscriptions(ev)
    assert len(ins) == 40 and all(i["dossard"] for i in ins) and len(dor.epreuves(ev)) == 2
    dch.ajouter_passage(ev, ins[0]["dossard"], "2026-11-07T10:00:00")
    assert RE.supprimer_repetition() and RE.repetition() is None and not dor.evenement(ev)
    from data.database import definir_parametre
    definir_parametre("derniere_sauvegarde", date.today().isoformat())
    assert {x["code"]: x for x in RE.controles()}["sauvegarde"]["etat"] == "ok"
    assert RE.rapport()["total"]["faits"] == 1


def test_rgpd(base_vide):
    from noyau import rgpd as RG
    from noyau.donnees import club as dclub, organisation as dor, comptes as dco, personnes as dper
    from noyau.club import imports as imp
    cid = dclub.enregistrer_club({"nom": "Ventoux Trail"})
    dclub.importer(cid, "2021-2022", imp.analyser(imp.lire_tableau("Nom;Prénom;Date de naissance\nANCIEN;Paul;01/01/1970\n"))["lignes"])
    dclub.importer(cid, "2026-2027", imp.analyser(imp.lire_tableau("Nom;Prénom;Date de naissance\nFAURE;Léa;30/06/2016\n"))["lignes"])
    lea = next(a["personne_id"] for a in dclub.adhesions(cid, "2026-2027"))
    dco.enregistrer_consentement(lea, "image", True)
    ev = dor.enregistrer_evenement({"nom": "Trail 2024", "date_debut": "2024-10-12"})
    e = dor.enregistrer_epreuve(ev, {"nom": "10 km", "dossard_debut": 1, "dossard_fin": 9})
    dor.enregistrer_inscription({"epreuve_id": e, "nom": "FAURE", "prenom": "Léa", "personne_id": lea, "statut": "validee",
                                 "email": "lea@ex.org", "telephone": "0600000000"})
    dor.enregistrer_inscription({"epreuve_id": e, "nom": "AUTRE", "statut": "validee", "email": "x@ex.org"})
    reg = RG.registre({"club", "kids", "organisation", "photos_dossard", "trail_live", "serveur"})
    assert len(reg) == 6 and any("mineurs" in t["personnes"] for t in reg) and "consentement" in reg[3]["base_legale"]
    assert RG.registre(set()) == []
    n = RG.a_nettoyer(date(2026, 11, 6))
    assert n["inscrits"] == 2 and [a["nom"] for a in RG.anciens_adherents(date(2026, 11, 6))] == ["ANCIEN"]
    RG.regler_duree("inscrits", 48)
    assert RG.a_nettoyer(date(2026, 11, 6))["inscrits"] == 0
    with pytest.raises(ValueError):
        RG.regler_duree("inscrits", 0)
    RG.regler_duree("inscrits", 12)
    assert RG.nettoyer(["inscrits"], date(2026, 11, 6)) == {"inscrits": 2}
    assert all(i["email"] is None and i["nom"] in ("FAURE", "AUTRE") for i in dor.inscriptions(ev))   # résultats gardés
    d = RG.donnees_de(lea)
    assert d["fiche"][0]["nom"] == "FAURE" and d["adhesions"] and d["consentements"] and len(d["inscriptions"]) == 1
    json.loads(RG.export_json(lea))
    dem = RG.enregistrer_demande("effacement", "Léa Faure", lea, "2026-09-01")
    assert RG.demandes()[0]["en_retard"]
    RG.effacer_personne(lea)
    RG.traiter_demande(dem, "effacée")
    assert dper.fiche(lea) is None and not RG.demandes()[0]["en_retard"]
    assert sorted(i["nom"] for i in dor.inscriptions(ev)) == ["AUTRE", "Anonyme"]
    with pytest.raises(ValueError):
        RG.enregistrer_demande("autre", "x")
    with pytest.raises(ValueError):
        RG.effacer_personne(dper.creer({"nom": "Coureur"}, ["coureur"]))         # profil coureur : refus
    i = RG.enregistrer_incident({"description": "ordinateur du trésorier volé", "personnes": 120})
    x = RG.incidents()[0]
    assert x["id"] == i and x["limite_cnil"] > x["constate_le"]
    RG.enregistrer_incident({"cnil_le": "2026-11-07", "clos": 1}, i)
    assert RG.incidents()[0]["clos"] == 1


def test_fenetre(base_vide):
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    from interface.mise_en_service import MiseEnServiceFenetre
    f = MiseEnServiceFenetre(1)
    assert f.tabs.count() == 3
    f.recette.rafraichir()
    assert f.recette.t_rec.rowCount() > 20 and f.recette.t_ctrl.rowCount() >= 8
    f.donnees.rafraichir()
    assert f.donnees.t_dur.rowCount() == 5
