import sys

# Avant toute connexion internet : évite les erreurs « certificats SSL » sur Mac.
from interface.certificats_ssl import configurer_certificats_ssl
configurer_certificats_ssl()

from PySide6.QtCore import Qt, QCoreApplication
from PySide6.QtWidgets import QApplication

# Doit être fait AVANT la création de QApplication : bonne pratique Qt
# pour la carte réelle (QtWebEngine), évite des soucis de partage de
# contexte OpenGL sur certaines configurations.
QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)

from interface.accueil import Accueil
from interface.theme import appliquer_mode_couleur_enregistre


app = QApplication(sys.argv)

# Applique le mode sombre/clair mémorisé (Réglages > Apparence) avant
# d'ouvrir la moindre fenêtre — sinon le logiciel démarrerait toujours
# en sombre puis basculerait au premier changement d'écran.
appliquer_mode_couleur_enregistre()

fenetre = Accueil()
fenetre.resize(1200, 800)
fenetre.show()

sys.exit(app.exec())