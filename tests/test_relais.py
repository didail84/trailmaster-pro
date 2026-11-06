"""Étape 8 : mises à jour par Relais (manifeste signé, empreinte, choix du fichier, installation)."""
import json

import pytest

from noyau.relais import manifeste as M, client as RC


def _cles():
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    k = Ed25519PrivateKey.generate()
    return (k.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()),
            k.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo))


def test_manifeste(tmp_path):
    priv, pub = _cles()
    for nom in ("TrailMasterPro-109-linux-x64.AppImage", "TrailMasterPro-109-linux-amd64.deb",
                "TrailMasterPro-109-windows-x64.exe", "TrailMasterPro-109-windows-portable.zip",
                "TrailMasterPro-109-mac-arm64.dmg", "lisez-moi.txt"):
        (tmp_path / nom).write_bytes(nom.encode())
    fs = [M.decrire_fichier(p, "https://github.com/x/releases/download/V109") for p in sorted(tmp_path.iterdir())]
    fs = [f for f in fs if f]
    assert len(fs) == 5 and {f["plateforme"] for f in fs} == {"linux-x64", "windows-x64", "mac-arm64"}
    m = M.construire("109", fs, notes="Photos par dossard")
    with pytest.raises(M.ErreurRelais, match="non signé"):
        M.valider(m, pub)
    assert M.valider(m, b"")["signe"] is False                       # pas de clé livrée : accepté, non signé
    s = M.signer(m, priv)
    assert M.valider(s, pub)["signe"] is True
    triche = json.loads(json.dumps(s))
    triche["fichiers"][0]["url"] = "https://pirate.example/x"
    with pytest.raises(M.ErreurRelais, match="invalide"):
        M.valider(triche, pub)
    with pytest.raises(M.ErreurRelais):
        M.valider({**s, "logiciel": "autre"}, pub)
    with pytest.raises(M.ErreurRelais):
        M.valider({"format": "x"}, pub)
    assert M.fichier_pour(s, "linux-x64", ["deb", "appimage"])["type"] == "deb"
    assert M.fichier_pour(s, "linux-x64", ["appimage"])["type"] == "appimage"
    assert M.fichier_pour(s, "mac-x64", ["dmg"]) is None
    assert M.numero("V109") > M.numero("108") and M.numero("1.10") > M.numero("1.9")


def test_client(tmp_path, monkeypatch):
    priv, pub = _cles()
    monkeypatch.setattr(M, "cle_publique", lambda: pub)
    fichier = tmp_path / "TrailMasterPro-109-linux-x64.AppImage"
    fichier.write_bytes(b"nouvelle version")
    f = M.decrire_fichier(fichier, "https://exemple.org/v")
    man = M.signer(M.construire("109", [f], notes="Nouveautés"), priv)
    lus = []

    def faux_json(url, delai=6):
        lus.append(url)
        if "nas" in url:
            raise OSError("NAS éteint")
        return man
    monkeypatch.setattr(RC, "_lire_json", faux_json)
    monkeypatch.setattr(RC, "manifeste_github", lambda canal="stable": faux_json("github"))
    monkeypatch.setattr(RC, "plateforme", lambda: "linux-x64")
    monkeypatch.setattr(RC, "installation", lambda: "appimage")
    r = RC.chercher("108", "stable", "https://nas.local:8780")
    assert lus[0] == "https://nas.local:8780/trail-hub-center/stable/relais.json" and r["source"] == "GitHub"
    assert not r["a_jour"] and r["signe"] and r["fichier"]["type"] == "appimage"
    assert RC.chercher("109")["a_jour"]
    # téléchargement vérifié
    import io
    import urllib.request

    class Rep(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False
    monkeypatch.setattr(urllib.request, "urlopen", lambda req, timeout=60: Rep(b"nouvelle version"))
    dl = RC.telecharger(r["fichier"], tmp_path / "dl")
    assert dl.read_bytes() == b"nouvelle version"
    monkeypatch.setattr(urllib.request, "urlopen", lambda req, timeout=60: Rep(b"version piratee"))
    with pytest.raises(M.ErreurRelais, match="empreinte"):
        RC.telecharger(r["fichier"], tmp_path / "dl2")
    assert not list((tmp_path / "dl2").iterdir())
    # remplacement de l'AppImage et retour arrière
    actuelle = tmp_path / "Trail.AppImage"
    actuelle.write_bytes(b"ancienne")
    monkeypatch.setenv("APPIMAGE", str(actuelle))
    assert RC.plan_installation(dl)[0] == "remplacer_appimage"
    RC.remplacer_appimage(dl, actuelle)
    assert actuelle.read_bytes() == b"nouvelle version" and RC.revenir_en_arriere() and actuelle.read_bytes() == b"ancienne"
    # signature fausse : refus
    monkeypatch.setattr(RC, "manifeste_github", lambda canal="stable": {**man, "version": "999"})
    with pytest.raises(M.ErreurRelais):
        RC.chercher("108")


def test_verification_maj(monkeypatch, base_vide):
    from interface import verification_maj as V
    monkeypatch.setattr(V, "version_locale", lambda: 108)
    monkeypatch.setattr(RC, "chercher", lambda v, c, u: {"a_jour": False, "version": "109", "notes": "n", "fichier": None,
                                                        "signe": True, "source": "GitHub", "canal": "stable"})
    r = V.verifier_mise_a_jour()
    assert r["version"] == "109" and r["source"] == "GitHub"
    monkeypatch.setattr(RC, "chercher", lambda v, c, u: {"a_jour": True})
    assert V.verifier_mise_a_jour() is None
    monkeypatch.setattr(RC, "chercher", lambda v, c, u: None)
    monkeypatch.setattr(V, "verifier_mise_a_jour_github", lambda: "ancien")
    assert V.verifier_mise_a_jour() == "ancien"


def test_script_manifeste(tmp_path, monkeypatch):
    import subprocess
    import sys
    from pathlib import Path
    (tmp_path / "TrailMasterPro-109-linux-x64.tar.gz").write_bytes(b"x")
    racine = Path(__file__).resolve().parent.parent
    priv, _pub = _cles()
    env = dict(__import__("os").environ, RELAIS_CLE_PRIVEE=priv.decode(), HOME=str(tmp_path))
    r = subprocess.run([sys.executable, str(racine / "packaging" / "relais_manifeste.py"), str(tmp_path), "V109"],
                       capture_output=True, text=True, env=env)
    assert r.returncode == 0, r.stderr
    m = json.loads((tmp_path / "relais.json").read_text())
    assert m["version"] == "109" and m["signature"] and m["fichiers"][0]["type"] == "archive"


def test_relais_du_nas(base_vide, tmp_path):
    import http.client
    import ssl
    from pathlib import Path
    import data.database as db
    from noyau.serveur import serveur as S
    d = Path(db.CHEMIN_BDD).parent / "relais" / "trail-hub-center" / "stable"
    d.mkdir(parents=True)
    (d / "relais.json").write_text('{"format": "relais/1"}')
    info = S.demarrer(0, True, "127.0.0.1", tmp_path / "certs")
    try:
        def get(ch):
            c = http.client.HTTPSConnection("127.0.0.1", info["port"], context=ssl._create_unverified_context(), timeout=10)
            c.request("GET", ch)
            r = c.getresponse()
            return r.status, r.read()
        assert get("/relais/trail-hub-center/stable/relais.json") == (200, b'{"format": "relais/1"}')
        assert get("/relais/../trail_hub.db")[0] == 404 and get("/relais/%2e%2e/x")[0] == 404
    finally:
        S.arreter()
