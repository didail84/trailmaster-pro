"""
Petit widget réutilisable : le repère visuel "montagne" de
TrailMaster Pro, dessiné au pinceau (QPainter) plutôt que comme
fichier image — pour rester net à toutes les tailles et suivre
automatiquement la couleur d'accent choisie dans Réglages.

Utilisé sur l'écran de démarrage (interface/accueil.py) et dans le
menu latéral du tableau de bord (interface/tableau_bord.py) : un seul
endroit à modifier si le logo doit évoluer.
"""

from PySide6.QtWidgets import QWidget
from PySide6.QtCore import Qt
from PySide6.QtGui import QPainter, QPainterPath, QColor, QPen

from interface.theme import obtenir_couleur_accent


class LogoMontagne(QWidget):

    def __init__(self, taille=72, parent=None):
        super().__init__(parent)
        self._taille = taille
        self.setFixedSize(taille, taille)

    def paintEvent(self, event):
        peintre = QPainter(self)
        peintre.setRenderHint(QPainter.RenderHint.Antialiasing)

        s = self._taille / 72.0
        accent = QColor(obtenir_couleur_accent())

        contour = QPen(QColor("#3A4550"))
        contour.setWidthF(1.5 * s)
        contour.setJoinStyle(Qt.PenJoinStyle.RoundJoin)

        chemin_gauche = QPainterPath()
        chemin_gauche.moveTo(6 * s, 54 * s)
        chemin_gauche.lineTo(26 * s, 20 * s)
        chemin_gauche.lineTo(36 * s, 36 * s)
        chemin_gauche.lineTo(44 * s, 24 * s)
        chemin_gauche.lineTo(66 * s, 54 * s)
        chemin_gauche.closeSubpath()
        peintre.setPen(contour)
        peintre.setBrush(QColor("#171D22"))
        peintre.drawPath(chemin_gauche)

        chemin_droite = QPainterPath()
        chemin_droite.moveTo(36 * s, 36 * s)
        chemin_droite.lineTo(44 * s, 24 * s)
        chemin_droite.lineTo(66 * s, 54 * s)
        chemin_droite.lineTo(48 * s, 54 * s)
        chemin_droite.closeSubpath()
        peintre.setBrush(QColor("#20272D"))
        peintre.drawPath(chemin_droite)

        sommet = QPainterPath()
        sommet.moveTo(26 * s, 20 * s)
        sommet.lineTo(34 * s, 32 * s)
        sommet.lineTo(28 * s, 36 * s)
        sommet.lineTo(20 * s, 32 * s)
        sommet.closeSubpath()
        peintre.setPen(Qt.PenStyle.NoPen)
        peintre.setBrush(accent)
        peintre.drawPath(sommet)

        peintre.end()
