"""
Roadbook course (v108) — préparer une course précise : tracé GPX, temps de passage
estimés selon ton niveau, barrières horaires et marges, ravitaillements avec ce qu'il
faut manger / boire, checklist du sac, mini-fiche A5 à imprimer.

Écran de montage : tous les calculs viennent de data/roadbook.py, qui réutilise le
pacing par pente, la prédiction VO₂max, le plan de ravitaillement et la liste de
matériel déjà présents dans TrailMaster (aucun calcul refait ici).
"""

import json
from datetime import date, datetime

from PySide6.QtCore import Qt, QDate, QTime, QPointF, QRectF
from PySide6.QtGui import QPainter, QColor, QPen, QBrush, QPolygonF, QFont
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QLineEdit, QPushButton, QComboBox,
    QDoubleSpinBox, QCheckBox, QDateEdit, QTimeEdit, QFrame, QTableWidget, QTableWidgetItem,
    QListWidget, QListWidgetItem, QFileDialog, QMessageBox, QAbstractItemView,
)
from noyau.donnees import parcours as dparc  # accès aux données

import noyau.course.roadbook as rbk
import noyau.course.strategie as strat
import noyau.entrainement.metriques as met
from noyau.entrainement.conformite import parser_allure
from interface.ecran_liste import configurer_table_redimensionnable
from interface.forme_evolution import _EcranAthlete
from interface.theme import PALETTE
from noyau.donnees import courses as dcourse

VERT, ORANGE, ROUGE, BLEU = "#66BB6A", "#FFA726", "#EF5350", "#42A5F5"
MODES = [("appris", "Appris sur tes sorties (conseillé)"),
         ("vo2", "Prédit depuis ton VO₂max (estimation basse)"),
         ("allure", "Je donne mon allure sur le plat"),
         ("temps", "Je vise un temps total")]
INTENSITES = [("facile", "Facile"), ("modere", "Modérée"), ("soutenu", "Soutenue")]
SAISONS = ["Automatique", "Printemps", "Été", "Automne", "Hiver"]


def _fr(v, d=1):
    return f"{v:.{d}f}".replace(".", ",")


def _parser_temps(texte):
    """« 6:30 », « 6h30 », « 6 » -> secondes, ou None."""
    h = rbk._hhmm(texte)
    if h is None:
        try:
            return float(str(texte).replace(",", ".")) * 3600
        except ValueError:
            return None
    return h[0] * 3600 + h[1] * 60


CASES_QSS = ("QListWidget::indicator, QCheckBox::indicator { width: 16px; height: 16px; border: 1px solid #8A949E; "
             "border-radius: 3px; background: transparent; } "
             "QListWidget::indicator:checked, QCheckBox::indicator:checked { background: #42A5F5; border-color: #42A5F5; }")


class ProfilWidget(QWidget):
    """Profil altimétrique avec un repère par point de passage."""

    def __init__(self):
        super().__init__()
        self.setMinimumHeight(170)
        self.prof = []
        self.passages = []

    def definir(self, prof, passages):
        self.prof, self.passages = prof, passages
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        p.fillRect(0, 0, w, h, QColor(PALETTE["fond_secondaire"]))
        if len(self.prof) < 2:
            p.setPen(QColor(PALETTE["texte_secondaire"]))
            p.drawText(QRectF(0, 0, w, h), Qt.AlignmentFlag.AlignCenter, "Charge un fichier GPX pour voir le profil")
            return
        gauche, droite, haut, bas = 44, 12, 14, 24
        kmax = self.prof[-1][0] or 1.0
        alts = [a for _, a in self.prof]
        amin, amax = min(alts), max(alts)
        marge = (amax - amin) * 0.1 + 1
        amin, amax = amin - marge, amax + marge
        X = lambda km: gauche + (w - gauche - droite) * km / kmax
        Y = lambda a: haut + (h - haut - bas) * (1 - (a - amin) / (amax - amin))
        pts = [QPointF(X(k), Y(a)) for k, a in self.prof]
        poly = QPolygonF([QPointF(X(0), h - bas)] + pts + [QPointF(X(kmax), h - bas)])
        p.setPen(Qt.PenStyle.NoPen)
        c = QColor(BLEU)
        c.setAlpha(55)
        p.setBrush(QBrush(c))
        p.drawPolygon(poly)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(QColor(BLEU), 2))
        p.drawPolyline(QPolygonF(pts))
        p.setPen(QColor(PALETTE["texte_secondaire"]))
        p.setFont(QFont(self.font().family(), 8))
        p.drawText(QRectF(0, haut - 6, gauche - 4, 14), Qt.AlignmentFlag.AlignRight, f"{int(amax)} m")
        p.drawText(QRectF(0, h - bas - 10, gauche - 4, 14), Qt.AlignmentFlag.AlignRight, f"{int(amin)} m")
        pas = 5 if kmax <= 40 else 10 if kmax <= 100 else 20
        k = 0
        while k <= kmax:
            p.drawText(QRectF(X(k) - 20, h - bas + 4, 40, 14), Qt.AlignmentFlag.AlignHCenter, f"{k}")
            k += pas
        for i, pt in enumerate(self.passages, 1):
            if pt["type"] == "Repère" and i not in (1, len(self.passages)):
                continue
            col = QColor(ROUGE if pt["statut"] == "depasse" else ORANGE if pt["statut"] == "serre"
                         else VERT if pt["type"] == "Ravitaillement" else PALETTE["texte_secondaire"])
            x = X(min(pt["km"], kmax))
            p.setPen(QPen(col, 1, Qt.PenStyle.DashLine))
            p.drawLine(int(x), haut, int(x), h - bas)
            p.setBrush(QBrush(col))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(QPointF(x, haut + 2), 7, 7)
            p.setPen(QColor("white"))
            p.drawText(QRectF(x - 8, haut - 6, 16, 16), Qt.AlignmentFlag.AlignCenter, str(i))


class RoadbookCourse(_EcranAthlete):

    ANALYSE_IA = None

    def __init__(self, athlete_id_initial=None, course_preselectionnee=None):
        super().__init__(
            "🗺️ Roadbook course",
            "Prépare une course précise : temps de passage estimés selon ton niveau, barrières horaires, "
            "ravitaillements, checklist du sac et mini-fiche à imprimer. En complément de TrailMaster, "
            "qui gère l'entraînement : les calculs réutilisent ceux de l'appli.",
            athlete_id_initial,
        )
        rbk.creer_table()
        self._rb_id = None
        self._trace, self._wp = [], []
        self._points, self._checklist = [], []
        self._passages, self._plan, self._nutrition = [], None, []
        self._scenarios, self._sacs, self._facteurs = {}, [], None
        self._distance, self._deniv = 0.0, 0
        self._bloque = False
        self._course_pre = course_preselectionnee

        # ---- 1. Course
        c1, l1 = self._carte("1. La course")
        ligne = QHBoxLayout()
        self.combo_rb = QComboBox()
        self.combo_rb.currentIndexChanged.connect(self._rb_choisi)
        self.btn_suppr_rb = QPushButton("🗑️ Supprimer ce roadbook")
        self.btn_suppr_rb.clicked.connect(self._supprimer_rb)
        ligne.addWidget(QLabel("Roadbook :"))
        ligne.addWidget(self.combo_rb, 1)
        ligne.addWidget(self.btn_suppr_rb)
        l1.addLayout(ligne)
        ligne = QHBoxLayout()
        self.combo_course = QComboBox()
        self.combo_course.currentIndexChanged.connect(self._course_choisie)
        ligne.addWidget(QLabel("Course de « Courses à venir » :"))
        ligne.addWidget(self.combo_course, 1)
        l1.addLayout(ligne)
        ligne = QHBoxLayout()
        self.champ_nom = QLineEdit()
        self.champ_nom.setPlaceholderText("Nom de la course")
        self.champ_date = QDateEdit(QDate.currentDate())
        self.champ_date.setCalendarPopup(True)
        self.champ_date.setDisplayFormat("dd/MM/yyyy")
        self.champ_depart = QTimeEdit(QTime(7, 0))
        self.champ_depart.setDisplayFormat("HH:mm")
        self.champ_nom.textChanged.connect(self._recalculer)
        self.champ_date.dateChanged.connect(self._recalculer)
        self.champ_depart.timeChanged.connect(self._recalculer)
        ligne.addWidget(self.champ_nom, 2)
        ligne.addWidget(QLabel("Date :"))
        ligne.addWidget(self.champ_date)
        ligne.addWidget(QLabel("Départ :"))
        ligne.addWidget(self.champ_depart)
        l1.addLayout(ligne)
        ligne = QHBoxLayout()
        btn_gpx = QPushButton("📂 Charger un GPX…")
        btn_gpx.clicked.connect(self._charger_gpx)
        self.combo_parcours = QComboBox()
        self.combo_parcours.currentIndexChanged.connect(self._parcours_choisi)
        self.label_trace = QLabel("Aucun tracé chargé.")
        self.label_trace.setObjectName("texteSecondaire")
        ligne.addWidget(btn_gpx)
        ligne.addWidget(QLabel("ou parcours déjà importé :"))
        ligne.addWidget(self.combo_parcours, 1)
        l1.addLayout(ligne)
        l1.addWidget(self.label_trace)
        self.principal.addWidget(c1)

        # ---- 2. Niveau
        c2, l2 = self._carte("2. Ton niveau — temps de passage")
        ligne = QHBoxLayout()
        self.combo_mode = QComboBox()
        for cle, lib in MODES:
            self.combo_mode.addItem(lib, cle)
        self.combo_mode.currentIndexChanged.connect(self._recalculer)
        self.champ_allure = QLineEdit("6:00")
        self.champ_allure.setPlaceholderText("mm:ss /km sur le plat")
        self.champ_allure.setMaximumWidth(110)
        self.champ_temps = QLineEdit("6:00")
        self.champ_temps.setPlaceholderText("h:mm")
        self.champ_temps.setMaximumWidth(90)
        for w_ in (self.champ_allure, self.champ_temps):
            w_.textChanged.connect(self._recalculer)
        ligne.addWidget(self.combo_mode, 1)
        ligne.addWidget(QLabel("Allure plat :"))
        ligne.addWidget(self.champ_allure)
        ligne.addWidget(QLabel("Temps visé :"))
        ligne.addWidget(self.champ_temps)
        l2.addLayout(ligne)
        self.label_niveau = QLabel("")
        self.label_niveau.setWordWrap(True)
        self.label_niveau.setObjectName("texteSecondaire")
        l2.addWidget(self.label_niveau)
        # Trois scénarios (étape 3) : un bloc par scénario, temps total et arrivée
        ligne_sc = QHBoxLayout()
        self.blocs_scenarios = {}
        for code, libelle in strat.SCENARIOS:
            bloc = QFrame()
            bloc.setObjectName("carteScenario")
            lb = QVBoxLayout(bloc)
            t = QLabel(libelle.upper())
            t.setObjectName("labelChamp")
            v = QLabel("—")
            v.setStyleSheet("font-size: 20px; font-weight: 700; background: transparent;")
            d = QLabel("")
            d.setObjectName("texteSecondaire")
            d.setWordWrap(True)
            for w_ in (t, v, d):
                lb.addWidget(w_)
            self.blocs_scenarios[code] = (v, d)
            ligne_sc.addWidget(bloc, 1)
        l2.addLayout(ligne_sc)
        self.label_scenarios = QLabel("")
        self.label_scenarios.setWordWrap(True)
        self.label_scenarios.setObjectName("texteSecondaire")
        l2.addWidget(self.label_scenarios)
        self.principal.addWidget(c2)

        # ---- 3. Conditions
        c3, l3 = self._carte("3. Conditions et sac")
        ligne = QHBoxLayout()
        self.spin_temp = QDoubleSpinBox()
        self.spin_temp.setRange(-20, 45)
        self.spin_temp.setValue(15)
        self.spin_temp.setSuffix(" °C")
        self.spin_poids = QDoubleSpinBox()
        self.spin_poids.setRange(35, 200)
        self.spin_poids.setValue(70)
        self.spin_poids.setSuffix(" kg")
        self.combo_intensite = QComboBox()
        for cle, lib in INTENSITES:
            self.combo_intensite.addItem(lib, cle)
        self.combo_intensite.setCurrentIndex(1)
        self.case_nuit = QCheckBox("Portion nocturne")
        self.case_alt = QCheckBox("Haute montagne")
        self.case_nuit.setStyleSheet(CASES_QSS)
        self.case_alt.setStyleSheet(CASES_QSS)
        self.combo_saison = QComboBox()
        self.combo_saison.addItems(SAISONS)
        for w_ in (self.spin_temp, self.spin_poids):
            w_.valueChanged.connect(self._recalculer)
        self.combo_intensite.currentIndexChanged.connect(self._recalculer)
        self.combo_saison.currentIndexChanged.connect(self._regenerer_checklist)
        self.case_nuit.toggled.connect(self._regenerer_checklist)
        self.case_alt.toggled.connect(self._regenerer_checklist)
        for lab, w_ in (("Température :", self.spin_temp), ("Poids :", self.spin_poids),
                        ("Intensité :", self.combo_intensite), ("Saison :", self.combo_saison)):
            ligne.addWidget(QLabel(lab))
            ligne.addWidget(w_)
        ligne.addWidget(self.case_nuit)
        ligne.addWidget(self.case_alt)
        ligne.addStretch()
        l3.addLayout(ligne)
        self.principal.addWidget(c3)

        # ---- 4. Profil
        c4, l4 = self._carte("4. Profil et points de passage")
        self.profil = ProfilWidget()
        l4.addWidget(self.profil)
        self.table = QTableWidget(0, 10)
        self.table.setHorizontalHeaderLabels(["Point", "Km", "Type", "Barrière (hh:mm)", "Ambitieux", "Réaliste",
                                              "Prudent", "Marge (prudent)", "Tronçon", "Temps du tronçon"])
        configurer_table_redimensionnable(self.table)
        self.table.setMinimumHeight(240)
        self.table.itemChanged.connect(self._cellule_modifiee)
        l4.addWidget(self.table)
        ligne = QHBoxLayout()
        for texte, f in (("➕ Ajouter un point", self._ajouter_point), ("➖ Supprimer le point",
                         self._supprimer_point), ("📌 Reprendre les points du GPX", self._points_du_gpx),
                         ("⛰️ Ravitaillement tous les… km", self._ravitos_reguliers)):
            b = QPushButton(texte)
            b.clicked.connect(f)
            ligne.addWidget(b)
        self.spin_pas = QDoubleSpinBox()
        self.spin_pas.setRange(2, 50)
        self.spin_pas.setValue(10)
        self.spin_pas.setSuffix(" km")
        ligne.addWidget(self.spin_pas)
        ligne.addStretch()
        l4.addLayout(ligne)
        self.label_marges = QLabel("")
        self.label_marges.setWordWrap(True)
        l4.addWidget(self.label_marges)
        self.principal.addWidget(c4)

        # ---- 5. Nutrition
        c5, l5 = self._carte("5. Manger et boire entre les points")
        self.label_plan = QLabel("")
        self.label_plan.setObjectName("texteSecondaire")
        self.label_plan.setWordWrap(True)
        l5.addWidget(self.label_plan)
        self.table_nutri = QTableWidget(0, 5)
        self.table_nutri.setHorizontalHeaderLabels(["Jusqu'à", "Temps", "Glucides", "Eau", "À prendre"])
        configurer_table_redimensionnable(self.table_nutri)
        self.table_nutri.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table_nutri.setMinimumHeight(180)
        l5.addWidget(self.table_nutri)
        self.principal.addWidget(c5)

        # ---- 6. Sacs d'assistance
        c7, l7 = self._carte("6. Sacs d'assistance")
        self.label_sacs = QLabel("")
        self.label_sacs.setWordWrap(True)
        self.label_sacs.setTextFormat(Qt.TextFormat.RichText)
        self.label_sacs.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        l7.addWidget(self.label_sacs)
        self.principal.addWidget(c7)

        # ---- 7. Checklist
        c6, l6 = self._carte("7. Checklist du sac")
        self.liste_check = QListWidget()
        self.liste_check.setStyleSheet(CASES_QSS)
        self.liste_check.setMinimumHeight(260)
        self.liste_check.itemChanged.connect(self._case_cochee)
        l6.addWidget(self.liste_check)
        ligne = QHBoxLayout()
        self.champ_perso = QLineEdit()
        self.champ_perso.setPlaceholderText("Ajouter un élément à toi (ex. bâtons, lunettes, crème…)")
        self.champ_perso.returnPressed.connect(self._ajouter_perso)
        b = QPushButton("➕ Ajouter")
        b.clicked.connect(self._ajouter_perso)
        b2 = QPushButton("🔄 Recalculer la liste")
        b2.clicked.connect(self._regenerer_checklist)
        ligne.addWidget(self.champ_perso, 1)
        ligne.addWidget(b)
        ligne.addWidget(b2)
        l6.addLayout(ligne)
        self.principal.addWidget(c6)

        # ---- Actions
        ligne = QHBoxLayout()
        b_save = QPushButton("💾 Enregistrer le roadbook")
        b_save.setObjectName("boutonPrincipal")
        b_save.clicked.connect(self._enregistrer)
        b_pdf = QPushButton("🖨️ Exporter la mini-fiche (PDF A5)")
        b_pdf.setObjectName("boutonPrincipal")
        b_pdf.clicked.connect(self._exporter_pdf)
        b_bracelet = QPushButton("⌚ Bracelet d'allures (PDF)")
        b_bracelet.setObjectName("boutonPrincipal")
        b_bracelet.clicked.connect(self._exporter_bracelet)
        ligne.addWidget(b_save)
        ligne.addWidget(b_pdf)
        ligne.addWidget(b_bracelet)
        ligne.addStretch()
        self.principal.addLayout(ligne)
        note = QLabel("Les temps sont des estimations (pente, niveau, VO₂max « estimation basse ») : garde de la "
                      "réserve sur les barrières. Les règlements de course priment sur la liste de matériel.")
        note.setObjectName("texteSecondaire")
        note.setWordWrap(True)
        self.principal.addWidget(note)
        self.principal.addStretch()

        self._finaliser()

    # ------------------------------------------------------------------
    def _carte(self, titre):
        cadre = QFrame()
        cadre.setObjectName("carteForm")
        lay = QVBoxLayout(cadre)
        t = QLabel(titre)
        t.setObjectName("titreCarte")
        lay.addWidget(t)
        return cadre, lay

    def athlete_id(self):
        return self.combo_athlete.currentData()

    def actualiser(self):
        """Changement d'athlète (ou ouverture) : repart d'un roadbook vierge."""
        self._rb_id = None
        self._trace, self._wp, self._points, self._checklist = [], [], [], []
        self._distance, self._deniv = 0.0, 0
        self.label_trace.setText("Aucun tracé chargé.")
        self._remplir_listes()
        a = self.athlete_id()
        if self._course_pre and a is not None:
            c = self._course_pre
            self._course_pre = None
            self._bloque = True
            self.champ_nom.setText(c.get("nom") or "")
            if c.get("date"):
                d = QDate.fromString(str(c["date"])[:10], "yyyy-MM-dd")
                if d.isValid():
                    self.champ_date.setDate(d)
            self._bloque = False
            if c.get("distance_km"):
                self._distance, self._deniv = float(c["distance_km"]), int(c.get("denivele_m") or 0)
        self._recalculer()

    def _remplir_listes(self, rb_selectionne=None):
        a = self.athlete_id()
        self._bloque = True
        self.combo_rb.clear()
        self.combo_rb.addItem("— Nouveau roadbook —", None)
        self.combo_course.clear()
        self.combo_course.addItem("— choisir (facultatif) —", None)
        self.combo_parcours.clear()
        self.combo_parcours.addItem("— choisir (facultatif) —", None)
        if a is not None:
            for id_, nom, d, km, dp in rbk.lister(a):
                self.combo_rb.addItem(f"{nom}" + (f" ({d})" if d else ""), id_)
            for id_, nom, d, km, dp in dcourse.courses_pour_roadbook(a):
                self.combo_course.addItem(f"{nom}" + (f" — {km:g} km" if km else ""), id_)
            for id_, nom, km in dparc.liste_courte(a, par_id=True):
                self.combo_parcours.addItem(f"{nom} — {km:g} km" if km else nom, id_)
            if rb_selectionne is None:
                pr = met.poids_serie(a, 365)
                if pr:
                    self.spin_poids.setValue(round(pr[-1][1]))
        if rb_selectionne is not None:
            self.combo_rb.setCurrentIndex(max(self.combo_rb.findData(rb_selectionne), 0))
        self._bloque = False

    # ------------------------------------------------------------------
    # Chargement
    # ------------------------------------------------------------------
    def _course_choisie(self):
        if self._bloque or self.combo_course.currentData() is None:
            return
        r = dcourse.course(self.combo_course.currentData(), "nom", "date", "distance_km", "denivele_m")
        if not r:
            return
        nom, d, km, dp = r
        self._bloque = True
        self.champ_nom.setText(nom or "")
        q = QDate.fromString(str(d or "")[:10], "yyyy-MM-dd")
        if q.isValid():
            self.champ_date.setDate(q)
        self._bloque = False
        if not self._trace:
            self._distance, self._deniv = float(km or 0), int(dp or 0)
        self._recalculer()

    def _poser_trace(self, t, nom=None):
        self._trace = t["points"]
        self._wp = t.get("waypoints") or []
        self._distance, self._deniv = t["distance_km"], t["denivele_m"]
        if nom and not self.champ_nom.text().strip():
            self.champ_nom.setText(nom)
        self._recalculer()

    def _charger_gpx(self):
        chemin, _ = QFileDialog.getOpenFileName(self, "Choisir le tracé de la course", "", "Tracés GPX (*.gpx)")
        if not chemin:
            return
        try:
            t = rbk.charger_gpx(chemin)
        except Exception as e:
            QMessageBox.warning(self, "GPX illisible", f"Impossible de lire ce fichier : {e}")
            return
        import os
        self._poser_trace(t, os.path.splitext(os.path.basename(chemin))[0])
        if self._wp and not self._points:
            if QMessageBox.question(self, "Points du GPX",
                                    f"Le fichier contient {len(self._wp)} point(s) nommé(s). "
                                    "Les reprendre comme points de passage ?") == QMessageBox.StandardButton.Yes:
                self._points_du_gpx()

    def _parcours_choisi(self):
        if self._bloque or self.combo_parcours.currentData() is None:
            return
        try:
            t = rbk.trace_depuis_parcours(self.combo_parcours.currentData())
        except Exception as e:
            QMessageBox.warning(self, "Parcours", str(e))
            return
        self._poser_trace(t, t.get("nom"))

    def _rb_choisi(self):
        if self._bloque:
            return
        id_ = self.combo_rb.currentData()
        if id_ is None:
            self._rb_id = None
            return
        d = rbk.charger(id_)
        if not d:
            return
        self._rb_id = id_
        self._bloque = True
        self.champ_nom.setText(d["nom"] or "")
        q = QDate.fromString(str(d["date_course"] or ""), "yyyy-MM-dd")
        if q.isValid():
            self.champ_date.setDate(q)
        self.champ_depart.setTime(QTime.fromString(d["depart"] or "07:00", "HH:mm"))
        i = self.combo_mode.findData(d["mode_niveau"] or "vo2")
        self.combo_mode.setCurrentIndex(max(i, 0))
        self.champ_allure.setText(d["allure_plat"] or "6:00")
        self.champ_temps.setText(d["temps_vise"] or "6:00")
        self.spin_temp.setValue(d["temperature_c"] if d["temperature_c"] is not None else 15)
        self.spin_poids.setValue(d["poids_kg"] or 70)
        i = self.combo_intensite.findData(d["intensite"] or "modere")
        self.combo_intensite.setCurrentIndex(max(i, 0))
        self.case_nuit.setChecked(d["nocturne"])
        self.case_alt.setChecked(d["altitude"])
        self._trace = d["trace"]
        self._distance, self._deniv = d["distance_km"] or 0.0, d["denivele_m"] or 0
        self._points = d["points"]
        self._checklist = d["checklist"]
        self._bloque = False
        self._recalculer()

    def _supprimer_rb(self):
        if self._rb_id is None:
            return
        if QMessageBox.question(self, "Supprimer", "Supprimer ce roadbook enregistré ?") != QMessageBox.StandardButton.Yes:
            return
        rbk.supprimer(self._rb_id)
        self.actualiser()

    # ------------------------------------------------------------------
    # Points de passage
    # ------------------------------------------------------------------
    def _points_du_gpx(self):
        for nom, km in self._wp:
            if not any(abs(p["km"] - km) < 0.2 and p["nom"] == nom for p in self._points):
                bas = nom.lower()
                type_ = ("Ravitaillement" if any(m in bas for m in ("ravit", "ravito", "aid", "food", "eau", "water"))
                         else "Barrière horaire" if any(m in bas for m in ("barri", "cut", "limite"))
                         else "Repère")
                self._points.append({"nom": nom, "km": km, "type": type_, "barriere": ""})
        self._recalculer()

    def _ajouter_point(self):
        dernier = max([p["km"] for p in self._points], default=0.0)
        self._points.append({"nom": f"Ravitaillement {sum(1 for p in self._points if p['type'] == 'Ravitaillement') + 1}",
                             "km": round(min(dernier + 10, self._distance or dernier + 10), 1),
                             "type": "Ravitaillement", "barriere": ""})
        self._recalculer()

    def _ravitos_reguliers(self):
        if not self._distance:
            QMessageBox.information(self, "Tracé requis", "Charge d'abord un tracé GPX (ou choisis une course).")
            return
        pas = self.spin_pas.value()
        k = pas
        n = sum(1 for p in self._points if p["type"] == "Ravitaillement")
        while k < self._distance - 2:
            if not any(abs(p["km"] - k) < 1.0 for p in self._points):
                n += 1
                self._points.append({"nom": f"Ravitaillement {n}", "km": round(k, 1),
                                     "type": "Ravitaillement", "barriere": ""})
            k += pas
        self._recalculer()

    def _supprimer_point(self):
        r = self.table.currentRow()
        if r < 0 or r >= len(self._passages):
            return
        ps = self._passages[r]
        for i, p in enumerate(self._points):
            if p["nom"] == ps["nom"] and abs(p["km"] - ps["km"]) < 0.06:
                del self._points[i]
                break
        self._recalculer()

    def _cellule_modifiee(self, item):
        if self._bloque or item.row() >= len(self._passages):
            return
        ps = self._passages[item.row()]
        cible = next((p for p in self._points if p["nom"] == ps["nom"] and abs(p["km"] - ps["km"]) < 0.06), None)
        if cible is None:        # départ / arrivée automatiques : on les crée en les modifiant
            cible = {"nom": ps["nom"], "km": ps["km"], "type": ps["type"], "barriere": ""}
            self._points.append(cible)
        col, txt = item.column(), item.text().strip()
        if col == 0:
            cible["nom"] = txt or cible["nom"]
        elif col == 1:
            try:
                cible["km"] = max(0.0, float(txt.replace(",", ".")))
            except ValueError:
                pass
        elif col == 3:
            cible["barriere"] = txt if rbk._hhmm(txt) else ""
        self._recalculer()

    def _type_change(self, ligne, combo):
        if self._bloque or ligne >= len(self._passages):
            return
        ps = self._passages[ligne]
        cible = next((p for p in self._points if p["nom"] == ps["nom"] and abs(p["km"] - ps["km"]) < 0.06), None)
        if cible is None:
            cible = {"nom": ps["nom"], "km": ps["km"], "type": ps["type"], "barriere": ""}
            self._points.append(cible)
        cible["type"] = combo.currentText()
        self._recalculer()

    # ------------------------------------------------------------------
    # Calculs et affichage
    # ------------------------------------------------------------------
    def _allure_plat(self):
        """-> (allure_min_km | None, message)."""
        self._facteurs = None
        if len(self._trace) < 2:
            return None, "Charge un tracé GPX pour calculer les temps de passage."
        mode = self.combo_mode.currentData()
        a = self.athlete_id()
        if mode == "allure":
            al = parser_allure(self.champ_allure.text())
            return (al, f"Allure sur le plat : {self.champ_allure.text()} /km.") if al else (None, "Allure invalide (ex. 6:00).")
        if mode == "temps":
            s = _parser_temps(self.champ_temps.text())
            if not s:
                return None, "Temps visé invalide (ex. 6:30)."
            return rbk.allure_plat_pour_duree(self._trace, s), f"Temps visé : {rbk.texte_duree(s)}."
        if mode == "appris":
            jour = self.champ_date.date().toString("yyyy-MM-dd")
            d = strat.duree_apprise(a, self._distance, self._deniv, jour)
            self._facteurs = d["facteurs"] if d else None
            if not d:
                return None, ("Pas encore assez de sorties Trail/Course sur 2 ans pour apprendre ton temps : "
                              "choisis une autre méthode.")
            msg = (f"Temps appris sur {d['nb_sorties']} de tes sorties (distance + D+"
                   + (", ajusté à la saison" if d["ajustement_saison"] else "") + f") : {rbk.texte_duree(d['secondes'])}.")
            if d["extrapolation"]:
                msg += " ⚠️ Course bien plus longue que tes sorties : estimation à prendre avec prudence."
            return rbk.allure_plat_pour_duree(self._trace, d["secondes"]), msg
        s = rbk.duree_depuis_vo2max(a, self._distance, self._deniv) if a is not None else None
        if not s:
            return None, "Pas de VO₂max estimé pour cet athlète : choisis « allure sur le plat » ou « temps visé »."
        return (rbk.allure_plat_pour_duree(self._trace, s),
                f"Temps prédit depuis ton VO₂max (estimation basse, plutôt pessimiste) : {rbk.texte_duree(s)}.")

    def _recalculer(self, *_):
        if self._bloque:
            return
        self._bloque = True
        try:
            self._calculer_et_afficher()
        finally:
            self._bloque = False

    def _calculer_et_afficher(self):
        allure, msg = self._allure_plat()
        self.label_niveau.setText(msg)
        if self._trace:
            self.label_trace.setText(f"Tracé : {_fr(self._distance)} km · D+ {self._deniv} m")
        mode = self.combo_mode.currentData()
        self.champ_allure.setEnabled(mode == "allure")
        self.champ_temps.setEnabled(mode == "temps")
        prof = rbk.profil(self._trace) if self._trace else []
        self._passages, self._plan, self._nutrition = [], None, []
        if allure and prof:
            jour = self.champ_date.date().toPython()
            self._passages = rbk.calculer_passages(
                self._trace, self._points, self.champ_depart.time().toString("HH:mm"), allure, jour)
            self._plan, self._nutrition = rbk.nutrition_par_troncon(
                self._passages, self.spin_temp.value(), self.spin_poids.value(), self.combo_intensite.currentData())
            self._scenarios = strat.calculer_scenarios(
                self._trace, self._points, self.champ_depart.time().toString("HH:mm"),
                self._passages[-1]["temps_s"], jour, self._facteurs)
            if self._scenarios:
                self._passages = self._scenarios["realiste"]["passages"]
            from noyau.nutrition.tolerances import produits_course_de
            self._sacs = strat.sacs_assistance(self._scenarios, self._nutrition, self.spin_temp.value(),
                                               produits_course_de(self.athlete_id()))
            self.label_niveau.setText(
                f"{msg} Allure plat équivalente : {int(allure)}:{int(round((allure % 1) * 60)):02d} /km · "
                f"temps estimé {rbk.texte_duree(self._passages[-1]['temps_s'])} · "
                f"arrivée vers {rbk.texte_heure(self._passages[-1]['passage'])}.")
        if not (allure and prof):
            self._scenarios, self._sacs = {}, []
        self._afficher_scenarios()
        self._afficher_sacs()
        self.profil.definir(prof, self._passages)
        self._remplir_table()
        self._remplir_nutrition()
        self._maj_checklist()
        etat, phrase = strat.verdict_barrieres(self._scenarios)
        if etat is not None:
            couleur = {"ok": VERT, "serre": ORANGE, "depasse": ROUGE}[etat]
            self.label_marges.setText(("✅ " if etat == "ok" else "⚠️ ") + phrase)
            self.label_marges.setStyleSheet(f"color: {couleur}; font-weight: 600;")
            return
        pire, nom = rbk.temps_limite_theorique(self._passages)
        if pire is None:
            self.label_marges.setText("Ajoute des barrières horaires (colonne « Barrière ») pour voir ta marge à chaque point.")
            self.label_marges.setStyleSheet("")
        elif pire < 0:
            self.label_marges.setText(f"⚠️ Barrière dépassée à « {nom} » ({-pire} min de retard sur l'estimation) : "
                                      "il faut aller plus vite que ce niveau, ou viser une autre course.")
            self.label_marges.setStyleSheet(f"color: {ROUGE}; font-weight: 600;")
        elif pire < rbk.MARGE_SERREE_MIN:
            self.label_marges.setText(f"⚠️ Marge serrée à « {nom} » : seulement {pire} min d'avance sur l'estimation.")
            self.label_marges.setStyleSheet(f"color: {ORANGE}; font-weight: 600;")
        else:
            self.label_marges.setText(f"✅ Toutes les barrières passent avec de la marge (la plus faible : {pire} min à « {nom} »).")
            self.label_marges.setStyleSheet(f"color: {VERT}; font-weight: 600;")

    def _afficher_scenarios(self):
        for code, (v, d) in self.blocs_scenarios.items():
            sc = self._scenarios.get(code)
            if not sc:
                v.setText("—")
                d.setText("")
                continue
            v.setText(rbk.texte_duree(sc["temps_s"]))
            al = sc["allure_plat"]
            marge = "" if sc["pire_marge"] is None else f" · marge mini {sc['pire_marge']} min"
            d.setText(f"arrivée {rbk.texte_heure(sc['passages'][-1]['passage'])} · plat "
                      f"{int(al)}:{int(round((al % 1) * 60)) % 60:02d}/km{marge}")
        if self._scenarios:
            f = self._scenarios
            source = ("tirés de la dispersion de tes sorties autour du modèle" if self._facteurs
                      else "écarts habituels (−6 % / +10 %)")
            self.label_scenarios.setText(
                f"Ambitieux = {round((f['ambitieux']['facteur'] - 1) * 100):+d} %, prudent = "
                f"{round((f['prudent']['facteur'] - 1) * 100):+d} % par rapport au réaliste, {source}. "
                "Pars sur le réaliste ; le prudent te dit si les barrières tiennent un jour sans.")
        else:
            self.label_scenarios.setText("")

    def _afficher_sacs(self):
        if not self._scenarios:
            self.label_sacs.setText("Charge un tracé et choisis ton niveau.")
            return
        if not self._sacs:
            self.label_sacs.setText("Mets le type « Assistance » sur les points où tes proches t'attendent : "
                                    "le logiciel prépare le contenu de chaque sac et l'heure à laquelle ils doivent y être.")
            return
        morceaux = []
        for sac in self._sacs:
            h = sac["heures"]
            lignes = "".join(f"<li>{l}</li>" for l in sac["lignes"])
            morceaux.append(
                f"<p><b>{sac['nom']}</b> (km {_fr(sac['km'])}) — tes proches : entre "
                f"{rbk.texte_heure(h['ambitieux'])} et {rbk.texte_heure(h['prudent'])}, plutôt vers "
                f"<b>{rbk.texte_heure(h['realiste'])}</b>.<br>Pour aller jusqu'à {sac['jusqua']} "
                f"({rbk.texte_duree(sac['duree_s'])}) :</p><ul>{lignes}</ul>")
        self.label_sacs.setText("".join(morceaux))

    def _exporter_bracelet(self):
        if not self._scenarios:
            QMessageBox.information(self, "Rien à exporter",
                                    "Charge un tracé et choisis ton niveau pour obtenir les temps de passage.")
            return
        nom = (self.champ_nom.text().strip() or "course").replace("/", "-")
        chemin, _ = QFileDialog.getSaveFileName(self, "Enregistrer le bracelet d'allures",
                                                f"Bracelet_{nom}.pdf", "PDF (*.pdf)")
        if not chemin:
            return
        from interface.roadbook_fiche import rendre_bracelet_pdf
        try:
            pages = rendre_bracelet_pdf(chemin, self.champ_nom.text().strip() or "Course",
                                        strat.lignes_bracelet(self._scenarios), self.champ_depart.time().toString("HH:mm"))
        except Exception as e:
            QMessageBox.warning(self, "Export impossible", str(e))
            return
        QMessageBox.information(self, "Bracelet créé",
                                f"Bracelet d'allures enregistré ({pages} page(s), 4 bandes par feuille) :\n{chemin}\n\n"
                                "Imprime en « taille réelle » (100 %), découpe une bande, protège-la avec du "
                                "ruban adhésif transparent et porte-la à l'avant-bras.")

    def _remplir_table(self):
        t = self.table
        t.clearContents()
        t.setRowCount(len(self._passages))
        t.verticalHeader().setDefaultSectionSize(38)
        for i, p in enumerate(self._passages):
            auto = p["nom"] in ("Départ", "Arrivée") and not any(
                q["nom"] == p["nom"] for q in self._points)
            sc = self._scenarios
            amb = sc["ambitieux"]["passages"][i] if sc else p
            prud = sc["prudent"]["passages"][i] if sc else p
            vals = [p["nom"], _fr(p["km"]), None, p["barriere_txt"], rbk.texte_heure(amb["passage"]),
                    rbk.texte_heure(p["passage"]), rbk.texte_heure(prud["passage"]), "", "", ""]
            if prud["marge_min"] is not None:
                m = prud["marge_min"]
                vals[7] = (f"{'−' if m < 0 else '+'}{abs(m) // 60}h{abs(m) % 60:02d}"
                           if abs(m) >= 60 else f"{'−' if m < 0 else '+'}{abs(m)} min")
            if i:
                vals[8] = f"{_fr(p['troncon_km'])} km · D+ {p['troncon_dplus']} / D− {p['troncon_dmoins']}"
                vals[9] = rbk.texte_duree(p["troncon_s"])
            for c, v in enumerate(vals):
                if c == 2:
                    combo = QComboBox()
                    combo.addItems(rbk.TYPES_POINT)
                    combo.setCurrentText(p["type"])
                    combo.currentIndexChanged.connect(lambda _x, r=i, cb=combo: self._type_change(r, cb))
                    t.setCellWidget(i, 2, combo)
                    continue
                it = QTableWidgetItem(v)
                if c >= 4:
                    it.setFlags(it.flags() & ~Qt.ItemFlag.ItemIsEditable)
                if c == 5:
                    f = it.font()
                    f.setBold(True)
                    it.setFont(f)
                if c == 7 and prud["statut"]:
                    it.setForeground(QColor({"ok": VERT, "serre": ORANGE, "depasse": ROUGE}[prud["statut"]]))
                    f = it.font()
                    f.setBold(True)
                    it.setFont(f)
                t.setItem(i, c, it)
        t.resizeColumnsToContents()
        t.setColumnWidth(2, 170)

    def _remplir_nutrition(self):
        t = self.table_nutri
        t.clearContents()
        t.setRowCount(len(self._nutrition))
        t.setWordWrap(True)
        if self._plan:
            rp = self._plan["repere_pratique"]
            self.label_plan.setText(
                f"Base : {self._plan['glucides_g_h']} g de glucides/h, {self._plan['eau_ml_h']} ml d'eau/h, "
                f"{self._plan['sodium_mg_h']} mg de sodium/h sur {rbk.texte_duree(self._passages[-1]['temps_s'])} · "
                f"au total ≈ {rp['gels']} gels, {rp['barres']} barres, {rp['boisson_effort_ml']} ml de boisson d'effort. "
                "Aliments génériques : à vérifier sur l'étiquette et à tester avant la course.")
        else:
            self.label_plan.setText("Charge un tracé et choisis ton niveau pour obtenir le plan.")
        for i, n in enumerate(self._nutrition):
            for c, v in enumerate([f"{n['nom']} (km {_fr(n['km'])})", rbk.texte_duree(n["troncon_s"]),
                                   f"{n['glucides_g']} g", f"{n['eau_ml']} ml", n["texte"]]):
                t.setItem(i, c, QTableWidgetItem(v))
        t.resizeColumnsToContents()
        t.setColumnWidth(4, 620)
        t.resizeRowsToContents()

    # ------------------------------------------------------------------
    # Checklist
    # ------------------------------------------------------------------
    def _regenerer_checklist(self, *_):
        if not self._bloque:
            self._maj_checklist()

    def _maj_checklist(self):
        if not (self._distance or self._trace):
            self._checklist = [e for e in self._checklist if e["section"] == "Perso"]
            self._afficher_checklist()
            return
        self._checklist = rbk.construire_checklist(
            self._distance, self._deniv, self.case_nuit.isChecked(), self.case_alt.isChecked(),
            (self.combo_saison.currentText() if self.combo_saison.currentIndex() > 0 else None), self._plan, self._checklist)
        self._afficher_checklist()

    def _afficher_checklist(self):
        self.liste_check.blockSignals(True)
        self.liste_check.clear()
        section = None
        for i, it in enumerate(self._checklist):
            if it["section"] != section:
                section = it["section"]
                h = QListWidgetItem(f"— {section} —")
                h.setFlags(Qt.ItemFlag.NoItemFlags)
                f = h.font()
                f.setBold(True)
                h.setFont(f)
                self.liste_check.addItem(h)
            li = QListWidgetItem(it["texte"] + (f"\n{it['raison']}" if it.get("raison") else ""))
            li.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable)
            li.setCheckState(Qt.CheckState.Checked if it.get("coche") else Qt.CheckState.Unchecked)
            li.setData(Qt.ItemDataRole.UserRole, i)
            self.liste_check.addItem(li)
        self.liste_check.blockSignals(False)

    def _case_cochee(self, li):
        i = li.data(Qt.ItemDataRole.UserRole)
        if i is not None and 0 <= i < len(self._checklist):
            self._checklist[i]["coche"] = li.checkState() == Qt.CheckState.Checked

    def _ajouter_perso(self):
        txt = self.champ_perso.text().strip()
        if not txt:
            return
        self._checklist.append({"texte": txt, "section": "Perso", "raison": "", "coche": False})
        self.champ_perso.clear()
        self._afficher_checklist()

    # ------------------------------------------------------------------
    # Enregistrement et fiche
    # ------------------------------------------------------------------
    def _donnees(self):
        return {
            "nom": self.champ_nom.text().strip() or "Course",
            "date_course": self.champ_date.date().toString("yyyy-MM-dd"),
            "depart": self.champ_depart.time().toString("HH:mm"),
            "mode_niveau": self.combo_mode.currentData(),
            "allure_plat": self.champ_allure.text(), "temps_vise": self.champ_temps.text(),
            "temperature_c": self.spin_temp.value(), "poids_kg": self.spin_poids.value(),
            "intensite": self.combo_intensite.currentData(),
            "nocturne": self.case_nuit.isChecked(), "altitude": self.case_alt.isChecked(),
            "distance_km": self._distance, "denivele_m": self._deniv,
            "trace": self._trace, "points": self._points, "checklist": self._checklist,
        }

    def _enregistrer(self):
        a = self.athlete_id()
        if a is None:
            QMessageBox.information(self, "Athlète requis", "Sélectionne d'abord un athlète.")
            return
        self._rb_id = rbk.enregistrer(a, self._donnees(), self._rb_id)
        self._remplir_listes(self._rb_id)
        QMessageBox.information(self, "Enregistré", "Le roadbook est enregistré : tu le retrouves dans la liste « Roadbook ».")

    def _exporter_pdf(self):
        if not self._passages:
            QMessageBox.information(self, "Rien à exporter",
                                    "Charge un tracé et choisis ton niveau pour obtenir les temps de passage.")
            return
        nom = (self.champ_nom.text().strip() or "course").replace("/", "-")
        chemin, _ = QFileDialog.getSaveFileName(self, "Enregistrer la mini-fiche", f"Roadbook_{nom}.pdf", "PDF (*.pdf)")
        if not chemin:
            return
        from interface.roadbook_fiche import rendre_fiche_pdf
        d = self._donnees()
        d["temps_total_s"] = self._passages[-1]["temps_s"]
        d["date_course"] = self.champ_date.date().toString("dd/MM/yyyy")
        try:
            pages = rendre_fiche_pdf(chemin, d, self._passages, rbk.profil(self._trace), self._nutrition,
                                     self._checklist, self._scenarios or None, self._sacs or None)
        except Exception as e:
            QMessageBox.warning(self, "Export impossible", str(e))
            return
        QMessageBox.information(self, "Fiche créée",
                                f"Mini-fiche A5 de {pages} page(s) enregistrée :\n{chemin}\n\n"
                                "À imprimer en « taille réelle » (100 %), puis à plastifier.")
