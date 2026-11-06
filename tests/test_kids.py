"""Chantier D : Kids (carnet de progression, badges, équipement, espace parents)."""
import re

import pytest

from noyau.club import kids as KI


def test_regles():
    assert KI.niveau_conseille("2018-05-01", "2026-2027") == "decouverte"       # 9 ans en 2027 : éveil athlé
    assert KI.niveau_conseille("2014-05-01", "2026-2027") == "montagnard"
    assert KI.est_kid("2012-01-01", "2026-2027") and not KI.est_kid("1985-01-01", "2026-2027")
    comp = [{"id": i, "niveau": n, "domaine": d} for i, (_c, n, d, _l) in enumerate(KI.COMPETENCES)]
    dec = {c["id"] for c in comp if c["niveau"] == "decouverte"}
    p = KI.progression(comp, dec)
    assert p["decouverte"] == {"total": 7, "faites": 7, "pct": 100} and p["explorateur"]["faites"] == 0
    assert KI.niveau_atteint(p) == "decouverte"
    b = KI.badges_dus(comp, dec, nb_presences=26, nb_courses=1)
    assert "niveau_decouverte" in b and "presences_25" in b and "presences_50" not in b and "premiere_course" in b
    assert "domaine_courir" in b                      # les deux compétences « courir » du niveau commencé
    assert KI.libelle_badge("domaine_monter").endswith("Grimpeur") and "Découverte" in KI.libelle_badge("niveau_decouverte")
    assert KI.reperes_ffa("BE") == ["trail : 3 km et 150 m D+ au plus", "route : 3 km au plus"]
    assert "animations" in KI.reperes_ffa("EA")[0]


def _ecole():
    from noyau.donnees import club as dclub, personnes as dper
    from noyau.club import imports as imp
    cid = dclub.enregistrer_club({"nom": "Ventoux Trail Athlé"})
    dclub.importer(cid, "2026-2027", imp.analyser(imp.lire_tableau(
        "Nom;Prénom;Date de naissance\nFAURE;Léa;30/06/2016\nGARCIN;Lou;01/02/2014\nMARTIN;Lucas;12/03/1985\n"))["lignes"])
    adh = {a["nom"]: a["personne_id"] for a in dclub.adhesions(cid, "2026-2027")}
    parent = dper.creer({"nom": "FAURE", "prenom": "Marc"}, ["parent"])
    dper.lier_parent(parent, adh["FAURE"])
    return cid, adh, parent


def test_base(base_vide):
    from noyau.donnees import kids as dki
    cid, adh, parent = _ecole()
    es = dki.enfants(cid, "2026-2027")
    assert [e["nom"] for e in es] == ["FAURE", "GARCIN"]          # pas l'adulte
    comp = dki.competences(cid)
    assert len(comp) == len(KI.COMPETENCES) and dki.competences(cid) == comp   # référentiel créé une fois
    dec = [c for c in comp if c["niveau"] == "decouverte"]
    for c in dec[:-1]:
        assert dki.valider(adh["FAURE"], c["id"], "Marc") in ([], ["🏃 Coureur"])
    gagnes = dki.valider(adh["FAURE"], dec[-1]["id"], "Marc")
    assert any("Découverte terminé" in g for g in gagnes)
    assert dki.valider(adh["FAURE"], dec[-1]["id"]) == []         # pas de doublon
    dki.retirer_validation(adh["FAURE"], dec[0]["id"])
    assert any(b["code"] == "niveau_decouverte" for b in dki.badges(adh["FAURE"]))   # le badge reste
    with pytest.raises(dki.ErreurKids):
        dki.valider(adh["FAURE"], 99999)
    perso = dki.ajouter_competence(cid, "explorateur", "nature", "Reconnaître trois plantes du Ventoux")
    assert any(c["id"] == perso for c in dki.competences(cid)) and not any(c["id"] == perso for c in dki.competences(None))
    with pytest.raises(dki.ErreurKids):
        dki.ajouter_competence(cid, "expert", "nature", "x")
    dki.enregistrer_equipement(adh["FAURE"], {"pointure": "33", "gourde": True})
    dki.enregistrer_equipement(adh["FAURE"], {"taille_tshirt": "10 ans"})
    eq = dki.equipement(adh["FAURE"])
    assert eq["pointure"] == "33" and eq["gourde"] == 1 and eq["taille_tshirt"] == "10 ans"
    c = dki.carnet(adh["FAURE"], cid, "2026-2027")
    assert c["niveaux"][0]["faites"] == 6 and c["categorie"]["code"] == "PO" and not c["accord_parental"]
    assert dki.enfants_du_parent(parent) == [adh["FAURE"]]
    b = dki.bilan_club(cid, "2026-2027")
    assert b["enfants"] == 2 and b["badges_saison"] >= 1 and b["sans_accord"] == 2


def test_pages(base_vide, tmp_path):
    import sys
    sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent))
    from test_serveur import _web
    from noyau.serveur import serveur as S
    from noyau.donnees import comptes as dco, kids as dki, personnes as dper
    cid, adh, parent = _ecole()
    autre = dper.creer({"nom": "X", "prenom": "Y"}, ["parent"])
    for ident, role, pid in (("coach", "entraineur", None), ("papa", "parent", parent), ("autre", "parent", autre)):
        k, _p = dco.creer_compte(ident, ident, pid, "Ventoux-2026")
        dco.ajouter_role(k, role, cid)
    info = S.demarrer(0, True, "127.0.0.1", tmp_path / "c")
    try:
        port = info["port"]
        ck = _web(port, "POST", "/m/connexion", {"identifiant": "coach", "mot_de_passe": "Ventoux-2026"})[1].split(";")[0]
        page = _web(port, "GET", "/m/kids", cookie=ck)[3]
        assert "FAURE Léa" in page and "GARCIN Lou" in page and "MARTIN" not in page
        page = _web(port, "GET", f"/m/kids?enfant={adh['FAURE']}", cookie=ck)[3]
        csrf = re.search(r"name='csrf' value='([0-9a-f]+)'", page).group(1)
        cid0 = re.search(r"name='competence' value='(\d+)'", page).group(1)
        page = _web(port, "POST", f"/m/kids?enfant={adh['FAURE']}", {"csrf": csrf, "competence": cid0, "valide": "1"}, ck)[3]
        assert "Compétence validée" in page and int(cid0) in dki.validees(adh["FAURE"])
        assert _web(port, "GET", f"/m/kids?enfant={adh['MARTIN']}", cookie=ck)[0] == 200   # adhérent du club, même adulte
        # le parent voit son enfant, sans pouvoir valider ; pas les autres
        ckp = _web(port, "POST", "/m/connexion", {"identifiant": "papa", "mot_de_passe": "Ventoux-2026"})[1].split(";")[0]
        page = _web(port, "GET", "/m/kids", cookie=ckp)[3]
        assert "Léa" in page and "GARCIN" not in page
        page = _web(port, "GET", f"/m/kids?enfant={adh['FAURE']}", cookie=ckp)[3]
        assert "Prochaines séances" in page and "name='competence'" not in page
        assert _web(port, "GET", f"/m/kids?enfant={adh['GARCIN']}", cookie=ckp)[0] == 403
        cka = _web(port, "POST", "/m/connexion", {"identifiant": "autre", "mot_de_passe": "Ventoux-2026"})[1].split(";")[0]
        assert _web(port, "GET", f"/m/kids?enfant={adh['FAURE']}", cookie=cka)[0] == 403
    finally:
        S.arreter()


def test_ecran(base_vide, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QApplication, QMessageBox
    from PySide6.QtCore import Qt
    QApplication.instance() or QApplication([])
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: None))
    from noyau.donnees import kids as dki
    cid, adh, parent = _ecole()
    from interface.club import ClubFenetre
    from interface.club_kids import html_carnet
    f = ClubFenetre(1)
    assert f.tabs.count() == 12
    k = f.kids
    k.combo_saison.setCurrentIndex(max(0, k.combo_saison.findData("2026-2027")))
    k.actualiser()
    assert k.table.rowCount() == 2
    k.table.selectRow(0)
    assert "Léa" in k.titre.text() and k.liste.count() > 20
    it = next(k.liste.item(i) for i in range(k.liste.count()) if k.liste.item(i).flags() & Qt.ItemFlag.ItemIsUserCheckable)
    it.setCheckState(Qt.CheckState.Checked)
    assert len(dki.validees(adh["FAURE"])) == 1
    k.table.selectRow(0)
    k.eq["pointure"].setText("34")
    k._enregistrer_eq()
    assert dki.equipement(adh["FAURE"])["pointure"] == "34"
    from interface import orga_pdf as P
    P.rendre(tmp_path / "c.pdf", "c", html_carnet({"nom": "Club"}, dki.carnet(adh["FAURE"])))
    assert (tmp_path / "c.pdf").read_bytes()[:4] == b"%PDF"
    f.close()
