"""Chantier E : Analyse (prévu ou réel, bilans du club, bilans des événements)."""
import pytest

from noyau.analyse import bilans as B


def test_regles():
    assert B.lire_temps("3:12:05") == 11525 and B.lire_temps("45:10") == 2710 and B.lire_temps("3h12") == 11520
    assert B.lire_temps("") is None and B.lire_temps("n'importe") is None
    assert B.meme_course("Trail des Dentelles 25 km", "2026-10-12", "Dentelles", "2026-10-12")
    assert not B.meme_course("Trail des Dentelles", "2026-10-12", "Ventoux", "2026-10-12")
    assert not B.meme_course("Dentelles", "2026-10-12", "Dentelles", "2026-10-13")
    res = [{"id": 1, "nom": "Dentelles", "date": "2026-10-12", "temps": "3:30:00"},
           {"id": 2, "nom": "Ventoux", "date": "2026-06-01", "temps": "2:00:00"},
           {"id": 3, "nom": "Sans roadbook", "date": "2026-05-01", "temps": "1:00:00"}]
    prev = [{"id": 10, "nom": "Trail des Dentelles", "date": "2026-10-12", "prevu_s": 3 * 3600,
             "prudent_s": 3.3 * 3600, "ambitieux_s": 2.82 * 3600},
            {"id": 11, "nom": "Ventoux", "date": "2026-06-01", "prevu_s": 7200, "prudent_s": 7920, "ambitieux_s": 6768}]
    lignes, syn = B.prevu_reel(res, prev)
    assert [l["resultat_id"] for l in lignes] == [1, 2]
    assert lignes[0]["ecart_s"] == 1800 and lignes[0]["ecart_pct"] == 16.7 and lignes[0]["scenario"] == "plus lent que prudent"
    assert lignes[1]["scenario"] == "réaliste"
    assert syn["courses"] == 2 and syn["facteur"] == pytest.approx(1.083, abs=0.001) and "8 % plus lent" in syn["texte"]
    assert B.synthese(lignes[:1])["facteur"] is None                  # une seule course : pas de correction
    assert B.synthese([dict(lignes[0], reel_s=99999)] * 3)["facteur"] == 1.2   # borné
    assert B.evolution({"2025-2026": 40, "2024-2025": 30, "2026-2027": 45}) == [
        ("2024-2025", 30, None), ("2025-2026", 40, 10), ("2026-2027", 45, 5)]
    b = B.bilan_evenement(200, 180, 171, 9, 3, 40, 38, 5000, 4200)
    assert b["taux_finishers"] == 95 and b["taux_abandon"] == 5 and b["solde"] == 800 and b["benevoles"] == "38/40"
    assert B.nom_de_base("Trail des Dentelles 2027") == B.nom_de_base("trail des dentelles") == "trail des dentelles"


def test_prevu_reel_et_correction(base_vide):
    from noyau.course import roadbook as rbk, strategie as strat
    from noyau.donnees import analyse as dan, base
    trace = [[44.0 + i * 0.001, 5.0, 300 + (i % 10) * 5] for i in range(200)]
    rbk.enregistrer(1, {"nom": "Trail des Dentelles", "date_course": "2026-10-12", "mode_niveau": "temps",
                        "temps_vise": "3:00", "trace": trace, "distance_km": 22, "denivele_m": 900})
    rbk.enregistrer(1, {"nom": "Ventoux", "date_course": "2026-06-01", "mode_niveau": "allure", "allure_plat": "6:00",
                        "trace": trace})
    rbk.enregistrer(1, {"nom": "Autre", "date_course": "2026-04-01", "mode_niveau": "temps", "temps_vise": "2:00"})
    prevu_v = dan._prevision(2)["prevu_s"]
    assert dan._prevision(1)["prevu_s"] == 3 * 3600                    # « 3:00 » = 3 h dans le roadbook
    base.inserer("resultats_courses", {"athlete_id": 1, "nom_course": "Dentelles 22 km", "date": "2026-10-12",
                                      "temps": "3:15:00"})
    base.inserer("resultats_courses", {"athlete_id": 1, "nom_course": "Ventoux", "date": "2026-06-01",
                                      "temps": B.texte_duree(prevu_v * 1.05)})
    lignes, syn = dan.prevu_reel(1)
    assert len(lignes) == 2 and lignes[0]["methode"] == "temps" and lignes[1]["methode"] == "allure"
    assert syn["facteur"] == pytest.approx((3.25 / 3 + 1.05) / 2, abs=0.002) and syn["applique"] is None
    assert strat.facteur_correction(1) == 1.0
    dan.appliquer_correction(1, syn["facteur"])
    assert strat.facteur_correction(1) == pytest.approx(syn["facteur"]) and dan.facteur_applique(1) == pytest.approx(syn["facteur"])
    with pytest.raises(ValueError):
        dan.appliquer_correction(1, 2)
    dan.appliquer_correction(1, None)
    assert strat.facteur_correction(1) == 1.0 and dan.facteur_applique(1) is None


def test_bilans_club(base_vide):
    from noyau.donnees import analyse as dan, club as dclub, agenda_club as dag, profils as dpro
    from noyau.club import imports as imp
    cid = dclub.enregistrer_club({"nom": "Ventoux Trail Athlé"})
    dclub.importer(cid, "2025-2026", imp.analyser(imp.lire_tableau(
        "Nom;Prénom;Date de naissance;Sexe\nFAURE;Léa;30/06/2016;F\nMARTIN;Lucas;12/03/1985;M\nROUX;Paul;01/01/1980;M\n"))["lignes"])
    dclub.renouveler(cid, "2025-2026", "2026-2027")
    a26 = {a["nom"]: a for a in dclub.adhesions(cid, "2026-2027")}
    dclub.supprimer_adhesion(a26["ROUX"]["id"])
    dclub.importer(cid, "2026-2027", imp.analyser(imp.lire_tableau(
        "Nom;Prénom;Date de naissance;Sexe\nBLANC;Julie;05/05/1990;F\n"))["lignes"])
    adh = {a["nom"]: a["personne_id"] for a in dclub.adhesions(cid, "2026-2027")}
    s = dag.enregistrer_seance(cid, {"titre": "Côtes", "date": "2026-10-06"})
    dag.enregistrer_appel(s, {adh["FAURE"]: "present", adh["MARTIN"]: "retard", adh["BLANC"]: "absent"})
    dag.enregistrer_seance(cid, {"titre": "Sans appel", "date": "2026-10-08"})
    dpro.enregistrer_resultat(adh["MARTIN"], {"date": "2026-10-12", "course": "Dentelles", "distance_km": 22,
                                              "denivele_m": 900, "temps_s": 9000, "classement_categorie": 2})
    lignes, evo = dan.bilans_club(cid)
    assert [l["saison"] for l in lignes] == ["2025-2026", "2026-2027"]
    l = lignes[-1]
    assert (l["adherents"], l["nouveaux"], l["renouveles"], l["partis"], l["fidelisation"]) == (3, 1, 2, 1, 67)
    assert (l["femmes"], l["hommes"], l["jeunes"]) == (2, 1, 1)
    assert (l["seances"], l["presence_moyenne"]) == (1, 2.0)          # la séance sans appel ne compte pas
    assert (l["resultats"], l["podiums"], l["km_course"], l["courses"]) == (1, 1, 22, 1)
    assert evo["adherents"][-1] == ("2026-2027", 3, 0)


def test_bilans_evenements(base_vide):
    from noyau.donnees import analyse as dan, organisation as dor, chrono as dch, commandement as dcm
    eps = {}
    for an in (2025, 2026):
        ev = dor.enregistrer_evenement({"nom": f"Trail des Dentelles {an}", "date_debut": f"{an}-10-12"})
        e = dor.enregistrer_epreuve(ev, {"nom": "22 km", "distance_km": 22, "tarif": 20, "dossard_debut": 1, "dossard_fin": 300})
        eps[an] = (ev, e)
    ev, e = eps[2026]
    ids = [dor.enregistrer_inscription({"epreuve_id": e, "nom": f"COUREUR{k}", "prenom": "A", "sexe": "M",
                                        "date_naissance": "1980-01-01", "statut": "validee", "montant": 20})
           for k in range(4)]
    dor.attribuer_dossards(ev)
    doss = {i["id"]: i["dossard"] for i in dor.inscriptions(ev)}
    dch.donner_depart(e, "2026-10-12T08:00:00")
    dch.ajouter_passage(ev, doss[ids[0]], "2026-10-12T10:30:00")
    dch.ajouter_passage(ev, doss[ids[1]], "2026-10-12T10:45:00")
    dch.definir_statut([ids[2]], "abandon")
    dch.definir_statut([ids[3]], "non_partant")
    dcm.signaler(ev, {"type": "blessure", "gravite": "urgent", "description": "cheville"})
    dor.enregistrer_inscription({"epreuve_id": eps[2025][1], "nom": "ANCIEN", "prenom": "B", "sexe": "F",
                                 "date_naissance": "1980-01-01", "statut": "validee", "montant": 20})
    lignes, comp = dan.bilans_evenements()
    assert [l["nom"] for l in lignes] == ["Trail des Dentelles 2026", "Trail des Dentelles 2025"]
    b = lignes[0]
    assert (b["inscrits"], b["partants"], b["arrives"], b["abandons"], b["incidents"], b["graves"]) == (4, 3, 2, 1, 1, 1)
    assert b["taux_finishers"] == 67
    assert list(comp) == ["trail des dentelles"] and [x["date"][:4] for x in comp["trail des dentelles"]] == ["2025", "2026"]
    t = dan.tableau(athlete_id=1)
    assert t["prevu_reel"]["courses"] == 0 and len(t["evenements"]) == 2


def test_fenetre(base_vide):
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    from interface.analyse import AnalyseFenetre, html_bilans_club, html_bilans_evenements
    f = AnalyseFenetre(athlete_id_initial=1)
    assert f.tabs.count() == 3
    for ec in f.ecrans:
        ec.rafraichir()
    assert "Bilans du club" in html_bilans_club("Club", []) and "0 événement" in html_bilans_evenements([], {})
