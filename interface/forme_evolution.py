"""
Deux écrans à onglet, repris de la page de suivi en lecture seule :

- « Forme & fatigue » : cartes (forme, fatigue, fraîcheur), courbe forme +
  fatigue et courbe de fraîcheur, période au choix (3 mois à 2 ans) ;
- « Évolution » : une mesure au choix (VO2max, FC, allure, D+, durée,
  distance), mois par mois, avec trois repères (dernière valeur,
  meilleure valeur, variation sur la période).

Les calculs viennent de interface/coach.py (forme) et de
interface/evolution_performance.py (évolution) : aucune donnée n'est
recalculée ici.
"""

from datetime import date

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QFrame, QScrollArea,
)

from data.database import obtenir_athletes
from interface.ecran_liste import obtenir_style_ecran
from interface.courbe_multiligne import CourbeMultiLignes
from interface.coach import calculer_serie_forme, obtenir_blessures_periode
from interface.evolution_performance import MESURES_EVOLUTION, serie_evolution_mensuelle
from interface.apercu_widgets import etat_fraicheur, virgule

PERIODES_FORME = [("3 mois", 91), ("6 mois", 182), ("1 an", 365), ("2 ans", 730)]
PERIODES_EVOLUTION = [("12 mois", 12), ("24 mois", 24)]


class _EcranAthlete(QMainWindow):
    """Squelette commun : titre, sélecteur d'athlète, zone défilante."""

    def __init__(self, titre, sous_titre, athlete_id_initial=None):
        super().__init__()
        self.setWindowTitle(f"TrailMaster Pro – {titre}")
        self.resize(1300, 900)
        self.setMinimumSize(1050, 700)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.setCentralWidget(scroll)
        central = QWidget()
        scroll.setWidget(central)
        self.principal = QVBoxLayout(central)
        self.principal.setContentsMargins(25, 20, 25, 20)
        self.principal.setSpacing(15)

        t = QLabel(titre)
        t.setObjectName("titrePage")
        s = QLabel(sous_titre)
        s.setObjectName("sousTitrePage")
        s.setWordWrap(True)
        self.principal.addWidget(t)
        self.principal.addWidget(s)

        self.barre = QHBoxLayout()
        label = QLabel("Athlète :")
        label.setObjectName("labelChamp")
        self.combo_athlete = QComboBox()
        self.combo_athlete.addItem("Sélectionner...", None)
        for a in obtenir_athletes():
            self.combo_athlete.addItem(f"{a[2]} {a[1]}", a[0])
        self.barre.addWidget(label)
        self.barre.addWidget(self.combo_athlete)
        self.barre.addStretch()
        self.principal.addLayout(self.barre)
        self._athlete_initial = athlete_id_initial

    def _finaliser(self):
        self.setStyleSheet(obtenir_style_ecran() + "#carteForm QLabel { background: transparent; }")
        if self._athlete_initial is not None:
            for i in range(self.combo_athlete.count()):
                if self.combo_athlete.itemData(i) == self._athlete_initial:
                    self.combo_athlete.setCurrentIndex(i)
                    break
        elif self.combo_athlete.count() == 2:
            self.combo_athlete.setCurrentIndex(1)
        self.combo_athlete.currentIndexChanged.connect(self.actualiser)
        self.actualiser()

    @staticmethod
    def _carte(titre):
        cadre = QFrame()
        cadre.setObjectName("carteForm")
        lay = QVBoxLayout(cadre)
        t = QLabel(titre)
        t.setObjectName("texteSecondaire")
        v = QLabel("—")
        v.setStyleSheet("font-size: 24px; font-weight: 700;")
        d = QLabel("")
        d.setObjectName("texteSecondaire")
        d.setWordWrap(True)
        d.setTextFormat(Qt.TextFormat.RichText)
        lay.addWidget(t)
        lay.addWidget(v)
        lay.addWidget(d)
        cadre.valeur, cadre.detail = v, d
        return cadre

    @staticmethod
    def _cadre_courbe(titre, note=None, hauteur=260):
        cadre = QFrame()
        cadre.setObjectName("carteForm")
        lay = QVBoxLayout(cadre)
        entete = QHBoxLayout()
        t = QLabel(titre)
        t.setObjectName("titreCarte")
        entete.addWidget(t)
        entete.addStretch()
        lay.addLayout(entete)
        n = QLabel(note or "")
        n.setObjectName("texteSecondaire")
        n.setWordWrap(True)
        n.setVisible(bool(note))
        lay.addWidget(n)
        courbe = CourbeMultiLignes()
        courbe.setMinimumHeight(hauteur)
        lay.addWidget(courbe)
        cadre.titre, cadre.note, cadre.courbe, cadre.entete = t, n, courbe, entete
        return cadre

    @property
    def athlete_id(self):
        return self.combo_athlete.currentData()


# ------------------------------------------------------------------
# Forme & fatigue
# ------------------------------------------------------------------

class FormeFatigue(_EcranAthlete):

    def __init__(self, athlete_id_initial=None):
        super().__init__(
            "📈  Forme, fatigue et fraîcheur",
            "La forme monte avec les semaines d'entraînement régulières. La fatigue réagit vite "
            "après une grosse sortie. La fraîcheur est la forme moins la fatigue : positive quand "
            "tu es reposé, négative quand tu es chargé. Un jour de repos compte pour une charge de zéro.",
            athlete_id_initial,
        )
        self.combo_periode = QComboBox()
        for libelle, _ in PERIODES_FORME:
            self.combo_periode.addItem(libelle)
        self.combo_periode.setCurrentText("6 mois")
        self.combo_periode.currentIndexChanged.connect(self.actualiser)
        self.barre.insertWidget(2, QLabel("Période :"))
        self.barre.insertWidget(3, self.combo_periode)

        ligne = QHBoxLayout()
        ligne.setSpacing(15)
        self.cartes = {}
        for cle, titre in (("forme", "Forme (fitness)"), ("fatigue", "Fatigue"), ("fraicheur", "Fraîcheur")):
            self.cartes[cle] = self._carte(titre)
            ligne.addWidget(self.cartes[cle], 1)
        self.principal.addLayout(ligne)

        self.cadre_ff = self._cadre_courbe(
            "Forme et fatigue", "Survole la courbe pour lire les valeurs de chaque jour.", 280)
        self.principal.addWidget(self.cadre_ff)

        self.cadre_fr = self._cadre_courbe(
            "Fraîcheur", "Au-dessus de zéro : reposé. Sous −25 : très chargé.", 220)
        self.cadre_fr.courbe.remplissage = True
        self.principal.addWidget(self.cadre_fr)

        self.label_blessures = QLabel("")
        self.label_blessures.setObjectName("texteSecondaire")
        self.label_blessures.setWordWrap(True)
        self.principal.addWidget(self.label_blessures)
        self.principal.addStretch()
        self._finaliser()

    def actualiser(self):
        athlete_id = self.athlete_id
        for c in self.cartes.values():
            c.valeur.setText("—")
            c.detail.setText("")
        if athlete_id is None:
            self.cadre_ff.courbe.definir_series([])
            self.cadre_fr.courbe.definir_series([])
            self.label_blessures.setText("")
            return

        nb_jours = dict(PERIODES_FORME)[self.combo_periode.currentText()]
        serie = calculer_serie_forme(athlete_id, nb_jours=nb_jours)
        if not serie:
            self.cadre_ff.courbe.definir_series([])
            self.cadre_fr.courbe.definir_series([])
            return

        dernier = serie[-1]
        self.cartes["forme"].valeur.setText(virgule(dernier["fitness"]))
        self.cartes["forme"].detail.setText("moyenne 42 jours")
        self.cartes["fatigue"].valeur.setText(virgule(dernier["fatigue"]))
        self.cartes["fatigue"].detail.setText("moyenne 7 jours")
        fr = dernier["forme"]
        etat, couleur = etat_fraicheur(fr)
        self.cartes["fraicheur"].valeur.setText(f"{'+' if fr > 0 else ''}{virgule(fr)}".replace("-", "−"))
        self.cartes["fraicheur"].detail.setText(f'<span style="color:{couleur}">● {etat}</span>')

        fmt = "%d/%m/%y" if nb_jours > 200 else "%d/%m"
        self.cadre_ff.courbe.definir_series([
            {"nom": "Forme", "couleur": "#42A5F5",
             "valeurs": [(j["date"].strftime(fmt), j["fitness"]) for j in serie]},
            {"nom": "Fatigue", "couleur": "#FFA726",
             "valeurs": [(j["date"].strftime(fmt), j["fatigue"]) for j in serie]},
        ])
        self.cadre_fr.courbe.definir_series([
            {"nom": "Fraîcheur", "couleur": "#66BB6A",
             "valeurs": [(j["date"].strftime(fmt), j["forme"]) for j in serie]},
        ])

        blessures = obtenir_blessures_periode(athlete_id, serie[0]["date"], serie[-1]["date"])
        if blessures:
            morceaux = []
            for b in blessures:
                fin = f" → {b['date_fin'].strftime('%d/%m/%y')}" if b["statut"] == "Guérie" else " → en cours"
                morceaux.append(f"🩹 {b['date_debut'].strftime('%d/%m/%y')}{fin} : {b['type']} ({b['zone']})")
            self.label_blessures.setText("Blessures sur la période : " + " · ".join(morceaux))
        else:
            self.label_blessures.setText("Aucune blessure enregistrée sur la période affichée.")


# ------------------------------------------------------------------
# Évolution
# ------------------------------------------------------------------

class EvolutionPerformances(_EcranAthlete):

    def __init__(self, athlete_id_initial=None):
        super().__init__(
            "📉  Évolution des performances",
            "Une tendance de fond, mois par mois, sur jusqu'à deux ans.",
            athlete_id_initial,
        )
        self.combo_mesure = QComboBox()
        for cle, info in MESURES_EVOLUTION.items():
            self.combo_mesure.addItem(info["libelle"], cle)
        self.combo_periode = QComboBox()
        for libelle, _ in PERIODES_EVOLUTION:
            self.combo_periode.addItem(libelle)
        self.combo_periode.setCurrentText("24 mois")
        self.combo_mesure.currentIndexChanged.connect(self.actualiser)
        self.combo_periode.currentIndexChanged.connect(self.actualiser)
        self.barre.insertWidget(2, QLabel("Mesure :"))
        self.barre.insertWidget(3, self.combo_mesure)
        self.barre.insertWidget(4, self.combo_periode)

        ligne = QHBoxLayout()
        ligne.setSpacing(15)
        self.cartes = {}
        for cle, titre in (("derniere", "Dernière valeur"), ("meilleure", "Meilleure valeur"),
                           ("variation", "Variation sur la période")):
            self.cartes[cle] = self._carte(titre)
            ligne.addWidget(self.cartes[cle], 1)
        self.principal.addLayout(ligne)

        self.cadre = self._cadre_courbe("", "", 320)
        self.cadre.courbe.remplissage = True
        self.principal.addWidget(self.cadre)
        self.principal.addStretch()
        self._finaliser()

    @staticmethod
    def _format(cle, valeur):
        if valeur is None:
            return "—"
        if cle == "allure_moyenne":
            minutes = int(valeur)
            return f"{minutes}:{round((valeur - minutes) * 60):02d} /km"
        unites = {"vo2max": "", "fc_moyenne": " bpm", "denivele": " m", "duree": " h", "distance": " km"}
        decimales = 1 if cle in ("vo2max", "duree") else 0
        return virgule(valeur, decimales) + unites.get(cle, "")

    def actualiser(self):
        athlete_id = self.athlete_id
        cle = self.combo_mesure.currentData()
        info = MESURES_EVOLUTION.get(cle, {})
        self.cadre.titre.setText(info.get("libelle", ""))
        self.cadre.note.setText(info.get("note", ""))
        self.cadre.note.setVisible(True)
        for c in self.cartes.values():
            c.valeur.setText("—")
            c.detail.setText("")
        if athlete_id is None or cle is None:
            self.cadre.courbe.definir_series([])
            return

        nb_mois = dict(PERIODES_EVOLUTION)[self.combo_periode.currentText()]
        serie = serie_evolution_mensuelle(athlete_id, cle, nb_mois=nb_mois)
        self.cadre.courbe.echelle_ajustee = cle in ("vo2max", "fc_moyenne", "allure_moyenne")
        self.cadre.courbe.definir_series([
            {"nom": info.get("libelle", cle), "couleur": "#42A5F5", "valeurs": serie}
        ] if serie else [])
        if not serie:
            return

        valeurs = [v for _, v in serie if v is not None]
        premiere, derniere = valeurs[0], valeurs[-1]
        # Pour l'allure, « meilleure » = la plus basse ; pour le reste, la plus haute.
        meilleure = min(valeurs) if cle == "allure_moyenne" else max(valeurs)
        label_meilleure = next(l for l, v in serie if v == meilleure)
        self.cartes["derniere"].valeur.setText(self._format(cle, derniere))
        self.cartes["derniere"].detail.setText(f"mois {serie[-1][0]}")
        self.cartes["meilleure"].valeur.setText(self._format(cle, meilleure))
        self.cartes["meilleure"].detail.setText(f"mois {label_meilleure}")
        if premiere:
            ecart = (derniere - premiere) / premiere * 100
            if abs(ecart) < 1:
                self.cartes["variation"].valeur.setText("= stable")
            else:
                self.cartes["variation"].valeur.setText(
                    f"{'+' if ecart > 0 else '−'}{virgule(abs(ecart), 1)} %")
                # Allure : moins = mieux ; autres mesures : neutre.
                if cle == "allure_moyenne":
                    bon = ecart < 0
                    couleur = "#66BB6A" if bon else "#F9A825"
                    self.cartes["variation"].valeur.setStyleSheet(
                        f"font-size: 24px; font-weight: 700; color: {couleur};")
            self.cartes["variation"].detail.setText(f"depuis {serie[0][0]}")
