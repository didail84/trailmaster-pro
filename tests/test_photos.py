"""Étape 7 : photos par dossard (lecture, droit à l'image, accès par code, zip, envoi)."""
import io
import zipfile

import pytest

from noyau.photos import regles as R


def _jpeg(couleur=(200, 30, 30), taille=(640, 480), exif_date=None):
    from PIL import Image
    im = Image.new("RGB", taille, couleur)
    out = io.BytesIO()
    if exif_date:
        ex = Image.Exif()
        ex[306] = exif_date
        im.save(out, "JPEG", exif=ex)
    else:
        im.save(out, "JPEG")
    return out.getvalue()


def test_regles():
    assert R.numeros("N°312 et 57.") == [312, 57] and R.numeros("123456") == []
    connus = {8, 57, 312, 1234}
    a = R.analyser_lecture([("TRAIL DES DENTELLES", 0.9), ("312", 0.74), ("57", 0.66)], connus)
    assert a["dossards"] == {57: 0.66, 312: 0.74} and a["statut"] == "lue"
    assert R.analyser_lecture([("31", 0.8), ("312", 0.8)], connus)["dossards"] == {312: 0.8}     # morceau ignoré
    assert R.analyser_lecture([("312", 0.4)], connus)["statut"] == "a_verifier"                  # lecture hésitante
    assert R.analyser_lecture([("999", 0.9)], connus)["statut"] == "a_verifier"                  # ressemble à un dossard
    assert R.analyser_lecture([("2026", 0.9), ("312", 0.9)], connus)["statut"] == "a_verifier"
    assert R.analyser_lecture([("TRAIL", 0.9)], connus)["statut"] == "sans_dossard"
    assert R.lire_dossards_saisis("57, 312 ; 57") == [57, 312]
    c = R.nouveau_code()
    assert len(c) == 6 and not set(c) & set("01OIL")
    assert R.normaliser_code(" abc 1o9 ") == R.normaliser_code("ABCIO9")
    ok = {"droit_image": 1, "date_naissance": "1980-01-01"}
    assert R.peut_diffuser(ok, "2026-10-12") == (True, "")
    assert R.peut_diffuser({"droit_image": 0}, "2026-10-12")[0] is False
    assert R.peut_diffuser({}, "2026-10-12", image_personne=True)[0] is True                      # accord sur la fiche
    mineur = {"droit_image": 1, "date_naissance": "2012-05-01"}
    assert R.peut_diffuser(mineur, "2026-10-12") == (False, "mineur sans autorisation parentale")
    assert R.peut_diffuser({**mineur, "autorisation_parentale": 1}, "2026-10-12")[0]
    dr = {1: (True, ""), 2: (False, "x")}
    assert R.photo_diffusable([1], dr) and not R.photo_diffusable([1, 2], dr) and not R.photo_diffusable([], dr)
    assert not R.photo_diffusable([3], dr)
    assert R.nom_zip(12, "Léa", "Fauré") == "12_Lea_Faure.zip"
    assert R.lien_direct("https://www.dropbox.com/scl/fi/abc/photos.zip?rlkey=x&dl=0")[0] == \
        "https://www.dropbox.com/scl/fi/abc/photos.zip?rlkey=x&dl=1"
    assert R.lien_direct("https://drive.google.com/file/d/AbC_1/view?usp=sharing")[0] == \
        "https://drive.google.com/uc?export=download&id=AbC_1"
    assert R.lien_direct("https://we.tl/t-xyz")[0] is None and R.lien_direct("ftp://x")[0] is None
    o, t = R.texte_courriel({"nom": "Trail des Dentelles"}, {"prenom": "Léa", "nom": "FAURE", "dossard": 12}, "ABC234", 3,
                            "https://club.example/photos/u")
    assert "Tes photos" in o and "ABC234" in t and "dossard 12" in t


def _course():
    from noyau.donnees import organisation as dor
    ev = dor.enregistrer_evenement({"nom": "Trail des Dentelles 2026", "date_debut": "2026-10-12"})
    e = dor.enregistrer_epreuve(ev, {"nom": "22 km", "distance_km": 22, "dossard_debut": 101, "dossard_fin": 500})
    ids = {}
    for nom, dn, droit, aut in (("ADULTE", "1980-01-01", 1, 0), ("REFUS", "1985-01-01", 0, 0), ("JEUNE", "2011-03-01", 1, 0),
                                ("JEUNEOK", "2011-03-01", 1, 1)):
        ids[nom] = dor.enregistrer_inscription({"epreuve_id": e, "nom": nom, "prenom": "A", "sexe": "M", "date_naissance": dn,
                                                "statut": "validee", "droit_image": droit, "autorisation_parentale": aut,
                                                "email": f"{nom.lower()}@ex.org"})
    dor.attribuer_dossards(ev)
    doss = {i["nom"]: i["dossard"] for i in dor.inscriptions(ev)}
    return ev, ids, doss


def test_base(base_vide):
    from noyau.donnees import photos as dph
    ev, ids, doss = _course()
    a, r, j, jo = doss["ADULTE"], doss["REFUS"], doss["JEUNE"], doss["JEUNEOK"]
    p1 = dph.importer_contenu(ev, "IMG_1.jpg", _jpeg(exif_date="2026:10:12 09:31:05"), lectures=[(str(a), 0.8)])
    assert p1["nouvelle"] and dph.importer_contenu(ev, "copie.jpg", _jpeg(exif_date="2026:10:12 09:31:05"))["nouvelle"] is False
    ph = dph.photo(p1["id"])
    assert ph["dossards"] == [a] and ph["statut"] == "lue" and ph["prise_le"] == "2026-10-12T09:31:05"
    assert (dph.racine() / ph["fichier"]).exists() and ph["largeur"] == 640
    p2 = dph.importer_contenu(ev, "IMG_2.jpg", _jpeg((0, 90, 0)), lectures=[(f"{a} {r}", 0.9)])["id"]   # avec un refus
    p3 = dph.importer_contenu(ev, "IMG_3.jpg", _jpeg((0, 0, 90)), lectures=[(str(j), 0.9)])["id"]       # mineur sans accord
    p4 = dph.importer_contenu(ev, "IMG_4.jpg", _jpeg((90, 90, 0)), lectures=[("999", 0.9)])["id"]       # à vérifier
    p5 = dph.importer_contenu(ev, "IMG_5.jpg", _jpeg((9, 9, 9)))["id"]
    assert dph.a_lire(ev) == [p5] and dph.photo(p4)["statut"] == "a_verifier"
    with pytest.raises(dph.ErreurPhotos):
        dph.definir_dossards(p4, "999")
    assert dph.definir_dossards(p4, f"{jo}, {a}") == sorted([jo, a]) and dph.photo(p4)["statut"] == "verifiee"
    dph.enregistrer_lecture(p4, [("1", 0.9)])                                  # ta correction garde le dernier mot
    assert dph.photo(p4)["dossards"] == sorted([jo, a])
    with pytest.raises(dph.ErreurPhotos):
        dph.importer_contenu(ev, "notes.txt", b"x")
    d = dph.diffusion(ev)
    par = {c["nom"]: c for c in d["coureurs"]}
    assert par["ADULTE"]["nb_photos"] == 3 and par["ADULTE"]["nb_diffusables"] == 2          # p1 et p4 ; p2 retenue
    assert not par["REFUS"]["diffusable"] and par["JEUNE"]["raison"] == "mineur sans autorisation parentale"
    assert par["JEUNEOK"]["nb_diffusables"] == 1 and d["retenues"] == 2                      # p2 et p3
    assert dph.generer_codes(ev) == 4 and dph.generer_codes(ev) == 0
    code = dph.diffusion(ev)["coureurs"][0]["code"]
    assert dph.acces_public("x", a, code) is None                                            # page pas ouverte
    dph.ouvrir_photos(ev, True, "Le Trail Club")
    uuid = dph._ev(ev)["uuid"]
    adulte = next(c for c in dph.diffusion(ev)["coureurs"] if c["nom"] == "ADULTE")
    acc = dph.acces_public(uuid, adulte["dossard"], adulte["code"].lower())
    assert acc and [p["id"] for p in acc["photos"]] == [p1["id"], p4]
    assert dph.acces_public(uuid, adulte["dossard"], "AAAAAA") is None and dph.acces_public(uuid, "abc", "x") is None
    z = zipfile.ZipFile(io.BytesIO(dph.zip_coureur(adulte["inscription_id"])))
    assert z.namelist() == ["photo_001.jpg", "photo_002.jpg"]
    assert dph.image(p1["id"], "vignette")[:2] == b"\xff\xd8"
    dph.masquer(p1["id"])
    assert [p["id"] for p in dph.photos_du_coureur(adulte["inscription_id"])] == [p4]
    assert len(dph.photos(ev, statut="masquees")) == 1
    dph.noter_envoi(adulte["inscription_id"], "email")
    assert next(c for c in dph.diffusion(ev)["coureurs"] if c["nom"] == "ADULTE")["envoye_le"]
    t = dph.tableau(ev)
    assert t["ouvertes"] and t["sans_accord"] == 2 and t["photos"] == 4
    dph.supprimer_photo(p5)
    assert dph.photo(p5) is None
    # zip importé
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as zz:
        zz.writestr("course/A.jpg", _jpeg((1, 2, 3)))
        zz.writestr("course/A_copie.jpg", _jpeg((1, 2, 3)))
        zz.writestr("__MACOSX/._A.jpg", b"x")
        zz.writestr("lisez-moi.txt", b"x")
    r_ = dph.importer_zip(ev, out.getvalue(), lire=lambda chemin: [(str(r), 0.9)])
    assert r_ == {"importees": 1, "deja": 1, "erreurs": []}


def test_profil_et_courriel(base_vide, monkeypatch):
    from noyau.donnees import photos as dph, organisation as dor, personnes as dper
    from noyau.photos import courriel as C
    ev, ids, doss = _course()
    pid = dper.creer({"nom": "ADULTE", "prenom": "A"}, ["licencie"])
    dor.enregistrer_inscription({"personne_id": pid}, ids["ADULTE"])
    dph.importer_contenu(ev, "a.jpg", _jpeg(), lectures=[(str(doss["ADULTE"]), 0.9)])
    assert len(dph.photos_de_la_personne(pid)) == 1
    m = C.message("club@ex.org", "Trail Club", "a@ex.org", "Tes photos", "Bonjour", [("p.jpg", b"\xff\xd8x")])
    assert m["To"] == "a@ex.org" and m.get_content_type() == "multipart/mixed"
    assert C.message("c@ex.org", "", "a@ex.org", "o", "t", [("p.jpg", b"x" * (C.TAILLE_MAX_PIECES + 1))]).get_content_type() \
        == "text/plain"
    with pytest.raises(C.ErreurCourriel):
        C.connexion({}, None)


def test_lecture_automatique(base_vide):
    from noyau.photos import lecture
    if not lecture.disponible():
        pytest.skip("lecture automatique non installée")
    from PIL import Image, ImageDraw, ImageFont
    from noyau.donnees import photos as dph
    ev, ids, doss = _course()
    im = Image.new("RGB", (1600, 1000), (70, 110, 60))
    d = ImageDraw.Draw(im)
    d.rectangle((300, 300, 800, 650), fill="white")
    try:
        f = ImageFont.truetype("DejaVuSans-Bold.ttf", 160)
    except OSError:
        pytest.skip("police indisponible")
    d.text((340, 380), str(doss["ADULTE"]), fill="black", font=f)
    out = io.BytesIO()
    im.save(out, "JPEG")
    p = dph.importer_contenu(ev, "a.jpg", out.getvalue())["id"]
    dph.lire_sur_place(p)
    assert dph.photo(p)["dossards"] == [doss["ADULTE"]]


def _https(port, verbe, chemin, corps=None, cookie=None, type_="application/x-www-form-urlencoded"):
    import http.client
    import ssl
    from urllib.parse import urlencode
    c = http.client.HTTPSConnection("127.0.0.1", port, context=ssl._create_unverified_context(), timeout=20)
    e = {"Content-Type": type_}
    if cookie:
        e["Cookie"] = cookie
    if isinstance(corps, dict):
        corps = urlencode(corps)
    c.request(verbe, chemin, body=corps, headers=e)
    r = c.getresponse()
    return r.status, r.getheader("Set-Cookie"), r.getheader("Content-Type"), r.read()


def test_serveur(base_vide, tmp_path):
    import re
    from noyau.serveur import serveur as S
    from noyau.donnees import photos as dph, comptes as dco
    ev, ids, doss = _course()
    cid, _ = dco.creer_compte("photographe", mot_de_passe="Ventoux-2026")
    dco.ajouter_role(cid, "benevole", None, ev)
    info = S.demarrer(0, True, "127.0.0.1", tmp_path / "certs")
    port = info["port"]
    try:
        s, ck, _t, _b = _https(port, "POST", "/m/connexion", {"identifiant": "photographe", "mot_de_passe": "Ventoux-2026"})
        cookie = ck.split(";")[0]
        s, _c, _t, page = _https(port, "GET", f"/m/photos?ev={ev}", cookie=cookie)
        assert s == 200 and b"multipart/form-data" in page
        csrf = re.search(rb"name='csrf' value='([0-9a-f]+)'", page).group(1).decode()
        limite = "----trailhub"
        corps = (f"--{limite}\r\nContent-Disposition: form-data; name=\"csrf\"\r\n\r\n{csrf}\r\n"
                 f"--{limite}\r\nContent-Disposition: form-data; name=\"photographe\"\r\n\r\nMarc\r\n"
                 f"--{limite}\r\nContent-Disposition: form-data; name=\"photos\"; filename=\"IMG_9.jpg\"\r\n"
                 f"Content-Type: image/jpeg\r\n\r\n").encode() + _jpeg((5, 50, 5)) + f"\r\n--{limite}--\r\n".encode()
        s, _c, _t, page = _https(port, "POST", f"/m/photos?ev={ev}", corps, cookie, f"multipart/form-data; boundary={limite}")
        assert s == 200 and "1 photo(s) reçue(s)".encode() in page
        p = dph.photos(ev)[0]
        assert p["photographe"] == "Marc" and p["source"] == "telephone"
        dph.definir_dossards(p["id"], [doss["ADULTE"]])
        # page publique : fermée, puis ouverte
        uuid = dph._ev(ev)["uuid"]
        assert _https(port, "GET", f"/photos/{uuid}")[0] == 404
        dph.ouvrir_photos(ev, True)
        adulte = next(c for c in dph.diffusion(ev)["coureurs"] if c["nom"] == "ADULTE")
        s, _c, _t, page = _https(port, "POST", f"/photos/{uuid}", {"dossard": adulte["dossard"], "code": "ZZZZZZ"})
        assert "incorrect" in page.decode()
        s, _c, _t, page = _https(port, "POST", f"/photos/{uuid}", {"dossard": adulte["dossard"], "code": adulte["code"]})
        liens = re.findall(rb"src='(/photos/[^']+)'", page)
        assert s == 200 and len(liens) == 1
        s, _c, typ, img = _https(port, "GET", liens[0].decode().replace("&amp;", "&"))
        assert s == 200 and typ == "image/jpeg" and img[:2] == b"\xff\xd8"
        dph.masquer(p["id"])
        assert _https(port, "GET", liens[0].decode().replace("&amp;", "&"))[0] == 404
        assert _https(port, "GET", f"/photos/{uuid}/i/faux.jeton")[0] == 403
    finally:
        S.arreter()


def test_fenetre(base_vide):
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    from noyau.donnees import photos as dph
    ev, ids, doss = _course()
    p1 = dph.importer_contenu(ev, "a.jpg", _jpeg(), lectures=[("999", 0.9)])["id"]
    dph.importer_contenu(ev, "b.jpg", _jpeg((1, 1, 1)), lectures=[(str(doss["ADULTE"]), 0.9)])
    from interface.organisation import OrganisationFenetre
    f = OrganisationFenetre(1)
    ph = f.photos
    f.tabs.setCurrentWidget(ph)
    ph.rafraichir()
    assert ph.galerie.count() == 1 and ph.c_verif.valeur.text() == "1"              # filtre « à vérifier »
    ph.saisie.setText(str(doss["JEUNEOK"]))
    ph._enregistrer_saisie()
    assert ph.galerie.count() == 0 and dph.photo(p1)["dossards"] == [doss["JEUNEOK"]]
    ph.filtre.setCurrentIndex(ph.filtre.findData(None))
    assert ph.galerie.count() == 2 and ph.table.rowCount() == 4
    from interface.organisation_photos import DialoguePhotos
    DialoguePhotos(ph, "x", [p1]).close()
