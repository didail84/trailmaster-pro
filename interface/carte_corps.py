"""
S9 — Carte du corps : une silhouette (face et dos) où l'on voit d'un coup
d'œil où l'on a déjà été blessé, et où l'on clique pour ajouter ou
consulter une blessure. Les blessures déjà saisies en texte libre dans
l'onglet Blessures (« genou droit », « tendon d'Achille »…) sont
reconnues par leurs mots-clés.
"""

import unicodedata
from datetime import date

from PySide6.QtCore import Qt, QRectF, QPointF, Signal
from PySide6.QtGui import QPainter, QColor, QPen, QPainterPath, QBrush, QFont
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QListWidget, QPushButton, QDialog, QFormLayout,
    QLineEdit, QComboBox, QDialogButtonBox, QFrame,
)

from data.database import connexion
from interface.forme_evolution import _EcranAthlete
from interface.theme import PALETTE, obtenir_couleur_accent
from interface.outils_ui import notifier

# id -> (libellé, vue, rectangle (x, y, l, h) dans un repère 100 x 210, forme)
ZONES = {
    "epaule_g": ("Épaule gauche", "face", (62, 32, 16, 14), "ellipse"),
    "epaule_d": ("Épaule droite", "face", (22, 32, 16, 14), "ellipse"),
    "hanche_g": ("Hanche gauche", "face", (52, 80, 18, 14), "ellipse"),
    "hanche_d": ("Hanche droite", "face", (30, 80, 18, 14), "ellipse"),
    "cuisse_g": ("Cuisse gauche (quadriceps)", "face", (52, 94, 17, 34), "rect"),
    "cuisse_d": ("Cuisse droite (quadriceps)", "face", (31, 94, 17, 34), "rect"),
    "genou_g": ("Genou gauche", "face", (53, 128, 15, 14), "ellipse"),
    "genou_d": ("Genou droit", "face", (32, 128, 15, 14), "ellipse"),
    "tibia_g": ("Tibia gauche", "face", (54, 142, 13, 30), "rect"),
    "tibia_d": ("Tibia droit", "face", (33, 142, 13, 30), "rect"),
    "cheville_g": ("Cheville gauche", "face", (54, 172, 13, 10), "ellipse"),
    "cheville_d": ("Cheville droite", "face", (33, 172, 13, 10), "ellipse"),
    "pied_g": ("Pied gauche", "face", (53, 183, 16, 12), "ellipse"),
    "pied_d": ("Pied droit", "face", (31, 183, 16, 12), "ellipse"),
    "dos_haut": ("Haut du dos", "dos", (35, 32, 30, 24), "rect"),
    "lombaires": ("Lombaires", "dos", (38, 58, 24, 20), "rect"),
    "fessier_g": ("Fessier gauche", "dos", (31, 80, 18, 16), "ellipse"),
    "fessier_d": ("Fessier droit", "dos", (51, 80, 18, 16), "ellipse"),
    "ischio_g": ("Ischio-jambiers gauches", "dos", (31, 96, 17, 32), "rect"),
    "ischio_d": ("Ischio-jambiers droits", "dos", (52, 96, 17, 32), "rect"),
    "mollet_g": ("Mollet gauche", "dos", (32, 135, 15, 28), "rect"),
    "mollet_d": ("Mollet droit", "dos", (53, 135, 15, 28), "rect"),
    "achille_g": ("Tendon d'Achille gauche", "dos", (34, 163, 11, 20), "rect"),
    "achille_d": ("Tendon d'Achille droit", "dos", (55, 163, 11, 20), "rect"),
}

# Mots-clés (sans accent, minuscules) -> préfixe de zone. L'ordre compte :
# le premier qui correspond gagne.
MOTS_CLES = [
    ("achille", "achille"), ("mollet", "mollet"), ("soleaire", "mollet"), ("jumeau", "mollet"),
    ("ischio", "ischio"), ("fessier", "fessier"), ("piriforme", "fessier"), ("lombaire", "lombaires"),
    ("bas du dos", "lombaires"), ("dos", "dos_haut"), ("cervical", "dos_haut"), ("trapeze", "dos_haut"),
    ("quadriceps", "cuisse"), ("cuisse", "cuisse"), ("adducteur", "hanche"), ("aine", "hanche"),
    ("hanche", "hanche"), ("psoas", "hanche"), ("fascia", "pied"), ("plantaire", "pied"),
    ("voute", "pied"), ("metatars", "pied"), ("orteil", "pied"), ("pied", "pied"),
    ("cheville", "cheville"), ("tibia", "tibia"), ("periost", "tibia"), ("genou", "genou"),
    ("rotul", "genou"), ("tfl", "genou"), ("bandelette", "genou"), ("menisque", "genou"),
    ("epaule", "epaule"),
]


def _norm(t):
    t = unicodedata.normalize("NFD", (t or "").lower())
    return "".join(c for c in t if unicodedata.category(c) != "Mn")


def zones_pour_texte(texte):
    """Texte libre (« Genou droit », « tendon d'Achille ») -> liste d'ids de zone."""
    t = _norm(texte)
    prefixe = next((p for mot, p in MOTS_CLES if mot in t), None)
    if prefixe is None:
        return []
    gauche, droit = "gauche" in t, "droit" in t
    candidats = [z for z in ZONES if z == prefixe or z.rsplit("_", 1)[0] == prefixe]
    if len(candidats) == 1:
        return candidats
    if gauche and not droit:
        return [z for z in candidats if z.endswith("_g")]
    if droit and not gauche:
        return [z for z in candidats if z.endswith("_d")]
    return candidats


def blessures_par_zone(athlete_id):
    """{zone_id: [dict blessure, …]} d'après les blessures saisies."""
    conn = connexion()
    cur = conn.cursor()
    cur.execute("SELECT id, date_debut, date_fin, zone_corporelle, type_blessure, gravite, statut "
                "FROM blessures WHERE athlete_id=? ORDER BY date_debut DESC", (athlete_id,))
    res, sans_zone = {}, []
    for r in cur.fetchall():
        b = dict(zip(("id", "debut", "fin", "zone", "type", "gravite", "statut"), r))
        zs = zones_pour_texte(f"{b['zone']} {b['type'] or ''}")
        if not zs:
            sans_zone.append(b)
        for z in zs:
            res.setdefault(z, []).append(b)
    conn.close()
    return res, sans_zone


class SilhouetteWidget(QWidget):
    zone_cliquee = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(520, 460)
        self.setMouseTracking(True)
        self.donnees = {}
        self.selection = None
        self._survol = None

    def definir_donnees(self, par_zone):
        self.donnees = par_zone
        self.update()

    # géométrie : deux silhouettes côte à côte (face puis dos)
    def _echelle(self):
        h = self.height() - 40
        e = min(h / 210.0, (self.width() / 2 - 20) / 100.0)
        return e, (self.width() / 2 - 100 * e) / 2, 28

    def _rect_zone(self, zid):
        _l, vue, (x, y, w, h), forme = ZONES[zid]
        e, ox, oy = self._echelle()
        if vue == "dos":
            ox += self.width() / 2
        return QRectF(ox + x * e, oy + y * e, w * e, h * e), forme

    def _zone_a(self, pos):
        for zid in ZONES:
            r, forme = self._rect_zone(zid)
            if forme == "ellipse":
                chemin = QPainterPath()
                chemin.addEllipse(r)
                if chemin.contains(pos):
                    return zid
            elif r.contains(pos):
                return zid
        return None

    def mouseMoveEvent(self, ev):
        z = self._zone_a(ev.position())
        if z != self._survol:
            self._survol = z
            self.setCursor(Qt.CursorShape.PointingHandCursor if z else Qt.CursorShape.ArrowCursor)
            self.setToolTip(ZONES[z][0] if z else "")
            self.update()

    def mousePressEvent(self, ev):
        z = self._zone_a(ev.position())
        if z:
            self.selection = z
            self.zone_cliquee.emit(z)
            self.update()

    def _silhouette(self, p, ox, e, oy):
        p.setPen(QPen(QColor(PALETTE["bordure"]), 1.5))
        p.setBrush(QColor(PALETTE["carte"]))
        def R(x, y, w, h, r=6):
            p.drawRoundedRect(QRectF(ox + x * e, oy + y * e, w * e, h * e), r * e / 2, r * e / 2)
        p.drawEllipse(QRectF(ox + 41 * e, oy + 4 * e, 18 * e, 22 * e))      # tête
        R(44, 24, 12, 8, 4)                                                  # cou
        R(30, 30, 40, 52, 10)                                                # torse
        R(14, 32, 14, 56, 8)                                                 # bras d
        R(72, 32, 14, 56, 8)                                                 # bras g
        R(29, 80, 42, 18, 8)                                                 # bassin
        R(30, 94, 19, 40, 8); R(51, 94, 19, 40, 8)                           # cuisses
        R(31, 134, 17, 46, 8); R(52, 134, 17, 46, 8)                         # jambes
        R(29, 180, 20, 14, 6); R(51, 180, 20, 14, 6)                         # pieds

    def paintEvent(self, ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), QColor(PALETTE["fond"]))
        e, ox, oy = self._echelle()
        self._silhouette(p, ox, e, oy)
        self._silhouette(p, ox + self.width() / 2, e, oy)
        p.setPen(QColor(PALETTE["texte_secondaire"]))
        f = QFont(p.font()); f.setPointSizeF(10); p.setFont(f)
        p.drawText(QRectF(0, 4, self.width() / 2, 20), Qt.AlignmentFlag.AlignCenter, "FACE")
        p.drawText(QRectF(self.width() / 2, 4, self.width() / 2, 20), Qt.AlignmentFlag.AlignCenter, "DOS")

        for zid, (_l, _v, _g, forme) in ZONES.items():
            r, _ = self._rect_zone(zid)
            liste = self.donnees.get(zid, [])
            en_cours = any(b["statut"] != "Guérie" for b in liste)
            if liste:
                n = min(len(liste), 4)
                couleur = QColor("#EF5350") if en_cours else QColor("#FFA726")
                couleur.setAlpha(80 + n * 40)
            else:
                couleur = QColor(255, 255, 255, 14 if self._survol != zid else 70)
            p.setBrush(QBrush(couleur))
            contour = QColor(obtenir_couleur_accent()) if self.selection == zid else QColor(255, 255, 255, 40)
            p.setPen(QPen(contour, 2 if self.selection == zid else 1))
            if forme == "ellipse":
                p.drawEllipse(r)
            else:
                p.drawRoundedRect(r, 5, 5)
            if len(liste) > 1:
                p.setPen(QColor("white"))
                p.drawText(r, Qt.AlignmentFlag.AlignCenter, str(len(liste)))
        p.end()


class DialogueNouvelleBlessureZone(QDialog):
    def __init__(self, libelle_zone, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Blessure : {libelle_zone}")
        f = QFormLayout(self)
        self.type = QLineEdit()
        self.type.setPlaceholderText("ex. tendinite, contracture, douleur…")
        self.gravite = QComboBox(); self.gravite.addItems(["Légère", "Modérée", "Sévère"])
        self.statut = QComboBox(); self.statut.addItems(["En cours", "En reprise", "Guérie"])
        f.addRow("Type :", self.type)
        f.addRow("Gravité :", self.gravite)
        f.addRow("Statut :", self.statut)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        f.addRow(bb)


class CarteCorps(_EcranAthlete):

    def __init__(self, athlete_id_initial=None):
        super().__init__(
            "🧍  Carte du corps",
            "Où as-tu eu mal ? Rouge : blessure en cours ; orange : déjà soignée (plus c'est foncé, plus "
            "c'est fréquent). Clique sur une zone pour voir son historique ou y ajouter une blessure.",
            athlete_id_initial,
        )
        corps = QHBoxLayout()
        self.silhouette = SilhouetteWidget()
        self.silhouette.zone_cliquee.connect(self._zone)
        corps.addWidget(self.silhouette, 3)
        droite = QVBoxLayout()
        self.titre_zone = QLabel("Clique sur une zone")
        self.titre_zone.setObjectName("titreCarte")
        self.liste = QListWidget()
        self.bouton_ajout = QPushButton("➕ Ajouter une blessure ici")
        self.bouton_ajout.setObjectName("boutonPrincipal")
        self.bouton_ajout.setEnabled(False)
        self.bouton_ajout.clicked.connect(self._ajouter)
        self.note = QLabel("")
        self.note.setObjectName("texteSecondaire")
        self.note.setWordWrap(True)
        droite.addWidget(self.titre_zone)
        droite.addWidget(self.liste, 1)
        droite.addWidget(self.bouton_ajout)
        droite.addWidget(self.note)
        corps.addLayout(droite, 2)
        self.principal.addLayout(corps, 1)
        self.par_zone = {}
        self._finaliser()

    def actualiser(self):
        a = self.athlete_id
        self.liste.clear()
        self.silhouette.selection = None
        self.bouton_ajout.setEnabled(False)
        self.titre_zone.setText("Clique sur une zone")
        if a is None:
            self.par_zone = {}
            self.silhouette.definir_donnees({})
            return
        self.par_zone, sans = blessures_par_zone(a)
        self.silhouette.definir_donnees(self.par_zone)
        self.note.setText(f"{len(sans)} blessure(s) dont la zone n'a pas été reconnue (non placée sur la carte)."
                          if sans else "")

    def _zone(self, zid):
        self.titre_zone.setText(ZONES[zid][0])
        self.bouton_ajout.setEnabled(True)
        self.liste.clear()
        liste = self.par_zone.get(zid, [])
        if not liste:
            self.liste.addItem("Aucune blessure enregistrée ici. 👍")
        for b in liste:
            fin = f" → {b['fin']}" if b["fin"] else ""
            self.liste.addItem(f"{b['debut']}{fin} · {b['type'] or 'blessure'} · {b['gravite'] or '—'} · {b['statut']}")

    def _ajouter(self):
        zid = self.silhouette.selection
        if not zid or self.athlete_id is None:
            return
        d = DialogueNouvelleBlessureZone(ZONES[zid][0], self)
        if d.exec():
            conn = connexion()
            conn.execute("INSERT INTO blessures (athlete_id, date_debut, zone_corporelle, type_blessure, gravite, statut) "
                         "VALUES (?,?,?,?,?,?)",
                         (self.athlete_id, date.today().isoformat(), ZONES[zid][0], d.type.text().strip(),
                          d.gravite.currentText(), d.statut.currentText()))
            conn.commit()
            conn.close()
            notifier("Blessure ajoutée", parent=self)
            self.par_zone, _ = blessures_par_zone(self.athlete_id)
            self.silhouette.definir_donnees(self.par_zone)
            self._zone(zid)
