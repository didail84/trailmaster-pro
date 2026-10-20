"""
Graphique en barres minimal, dessiné directement avec QPainter — pas de
dépendance à une librairie de graphiques externe. Utilisé pour
l'évolution de la charge d'entraînement dans l'écran Analyses.
"""

import re

from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QPainter, QColor, QPen
from PySide6.QtWidgets import QWidget

from interface.survol_graphique import formater_valeur, dessiner_infobulle


class CourbeBarres(QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)
        self.valeurs = []   # liste de (label_court, valeur)
        self.seuil = None   # valeur de référence optionnelle (ligne pointillée)
        self.libelle = "Valeur"   # nom de la mesure, affiché dans l'info-bulle
        self.unite = ""
        self._survol = None
        self.setMinimumHeight(220)
        self.setMouseTracking(True)

    def definir_donnees(self, valeurs, seuil=None, libelle=None, unite=None):
        """libelle/unite : nom et unité de la mesure pour l'info-bulle au
        survol (ex. libelle="Charge", unite="" ou "Distance (km)")."""
        self.valeurs = valeurs
        self.seuil = seuil
        if libelle is not None:
            m = re.match(r"^(.*?)\s*\(([^)]*)\)\s*$", libelle)
            if m and unite is None:  # « Distance (km) » -> Distance + km
                libelle, unite = m.group(1), m.group(2)
            self.libelle = libelle
        if unite is not None:
            self.unite = unite
        self._survol = None
        self.update()

    def _indice_sous_souris(self, x):
        n = len(self.valeurs)
        if not n:
            return None
        largeur = max(self.width() - 40 - 10, 1)
        i = int((x - 40) / (largeur / n))
        return i if 0 <= i < n else None

    def mouseMoveEvent(self, event):
        i = self._indice_sous_souris(event.position().x())
        if i != self._survol:
            self._survol = i
            self.update()

    def leaveEvent(self, event):
        if self._survol is not None:
            self._survol = None
            self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor("#15191D"))

        if not self.valeurs:
            painter.setPen(QColor("#7F878D"))
            painter.drawText(
                self.rect(), Qt.AlignmentFlag.AlignCenter,
                "Pas encore assez de données pour tracer la charge"
            )
            painter.end()
            return

        marge_gauche = 40
        marge_bas = 22
        marge_haut = 15
        marge_droite = 10

        largeur = max(self.width() - marge_gauche - marge_droite, 1)
        hauteur = max(self.height() - marge_haut - marge_bas, 1)

        valeur_max = max([v for _, v in self.valeurs] + [self.seuil or 0, 1])

        n = len(self.valeurs)
        pas = largeur / n
        largeur_barre = max(pas * 0.6, 2)

        for i, (_, valeur) in enumerate(self.valeurs):
            x = marge_gauche + i * pas + (pas - largeur_barre) / 2
            h = (valeur / valeur_max) * hauteur
            y = marge_haut + (hauteur - h)

            couleur = QColor("#2E7D32")
            if self.seuil and valeur > self.seuil:
                couleur = QColor("#D32F2F")

            if i == self._survol:
                couleur = couleur.lighter(135)
            painter.fillRect(QRectF(x, y, largeur_barre, h), couleur)

        if self.seuil:
            y_seuil = marge_haut + hauteur - (self.seuil / valeur_max) * hauteur
            painter.setPen(QPen(QColor("#F9A825"), 1, Qt.PenStyle.DashLine))
            painter.drawLine(
                int(marge_gauche), int(y_seuil),
                int(self.width() - marge_droite), int(y_seuil),
            )

        painter.setPen(QColor("#7F878D"))
        painter.drawText(2, marge_haut + 10, f"{round(valeur_max)}")
        painter.drawText(2, self.height() - marge_bas, "0")

        pas_label = max(n // 6, 1)
        for i, (label, _) in enumerate(self.valeurs):
            if i % pas_label == 0:
                x = marge_gauche + i * pas
                painter.drawText(int(x), self.height() - 6, label)

        # Info-bulle au survol d'une barre
        i = self._survol
        if i is not None and i < n:
            label, valeur = self.valeurs[i]
            x_barre = marge_gauche + i * pas + pas / 2
            y_barre = marge_haut + hauteur - (valeur / valeur_max) * hauteur
            lignes = [("#66BB6A" if not (self.seuil and valeur > self.seuil) else "#EF5350",
                       f"{self.libelle} : {formater_valeur(valeur, {'unite': self.unite})}")]
            if self.seuil:
                lignes.append((None, f"Seuil : {formater_valeur(round(self.seuil, 1))}"
                                     + (" — dépassé" if valeur > self.seuil else "")))
            dessiner_infobulle(painter, QRectF(self.rect()), x_barre, y_barre, str(label), lignes)

        painter.end()
