"""Étape 5 : mode serveur (comptes, droits, journal, consentements, API, pages web, accès simultanés)."""
import http.client
import json
import re
import ssl
import threading
from datetime import datetime, timedelta
from urllib.parse import urlencode

import pytest

from noyau.serveur import droits as D, mots_de_passe as M


def test_mots_de_passe():
    h = M.hacher("Trail2026!x", 1000)
    assert h.startswith("pbkdf2_sha256$1000$") and M.verifier("Trail2026!x", h) and not M.verifier("autre", h)
    assert not M.verifier("x", "n'importe quoi")
    for mauvais in ("court1", "seulementdeslettres", "didier2026xx"):
        with pytest.raises(M.ErreurMotDePasse):
            M.verifier_solidite(mauvais, "didier")
    M.verifier_solidite("Ventoux-2026", "didier")
    p = M.mot_de_passe_provisoire()
    assert len(p) == 12 and not set(p) & set("0O1l")
    assert M.empreinte_jeton("a") != M.empreinte_jeton("b")


def test_droits():
    bureau_a = [{"role": "bureau", "club_id": 1, "evenement_id": None}]
    assert D.autorise(bureau_a, "club", True, {1}) and not D.autorise(bureau_a, "club", True, {2})
    assert D.autorise(bureau_a, "organisation", True, evenements_vises={7}, clubs_des_evenements={7: 1})
    assert not D.autorise(bureau_a, "organisation", True, evenements_vises={8}, clubs_des_evenements={8: 2})
    ent = [{"role": "entraineur", "club_id": 1}]
    assert D.autorise(ent, "presences", True, {1}) and not D.autorise(ent, "club", True, {1})
    assert D.autorise(ent, "club", False, {1})
    orga = [{"role": "organisateur", "evenement_id": 7}]
    assert D.autorise(orga, "chrono", True, evenements_vises={7}) and not D.autorise(orga, "chrono", True, evenements_vises={8})
    assert not D.autorise(orga, "club", True, {1}) and D.autorise(orga, "club", False, {1})
    assert not D.autorise([{"role": "benevole", "evenement_id": 7}], "chrono", True, evenements_vises={7})
    assert D.autorise([{"role": "admin"}], "comptes", True) and not D.autorise(bureau_a, "comptes", False)
    assert D.est_lecture("adhesions") and not D.est_lecture("enregistrer_adhesion") and not D.est_lecture("choisir_club")
    assert D.clubs_de([{"role": "admin"}]) is None and D.clubs_de(bureau_a) == {1}
    assert "chrono" in D.pages_autorisees([{"role": "benevole"}]) and "appel" not in D.pages_autorisees([{"role": "benevole"}])


def test_comptes(base_vide):
    from noyau.donnees import comptes as dco, personnes as dper
    cid, prov = dco.creer_compte("didier", "Didier")
    assert prov and dco.compte(cid)["doit_changer"] == 1
    with pytest.raises(dco.ErreurCompte):
        dco.creer_compte("Didier")
    with pytest.raises(dco.ErreurCompte):
        dco.creer_compte("avec espace")
    dco.ajouter_role(cid, "admin")
    assert dco.a_un_admin()
    with pytest.raises(dco.ErreurCompte):
        dco.supprimer_compte(cid)                       # dernier administrateur
    with pytest.raises(dco.ErreurCompte):
        dco.ajouter_role(cid, "bureau")                 # il faut une association
    j, c = dco.authentifier("DIDIER", prov, "10.0.0.2")
    assert dco.session(j)["id"] == cid and c["roles"][0]["role"] == "admin"
    dco.changer_mot_de_passe(cid, "Ventoux-2026", prov)
    with pytest.raises(dco.ErreurCompte):
        dco.changer_mot_de_passe(cid, "Ventoux-2027", "faux")
    # 5 essais manqués : bloqué
    for _ in range(5):
        with pytest.raises(dco.ErreurCompte):
            dco.authentifier("didier", "mauvais", "10.0.0.9")
    with pytest.raises(dco.ErreurCompte, match="Trop d'essais"):
        dco.authentifier("didier", "Ventoux-2026")
    j2 = dco.reinitialiser_mot_de_passe(cid)
    assert dco.session(j) is None                       # sessions fermées
    assert dco.authentifier("didier", j2)[1]["doit_changer"] == 1
    with pytest.raises(dco.ErreurCompte):
        dco.authentifier("inconnu", "x")
    jr = dco.journal()
    assert any(l["detail"] == "compte bloqué" for l in jr) and any(not l["reussi"] for l in jr)
    # consentements
    pid = dper.creer({"nom": "Faure", "prenom": "Léa", "date_naissance": "2016-06-30"}, ["enfant"])
    par = dper.creer({"nom": "Faure", "prenom": "Marc"}, ["parent"])
    k = dco.enregistrer_consentement(pid, "parental", True, par, "Marc Faure")
    dco.enregistrer_consentement(pid, "image", False, par)
    assert dco.a_consenti(pid, "parental") and not dco.a_consenti(pid, "image")
    dco.retirer_consentement(k)
    assert not dco.a_consenti(pid, "parental")
    with pytest.raises(dco.ErreurCompte):
        dco.enregistrer_consentement(pid, "inconnu")


def _monde():
    """Deux associations, un événement de chacune ; comptes bureau A, entraîneur A, organisateur de l'événement A,
    bénévole de l'événement A."""
    from noyau.donnees import club as dclub, organisation as dor, comptes as dco
    from noyau.club import imports as imp
    a = dclub.enregistrer_club({"nom": "Club A"})
    b = dclub.enregistrer_club({"nom": "Club B"})
    dclub.importer(a, "2026-2027", imp.analyser(imp.lire_tableau("Nom;Prénom;Date de naissance\nMARTIN;Lucas;12/03/1985\n"))["lignes"])
    dclub.importer(b, "2026-2027", imp.analyser(imp.lire_tableau("Nom;Prénom;Date de naissance\nFAURE;Léa;01/01/1990\n"))["lignes"])
    jour = (datetime.now().date()).isoformat()
    ea = dor.enregistrer_evenement({"nom": "Trail A", "date_debut": jour, "club_id": a})
    eb = dor.enregistrer_evenement({"nom": "Trail B", "date_debut": jour, "club_id": b})
    ep = dor.enregistrer_epreuve(ea, {"nom": "25 km", "distance_km": 25, "dossard_debut": 1, "dossard_fin": 50})
    for n in ("Roux", "Blanc"):
        dor.enregistrer_inscription({"epreuve_id": ep, "nom": n, "prenom": "X", "statut": "validee"})
    dor.attribuer_dossards(ea)
    comptes = {}
    for ident, role, cl, ev in (("admin", "admin", None, None), ("bureau.a", "bureau", a, None),
                                ("coach.a", "entraineur", a, None), ("orga.a", "organisateur", None, ea),
                                ("benevole.a", "benevole", None, ea)):
        cid, _ = dco.creer_compte(ident, mot_de_passe="Ventoux-2026")
        dco.ajouter_role(cid, role, cl, ev)
        comptes[ident] = dco.compte(cid)
    return a, b, ea, eb, ep, comptes


def test_rpc(base_vide):
    from noyau.serveur import rpc
    from noyau.donnees import club as dclub, comptes as dco
    a, b, ea, eb, ep, c = _monde()
    x = lambda ident, m, f, *args, **kw: rpc.executer(c[ident], m, f, args, kw)
    assert [k["nom"] for k in x("bureau.a", "club", "clubs")["ok"]] == ["Club A"]
    assert len(x("admin", "club", "clubs")["ok"]) == 2
    assert len(x("bureau.a", "club", "adhesions", a, "2026-2027")["ok"]) == 1
    r = x("bureau.a", "club", "adhesions", b, "2026-2027")
    assert r["erreur"]["type"] == "Refus"
    adh_b = dclub.adhesions(b, "2026-2027")[0]
    assert x("bureau.a", "club", "enregistrer_paiement", adh_b["id"], 10)["erreur"]["type"] == "Refus"
    assert x("bureau.a", "personnes", "fiche", adh_b["personne_id"])["erreur"]["type"] == "Refus"
    assert [p["nom"] for p in x("bureau.a", "personnes", "lister")["ok"]] == ["MARTIN"]
    # erreur lisible du noyau : même type que sur le poste
    assert x("bureau.a", "club", "enregistrer_groupe", a, {"nom": ""})["erreur"]["type"] == "ErreurClub"
    assert x("coach.a", "club", "enregistrer_groupe", a, {"nom": "Adultes"})["erreur"]["type"] == "Refus"
    assert x("coach.a", "club", "groupes", a)["ok"] == []
    # organisateur : son événement seulement
    assert "ok" in x("orga.a", "chrono", "donner_depart", ep)
    assert x("orga.a", "chrono", "ajouter_passage", ea, 1)["ok"]["inscrit"]["nom"] == "Blanc"
    assert x("orga.a", "chrono", "ajouter_passage", eb, 1)["erreur"]["type"] == "Refus"
    assert [e["nom"] for e in x("orga.a", "organisation", "evenements")["ok"]] == ["Trail A"]
    assert x("benevole.a", "chrono", "passages", ea)["erreur"]["type"] == "Refus"       # pages web seulement
    assert x("admin", "comptes", "comptes")["ok"] and x("bureau.a", "comptes", "comptes")["erreur"]["type"] == "Refus"
    assert x("admin", "comptes", "authentifier", "admin", "x")["erreur"]["type"] == "Refus"   # jamais par l'API
    assert x("admin", "club", "choisir_club", b)["erreur"]["type"] == "Refus"            # propre à chaque poste
    assert x("admin", "inconnu", "f")["erreur"]["type"] == "Refus"
    # clés entières et tuples gardés
    assert rpc.decoder(rpc.encoder({3: ("present", "note")})) == {3: ["present", "note"]}
    assert rpc.decoder(rpc.encoder(b"\x00\x01")) == b"\x00\x01"
    # contexte : l'association choisie par la personne, pas celle du serveur
    dclub.choisir_club(b)
    assert rpc.executer(c["bureau.a"], "club", "club_id_ou_creer", contexte={"club_id": a}).get("erreur")
    assert dclub.club_courant_id() == b
    assert any(l["action"] == "ecriture" and l["objet"] == "chrono.ajouter_passage" for l in dco.journal())
    assert any(l["action"] == "refus" for l in dco.journal())


def test_conflit_de_modification(base_vide):
    from noyau.donnees import club as dclub, organisation as dor
    a, b, ea, eb, ep, c = _monde()
    ad = dclub.adhesions(a, "2026-2027")[0]
    lu = ad["maj"]
    assert lu
    dclub.enregistrer_adhesion(a, ad["personne_id"], "2026-2027", {"notes": "première"}, ad["id"], lu)
    with pytest.raises(dclub.ErreurClub, match="modifiée par quelqu'un d'autre"):
        dclub.enregistrer_adhesion(a, ad["personne_id"], "2026-2027", {"notes": "seconde"}, ad["id"], lu)
    i = dor.inscriptions(ea)[0]
    dor.enregistrer_inscription({"club": "X"}, i["id"], i["maj"])
    with pytest.raises(dor.ErreurOrganisation):
        dor.enregistrer_inscription({"club": "Y"}, i["id"], i["maj"])


# ------------------------------------------------------------------ serveur réel

@pytest.fixture
def serveur(base_vide, tmp_path):
    from noyau.serveur import serveur as S
    monde = _monde()
    info = S.demarrer(0, True, "127.0.0.1", tmp_path / "certs")
    yield info, monde
    S.arreter()


def _web(port, verbe, chemin, corps=None, cookie=None):
    ctx = ssl._create_unverified_context()
    c = http.client.HTTPSConnection("127.0.0.1", port, context=ctx, timeout=10)
    e = {"Content-Type": "application/x-www-form-urlencoded"}
    if cookie:
        e["Cookie"] = cookie
    c.request(verbe, chemin, body=urlencode(corps) if corps else None, headers=e)
    r = c.getresponse()
    return r.status, r.getheader("Set-Cookie"), r.getheader("Location"), r.read().decode()


@pytest.fixture
def serveur_a_part(base_vide, tmp_path):
    """Le serveur dans un autre processus, comme sur le NAS (même fichier de base)."""
    import socket
    import subprocess
    import sys
    import time
    from pathlib import Path
    monde = _monde()
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    racine = Path(__file__).resolve().parent.parent
    p = subprocess.Popen([sys.executable, str(racine / "trailhub_serveur.py"), "--base", str(base_vide), "--port", str(port),
                          "--hote", "127.0.0.1"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    sortie = []
    for _ in range(100):
        ligne = p.stdout.readline()
        sortie.append(ligne)
        if "Ctrl+C" in ligne or p.poll() is not None:
            break
    texte = "".join(sortie)
    assert "Serveur ouvert" in texte, texte
    empreinte = re.search(r"([0-9A-F]{2}(?::[0-9A-F]{2}){31})", texte).group(1)
    yield port, empreinte, monde
    p.terminate()
    p.wait(10)


def test_client_et_bascule(serveur_a_part):
    from noyau.serveur import client as C
    from noyau.donnees import club as dclub
    port, emp, (a, b, ea, eb, ep, comptes) = serveur_a_part
    cl = C.Client(f"https://127.0.0.1:{port}")
    assert cl.info()["application"] == "Trail Hub Center" and cl.empreinte == emp
    url = f"https://127.0.0.1:{port}"
    with pytest.raises(C.ErreurServeur):
        cl.connecter("bureau.a", "faux")
    assert cl.connecter("bureau.a", "Ventoux-2026")["identifiant"] == "bureau.a"
    # mauvaise empreinte : refus
    with pytest.raises(C.ErreurConnexion, match="certificat"):
        C.Client(url, empreinte="00:11").info()
    restaurer = C.installer(cl, _Depot())
    try:
        assert C.branche() and [x["nom"] for x in dclub.clubs()] == ["Club A"]
        assert dclub.club_principal()["nom"] == "Club A"
        assert len(dclub.adhesions(a, "2026-2027")) == 1
        with pytest.raises(dclub.ErreurClub):
            dclub.enregistrer_groupe(a, {"nom": " "})
        g = dclub.enregistrer_groupe(a, {"nom": "Adultes"})
        assert isinstance(g, int)
        with pytest.raises(Exception, match="droit"):
            dclub.adhesions(b, "2026-2027")
    finally:
        restaurer()
    assert not C.branche() and len(dclub.clubs()) == 2 and dclub.groupes(a)[0]["nom"] == "Adultes"


def test_pas_de_bascule_sur_soi_meme(serveur):
    from noyau.serveur import client as C
    with pytest.raises(C.ErreurConnexion, match="lui-même le serveur"):
        C.installer(C.Client("https://127.0.0.1:1"), _Depot())


class _Depot:
    def __init__(self):
        self.d = {}

    def obtenir(self, k):
        return self.d.get(k)

    def definir(self, k, v):
        self.d[k] = v


def test_pages_web_et_saisie_simultanee(serveur):
    from noyau.donnees import chrono as dch, organisation as dor, comptes as dco
    info, (a, b, ea, eb, ep, comptes) = serveur
    port = info["port"]
    s, _ck, ou, page = _web(port, "GET", "/m/")
    assert s == 303 and ou == "/m/connexion"
    s, _ck, _o, page = _web(port, "POST", "/m/connexion", {"identifiant": "benevole.a", "mot_de_passe": "faux"})
    assert s == 401 and "incorrect" in page
    s, ck, ou, _p = _web(port, "POST", "/m/connexion", {"identifiant": "benevole.a", "mot_de_passe": "Ventoux-2026"})
    assert s == 303 and "HttpOnly" in ck and "Secure" in ck and "SameSite=Strict" in ck
    cookie = ck.split(";")[0]
    s, _c, _o, page = _web(port, "GET", "/m/", cookie=cookie)
    assert "Trail A" in page and f"/m/chrono?ev={ea}" in page and "Trail B" not in page
    s, _c, _o, page = _web(port, "GET", f"/m/chrono?ev={eb}", cookie=cookie)
    assert s == 403
    s, _c, _o, page = _web(port, "GET", f"/m/chrono?ev={ea}", cookie=cookie)
    csrf = re.search(r"name='csrf' value='([0-9a-f]+)'", page).group(1)
    s, _c, _o, page = _web(port, "POST", f"/m/chrono?ev={ea}", {"dossard": "1"}, cookie)
    assert s == 403                                       # sans jeton anti-falsification
    s, _c, _o, page = _web(port, "POST", f"/m/chrono?ev={ea}", {"dossard": "1", "csrf": csrf}, cookie)
    assert "Blanc" in page
    # deux personnes au chrono en même temps : aucun passage perdu
    s, ck2, _o, _p = _web(port, "POST", "/m/connexion", {"identifiant": "orga.a", "mot_de_passe": "Ventoux-2026"})
    cookie2 = ck2.split(";")[0]
    _s, _c, _o, p2 = _web(port, "GET", f"/m/chrono?ev={ea}", cookie=cookie2)
    csrf2 = re.search(r"name='csrf' value='([0-9a-f]+)'", p2).group(1)
    erreurs = []

    def saisir(ck, cs, debut):
        for d in range(debut, debut + 10):
            st, _a, _b, _c = _web(port, "POST", f"/m/chrono?ev={ea}", {"dossard": str(d), "csrf": cs}, ck)
            if st != 200:
                erreurs.append(st)
    t1 = threading.Thread(target=saisir, args=(cookie, csrf, 100))
    t2 = threading.Thread(target=saisir, args=(cookie2, csrf2, 200))
    t1.start(); t2.start(); t1.join(); t2.join()
    assert not erreurs and len(dch.passages(ea)) == 21
    s, _c, _o, page = _web(port, "POST", f"/m/chrono-annuler?ev={ea}", {"csrf": csrf}, cookie)
    assert "annulé" in page and len(dch.passages(ea)) == 20
    # mon poste : compte non relié
    s, _c, _o, page = _web(port, "GET", f"/m/poste?ev={ea}", cookie=cookie)
    assert "relié" in page
    # l'entraîneur fait l'appel ; le bénévole ne peut pas
    from noyau.donnees import agenda_club as dag
    sid = dag.enregistrer_seance(a, {"titre": "Piste", "date": datetime.now().date().isoformat()})
    s, ck3, _o, _p = _web(port, "POST", "/m/connexion", {"identifiant": "coach.a", "mot_de_passe": "Ventoux-2026"})
    cookie3 = ck3.split(";")[0]
    _s, _c, _o, page = _web(port, "GET", "/m/", cookie=cookie3)
    assert f"/m/appel?seance={sid}" in page
    _s, _c, _o, page = _web(port, "GET", f"/m/appel?seance={sid}", cookie=cookie3)
    csrf3 = re.search(r"name='csrf' value='([0-9a-f]+)'", page).group(1)
    pid = re.search(r"name='p(\d+)'", page).group(1)
    _s, _c, _o, page = _web(port, "POST", f"/m/appel?seance={sid}", {f"p{pid}": "present", "csrf": csrf3}, cookie3)
    assert "Appel enregistré (1" in page and dag.seance(sid)["appel_fait"] == 1
    assert _web(port, "GET", f"/m/appel?seance={sid}", cookie=cookie)[0] == 403
    # mot de passe provisoire : changement imposé
    cid, prov = dco.creer_compte("nouveau")
    dco.ajouter_role(cid, "benevole", evenement_id=ea)
    _s, ck4, _o, _p = _web(port, "POST", "/m/connexion", {"identifiant": "nouveau", "mot_de_passe": prov})
    _s, _c, _o, page = _web(port, "GET", f"/m/chrono?ev={ea}", cookie=ck4.split(";")[0])
    assert "Choisis ton mot de passe" in page
    # déconnexion
    s, ck, ou, _p = _web(port, "GET", "/m/deconnexion", cookie=cookie)
    assert ou == "/m/connexion" and _web(port, "GET", "/m/", cookie=cookie)[2] == "/m/connexion"


def test_ecrans(base_vide, monkeypatch):
    from PySide6.QtWidgets import QApplication, QMessageBox
    QApplication.instance() or QApplication([])
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: None))
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes))
    from interface.serveur import ServeurFenetre
    from noyau.donnees import comptes as dco
    from noyau.serveur import serveur as S, demarrage as DM
    f = ServeurFenetre(1)
    assert f.tabs.count() == 5
    l = f.local
    l.actualiser()
    assert l.b_admin.isEnabled()
    l.ident.setText("didier"); l.mdp.setText("Ventoux-2026"); l.mdp2.setText("Ventoux-2026")
    l._creer_admin()
    assert dco.a_un_admin() and not l.b_admin.isEnabled()
    try:
        S.demarrer(0, True, "127.0.0.1")
        l.actualiser()
        assert "/m/" in l.infos.text() and "Empreinte" in l.infos.text()
        # se connecter à ce serveur depuis l'onglet (comme un autre poste)
        c = f.connexion
        c.url.setText(f"https://127.0.0.1:{S.infos()['port']}")
        c.ident.setText("didier"); c.mdp.setText("Ventoux-2026")
        assert c._connecter(confirmer=False) and DM.configuration()["identifiant"] == "didier"
        c._oublier()
        assert DM.configuration()["url"] == ""
    finally:
        S.arreter()
    cp = f.comptes
    cp.rafraichir()
    assert cp.table.rowCount() == 1 and "Administrateur" in cp.table.item(0, 3).text()
    f.journal.rafraichir()
    assert f.journal.table.rowCount() >= 1
    f.consentements.rafraichir()
    f.close()


def test_copie_de_la_base(serveur_a_part, tmp_path):
    import sqlite3
    from noyau.serveur import client as C
    port, emp, monde = serveur_a_part
    cl = C.Client(f"https://127.0.0.1:{port}", emp)
    cl.connecter("bureau.a", "Ventoux-2026")
    with pytest.raises(C.ErreurServeur, match="administrateur"):
        cl.telecharger_copie(tmp_path / "x.db")
    cl.connecter("admin", "Ventoux-2026")
    assert cl.telecharger_copie(tmp_path / "copie.db") > 10000
    k = sqlite3.connect(tmp_path / "copie.db")
    assert k.execute("SELECT COUNT(*) FROM clubs").fetchone()[0] == 2
    assert k.execute("SELECT COUNT(*) FROM comptes").fetchone()[0] == 0
