"""
Coach du jour (v103) — trois outils d'aide à la décision, 100 % locaux sauf
l'envoi optionnel de la séance sur Garmin Connect :
  • Séance du jour : jambes + RPE + fraîcheur + HRV -> séance adaptée, routine
    de renfort / mobilité, envoi sur la montre ;
  • Prédictions : chronos 5 km à marathon et sur un parcours avec D+ (« estimation basse ») ;
  • Ravitaillement : glucides, eau, sodium par heure.
"""

import json

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QComboBox,
    QScrollArea, QPushButton, QSpinBox, QDoubleSpinBox, QMessageBox, QTableWidget,
    QTableWidgetItem, QCheckBox,
)

from data.database import obtenir_athletes
from noyau.entrainement import coach_du_jour as cdj
from noyau.course import predictions_course as pred
from noyau.course import ravitaillement as rav
from interface.ecran_liste import obtenir_style_ecran
from interface.vma import _table, _remplir, duree_texte
from noyau.donnees import seances as dseance
from noyau.donnees import sante as dsante

COULEURS = {"vert": "#66BB6A", "orange": "#FFA726", "rouge": "#EF5350"}
LIBELLES = {"vert": "🟢 Feu vert", "orange": "🟠 Prudence", "rouge": "🔴 Repos conseillé"}


def _carte(titre):
    c = QFrame()
    c.setObjectName("carteForm")
    l = QVBoxLayout(c)
    t = QLabel(titre)
    t.setObjectName("titreCarte")
    l.addWidget(t)
    return c, l


def _note(texte):
    n = QLabel(texte)
    n.setObjectName("texteSecondaire")
    n.setWordWrap(True)
    return n


class CoachDuJour(QMainWindow):

    def __init__(self, athlete_id_initial=None):
        super().__init__()
        self.setWindowTitle("TrailMaster Pro – Coach du jour")
        self.resize(1200, 900)
        self.setStyleSheet(obtenir_style_ecran())
        self.decision = None

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.setCentralWidget(scroll)
        central = QWidget()
        scroll.setWidget(central)
        self.principal = QVBoxLayout(central)
        self.principal.setContentsMargins(25, 20, 25, 20)
        self.principal.setSpacing(15)

        titre = QLabel("🎯  Coach du jour")
        titre.setObjectName("titrePage")
        self.principal.addWidget(titre)
        self.principal.addWidget(_note(
            "Décide la séance du jour d'après tes jambes, ta RPE, ta fraîcheur, ta HRV et ton sommeil ; "
            "prédit tes chronos ; chiffre ton ravitaillement. Ce sont des repères d'entraînement, pas un avis médical."))

        barre = QHBoxLayout()
        lab = QLabel("Athlète :")
        lab.setObjectName("labelChamp")
        self.combo_athlete = QComboBox()
        self.combo_athlete.addItem("Sélectionner...", None)
        for a in obtenir_athletes():
            self.combo_athlete.addItem(f"{a[2]} {a[1]}", a[0])
        if self.combo_athlete.count() > 1:
            self.combo_athlete.setCurrentIndex(1)
        barre.addWidget(lab)
        barre.addWidget(self.combo_athlete)
        barre.addStretch()
        self.principal.addLayout(barre)

        self._construire_seance()
        self._construire_predictions()
        self._construire_ravitaillement()
        self.principal.addStretch()
        self.combo_athlete.currentIndexChanged.connect(self.actualiser)
        self.actualiser()

    # ------------------------------------------------------------ séance
    def _construire_seance(self):
        c, l = _carte("🗓️ Séance du jour")
        saisie = QHBoxLayout()
        self.spin_jambes = QSpinBox()
        self.spin_jambes.setRange(0, 10)
        self.spin_jambes.setSpecialValueText("—")
        self.spin_rpe = QSpinBox()
        self.spin_rpe.setRange(0, 10)
        self.spin_rpe.setSpecialValueText("—")
        saisie.addWidget(QLabel("Fatigue des jambes (1–10) :"))
        saisie.addWidget(self.spin_jambes)
        saisie.addWidget(QLabel("RPE de la dernière sortie (1–10) :"))
        saisie.addWidget(self.spin_rpe)
        b = QPushButton("Décider ma séance")
        b.setObjectName("boutonPrincipal")
        b.clicked.connect(self.decider)
        saisie.addWidget(b)
        saisie.addStretch()
        l.addLayout(saisie)
        self.etiquette_niveau = QLabel("")
        self.etiquette_niveau.setStyleSheet("font-size: 20px; font-weight: 700;")
        self.etiquette_titre = QLabel("")
        self.etiquette_titre.setStyleSheet("font-size: 16px; font-weight: 600;")
        self.texte_consigne = _note("")
        self.texte_raisons = _note("")
        self.texte_routine = _note("")
        l.addWidget(self.etiquette_niveau)
        l.addWidget(self.etiquette_titre)
        l.addWidget(self.texte_consigne)
        l.addWidget(self.texte_raisons)
        self.table_etapes = _table(["Étape", "Durée", "Allure cible", "FC cible"], 0, 14)
        l.addWidget(self.table_etapes)
        l.addWidget(self.texte_routine)
        actions = QHBoxLayout()
        self.bouton_garmin = QPushButton("☁️ Envoyer sur Garmin Connect")
        self.bouton_garmin.clicked.connect(self.envoyer_garmin)
        self.bouton_enregistrer = QPushButton("💾 Enregistrer dans mes séances")
        self.bouton_enregistrer.clicked.connect(self.enregistrer)
        actions.addWidget(self.bouton_garmin)
        actions.addWidget(self.bouton_enregistrer)
        actions.addStretch()
        l.addLayout(actions)
        self.etat_envoi = _note("")
        l.addWidget(self.etat_envoi)
        self.principal.addWidget(c)

    def _athlete(self):
        return self.combo_athlete.currentData()

    def decider(self):
        a = self._athlete()
        if a is None:
            self._afficher_decision(None)
            return
        j = self.spin_jambes.value() or None
        r = self.spin_rpe.value() or None
        self.decision = cdj.coach_du_jour(a, jambes=j, rpe=r)
        self._afficher_decision(self.decision)

    def _afficher_decision(self, d):
        self.table_etapes.setRowCount(0)
        if not d:
            self.etiquette_niveau.setText("Sélectionne un athlète.")
            for w in (self.etiquette_titre, self.texte_consigne, self.texte_raisons, self.texte_routine):
                w.setText("")
            self.bouton_garmin.setEnabled(False)
            self.bouton_enregistrer.setEnabled(False)
            return
        self.etiquette_niveau.setText(LIBELLES[d["niveau"]])
        self.etiquette_niveau.setStyleSheet(
            f"font-size: 20px; font-weight: 700; color: {COULEURS[d['niveau']]};")
        self.etiquette_titre.setText(d["titre"])
        self.texte_consigne.setText(d["consigne"])
        pourquoi = "Pourquoi : " + " ".join(d["raisons"]) if d["raisons"] else ""
        if d["avertissement"]:
            pourquoi = (pourquoi + "\n" if pourquoi else "") + d["avertissement"]
        self.texte_raisons.setText(pourquoi)
        self.texte_routine.setText("Renfort / mobilité : " + " ".join(d["routine"]))
        lignes = [(e["type"], f"{e['valeur']:g} min", e.get("allure_cible") or "—",
                   e.get("fc_cible") or "—") for e in d["etapes"]]
        _remplir(self.table_etapes, lignes)
        possible = bool(d["etapes"])
        self.bouton_garmin.setEnabled(possible)
        self.bouton_enregistrer.setEnabled(possible)

    def enregistrer(self):
        d, a = self.decision, self._athlete()
        if not d or not d["etapes"] or a is None:
            return
        from datetime import date
        dseance.creer({"athlete_id": a, "nom": d["titre"][:60], "type_seance": "Coach du jour",
                       "date_prevue": date.today().isoformat(), "etapes_json": json.dumps(d["etapes"])})
        QMessageBox.information(self, "Enregistrée", "La séance est dans l'écran Séances.")

    def envoyer_garmin(self):
        d = self.decision
        if not d or not d["etapes"]:
            return
        from datetime import date
        from noyau.imports import garmin_connect as gc
        if not gc.est_connecte():
            QMessageBox.information(self, "Garmin non connecté",
                                    "Connecte-toi d'abord dans Import & synchro > Garmin Connect (auto).")
            return
        self.bouton_garmin.setEnabled(False)
        self.etat_envoi.setText("Envoi en cours…")
        from interface import arriere_plan

        def travail():
            return gc.envoyer_seance(d["titre"], d["etapes"], date.today().isoformat())

        def fini(resultat, erreur):
            self.bouton_garmin.setEnabled(True)
            self.etat_envoi.setText(str(erreur) if erreur else resultat)

        arriere_plan.executer(travail, fini, proprietaire=self)

    # ------------------------------------------------------- prédictions
    def _construire_predictions(self):
        c, l = _carte("⏱️ Prédiction de chrono — estimation basse")
        self.note_pred = _note("")
        l.addWidget(self.note_pred)
        self.table_pred = _table(["Distance", "Chrono prédit", "Allure"], 0, 8)
        l.addWidget(self.table_pred)
        perso = QHBoxLayout()
        self.spin_dist = QDoubleSpinBox()
        self.spin_dist.setRange(1, 330)
        self.spin_dist.setValue(25)
        self.spin_dist.setSuffix(" km")
        self.spin_dp = QSpinBox()
        self.spin_dp.setRange(0, 20000)
        self.spin_dp.setValue(1200)
        self.spin_dp.setSuffix(" m D+")
        b = QPushButton("Prédire ce parcours")
        b.clicked.connect(self._predire_parcours)
        self.resultat_parcours = QLabel("")
        perso.addWidget(QLabel("Parcours :"))
        perso.addWidget(self.spin_dist)
        perso.addWidget(self.spin_dp)
        perso.addWidget(b)
        perso.addWidget(self.resultat_parcours)
        perso.addStretch()
        l.addLayout(perso)
        self.principal.addWidget(c)
        self.vo2 = None

    def _maj_predictions(self):
        a = self._athlete()
        self.vo2 = pred.vo2max_de_reference(a) if a else None
        if not self.vo2:
            self.note_pred.setText("Pas assez de sorties Trail/Course pour estimer ton VO₂max.")
            self.table_pred.setRowCount(0)
            self.resultat_parcours.setText("")
            return
        self.note_pred.setText(
            f"Basé sur un VO₂max estimé de {self.vo2:.1f} ml/kg/min (estimation basse : tes sorties sont "
            "rarement des efforts maximaux, les chronos sont donc plutôt pessimistes). Au-delà du semi, "
            "l'endurance et le ravitaillement comptent autant que le moteur.")
        _remplir(self.table_pred, [(x["nom"], x["duree"], x["allure"]) for x in pred.table_predictions(self.vo2)])

    def _predire_parcours(self):
        if not self.vo2:
            return
        t = pred.predire(self.vo2, self.spin_dist.value(), self.spin_dp.value())
        self.resultat_parcours.setText(
            f"≈ {pred.texte_duree(t)} (estimation basse)" if t else "Hors de la plage de calcul.")

    # ------------------------------------------------------ ravitaillement
    def _construire_ravitaillement(self):
        c, l = _carte("🍌 Plan de ravitaillement")
        saisie = QHBoxLayout()
        self.spin_duree = QDoubleSpinBox()
        self.spin_duree.setRange(0.5, 40)
        self.spin_duree.setValue(3.0)
        self.spin_duree.setSuffix(" h")
        self.spin_temp = QSpinBox()
        self.spin_temp.setRange(-15, 45)
        self.spin_temp.setValue(15)
        self.spin_temp.setSuffix(" °C")
        self.combo_intensite = QComboBox()
        for cle, nom in (("facile", "Facile"), ("modere", "Modérée"), ("soutenu", "Soutenue")):
            self.combo_intensite.addItem(nom, cle)
        self.combo_intensite.setCurrentIndex(1)
        self.case_sueur = QCheckBox("Je transpire beaucoup")
        b = QPushButton("Calculer")
        b.setObjectName("boutonPrincipal")
        b.clicked.connect(self._calculer_ravito)
        for w in (QLabel("Durée :"), self.spin_duree, QLabel("Température :"), self.spin_temp,
                  QLabel("Intensité :"), self.combo_intensite, self.case_sueur, b):
            saisie.addWidget(w)
        saisie.addStretch()
        l.addLayout(saisie)
        self.resume_ravito = _note("")
        l.addWidget(self.resume_ravito)
        self.table_ravito = _table(["Heure", "Glucides (g)", "Eau (ml)", "Sodium (mg)", "Exemple concret"], 0, 10)
        l.addWidget(self.table_ravito)
        self.notes_ravito = _note("")
        l.addWidget(self.notes_ravito)
        self.principal.addWidget(c)

    def _poids(self):
        a = self._athlete()
        if a is None:
            return 70
        r = dsante.dernier_poids(a)
        return r[0] if r else 70

    def _calculer_ravito(self):
        p = rav.plan_ravitaillement(self.spin_duree.value(), self.spin_temp.value(), self._poids(),
                                    self.combo_intensite.currentData(), self.case_sueur.isChecked())
        if not p:
            return
        t, rp = p["totaux"], p["repere_pratique"]
        self.resume_ravito.setText(
            f"Par heure : {p['glucides_g_h']} g de glucides · {p['eau_ml_h']} ml d'eau · {p['sodium_mg_h']} mg de sodium. "
            f"Total : {t['glucides_g']} g de glucides, {t['eau_l']} L, {t['sodium_mg']} mg de sodium. "
            "Le tableau propose un exemple d'aliments pour chaque heure.")
        menu = {m["heure"]: m for m in rav.menu_exemple(p)}
        _remplir(self.table_ravito, [(f"Heure {x['heure']}" + ("" if x["duree_h"] >= 1 else f" ({x['duree_h'] * 60:.0f} min)"),
                                      x["glucides_g"], x["eau_ml"], x["sodium_mg"],
                                      rav.texte_menu(menu[x["heure"]])) for x in p["heures"]])
        sale = (f" Au-delà de 4 h, ajoute du salé de temps en temps : {rav.SALE}."
                if self.spin_duree.value() >= 4 else "")
        self.notes_ravito.setText(" ".join(p["notes"]) + sale +
                                  " Aliments génériques, glucides indicatifs : vérifie l'étiquette de tes produits.")

    # -------------------------------------------------------------- global
    def actualiser(self):
        self.decision = None
        self._afficher_decision(None) if self._athlete() is None else None
        self.etiquette_niveau.setText("Saisis tes jambes et ta RPE puis « Décider ma séance »." if self._athlete() else
                                      "Sélectionne un athlète.")
        self.bouton_garmin.setEnabled(False)
        self.bouton_enregistrer.setEnabled(False)
        self._maj_predictions()
        self._calculer_ravito()
