import sys
import traceback
from datetime import datetime
from pathlib import Path

# Si le démarrage échoue, le message complet est écrit dans ce fichier (dans ton dossier
# personnel) et affiché dans une fenêtre : il suffit de l'envoyer pour trouver la cause.
FICHIER_ERREUR = Path.home() / "TrailHubCenter_erreur_demarrage.txt"


def _signaler_erreur_demarrage(erreur):
    texte = (f"Trail Hub Center n'a pas pu démarrer ({datetime.now():%d/%m/%Y %H:%M}).\n"
             f"Python {sys.version.split()[0]} · {sys.platform}\n\n"
             + "".join(traceback.format_exception(type(erreur), erreur, erreur.__traceback__)))
    try:
        FICHIER_ERREUR.write_text(texte, encoding="utf-8")
    except OSError:
        pass
    print(texte, file=sys.stderr)
    try:
        from PySide6.QtWidgets import QApplication, QMessageBox
        appli = QApplication.instance() or QApplication(sys.argv)
        boite = QMessageBox(QMessageBox.Icon.Critical, "Trail Hub Center ne démarre pas",
                            f"{type(erreur).__name__} : {erreur}\n\n"
                            f"Le détail a été enregistré dans :\n{FICHIER_ERREUR}\n\n"
                            "Envoie ce fichier (ou une capture de ce message) pour que la cause soit corrigée. "
                            "Ta base n'a pas été modifiée par cette erreur.")
        boite.setDetailedText(texte)
        boite.exec()
        del appli
    except Exception:
        pass


def demarrer():
    # Avant toute connexion internet : évite les erreurs « certificats SSL » sur Mac.
    from noyau.outils.certificats_ssl import configurer_certificats_ssl
    configurer_certificats_ssl()

    from PySide6.QtCore import Qt, QCoreApplication
    from PySide6.QtWidgets import QApplication

    # Doit être fait AVANT la création de QApplication : bonne pratique Qt
    # pour la carte réelle (QtWebEngine), évite des soucis de partage de
    # contexte OpenGL sur certaines configurations.
    QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)

    app = QApplication(sys.argv)

    from interface.accueil import Accueil
    from interface.theme import appliquer_mode_couleur_enregistre

    # Applique le mode sombre/clair mémorisé (Réglages > Apparence) avant
    # d'ouvrir la moindre fenêtre — sinon le logiciel démarrerait toujours
    # en sombre puis basculerait au premier changement d'écran.
    appliquer_mode_couleur_enregistre()

    # Une erreur plus tard (ouverture d'un écran…) est aussi notée dans le fichier d'erreur.
    precedent = sys.excepthook

    def noter(type_, valeur, trace):
        try:
            with open(FICHIER_ERREUR, "a", encoding="utf-8") as f:
                f.write(f"\n--- {datetime.now():%d/%m/%Y %H:%M:%S}\n" + "".join(traceback.format_exception(type_, valeur, trace)))
        except OSError:
            pass
        precedent(type_, valeur, trace)
    sys.excepthook = noter

    fenetre = Accueil()
    fenetre.resize(1200, 800)
    fenetre.show()
    return app.exec()


if __name__ == "__main__":
    try:
        code = demarrer()
    except Exception as e:
        _signaler_erreur_demarrage(e)
        code = 1
    sys.exit(code)
