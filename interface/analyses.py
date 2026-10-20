from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QComboBox,
    QFrame,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
)

from data.database import obtenir_athletes
from interface.ecran_liste import obtenir_style_ecran, configurer_table_redimensionnable
from interface.courbe_widget import CourbeBarres
from interface.courbe_multiligne import CourbeMultiLignes
from interface.coach import (
    calculer_acwr,
    generer_alertes,
    obtenir_charges_journalieres,
    obtenir_charges_periode,
    obtenir_date_premiere_activite,
    calculer_serie_forme,
    calculer_score_forme_jour,
    obtenir_blessures_periode,
    serie_rythme_vie_actif,
    repartition_par_sport,
    PERIODES_DISPONIBLES,
)
from interface.records import calculer_records, calculer_predictions, DISTANCES_REFERENCE
from interface.vo2max import estimer_vo2max_depuis_records, estimer_vo2max_recent
from interface.allure_critique import calculer_courbe_allure_critique
from interface.evolution_performance import MESURES_EVOLUTION, serie_evolution_mensuelle


COULEUR_NIVEAU = {
    "critique": "#EF5350",
    "attention": "#F9A825",
    "info": "#42A5F5",
    "ok": "#66BB6A",
}

ICONE_NIVEAU = {
    "critique": "🛑",
    "attention": "⚠️",
    "info": "ℹ️",
    "ok": "✅",
}


class Analyses(QMainWindow):

    def __init__(self, athlete_id_initial=None):
        super().__init__()

        self.setWindowTitle("TrailMaster Pro – Analyses & Coach")
        self.resize(1300, 900)
        self.setMinimumSize(1050, 700)

        conteneur_scroll = QScrollArea()
        conteneur_scroll.setWidgetResizable(True)
        conteneur_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        conteneur_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        conteneur_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.setCentralWidget(conteneur_scroll)

        central = QWidget()
        conteneur_scroll.setWidget(central)

        principal = QVBoxLayout(central)
        principal.setContentsMargins(25, 20, 25, 20)
        principal.setSpacing(15)

        titre = QLabel("📊  Analyses & Coach")
        titre.setObjectName("titrePage")
        sous_titre = QLabel(
            "Charge d'entraînement, forme, records et conseils générés à partir des données enregistrées"
        )
        sous_titre.setObjectName("sousTitrePage")
        principal.addWidget(titre)
        principal.addWidget(sous_titre)

        # ------------------------------------------------------------
        # SÉLECTEUR ATHLÈTE
        # ------------------------------------------------------------

        barre = QHBoxLayout()
        label_athlete = QLabel("Athlète :")
        label_athlete.setObjectName("labelChamp")

        self.combo_athlete = QComboBox()
        self.athletes = obtenir_athletes()
        self.combo_athlete.addItem("Sélectionner...", None)
        for a in self.athletes:
            self.combo_athlete.addItem(f"{a[2]} {a[1]}", a[0])

        barre.addWidget(label_athlete)
        barre.addWidget(self.combo_athlete)
        barre.addStretch()
        principal.addLayout(barre)

        # ------------------------------------------------------------
        # CARTES KPI (dont le score de forme du jour)
        # ------------------------------------------------------------

        self.cartes_layout = QHBoxLayout()
        self.cartes_layout.setSpacing(15)
        principal.addLayout(self.cartes_layout)

        # ------------------------------------------------------------
        # COURBE DE CHARGE (35 jours)
        # ------------------------------------------------------------

        cadre_courbe = QFrame()
        cadre_courbe.setObjectName("carteForm")
        courbe_layout = QVBoxLayout(cadre_courbe)

        barre_titre_courbe = QHBoxLayout()
        titre_courbe = QLabel("Charge d'entraînement")
        titre_courbe.setObjectName("titreCarte")

        self.combo_periode_charge = QComboBox()
        for label, _ in PERIODES_DISPONIBLES:
            self.combo_periode_charge.addItem(label)
        self.combo_periode_charge.setCurrentText("1 mois")
        self.combo_periode_charge.currentIndexChanged.connect(self.actualiser)

        barre_titre_courbe.addWidget(titre_courbe)
        barre_titre_courbe.addStretch()
        barre_titre_courbe.addWidget(self.combo_periode_charge)
        courbe_layout.addLayout(barre_titre_courbe)

        self.courbe = CourbeBarres()
        courbe_layout.addWidget(self.courbe)
        principal.addWidget(cadre_courbe)

        # ------------------------------------------------------------
        # COURBE FITNESS / FATIGUE / FORME (180 jours)
        # ------------------------------------------------------------

        cadre_forme = QFrame()
        cadre_forme.setObjectName("carteForm")
        forme_layout = QVBoxLayout(cadre_forme)
        barre_titre_forme = QHBoxLayout()
        titre_forme = QLabel("Fitness / Fatigue / Forme — long terme")
        titre_forme.setObjectName("titreCarte")
        self.combo_periode_forme = QComboBox()
        for label, _ in PERIODES_DISPONIBLES:
            self.combo_periode_forme.addItem(label)
        self.combo_periode_forme.setCurrentText("6 mois")
        self.combo_periode_forme.currentIndexChanged.connect(self.actualiser)
        self.case_rythme_vie = QComboBox()
        self.case_rythme_vie.addItems(["Sans rythme de vie", "+ Rythme de vie actif"])
        self.case_rythme_vie.currentIndexChanged.connect(self.actualiser)
        barre_titre_forme.addWidget(titre_forme)
        barre_titre_forme.addStretch()
        barre_titre_forme.addWidget(self.combo_periode_forme)
        barre_titre_forme.addWidget(self.case_rythme_vie)
        forme_layout.addLayout(barre_titre_forme)
        note_forme = QLabel(
            "Fitness = charge de fond (moyenne 42j) · Fatigue = charge récente (moyenne 7j) · "
            "Forme = Fitness − Fatigue (positif = reposé, très négatif = fatigué). "
            "« + Rythme de vie actif » superpose les jours de semaine à journée longue "
            "(interface Réglages) pour visualiser la corrélation avec les baisses de forme."
        )
        note_forme.setObjectName("texteSecondaire")
        note_forme.setWordWrap(True)
        forme_layout.addWidget(note_forme)
        self.courbe_forme = CourbeMultiLignes()
        forme_layout.addWidget(self.courbe_forme)
        self.label_blessures_periode = QLabel("")
        self.label_blessures_periode.setObjectName("texteSecondaire")
        self.label_blessures_periode.setWordWrap(True)
        forme_layout.addWidget(self.label_blessures_periode)
        principal.addWidget(cadre_forme)

        # ------------------------------------------------------------
        # RÉPARTITION MULTISPORT (90 derniers jours)
        # ------------------------------------------------------------

        cadre_multisport = QFrame()
        cadre_multisport.setObjectName("carteForm")
        multisport_layout = QVBoxLayout(cadre_multisport)
        titre_multisport = QLabel("Répartition multisport — 90 derniers jours")
        titre_multisport.setObjectName("titreCarte")
        multisport_layout.addWidget(titre_multisport)
        note_multisport = QLabel(
            "Charge totale par type d'activité — pour ne pas sous-estimer la charge globale "
            "quand un autre sport (vélo, natation...) s'ajoute au trail."
        )
        note_multisport.setObjectName("texteSecondaire")
        note_multisport.setWordWrap(True)
        multisport_layout.addWidget(note_multisport)
        self.table_multisport = QTableWidget()
        self.table_multisport.setColumnCount(4)
        self.table_multisport.setHorizontalHeaderLabels(
            ["Sport", "Séances", "Distance (km)", "Charge cumulée"]
        )
        configurer_table_redimensionnable(self.table_multisport)
        self.table_multisport.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        multisport_layout.addWidget(self.table_multisport)
        principal.addWidget(cadre_multisport)

        # ------------------------------------------------------------
        # RECORDS PERSONNELS + PRÉDICTIONS (côte à côte)
        # ------------------------------------------------------------

        zone_records = QHBoxLayout()
        zone_records.setSpacing(15)

        cadre_records = QFrame()
        cadre_records.setObjectName("carteForm")
        records_layout = QVBoxLayout(cadre_records)
        titre_records = QLabel("🏅 Records personnels")
        titre_records.setObjectName("titreCarte")
        records_layout.addWidget(titre_records)
        self.table_records = QTableWidget()
        self.table_records.setColumnCount(3)
        self.table_records.setHorizontalHeaderLabels(["Distance", "Temps", "Date"])
        configurer_table_redimensionnable(self.table_records)
        self.table_records.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table_records.setMinimumHeight(220)
        records_layout.addWidget(self.table_records)
        zone_records.addWidget(cadre_records)

        cadre_predictions = QFrame()
        cadre_predictions.setObjectName("carteForm")
        predictions_layout = QVBoxLayout(cadre_predictions)
        titre_predictions = QLabel("🔮 Temps de course estimés")
        titre_predictions.setObjectName("titreCarte")
        predictions_layout.addWidget(titre_predictions)
        note_predictions = QLabel(
            "Formule de Riegel, à partir de tes records connus — indicatif, pas une garantie."
        )
        note_predictions.setObjectName("texteSecondaire")
        note_predictions.setWordWrap(True)
        predictions_layout.addWidget(note_predictions)
        self.table_predictions = QTableWidget()
        self.table_predictions.setColumnCount(2)
        self.table_predictions.setHorizontalHeaderLabels(["Distance", "Temps estimé"])
        configurer_table_redimensionnable(self.table_predictions)
        self.table_predictions.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table_predictions.setMinimumHeight(220)
        predictions_layout.addWidget(self.table_predictions)
        zone_records.addWidget(cadre_predictions)

        principal.addLayout(zone_records)

        # ------------------------------------------------------------
        # ALLURE CRITIQUE (courbe puissance-durée approximative)
        # ------------------------------------------------------------

        cadre_allure_critique = QFrame()
        cadre_allure_critique.setObjectName("carteForm")
        allure_critique_layout = QVBoxLayout(cadre_allure_critique)
        titre_allure_critique = QLabel("⚡ Allure critique par durée")
        titre_allure_critique.setObjectName("titreCarte")
        allure_critique_layout.addWidget(titre_allure_critique)
        note_allure_critique = QLabel(
            "Meilleure allure moyenne obtenue pour chaque palier de durée, sur les sorties de "
            "l'année écoulée — approximation par séance entière (pas une analyse seconde par "
            "seconde du tracé), utile pour repérer une tendance, pas un calcul scientifique."
        )
        note_allure_critique.setObjectName("texteSecondaire")
        note_allure_critique.setWordWrap(True)
        allure_critique_layout.addWidget(note_allure_critique)
        self.table_allure_critique = QTableWidget()
        self.table_allure_critique.setColumnCount(3)
        self.table_allure_critique.setHorizontalHeaderLabels(["Durée", "Meilleure allure", "D'après"])
        configurer_table_redimensionnable(self.table_allure_critique)
        self.table_allure_critique.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        allure_critique_layout.addWidget(self.table_allure_critique)
        principal.addWidget(cadre_allure_critique)

        # ------------------------------------------------------------
        # ÉVOLUTION DES PERFORMANCES (mois par mois, jusqu'à 2 ans)
        # ------------------------------------------------------------

        cadre_evolution = QFrame()
        cadre_evolution.setObjectName("carteForm")
        evolution_layout = QVBoxLayout(cadre_evolution)

        barre_titre_evolution = QHBoxLayout()
        titre_evolution = QLabel("📈 Évolution des performances")
        titre_evolution.setObjectName("titreCarte")

        self.combo_mesure_evolution = QComboBox()
        for cle, info in MESURES_EVOLUTION.items():
            self.combo_mesure_evolution.addItem(info["libelle"], cle)
        self.combo_mesure_evolution.currentIndexChanged.connect(self.actualiser)

        self.combo_periode_evolution = QComboBox()
        self.combo_periode_evolution.addItems(["6 mois", "1 an", "2 ans"])
        self.combo_periode_evolution.setCurrentText("2 ans")
        self.combo_periode_evolution.currentIndexChanged.connect(self.actualiser)

        barre_titre_evolution.addWidget(titre_evolution)
        barre_titre_evolution.addStretch()
        barre_titre_evolution.addWidget(self.combo_mesure_evolution)
        barre_titre_evolution.addWidget(self.combo_periode_evolution)
        evolution_layout.addLayout(barre_titre_evolution)

        self.note_evolution = QLabel("")
        self.note_evolution.setObjectName("texteSecondaire")
        self.note_evolution.setWordWrap(True)
        evolution_layout.addWidget(self.note_evolution)

        self.courbe_evolution = CourbeMultiLignes()
        evolution_layout.addWidget(self.courbe_evolution)
        principal.addWidget(cadre_evolution)

        # ------------------------------------------------------------
        # CONSEILS
        # ------------------------------------------------------------

        titre_alertes = QLabel("Conseils")
        titre_alertes.setObjectName("titreCarte")
        principal.addWidget(titre_alertes)

        self.zone_alertes = QVBoxLayout()
        self.zone_alertes.setSpacing(8)
        principal.addLayout(self.zone_alertes)

        self.setStyleSheet(obtenir_style_ecran())

        if athlete_id_initial is not None:
            for i in range(self.combo_athlete.count()):
                if self.combo_athlete.itemData(i) == athlete_id_initial:
                    self.combo_athlete.setCurrentIndex(i)
                    break

        self.combo_athlete.currentIndexChanged.connect(self.actualiser)
        self.actualiser()

    # ------------------------------------------------------------
    def _vider_layout(self, layout):
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

    def _creer_carte(self, titre, valeur, description, couleur=None):
        carte = QFrame()
        carte.setObjectName("carteForm")
        carte.setMinimumHeight(110)
        layout = QVBoxLayout(carte)

        titre_label = QLabel(titre)
        titre_label.setObjectName("titreCarte")

        valeur_label = QLabel(str(valeur))
        valeur_label.setStyleSheet(
            f"font-size: 26px; font-weight: bold; color: {couleur or 'white'};"
        )

        description_label = QLabel(description)
        description_label.setObjectName("texteSecondaire")
        description_label.setWordWrap(True)

        layout.addWidget(titre_label)
        layout.addWidget(valeur_label)
        layout.addWidget(description_label)

        return carte

    def _creer_ligne_alerte(self, alerte):
        cadre = QFrame()
        cadre.setObjectName("carteForm")
        layout = QHBoxLayout(cadre)

        icone = ICONE_NIVEAU.get(alerte["niveau"], "ℹ️")
        couleur = COULEUR_NIVEAU.get(alerte["niveau"], "#B8B8B8")

        label_icone = QLabel(icone)
        label_icone.setStyleSheet("font-size: 18px;")

        label_message = QLabel(alerte["message"])
        label_message.setWordWrap(True)
        label_message.setStyleSheet(f"color: {couleur};")

        layout.addWidget(label_icone)
        layout.addWidget(label_message, 1)

        return cadre

    def _couleur_score_forme(self, score):
        if score >= 75:
            return "#66BB6A"
        if score >= 50:
            return "#9CCC65"
        if score >= 30:
            return "#F9A825"
        return "#EF5350"

    # ------------------------------------------------------------
    def actualiser(self):
        self._vider_layout(self.cartes_layout)
        self._vider_layout(self.zone_alertes)
        self.table_records.setRowCount(0)
        self.table_predictions.setRowCount(0)

        athlete_id = self.combo_athlete.currentData()
        if athlete_id is None:
            self.courbe.definir_donnees([])
            self.courbe_forme.definir_series([])
            self.courbe_evolution.definir_series([])
            self.note_evolution.setText("")
            self.label_blessures_periode.setText("")
            self.table_multisport.setRowCount(0)
            self.table_allure_critique.setRowCount(0)
            label = QLabel("Sélectionnez un athlète pour voir ses analyses.")
            label.setObjectName("texteSecondaire")
            self.zone_alertes.addWidget(label)
            return

        # --- Cartes KPI ---
        acwr_info = calculer_acwr(athlete_id)

        couleur_acwr = "#66BB6A"
        if acwr_info["acwr"] is not None:
            if acwr_info["acwr"] > 1.5:
                couleur_acwr = "#EF5350"
            elif acwr_info["acwr"] > 1.3:
                couleur_acwr = "#F9A825"
            elif acwr_info["acwr"] < 0.8:
                couleur_acwr = "#42A5F5"

        score_forme = calculer_score_forme_jour(athlete_id)
        records = calculer_records(athlete_id)
        vo2max_info = estimer_vo2max_depuis_records(records, DISTANCES_REFERENCE)

        self.cartes_layout.addWidget(
            self._creer_carte(
                "FORME DU JOUR", f"{score_forme['score']}/100",
                score_forme["interpretation"],
                couleur=self._couleur_score_forme(score_forme["score"]),
            )
        )
        self.cartes_layout.addWidget(
            self._creer_carte(
                "CHARGE CHRONIQUE (28j)", acwr_info["charge_chronique"],
                "Moyenne quotidienne sur 28 jours",
            )
        )
        self.cartes_layout.addWidget(
            self._creer_carte(
                "CHARGE AIGUË (7j)", acwr_info["charge_aigue"],
                "Moyenne quotidienne sur 7 jours",
            )
        )
        self.cartes_layout.addWidget(
            self._creer_carte(
                "ACWR",
                acwr_info["acwr"] if acwr_info["acwr"] is not None else "--",
                acwr_info["interpretation"],
                couleur=couleur_acwr,
            )
        )
        vo2max_recent = estimer_vo2max_recent(athlete_id, jours=180)
        if vo2max_recent:
            self.cartes_layout.addWidget(
                self._creer_carte(
                    "VO2MAX RÉCENT (6 mois)", f"{vo2max_recent['vo2max']} ml/kg/min",
                    f"Meilleur effort du {str(vo2max_recent['date'])[:10]} — reflète la forme actuelle",
                    couleur="#42A5F5",
                )
            )
        if vo2max_info["meilleur_vo2max"]:
            self.cartes_layout.addWidget(
                self._creer_carte(
                    "VO2MAX RECORD (absolu)", f"{vo2max_info['meilleur_vo2max']} ml/kg/min",
                    f"D'après le record « {vo2max_info['meilleur_label']} » "
                    f"({str(vo2max_info['meilleur_date'])[:10]}) — peut dater, ne reflète "
                    "pas forcément la forme actuelle",
                    couleur="#7E57C2",
                )
            )

        # --- Courbe de charge ---
        label_periode = self.combo_periode_charge.currentText()
        nb_jours_periode = dict(PERIODES_DISPONIBLES).get(label_periode)
        if nb_jours_periode is None:  # "Tout l'historique"
            premiere_date = obtenir_date_premiere_activite(athlete_id)
            if premiere_date:
                from datetime import date
                nb_jours_periode = (date.today() - premiere_date).days + 1
            else:
                nb_jours_periode = 35

        donnees_courbe, _ = obtenir_charges_periode(athlete_id, nb_jours_periode)
        seuil = (
            acwr_info["charge_chronique"] * 1.5
            if (acwr_info["charge_chronique"] and nb_jours_periode <= 35) else None
        )
        self.courbe.definir_donnees(donnees_courbe, seuil=seuil, libelle="Charge")

        # --- Courbe Fitness/Fatigue/Forme (long terme, période au choix) ---
        label_periode_forme = self.combo_periode_forme.currentText()
        nb_jours_forme = dict(PERIODES_DISPONIBLES).get(label_periode_forme)
        if nb_jours_forme is None:  # "Tout l'historique"
            premiere_date = obtenir_date_premiere_activite(athlete_id)
            if premiere_date:
                from datetime import date
                nb_jours_forme = (date.today() - premiere_date).days + 1
            else:
                nb_jours_forme = 180

        serie_forme = calculer_serie_forme(athlete_id, nb_jours=nb_jours_forme)
        series_forme = [
            {
                "nom": "Fitness",
                "couleur": "#42A5F5",
                "valeurs": [(j["date"].strftime("%d/%m/%y"), j["fitness"]) for j in serie_forme],
            },
            {
                "nom": "Fatigue",
                "couleur": "#EF5350",
                "valeurs": [(j["date"].strftime("%d/%m/%y"), j["fatigue"]) for j in serie_forme],
            },
            {
                "nom": "Forme",
                "couleur": "#66BB6A",
                "valeurs": [(j["date"].strftime("%d/%m/%y"), j["forme"]) for j in serie_forme],
            },
        ]
        if self.case_rythme_vie.currentIndex() == 1:
            rythme_serie = serie_rythme_vie_actif(nb_jours=nb_jours_forme)
            # Ramené à une échelle comparable à la Forme (souvent entre
            # -10 et +10) plutôt que 0/100 brut, pour rester lisible sur
            # le même graphique : 0 -> inactif, valeur haute -> journée
            # longue ce jour-là.
            valeur_max_forme = max((j["forme"] for j in serie_forme), default=5) or 5
            echelle = max(abs(valeur_max_forme), 5)
            series_forme.append({
                "nom": "Rythme de vie actif",
                "couleur": "#AB47BC",
                "valeurs": [
                    (jour.strftime("%d/%m/%y"), echelle if actif else 0)
                    for jour, actif in rythme_serie
                ],
            })
        self.courbe_forme.definir_series(series_forme)

        # --- Annotations blessures sur la période affichée ---
        if serie_forme:
            date_min_forme = serie_forme[0]["date"]
            date_max_forme = serie_forme[-1]["date"]
            blessures_periode = obtenir_blessures_periode(athlete_id, date_min_forme, date_max_forme)
        else:
            blessures_periode = []

        if blessures_periode:
            morceaux = []
            for b in blessures_periode:
                periode_texte = (
                    f"{b['date_debut'].strftime('%d/%m/%y')}"
                    + (f" → {b['date_fin'].strftime('%d/%m/%y')}" if b["statut"] == "Guérie" else " → en cours")
                )
                morceaux.append(f"🩹 {periode_texte} : {b['type']} ({b['zone']})")
            self.label_blessures_periode.setText(
                "Blessures sur la période : " + " · ".join(morceaux)
            )
        else:
            self.label_blessures_periode.setText("Aucune blessure enregistrée sur la période affichée.")

        # --- Allure critique ---
        courbe_allure_critique = calculer_courbe_allure_critique(athlete_id)
        self.table_allure_critique.setRowCount(len(courbe_allure_critique))
        for i, point in enumerate(courbe_allure_critique):
            libelle_duree = (
                f"{point['palier_min']} min" if point["palier_min"] < 60
                else f"{point['palier_min'] // 60}h{point['palier_min'] % 60:02d}"
            )
            self.table_allure_critique.setItem(i, 0, QTableWidgetItem(libelle_duree))
            self.table_allure_critique.setItem(i, 1, QTableWidgetItem(f"{point['allure_texte']}/km"))
            self.table_allure_critique.setItem(
                i, 2, QTableWidgetItem(f"{point['nb_sorties_considerees']} sortie(s), meilleure le {point['date'].strftime('%d/%m/%Y')}")
            )
        self.table_allure_critique.resizeColumnsToContents()

        # --- Évolution des performances (mois par mois) ---
        mesure_evolution = self.combo_mesure_evolution.currentData()
        nb_mois = {"6 mois": 6, "1 an": 12, "2 ans": 24}.get(
            self.combo_periode_evolution.currentText(), 24
        )
        serie = serie_evolution_mensuelle(athlete_id, mesure_evolution, nb_mois=nb_mois)
        info_mesure = MESURES_EVOLUTION.get(mesure_evolution, {})
        self.courbe_evolution.definir_series([
            {
                "nom": info_mesure.get("libelle", mesure_evolution),
                "couleur": "#42A5F5",
                "valeurs": serie,
            }
        ])
        self.note_evolution.setText(info_mesure.get("note", ""))

        # --- Répartition multisport ---
        repartition = repartition_par_sport(athlete_id, nb_jours=90)
        self.table_multisport.setRowCount(len(repartition))
        for i, (type_sport, info) in enumerate(repartition.items()):
            self.table_multisport.setItem(i, 0, QTableWidgetItem(type_sport))
            self.table_multisport.setItem(i, 1, QTableWidgetItem(str(info["nb_seances"])))
            self.table_multisport.setItem(i, 2, QTableWidgetItem(str(info["distance_km"])))
            self.table_multisport.setItem(i, 3, QTableWidgetItem(str(info["charge"])))
        self.table_multisport.resizeColumnsToContents()

        # --- Records personnels ---
        lignes_records = []
        for label, _ in DISTANCES_REFERENCE:
            r = records.get(label)
            if r:
                lignes_records.append((label, r["duree_texte"], str(r["date"])[:10]))
            else:
                lignes_records.append((label, "—", "—"))
        if records.get("Plus longue sortie"):
            r = records["Plus longue sortie"]
            lignes_records.append(("Plus longue sortie", f"{r['distance_reelle']} km", str(r["date"])[:10]))
        if records.get("Plus gros dénivelé"):
            r = records["Plus gros dénivelé"]
            lignes_records.append(("Plus gros D+", f"{r['denivele']} m", str(r["date"])[:10]))

        self.table_records.setRowCount(len(lignes_records))
        for i, (label, valeur, date) in enumerate(lignes_records):
            self.table_records.setItem(i, 0, QTableWidgetItem(label))
            self.table_records.setItem(i, 1, QTableWidgetItem(valeur))
            self.table_records.setItem(i, 2, QTableWidgetItem(date))

        # --- Prédictions ---
        predictions = calculer_predictions(records)
        self.table_predictions.setRowCount(len(DISTANCES_REFERENCE))
        for i, (label, _) in enumerate(DISTANCES_REFERENCE):
            self.table_predictions.setItem(i, 0, QTableWidgetItem(label))
            if records.get(label):
                texte = f"{records[label]['duree_texte']} (record réel)"
            elif predictions.get(label):
                texte = predictions[label]["duree_texte"]
            else:
                texte = "—"
            self.table_predictions.setItem(i, 1, QTableWidgetItem(texte))

        self.table_records.resizeColumnsToContents()
        self.table_predictions.resizeColumnsToContents()

        # --- Conseils ---
        for alerte in generer_alertes(athlete_id):
            self.zone_alertes.addWidget(self._creer_ligne_alerte(alerte))
