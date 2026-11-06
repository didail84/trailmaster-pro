"""Étape 4.1 : Espace Club — adhérents, licences FFA, cotisations, groupes, import."""
import pytest

from noyau.club import adhesions as regles, categories as cat, imports as imp


# ----------------------------------------------------------------- saisons et catégories

def test_saisons():
    assert cat.saison_de("2026-08-31") == "2025-2026"
    assert cat.saison_de("2026-09-01") == "2026-2027"
    assert cat.saison_precedente("2026-2027") == "2025-2026"
    assert cat.saison_suivante("2025-2026") == "2026-2027"
    debut, fin = cat.bornes_saison("2025-2026")
    assert (debut.isoformat(), fin.isoformat()) == ("2025-09-01", "2026-08-31")


@pytest.mark.parametrize("code, annees", [
    # tableau des catégories FFA 2025-2026 (années de naissance)
    ("EA", (2017, 2019)), ("PO", (2015, 2016)), ("BE", (2013, 2014)), ("MI", (2011, 2012)),
    ("CA", (2009, 2010)), ("JU", (2007, 2008)), ("ES", (2004, 2006)), ("SE", (1992, 2003)),
    ("M0", (1987, 1991)), ("M1", (1982, 1986)), ("M5", (1962, 1966)), ("M10", (None, 1941)),
])
def test_categories_2025_2026(code, annees):
    assert cat.annees_de_la_categorie(code, "2025-2026") == annees
    premiere, derniere = annees
    for an in (premiere, derniere):
        if an:
            assert cat.categorie(f"{an}-06-15", "2025-2026")["code"] == code


def test_categorie_change_avec_la_saison_pas_avec_l_anniversaire():
    # né en décembre : même catégorie toute la saison, qu'il ait eu son anniversaire ou non
    assert cat.categorie("2010-12-31", "2025-2026")["code"] == "CA"
    assert cat.categorie("2010-01-01", "2025-2026")["code"] == "CA"
    assert cat.categorie("2010-12-31", "2026-2027")["code"] == "CA"
    assert cat.categorie("2008-05-01", "2026-2027")["code"] == "JU"
    assert cat.categorie(None) is None


def test_licence_selon_l_age():
    assert cat.licence_possible("decouverte", "2016-03-01", "2025-2026") is None       # poussin
    assert "Benjamins" in cat.licence_possible("decouverte", "2013-03-01", "2025-2026")
    assert cat.licence_possible("running", "2012-03-01", "2025-2026")                   # minime : non
    assert cat.licence_possible("competition", "1984-03-01", "2025-2026") is None
    assert cat.licence_possible("adherent", "2016-03-01", "2025-2026") is None


# ----------------------------------------------------------------- dossier et chiffres

def _adh(**k):
    a = {"personne_id": 1, "type_licence": "competition", "numero_licence": "123", "sante_type": "questionnaire",
         "cotisation": 95, "montant_paye": 95, "date_naissance": "1984-03-01", "mineur": False, "statut": "validee",
         "saison": "2025-2026", "sexe": "H"}
    a.update(k)
    return a


def test_dossier():
    assert regles.dossier(_adh())["complet"]
    d = regles.dossier(_adh(numero_licence="", sante_type=None, montant_paye=40))
    assert d["manques"] == ["numéro de licence FFA", "pièce de santé (certificat ou questionnaire)",
                            "cotisation : reste 55 €"]
    # adhérent sans licence : pas de numéro demandé
    assert regles.dossier(_adh(type_licence="adherent", numero_licence=""))["complet"]
    mineur = regles.dossier(_adh(date_naissance="2014-05-01", mineur=True, autorisation_parentale=0))
    assert "autorisation parentale" in mineur["manques"]
    assert any("Benjamins" not in x for x in mineur["avertissements"])
    assert "droit à l'image non renseigné" in mineur["avertissements"]
    assert regles.dossier(_adh(statut="annulee", numero_licence=""))["complet"]


def test_chiffres_et_renouvellements():
    avant = [_adh(personne_id=i) for i in (1, 2, 3, 4)]
    maintenant = [_adh(personne_id=1), _adh(personne_id=2, sexe="F", montant_paye=0), _adh(personne_id=9),
                  _adh(personne_id=7, statut="annulee")]
    ch = regles.chiffres(maintenant, avant, "2025-2026")
    assert ch["effectif"] == 3 and ch["annulees"] == 1
    assert ch["renouveles"] == 2 and ch["nouveaux"] == 1 and ch["non_renouveles"] == [3, 4]
    assert ch["taux_renouvellement"] == 50
    assert ch["cotisations_dues"] == 285 and ch["cotisations_payees"] == 190 and ch["reste"] == 95
    assert ch["sexes"] == {"H": 2, "F": 1}
    al = regles.alertes(maintenant, ch, "2025-2026")
    assert any("95 €" in x for x in al) and any("2 adhérents" in x for x in al)


def test_tarif_pour():
    tarifs = [{"libelle": "Adulte", "type_licence": None, "montant": 90},
              {"libelle": "Jeune", "type_licence": "decouverte", "montant": 70}]
    assert regles.tarif_pour(tarifs, "decouverte")["libelle"] == "Jeune"
    assert regles.tarif_pour(tarifs, "running")["libelle"] == "Adulte"


# ----------------------------------------------------------------- lecture des fichiers

HELLOASSO = """Référence commande;Date de la commande;Statut de la commande;Nom adhérent;Prénom adhérent;Formule;Montant tarif;Email payeur;Date de naissance;Sexe;Numéro de licence FFA (si renouvellement);Moyen de paiement
1001;02/09/2025 18:22;Validé;Martin;Lucas;Licence compétition adulte;95,00 €;lucas@ex.fr;12/03/1985;Homme;1234567;Carte bancaire
1002;03/09/2025 09:10;Validé;Durand;Emma;Licence découverte (poussins);70,00 €;famille@ex.fr;05/07/2016;Femme;;Carte bancaire
1003;04/09/2025 10:00;Remboursé;Roux;Chloé;Licence running;75,00 €;chloe@ex.fr;22/11/1978;Femme;;Carte bancaire
1004;05/09/2025 11:00;Validé;Blanc;Hugo;Licence compétition;95,00 €;hugo@ex.fr;31/02/2009;M;;Carte bancaire
"""


def test_lecture_helloasso():
    lignes = imp.lire_tableau(HELLOASSO.encode("cp1252"))
    a = imp.analyser(lignes)
    assert [l["personne"]["nom"] for l in a["lignes"]] == ["Martin", "Durand", "Blanc"]     # remboursé écarté
    m = a["lignes"][0]
    assert m["personne"]["date_naissance"] == "1985-03-12" and m["personne"]["sexe"] == "H"
    assert m["adhesion"]["type_licence"] == "competition" and m["adhesion"]["numero_licence"] == "1234567"
    assert m["adhesion"]["cotisation"] == 95 and m["adhesion"]["montant_paye"] == 95
    assert m["adhesion"]["paiement_date"] == "2025-09-02"
    assert a["lignes"][1]["adhesion"]["type_licence"] == "decouverte"
    assert a["lignes"][2]["erreurs"] and a["lignes"][2]["personne"]["date_naissance"] is None
    assert a["colonnes"]["numero_licence"].startswith("Numéro de licence FFA")
    assert "Référence commande" in a["non_reconnues"]


def test_lecture_csv_virgules_et_entete_decale():
    texte = "Export SI-FFA\n\nNom,Prénom,Né(e) le,N° Licence,Type licence\nGIRAUD,Paul,14/02/1960,4567890,Athlé Running\n"
    a = imp.analyser(imp.lire_tableau(texte))
    assert len(a["lignes"]) == 1
    p = a["lignes"][0]
    assert p["personne"]["date_naissance"] == "1960-02-14"
    assert p["adhesion"]["type_licence"] == "running" and p["adhesion"]["montant_paye"] == 0


# ----------------------------------------------------------------- base de données

def test_club_import_renouvellement_recus(base_vide):
    from noyau.donnees import club as dclub, personnes as dper
    cid = dclub.club_id_ou_creer()
    assert dclub.club_id_ou_creer() == cid
    dclub.enregistrer_club({"nom": "Ventoux Trail Athlé", "ville": "Carpentras"}, cid)
    assert dclub.club_principal()["nom"] == "Ventoux Trail Athlé"
    lignes = imp.analyser(imp.lire_tableau(HELLOASSO.encode()))["lignes"]
    r = dclub.importer(cid, "2025-2026", lignes, "helloasso")
    assert r["crees"] == 3 and r["adhesions"] == 3
    # réimporter le même fichier : aucun doublon
    r2 = dclub.importer(cid, "2025-2026", lignes, "helloasso")
    assert r2["crees"] == 0 and r2["adhesions"] == 0 and r2["deja"] == 3
    assert len(dper.lister()) == 4                              # + le coureur de la base de test
    adh = dclub.adhesions(cid, "2025-2026")
    martin = next(a for a in adh if a["nom"] == "Martin")
    assert "licencie" in dper.fiche(martin["personne_id"])["roles"]
    assert martin["recu_numero"] == "2025-26-0001"                 # payé à l'import : reçu attribué
    assert martin["categorie"]["code"] == "M1"
    durand = next(a for a in adh if a["nom"] == "Durand")
    assert durand["mineur"] and "autorisation parentale" in durand["dossier"]["manques"]
    # tarifs, renouvellement, paiement en deux fois
    dclub.enregistrer_tarif(cid, "2026-2027", "Adulte", 100, "competition")
    dclub.enregistrer_tarif(cid, "2026-2027", "Jeune", 75, "decouverte")
    with pytest.raises(dclub.ErreurClub):
        dclub.enregistrer_tarif(cid, "2026-2027", "Jeune", 80)
    assert dclub.copier_tarifs(cid, "2026-2027", "2027-2028") == 2
    assert dclub.renouveler(cid, "2025-2026", "2026-2027", {martin["personne_id"], durand["personne_id"]}) == 2
    assert dclub.renouveler(cid, "2025-2026", "2026-2027") == 1                    # Blanc seulement
    nouv = {a["nom"]: a for a in dclub.adhesions(cid, "2026-2027")}
    assert nouv["Martin"]["cotisation"] == 100 and nouv["Martin"]["numero_licence"] == "1234567"
    assert nouv["Durand"]["tarif"] == "Jeune" and nouv["Durand"]["montant_paye"] == 0
    assert dclub.enregistrer_paiement(nouv["Martin"]["id"], 60, "Chèque") is None
    assert dclub.enregistrer_paiement(nouv["Martin"]["id"], 40, "Chèque") == "2026-27-0001"
    assert dclub.adhesion(nouv["Martin"]["id"])["reste"] == 0
    with pytest.raises(dclub.ErreurClub):
        dclub.enregistrer_paiement(nouv["Martin"]["id"], 0)
    assert dclub.saisons(cid)[:2] == ["2026-2027", "2025-2026"]
    # une adhésion par personne et par saison
    with pytest.raises(dclub.ErreurClub):
        dclub.enregistrer_adhesion(cid, martin["personne_id"], "2026-2027", {"type_licence": "running"})
    # groupes
    g = dclub.enregistrer_groupe(cid, {"nom": "Adultes trail"})
    with pytest.raises(dclub.ErreurClub):
        dclub.enregistrer_groupe(cid, {"nom": " "})
    dclub.definir_groupes(martin["personne_id"], [g], cid)
    assert dclub.membres_du_groupe(g) == [martin["personne_id"]]
    assert len(dclub.adhesions(cid, "2026-2027", g)) == 1
    assert nouv["Martin"]["groupes"] is None and dclub.adhesion(nouv["Martin"]["id"])["groupes"] == "Adultes trail"
    # export tableur
    csv = dclub.export_csv(dclub.adhesions(cid, "2026-2027"))
    assert csv.lstrip("\ufeff").startswith("Nom;Prénom") and "Martin;Lucas" in csv
    # retirer une adhésion garde la personne
    dclub.supprimer_adhesion(nouv["Blanc"]["id"])
    assert len(dclub.adhesions(cid, "2026-2027")) == 2 and len(dper.lister()) == 4


def test_ecrans(base_vide, tmp_path):
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    from noyau.donnees import club as dclub
    cid = dclub.club_id_ou_creer()
    saison = cat.saison_de()
    dclub.enregistrer_club({"nom": "VTA"}, cid)
    fichier = tmp_path / "export_helloasso.csv"
    fichier.write_text(HELLOASSO, encoding="utf-8")
    from interface.club import ClubFenetre, DialogueAdherent
    f = ClubFenetre(1)
    assert f.tabs.count() == 8
    f.import_.charger(str(fichier))
    assert f.import_.table.rowCount() == 3 and f.import_.b_importer.isEnabled()
    r = dclub.importer(cid, saison, f.import_._analyse["lignes"])
    assert r["adhesions"] == 3
    f.adherents.actualiser()
    assert f.adherents.table.rowCount() == 3
    f.adherents.f_etat.setCurrentIndex(3)                      # moins de 18 ans
    assert f.adherents.table.rowCount() == 1                    # Emma (Hugo : date illisible)
    f.adherents.f_etat.setCurrentIndex(0)
    f.adherents.recherche.setText("lucas")
    assert f.adherents.table.rowCount() == 1
    f.tableau.actualiser()
    assert f.tableau.cartes["effectif"].valeur.text() == "3"
    a = dclub.adhesions(cid, saison)[0]
    d = DialogueAdherent(f, cid, saison, a)
    assert d.nom.text() == a["nom"] and "manque" in d.label_dossier.text().lower() or "complet" in d.label_dossier.text()
    d.close()
    from interface.club_pdf import html_recu, rendre_recu
    m = next(x for x in dclub.adhesions(cid, saison) if x["recu_numero"])
    assert "Reçu n°" in html_recu(dclub.club_principal(), m)
    pdf = tmp_path / "recu.pdf"
    rendre_recu(pdf, dclub.club_principal(), m)
    assert pdf.read_bytes()[:4] == b"%PDF"
    f.close()
