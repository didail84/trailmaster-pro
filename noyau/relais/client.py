"""
Client Relais (étape 8), sans Qt : où chercher la mise à jour, laquelle
convient à cet ordinateur, téléchargement vérifié et façon de l'installer.

Ordre de recherche : le Relais du club (adresse du NAS, Réglages), puis la
dernière version publiée sur GitHub (son fichier relais.json). Réseau
absent : rien ne se passe, le logiciel continue normalement.
"""

import json
import os
import platform
import shutil
import sys
import urllib.error
import urllib.request
from pathlib import Path

from noyau.relais import manifeste as M

DEPOT = "didail84/trailmaster-pro"
URL_GITHUB = f"https://api.github.com/repos/{DEPOT}/releases"
AGENT = "TrailHubCenter-Relais/1"
DELAI = 6


def version_installee():
    """Numéro du fichier VERSION livré avec le logiciel (0 si illisible)."""
    import re
    racine = Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent)) if getattr(sys, "frozen", False) \
        else Path(__file__).resolve().parents[2]
    try:
        return int(re.sub(r"[^0-9]", "", (racine / "VERSION").read_text(encoding="utf-8")) or "0")
    except (OSError, ValueError):
        return 0


def reglages():
    """(canal, adresse du Relais du club) choisis dans Réglages."""
    try:
        from data.database import obtenir_parametre
        return obtenir_parametre("relais_canal") or "stable", (obtenir_parametre("relais_url") or "").strip() or None
    except Exception:
        return "stable", None


def plateforme():
    machine = platform.machine().lower()
    arch = "arm64" if machine in ("arm64", "aarch64") else "x64"
    os_ = {"win32": "windows", "darwin": "mac"}.get(sys.platform, "linux")
    return f"{os_}-{arch}"


def installation():
    """Comment ce logiciel a été installé : « appimage », « deb », « installateur », « dmg », « portable » ou
    « sources » (lancé avec python main.py)."""
    if not getattr(sys, "frozen", False):
        return "sources"
    if os.environ.get("APPIMAGE"):
        return "appimage"
    exe = Path(sys.executable).resolve()
    if sys.platform == "darwin":
        return "dmg"
    if sys.platform == "win32":
        return "portable" if (exe.parent / "Donnees").exists() else "installateur"
    if str(exe).startswith("/opt/"):
        return "deb"
    return "archive"


def types_preferes():
    i = installation()
    ordre = {"appimage": ["appimage"], "deb": ["deb", "appimage"], "archive": ["archive", "appimage"],
             "installateur": ["installateur"], "portable": ["portable", "installateur"], "dmg": ["dmg"],
             "sources": []}
    return ordre.get(i, [])


def _lire_json(url, delai=DELAI):
    req = urllib.request.Request(url, headers={"User-Agent": AGENT, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=delai) as r:
        return json.loads(r.read(2_000_000).decode("utf-8"))


def manifeste_github(canal="stable"):
    """Le relais.json de la dernière version GitHub (les versions « pre-release » = canal test)."""
    versions = _lire_json(URL_GITHUB + "?per_page=10")
    for v in versions if isinstance(versions, list) else []:
        if v.get("draft") or (v.get("prerelease") and canal != "test"):
            continue
        a = next((x for x in v.get("assets") or [] if x.get("name") == "relais.json"), None)
        if a:
            return _lire_json(a["browser_download_url"])
        return None
    return None


def chercher(version_locale, canal="stable", url_nas=None):
    """{a_jour, version, notes, fichier, signe, source, canal} d'après le premier manifeste trouvé, ou None si aucun
    (réseau absent, versions publiées avant Relais). Lève M.ErreurRelais si un manifeste est refusé."""
    sources = []
    if url_nas:
        sources.append(("NAS du club", lambda: _lire_json(f"{url_nas.rstrip('/')}/{M.LOGICIEL}/{canal}/relais.json")))
    sources.append(("GitHub", lambda: manifeste_github(canal)))
    for nom, lire in sources:
        try:
            m = lire()
        except (urllib.error.URLError, OSError, ValueError, TimeoutError):
            continue
        if not m:
            continue
        v = M.valider(m)
        man = v["manifeste"]
        f = M.fichier_pour(man, plateforme(), types_preferes())
        if f and nom == "NAS du club":                   # le fichier est d'abord pris sur le NAS (même empreinte)
            f = {**f, "miroir": f"{url_nas.rstrip('/')}/{M.LOGICIEL}/{canal}/{f['nom']}"}
        return {"a_jour": M.numero(man["version"]) <= M.numero(version_locale), "version": man["version"],
                "notes": man.get("notes") or "", "fichier": f, "signe": v["signe"],
                "source": nom, "canal": man.get("canal"), "manifeste": man}
    return None


def telecharger(fichier, dossier=None, progression=None):
    """Télécharge le fichier et vérifie son empreinte ; un fichier abîmé ou modifié est effacé. Renvoie le chemin."""
    dossier = Path(dossier or Path.home() / "Downloads")
    dossier.mkdir(parents=True, exist_ok=True)
    cible = dossier / fichier["nom"]
    partiel = cible.with_name(cible.name + ".partiel")
    adresses = [u for u in (fichier.get("miroir"), fichier["url"]) if u]
    for k, url in enumerate(adresses):
        req = urllib.request.Request(url, headers={"User-Agent": AGENT})
        n = 0
        try:
            with urllib.request.urlopen(req, timeout=60) as r, open(partiel, "wb") as out:
                while True:
                    b = r.read(1 << 20)
                    if not b:
                        break
                    out.write(b)
                    n += len(b)
                    if progression:
                        progression(n, fichier.get("taille") or 0)
            break
        except (urllib.error.URLError, OSError):
            if k == len(adresses) - 1:
                raise
    if M.empreinte(partiel) != fichier["sha256"]:
        partiel.unlink(missing_ok=True)
        raise M.ErreurRelais("Le fichier téléchargé ne correspond pas à son empreinte : effacé, rien n'est installé.")
    partiel.replace(cible)
    return cible


def plan_installation(chemin):
    """Ce qu'il faut faire du fichier téléchargé : (action, détail) ; action parmi « remplacer_appimage »,
    « lancer », « ouvrir », « dossier »."""
    t = installation()
    p = Path(chemin)
    if t == "appimage" and p.name.endswith(".AppImage"):
        return "remplacer_appimage", os.environ["APPIMAGE"]
    if sys.platform == "win32" and p.suffix == ".exe":
        return "lancer", [str(p), "/SILENT", "/CLOSEAPPLICATIONS"]
    if p.suffix in (".dmg", ".deb"):
        return "ouvrir", str(p)
    return "dossier", str(p.parent)


def remplacer_appimage(nouvelle, actuelle):
    """Met la nouvelle AppImage à la place de l'actuelle et garde l'ancienne à côté (retour arrière possible)."""
    actuelle, nouvelle = Path(actuelle), Path(nouvelle)
    ancienne = actuelle.with_name(actuelle.name + ".ancienne")
    tmp = actuelle.with_name(actuelle.name + ".nouvelle")
    shutil.copy2(nouvelle, tmp)
    os.chmod(tmp, 0o755)
    if actuelle.exists():
        shutil.copy2(actuelle, ancienne)
    os.replace(tmp, actuelle)
    return ancienne


def revenir_en_arriere():
    """Remet l'AppImage précédente (gardée lors de la dernière mise à jour). Renvoie True si fait."""
    a = os.environ.get("APPIMAGE")
    if not a:
        return False
    ancienne = Path(a + ".ancienne")
    if not ancienne.exists():
        return False
    os.replace(ancienne, a)
    return True


def miroir(etiquette, dossier, canal="stable"):
    """Copie une version publiée sur GitHub (relais.json et installateurs) dans le dossier Relais du NAS :
    <dossier>/trail-hub-center/<canal>/. Le manifeste reste celui signé ; les postes du club téléchargent ensuite
    sur le réseau local. Renvoie la liste des fichiers copiés."""
    versions = _lire_json(URL_GITHUB + "?per_page=20", 20)
    v = next((x for x in versions if x.get("tag_name") == etiquette), None)
    if not v:
        raise M.ErreurRelais(f"Version {etiquette} introuvable sur GitHub.")
    a = next((x for x in v.get("assets") or [] if x.get("name") == "relais.json"), None)
    if not a:
        raise M.ErreurRelais("Cette version n'a pas de relais.json (publiée avant Relais).")
    m = M.valider(_lire_json(a["browser_download_url"], 30))["manifeste"]
    cible = Path(dossier) / M.LOGICIEL / canal
    cible.mkdir(parents=True, exist_ok=True)
    copies = []
    for f in m["fichiers"]:
        telecharger(f, cible)
        copies.append(f["nom"])
    (cible / "relais.json").write_text(json.dumps(m, ensure_ascii=False, indent=1), encoding="utf-8")
    return copies
