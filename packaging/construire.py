"""
Fabrique l'application installable de TrailMaster Pro, sur l'ordinateur
où ce script tourne :

  - Windows : dist/TrailMasterPro-<version>-windows-x64.exe (installateur)
  - Mac     : dist/TrailMasterPro-<version>-mac-<x64|arm64>.dmg

Utilisé par GitHub (.github/workflows/installateurs.yml) pour chaque
nouvelle version ; on peut aussi le lancer à la main :

    pip install -r requirements.txt pyinstaller pillow
    python packaging/construire.py

Ne met JAMAIS de base de données dans l'application : les données de
chacun restent dans son dossier personnel (Application Support sur Mac,
%APPDATA% sous Windows).
"""

import os
import platform
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
NOM = "TrailMaster Pro"
SEP = ";" if sys.platform == "win32" else ":"


def lancer(*commande):
    print("→", " ".join(str(c) for c in commande), flush=True)
    subprocess.run([str(c) for c in commande], check=True, cwd=RACINE)


def version():
    return (RACINE / "VERSION").read_text(encoding="utf-8").strip()


def architecture():
    machine = platform.machine().lower()
    return "arm64" if machine in ("arm64", "aarch64") else "x64"


def pyinstaller():
    # Numéro de fabrication affiché en bas de l'écran Réglages
    assets = RACINE / "interface" / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    build_id = os.environ.get("BUILD_ID") or datetime.now(timezone.utc).strftime("%Y%m%d-%H%M")
    (assets / "version_build.txt").write_text(build_id, encoding="utf-8")

    for dossier in ("build", "dist"):
        shutil.rmtree(RACINE / dossier, ignore_errors=True)

    keyring = "keyring.backends.Windows" if sys.platform == "win32" else "keyring.backends.macOS"
    commande = [
        sys.executable, "-m", "PyInstaller",
        "--windowed", "--noconfirm", "--log-level", "WARN",
        "--name", NOM,
        "--icon", "packaging/icone.png",
        "--add-data", f"interface/assets{SEP}interface/assets",
        "--add-data", f"interface/modele_suivi_telephone.html{SEP}interface",
        "--add-data", f"ressources{SEP}ressources",
        "--add-data", f"VERSION{SEP}.",
        "--hidden-import", "PySide6.QtWebEngineWidgets",
        "--hidden-import", "PySide6.QtWebEngineCore",
        "--hidden-import", "PySide6.QtWebChannel",
        "--hidden-import", keyring,
        "--collect-all", "PySide6",
        "--collect-all", "garminconnect",
        "--collect-all", "curl_cffi",
        "--collect-all", "ua_generator",
        "--collect-all", "certifi",
    ]
    if sys.platform == "darwin":
        commande += ["--osx-bundle-identifier", "io.github.didail84.trailmasterpro"]
    commande.append("main.py")
    lancer(*commande)


def dmg():
    app = RACINE / "dist" / f"{NOM}.app"
    plist = app / "Contents" / "Info.plist"
    # Version lisible dans « Lire les informations » + accès réseau local
    lancer("/usr/libexec/PlistBuddy", "-c", f"Set :CFBundleShortVersionString {version()}", plist)
    lancer("/usr/libexec/PlistBuddy", "-c", "Add :LSMinimumSystemVersion string 12.0", plist)
    lancer("codesign", "--force", "--deep", "--sign", "-", app)

    dossier = RACINE / "dist" / "dmg"
    shutil.rmtree(dossier, ignore_errors=True)
    dossier.mkdir()
    lancer("ditto", app, dossier / f"{NOM}.app")
    (dossier / "Applications").symlink_to("/Applications")
    sortie = RACINE / "dist" / f"TrailMasterPro-{version()}-mac-{architecture()}.dmg"
    lancer("hdiutil", "create", "-volname", f"{NOM} {version()}", "-srcfolder", dossier,
           "-fs", "HFS+", "-format", "UDZO", "-ov", sortie)
    print("Installateur Mac :", sortie)


def installateur_windows():
    from PIL import Image
    (RACINE / "build").mkdir(exist_ok=True)
    Image.open(RACINE / "packaging" / "icone.png").save(
        RACINE / "build" / "icone.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    iscc = shutil.which("iscc") or r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
    lancer(iscc, f"/DVersionApp={version()}", "packaging/windows.iss")
    print("Installateur Windows :", RACINE / "dist" / f"TrailMasterPro-{version()}-windows-x64.exe")


if __name__ == "__main__":
    pyinstaller()
    if sys.platform == "darwin":
        dmg()
    elif sys.platform == "win32":
        installateur_windows()
