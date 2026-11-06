"""
Fabrique l'application installable de TrailMaster Pro, sur l'ordinateur
où ce script tourne :

  - Windows : dist/TrailMasterPro-<version>-windows-x64.exe (installateur)
  - Mac     : dist/TrailMasterPro-<version>-mac-<x64|arm64>.dmg
  - Linux   : dist/TrailMasterPro-<version>-linux-<x64|arm64>.AppImage (un seul fichier, toutes distributions),
              .deb (Ubuntu, Debian, Mint) et .tar.gz (à décompresser n'importe où)

Utilisé par GitHub (.github/workflows/installateurs.yml) pour chaque
nouvelle version ; on peut aussi le lancer à la main :

    pip install -r requirements.txt pyinstaller pillow
    python packaging/construire.py

Ne met JAMAIS de base de données dans l'application : les données de
chacun restent dans son dossier personnel (Application Support sur Mac,
%APPDATA% sous Windows, ~/.local/share sous Linux).
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
    print(">", " ".join(str(c) for c in commande), flush=True)
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

    keyring = {"win32": "keyring.backends.Windows", "darwin": "keyring.backends.macOS"}.get(
        sys.platform, "keyring.backends.SecretService")          # Linux : trousseau GNOME ou KDE
    commande = [
        sys.executable, "-m", "PyInstaller",
        "--windowed", "--noconfirm", "--log-level", "WARN",
        "--name", NOM,
        "--icon", "packaging/icone.png",
        "--add-data", f"interface/assets{SEP}interface/assets",
        "--add-data", f"interface/modele_suivi_telephone.html{SEP}interface",
        "--add-data", f"ressources{SEP}ressources",
        "--add-data", f"VERSION{SEP}.",
        "--add-data", f"LICENSE{SEP}.",
        "--add-data", f"THIRD_PARTY_NOTICES.md{SEP}.",
        "--add-data", f"noyau/relais{SEP}noyau/relais",
        "--add-data", f"data/annuaire{SEP}data/annuaire",
        "--add-data", f"data/actualites{SEP}data/actualites",
        "--hidden-import", "PySide6.QtWebEngineWidgets",
        "--hidden-import", "PySide6.QtWebEngineCore",
        "--hidden-import", "PySide6.QtWebChannel",
        "--hidden-import", keyring,
        "--collect-submodules", "noyau",
        "--collect-all", "PySide6",
        "--collect-all", "garminconnect",
        "--collect-all", "curl_cffi",
        "--collect-all", "ua_generator",
        "--collect-all", "certifi",
        "--collect-all", "rapidocr_onnxruntime",
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
    portable_windows()


LISEZ_MOI_PORTABLE = """TrailMaster Pro - version portable (cle USB)
=============================================

Rien a installer : double-clique sur « TrailMaster Pro.exe ».

Tes donnees (base, photos) sont rangees dans le dossier « Donnees »,
juste a cote : elles restent sur la cle et te suivent d'un PC a l'autre.
Ne supprime pas ce dossier et fais-en des copies de temps en temps.

Pour reprendre ta base du Mac : copie le fichier
~/Library/Application Support/TrailMaster Pro/trailmaster.db
dans le dossier « Donnees » de la cle (TrailMaster ferme).

Ferme toujours TrailMaster avant de retirer la cle.

Conseil : dezippe ce fichier sur la cle depuis ton Mac ou ton PC
personnel, puis branche la cle sur l'autre ordinateur.
"""


def portable_windows():
    import zipfile
    source = RACINE / "dist" / NOM
    nom_dossier = f"{NOM} portable"
    sortie = RACINE / "dist" / f"TrailMasterPro-{version()}-windows-portable.zip"
    with zipfile.ZipFile(sortie, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for fichier in sorted(source.rglob("*")):
            if fichier.is_file():
                archive.write(fichier, f"{nom_dossier}/{fichier.relative_to(source).as_posix()}")
        archive.writestr(f"{nom_dossier}/Donnees/", "")
        archive.writestr(f"{nom_dossier}/LISEZ-MOI.txt", LISEZ_MOI_PORTABLE.replace("\n", "\r\n"))
    print("Version portable Windows :", sortie)


# ------------------------------------------------------------------ Linux

ID_LINUX = "trailhub-center"
FICHIER_DESKTOP = """[Desktop Entry]
Type=Application
Name=Trail Hub Center
GenericName=Entraînement, club et organisation de trail
Comment=Entraînement trail, club, organisation de courses
Exec={exec} %F
Icon={icone}
Terminal=false
Categories=Sports;Utility;Education;
Keywords=trail;course;club;chrono;entraînement;
StartupWMClass=TrailMaster Pro
"""


def _dossier_linux():
    return RACINE / "dist" / NOM


def tar_linux():
    import tarfile
    sortie = RACINE / "dist" / f"TrailMasterPro-{version()}-linux-{architecture()}.tar.gz"
    with tarfile.open(sortie, "w:gz") as t:
        t.add(_dossier_linux(), arcname=f"{ID_LINUX}")
    print("Archive Linux :", sortie)
    return sortie


def appimage():
    """AppImage : un seul fichier exécutable. appimagetool est pris dans APPIMAGETOOL ou le PATH ; sans lui, on passe."""
    outil = os.environ.get("APPIMAGETOOL") or shutil.which("appimagetool")
    if not outil:
        print("appimagetool introuvable : pas d'AppImage (l'archive et le .deb suffisent).")
        return None
    appdir = RACINE / "build" / "AppDir"
    shutil.rmtree(appdir, ignore_errors=True)
    (appdir / "usr").mkdir(parents=True)
    shutil.copytree(_dossier_linux(), appdir / "usr" / "lib" / ID_LINUX)
    (appdir / "AppRun").write_text('#!/bin/sh\nICI="$(dirname "$(readlink -f "$0")")"\n'
                                   f'exec "$ICI/usr/lib/{ID_LINUX}/{NOM}" "$@"\n', encoding="utf-8")
    os.chmod(appdir / "AppRun", 0o755)
    (appdir / f"{ID_LINUX}.desktop").write_text(FICHIER_DESKTOP.format(exec="AppRun", icone=ID_LINUX), encoding="utf-8")
    shutil.copy(RACINE / "packaging" / "icone.png", appdir / f"{ID_LINUX}.png")
    shutil.copy(RACINE / "packaging" / "icone.png", appdir / ".DirIcon")
    sortie = RACINE / "dist" / f"TrailMasterPro-{version()}-linux-{architecture()}.AppImage"
    env = dict(os.environ, ARCH="x86_64" if architecture() == "x64" else "aarch64", APPIMAGE_EXTRACT_AND_RUN="1")
    print(">", outil, appdir, sortie, flush=True)
    subprocess.run([outil, "--no-appstream", str(appdir), str(sortie)], check=True, cwd=RACINE, env=env)
    print("AppImage :", sortie)
    return sortie


def deb():
    """Paquet .deb (Ubuntu, Debian, Mint) : installé dans /opt, entrée dans le menu des applications."""
    if not shutil.which("dpkg-deb"):
        print("dpkg-deb introuvable : pas de .deb.")
        return None
    racine = RACINE / "build" / "deb"
    shutil.rmtree(racine, ignore_errors=True)
    opt = racine / "opt" / ID_LINUX
    shutil.copytree(_dossier_linux(), opt)
    (racine / "usr" / "bin").mkdir(parents=True)
    (racine / "usr" / "bin" / ID_LINUX).symlink_to(f"/opt/{ID_LINUX}/{NOM}")
    apps = racine / "usr" / "share" / "applications"
    apps.mkdir(parents=True)
    (apps / f"{ID_LINUX}.desktop").write_text(FICHIER_DESKTOP.format(exec=f"/opt/{ID_LINUX}/{NOM.replace(' ', chr(92) + ' ')}",
                                                                     icone=ID_LINUX), encoding="utf-8")
    ic = racine / "usr" / "share" / "icons" / "hicolor" / "256x256" / "apps"
    ic.mkdir(parents=True)
    from PIL import Image
    Image.open(RACINE / "packaging" / "icone.png").resize((256, 256)).save(ic / f"{ID_LINUX}.png")
    (racine / "DEBIAN").mkdir()
    taille = sum(f.stat().st_size for f in opt.rglob("*") if f.is_file()) // 1024
    arch = "amd64" if architecture() == "x64" else "arm64"
    (racine / "DEBIAN" / "control").write_text(
        f"Package: {ID_LINUX}\nVersion: {version()}\nSection: misc\nPriority: optional\nArchitecture: {arch}\n"
        f"Installed-Size: {taille}\nMaintainer: Didier Beltran <noreply@github.com>\n"
        "Depends: libegl1, libxkbcommon-x11-0, libxcb-cursor0, libnss3, libfontconfig1\n"
        "Recommends: gnome-keyring | kwalletmanager\n"
        "Homepage: https://github.com/didail84/trailmaster-pro\n"
        "Description: Trail Hub Center : entraînement trail, club et organisation de courses\n"
        " Suivi d'entraînement, stratégie de course, gestion du club, organisation et chrono.\n", encoding="utf-8")
    sortie = RACINE / "dist" / f"TrailMasterPro-{version()}-linux-{arch}.deb"
    lancer("dpkg-deb", "--root-owner-group", "--build", racine, sortie)
    print("Paquet .deb :", sortie)
    return sortie


def paquets_linux():
    tar_linux()
    deb()
    appimage()


if __name__ == "__main__":
    pyinstaller()
    if sys.platform == "darwin":
        dmg()
    elif sys.platform == "win32":
        installateur_windows()
    else:
        paquets_linux()
