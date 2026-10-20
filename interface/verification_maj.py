"""
Vérification des mises à jour disponibles sur GitHub, au démarrage du
logiciel.

Fonctionnement :
  1. Au lancement, l'appli compare le numéro de version embarqué
     (fichier VERSION, à la racine du projet) au numéro de la dernière
     "release" publiée sur https://github.com/didail84/trailmaster-pro.
  2. Si une version plus récente existe, une notification discrète
     propose de télécharger automatiquement le nouveau zip dans le
     dossier Téléchargements.
  3. La dernière étape (remplacer les fichiers + reconstruire la vraie
     application Mac) reste manuelle : redonner un double-clic sur
     Installer_MacBook.command, exactement comme pour une première
     installation — l'automatiser entièrement reviendrait à faire
     s'auto-remplacer une application pendant qu'elle tourne, ce qui
     n'est pas fiable.

Tout est pensé pour ne jamais bloquer ni planter le logiciel : pas de
connexion internet, dépôt encore vide, erreur réseau quelconque -> on
ignore silencieusement et l'appli continue normalement.
"""

import json
import platform
import re
import sys
import urllib.request
import urllib.error
from pathlib import Path

from PySide6.QtCore import QThread, Signal

from interface.theme import dossier_racine_ressources


DEPOT_GITHUB = "didail84/trailmaster-pro"
URL_DERNIERE_RELEASE = f"https://api.github.com/repos/{DEPOT_GITHUB}/releases/latest"
DELAI_RESEAU_SECONDES = 4


def version_locale():
    """Numéro de version de cette copie du logiciel (entier), lu dans
    le fichier VERSION à la racine du projet. Renvoie 0 si le fichier
    est absent ou illisible — dans ce cas, aucune mise à jour ne sera
    jamais proposée (on ne sait pas comparer), ce qui est le choix le
    plus sûr plutôt que de spammer une notification erronée."""

    chemin = dossier_racine_ressources() / "VERSION"
    try:
        contenu = chemin.read_text(encoding="utf-8").strip()
        return int(re.sub(r"[^0-9]", "", contenu) or "0")
    except (OSError, ValueError):
        return 0


def _numero_depuis_tag(tag):
    """'v75', 'V75', '75' -> 75. None si rien d'exploitable."""
    if not tag:
        return None
    chiffres = re.sub(r"[^0-9]", "", str(tag))
    return int(chiffres) if chiffres else None


def verifier_mise_a_jour():
    """Interroge GitHub. Renvoie un dict {version, tag, nom, notes,
    url_zip} si une version plus récente que la version locale est
    disponible, sinon None (y compris en cas d'erreur réseau, de dépôt
    sans aucune release, ou de première exécution hors version
    numérotée)."""

    locale = version_locale()
    if locale <= 0:
        return None

    try:
        requete = urllib.request.Request(
            URL_DERNIERE_RELEASE,
            headers={"Accept": "application/vnd.github+json", "User-Agent": "TrailMasterPro"},
        )
        with urllib.request.urlopen(requete, timeout=DELAI_RESEAU_SECONDES) as reponse:
            donnees = json.loads(reponse.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError, ValueError):
        return None

    if not isinstance(donnees, dict) or "tag_name" not in donnees:
        return None

    distante = _numero_depuis_tag(donnees.get("tag_name"))
    if distante is None or distante <= locale:
        return None

    url_zip = None
    for actif in donnees.get("assets", []) or []:
        nom_fichier = (actif.get("name") or "").lower()
        if nom_fichier.endswith(".zip"):
            url_zip = actif.get("browser_download_url")
            break
    if url_zip is None:
        # Repli : archive automatique du code source généré par GitHub,
        # toujours disponible même si aucun zip n'a été joint à la
        # release manuellement.
        url_zip = donnees.get("zipball_url")

    installateur = _installateur_pour_cet_ordinateur(donnees.get("assets", []) or [])

    return {
        "version": distante,
        "tag": donnees.get("tag_name"),
        "nom": donnees.get("name") or donnees.get("tag_name"),
        "notes": donnees.get("body") or "",
        "url_zip": url_zip,
        "url_installateur": installateur[0] if installateur else None,
        "nom_installateur": installateur[1] if installateur else None,
    }


def appli_installee():
    """Vrai quand le logiciel tourne depuis l'application installée
    (fabriquée avec PyInstaller), faux quand on lance python3 main.py."""
    return bool(getattr(sys, "frozen", False))


def _installateur_pour_cet_ordinateur(actifs):
    """Dans une release, l'installateur qui convient à cet ordinateur :
    .exe sous Windows, .dmg Intel (x64) ou Apple Silicon (arm64) sur Mac.
    Renvoie (url, nom_fichier) ou None. Seulement pour l'appli installée :
    depuis les sources, on garde le zip du code."""
    if not appli_installee():
        return None
    if sys.platform == "win32" and (Path(sys.executable).resolve().parent / "Donnees").is_dir():
        voulu = lambda n: n.endswith(".zip") and "windows-portable" in n
    elif sys.platform == "win32":
        voulu = lambda n: n.endswith(".exe") and "windows" in n
    elif sys.platform == "darwin":
        arch = "arm64" if platform.machine().lower() in ("arm64", "aarch64") else "x64"
        voulu = lambda n: n.endswith(".dmg") and f"mac-{arch}" in n
    else:
        return None
    for actif in actifs:
        nom = actif.get("name") or ""
        if voulu(nom.lower()):
            return actif.get("browser_download_url"), nom
    return None


def telecharger_mise_a_jour(url_zip, nom_fichier=None):
    """Télécharge le zip de mise à jour dans le dossier Téléchargements
    de l'utilisateur. Renvoie le chemin du fichier téléchargé, ou None
    en cas d'échec (jamais d'exception propagée)."""

    if not url_zip:
        return None

    dossier_telechargements = Path.home() / "Downloads"
    try:
        dossier_telechargements.mkdir(parents=True, exist_ok=True)
    except OSError:
        dossier_telechargements = Path.home()

    nom_fichier = nom_fichier or "TrailMaster_Pro_mise_a_jour.zip"
    destination = dossier_telechargements / nom_fichier

    try:
        requete = urllib.request.Request(url_zip, headers={"User-Agent": "TrailMasterPro"})
        with urllib.request.urlopen(requete, timeout=60) as reponse, open(destination, "wb") as fichier:
            while True:
                morceau = reponse.read(1024 * 1024)
                if not morceau:
                    break
                fichier.write(morceau)
    except (urllib.error.URLError, TimeoutError, OSError):
        return None

    return destination


class VerificationMajThread(QThread):
    """Lance verifier_mise_a_jour() en arrière-plan au démarrage, pour
    ne jamais faire attendre l'ouverture du logiciel en cas de réseau
    lent ou absent (délai réseau plafonné à DELAI_RESEAU_SECONDES de
    toute façon, mais autant ne jamais bloquer l'interface)."""

    resultat_disponible = Signal(object)  # dict ou None

    def run(self):
        try:
            resultat = verifier_mise_a_jour()
        except Exception:
            resultat = None
        self.resultat_disponible.emit(resultat)


# ---------------------------------------------------------------------
# v98 — mise à jour « en un clic » : télécharge, dézippe et ouvre le
# dossier prêt pour Installer_MacBook.command.
# ---------------------------------------------------------------------

def texte_version():
    """« Version 98 » (ou « Version inconnue » si le fichier VERSION manque)."""
    numero = version_locale()
    return f"Version {numero}" if numero > 0 else "Version inconnue"


def telecharger_et_preparer(url_zip, tag=None):
    """Télécharge le zip puis le dézippe à côté. Renvoie
    (chemin_zip, dossier_dezippe_ou_None) ou (None, None) si échec."""
    import zipfile

    nom_fichier = f"TrailMaster_Pro_{tag or 'maj'}.zip"
    chemin = telecharger_mise_a_jour(url_zip, nom_fichier)
    if not chemin:
        return None, None
    dossier = chemin.with_suffix("")
    try:
        with zipfile.ZipFile(chemin) as archive:
            archive.extractall(dossier)
    except (zipfile.BadZipFile, OSError):
        return chemin, None
    return chemin, dossier


def proposer_mise_a_jour(parent, resultat):
    """Boîte de dialogue complète : propose, télécharge, dézippe, ouvre
    le dossier. Utilisable depuis l'écran de démarrage comme depuis le
    menu. Aucune exception ne remonte."""
    from PySide6.QtWidgets import QMessageBox, QApplication
    from PySide6.QtGui import QDesktopServices
    from PySide6.QtCore import QUrl, Qt

    if not resultat:
        return False
    if resultat.get("url_installateur"):
        return _proposer_installateur(parent, resultat)
    boite = QMessageBox(parent)
    boite.setWindowTitle("Mise à jour disponible")
    boite.setIcon(QMessageBox.Icon.Information)
    notes = (resultat.get("notes") or "").strip()
    texte = f"Une nouvelle version est disponible : {resultat.get('nom')}."
    if notes:
        texte += f"\n\n{notes[:900]}"
    texte += (
        "\n\nUn clic sur « Mettre à jour » télécharge et dézippe la nouvelle version, puis "
        "ouvre le dossier. Il ne te restera qu'à double-cliquer sur Installer_MacBook.command."
    )
    boite.setText(texte)
    bouton_ok = boite.addButton("Mettre à jour", QMessageBox.ButtonRole.AcceptRole)
    boite.addButton("Plus tard", QMessageBox.ButtonRole.RejectRole)
    boite.exec()
    if boite.clickedButton() is not bouton_ok:
        return False

    QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
    try:
        chemin, dossier = telecharger_et_preparer(resultat.get("url_zip"), resultat.get("tag"))
    finally:
        QApplication.restoreOverrideCursor()

    if not chemin:
        QMessageBox.warning(
            parent, "Mise à jour",
            "Le téléchargement a échoué (réseau indisponible ou interrompu). Réessaie plus tard, "
            "ou récupère la version sur github.com/didail84/trailmaster-pro.",
        )
        return False
    cible = dossier or chemin.parent
    QDesktopServices.openUrl(QUrl.fromLocalFile(str(cible)))
    QMessageBox.information(
        parent, "Mise à jour",
        f"Nouvelle version prête dans :\n{cible}\n\nDouble-clique sur Installer_MacBook.command "
        "pour terminer (tes données ne sont pas touchées).",
    )
    return True


def _proposer_installateur(parent, resultat):
    """Appli installée : télécharge le nouvel installateur (.dmg ou .exe)
    dans Téléchargements puis l'ouvre. Les données ne sont pas touchées :
    elles restent dans le dossier de l'application (Application Support
    sur Mac, %APPDATA% sous Windows)."""
    from PySide6.QtWidgets import QMessageBox, QApplication
    from PySide6.QtGui import QDesktopServices
    from PySide6.QtCore import QUrl, Qt

    boite = QMessageBox(parent)
    boite.setWindowTitle("Mise à jour disponible")
    boite.setIcon(QMessageBox.Icon.Information)
    notes = (resultat.get("notes") or "").strip()
    texte = f"Une nouvelle version est disponible : {resultat.get('nom')}."
    if notes:
        texte += f"\n\n{notes[:900]}"
    if sys.platform == "darwin":
        texte += ("\n\nUn clic sur « Mettre à jour » télécharge la nouvelle version et l'ouvre. "
                  "Quitte TrailMaster, puis fais glisser TrailMaster Pro dans Applications "
                  "(remplace l'ancienne). Tes données sont conservées.")
    else:
        texte += ("\n\nUn clic sur « Mettre à jour » télécharge l'installateur et le lance. "
                  "Ferme TrailMaster quand l'installateur le demande. Tes données sont conservées.")
    boite.setText(texte)
    bouton_ok = boite.addButton("Mettre à jour", QMessageBox.ButtonRole.AcceptRole)
    boite.addButton("Plus tard", QMessageBox.ButtonRole.RejectRole)
    boite.exec()
    if boite.clickedButton() is not bouton_ok:
        return False

    QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
    try:
        chemin = telecharger_mise_a_jour(resultat.get("url_installateur"), resultat.get("nom_installateur"))
    finally:
        QApplication.restoreOverrideCursor()
    if not chemin:
        QMessageBox.warning(
            parent, "Mise à jour",
            "Le téléchargement a échoué (réseau indisponible ou interrompu). Réessaie plus tard, "
            "ou récupère la version sur github.com/didail84/trailmaster-pro/releases.",
        )
        return False
    QDesktopServices.openUrl(QUrl.fromLocalFile(str(chemin)))
    return True
