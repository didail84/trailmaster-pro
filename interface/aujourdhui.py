"""
Écran « Aujourd'hui » (style Cockpit, D3) : ce qui compte ce matin, d'un
coup d'œil — disponibilité en anneau, séance du jour, charge de la
semaine, alertes, ressenti à saisir. Chaque bloc est cliquable (U5) et
mène à l'écran de détail correspondant.
"""

from datetime import date

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton, QScrollArea, QVBoxLayout, QWidget, QComboBox,
)

import data.metriques as met
from interface import arriere_plan
from interface.cockpit import Anneau, JaugeBarre, couleur_score
from interface.theme import PALETTE, obtenir_couleur_accent

JOURS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre", "novembre", "décembre"]
COULEUR_NIVEAU = {"critique": "#EF5350", "attention": "#FFA726", "info": "#4C8DFF", "ok": "#66BB6A"}


class CarteCliquable(QFrame):
    clique = Signal()

    def __init__(self, cible=None, parent=None):
        super().__init__(parent)
        self.setObjectName("carteCockpit")
        self._cible = cible
        if cible:
            self.setCursor(Qt.CursorShape.PointingHandCursor)

    def mouseReleaseEvent(self, e):
        if self._cible and e.button() == Qt.MouseButton.LeftButton and self.rect().contains(e.position().toPoint()):
            self.clique.emit()
        super().mouseReleaseEvent(e)


def _label(texte, style="", secondaire=False, mots=True):
    l = QLabel(texte)
    l.setWordWrap(mots)
    l.setStyleSheet("background:transparent;" + f"color:{PALETTE['texte_secondaire'] if secondaire else PALETTE['texte']};" + style)
    l.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
    return l


class EcranAujourdhui(QWidget):

    def __init__(self, navigation, athletes, athlete_id=None, parent=None):
        """navigation : dict cle -> fonction sans argument. athletes : [(id, libellé)]."""
        super().__init__(parent)
        self.nav = navigation
        self.athlete_id = athlete_id
        self._donnees = None
        self.setObjectName("ecranAujourdhui")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        racine = QVBoxLayout(self)
        racine.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        racine.addWidget(scroll)
        scroll.setStyleSheet(f"QScrollArea {{ background:{PALETTE['fond']}; }}")
        self.corps = QWidget()
        self.corps.setObjectName("corpsAujourdhui")
        scroll.setWidget(self.corps)
        self.lay = QVBoxLayout(self.corps)
        self.lay.setContentsMargins(36, 30, 36, 30)
        self.lay.setSpacing(16)

        # en-tête
        entete = QHBoxLayout()
        bloc = QVBoxLayout()
        self.salut = QLabel("")
        self.salut.setStyleSheet(f"font-size:30px; font-weight:800; background:transparent; color:{PALETTE['texte']};")
        self.date_l = QLabel("")
        self.date_l.setStyleSheet(f"color:{PALETTE['texte_secondaire']}; font-size:14px; background:transparent;")
        bloc.addWidget(self.salut)
        bloc.addWidget(self.date_l)
        entete.addLayout(bloc, 1)
        self.combo = QComboBox()
        for id_, lib in athletes:
            self.combo.addItem(lib, id_)
        entete.addWidget(self.combo)
        b_nv = QPushButton("＋ Nouvelle activité")
        b_nv.setObjectName("boutonPrincipal")
        b_nv.clicked.connect(lambda: self.nav["nouvelle"]())
        b_pal = QPushButton("⌘K  Aller à…")
        b_pal.setObjectName("boutonSecondaire")
        b_pal.clicked.connect(lambda: self.nav["palette"]())
        entete.addWidget(b_nv)
        entete.addWidget(b_pal)
        self.lay.addLayout(entete)

        self.message = QLabel("")
        self.message.setWordWrap(True)
        self.message.setVisible(False)
        self.lay.addWidget(self.message)

        self.zone = QVBoxLayout()
        self.zone.setSpacing(16)
        self.lay.addLayout(self.zone)
        self.lay.addStretch(1)

        if athlete_id is not None:
            i = self.combo.findData(athlete_id)
            if i >= 0:
                self.combo.setCurrentIndex(i)
        self.combo.currentIndexChanged.connect(self._athlete_change)
        self.athlete_id = self.combo.currentData()
        self._style()
        self.actualiser()

    def _style(self):
        self.setStyleSheet(
            f"#carteCockpit {{ background:{PALETTE['carte']}; border:1px solid {PALETTE['bordure']}; border-radius:16px; }}"
            f"#carteCockpit:hover {{ border-color:{obtenir_couleur_accent()}; }}"
            f"#ecranAujourdhui, #corpsAujourdhui {{ background:{PALETTE['fond']}; }}"
        )

    # ------------------------------------------------------------------
    def definir_athlete(self, athlete_id):
        if athlete_id is None:      # « Tous les athlètes » : on garde l'athlète affiché
            return
        i = self.combo.findData(athlete_id)
        if i >= 0 and self.combo.currentIndex() != i:
            self.combo.blockSignals(True)
            self.combo.setCurrentIndex(i)
            self.combo.blockSignals(False)
        if athlete_id != self.athlete_id:
            self.athlete_id = athlete_id
            self.actualiser()

    def _athlete_change(self):
        self.athlete_id = self.combo.currentData()
        if "athlete_change" in self.nav:
            self.nav["athlete_change"](self.athlete_id)
        self.actualiser()

    def afficher_message(self, texte):
        self.message.setText("🔄  " + texte)
        self.message.setStyleSheet(f"background:{PALETTE['carte']}; border:1px solid {obtenir_couleur_accent()};"
                                   " border-radius:10px; padding:10px 14px;")
        self.message.setVisible(True)

    def actualiser(self):
        t = date.today()
        self.salut.setText("Aujourd'hui")
        self.date_l.setText(f"{JOURS[t.weekday()].capitalize()} {t.day} {MOIS[t.month - 1]} {t.year}")
        self._vider()
        if self.athlete_id is None:
            self.zone.addWidget(_label("Crée ou sélectionne un athlète pour voir ton tableau du jour.", "font-size:15px;", True))
            return
        self.zone.addWidget(_label("Chargement…", "font-size:15px;", True))
        arriere_plan.executer(met.donnees_aujourdhui, self._recu, self.athlete_id, proprietaire=self)

    def _vider(self):
        while self.zone.count():
            it = self.zone.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
            elif it.layout():
                self._vider_layout(it.layout())

    def _vider_layout(self, lay):
        while lay.count():
            it = lay.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
            elif it.layout():
                self._vider_layout(it.layout())

    def _recu(self, d, erreur):
        if erreur or d is None:
            self._vider()
            self.zone.addWidget(_label(f"Impossible de calculer l'écran : {erreur}", "", True))
            return
        if d.get("athlete_id") != self.athlete_id:
            return
        self._vider()
        self._donnees = d
        ligne1 = QHBoxLayout()
        ligne1.setSpacing(16)
        ligne1.addWidget(self._carte_dispo(d), 7)
        ligne1.addWidget(self._carte_seance(d), 5)
        self.zone.addLayout(ligne1)
        ligne2 = QHBoxLayout()
        ligne2.setSpacing(16)
        ligne2.addWidget(self._carte_semaine(d), 5)
        ligne2.addWidget(self._carte_charge(d), 4)
        ligne2.addWidget(self._carte_course(d), 4)
        self.zone.addLayout(ligne2)
        ligne3 = QHBoxLayout()
        ligne3.setSpacing(16)
        ligne3.addWidget(self._carte_alertes(d), 7)
        ligne3.addWidget(self._carte_sortie(d), 5)
        self.zone.addLayout(ligne3)

    # ------------------------------------------------------------------
    def _carte(self, cle=None):
        c = CarteCliquable(cle)
        if cle:
            c.clique.connect(lambda k=cle: self.nav[k]())
        lay = QVBoxLayout(c)
        lay.setContentsMargins(20, 16, 20, 16)
        lay.setSpacing(6)
        return c, lay

    def _titre(self, texte):
        return _label(texte.upper(), f"font-size:11px; font-weight:700; color:{PALETTE['texte_discret']};")

    def _carte_dispo(self, d):
        c, lay = self._carte("sante")
        lay.addWidget(self._titre("Disponibilité du matin"))
        h = QHBoxLayout()
        h.setSpacing(22)
        anneau = Anneau(taille=190, epaisseur=16)
        anneau.setFixedSize(190, 190)
        dispo = d["dispo"]
        anneau.definir(dispo["score"], sous_texte="sur 100")
        anneau.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        h.addWidget(anneau)
        col = QVBoxLayout()
        col.setSpacing(5)
        col.addWidget(_label(dispo["verdict"], "font-size:19px; font-weight:700;"))
        for f in dispo["facteurs"]:
            ligne = QHBoxLayout()
            nom = _label(f["libelle"], "font-weight:600;", mots=False)
            nom.setFixedWidth(104)
            jauge = JaugeBarre()
            jauge.definir(f["score"], couleur=couleur_score(f["score"]))
            jauge.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
            jauge.setFixedWidth(84)
            det = _label(f["detail"], "font-size:12px;", True)
            ligne.addWidget(nom)
            ligne.addWidget(jauge)
            ligne.addWidget(det, 1)
            col.addLayout(ligne)
        if not dispo["facteurs"]:
            col.addWidget(_label("Importe ta santé quotidienne Garmin (sommeil, HRV, FC repos) pour affiner.", "", True))
        col.addStretch(1)
        h.addLayout(col, 1)
        lay.addLayout(h)
        return c

    def _carte_seance(self, d):
        c, lay = self._carte("plan")
        lay.addWidget(self._titre("Séance du jour"))
        s = d["seance"]
        if s:
            lay.addWidget(_label(s["nom"], "font-size:20px; font-weight:700;"))
            lay.addWidget(_label(f"{s['type'] or ''} · {s['statut']}", "", True))
            if s.get("commentaire"):
                lay.addWidget(_label("🔄 Ajustée : " + s["commentaire"], "font-size:12px;", True))
        else:
            lay.addWidget(_label("Jour libre", "font-size:20px; font-weight:700;"))
            lay.addWidget(_label("Aucune séance prévue aujourd'hui.", "", True))
        lay.addStretch(1)
        lay.addWidget(_label("Ouvrir le calendrier →", f"color:{obtenir_couleur_accent()}; font-weight:600;"))
        return c

    def _carte_semaine(self, d):
        c, lay = self._carte("bilans")
        lay.addWidget(self._titre("Cette semaine"))
        s = d["semaine"]
        lay.addWidget(_label(f"{s['distance']:.1f} km", "font-size:28px; font-weight:800;", mots=False))
        lay.addWidget(_label(f"{s['denivele']} m D+ · {int(s['duree_h'])} h {round((s['duree_h'] % 1) * 60):02d} · {s['sorties']} sortie{'s' if s['sorties'] > 1 else ''}", "", True))
        v = d["volume"]
        if v:
            pct = v["pct"]["distance"]
            jauge = JaugeBarre()
            jauge.definir(min(pct, 100) if pct <= 100 else pct, repere=100 if pct > 100 else None, couleur=couleur_score(100 - abs(100 - pct) * 0.8))
            jauge.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
            lay.addWidget(jauge)
            lay.addWidget(_label(f"Cible conseillée : {v['cible']['distance']:.1f} km ({round(pct)} %)", "font-size:12px;", True))
        lay.addStretch(1)
        return c

    def _carte_charge(self, d):
        c, lay = self._carte("charge")
        lay.addWidget(self._titre("Charge (ACWR)"))
        a = d.get("acwr") or {}
        val = a.get("acwr")
        if val is None:
            lay.addWidget(_label("—", "font-size:28px; font-weight:800;"))
            lay.addWidget(_label("Pas assez de sorties récentes.", "", True))
        else:
            coul = "#66BB6A" if 0.8 <= val <= 1.3 else "#FFA726" if val <= 1.5 else "#EF5350"
            lay.addWidget(_label(f"{val:.2f}".replace(".", ","), f"font-size:28px; font-weight:800; color:{coul};", mots=False))
            lay.addWidget(_label(a.get("interpretation", ""), "font-size:12px;", True))
        lay.addStretch(1)
        return c

    def _carte_course(self, d):
        c, lay = self._carte("courses")
        lay.addWidget(self._titre("Prochaine course"))
        k = d["course"]
        if k:
            try:
                jours = (date.fromisoformat(str(k["date"])[:10]) - date.today()).days
            except ValueError:
                jours = None
            lay.addWidget(_label("Aujourd'hui !" if jours == 0 else (f"J-{jours}" if jours is not None else "—"), "font-size:28px; font-weight:800;", mots=False))
            lay.addWidget(_label(f"{k['nom']}\n{k['distance_km']} km · {k['denivele_m'] or 0} m D+", "font-size:12px;", True))
        else:
            lay.addWidget(_label("—", "font-size:28px; font-weight:800;"))
            lay.addWidget(_label("Aucune course au calendrier.", "", True))
        lay.addStretch(1)
        return c

    def _carte_alertes(self, d):
        c, lay = self._carte("alertes")
        lay.addWidget(self._titre("Points d'attention"))
        if not d["alertes"]:
            lay.addWidget(_label("✅ Rien d'inquiétant : continue comme ça.", "font-size:15px;"))
        for a in d["alertes"]:
            ligne = QHBoxLayout()
            pastille = QLabel("●")
            pastille.setStyleSheet(f"color:{COULEUR_NIVEAU.get(a['niveau'], '#999')}; background:transparent; font-size:16px;")
            pastille.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
            pastille.setAlignment(Qt.AlignmentFlag.AlignTop)
            ligne.addWidget(pastille)
            ligne.addWidget(_label(a["message"], "font-size:13px;"), 1)
            lay.addLayout(ligne)
        lay.addStretch(1)
        return c

    def _carte_sortie(self, d):
        s = d["derniere"]
        sr = d["sans_ressenti"]
        c, lay = self._carte("sortie" if s else None)
        lay.addWidget(self._titre("Dernière sortie"))
        if not s:
            lay.addWidget(_label("Aucune sortie récente.", "", True))
            return c
        lay.addWidget(_label(s["nom"] or s["type"] or "Sortie", "font-size:17px; font-weight:700;"))
        mn = s["duree"] // 60
        lay.addWidget(_label(f"{s['jour'].day}/{s['jour'].month} · {s['type']} · {s['distance']:.1f} km · {s['denivele']} m D+ · {mn // 60} h {mn % 60:02d}", "font-size:12px;", True))
        if sr:
            b = QPushButton("💬  Comment c'était ? (3 clics)")
            b.setObjectName("boutonPrincipal")
            b.clicked.connect(lambda: self.nav["ressenti"](sr))
            lay.addWidget(b)
        lay.addStretch(1)
        return c
