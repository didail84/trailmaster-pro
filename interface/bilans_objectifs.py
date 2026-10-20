"""
Écrans « Bilans & objectifs » de la v98 :
  - TotauxPeriodes     (P7) totaux par semaine, mois ou année
  - ComparerPeriodes   (P6) deux périodes côte à côte
  - ObjectifsAnnuels   (P8) objectifs de l'année avec jauges
  - PlanifierCharge    (E5 + E6) simulateur de charge et volume cible
"""

from datetime import date, timedelta

from PySide6.QtCore import Qt, QDate
from PySide6.QtWidgets import (
    QHBoxLayout, QVBoxLayout, QLabel, QComboBox, QPushButton, QSpinBox, QDoubleSpinBox, QFrame,
    QDateEdit, QGridLayout,
)

import data.metriques as met
from interface.cockpit import JaugeBarre, couleur_score
from interface.courbe_widget import CourbeBarres
from interface.forme_evolution import _EcranAthlete
from interface.apercu_widgets import virgule
from interface.outils_ui import notifier
from interface.vma import _table, _remplir

VERT, ORANGE, ROUGE, BLEU = "#66BB6A", "#FFA726", "#EF5350", "#42A5F5"
MESURES = [("Distance (km)", "distance"), ("Dénivelé + (m)", "denivele"), ("Durée (h)", "duree_h"),
           ("Nombre de sorties", "sorties"), ("Charge d'entraînement", "charge")]


def _h(h):
    if h is None:
        return "—"
    return f"{int(h)} h {round((h - int(h)) * 60):02d}"


def _allure(v):
    if v is None:
        return "—"
    m = int(v)
    return f"{m}:{round((v - m) * 60):02d} /km"


class TotauxPeriodes(_EcranAthlete):

    def __init__(self, athlete_id_initial=None):
        super().__init__("🧮  Totaux par semaine, mois ou année",
                         "Tout ce que tu as fait, regroupé par période. Le dernier total est celui de la période en cours.",
                         athlete_id_initial)
        self.combo_gran = QComboBox()
        for lib, v in (("Par semaine (12)", ("semaine", 12)), ("Par mois (12)", ("mois", 12)),
                       ("Par mois (24)", ("mois", 24)), ("Par année", ("annee", 8))):
            self.combo_gran.addItem(lib, v)
        self.combo_gran.setCurrentIndex(1)
        self.combo_mesure = QComboBox()
        for lib, v in MESURES:
            self.combo_mesure.addItem(lib, v)
        for c in (self.combo_gran, self.combo_mesure):
            c.currentIndexChanged.connect(self.actualiser)
        self.barre.insertWidget(2, self.combo_gran)
        self.barre.insertWidget(3, self.combo_mesure)
        self.cadre = QFrame()
        self.cadre.setObjectName("carteForm")
        lay = QVBoxLayout(self.cadre)
        self.titre_graph = QLabel("")
        self.titre_graph.setObjectName("titreCarte")
        self.barres = CourbeBarres()
        self.barres.setMinimumHeight(260)
        lay.addWidget(self.titre_graph)
        lay.addWidget(self.barres)
        self.principal.addWidget(self.cadre)
        self.table = _table(["Période", "Sorties", "Distance", "D+", "Durée", "Charge", "Allure course"], 320)
        self.principal.addWidget(self.table)
        self.principal.addStretch()
        self._finaliser()

    def actualiser(self):
        a = self.athlete_id
        self.barres.definir_donnees([])
        _remplir(self.table, [])
        if a is None:
            return
        gran, n = self.combo_gran.currentData()
        data = met.totaux(a, gran, n)
        champ = self.combo_mesure.currentData()
        lib = self.combo_mesure.currentText()
        self.titre_graph.setText(lib)
        self.barres.definir_donnees([(d["libelle"], d[champ] or 0) for d in data], libelle=lib.split(" (")[0],
                                    unite=lib.split("(")[1].rstrip(")") if "(" in lib else "")
        _remplir(self.table, [(d["libelle"] + (" (en cours)" if d["en_cours"] else ""), d["sorties"], f"{virgule(d['distance'], 1)} km",
                               f"{d['denivele']} m", _h(d["duree_h"]), int(d["charge"] or 0), _allure(d["allure_course"]))
                              for d in reversed(data)])


class ComparerPeriodes(_EcranAthlete):

    LIGNES = [("Sorties", "sorties", lambda v: str(int(v))), ("Jours actifs", "jours_actifs", lambda v: str(int(v))),
              ("Distance", "distance", lambda v: f"{virgule(v, 1)} km"), ("Dénivelé +", "denivele", lambda v: f"{int(v)} m"),
              ("Durée", "duree_h", _h), ("Charge", "charge", lambda v: str(int(v))),
              ("Allure course/trail", "allure_course", _allure), ("FC moyenne", "fc_moy", lambda v: f"{int(v)} bpm"),
              ("Plus longue sortie", "plus_longue", lambda v: f"{virgule(v, 1)} km"),
              ("Plus gros dénivelé", "plus_gros_d", lambda v: f"{int(v)} m")]
    MEILLEUR_BAS = ("allure_course",)

    def __init__(self, athlete_id_initial=None):
        super().__init__("🔀  Comparer deux périodes",
                         "Choisis deux périodes : A est la référence, B est celle que tu compares. Les flèches montrent l'évolution de B par rapport à A.",
                         athlete_id_initial)
        self.combo_pre = QComboBox()
        self.combo_pre.addItem("Dates libres…", None)
        for lib, v in met.periodes_predefinies().items():
            self.combo_pre.addItem(lib, v)
        self.combo_pre.setCurrentIndex(1)
        self.combo_pre.currentIndexChanged.connect(self._preset)
        self.barre.insertWidget(2, self.combo_pre)
        self.dates = {}
        ligne = QHBoxLayout()
        for cle, lib in (("a1", "A du"), ("a2", "au"), ("b1", "B du"), ("b2", "au")):
            ligne.addWidget(QLabel(lib))
            de = QDateEdit()
            de.setCalendarPopup(True)
            de.setDisplayFormat("dd/MM/yyyy")
            de.dateChanged.connect(self._libre)
            self.dates[cle] = de
            ligne.addWidget(de)
        ligne.addStretch()
        self.principal.addLayout(ligne)
        self.table = _table(["", "Période A", "Période B", "Écart", "%"], 380)
        self.principal.addWidget(self.table)
        self.cadre = QFrame()
        self.cadre.setObjectName("carteForm")
        lay = QVBoxLayout(self.cadre)
        self.verdict = QLabel("")
        self.verdict.setWordWrap(True)
        self.verdict.setTextFormat(Qt.TextFormat.RichText)
        lay.addWidget(self.verdict)
        self.principal.addWidget(self.cadre)
        self.principal.addStretch()
        self._verrou = False
        self._finaliser()

    def _preset(self):
        v = self.combo_pre.currentData()
        if v:
            self._verrou = True
            for cle, d in zip(("a1", "a2", "b1", "b2"), v):
                self.dates[cle].setDate(QDate(d.year, d.month, d.day))
            self._verrou = False
        self.actualiser()

    def _libre(self):
        if not self._verrou:
            self._verrou = True
            self.combo_pre.setCurrentIndex(0)
            self._verrou = False
            self.actualiser()

    def actualiser(self):
        a = self.athlete_id
        if self.combo_pre.currentData() and not self._verrou:
            v = self.combo_pre.currentData()
            self._verrou = True
            for cle, d in zip(("a1", "a2", "b1", "b2"), v):
                self.dates[cle].setDate(QDate(d.year, d.month, d.day))
            self._verrou = False
        _remplir(self.table, [])
        self.verdict.setText("")
        if a is None:
            return
        d = {k: w.date().toPython() for k, w in self.dates.items()}
        r = met.comparer_periodes(a, d["a1"], d["a2"], d["b1"], d["b2"])
        lignes, mieux, moins = [], 0, 0
        for lib, cle, fmt in self.LIGNES:
            va, vb = r["a"].get(cle), r["b"].get(cle)
            ecart, pct = r["ecarts"][cle]
            if va is None or vb is None:
                lignes.append((lib, fmt(va) if va is not None else "—", fmt(vb) if vb is not None else "—", "—", ""))
                continue
            flèche = "" if not ecart else ("▲" if ecart > 0 else "▼")
            bon = (ecart < 0) if cle in self.MEILLEUR_BAS else (ecart > 0)
            if ecart:
                mieux += bon
                moins += not bon
            signe = "+" if ecart > 0 else "−" if ecart < 0 else ""
            txt_e = fmt(abs(ecart)) if cle != "allure_course" else _allure(abs(ecart))
            lignes.append((lib, fmt(va), fmt(vb), f"{flèche} {signe}{txt_e}" if ecart else "=",
                           f"{signe}{abs(pct)} %" if pct is not None and ecart else ""))
        _remplir(self.table, lignes)
        self.verdict.setText(f"B fait <b>mieux</b> que A sur {mieux} indicateur(s) et <b>moins bien</b> sur {moins}.")


class ObjectifsAnnuels(_EcranAthlete):

    def __init__(self, athlete_id_initial=None):
        super().__init__("🏆  Objectifs de l'année",
                         "Fixe ce que tu veux atteindre cette année : la jauge te dit si tu es dans le rythme (trait blanc = "
                         "où tu devrais en être aujourd'hui) et où tu finiras à ce rythme (zone claire).", athlete_id_initial)
        self.spin_annee = QSpinBox()
        self.spin_annee.setRange(2000, 2100)
        self.spin_annee.setValue(date.today().year)
        self.spin_annee.valueChanged.connect(self.actualiser)
        self.barre.insertWidget(2, QLabel("Année :"))
        self.barre.insertWidget(3, self.spin_annee)
        self.zone = QVBoxLayout()
        self.principal.addLayout(self.zone)
        self.principal.addStretch()
        self.saisies = {}
        self._finaliser()

    def actualiser(self):
        while self.zone.count():
            it = self.zone.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        a = self.athlete_id
        if a is None:
            return
        annee = self.spin_annee.value()
        for p in met.progression_annuelle(a, annee):
            cadre = QFrame()
            cadre.setObjectName("carteForm")
            lay = QVBoxLayout(cadre)
            tete = QHBoxLayout()
            titre = QLabel(f"{p['libelle']}")
            titre.setObjectName("titreCarte")
            tete.addWidget(titre)
            tete.addStretch()
            spin = QDoubleSpinBox()
            spin.setRange(0, 1000000)
            spin.setDecimals(0)
            spin.setSingleStep(50)
            spin.setSuffix(f" {p['unite']}" if p["unite"] else "")
            spin.setSpecialValueText("Pas d'objectif")
            spin.setValue(p["cible"] or 0)
            spin.editingFinished.connect(lambda c=p["cle"], s=spin: self._enregistrer(c, s.value()))
            tete.addWidget(QLabel("Objectif :"))
            tete.addWidget(spin)
            lay.addLayout(tete)
            if p["cible"]:
                j = JaugeBarre()
                coul = {"atteint": VERT, "avance": VERT, "rythme": BLEU, "retard": ORANGE}[p["statut"]]
                j.definir(p["pct"], repere=p["attendu"] / p["cible"] * 100,
                          projection=(p["projection"] / p["cible"] * 100) if p["projection"] else None, couleur=coul)
                lay.addWidget(j)
                txt = {"atteint": "🎉 Objectif atteint !", "avance": "En avance sur le rythme", "rythme": "Dans le rythme",
                       "retard": "En retard sur le rythme"}[p["statut"]]
                detail = (f"{txt} — {virgule(p['realise'], 0)} / {virgule(p['cible'], 0)} {p['unite']} ({round(p['pct'])} %)"
                          + (f" · à ce rythme : {virgule(p['projection'], 0)} {p['unite']} fin d'année" if p["projection"] and p["statut"] != "atteint" else ""))
                lab = QLabel(detail)
            else:
                lab = QLabel(f"Réalisé depuis le 1er janvier : {virgule(p['realise'], 0)} {p['unite']}")
            lab.setObjectName("texteSecondaire")
            lab.setWordWrap(True)
            lay.addWidget(lab)
            self.zone.addWidget(cadre)

    def _enregistrer(self, cle, valeur):
        if self.athlete_id is None:
            return
        met.definir_objectif_annuel(self.athlete_id, self.spin_annee.value(), cle, valeur)
        notifier("Objectif enregistré", parent=self)
        self.actualiser()


class PlanifierCharge(_EcranAthlete):
    """E6 (volume cible de la semaine) + E5 (simulateur de charge)."""

    JOURS = ["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"]

    def __init__(self, athlete_id_initial=None):
        super().__init__("🧪  Planifier la charge",
                         "En haut : le volume conseillé pour cette semaine. En bas : un simulateur — ajoute des séances "
                         "prévues et vois comment seront ta forme et ta fatigue dans 2 semaines, avant de les faire.",
                         athlete_id_initial)
        self.cadre_cible = QFrame()
        self.cadre_cible.setObjectName("carteForm")
        lay = QVBoxLayout(self.cadre_cible)
        t = QLabel("Volume cible de la semaine")
        t.setObjectName("titreCarte")
        self.motif = QLabel("")
        self.motif.setObjectName("texteSecondaire")
        self.motif.setWordWrap(True)
        self.grille = QGridLayout()
        lay.addWidget(t)
        lay.addWidget(self.motif)
        lay.addLayout(self.grille)
        self.principal.addWidget(self.cadre_cible)

        from interface.courbe_multiligne import CourbeMultiLignes
        cadre = QFrame()
        cadre.setObjectName("carteForm")
        lay2 = QVBoxLayout(cadre)
        t2 = QLabel("Simulateur : séances prévues")
        t2.setObjectName("titreCarte")
        lay2.addWidget(t2)
        self.lignes = []
        grille = QGridLayout()
        for i in range(14):
            j = date.today() + timedelta(days=i + 1)
            lab = QLabel(f"{self.JOURS[j.weekday()]} {j.day:02d}/{j.month:02d}")
            duree = QSpinBox()
            duree.setRange(0, 600)
            duree.setSuffix(" min")
            duree.setSingleStep(15)
            inten = QComboBox()
            inten.addItems(list(met.INTENSITES))
            inten.setCurrentText("Modérée")
            duree.valueChanged.connect(self._simuler)
            inten.currentIndexChanged.connect(self._simuler)
            grille.addWidget(lab, i % 7, (i // 7) * 3)
            grille.addWidget(duree, i % 7, (i // 7) * 3 + 1)
            grille.addWidget(inten, i % 7, (i // 7) * 3 + 2)
            self.lignes.append((j, duree, inten))
        lay2.addLayout(grille)
        self.courbe = CourbeMultiLignes()
        self.courbe.setMinimumHeight(260)
        self.resume = QLabel("")
        self.resume.setObjectName("texteSecondaire")
        self.resume.setWordWrap(True)
        lay2.addWidget(self.courbe)
        lay2.addWidget(self.resume)
        self.principal.addWidget(cadre)
        self.principal.addStretch()
        self._finaliser()

    def actualiser(self):
        a = self.athlete_id
        while self.grille.count():
            it = self.grille.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        if a is None:
            return
        v = met.volume_cible_semaine(a)
        if not v:
            self.motif.setText("Pas assez d'historique (3 semaines complètes minimum) pour proposer un volume.")
        else:
            self.motif.setText(v["motif"] + f" Il reste {v['jours_restants']} jour(s) dans la semaine.")
            for r, (cle, lib, fmt) in enumerate((("distance", "Distance", lambda x: f"{virgule(x, 1)} km"),
                                                 ("denivele", "Dénivelé +", lambda x: f"{int(x)} m"),
                                                 ("duree_h", "Durée", _h), ("charge", "Charge", lambda x: str(int(x))))):
                self.grille.addWidget(QLabel(lib), r, 0)
                j = JaugeBarre()
                pct = v["pct"][cle]
                j.definir(pct, repere=100, couleur=VERT if pct >= 100 else BLEU if pct >= 50 else ORANGE)
                self.grille.addWidget(j, r, 1)
                self.grille.addWidget(QLabel(f"{fmt(v['fait'][cle])} / {fmt(v['cible'][cle])}"), r, 2)
            self.grille.setColumnStretch(1, 1)
        self._simuler()

    def _simuler(self):
        a = self.athlete_id
        if a is None:
            self.courbe.definir_series([])
            return
        charges = {}
        for j, duree, inten in self.lignes:
            if duree.value() > 0:
                charges[j] = met.charge_seance(a, duree.value(), inten.currentText())
        s = met.simuler_charge(a, charges, 14, 45)
        fmt = lambda x: x["date"].strftime("%d/%m")
        self.courbe.reperes = [(0, "", "#3A4046")]
        self.courbe.definir_series([
            {"nom": "Forme", "couleur": BLEU, "valeurs": [(fmt(x), round(x["fitness"], 1)) for x in s]},
            {"nom": "Fatigue", "couleur": ORANGE, "valeurs": [(fmt(x), round(x["fatigue"], 1)) for x in s]},
            {"nom": "Fraîcheur", "couleur": VERT, "valeurs": [(fmt(x), round(x["forme"], 1)) for x in s]},
        ])
        fin = s[-1]
        total = sum(charges.values())
        self.resume.setText(
            f"Charge prévue sur 14 jours : {round(total)}. Dans 2 semaines : forme {round(fin['fitness'])}, fatigue "
            f"{round(fin['fatigue'])}, fraîcheur {round(fin['forme']):+d}. "
            + ("Une fraîcheur entre 0 et +15 est idéale pour une course." if charges else "Ajoute des séances pour simuler."))
