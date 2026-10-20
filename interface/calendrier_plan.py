"""
E1 — Calendrier du plan par glisser-déposer : les séances prévues sont des
pastilles qu'on attrape à la souris et qu'on dépose sur un autre jour ; les
sorties réalisées et les courses apparaissent en lecture seule.
"""

from datetime import date, timedelta
import calendar

from PySide6.QtCore import Qt, QMimeData
from PySide6.QtGui import QDrag
from PySide6.QtWidgets import QFrame, QGridLayout, QLabel, QPushButton, QVBoxLayout, QHBoxLayout, QWidget

from data.database import connexion
from interface.forme_evolution import _EcranAthlete
from interface.outils_ui import notifier
import data.metriques as met

MIME = "application/x-trailmaster-seance"
MOIS = ["Janvier", "Février", "Mars", "Avril", "Mai", "Juin", "Juillet", "Août", "Septembre", "Octobre", "Novembre", "Décembre"]
JOURS = ["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"]


class Pastille(QLabel):
    def __init__(self, texte, seance_id=None, couleur="#2E7D32", tip=""):
        super().__init__(texte)
        self.seance_id = seance_id
        self.setToolTip(tip or texte)
        mobile = seance_id is not None
        self.setStyleSheet(f"background:{couleur}; color:white; border-radius:4px; padding:1px 5px; font-size:11px;"
                           + ("" if mobile else " opacity:0.7;"))
        if mobile:
            self.setCursor(Qt.CursorShape.OpenHandCursor)

    def mousePressEvent(self, e):
        if self.seance_id is None or e.button() != Qt.MouseButton.LeftButton:
            return super().mousePressEvent(e)
        drag = QDrag(self)
        mime = QMimeData()
        mime.setData(MIME, str(self.seance_id).encode())
        drag.setMimeData(mime)
        drag.setPixmap(self.grab())
        drag.exec(Qt.DropAction.MoveAction)


class CaseJour(QFrame):
    def __init__(self, jour, ecran, courant):
        super().__init__()
        self.jour, self.ecran = jour, ecran
        self.setAcceptDrops(True)
        self.setObjectName("caseJour")
        self.setMinimumHeight(92)
        self.lay = QVBoxLayout(self)
        self.lay.setContentsMargins(4, 3, 4, 3)
        self.lay.setSpacing(2)
        n = QLabel(str(jour.day))
        aujourd = jour == date.today()
        n.setStyleSheet(f"font-weight:{'800' if aujourd else '500'}; {'color:#2E7D32;' if aujourd else ('' if courant else 'color:#888;')} background:transparent;")
        self.lay.addWidget(n)
        self.lay.addStretch(1)
        self._style(False)
        if not courant:
            self.setEnabled(True)

    def _style(self, survol):
        self.setStyleSheet("#caseJour { border:1px solid " + ("#2E7D32" if survol else "rgba(128,128,128,0.35)") +
                           "; border-radius:6px; background:" + ("rgba(46,125,50,0.15)" if survol else "transparent") + "; }")

    def ajouter(self, w):
        self.lay.insertWidget(self.lay.count() - 1, w)

    def dragEnterEvent(self, e):
        if e.mimeData().hasFormat(MIME):
            e.acceptProposedAction()
            self._style(True)

    def dragLeaveEvent(self, e):
        self._style(False)

    def dropEvent(self, e):
        self._style(False)
        sid = int(bytes(e.mimeData().data(MIME)).decode())
        e.acceptProposedAction()
        self.ecran.deplacer(sid, self.jour)


def deplacer_seance(seance_id, jour):
    conn = connexion()
    cur = conn.cursor()
    cur.execute("UPDATE seances_structurees SET date_prevue=? WHERE id=? AND statut='Prévue'", (jour.isoformat(), seance_id))
    ok = cur.rowcount > 0
    conn.commit()
    conn.close()
    return ok


class CalendrierPlan(_EcranAthlete):

    def __init__(self, athlete_id_initial=None):
        super().__init__("🗓️  Calendrier du plan",
                         "Glisse une séance prévue sur un autre jour pour la déplacer. Les sorties faites (gris) et les courses (orange) sont affichées pour repère.",
                         athlete_id_initial)
        self.mois = date.today().replace(day=1)
        nav = QHBoxLayout()
        self.prec, self.suiv = QPushButton("◀"), QPushButton("▶")
        self.auj = QPushButton("Aujourd'hui")
        self.titre = QLabel("")
        self.titre.setStyleSheet("font-size:18px; font-weight:700;")
        self.prec.clicked.connect(lambda: self._aller(-1))
        self.suiv.clicked.connect(lambda: self._aller(1))
        self.auj.clicked.connect(lambda: self._aller(0))
        for w in (self.prec, self.titre, self.suiv):
            nav.addWidget(w)
        nav.addStretch(1)
        nav.addWidget(self.auj)
        self.principal.addLayout(nav)
        self.grille_w = QWidget()
        self.grille = QGridLayout(self.grille_w)
        self.grille.setSpacing(4)
        self.principal.addWidget(self.grille_w)
        self.principal.addStretch(1)
        self._finaliser()

    def _aller(self, d):
        if d == 0:
            self.mois = date.today().replace(day=1)
        else:
            m = self.mois.month - 1 + d
            self.mois = date(self.mois.year + m // 12, m % 12 + 1, 1)
        self.actualiser()

    def deplacer(self, seance_id, jour):
        if deplacer_seance(seance_id, jour):
            notifier(f"Séance déplacée au {jour.day}/{jour.month}", parent=self)
        self.actualiser()

    def actualiser(self):
        while self.grille.count():
            it = self.grille.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        self.titre.setText(f"{MOIS[self.mois.month - 1]} {self.mois.year}")
        for i, j in enumerate(JOURS):
            l = QLabel(j)
            l.setAlignment(Qt.AlignmentFlag.AlignCenter)
            l.setObjectName("texteSecondaire")
            self.grille.addWidget(l, 0, i)
        a = self.athlete_id
        premier = self.mois - timedelta(days=self.mois.weekday())
        fin_mois = (self.mois.replace(day=calendar.monthrange(self.mois.year, self.mois.month)[1]))
        nb_sem = ((fin_mois - premier).days // 7) + 1
        dernier = premier + timedelta(days=7 * nb_sem - 1)
        seances, faites, courses = {}, {}, {}
        if a is not None:
            conn = connexion()
            cur = conn.cursor()
            cur.execute("SELECT id, nom, type_seance, date_prevue, statut FROM seances_structurees WHERE athlete_id=? "
                        "AND date_prevue>=? AND date_prevue<=?", (a, premier.isoformat(), dernier.isoformat() + "z"))
            for sid, nom, typ, dp, st in cur.fetchall():
                try:
                    seances.setdefault(date.fromisoformat(str(dp)[:10]), []).append((sid, nom, typ, st))
                except ValueError:
                    pass
            conn.close()
            for s in met.activites_periode(a, premier, dernier):
                if s["jour"]:
                    faites.setdefault(s["jour"], []).append(s)
            for c in met.courses_a_venir(a):
                try:
                    courses.setdefault(date.fromisoformat(str(c["date"])[:10]), []).append(c)
                except ValueError:
                    pass
        for k in range(nb_sem * 7):
            j = premier + timedelta(days=k)
            case = CaseJour(j, self, j.month == self.mois.month)
            for s in faites.get(j, []):
                case.ajouter(Pastille(f"✓ {s['type'] or ''} {s['distance']:.1f} km", None, "#7a7a7a", s["nom"] or ""))
            for sid, nom, typ, st in seances.get(j, []):
                if st == "Prévue":
                    case.ajouter(Pastille(nom or typ or "Séance", sid, "#2E7D32", f"{nom} — glisse pour déplacer"))
                else:
                    case.ajouter(Pastille(f"✓ {nom}", None, "#5b8a5e", nom or ""))
            for c in courses.get(j, []):
                case.ajouter(Pastille(f"🏁 {c['nom'][:22]}", None, "#E07B00", c["nom"]))
            self.grille.addWidget(case, k // 7 + 1, k % 7)
