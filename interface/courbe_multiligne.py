"""
Graphique à plusieurs courbes superposées, dessiné directement avec
QPainter — pas de dépendance à une librairie de graphiques externe.
Utilisé pour la courbe Fitness / Fatigue / Forme dans l'écran Analyses.
"""

from PySide6.QtCore import Qt, QPointF, QRectF
from PySide6.QtGui import QPainter, QColor, QPen, QPolygonF
from PySide6.QtWidgets import QWidget

from interface.survol_graphique import formater_valeur, dessiner_infobulle, nom_et_serie


class CourbeMultiLignes(QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)
        self.series = []  # liste de {"nom": str, "couleur": str, "valeurs": [(label, valeur), ...]}
        self.setMinimumHeight(240)
        # True : l'échelle suit les valeurs (sans forcer le zéro) — utile pour
        # une VMA, un chrono ou une allure, qui varient peu autour d'une valeur.
        self.echelle_ajustee = False
        # Info-bulle au survol : indice du point sous la souris (None = aucun)
        self._survol = None
        self._geo = None
        # True : une teinte légère est ajoutée sous chaque courbe (aire)
        self.remplissage = False
        # v98 — bande de référence : liste (une entrée par point) de
        # (bas, haut) ou None ; dessinée en aire translucide (ex. HRV normale).
        self.bande = None
        self.bande_nom = "Bande normale"
        self.bande_couleur = "#66BB6A"
        # v98 — lignes horizontales de repère : [(valeur, texte, couleur)]
        self.reperes = []
        self.setMouseTracking(True)

    def mouseMoveEvent(self, event):
        g = self._geo
        if not g or not self.series or not self.series[0]["valeurs"]:
            return
        n = g["n"]
        i = round((event.position().x() - g["mg"]) / max(g["largeur"], 1) * max(n - 1, 1))
        i = max(0, min(n - 1, i))
        if i != self._survol:
            self._survol = i
            self.update()

    def leaveEvent(self, event):
        if self._survol is not None:
            self._survol = None
            self.update()

    def definir_series(self, series):
        self.series = series
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor("#15191D"))

        if not self.series or not self.series[0]["valeurs"]:
            painter.setPen(QColor("#7F878D"))
            painter.drawText(
                self.rect(), Qt.AlignmentFlag.AlignCenter,
                "Pas encore assez de données"
            )
            painter.end()
            return

        marge_gauche = 45
        marge_bas = 40
        marge_haut = 20
        marge_droite = 15

        largeur = max(self.width() - marge_gauche - marge_droite, 1)
        hauteur = max(self.height() - marge_haut - marge_bas, 1)

        toutes_valeurs = [v for serie in self.series for _, v in serie["valeurs"]]
        if self.bande:
            toutes_valeurs += [b for e in self.bande if e for b in e]
        toutes_valeurs += [r[0] for r in (self.reperes or [])]
        if self.echelle_ajustee:
            valeur_max = max(toutes_valeurs)
            valeur_min = min(toutes_valeurs)
            etendue = max(valeur_max - valeur_min, 0.5)
        else:
            valeur_max = max(toutes_valeurs + [1])
            valeur_min = min(toutes_valeurs + [0])
            etendue = max(valeur_max - valeur_min, 1)
        # Un peu de marge pour ne pas coller les courbes aux bords
        valeur_max += etendue * 0.1
        valeur_min -= etendue * 0.1
        etendue = valeur_max - valeur_min

        n = len(self.series[0]["valeurs"])
        self._geo = {"mg": marge_gauche, "largeur": largeur, "n": n}

        def vers_pixel(i, valeur):
            px = marge_gauche + (i / max(n - 1, 1)) * largeur
            py = marge_haut + (1 - (valeur - valeur_min) / etendue) * hauteur
            return QPointF(px, py)

        # Ligne du zéro (repère pour la Forme, qui peut être négative)
        if valeur_min < 0 < valeur_max:
            y_zero = vers_pixel(0, 0).y()
            painter.setPen(QPen(QColor("#3A4046"), 1, Qt.PenStyle.DashLine))
            painter.drawLine(marge_gauche, int(y_zero), self.width() - marge_droite, int(y_zero))

        if self.bande:
            haut_pts, bas_pts = [], []
            for i, e in enumerate(self.bande):
                if e is None:
                    continue
                haut_pts.append(vers_pixel(i, e[1]))
                bas_pts.append(vers_pixel(i, e[0]))
            if len(haut_pts) >= 2:
                teinte = QColor(self.bande_couleur)
                teinte.setAlpha(48)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(teinte)
                painter.drawPolygon(QPolygonF(haut_pts + list(reversed(bas_pts))))
                painter.setBrush(Qt.BrushStyle.NoBrush)

        for valeur_repere, texte_repere, couleur_repere in (self.reperes or []):
            y_r = vers_pixel(0, valeur_repere).y()
            painter.setPen(QPen(QColor(couleur_repere), 1, Qt.PenStyle.DashLine))
            painter.drawLine(marge_gauche, int(y_r), self.width() - marge_droite, int(y_r))
            painter.drawText(marge_gauche + 4, int(y_r) - 3, texte_repere)

        if self.remplissage:
            base = marge_haut + hauteur
            for serie in self.series:
                pts = [vers_pixel(i, v) for i, (_, v) in enumerate(serie["valeurs"])]
                if len(pts) < 2:
                    continue
                aire = QPolygonF([QPointF(pts[0].x(), base)] + pts + [QPointF(pts[-1].x(), base)])
                teinte = QColor(serie["couleur"])
                teinte.setAlpha(46)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(teinte)
                painter.drawPolygon(aire)
            painter.setBrush(Qt.BrushStyle.NoBrush)

        for serie in self.series:
            points = [vers_pixel(i, v) for i, (_, v) in enumerate(serie["valeurs"])]
            painter.setPen(QPen(QColor(serie["couleur"]), 2))
            for i in range(1, len(points)):
                painter.drawLine(points[i - 1], points[i])

        # Axe des valeurs
        painter.setPen(QColor("#7F878D"))
        if self.echelle_ajustee:
            painter.drawText(2, marge_haut + 10, f"{valeur_max:.1f}")
            painter.drawText(2, marge_haut + hauteur, f"{valeur_min:.1f}")
        else:
            painter.drawText(2, marge_haut + 10, f"{round(valeur_max)}")
            painter.drawText(2, marge_haut + hauteur, f"{round(valeur_min)}")

        # Labels d'axe X (quelques dates seulement)
        pas_label = max(n // 6, 1)
        for i, (label, _) in enumerate(self.series[0]["valeurs"]):
            if i % pas_label == 0:
                x = marge_gauche + (i / max(n - 1, 1)) * largeur
                largeur_label = painter.fontMetrics().horizontalAdvance(str(label))
                x = min(x, self.width() - largeur_label - 3)  # jamais coupé à droite
                painter.drawText(int(x), self.height() - marge_bas + 16, label)

        # Légende
        x_legende = marge_gauche
        y_legende = self.height() - 12
        for serie in self.series:
            painter.setPen(QPen(QColor(serie["couleur"]), 3))
            painter.drawLine(x_legende, y_legende, x_legende + 16, y_legende)
            painter.setPen(QColor("#C8CDD2"))
            painter.drawText(x_legende + 22, y_legende + 4, serie["nom"])
            x_legende += 22 + len(serie["nom"]) * 7 + 20

        if self.bande and any(self.bande):
            teinte = QColor(self.bande_couleur)
            teinte.setAlpha(110)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(teinte)
            painter.drawRect(x_legende, y_legende - 5, 16, 10)
            painter.setPen(QColor("#C8CDD2"))
            painter.drawText(x_legende + 22, y_legende + 4, self.bande_nom)

        # Info-bulle au survol : repère vertical + valeur de chaque courbe
        i = self._survol
        if i is not None and i < n:
            x_repere = marge_gauche + (i / max(n - 1, 1)) * largeur
            painter.setPen(QPen(QColor("#6B737A"), 1, Qt.PenStyle.DashLine))
            painter.drawLine(int(x_repere), marge_haut, int(x_repere), marge_haut + hauteur)
            lignes = []
            for serie in self.series:
                valeurs = serie["valeurs"]
                if i < len(valeurs):
                    point = vers_pixel(i, valeurs[i][1])
                    painter.setPen(QPen(QColor("#15191D"), 2))
                    painter.setBrush(QColor(serie["couleur"]))
                    painter.drawEllipse(point, 4.5, 4.5)
                    nom_court, serie_fmt = nom_et_serie(serie)
                    lignes.append((serie["couleur"], f"{nom_court} : {formater_valeur(valeurs[i][1], serie_fmt)}"))
            titre = str(self.series[0]["valeurs"][i][0])
            dessiner_infobulle(
                painter, QRectF(self.rect()), x_repere, marge_haut + hauteur / 2, titre, lignes
            )

        painter.end()
