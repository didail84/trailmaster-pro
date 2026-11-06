"""Étape 6 : jour de course (points de contrôle, situation des coureurs, incidents hors ligne, présence des
bénévoles, Trail Live)."""
import json
import re
from datetime import datetime, timedelta

import pytest

from noyau.organisation import commandement as K

JOUR = "2027-04-11"


def _t(h):
    return f"{JOUR}T{h}"


def test_situation():
    eps = [{"id": 1, "nom": "25 km", "distance_km": 25, "denivele_m": 1000, "depart_reel": _t("08:00:00"), "date": JOUR}]
    pts = [{"id": 10, "nom": "Col", "km": 10, "epreuve_ids": [], "barriere_horaire": None},
           {"id": 11, "nom": "Crête", "km": 18, "epreuve_ids": [1], "barriere_horaire": "11:30"}]
    ins = [{"id": i, "dossard": i, "nom": n, "prenom": "", "epreuve_id": 1, "statut_course": st, "temps_corrige_s": None}
           for i, n, st in ((1, "Rapide", None), (2, "Lent", None), (3, "Perdu", None), (4, "Abd", "abandon"), (5, "Fini", None))]
    ps = [{"dossard": 1, "heure": _t("09:00:00"), "point": "pc10"}, {"dossard": 1, "heure": _t("10:50:00"), "point": "pc11"},
          {"dossard": 2, "heure": _t("10:00:00"), "point": "pc10"}, {"dossard": 5, "heure": _t("10:30:00"), "point": "arrivee"}]
    l = {x["dossard"]: x for x in K.situation(ins, eps, pts, ps, datetime.fromisoformat(_t("11:45:00")))}
    assert l[5]["etat"] == "arrivé" and l[5]["temps"] == 9000
    assert l[4]["etat"] == "abandon"
    # rapide : à la crête à 10:50, attendu à l'arrivée vers 11:56 ; pas encore en retard
    assert l[1]["etat"] == "en course" and l[1]["dernier"] == "Crête" and l[1]["prochain"] == "Arrivée"
    # lent : pointé au col à 10:00, attendu à la crête vers 11:36 ; barrière de 11:30 dépassée
    assert l[2]["etat"] == "hors délai" and "11:30" in l[2]["alerte"]
    # perdu : jamais pointé, attendu au col vers 10:06 (9 min / km-effort) → à chercher
    assert l[3]["etat"] == "à chercher" and "Col" in l[3]["alerte"] and l[3]["attendu"] == _t("10:06:00")
    b = K.bilan(list(l.values()))
    assert b == {"total": 5, "en_course": 3, "a_chercher": 1, "hors_delai": 1, "arrives": 1, "abandons": 1, "non_partis": 0}
    # pas de départ donné : « pas parti »
    eps[0]["depart_reel"] = None
    assert K.situation(ins[:1], eps, pts, [])[0]["etat"] == "pas parti"


def test_carte_et_positions():
    pts = [{"id": 1, "nom": "Col", "km": 10}, {"id": 2, "nom": "Crête", "km": 18}]
    svg = K.svg_carte(pts, [{"dossard": 7, "km": 12, "etat": "en course"}], [{"numero": 1, "km": 15}], km_total=25)
    assert svg.startswith("<svg") and "Col · km 10" in svg and "<title>7</title>" in svg and "n°1" in svg
    geo = [{"id": 1, "nom": "A", "km": 0, "lat": 44.1, "lon": 5.0}, {"id": 2, "nom": "B", "km": 10, "lat": 44.2, "lon": 5.1}]
    assert "polyline" in K.svg_carte(geo, [{"dossard": 3, "lat": 44.15, "lon": 5.05, "etat": "à chercher"}])
    lus = K.lire_positions("dossard;heure;lat;lon\n12;2027-04-11 09:10:00;44,12;5,04\nx;y;z;w\n")
    assert lus == [(12, "2027-04-11T09:10:00", 44.12, 5.04)]
    gpx = ('<gpx><trk><trkseg><trkpt lat="44.1" lon="5.0"><time>2027-04-11T07:10:00Z</time></trkpt>'
           '<trkpt lat="44.2" lon="5.1"></trkpt></trkseg></trk></gpx>')
    assert len(K.lire_positions(gpx, "a.gpx", 9)) == 1
    with pytest.raises(ValueError):
        K.lire_positions(gpx, "a.gpx")


def _course():
    from noyau.donnees import organisation as dor, chrono as dch, logistique as dl
    ev = dor.enregistrer_evenement({"nom": "Trail des Dentelles", "date_debut": datetime.now().date().isoformat()})
    ep = dor.enregistrer_epreuve(ev, {"nom": "25 km", "distance_km": 25, "denivele_m": 1000, "dossard_debut": 1, "dossard_fin": 99})
    for n in ("Roux", "Blanc", "Faure"):
        dor.enregistrer_inscription({"epreuve_id": ep, "nom": n, "prenom": "X", "statut": "validee"})
    dor.attribuer_dossards(ev)
    dch.donner_depart(ep, (datetime.now() - timedelta(hours=3)).isoformat(timespec="seconds"))
    r = dl.enregistrer_ravitaillement(ev, {"nom": "Col du Cayron", "km": 10, "type": "complet", "barriere_horaire": "23:59"})
    dl.enregistrer_ravitaillement(ev, {"nom": "Arrivée", "km": 25, "type": "arrivee"})
    return ev, ep, r


def test_base(base_vide):
    from noyau.donnees import commandement as dk, organisation as dor, logistique as dl, comptes as dco
    ev, ep, r = _course()
    assert dk.creer_points_depuis_ravitaillements(ev) == 1 and dk.creer_points_depuis_ravitaillements(ev) == 0
    col = dk.points(ev)[0]
    assert col["nom"] == "Col du Cayron" and col["barriere_horaire"] == "23:59" and col["cle"] == f"pc{col['id']}"
    assert dk.pointer(ev, col["id"], 1)["inscrit"]["nom"] == "Blanc"
    assert "double top" in dk.pointer(ev, col["id"], 1)["avertissement"]
    assert dk.pointer(ev, col["id"], 1, (datetime.now() + timedelta(minutes=1)).isoformat())["avertissement"].endswith("(doublon)")
    assert dk.pointer(ev, "arrivee", 2)["avertissement"] is None        # l'arrivée garde ses propres doubles tops
    with pytest.raises(dk.ErreurCommandement):
        dk.pointer(ev, 9999, 1)
    s = {l["dossard"]: l for l in dk.situation(ev)}
    assert s[1]["dernier"] == "Col du Cayron" and s[2]["etat"] == "arrivé" and s[3]["etat"] == "à chercher"
    # incidents : envoyés deux fois après une coupure, enregistrés une fois
    i1, c1 = dk.signaler(ev, {"type": "blessure", "gravite": "urgent", "dossard": "3", "point_id": str(col["id"]),
                              "description": "cheville", "cle_client": "abc"}, "Marc")
    assert c1 and dk.signaler(ev, {"description": "x", "cle_client": "abc"}) == (i1, False)
    i2, _ = dk.signaler(ev, {"type": "balisage", "gravite": "info", "description": "rubalise arrachée"})
    with pytest.raises(dk.ErreurCommandement):
        dk.signaler(ev, {"type": "autre"})
    with pytest.raises(dk.ErreurCommandement):
        dk.signaler(ev, {"type": "volcan", "description": "x"})
    inc = dk.incidents(ev)
    assert [i["numero"] for i in inc] == [1, 2] and inc[0]["km"] == 10 and inc[0]["coureur"] == "X Roux"
    dk.prendre_en_charge(i1, "PC")
    dk.ajouter_suivi(i1, "secouristes envoyés", "PC")
    dk.clore(i1, "PC", "évacué")
    i = next(x for x in dk.incidents(ev) if x["id"] == i1)
    assert i["statut"] == "clos" and [s["texte"] for s in i["suivi"]] == ["pris en charge", "secouristes envoyés", "évacué"]
    assert len(dk.incidents(ev, True)) == 1
    dk.rouvrir(i1)
    assert len(dk.incidents(ev, True)) == 2
    dk.marquer_abandon(ev, 3)
    assert {l["dossard"]: l for l in dk.situation(ev)}[3]["etat"] == "abandon"
    # présence des bénévoles
    b = dl.enregistrer_benevole(ev, {"nom": "Bonnet", "prenom": "Marc"})
    p = dl.enregistrer_poste(ev, {"nom": "Ravito Col", "besoin": 2})
    dl.affecter(p, b)
    with pytest.raises(dk.ErreurCommandement):
        dk.marquer_present(p, 999)
    dk.marquer_present(p, b)
    assert dk.presences(ev)[0]["presents"] == 1 and dk.tableau(ev)["benevoles_presents"] == 1
    # Trail Live : position cachée sans consentement
    assert dk.importer_positions(ev, "1;2027-04-11T09:00:00;44.1;5.0\n1;2027-04-11T09:05:00;44.2;5.1\n") == {"lues": 2, "ajoutees": 2}
    assert dk.importer_positions(ev, "1;2027-04-11T09:05:00;44.2;5.1\n")["ajoutees"] == 0
    assert dk.dernieres_positions(ev)[1]["lat"] == 44.2
    j = dk.activer_live(ev, avec_noms=False, telephone_pc="0600000000")
    assert dk.evenement_du_jeton(j) == ev and dk.activer_live(ev) == j
    pub = dk.suivi_public(ev)
    assert {x["dossard"] for x in pub} == {1, 2, 3} and all(x["position"] is None for x in pub)
    dk.activer_live(ev, avec_noms=False)
    assert all(x["nom"] == "" for x in dk.suivi_public(ev)) and dk.suivi_public(ev, "2")[0]["dossard"] == 2
    from noyau.donnees import personnes as dper
    pid = dper.creer({"nom": "Blanc", "prenom": "X"}, ["coureur"])
    ins = next(x for x in dor.inscriptions(ev) if x["dossard"] == 1)
    dor.enregistrer_inscription({"personne_id": pid}, ins["id"])
    dco.enregistrer_consentement(pid, "geolocalisation", True)
    assert next(x for x in dk.suivi_public(ev) if x["dossard"] == 1)["position"]["lat"] == 44.2
    dk.desactiver_live(ev)
    assert dk.evenement_du_jeton(j) is None


def test_pages_jour_de_course(base_vide, tmp_path):
    import sys
    sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent))
    from test_serveur import _web
    from noyau.serveur import serveur as S
    from noyau.donnees import commandement as dk, comptes as dco, logistique as dl, personnes as dper
    ev, ep, r = _course()
    dk.creer_points_depuis_ravitaillements(ev)
    col = dk.points(ev)[0]
    pid = dper.creer({"nom": "Bonnet", "prenom": "Marc"}, ["benevole"])
    cid, _p = dco.creer_compte("marc", "Marc", pid, "Ventoux-2026")
    dco.ajouter_role(cid, "benevole", evenement_id=ev)
    oid, _p = dco.creer_compte("orga", "Orga", None, "Ventoux-2026")
    dco.ajouter_role(oid, "organisateur", evenement_id=ev)
    b = dl.ajouter_personnes(ev, [pid])
    poste = dl.enregistrer_poste(ev, {"nom": "Ravito Col"})
    dl.affecter(poste, dl.benevoles(ev)[0]["id"])
    info = S.demarrer(0, True, "127.0.0.1", tmp_path / "c")
    try:
        port = info["port"]
        ck = _web(port, "POST", "/m/connexion", {"identifiant": "marc", "mot_de_passe": "Ventoux-2026"})[1].split(";")[0]
        # pointage à un point de contrôle
        page = _web(port, "GET", f"/m/chrono?ev={ev}&pc={col['id']}", cookie=ck)[3]
        assert "Pointage · Col du Cayron" in page and "Je pointe à" in page
        csrf = re.search(r"name='csrf' value='([0-9a-f]+)'", page).group(1)
        page = _web(port, "POST", f"/m/chrono?ev={ev}&pc={col['id']}", {"dossard": "2", "csrf": csrf}, ck)[3]
        assert "Faure" in page
        assert any(l["dossard"] == 2 and l["dernier"] == "Col du Cayron" for l in dk.situation(ev))
        # incident : formulaire, puis envoi « hors ligne » deux fois
        page = _web(port, "GET", f"/m/incident?ev={ev}", cookie=ck)[3]
        assert "15 ou le 112" in page and "/m/hors-ligne.js" in page
        js = _web(port, "GET", "/m/hors-ligne.js", cookie=ck)
        assert js[0] == 200 and "localStorage" in js[3]
        corps = {"ev": str(ev), "csrf": csrf, "type": "malaise", "gravite": "urgent", "dossard": "1", "description": "vertiges",
                 "cle_client": "tel-1", "horodatage": "2027-04-11T10:12:00"}
        s1 = _web(port, "POST", "/m/incident-envoi", corps, ck)
        s2 = _web(port, "POST", "/m/incident-envoi", corps, ck)
        assert json.loads(s1[3])["numero"] == 1 and json.loads(s2[3])["deja"] is True and len(dk.incidents(ev)) == 1
        assert _web(port, "POST", "/m/incident-envoi", {**corps, "csrf": "x"}, ck)[0] == 403
        page = _web(port, "POST", f"/m/incident?ev={ev}", {"csrf": csrf, "type": "balisage", "gravite": "info",
                                                            "description": "flèche tournée"}, ck)[3]
        assert "Incident n°2 reçu" in page
        # présence au poste
        page = _web(port, "GET", f"/m/poste?ev={ev}", cookie=ck)[3]
        assert "Je suis arrivé à mon poste" in page
        _web(port, "POST", f"/m/poste-present?ev={ev}", {"csrf": csrf, "poste": str(poste), "present": "1"}, ck)
        assert dk.presences(ev)[0]["presents"] == 1
        # le bénévole n'a pas le tableau de commandement ; l'organisateur oui
        assert _web(port, "GET", f"/m/commandement?ev={ev}", cookie=ck)[0] == 403
        ck2 = _web(port, "POST", "/m/connexion", {"identifiant": "orga", "mot_de_passe": "Ventoux-2026"})[1].split(";")[0]
        page = _web(port, "GET", f"/m/commandement?ev={ev}", cookie=ck2)[3]
        assert "Incidents ouverts (2)" in page and "vertiges" in page
        csrf2 = re.search(r"name='csrf' value='([0-9a-f]+)'", page).group(1)
        iid = dk.incidents(ev)[0]["id"]
        page = _web(port, "POST", f"/m/commandement?ev={ev}", {"csrf": csrf2, "incident": str(iid), "action": "clore"}, ck2)[3]
        assert "Incident clos" in page and len(dk.incidents(ev, True)) == 1
        # page publique, sans compte
        assert _web(port, "GET", "/live/inexistant")[0] == 404
        j = dk.activer_live(ev)
        s, _c, _o, page = _web(port, "GET", f"/live/{j}?q=Faure")
        assert s == 200 and "Faure" in page and "Blanc" not in page and "refresh" in page
    finally:
        S.arreter()


def test_ecran(base_vide, monkeypatch):
    from PySide6.QtWidgets import QApplication, QMessageBox
    QApplication.instance() or QApplication([])
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: None))
    from noyau.donnees import commandement as dk
    ev, ep, r = _course()
    from interface.organisation import OrganisationFenetre
    f = OrganisationFenetre(1)
    c = f.commandement
    c._points_ravitos()
    assert c.table_pts.rowCount() == 1
    c.saisie.setText("1")
    c.point_saisie.setCurrentIndex(0)
    c._pointer()
    assert "Col du Cayron" in c.retour.text()
    dk.signaler(ev, {"type": "blessure", "gravite": "urgent", "description": "chute", "dossard": "3"})
    c.rafraichir()
    assert c.table_inc.rowCount() == 1 and c.cartes["incidents"].valeur.text() == "1"
    assert c.cartes["a_chercher"].valeur.text() in ("1", "2")
    assert c.table.rowCount() == 3
    c._live()
    assert "/live/" in c.info_live.text()
    p = __import__("pathlib").Path(__file__).parent / "_pos.csv"
    p.write_text("1;2027-04-11T09:00:00;44.1;5.0\n")
    try:
        assert c.importer_positions(str(p))["ajoutees"] == 1
    finally:
        p.unlink()
    f.close()
