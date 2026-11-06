"""Chantier A : plusieurs associations et leurs sections, sans mélange."""
import pytest


def _deux_associations():
    from noyau.donnees import club as dclub
    from noyau.club import imports as imp
    a1 = dclub.enregistrer_club({"nom": "Ventoux Trail Athlé", "type_structure": "club_ffa", "affiliation": "FFA"})
    a2 = dclub.enregistrer_club({"nom": "Les Traileurs des Dentelles", "type_structure": "association_trail",
                                 "affiliation": "aucune"})
    tab = imp.lire_tableau("Nom;Prénom;Date de naissance;Numéro de licence;Formule\nMARTIN;Lucas;12/03/1985;111;competition\n"
                           "ROUX;Chloé;22/11/1978;222;running\n")
    dclub.importer(a1, "2026-2027", imp.analyser(tab)["lignes"])
    tab2 = imp.lire_tableau("Nom;Prénom;Date de naissance\nMARTIN;Lucas;12/03/1985\nFAURE;Léa;01/01/1990\n")
    dclub.importer(a2, "2026-2027", imp.analyser(tab2)["lignes"])
    return a1, a2


def test_associations_sans_melange(base_vide):
    from noyau.donnees import club as dclub, personnes as dper
    a1, a2 = _deux_associations()
    assert [c["nom"] for c in dclub.clubs()] == ["Ventoux Trail Athlé", "Les Traileurs des Dentelles"]
    assert dclub.club_courant_id() == a1 and dclub.club_principal()["affiliation"] == "FFA"
    n1 = {a["nom"] for a in dclub.adhesions(a1, "2026-2027")}
    n2 = {a["nom"] for a in dclub.adhesions(a2, "2026-2027")}
    assert n1 == {"MARTIN", "ROUX"} and n2 == {"MARTIN", "FAURE"}
    # Lucas Martin : une seule fiche, deux adhésions
    assert len([p for p in dper.lister() if p["nom"] == "MARTIN"]) == 1
    pid = next(a["personne_id"] for a in dclub.adhesions(a1, "2026-2027") if a["nom"] == "MARTIN")
    assert {a["club_id"] for a in dclub.adhesions_de_la_personne(pid)} == {a1, a2}
    # choisir l'association courante
    dclub.choisir_club(a2)
    assert dclub.club_principal()["nom"] == "Les Traileurs des Dentelles"
    with pytest.raises(dclub.ErreurClub):
        dclub.choisir_club(999)
    # reçus numérotés par association
    ad1 = next(a for a in dclub.adhesions(a1, "2026-2027") if a["nom"] == "MARTIN")
    ad2 = next(a for a in dclub.adhesions(a2, "2026-2027") if a["nom"] == "MARTIN")
    dclub.enregistrer_adhesion(a1, pid, "2026-2027", {"cotisation": 90}, ad1["id"])
    dclub.enregistrer_adhesion(a2, pid, "2026-2027", {"cotisation": 30}, ad2["id"])
    assert dclub.enregistrer_paiement(ad1["id"], 90) == "2026-27-0001"
    assert dclub.enregistrer_paiement(ad2["id"], 30) == "2026-27-0001"
    # groupes et tarifs propres à chaque association
    dclub.enregistrer_groupe(a1, {"nom": "Adultes"})
    dclub.enregistrer_groupe(a2, {"nom": "Adultes"})
    assert len(dclub.groupes(a1)) == 1 and len(dclub.groupes(a2)) == 1
    with pytest.raises(dclub.ErreurClub):
        dclub.supprimer_club(a2)
    vide = dclub.enregistrer_club({"nom": "Essai"})
    dclub.supprimer_club(vide)
    assert len(dclub.clubs()) == 2


def test_sections(base_vide):
    from noyau.donnees import club as dclub
    a1, a2 = _deux_associations()
    s_trail = dclub.enregistrer_section(a1, {"nom": "Trail", "discipline": "trail"})
    s_ecole = dclub.enregistrer_section(a1, {"nom": "École d'athlé"})
    with pytest.raises(dclub.ErreurClub):
        dclub.enregistrer_section(a1, {"nom": "trail"})
    assert [s["nom"] for s in dclub.sections(a1)] == ["École d'athlé", "Trail"] and dclub.sections(a2) == []
    roux = next(a for a in dclub.adhesions(a1, "2026-2027") if a["nom"] == "ROUX")
    dclub.enregistrer_adhesion(a1, roux["personne_id"], "2026-2027", {"section_id": s_trail}, roux["id"])
    assert [a["nom"] for a in dclub.adhesions(a1, "2026-2027", section_id=s_trail)] == ["ROUX"]
    assert dclub.adhesions(a1, "2026-2027", section_id=s_trail)[0]["section"] == "Trail"
    assert len(dclub.adhesions(a1, "2026-2027")) == 2
    g = dclub.enregistrer_groupe(a1, {"nom": "Trail du jeudi", "section_id": s_trail})
    dclub.enregistrer_groupe(a1, {"nom": "Poussins", "section_id": s_ecole})
    assert [x["nom"] for x in dclub.groupes(a1, section_id=s_trail)] == ["Trail du jeudi"]
    assert dclub.groupes(a1, section_id=s_trail)[0]["section"] == "Trail"
    dclub.enregistrer_tarif(a1, "2026-2027", "Adulte", 95)
    dclub.enregistrer_tarif(a1, "2026-2027", "Trail", 60, section_id=s_trail)
    assert [t["libelle"] for t in dclub.tarifs_de(a1, "2026-2027", s_trail)] == ["Trail", "Adulte"]
    assert [t["libelle"] for t in dclub.tarifs_de(a1, "2026-2027", s_ecole)] == ["Adulte"]
    # import dans une section : le tarif de la section s'applique
    from noyau.club import imports as imp
    dclub.importer(a1, "2026-2027", imp.analyser(imp.lire_tableau("Nom;Prénom\nBLANC;Hugo\n"))["lignes"], section_id=s_trail)
    blanc = next(a for a in dclub.adhesions(a1, "2026-2027") if a["nom"] == "BLANC")
    assert blanc["section_id"] == s_trail and blanc["cotisation"] == 60
    # renouvellement : la section suit
    assert dclub.renouveler(a1, "2026-2027", "2027-2028") == 3
    assert {a["nom"] for a in dclub.adhesions(a1, "2027-2028", section_id=s_trail)} == {"ROUX", "BLANC"}
    # section courante mémorisée par association
    dclub.choisir_section(a1, s_trail)
    assert dclub.section_courante(a1) == s_trail and dclub.section_courante(a2) is None
    dclub.choisir_section(a1, None)
    assert dclub.section_courante(a1) is None
    # supprimer la section : rien n'est perdu
    dclub.supprimer_section(s_trail)
    assert len(dclub.adhesions(a1, "2026-2027")) == 3 and dclub.groupes(a1, True)[-1]["section_id"] is None


def test_ecrans(base_vide):
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    from noyau.donnees import club as dclub
    a1, a2 = _deux_associations()
    s = dclub.enregistrer_section(a1, {"nom": "Trail"})
    roux = next(a for a in dclub.adhesions(a1, "2026-2027") if a["nom"] == "ROUX")
    dclub.enregistrer_adhesion(a1, roux["personne_id"], "2026-2027", {"section_id": s}, roux["id"])
    from interface.club import ClubFenetre
    f = ClubFenetre(1)
    ad = f.adherents
    ad.combo_saison.setCurrentIndex(max(0, ad.combo_saison.findData("2026-2027")))
    assert ad.combo_club.count() == 2 and ad.combo_section.count() == 2 and ad.table.rowCount() == 2
    ad.combo_section.setCurrentIndex(1)                       # section Trail
    assert ad.table.rowCount() == 1 and dclub.section_courante(a1) == s
    assert f.tableau.combo_section.currentData() == s          # tous les onglets suivent
    ad.combo_club.setCurrentIndex(1)                          # l'autre association
    assert dclub.club_courant_id() == a2 and not ad.combo_section.isVisibleTo(ad)
    textes = {ad.table.item(r, c).text() for r in range(ad.table.rowCount()) for c in range(ad.table.columnCount())
              if ad.table.item(r, c)}
    assert ad.table.rowCount() == 2 and any("FAURE" in t for t in textes) and not any("ROUX" in t for t in textes)
    f.reglages.actualiser()
    assert f.reglages.table_clubs.rowCount() == 2
    f.close()
