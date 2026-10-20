"""
X1 — Album et diaporama d'une sortie : les photos défilent en plein
écran avec leur légende, l'heure et l'endroit sur le tracé ; l'album se
rend aussi en PDF (page de couverture avec le tracé, puis les photos).
"""

import math
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QRectF, QPointF, QMarginsF
from PySide6.QtGui import QPixmap, QImageReader, QPainter, QColor, QPen, QPdfWriter, QPageSize, QPageLayout, QFont
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFileDialog, QWidget,
)

import data.metriques as met
import data.photos_sorties as ph
from data.database import connexion
from interface.theme import PALETTE, obtenir_couleur_accent
from interface.outils_ui import notifier


def _infos_sortie(activite_id):
    conn = connexion()
    cur = conn.cursor()
    cur.execute("SELECT nom, date, type, distance, denivele, duree FROM activites WHERE id=?", (activite_id,))
    r = cur.fetchone()
    conn.close()
    if not r:
        return {}
    return dict(zip(("nom", "date", "type", "distance", "denivele", "duree"), r))


def _km_a_la_photo(photo, points, debut):
    """Distance (km) parcourue au moment/lieu de la photo, ou None."""
    pos = ph.position_sur_trace(photo, points, debut)
    if not pos or not points:
        return None, pos
    import data.analyse_traces as at
    cumul, d, meilleur, idx = 0.0, 0.0, 1e18, 0
    for i, p in enumerate(points):
        if i:
            d += at._haversine_m(points[i - 1][0], points[i - 1][1], p[0], p[1])
        e = (p[0] - pos[0]) ** 2 + (p[1] - pos[1]) ** 2
        if e < meilleur:
            meilleur, idx, cumul = e, i, d
    return cumul / 1000.0, pos


class _Image(QLabel):
    def __init__(self):
        super().__init__()
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMinimumSize(500, 340)
        self.setStyleSheet("background: #05070A; border-radius: 10px;")
        self._pm = None

    def definir(self, chemin):
        lecteur = QImageReader(str(chemin))
        lecteur.setAutoTransform(True)
        img = lecteur.read()
        self._pm = QPixmap.fromImage(img) if not img.isNull() else None
        self._ajuster()

    def _ajuster(self):
        if self._pm is None:
            self.setText("Photo illisible")
            return
        self.setPixmap(self._pm.scaled(self.size(), Qt.AspectRatioMode.KeepAspectRatio,
                                       Qt.TransformationMode.SmoothTransformation))

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._ajuster()


class DialogueDiaporama(QDialog):
    """Diaporama automatique (4 s par photo) — flèches pour naviguer,
    Espace pour mettre en pause, Échap pour fermer."""

    DELAI_MS = 4000

    def __init__(self, activite_id, photos, parent=None):
        super().__init__(parent)
        self.photos = list(photos)
        self.index = 0
        self.info = _infos_sortie(activite_id)
        self.points = met.trace_de_activite(activite_id)
        self.setWindowTitle("Diaporama")
        self.resize(1100, 780)
        self.setStyleSheet(f"QDialog {{ background: #0B0D10; }} QLabel {{ color: {PALETTE['texte']}; }}"
                           f"QPushButton {{ background: {PALETTE['carte']}; color: {PALETTE['texte']}; border: 1px solid {PALETTE['bordure']};"
                           " border-radius: 8px; padding: 8px 16px; font-size: 14px; }}")
        lay = QVBoxLayout(self)
        self.titre = QLabel("")
        self.titre.setStyleSheet("font-size: 16px; font-weight: 700;")
        self.image = _Image()
        self.legende = QLabel("")
        self.legende.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.legende.setWordWrap(True)
        self.legende.setStyleSheet("font-size: 15px;")
        self.detail = QLabel("")
        self.detail.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.detail.setStyleSheet(f"color: {PALETTE['texte_secondaire']};")
        lay.addWidget(self.titre)
        lay.addWidget(self.image, 1)
        lay.addWidget(self.legende)
        lay.addWidget(self.detail)
        barre = QHBoxLayout()
        self.b_prec = QPushButton("◀")
        self.b_lecture = QPushButton("⏸ Pause")
        self.b_suiv = QPushButton("▶")
        self.b_fermer = QPushButton("Fermer")
        self.b_prec.clicked.connect(lambda: self.aller(-1))
        self.b_suiv.clicked.connect(lambda: self.aller(1))
        self.b_lecture.clicked.connect(self._basculer)
        self.b_fermer.clicked.connect(self.accept)
        barre.addStretch()
        for b in (self.b_prec, self.b_lecture, self.b_suiv, self.b_fermer):
            barre.addWidget(b)
        barre.addStretch()
        lay.addLayout(barre)
        self.minuteur = QTimer(self)
        self.minuteur.setInterval(self.DELAI_MS)
        self.minuteur.timeout.connect(lambda: self.aller(1, boucle=True))
        self._afficher()
        if len(self.photos) > 1:
            self.minuteur.start()
        else:
            self.b_lecture.setEnabled(False)

    def _basculer(self):
        if self.minuteur.isActive():
            self.minuteur.stop()
            self.b_lecture.setText("▶ Lecture")
        else:
            self.minuteur.start()
            self.b_lecture.setText("⏸ Pause")

    def aller(self, delta, boucle=False):
        n = len(self.photos)
        if not n:
            return
        self.index = (self.index + delta) % n if boucle or True else max(0, min(n - 1, self.index + delta))
        self._afficher()
        if self.minuteur.isActive():
            self.minuteur.start()

    def _afficher(self):
        if not self.photos:
            self.titre.setText("Aucune photo")
            return
        p = self.photos[self.index]
        self.titre.setText(f"{self.info.get('nom') or 'Sortie'} — photo {self.index + 1}/{len(self.photos)}")
        self.image.definir(ph.chemin_photo(p["fichier"]))
        self.legende.setText(p.get("legende") or "")
        morceaux = []
        if p.get("date_prise"):
            morceaux.append(p["date_prise"].replace("T", " ")[:16])
        km, _pos = _km_a_la_photo(p, self.points, self.info.get("date"))
        if km is not None:
            morceaux.append(f"au km {km:.1f}".replace(".", ","))
        self.detail.setText(" · ".join(morceaux))

    def keyPressEvent(self, e):
        k = e.key()
        if k == Qt.Key.Key_Right:
            self.aller(1)
        elif k == Qt.Key.Key_Left:
            self.aller(-1)
        elif k == Qt.Key.Key_Space:
            self._basculer()
        else:
            super().keyPressEvent(e)


# ----------------------------------------------------------------------
# Album PDF
# ----------------------------------------------------------------------

def _dessiner_trace(p, points, rect, couleur, epaisseur=4):
    if len(points) < 2:
        return
    lats = [q[0] for q in points]
    lons = [q[1] for q in points]
    cos = math.cos(math.radians(sum(lats) / len(lats)))
    xs = [(lo - min(lons)) * cos for lo in lons]
    ys = [max(lats) - la for la in lats]
    w, h = max(xs) or 1e-9, max(ys) or 1e-9
    echelle = min(rect.width() / w, rect.height() / h)
    ox = rect.left() + (rect.width() - w * echelle) / 2
    oy = rect.top() + (rect.height() - h * echelle) / 2
    pts = [QPointF(ox + x * echelle, oy + y * echelle) for x, y in zip(xs, ys)]
    p.setPen(QPen(QColor(couleur), epaisseur, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
    pas = max(1, len(pts) // 600)
    for a, b in zip(pts[::pas], pts[pas::pas]):
        p.drawLine(a, b)
    p.setBrush(QColor("#66BB6A"))
    p.setPen(Qt.PenStyle.NoPen)
    p.drawEllipse(pts[0], epaisseur * 1.6, epaisseur * 1.6)
    p.setBrush(QColor("#EF5350"))
    p.drawEllipse(pts[-1], epaisseur * 1.6, epaisseur * 1.6)


def exporter_album_pdf(activite_id, chemin_pdf):
    """PDF A4 paysage : couverture (tracé + chiffres) puis une photo par
    page avec légende. Renvoie le nombre de photos."""
    photos = ph.photos_de_sortie(activite_id)
    info = _infos_sortie(activite_id)
    points = met.trace_de_activite(activite_id)
    pdf = QPdfWriter(str(chemin_pdf))
    pdf.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
    pdf.setPageOrientation(QPageLayout.Orientation.Landscape)
    pdf.setPageMargins(QMarginsF(0, 0, 0, 0))
    pdf.setResolution(150)
    p = QPainter(pdf)
    L, H = pdf.width(), pdf.height()
    p.fillRect(0, 0, L, H, QColor("#0F1318"))
    f = QFont("Helvetica")
    f.setPixelSize(int(H * 0.07))
    f.setBold(True)
    p.setFont(f)
    p.setPen(QColor("#F3F6F7"))
    p.drawText(QRectF(L * 0.05, H * 0.06, L * 0.9, H * 0.12), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
               info.get("nom") or "Sortie")
    f.setBold(False)
    f.setPixelSize(int(H * 0.035))
    p.setFont(f)
    p.setPen(QColor("#9AA7AE"))
    detail = f"{(info.get('date') or '')[:10]} · {info.get('distance') or 0:.1f} km · {info.get('denivele') or 0} m D+ · {len(photos)} photo(s)"
    p.drawText(QRectF(L * 0.05, H * 0.17, L * 0.9, H * 0.07), Qt.AlignmentFlag.AlignLeft, detail.replace(".", ","))
    _dessiner_trace(p, points, QRectF(L * 0.1, H * 0.28, L * 0.8, H * 0.62), obtenir_couleur_accent(), 6)
    for ph_ in photos:
        pdf.newPage()
        p.fillRect(0, 0, L, H, QColor("#0F1318"))
        lecteur = QImageReader(str(ph.chemin_photo(ph_["fichier"])))
        lecteur.setAutoTransform(True)
        img = lecteur.read()
        if not img.isNull():
            zone = QRectF(L * 0.04, H * 0.04, L * 0.92, H * 0.84)
            e = min(zone.width() / img.width(), zone.height() / img.height())
            w, h = img.width() * e, img.height() * e
            p.drawImage(QRectF(zone.left() + (zone.width() - w) / 2, zone.top() + (zone.height() - h) / 2, w, h), img)
        f.setPixelSize(int(H * 0.035))
        p.setFont(f)
        p.setPen(QColor("#C9D2D6"))
        texte = " · ".join(x for x in (ph_.get("legende"), (ph_.get("date_prise") or "").replace("T", " ")[:16]) if x)
        p.drawText(QRectF(L * 0.04, H * 0.9, L * 0.92, H * 0.07), Qt.AlignmentFlag.AlignCenter, texte)
    p.end()
    return len(photos)


def choisir_et_exporter_album(parent, activite_id):
    info = _infos_sortie(activite_id)
    nom = (info.get("nom") or "sortie").replace("/", "-").replace(" ", "_")
    defaut = str(Path.home() / f"Album_{nom}_{(info.get('date') or '')[:10]}.pdf")
    chemin, _ = QFileDialog.getSaveFileName(parent, "Enregistrer l'album", defaut, "PDF (*.pdf)")
    if not chemin:
        return None
    n = exporter_album_pdf(activite_id, chemin)
    notifier(f"Album enregistré ({n} photo(s))", parent=parent)
    return chemin
