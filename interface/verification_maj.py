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
import re
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


def reglages_relais():
    """(canal, adresse du Relais du club) choisis dans Réglages."""
    from noyau.relais import client as RC
    return RC.reglages()


def verifier_mise_a_jour():
    """Étape 8 : d'abord Relais (NAS du club, puis le manifeste signé de GitHub) ; pour les versions publiées avant
    Relais, l'ancienne comparaison avec la dernière version GitHub. Renvoie None si à jour ou hors ligne."""
    from noyau.relais import client as RC, manifeste as RM
    locale = version_locale()
    if locale <= 0:
        return None
    canal, url_nas = reglages_relais()
    try:
        r = RC.chercher(locale, canal, url_nas)
    except RM.ErreurRelais as e:
        return {"version": None, "nom": "mise à jour refusée", "notes": str(e), "refus": True}
    except Exception:
        r = None
    if r is not None:
        if r["a_jour"]:
            return None
        return {"version": r["version"], "tag": f"V{r['version']}", "nom": f"Version {r['version']}",
                "notes": r["notes"], "fichier": r["fichier"], "signe": r["signe"], "source": r["source"],
                "canal": r["canal"], "url_zip": None}
    return verifier_mise_a_jour_github()


def verifier_mise_a_jour_github():
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

    return {
        "version": distante,
        "tag": donnees.get("tag_name"),
        "nom": donnees.get("name") or donnees.get("tag_name"),
        "notes": donnees.get("body") or "",
        "url_zip": url_zip,
    }


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
        with urllib.request.urlopen(requete, timeout=30) as reponse, open(destination, "wb") as fichier:
            fichier.write(reponse.read())
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
    if resultat.get("refus"):
        QMessageBox.warning(parent, "Mise à jour", resultat.get("notes") or "Mise à jour refusée.")
        return False
    if resultat.get("fichier") or resultat.get("source"):
        return proposer_mise_a_jour_relais(parent, resultat)
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


# ---------------------------------------------------------------------
# Étape 8 — mise à jour par Relais : fichier de CET ordinateur, empreinte
# vérifiée, installation adaptée (Windows, Mac, Linux), retour arrière.
# ---------------------------------------------------------------------

def proposer_mise_a_jour_relais(parent, resultat):
    from PySide6.QtCore import QUrl, Qt, QProcess
    from PySide6.QtGui import QDesktopServices
    from PySide6.QtWidgets import QApplication, QMessageBox, QProgressDialog
    from noyau.relais import client as RC, manifeste as RM

    f = resultat.get("fichier")
    texte = (f"Une nouvelle version est disponible : {resultat.get('nom')}"
             f" (canal {resultat.get('canal') or 'stable'}, depuis {resultat.get('source')}"
             f"{', signée' if resultat.get('signe') else ', non signée'}).")
    notes = (resultat.get("notes") or "").strip()
    if notes:
        texte += f"\n\n{notes[:900]}"
    if not f:
        texte += ("\n\nPas de fichier tout prêt pour cet ordinateur (" + RC.plateforme()
                  + (", lancé depuis les sources" if RC.installation() == "sources" else "")
                  + ") : télécharge la nouvelle version sur github.com/didail84/trailmaster-pro.")
        QMessageBox.information(parent, "Mise à jour disponible", texte)
        return False
    texte += f"\n\nTéléchargement : {f['nom']} ({(f.get('taille') or 0) / 1048576:.0f} Mo), empreinte vérifiée avant installation."
    if QMessageBox.question(parent, "Mise à jour disponible", texte + "\n\nMettre à jour maintenant ?") != \
            QMessageBox.StandardButton.Yes:
        return False
    prog = QProgressDialog("Téléchargement de la mise à jour…", "Annuler", 0, 100, parent)
    prog.setWindowModality(Qt.WindowModality.WindowModal)
    prog.show()

    def avance(n, total):
        if total:
            prog.setValue(int(100 * n / total))
        QApplication.processEvents()
        if prog.wasCanceled():
            raise RM.ErreurRelais("Téléchargement annulé.")
    try:
        chemin = RC.telecharger(f, progression=avance)
    except Exception as e:
        prog.close()
        QMessageBox.warning(parent, "Mise à jour", f"Mise à jour non faite : {e}")
        return False
    prog.close()
    action, detail = RC.plan_installation(chemin)
    if action == "remplacer_appimage":
        RC.remplacer_appimage(chemin, detail)
        QMessageBox.information(parent, "Mise à jour", "Nouvelle version installée. Trail Hub Center redémarre ; "
                                "l'ancienne version est gardée à côté (retour arrière possible dans Réglages).")
        QProcess.startDetached(detail, [])
        QApplication.quit()
    elif action == "lancer":
        QMessageBox.information(parent, "Mise à jour", "L'installation va se lancer ; Trail Hub Center se ferme "
                                "puis se rouvre à jour. Tes données ne sont pas touchées.")
        QProcess.startDetached(detail[0], detail[1:])
        QApplication.quit()
    elif action == "ouvrir":
        QDesktopServices.openUrl(QUrl.fromLocalFile(detail))
        QMessageBox.information(parent, "Mise à jour", ("Glisse Trail Hub Center dans Applications (remplacer), puis "
                                                        "rouvre-le." if detail.endswith(".dmg") else
                                                        "Clique « Installer » dans la logithèque, puis rouvre Trail Hub "
                                                        "Center.") + " Tes données ne sont pas touchées.")
    else:
        QDesktopServices.openUrl(QUrl.fromLocalFile(detail))
        QMessageBox.information(parent, "Mise à jour", f"Nouvelle version téléchargée : {chemin}")
    return True
