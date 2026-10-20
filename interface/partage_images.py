"""
Images à partager de la v98 :
  - rendre_fiche_sortie()    X2 — fiche d'une sortie (tracé, chiffres, profil), 1080 × 1350 px,
                             format portrait pour WhatsApp / Instagram
  - rendre_affiche_annee()   E8 — affiche de l'année : toutes tes sorties en petites vignettes de
                             tracés, tes totaux et ton rythme mois par mois (à imprimer en A3/A2)

Tout est dessiné avec QPainter à partir de tes données : rien ne quitte l'ordinateur.
"""

import json
import math
from datetime import date, datetime
from pathlib import Path

from PySide6.QtCore import Qt, QRectF, QPointF, QMarginsF
from PySide6.QtGui import (
    QImage, QPainter, QColor, QPen, QLinearGradient, QFont, QPainterPath, QBrush, QPdfWriter, QPageSize,
    QPageLayout, QImageReader, QGuiApplication, QRadialGradient,
)

import data.analyse_traces as at
import data.metriques as met
import data.photos_sorties as ph
from data.database import connexion
from interface.theme import obtenir_couleur_accent as _accent_brut, eclaircir, POLICE_TITRE, POLICE_TEXTE


def obtenir_couleur_accent():
    """Accent éclairci : lisible sur fond sombre."""
    return eclaircir(eclaircir(_accent_brut()))

MOIS_LONGS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre",
              "novembre", "décembre"]
JOURS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
FOND_HAUT, FOND_BAS = QColor("#0E1217"), QColor("#1A2530")


def _police(taille, gras=False, titre=False):
    f = QFont(POLICE_TITRE if titre else POLICE_TEXTE)
    f.setPixelSize(int(taille))
    f.setBold(gras)
    return f


def _virgule(v, d=1):
    return f"{v:.{d}f}".replace(".", ",")


def _duree(s):
    s = int(s or 0)
    h, r = divmod(s, 3600)
    return f"{h} h {r // 60:02d}" if h else f"{r // 60} min"


def _allure(duree_s, km):
    if not km or not duree_s:
        return "—"
    v = duree_s / 60 / km
    return f"{int(v)}:{round((v - int(v)) * 60):02d} /km"


def _projeter(points, rect, marge=0.0):
    """Points (lat, lon, …) -> QPointF dans rect (aspect conservé)."""
    lats = [q[0] for q in points]
    lons = [q[1] for q in points]
    cos = math.cos(math.radians(sum(lats) / len(lats)))
    xs = [(lo - min(lons)) * cos for lo in lons]
    ys = [max(lats) - la for la in lats]
    w, h = max(xs) or 1e-9, max(ys) or 1e-9
    e = min(rect.width() / w, rect.height() / h)
    ox = rect.left() + (rect.width() - w * e) / 2
    oy = rect.top() + (rect.height() - h * e) / 2
    return [QPointF(ox + x * e, oy + y * e) for x, y in zip(xs, ys)]


def _tracer(p, pts, couleur, epaisseur, extremites=True, degrade=None):
    if len(pts) < 2:
        return
    pas = max(1, len(pts) // 700)
    echant = pts[::pas] + ([pts[-1]] if (len(pts) - 1) % pas else [])
    chemin = QPainterPath(echant[0])
    for q in echant[1:]:
        chemin.lineTo(q)
    p.setBrush(Qt.BrushStyle.NoBrush)
    # halo
    halo = QColor(couleur)
    halo.setAlpha(55)
    p.setPen(QPen(halo, epaisseur * 2.6, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
    p.drawPath(chemin)
    p.setPen(QPen(QColor(couleur), epaisseur, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
    p.drawPath(chemin)
    if extremites:
        p.setPen(QPen(QColor("#0E1217"), epaisseur * 0.5))
        p.setBrush(QColor("#66BB6A"))
        p.drawEllipse(echant[0], epaisseur * 1.7, epaisseur * 1.7)
        p.setBrush(QColor("#EF5350"))
        p.drawEllipse(echant[-1], epaisseur * 1.7, epaisseur * 1.7)


def _fond(p, L, H):
    g = QLinearGradient(0, 0, 0, H)
    g.setColorAt(0, FOND_HAUT)
    g.setColorAt(1, FOND_BAS)
    p.fillRect(0, 0, L, H, g)


def _date_longue(d):
    try:
        dt = datetime.fromisoformat(str(d)[:19].replace(" ", "T"))
    except ValueError:
        return str(d)[:10]
    return f"{JOURS[dt.weekday()]} {dt.day} {MOIS_LONGS[dt.month - 1]} {dt.year} · {dt:%H:%M}"


# ======================================================================
# X2 — Fiche de sortie
# ======================================================================

def rendre_fiche_sortie(activite_id, avec_photo=True, largeur=1080, hauteur=1350):
    """QImage de la fiche (None si la sortie n'existe pas)."""
    conn = connexion()
    cur = conn.cursor()
    cur.execute("SELECT nom, date, type, distance, denivele, duree, frequence_cardiaque_moyenne, athlete_id "
                "FROM activites WHERE id=?", (activite_id,))
    r = cur.fetchone()
    conn.close()
    if not r:
        return None
    nom, d, type_, km, dplus, duree, fc, athlete_id = r
    points = met.trace_de_activite(activite_id)
    accent = obtenir_couleur_accent()
    img = QImage(largeur, hauteur, QImage.Format.Format_ARGB32)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    _fond(p, largeur, hauteur)

    photo = None
    if avec_photo:
        photos = ph.photos_de_sortie(activite_id)
        if photos:
            lect = QImageReader(str(ph.chemin_photo(photos[0]["fichier"])))
            lect.setAutoTransform(True)
            photo = lect.read()
            if photo.isNull():
                photo = None
    zone_carte = QRectF(70, 360, largeur - 140, 560)
    if photo is not None:
        e = max(largeur / photo.width(), 520 / photo.height())
        w, h = photo.width() * e, photo.height() * e
        p.save()
        p.setClipRect(QRectF(0, 0, largeur, 560))
        p.drawImage(QRectF((largeur - w) / 2, (560 - h) / 2, w, h), photo)
        p.restore()
        voile = QLinearGradient(0, 0, 0, 560)
        voile.setColorAt(0.0, QColor(14, 18, 23, 130))
        voile.setColorAt(1.0, QColor(14, 18, 23, 255))
        p.fillRect(0, 0, largeur, 560, voile)
        zone_carte = QRectF(largeur - 430, 640, 360, 280)  # tracé en vignette sur la photo

    # en-tête
    p.setPen(QColor(accent))
    p.setFont(_police(30, True, True))
    p.drawText(QRectF(70, 60, largeur - 140, 50), Qt.AlignmentFlag.AlignLeft, f"{(type_ or 'SORTIE').upper()}  ·  TRAILMASTER PRO")
    p.setPen(QColor("#F3F6F7"))
    p.setFont(_police(70, True, True))
    p.drawText(QRectF(70, 120, largeur - 140, 190), Qt.TextFlag.TextWordWrap | Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop,
               nom or "Sortie")
    p.setPen(QColor("#9AA7AE"))
    p.setFont(_police(30))
    p.drawText(QRectF(70, 310, largeur - 140, 44), Qt.AlignmentFlag.AlignLeft, _date_longue(d))

    # tracé
    if len(points) >= 2:
        pts = _projeter(points, zone_carte)
        _tracer(p, pts, accent, 9 if photo is None else 6)
    else:
        p.setPen(QColor("#5C6770"))
        p.setFont(_police(28))
        p.drawText(zone_carte, Qt.AlignmentFlag.AlignCenter, "Pas de tracé GPS")

    # profil d'altitude
    prof = at.profil(points) if len(points) > 3 else []
    if prof:
        zone = QRectF(70, 940, largeur - 140, 90)
        alts = [e["alt"] for e in prof]
        lo, hi = min(alts), max(alts)
        etendue = max(hi - lo, 10)
        chemin = QPainterPath(QPointF(zone.left(), zone.bottom()))
        pas = max(1, len(prof) // 400)
        for e in prof[::pas]:
            chemin.lineTo(zone.left() + e["d"] / prof[-1]["d"] * zone.width(),
                          zone.bottom() - (e["alt"] - lo) / etendue * zone.height())
        chemin.lineTo(zone.right(), zone.bottom())
        chemin.closeSubpath()
        c = QColor(accent)
        c.setAlpha(80)
        p.setPen(QPen(QColor(accent), 3))
        p.setBrush(c)
        p.drawPath(chemin)

    # chiffres
    cases = [("DISTANCE", f"{_virgule(km or 0)} km"), ("DÉNIVELÉ +", f"{int(dplus or 0)} m"), ("DURÉE", _duree(duree)),
             ("ALLURE", _allure(duree, km)), ("FC MOY.", f"{fc} bpm" if fc else "—"),
             ("VITESSE", f"{_virgule((km or 0) / (duree / 3600), 1)} km/h" if duree else "—")]
    l_case, h_case = (largeur - 140) / 3, 130
    for i, (lib, val) in enumerate(cases):
        x = 70 + (i % 3) * l_case
        y = 1070 + (i // 3) * (h_case + 12)
        p.setBrush(QColor(255, 255, 255, 14))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(QRectF(x + 4, y, l_case - 12, h_case), 18, 18)
        p.setPen(QColor("#9AA7AE"))
        p.setFont(_police(22, True))
        p.drawText(QRectF(x + 24, y + 14, l_case - 40, 30), Qt.AlignmentFlag.AlignLeft, lib)
        p.setPen(QColor("#F3F6F7"))
        p.setFont(_police(44, True, True))
        p.drawText(QRectF(x + 24, y + 52, l_case - 40, 64), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, val)
    p.end()
    return img


def enregistrer_image(img, chemin):
    return img.save(str(chemin), "PNG" if str(chemin).lower().endswith(".png") else "JPG", 95)


def copier_dans_presse_papiers(img):
    cb = QGuiApplication.clipboard()
    if cb is not None:
        cb.setImage(img)
        return True
    return False


# ======================================================================
# E8 — Affiche de l'année
# ======================================================================

def _traces_de_l_annee(athlete_id, annee, maxi=260):
    conn = connexion()
    cur = conn.cursor()
    cur.execute(
        "SELECT a.id, a.date, a.distance, a.type, p.trace_json FROM activites a "
        "JOIN parcours_gpx p ON p.activite_id=a.id WHERE a.athlete_id=? AND a.date>=? AND a.date<? "
        "AND p.trace_json IS NOT NULL ORDER BY a.date",
        (athlete_id, f"{annee}-01-01", f"{annee + 1}-01-01"))
    res = []
    for id_, d, km, type_, tj in cur.fetchall():
        try:
            pts = json.loads(tj)
        except (ValueError, TypeError):
            continue
        if isinstance(pts, list) and len(pts) > 5 and (km or 0) >= 1:
            pas = max(1, len(pts) // 120)
            res.append({"id": id_, "date": d, "km": km or 0, "type": type_, "points": pts[::pas]})
    conn.close()
    if len(res) > maxi:
        res = sorted(res, key=lambda t: -t["km"])[:maxi]
        res.sort(key=lambda t: t["date"])
    return res


def rendre_affiche_annee(athlete_id, annee, largeur=2400, hauteur=3400):
    """QImage de l'affiche. Contient : titre, vignettes de toutes les
    sorties avec trace, 4 totaux, rythme mensuel et records."""
    accent = obtenir_couleur_accent()
    conn = connexion()
    cur = conn.cursor()
    cur.execute("SELECT prenom, nom FROM athletes WHERE id=?", (athlete_id,))
    a = cur.fetchone() or ("", "")
    conn.close()
    prenom = a[0] or ""
    mois = met.totaux(athlete_id, "mois", 12) if annee == date.today().year else None
    # totaux par mois de l'année demandée
    par_mois = []
    for m in range(1, 13):
        debut = date(annee, m, 1)
        fin = date(annee + (m == 12), (m % 12) + 1, 1)
        fin = date.fromordinal(fin.toordinal() - 1)
        sorties = met.activites_periode(athlete_id, debut, fin)
        par_mois.append((sum(s["distance"] for s in sorties), len(sorties)))
    tout = met.activites_periode(athlete_id, date(annee, 1, 1), date(annee, 12, 31))
    km_tot = sum(s["distance"] for s in tout)
    d_tot = sum(s["denivele"] for s in tout)
    h_tot = sum(s["duree"] for s in tout) / 3600
    jours_actifs = len({s["jour"] for s in tout if s["jour"]})
    plus_longue = max(tout, key=lambda s: s["distance"], default=None)
    plus_gros = max(tout, key=lambda s: s["denivele"], default=None)

    img = QImage(largeur, hauteur, QImage.Format.Format_ARGB32)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
    _fond(p, largeur, hauteur)
    marge = 140

    p.setPen(QColor(accent))
    p.setFont(_police(56, True, True))
    p.drawText(QRectF(marge, 110, largeur - 2 * marge, 80), Qt.AlignmentFlag.AlignLeft, "TRAILMASTER PRO")
    p.setPen(QColor("#F3F6F7"))
    p.setFont(_police(250, True, True))
    p.drawText(QRectF(marge, 190, largeur - 2 * marge, 300), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, str(annee))
    p.setPen(QColor("#9AA7AE"))
    p.setFont(_police(66))
    p.drawText(QRectF(marge, 490, largeur - 2 * marge, 90), Qt.AlignmentFlag.AlignLeft,
               f"L'année de {prenom}" if prenom else "Mon année")

    # vignettes de tracés
    traces = _traces_de_l_annee(athlete_id, annee)
    zone = QRectF(marge, 660, largeur - 2 * marge, 1500)
    if traces:
        n = len(traces)
        ratio = zone.width() / zone.height()
        cols = max(1, int(math.ceil(math.sqrt(n * ratio))))
        lignes = int(math.ceil(n / cols))
        while lignes * (zone.width() / cols) > zone.height() * 1.0 and cols < n:
            cols += 1
            lignes = int(math.ceil(n / cols))
        cote = min(zone.width() / cols, zone.height() / lignes)
        x0 = zone.left() + (zone.width() - cote * cols) / 2
        km_max = max(t["km"] for t in traces) or 1
        for i, t in enumerate(traces):
            cx = x0 + (i % cols) * cote
            cy = zone.top() + (i // cols) * cote
            taille = cote * (0.45 + 0.5 * math.sqrt(t["km"] / km_max))
            r = QRectF(cx + (cote - taille) / 2, cy + (cote - taille) / 2, taille, taille)
            pts = _projeter(t["points"], r)
            couleur = {"Trail": accent, "Course": "#42A5F5", "Randonnée": "#FFA726", "VTT": "#AB47BC", "Vélo": "#26C6DA"}.get(t["type"], "#9AA7AE")
            _tracer(p, pts, couleur, max(2.0, cote / 30), extremites=False)
    else:
        p.setPen(QColor("#5C6770"))
        p.setFont(_police(60))
        p.drawText(zone, Qt.AlignmentFlag.AlignCenter, "Aucune trace GPS cette année-là")

    # totaux
    y = 2260
    blocs = [("KILOMÈTRES", f"{km_tot:,.0f}".replace(",", " ")), ("DÉNIVELÉ + (M)", f"{d_tot:,.0f}".replace(",", " ")),
             ("HEURES", f"{h_tot:,.0f}".replace(",", " ")), ("SORTIES", str(len(tout)))]
    l_b = (largeur - 2 * marge) / 4
    for i, (lib, val) in enumerate(blocs):
        x = marge + i * l_b
        p.setPen(QColor("#9AA7AE"))
        p.setFont(_police(40, True))
        p.drawText(QRectF(x, y, l_b, 56), Qt.AlignmentFlag.AlignLeft, lib)
        p.setPen(QColor("#F3F6F7"))
        p.setFont(_police(130, True, True))
        p.drawText(QRectF(x, y + 56, l_b, 170), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, val)

    # rythme mensuel
    zone_b = QRectF(marge, 2600, largeur - 2 * marge, 380)
    vmax = max([k for k, _ in par_mois] + [1])
    l_m = zone_b.width() / 12
    for i, (k, nb) in enumerate(par_mois):
        h = zone_b.height() * 0.8 * (k / vmax)
        r = QRectF(zone_b.left() + i * l_m + l_m * 0.12, zone_b.bottom() - 60 - h, l_m * 0.76, max(h, 4))
        c = QColor(accent)
        c.setAlpha(230 if k else 60)
        p.setBrush(c)
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(r, 10, 10)
        p.setPen(QColor("#9AA7AE"))
        p.setFont(_police(36))
        p.drawText(QRectF(zone_b.left() + i * l_m, zone_b.bottom() - 52, l_m, 50), Qt.AlignmentFlag.AlignCenter,
                   MOIS_LONGS[i][:3].upper() if i != 5 and i != 6 else MOIS_LONGS[i][:4].upper())
        if k:
            p.setFont(_police(34, True))
            p.setPen(QColor("#F3F6F7"))
            p.drawText(QRectF(zone_b.left() + i * l_m, r.top() - 48, l_m, 44), Qt.AlignmentFlag.AlignCenter, f"{k:.0f}")

    # records
    p.setPen(QColor("#9AA7AE"))
    p.setFont(_police(44))
    lignes_rec = []
    if plus_longue:
        lignes_rec.append(f"Plus longue sortie : {_virgule(plus_longue['distance'])} km  ({str(plus_longue['date'])[:10]})")
    if plus_gros:
        lignes_rec.append(f"Plus gros dénivelé : {int(plus_gros['denivele'])} m  ({str(plus_gros['date'])[:10]})")
    lignes_rec.append(f"{jours_actifs} jours d'activité sur {366 if annee % 4 == 0 else 365}")
    for i, t in enumerate(lignes_rec):
        p.drawText(QRectF(marge, 3030 + i * 70, largeur - 2 * marge, 66), Qt.AlignmentFlag.AlignLeft, t)
    p.end()
    return img


def enregistrer_affiche_pdf(img, chemin_pdf, format_page=QPageSize.PageSizeId.A3):
    pdf = QPdfWriter(str(chemin_pdf))
    pdf.setPageSize(QPageSize(format_page))
    pdf.setPageMargins(QMarginsF(0, 0, 0, 0))
    pdf.setResolution(300)
    p = QPainter(pdf)
    L, H = pdf.width(), pdf.height()
    e = min(L / img.width(), H / img.height())
    p.drawImage(QRectF((L - img.width() * e) / 2, (H - img.height() * e) / 2, img.width() * e, img.height() * e), img)
    p.end()


# ======================================================================
# Interface : aperçu + enregistrement
# ======================================================================

from PySide6.QtWidgets import (  # noqa: E402
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFileDialog, QCheckBox, QSpinBox, QComboBox,
)
from PySide6.QtGui import QPixmap  # noqa: E402
from interface.forme_evolution import _EcranAthlete  # noqa: E402
from interface.outils_ui import notifier  # noqa: E402


class DialogueFicheSortie(QDialog):
    """X2 — aperçu de la fiche, avec ou sans photo, enregistrer / copier."""

    def __init__(self, activite_id, parent=None):
        super().__init__(parent)
        self.activite_id = activite_id
        self.setWindowTitle("Fiche de sortie à partager")
        self.resize(620, 860)
        lay = QVBoxLayout(self)
        self.apercu = QLabel()
        self.apercu.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self.apercu, 1)
        self.case_photo = QCheckBox("Utiliser la première photo de la sortie en fond (si elle en a)")
        self.case_photo.setChecked(True)
        self.case_photo.toggled.connect(self._rendre)
        lay.addWidget(self.case_photo)
        barre = QHBoxLayout()
        b1 = QPushButton("💾 Enregistrer l'image…")
        b1.setObjectName("boutonPrincipal")
        b1.clicked.connect(self._enregistrer)
        b2 = QPushButton("📋 Copier")
        b2.clicked.connect(self._copier)
        b3 = QPushButton("Fermer")
        b3.clicked.connect(self.accept)
        for b in (b1, b2, b3):
            barre.addWidget(b)
        lay.addLayout(barre)
        self.img = None
        self._rendre()

    def _rendre(self):
        self.img = rendre_fiche_sortie(self.activite_id, self.case_photo.isChecked())
        if self.img is not None:
            self.apercu.setPixmap(QPixmap.fromImage(self.img).scaled(
                560, 720, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))

    def _enregistrer(self):
        if self.img is None:
            return
        defaut = str(Path.home() / f"Sortie_{self.activite_id}.png")
        chemin, _ = QFileDialog.getSaveFileName(self, "Enregistrer la fiche", defaut, "Image PNG (*.png);;Image JPEG (*.jpg)")
        if chemin:
            enregistrer_image(self.img, chemin)
            notifier("Image enregistrée", parent=self)

    def _copier(self):
        if self.img is not None and copier_dans_presse_papiers(self.img):
            notifier("Image copiée : colle-la dans un message", parent=self)


class AfficheAnnuelle(_EcranAthlete):
    """E8 — affiche de l'année."""

    def __init__(self, athlete_id_initial=None):
        super().__init__("🖼️  Affiche de mon année",
                         "Toutes tes sorties de l'année en petites vignettes de tracés, tes totaux et ton rythme mois par mois : "
                         "une affiche à enregistrer en image ou à imprimer en PDF (A3).", athlete_id_initial)
        self.spin = QSpinBox()
        self.spin.setRange(2000, 2100)
        self.spin.setValue(date.today().year)
        self.spin.valueChanged.connect(self.actualiser)
        self.barre.insertWidget(2, QLabel("Année :"))
        self.barre.insertWidget(3, self.spin)
        b1 = QPushButton("💾 Image PNG…")
        b1.clicked.connect(self._png)
        b2 = QPushButton("🖨️ PDF A3…")
        b2.clicked.connect(self._pdf)
        self.barre.addWidget(b1)
        self.barre.addWidget(b2)
        self.apercu = QLabel("")
        self.apercu.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
        self.principal.addWidget(self.apercu, 1)
        self.img = None
        self._finaliser()

    def actualiser(self):
        a = self.athlete_id
        if a is None:
            self.apercu.clear()
            self.img = None
            return
        self.img = rendre_affiche_annee(a, self.spin.value())
        self.apercu.setPixmap(QPixmap.fromImage(self.img).scaled(
            720, 1020, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))

    def _png(self):
        if self.img is None:
            return
        chemin, _ = QFileDialog.getSaveFileName(self, "Enregistrer l'affiche",
                                                str(Path.home() / f"Affiche_{self.spin.value()}.png"), "Image PNG (*.png)")
        if chemin:
            enregistrer_image(self.img, chemin)
            notifier("Affiche enregistrée", parent=self)

    def _pdf(self):
        if self.img is None:
            return
        chemin, _ = QFileDialog.getSaveFileName(self, "Enregistrer le PDF",
                                                str(Path.home() / f"Affiche_{self.spin.value()}.pdf"), "PDF (*.pdf)")
        if chemin:
            enregistrer_affiche_pdf(self.img, chemin)
            notifier("PDF enregistré (A3)", parent=self)
