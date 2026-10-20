"""
Mini graphique de tendance (sparkline) — juste une ligne, sans axes ni
légende, pour donner un coup d'œil rapide sur une évolution récente
directement dans une carte du tableau de bord (forme, ACWR, charge)
sans avoir à ouvrir l'écran Analyses. Dessiné avec QPainter, comme
CourbeBarres — pas de dépendance à une librairie de graphiques.
"""

from PySide6.QtCore import Qt
from PySide6.QtGui import QPainter, QColor, QPen, QPainterPath
from PySide6.QtWidgets import QWidget, QToolTip


class Sparkline(QWidget):

    def __init__(self, parent=None, couleur="#4C8DFF"):
        super().__init__(parent)
        self.valeurs = []
        self.couleur = couleur
        self.etiquettes = []
        self.setMinimumHeight(28)
        self.setMaximumHeight(34)
        self.setMouseTracking(True)

    def definir_donnees(self, valeurs, etiquettes=None):
        """valeurs : liste de nombres (ordre chronologique), None ignorés.
        etiquettes : libellés (ex. dates) de même longueur, affichés au survol."""
        if etiquettes is not None and len(etiquettes) == len(valeurs):
            gardes = [(v, e) for v, e in zip(valeurs, etiquettes) if v is not None]
            self.valeurs = [v for v, _ in gardes]
            self.etiquettes = [e for _, e in gardes]
        else:
            self.valeurs = [v for v in valeurs if v is not None]
            self.etiquettes = []
        self.update()

    def mouseMoveEvent(self, event):
        n = len(self.valeurs)
        if n < 2:
            return
        pas = (self.width() - 4) / (n - 1)
        i = max(0, min(n - 1, round((event.position().x() - 2) / pas)))
        texte = f"{self.valeurs[i]:g}"
        if self.etiquettes:
            texte = f"{self.etiquettes[i]} : {texte}"
        QToolTip.showText(event.globalPosition().toPoint(), texte, self)

    def definir_couleur(self, couleur):
        self.couleur = couleur
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        if len(self.valeurs) < 2:
            return

        largeur = self.width()
        hauteur = self.height()
        marge = 2

        mini = min(self.valeurs)
        maxi = max(self.valeurs)
        etendue = (maxi - mini) or 1

        pas_x = (largeur - 2 * marge) / (len(self.valeurs) - 1)

        def point(i, v):
            x = marge + i * pas_x
            y = hauteur - marge - ((v - mini) / etendue) * (hauteur - 2 * marge)
            return x, y

        chemin = QPainterPath()
        x0, y0 = point(0, self.valeurs[0])
        chemin.moveTo(x0, y0)
        for i, v in enumerate(self.valeurs[1:], start=1):
            x, y = point(i, v)
            chemin.lineTo(x, y)

        stylo = QPen(QColor(self.couleur))
        stylo.setWidthF(1.6)
        painter.setPen(stylo)
        painter.drawPath(chemin)

        # Point final mis en évidence — dernière valeur = valeur
        # affichée juste au-dessus dans la carte.
        xf, yf = point(len(self.valeurs) - 1, self.valeurs[-1])
        painter.setBrush(QColor(self.couleur))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(xf - 2.2, yf - 2.2, 4.4, 4.4)
