"""
Éléments visuels réutilisables du style « Cockpit » (D3) : anneau de
valeur, jauge à barre avec repère, pastille de statut. Tout est dessiné
avec QPainter, aux couleurs de la palette du logiciel.
"""

from PySide6.QtCore import Qt, QRectF, QPointF
from PySide6.QtGui import QPainter, QColor, QPen, QFont
from PySide6.QtWidgets import QWidget

from interface.theme import PALETTE, obtenir_couleur_accent


def couleur_score(pct):
    """0-100 -> rouge / orange / jaune / vert (plus c'est haut, mieux c'est)."""
    if pct is None:
        return PALETTE["texte_discret"]
    if pct >= 75:
        return "#66BB6A"
    if pct >= 55:
        return "#C0CA33"
    if pct >= 35:
        return "#FFA726"
    return "#EF5350"


class Anneau(QWidget):
    """Anneau de progression (0-100) avec valeur au centre."""

    def __init__(self, parent=None, taille=150, epaisseur=14):
        super().__init__(parent)
        self.valeur = None          # 0-100 ou None
        self.texte = "—"
        self.sous_texte = ""
        self.couleur = None
        self.epaisseur = epaisseur
        self.setMinimumSize(taille, taille)

    def definir(self, valeur, texte=None, sous_texte="", couleur=None):
        self.valeur = valeur
        self.texte = texte if texte is not None else ("—" if valeur is None else str(round(valeur)))
        self.sous_texte = sous_texte
        self.couleur = couleur or couleur_score(valeur)
        self.update()

    def paintEvent(self, ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        cote = min(self.width(), self.height()) - self.epaisseur - 4
        r = QRectF((self.width() - cote) / 2, (self.height() - cote) / 2, cote, cote)
        p.setPen(QPen(QColor(PALETTE["bordure"]), self.epaisseur, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.drawArc(r, 0, 360 * 16)
        if self.valeur is not None:
            p.setPen(QPen(QColor(self.couleur or obtenir_couleur_accent()), self.epaisseur,
                          Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            p.drawArc(r, 90 * 16, -int(360 * 16 * max(0, min(100, self.valeur)) / 100))
        p.setPen(QColor(PALETTE["texte"]))
        f = QFont(p.font())
        f.setPixelSize(int(cote * 0.30))
        f.setBold(True)
        p.setFont(f)
        haut = r.adjusted(0, -cote * 0.06 if self.sous_texte else 0, 0, 0)
        p.drawText(haut, Qt.AlignmentFlag.AlignCenter, self.texte)
        if self.sous_texte:
            f2 = QFont(f)
            f2.setPixelSize(max(9, int(cote * 0.095)))
            f2.setBold(False)
            p.setFont(f2)
            p.setPen(QColor(PALETTE["texte_secondaire"]))
            p.drawText(QRectF(r.left(), r.center().y() + cote * 0.14, r.width(), cote * 0.2),
                       Qt.AlignmentFlag.AlignCenter, self.sous_texte)
        p.end()


class JaugeBarre(QWidget):
    """Barre de progression avec repère « attendu » et projection."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.pct = 0.0
        self.repere = None          # position attendue (0-100+)
        self.projection = None      # fin d'année estimée (0-100+)
        self.couleur = None
        self.setMinimumHeight(30)
        self.setMaximumHeight(34)

    def definir(self, pct, repere=None, projection=None, couleur=None):
        self.pct, self.repere, self.projection, self.couleur = pct, repere, projection, couleur
        self.update()

    def paintEvent(self, ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        h = 14
        y = (self.height() - h) / 2
        largeur = self.width() - 2
        echelle = max(100.0, self.pct, self.projection or 0, self.repere or 0)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(PALETTE["bordure"]))
        p.drawRoundedRect(QRectF(1, y, largeur, h), h / 2, h / 2)
        if self.projection:
            c = QColor(self.couleur or obtenir_couleur_accent())
            c.setAlpha(60)
            p.setBrush(c)
            p.drawRoundedRect(QRectF(1, y, largeur * self.projection / echelle, h), h / 2, h / 2)
        p.setBrush(QColor(self.couleur or obtenir_couleur_accent()))
        p.drawRoundedRect(QRectF(1, y, max(h, largeur * self.pct / echelle), h), h / 2, h / 2)
        if self.repere is not None:
            x = 1 + largeur * self.repere / echelle
            p.setPen(QPen(QColor(PALETTE["texte"]), 2))
            p.drawLine(QPointF(x, y - 4), QPointF(x, y + h + 4))
        p.end()
