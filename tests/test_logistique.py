"""Étape 4.6 : démarches et rétroplanning, bénévoles, ravitaillements, matériel, partenaires et budget."""
from datetime import date, timedelta

import pytest

from noyau.organisation import logistique as L


def test_demarches_selon_le_contexte():
    c = L.contexte({"voie_publique": True, "communes": 3, "natura2000": True, "buvette": True, "carrefours": 6},
                   {"code_postal": "84190"}, [{"quota": 300}, {"quota": 150}])
    assert c["departement"] == "84" and c["participants"] == 450
    ds = {d["code"]: d for d in L.demarches_pour("2027-07-11", c)}
    assert ds["declaration"]["autorite"] == "Préfet du département" and ds["declaration"]["echeance"] == "2027-05-12"
    assert "natura2000" in ds and "arretes" in ds and "signaleurs" in ds and "buvette" in ds
    assert "feux_repli" in ds and "risque-prevention-incendie.fr/vaucluse" in ds["feux_veille"]["pieces"]
    assert "onf" not in ds and "tombola" not in ds and "declaration_rando" not in ds
    assert ds["debalisage"]["echeance"] == "2027-07-12"
    # hors voie publique, une commune, en hiver : ni déclaration Cerfa, ni feux de forêt
    c2 = L.contexte({"terrains_prives": True, "foret_publique": True}, {"code_postal": "84000"}, [])
    ds2 = {d["code"] for d in L.demarches_pour("2027-01-10", c2)}
    assert "declaration" not in ds2 and "feux_repli" not in ds2 and {"onf", "proprietaires", "mairies"} <= ds2
    # plusieurs départements : 3 mois
    ds3 = {d["code"]: d for d in L.demarches_pour("2027-07-11", L.contexte({"voie_publique": True, "departements": 2}))}
    assert ds3["declaration"]["jours"] == 90 and "chaque département" in ds3["declaration"]["autorite"]
    assert L.jalon("2027-05-12", "2027-07-11") == "J-60" and L.jalon("2027-07-12", "2027-07-11") == "J+1"
    auj = date(2027, 5, 20)
    assert L.etat_demarche({"echeance": "2027-05-12", "statut": "a_faire"}, auj) == "en retard"
    assert L.etat_demarche({"echeance": "2027-05-30", "statut": "a_faire"}, auj) == "bientôt"
    assert L.etat_demarche({"echeance": "2027-05-12", "statut": "accorde"}, auj) == "faite"


def test_secours_ravitos_budget():
    assert L.dps(0)["dispositif"] == "aucun"
    assert L.dps(800)["dispositif"] == "PAPS" and L.dps(800)["intervenants"] == 2
    d = L.dps(3000)
    assert d["indice"] == 1.05 and d["ris"] == 3.15 and d["dispositif"] == "DPS-PE" and d["intervenants"] == 4
    assert L.dps(20000)["dispositif"] == "DPS-ME" and L.dps(20000)["intervenants"] % 2 == 0
    q = dict((p, n) for p, n, _u in L.quantites_ravito("complet", 300, 22, ete=True))
    assert q["Eau plate"] == 259 and q["Bananes"] == 150 and q["Gobelets"] == 0 and "Fromage, saucisson" in q
    assert dict((p, n) for p, n, _u in L.quantites_ravito("eau", 100, 5, gobelets=True))["Gobelets"] == 173
    assert L.quantites_ravito("eau", 0) == []
    assert L.avantage_fiscal(1000)["reduction"] == 600 and L.avantage_fiscal(1000, True)["reduction"] == 660
    assert L.controle_contreparties(1000, 200) is None and "parrainage" in L.controle_contreparties(1000, 400)
    assert L.seuil_rentabilite(6000, 8, 25, 1500) == 265 and L.seuil_rentabilite(100, 0, 20, 500) == 0
    assert L.seuil_rentabilite(1000, 30, 25) is None
    b = L.bilan_budget([{"sens": "depense", "categorie": "Secours et médecin", "libelle": "Croix-Rouge", "prevu": 800},
                        {"sens": "depense", "categorie": "Cadeaux coureurs (t-shirts…)", "libelle": "T-shirts", "prevu": 6,
                         "par_coureur": 1, "realise": 1200},
                        {"sens": "recette", "categorie": "Buvette et restauration", "libelle": "Buvette", "prevu": 400}],
                       3000, [{"nom": "Banque", "type": "parrainage", "statut": "accord", "montant": 500},
                              {"nom": "Refus", "type": "mecenat", "statut": "refus", "montant": 900}], 200)
    assert b["depenses_prevues"] == 2000 and b["recettes_prevues"] == 3900 and b["solde_prevu"] == 1900
    assert b["fixe"] == 800 and b["variable_par_coureur"] == 6 and b["autres_recettes"] == 900


def test_benevoles_controle():
    postes = [{"id": 1, "nom": "Carrefour D938", "type": "signaleur", "besoin": 2, "jour": "2027-04-11",
               "heure_debut": "08:00", "heure_fin": "11:00"},
              {"id": 2, "nom": "Ravito km 12", "type": "ravitaillement", "besoin": 3, "jour": "2027-04-11",
               "heure_debut": "10:00", "heure_fin": "13:00"}]
    bvs = [{"id": 1, "nom": "A", "date_naissance": "2011-01-01", "permis": 0},
           {"id": 2, "nom": "B", "date_naissance": "1980-01-01", "permis": 0},
           {"id": 3, "nom": "C", "date_naissance": "1975-01-01", "permis": 1}]
    c = L.controle_benevoles(postes, bvs, [(1, 1), (1, 2), (2, 2)], "2027-04-11", voie_publique=True)
    assert c["besoin"] == 5 and c["pourvus"] == 3 and c["manques"] == [{"poste": "Ravito km 12", "poste_id": 2, "manque": 2}]
    assert len(c["conflits"]) == 1 and "B" in c["conflits"][0]
    assert any("mineur" in a for a in c["alertes"]) and any("sans permis" in a for a in c["alertes"])
    assert [b["id"] for b in c["sans_poste"]] == [3]
    ps = L.postes_suggeres([{"nom": "Trail 25", "distance_km": 25, "denivele_m": 1200, "heure_depart": "08:30"}],
                           [{"id": 7, "nom": "Col", "km": 12, "coureurs": 300}], {"carrefours": 4, "buvette": True}, 300)
    noms = [p["nom"] for p in ps]
    assert "Ravitaillement Col" in noms and "Signaleurs" in noms and "Buvette" in noms and "Balisage (veille)" in noms
    assert next(p for p in ps if p["type"] == "ravitaillement")["besoin"] == 4


def test_courriers():
    ev = {"nom": "Trail des Dentelles", "date_debut": "2027-04-11", "commune": "Gigondas"}
    eps = [{"nom": "Trail 25 km", "distance_km": 25, "denivele_m": 1200, "heure_depart": "08:30"}]
    for code, _l in L.COURRIERS:
        objet, texte = L.courrier(code, ev, eps, {"nom": "Ventoux Trail Athlé", "ville": "Carpentras"}, {"nom": "Mairie"})
        assert "Trail des Dentelles" in objet and "dimanche 11 avril 2027" in texte and "Ventoux Trail Athlé" in texte
    assert "coupon" in L.courrier("proprietaire", ev, eps)[1].lower() or "Signature" in L.courrier("proprietaire", ev, eps)[1]


def _evenement():
    from noyau.donnees import organisation as dor
    ev = dor.enregistrer_evenement({"nom": "Trail des Dentelles", "date_debut": (date.today() + timedelta(days=50)).isoformat(),
                                    "commune": "Gigondas", "code_postal": "84190"})
    e1 = dor.enregistrer_epreuve(ev, {"nom": "Trail 25 km", "discipline": "trail", "distance_km": 25, "denivele_m": 1200,
                                      "heure_depart": "08:30", "quota": 300, "tarif": 28})
    e2 = dor.enregistrer_epreuve(ev, {"nom": "Trail 12 km", "discipline": "trail", "distance_km": 12, "denivele_m": 450,
                                      "heure_depart": "09:30", "quota": 200, "tarif": 15})
    for nom, ep, m in (("Roux", e1, 28), ("Blanc", e1, 28), ("Faure", e2, 15)):
        dor.enregistrer_inscription({"epreuve_id": ep, "nom": nom, "prenom": "X", "sexe": "F", "montant": m, "montant_paye": m})
    return ev, e1, e2


def test_base(base_vide):
    from noyau.donnees import logistique as dl, personnes as dper
    ev, e1, e2 = _evenement()
    c = dl.enregistrer_contexte(ev, {"voie_publique": True, "communes": 2, "carrefours": 3, "spectateurs": 500,
                                     "buvette": True, "terrains_prives": True})
    assert c["participants"] == 500 and c["departement"] == "84"
    r = dl.generer_demarches(ev)
    assert r["ajoutees"] > 20 and dl.generer_demarches(ev) == {"ajoutees": 0, "mises_a_jour": 0, "retirees": 0}
    ds = {d["code"]: d for d in dl.demarches(ev)}
    assert ds["declaration"]["etat"] == "en retard" and ds["declaration"]["jalon"] == "J-60"
    dl.changer_statut_demarches([ds["declaration"]["id"]], "envoye")
    dl.enregistrer_demarche(ev, {"notes": "dossier déposé"}, ds["proprietaires"]["id"])
    m = dl.enregistrer_demarche(ev, {"titre": "Réserver la salle des fêtes", "echeance": "2027-01-01"})
    # sans voie publique ni terrains privés : la déclaration (suivie) passe sans objet, les autres sont retirées
    dl.enregistrer_contexte(ev, {"voie_publique": False, "terrains_prives": False})
    r = dl.generer_demarches(ev)
    ds = {d["code"]: d for d in dl.demarches(ev)}
    assert ds["declaration"]["statut"] == "sans_objet" and ds["proprietaires"]["statut"] == "sans_objet"
    assert "arretes" not in ds and any(d["id"] == m for d in ds.values())
    dl.supprimer_demarche(m)
    assert not any(d["id"] == m for d in dl.demarches(ev))
    with pytest.raises(dl.ErreurLogistique):
        dl.enregistrer_demarche(ev, {"titre": " "})
    # bénévoles : club et import sans doublon
    pid = dper.creer({"nom": "Martin", "prenom": "Lucas", "date_naissance": "1985-03-12", "telephone": "0600000000"}, ["licencie"])
    assert dl.ajouter_personnes(ev, [pid]) == 1 and dl.ajouter_personnes(ev, [pid]) == 0
    assert "benevole" in dper.roles(pid)
    imp = ("Nom;Prénom;Téléphone;Permis;Date de naissance;Taille\nROUX;Chloé;0611;oui;22/11/1978;M\n"
           "DURAND;Emma;0622;non;01/05/2010;S\nMartin;Lucas;;;;\n")
    assert dl.importer_benevoles(ev, imp) == {"ajoutes": 2, "deja": 1, "ignores": 0}
    assert dl.importer_benevoles(ev, imp)["deja"] == 3
    bv = {b["nom"]: b for b in dl.benevoles(ev)}
    assert bv["ROUX"]["permis"] == 1 and bv["DURAND"]["date_naissance"] == "2010-05-01"
    # ravitaillements, postes suggérés, affectations
    r1 = dl.enregistrer_ravitaillement(ev, {"nom": "Col du Cayron", "km": 12.5, "type": "complet", "epreuve_ids": [e1]})
    dl.enregistrer_ravitaillement(ev, {"nom": "Arrivée", "km": 25, "type": "arrivee"})
    rv = dl.ravitaillements(ev)
    assert rv[0]["coureurs"] == 300 and rv[1]["coureurs"] == 500 and rv[0]["epreuves"] == ["Trail 25 km"]
    assert any(p == "Bananes" for p, _q, _u in rv[0]["quantites"]) and "Eau plate" in dl.liste_de_courses(ev)
    n = dl.creer_postes_suggeres(ev)
    assert n >= 8 and dl.creer_postes_suggeres(ev) == 0
    ps = {p["nom"]: p for p in dl.postes(ev)}
    assert ps["Ravitaillement Col du Cayron"]["ravitaillement_id"] == r1 and ps["Balisage (veille)"]["jour"] < ps["Chrono"]["jour"]
    sig = ps["Signaleurs"]["id"]
    assert dl.affecter(sig, bv["DURAND"]["id"]) and not dl.affecter(sig, bv["DURAND"]["id"])
    dl.affecter(sig, bv["ROUX"]["id"])
    dl.affecter(ps["Ravitaillement Col du Cayron"]["id"], bv["ROUX"]["id"])
    ctl = dl.controle(ev)
    assert any("DURAND" in a and "mineur" in a for a in ctl["alertes"])
    assert [s["nom"] for s in dl.signaleurs(ev)] == ["DURAND", "ROUX"]
    assert dl.ravitaillements(ev)[0]["benevoles"] == 1
    assert len(dl.planning_benevole(ev, bv["ROUX"]["id"])) == 2
    with pytest.raises(dl.ErreurLogistique):
        dl.enregistrer_poste(ev, {"nom": "x", "heure_debut": "25:00"})
    # matériel
    assert dl.ajouter_materiel_suggere(ev) > 15 and dl.ajouter_materiel_suggere(ev) == 0
    ms = {m["article"]: m for m in dl.materiel(ev)}
    assert ms["Jerricans d'eau 20 L"]["quantite"] >= 1
    dl.enregistrer_materiel(ev, {"disponible": 1, "fournisseur": "Mairie de Gigondas", "cout": 0}, ms["Arche départ et arrivée"]["id"])
    dl.changer_statut_materiel([ms["Arche départ et arrivée"]["id"]], "reserve")
    bm = dl.bilan_materiel(ev)
    assert bm["a_rendre"] == 1 and bm["manquants"] == bm["articles"] - 1
    # partenaires : reçu fiscal une seule fois, pas pour un parrainage
    p1 = dl.enregistrer_partenaire(ev, {"nom": "Cave de Gigondas", "type": "mecenat", "montant": 1000, "statut": "verse",
                                        "date_versement": "2027-02-01"})
    p2 = dl.enregistrer_partenaire(ev, {"nom": "Sport 2000", "type": "parrainage", "montant": 500, "statut": "accord"})
    assert dl.emettre_recu(p1)["recu_numero"] == "DON-2027-0001" and dl.emettre_recu(p1)["recu_numero"] == "DON-2027-0001"
    with pytest.raises(dl.ErreurLogistique):
        dl.emettre_recu(p2)
    # budget : inscriptions et partenaires repris tout seuls
    dl.enregistrer_ligne_budget(ev, {"sens": "depense", "categorie": "Secours et médecin", "libelle": "Croix-Rouge", "prevu": 900})
    dl.enregistrer_ligne_budget(ev, {"sens": "depense", "categorie": "Cadeaux coureurs (t-shirts…)", "libelle": "T-shirts",
                                     "prevu": 5, "par_coureur": True})
    with pytest.raises(dl.ErreurLogistique):
        dl.enregistrer_ligne_budget(ev, {"sens": "x", "libelle": "y"})
    b = dl.bilan(ev)
    assert b["attendus"] == 500 and b["recettes_prevues"] == 500 * 23.67 + 1500 and b["recettes_realisees"] == 71 + 1000
    assert b["depenses_prevues"] == 900 + 5 * 500 and b["tarif_moyen"] == 23.67
    t = dl.tableau(ev)
    assert t["benevoles"] == 3 and t["partenaires"]["accords"] == 2 and t["dps"]["dispositif"] == "PAPS"
    assert t["demarches"]["total"] == len(dl.demarches(ev))


def test_ecrans(base_vide, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QApplication, QMessageBox
    QApplication.instance() or QApplication([])
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: None))
    from noyau.donnees import logistique as dl
    ev, e1, e2 = _evenement()
    dl.enregistrer_contexte(ev, {"voie_publique": True, "carrefours": 2, "spectateurs": 400})
    from interface.organisation import OrganisationFenetre
    from interface.organisation_logistique import DialogueChamps, texte_ics
    f = OrganisationFenetre(1)
    assert f.tabs.count() == 13
    d = f.demarches
    d.rafraichir()
    assert d.table.rowCount() > 15 and d.cartes["dps"].valeur.text() == "PAPS"
    d.q["natura2000"].setChecked(True)
    d._enregistrer_contexte()
    assert "1 démarche(s) ajoutée(s)" in d.info_ctx.text()
    from noyau.donnees import organisation as dor
    assert texte_ics(dor.evenement(ev), d._ds).count("BEGIN:VEVENT") == sum(1 for x in d._ds if x["statut"] not in L.FINIS)
    r = f.ravitaillements
    dl.enregistrer_ravitaillement(ev, {"nom": "Col", "km": 12, "type": "complet"})
    r.rafraichir()
    r.table.selectRow(0)
    assert r.table.rowCount() == 1 and r.table_q.rowCount() > 5 and r.table_total.rowCount() > 5
    b = f.benevoles
    b._postes_types()
    dl.enregistrer_benevole(ev, {"nom": "Roux", "prenom": "Chloé", "date_naissance": "1978-11-22", "permis": True})
    b.rafraichir()
    b.table_postes.selectRow(0)
    b.table.selectRow(0)
    b._affecter()
    assert "1 / " in b.cartes["pourvus"].valeur.text()
    m = f.materiel
    m._type()
    assert m.table.rowCount() > 15
    p = f.partenaires
    dl.enregistrer_partenaire(ev, {"nom": "Cave", "type": "mecenat", "montant": 1000, "statut": "verse",
                                   "contreparties": "banderole 400 €"})
    p.rafraichir()
    p.table.selectRow(0)
    assert "600" in p.detail.text() and "parrainage" in p.detail.text()
    assert p.table_budget.rowCount() == 2
    f.tableau.rafraichir()
    assert "Démarches" in f.tableau.logistique.text()
    # dialogue générique : erreur lisible, reste ouvert
    dlg = DialogueChamps(None, "x", [("texte", "titre", "Démarche", None)], {}, lambda c: dl.enregistrer_demarche(ev, c))
    dlg.accept()
    assert "intitulé" in dlg.message.text()
    # documents
    from interface import orga_pdf as P
    e = dor.evenement(ev)
    docs = [P.html_retroplanning(e, dl.demarches(ev)), P.html_planning_postes(e, dl.postes(ev)),
            P.html_convocations(e, dl.benevoles(ev), dl.postes(ev), "06 00"), P.html_signaleurs(e, dl.signaleurs(ev)),
            P.html_ravitaillements(e, dl.ravitaillements(ev), dl.liste_de_courses(ev)), P.html_materiel(e, dl.materiel(ev)),
            P.html_budget(e, dl.bilan(ev)), P.html_recu_don({"nom": "Club"}, dl.emettre_recu(dl.partenaires(ev)[0]["id"]), e),
            P.html_courrier("Bonjour\nMerci")]
    for i, h in enumerate(docs):
        chemin = tmp_path / f"doc{i}.pdf"
        P.rendre(chemin, "t", h, i in (0, 1))
        assert chemin.read_bytes()[:4] == b"%PDF"
    assert "DON-" in docs[7] and "Chloé" in docs[2]
    f.close()
