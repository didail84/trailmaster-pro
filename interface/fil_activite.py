"""
Fil d'activité (Trail Hub Center) : tes sorties en cartes, comme sur
Strava — titre, chiffres clés, tracé, photos, ressenti — et sous chaque
sortie son analyse, écrite automatiquement dès réception de la sortie
(IA si une clé est réglée, sinon analyse hors ligne par les règles).

Ouvrir le fil suffit : les sorties affichées qui n'ont pas encore
d'analyse la reçoivent l'une après l'autre, sans bouton à presser.
Un clic sur une carte ouvre la fiche complète de la sortie.
"""

import json
import os
from datetime import date, datetime, timedelta

from PySide6.QtCore import Qt, QPointF, QThread, Signal
from PySide6.QtGui import QPainter, QPen, QColor, QPixmap, QPolygonF
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget, QSizePolicy,
)

import noyau.entrainement.metriques as met
from data import photos_sorties
from noyau.donnees import parcours as dparc
from noyau.ia import analyse_auto as aa
from interface.forme_evolution import _EcranAthlete
from interface.detail_sortie import style_sombre
from interface.journal import JOURS, MOIS, ICONES_TYPE, A_TEXTE, A_SEC, A_DISCRET, A_CARTE, A_BORDURE, A_FOND

VERT, VERT_CLAIR = "#2E7D32", "#66BB6A"
PAR_PAGE = 15
MAX_ANALYSES_PAR_OUVERTURE = 10     # protège le quota gratuit de l'IA


def _l(texte, style="", sec=False, markdown=False):
    l = QLabel(texte)
    l.setWordWrap(True)
    if markdown:
        l.setTextFormat(Qt.TextFormat.MarkdownText)
    l.setStyleSheet(f"color:{A_SEC if sec else A_TEXTE};background:transparent;{style}")
    return l


def _duree(sec):
    m = int(round((sec or 0) / 60))
    return f"{m // 60} h {m % 60:02d}" if m >= 60 else f"{m} min"


def _allure(sec, km):
    if not sec or not km:
        return "—"
    s = sec / km
    return f"{int(s // 60)}'{int(round(s % 60)) % 60:02d}\"/km"


def resume_analyse(texte, lignes=4):
    """Les premières lignes utiles d'une analyse (titres et lignes vides retirés)."""
    utiles = [l for l in (texte or "").splitlines() if l.strip() and not l.lstrip().startswith("#")
              and not l.strip().startswith("_")]
    return "\n".join(utiles[:lignes])


class MiniTrace(QWidget):
    """Tracé vu du dessus, sans fond de carte (aucune connexion nécessaire)."""

    def __init__(self, points):
        super().__init__()
        self.points = points
        self.setFixedSize(190, 130)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(A_FOND))
        p.drawRoundedRect(self.rect(), 10, 10)
        pts = self.points
        if len(pts) < 2:
            return
        import math
        lats = [q[0] for q in pts]
        lons = [q[1] for q in pts]
        k = math.cos(math.radians((min(lats) + max(lats)) / 2))
        w = max((max(lons) - min(lons)) * k, 1e-9)
        h = max(max(lats) - min(lats), 1e-9)
        marge = 12
        ech = min((self.width() - 2 * marge) / w, (self.height() - 2 * marge) / h)
        ox = (self.width() - w * ech) / 2
        oy = (self.height() - h * ech) / 2
        pas = max(1, len(pts) // 400)
        poly = QPolygonF([QPointF(ox + (q[1] - min(lons)) * k * ech, self.height() - oy - (q[0] - min(lats)) * ech)
                          for q in pts[::pas]])
        p.setPen(QPen(QColor(VERT_CLAIR), 2.4, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        p.drawPolyline(poly)
        for point, couleur in ((poly[0], "#43A047"), (poly[poly.size() - 1], "#E5534B")):
            p.setPen(QPen(QColor(A_CARTE), 2))
            p.setBrush(QColor(couleur))
            p.drawEllipse(point, 4.5, 4.5)


def _points_trace(activite_id):
    brut = dparc.trace_de_l_activite(activite_id)
    if not brut:
        return []
    try:
        pts = json.loads(brut)
        return [(float(q[0]), float(q[1])) for q in pts if isinstance(q, (list, tuple)) and len(q) >= 2]
    except (ValueError, TypeError):
        return []


def _live_actif():
    """Le module LiveTrack coach est-il allumé ? (les repères « suivi en direct » n'apparaissent que si oui)"""
    try:
        from noyau import modules as MO
        return MO.est_actif("livetrack_coach")
    except Exception:
        return False


def _repere_livetrack(activite_id):
    """« 📡 Suivie en direct par … » si un suivi LiveTrack a été rattaché à cette sortie, sinon None."""
    if not _live_actif():
        return None
    try:
        from noyau.donnees import livetrack as dliv
        from noyau.livetrack import regles as rliv
        sv = dliv.suivi_de_activite(activite_id)
        if not sv:
            return None
        d = rliv.duree_texte(sv.get("duree"))
        return f"📡 Suivie en direct ({sv['coureur_nom']})" + (f" · {d} de suivi" if d else "")
    except Exception:
        return None


def _lignes_live_recentes(heures=48, limite=3):
    """Phrases du fil pour les suivis LiveTrack des dernières heures (module allumé seulement)."""
    if not _live_actif():
        return []
    try:
        from noyau.donnees import livetrack as dliv
        depuis = (datetime.now() - timedelta(hours=heures)).isoformat(timespec="seconds")
        return [t for d, t in dliv.lignes_fil(limite * 3) if d >= depuis][:limite]
    except Exception:
        return []


class CarteSortie(QFrame):
    clique = Signal(int)

    def __init__(self, s, ressenti, photos, analyse):
        super().__init__()
        self.activite_id = s["id"]
        self.setObjectName("carteFil")
        self.setStyleSheet(f"#carteFil {{ background:{A_CARTE}; border:1px solid {A_BORDURE}; border-radius:14px; }}"
                           f"#carteFil:hover {{ border-color:{VERT}; }}")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 14, 18, 14)
        lay.setSpacing(8)

        haut = QHBoxLayout()
        gauche = QVBoxLayout()
        gauche.setSpacing(2)
        j = s["jour"]
        heure = (s["date"] or "")[11:16]
        gauche.addWidget(_l(f"{ICONES_TYPE.get(s['type'], '🏅')}  {s['nom'] or s['type'] or 'Sortie'}",
                            "font-size:17px; font-weight:700;"))
        gauche.addWidget(_l(f"{JOURS[j.weekday()]} {j.day} {MOIS[j.month - 1]} {j.year}" + (f" à {heure}" if heure else "")
                            + (f" · {s['type']}" if s["type"] else ""), "font-size:12.5px;", True))
        chiffres = QHBoxLayout()
        chiffres.setSpacing(26)
        for lib, val in (("Distance", f"{s['distance']:.2f} km".replace(".", ",")), ("Dénivelé", f"{int(s['denivele'] or 0)} m"),
                         ("Durée", _duree(s["duree"])), ("Allure", _allure(s["duree"], s["distance"])),
                         ("FC moy.", f"{int(s['fc_moy'])} bpm" if s["fc_moy"] else "—")):
            bloc = QVBoxLayout()
            bloc.setSpacing(0)
            bloc.addWidget(_l(lib.upper(), f"font-size:10.5px; letter-spacing:1px; color:{A_DISCRET};"))
            bloc.addWidget(_l(val, "font-size:18px; font-weight:700;"))
            chiffres.addLayout(bloc)
        chiffres.addStretch(1)
        gauche.addSpacing(6)
        gauche.addLayout(chiffres)
        if ressenti:
            gauche.addWidget(_l(ressenti, "font-size:12.5px;", True))
        repere = _repere_livetrack(s["id"])
        if repere:
            gauche.addWidget(_l(repere, "font-size:12.5px; font-weight:600;", True))
        gauche.addStretch(1)
        haut.addLayout(gauche, 1)
        pts = _points_trace(s["id"])
        if pts:
            haut.addWidget(MiniTrace(pts), 0, Qt.AlignmentFlag.AlignTop)
        lay.addLayout(haut)

        if photos:
            ligne = QHBoxLayout()
            for ph in photos:
                chemin = photos_sorties.chemin_photo(ph.get("fichier") or "")
                pm = QPixmap(str(chemin)) if chemin and os.path.exists(str(chemin)) else QPixmap()
                if not pm.isNull():
                    mini = QLabel()
                    mini.setPixmap(pm.scaled(120, 84, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                                             Qt.TransformationMode.SmoothTransformation).copy(0, 0, 120, 84))
                    ligne.addWidget(mini)
            ligne.addStretch(1)
            lay.addLayout(ligne)

        cadre = QFrame()
        cadre.setObjectName("cadreAnalyse")
        cadre.setStyleSheet(f"#cadreAnalyse {{ background:{A_FOND}; border-radius:10px; }}")
        lc = QVBoxLayout(cadre)
        lc.setContentsMargins(14, 10, 14, 10)
        lc.setSpacing(4)
        entete = QHBoxLayout()
        self.badge = _l("", "font-size:11px; font-weight:700; letter-spacing:1px;")
        self.badge.setWordWrap(False)
        entete.addWidget(self.badge)
        entete.addStretch(1)
        self.bouton_suite = QPushButton("Lire toute l'analyse")
        self.bouton_suite.setCursor(Qt.CursorShape.PointingHandCursor)
        self.bouton_suite.setStyleSheet(f"QPushButton {{ background:transparent; color:{VERT_CLAIR}; border:none; font-size:12px; }}")
        self.bouton_suite.clicked.connect(self._basculer)
        entete.addWidget(self.bouton_suite)
        lc.addLayout(entete)
        self.texte = _l("", "font-size:13px;", markdown=True)
        self.texte.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
        lc.addWidget(self.texte)
        lay.addWidget(cadre)
        self._complet = False
        self.definir_analyse(analyse)

    def definir_analyse(self, texte, en_cours=False):
        self._analyse = texte
        if texte:
            local = aa.source_du_texte(texte) == "local"
            self.badge.setText("ANALYSE HORS LIGNE" if local else "ANALYSE DE L'IA")
            self.badge.setStyleSheet(f"color:{A_SEC if local else VERT_CLAIR};background:transparent;"
                                     "font-size:11px; font-weight:700; letter-spacing:1px;")
            self.bouton_suite.setVisible(True)
            self._afficher()
        else:
            self.badge.setText("ANALYSE EN COURS…" if en_cours else "ANALYSE À VENIR")
            self.badge.setStyleSheet(f"color:{A_DISCRET};background:transparent;font-size:11px; font-weight:700; letter-spacing:1px;")
            self.texte.setText("L'analyse s'écrit toute seule : elle apparaîtra ici dans un instant."
                               if en_cours else "Cette sortie sera analysée automatiquement.")
            self.bouton_suite.setVisible(False)

    def _afficher(self):
        self.texte.setText(self._analyse if self._complet else resume_analyse(self._analyse))
        self.bouton_suite.setText("Réduire" if self._complet else "Lire toute l'analyse")

    def _basculer(self):
        self._complet = not self._complet
        self._afficher()

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton and not self.bouton_suite.underMouse():
            self.clique.emit(self.activite_id)
        super().mouseReleaseEvent(e)


class _AnalyseurFil(QThread):
    """Analyse, l'une après l'autre, les sorties du fil qui n'en ont pas encore."""
    une = Signal(int, str)

    def __init__(self, a_faire, parent=None):
        super().__init__(parent)
        self.a_faire = list(a_faire)
        self.arreter = False

    def run(self):
        essayer_ia = True
        for activite_id, athlete_id in self.a_faire:
            if self.arreter:
                return
            try:
                texte, source = aa.analyser(activite_id, athlete_id, essayer_ia)
            except Exception:
                continue
            if source == "local" and essayer_ia and aa._ia_disponible():
                essayer_ia = False          # quota ou réseau : le reste en hors ligne
            if texte:
                self.une.emit(activite_id, texte)


class FilActivite(_EcranAthlete):

    def __init__(self, athlete_id_initial=None):
        super().__init__("🏃  Fil d'activité",
                         "Tes sorties comme sur Strava, chacune avec son analyse écrite automatiquement : "
                         "par l'IA si une clé est réglée, sinon par les règles du logiciel (hors ligne).",
                         athlete_id_initial)
        self.nb = PAR_PAGE
        self.cartes = {}
        self._analyseur = None
        self.bandeau_semaine = QFrame()
        self.bandeau_semaine.setObjectName("bandeauSemaine")
        self.bandeau_semaine.setStyleSheet(f"#bandeauSemaine {{ background:{A_CARTE}; border:1px solid {A_BORDURE}; border-radius:14px; }}")
        lb = QHBoxLayout(self.bandeau_semaine)
        lb.setContentsMargins(18, 12, 18, 12)
        colonne = QVBoxLayout()
        colonne.setSpacing(4)
        self.texte_semaine = _l("", "font-size:14px; font-weight:600;")
        colonne.addWidget(self.texte_semaine)
        self.texte_live = _l("", "font-size:12.5px;", True)        # suivis LiveTrack récents (module LiveTrack coach)
        self.texte_live.setVisible(False)
        colonne.addWidget(self.texte_live)
        lb.addLayout(colonne)
        self.principal.addWidget(self.bandeau_semaine)
        self.fil = QVBoxLayout()
        self.fil.setSpacing(12)
        self.principal.addLayout(self.fil)
        self.plus = QPushButton("Afficher plus de sorties")
        self.plus.setObjectName("boutonSecondaire")
        self.plus.clicked.connect(self._plus)
        self.principal.addWidget(self.plus, 0, Qt.AlignmentFlag.AlignHCenter)
        self.principal.addStretch(1)
        try:
            from interface.analyse_auto import service
            service().analyse_prete.connect(self._analyse_recue)
        except Exception:
            pass
        self._finaliser()
        self.setStyleSheet(style_sombre() + f"QMainWindow, QScrollArea, QScrollArea > QWidget > QWidget {{ background:{A_FOND}; }}")

    def _plus(self):
        self.nb += PAR_PAGE
        self.actualiser()

    def _vider(self):
        while self.fil.count():
            it = self.fil.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        self.cartes = {}

    def _arreter_analyseur(self):
        # sans attendre : l'analyse en cours se termine en arrière-plan puis le fil s'arrête
        if self._analyseur is not None and self._analyseur.isRunning():
            self._analyseur.arreter = True
            self._analyseur.une.disconnect()
            self._anciens = [t for t in getattr(self, "_anciens", []) if t.isRunning()] + [self._analyseur]
        self._analyseur = None

    def actualiser(self):
        self._arreter_analyseur()
        self._vider()
        a = self.athlete_id
        if a is None:
            self.texte_semaine.setText("Sélectionne un athlète.")
            return
        lundi = date.today() - timedelta(days=date.today().weekday())
        semaine = met.activites_periode(a, lundi)
        km = sum(s["distance"] for s in semaine)
        dp = sum(s["denivele"] for s in semaine)
        sec = sum(s["duree"] for s in semaine)
        self.texte_semaine.setText(
            f"Cette semaine : {len(semaine)} sortie{'s' if len(semaine) > 1 else ''} · "
            f"{km:.1f} km · {int(dp)} m D+ · {_duree(sec)}".replace(".", ","))
        lignes_live = _lignes_live_recentes()
        self.texte_live.setText("\n".join(lignes_live))
        self.texte_live.setVisible(bool(lignes_live))

        # les sorties les plus récentes, sur une fenêtre qui s'élargit jusqu'à en avoir assez
        sorties, jours = [], 60
        while len(sorties) < self.nb and jours <= 365 * 30:
            sorties = met.activites_periode(a, date.today() - timedelta(days=jours))
            jours *= 3
        sorties = [s for s in reversed(sorties) if s["jour"]][: self.nb]
        if not sorties:
            self.fil.addWidget(_l("Aucune sortie pour l'instant. Importe une sortie ou synchronise ta montre : "
                                  "elle apparaîtra ici avec son analyse.", sec=True))
            self.plus.setVisible(False)
            return
        analyses = aa.analyses_des_sorties([s["id"] for s in sorties])
        from interface.ressenti import texte_ressenti
        a_faire = []
        mois = None
        for s in sorties:
            j = s["jour"]
            if (j.year, j.month) != mois:
                mois = (j.year, j.month)
                self.fil.addWidget(_l(f"{MOIS[j.month - 1].upper()} {j.year}", f"font-size:13px; font-weight:800; color:{A_DISCRET};"))
            texte = analyses.get(s["id"])
            carte = CarteSortie(s, texte_ressenti(met.ressenti_de_sortie(s["id"])),
                                photos_sorties.photos_de_sortie(s["id"])[:4], texte)
            carte.clique.connect(self._ouvrir)
            self.cartes[s["id"]] = carte
            self.fil.addWidget(carte)
            if not texte or (aa.source_du_texte(texte) == "local" and aa._ia_disponible()):
                a_faire.append((s["id"], a))
        self.plus.setVisible(True)
        if not aa.actif():
            a_faire = []
        elif aa._ia_disponible():
            a_faire = a_faire[:MAX_ANALYSES_PAR_OUVERTURE]   # l'analyse hors ligne, elle, est gratuite : pas de limite
        for aid, _ in a_faire:
            if not self.cartes[aid]._analyse:
                self.cartes[aid].definir_analyse(None, en_cours=True)
        if a_faire:
            self._analyseur = _AnalyseurFil(a_faire, self)
            self._analyseur.une.connect(self._analyse_texte)
            self._analyseur.start()

    def _analyse_texte(self, activite_id, texte):
        carte = self.cartes.get(activite_id)
        if carte is not None:
            carte.definir_analyse(texte)

    def _analyse_recue(self, activite_id, _source):
        if activite_id in self.cartes:
            self._analyse_texte(activite_id, aa.analyses_des_sorties([activite_id]).get(activite_id))
        elif self.isVisible():
            self.actualiser()       # une nouvelle sortie vient d'arriver : elle prend sa place en haut du fil

    def _ouvrir(self, activite_id):
        from interface.detail_sortie import DialogueDetailSortie
        DialogueDetailSortie(activite_id, self.athlete_id, parent=self, au_enregistrement=self.actualiser).exec()

    def closeEvent(self, e):
        self._arreter_analyseur()
        super().closeEvent(e)
