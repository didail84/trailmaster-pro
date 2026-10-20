from datetime import date

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QComboBox,
    QPushButton,
    QFrame,
    QLineEdit,
    QSpinBox,
    QDoubleSpinBox,
    QDateEdit,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QTabWidget,
    QMessageBox,
    QScrollArea,
    QStackedWidget,
)

from data.database import connexion, obtenir_athletes
from interface.ecran_liste import (
    obtenir_style_ecran, configurer_table_redimensionnable, creer_bouton_retour_tableau_bord,
)
from interface.adaptation_musculation import proposer_charge_suivante


class Renforcement(QMainWindow):

    def __init__(self, athlete_id_initial=None):
        super().__init__()

        self.setWindowTitle("TrailMaster Pro – Renforcement & Mobilité")
        self.resize(1350, 900)
        self.setMinimumSize(1050, 700)

        central = QWidget()
        self.setCentralWidget(central)

        principal = QVBoxLayout(central)
        principal.setContentsMargins(25, 20, 25, 10)
        principal.setSpacing(12)

        principal.addWidget(creer_bouton_retour_tableau_bord(self), 0, Qt.AlignmentFlag.AlignLeft)

        titre = QLabel("💪  Renforcement & Mobilité")
        titre.setObjectName("titrePage")
        sous_titre = QLabel("Plan de musculation, suivi avec adaptation automatique, mobilité & proprioception")
        sous_titre.setObjectName("sousTitrePage")
        principal.addWidget(titre)
        principal.addWidget(sous_titre)

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

        self.onglets = QTabWidget()
        self.onglets.setDocumentMode(True)
        principal.addWidget(self.onglets, 1)

        self._construire_onglet_plan()
        self._construire_onglet_suivi()
        self._construire_onglet_mobilite()

        self.setStyleSheet(obtenir_style_ecran() + """
            QTabWidget::pane { border: none; }
            QTabBar::tab {
                background-color: #1D2328; color: #B8B8B8;
                padding: 8px 16px; margin-right: 2px;
                border-top-left-radius: 6px; border-top-right-radius: 6px;
            }
            QTabBar::tab:selected { background-color: #20262B; color: white; }
        """)

        if athlete_id_initial is not None:
            for i in range(self.combo_athlete.count()):
                if self.combo_athlete.itemData(i) == athlete_id_initial:
                    self.combo_athlete.setCurrentIndex(i)
                    break

        self.combo_athlete.currentIndexChanged.connect(self.actualiser_tout)
        self.actualiser_tout()

    def _construire_onglet_plan(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(15, 15, 15, 15)

        note = QLabel(
            "Plan de référence par bloc de 4 semaines (progression sur 24 semaines). "
            "Charge de départ donnée à titre indicatif — ajuste selon ton ressenti réel."
        )
        note.setObjectName("texteSecondaire")
        note.setWordWrap(True)
        layout.addWidget(note)

        self.table_plan = QTableWidget()
        colonnes = ["Séance", "Exercice", "Charge départ (kg)", "Bloc 1 (S1-4)", "Bloc 2 (S5-8)",
                    "Bloc 3 (S9-12)", "Bloc 4 (S13-16)", "Bloc 5 (S17-20)", "Bloc 6 (S21-24)"]
        self.table_plan.setColumnCount(len(colonnes))
        self.table_plan.setHorizontalHeaderLabels(colonnes)
        configurer_table_redimensionnable(self.table_plan)
        self.table_plan.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self.table_plan)

        self.onglets.addTab(page, "🏋️ Plan de musculation")

    def _construire_onglet_suivi(self):
        page = QWidget()
        page_scroll = QScrollArea()
        page_scroll.setWidgetResizable(True)
        page_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        page_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        page_scroll.setFrameShape(QFrame.Shape.NoFrame)
        page_scroll.setWidget(page)

        layout = QVBoxLayout(page)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(12)

        cadre_form = QFrame()
        cadre_form.setObjectName("carteForm")
        form_layout = QVBoxLayout(cadre_form)

        titre_form = QLabel("Enregistrer une séance")
        titre_form.setObjectName("titreCarte")
        form_layout.addWidget(titre_form)

        ligne_entete = QHBoxLayout()
        self.champ_date = QDateEdit()
        self.champ_date.setCalendarPopup(True)
        self.champ_date.setDate(date.today())

        label_type = QLabel("Type de séance :")
        label_type.setObjectName("labelChamp")
        self.combo_type_seance = QComboBox()
        self.combo_type_seance.addItem("🏋️ Renforcement", "Renforcement")
        self.combo_type_seance.addItem("🏃 Cardio machine", "Cardio machine")
        self.combo_type_seance.currentIndexChanged.connect(self._basculer_type_seance)

        ligne_entete.addWidget(self.champ_date)
        ligne_entete.addWidget(label_type)
        ligne_entete.addWidget(self.combo_type_seance, 1)
        form_layout.addLayout(ligne_entete)

        self.pile_type_seance = QStackedWidget()
        form_layout.addWidget(self.pile_type_seance)

        # ---- Page "Renforcement" (existant) ----
        page_renfo = QWidget()
        layout_renfo = QVBoxLayout(page_renfo)
        layout_renfo.setContentsMargins(0, 0, 0, 0)

        ligne1 = QHBoxLayout()
        self.combo_exercice = QComboBox()

        self.champ_charge = QDoubleSpinBox()
        self.champ_charge.setRange(0, 300)
        self.champ_charge.setSuffix(" kg")
        self.champ_charge.setDecimals(1)

        self.champ_series = QSpinBox()
        self.champ_series.setRange(0, 10)
        self.champ_series.setPrefix("Séries : ")

        ligne1.addWidget(self.combo_exercice, 1)
        ligne1.addWidget(self.champ_charge)
        ligne1.addWidget(self.champ_series)
        layout_renfo.addLayout(ligne1)

        ligne2 = QHBoxLayout()
        self.champ_reps = QLineEdit()
        self.champ_reps.setPlaceholderText("Reps prévues (ex. 3x10)")

        self.champ_rpe = QSpinBox()
        self.champ_rpe.setRange(6, 10)
        self.champ_rpe.setValue(7)
        self.champ_rpe.setPrefix("RPE : ")

        self.champ_douleur = QSpinBox()
        self.champ_douleur.setRange(0, 10)
        self.champ_douleur.setPrefix("Douleur : ")

        ligne2.addWidget(self.champ_reps)
        ligne2.addWidget(self.champ_rpe)
        ligne2.addWidget(self.champ_douleur)
        layout_renfo.addLayout(ligne2)

        ligne3 = QHBoxLayout()
        label_groupe = QLabel("Groupe musculaire :")
        label_groupe.setObjectName("labelChamp")
        self.combo_groupe_musculaire = QComboBox()
        self.combo_groupe_musculaire.addItems(
            ["Jambes", "Haut du corps", "Gainage / Core", "Full body"]
        )

        self.champ_duree_renfo = QDoubleSpinBox()
        self.champ_duree_renfo.setRange(0, 180)
        self.champ_duree_renfo.setSuffix(" min")
        self.champ_duree_renfo.setDecimals(0)
        self.champ_duree_renfo.setToolTip(
            "Facultatif — utilisée pour intégrer cette séance à la charge "
            "d'entraînement globale. Si laissé à 0, une durée est estimée "
            "automatiquement à partir du nombre de séries."
        )

        ligne3.addWidget(label_groupe)
        ligne3.addWidget(self.combo_groupe_musculaire, 1)
        ligne3.addWidget(self.champ_duree_renfo)
        layout_renfo.addLayout(ligne3)

        note_rpe = QLabel(
            "RPE — 6 : il reste ~4 répétitions possibles · 7 : ~3 (progression possible) · "
            "8 : ~2 (conserver) · 9 : ~1 (diminuer 5%) · 10 : échec (à éviter)\n"
            "« Groupe musculaire : Jambes » permet au coach de te prévenir si une grosse "
            "séance jambes précède une sortie intense."
        )
        note_rpe.setObjectName("texteSecondaire")
        note_rpe.setWordWrap(True)
        layout_renfo.addWidget(note_rpe)

        self.pile_type_seance.addWidget(page_renfo)

        # ---- Page "Cardio machine" (nouveau) ----
        page_cardio = QWidget()
        layout_cardio = QVBoxLayout(page_cardio)
        layout_cardio.setContentsMargins(0, 0, 0, 0)

        ligne_c1 = QHBoxLayout()
        self.combo_appareil = QComboBox()
        self.combo_appareil.addItems(["Tapis de course", "Vélo / Home-trainer", "Rameur"])

        self.champ_duree = QDoubleSpinBox()
        self.champ_duree.setRange(0, 300)
        self.champ_duree.setSuffix(" min")
        self.champ_duree.setDecimals(0)

        self.champ_distance = QDoubleSpinBox()
        self.champ_distance.setRange(0, 200)
        self.champ_distance.setSuffix(" km")
        self.champ_distance.setDecimals(2)

        ligne_c1.addWidget(self.combo_appareil, 1)
        ligne_c1.addWidget(self.champ_duree)
        ligne_c1.addWidget(self.champ_distance)
        layout_cardio.addLayout(ligne_c1)

        ligne_c2 = QHBoxLayout()
        label_intensite = QLabel("Intensité :")
        label_intensite.setObjectName("labelChamp")
        self.combo_type_intensite = QComboBox()
        self.combo_type_intensite.addItems(["Résistance (niveau)", "Vitesse (km/h)"])
        self.combo_type_intensite.currentIndexChanged.connect(self._basculer_type_intensite)

        self.pile_intensite = QStackedWidget()

        self.champ_resistance = QSpinBox()
        self.champ_resistance.setRange(0, 30)
        self.champ_resistance.setPrefix("Niveau : ")
        self.pile_intensite.addWidget(self.champ_resistance)

        self.champ_vitesse = QDoubleSpinBox()
        self.champ_vitesse.setRange(0, 60)
        self.champ_vitesse.setSuffix(" km/h")
        self.champ_vitesse.setDecimals(1)
        self.pile_intensite.addWidget(self.champ_vitesse)

        ligne_c2.addWidget(label_intensite)
        ligne_c2.addWidget(self.combo_type_intensite)
        ligne_c2.addWidget(self.pile_intensite, 1)
        layout_cardio.addLayout(ligne_c2)

        ligne_c3 = QHBoxLayout()
        self.champ_fc_moyenne = QSpinBox()
        self.champ_fc_moyenne.setRange(0, 230)
        self.champ_fc_moyenne.setPrefix("FC moy. : ")
        self.champ_fc_moyenne.setSuffix(" bpm")

        self.champ_calories = QSpinBox()
        self.champ_calories.setRange(0, 3000)
        self.champ_calories.setPrefix("Calories : ")
        self.champ_calories.setSuffix(" kcal")

        ligne_c3.addWidget(self.champ_fc_moyenne)
        ligne_c3.addWidget(self.champ_calories)
        layout_cardio.addLayout(ligne_c3)

        self.pile_type_seance.addWidget(page_cardio)

        bouton_enregistrer = QPushButton("💾 Enregistrer la séance")
        bouton_enregistrer.setObjectName("boutonPrincipal")
        bouton_enregistrer.clicked.connect(self.enregistrer_suivi)
        form_layout.addWidget(bouton_enregistrer)

        self.label_resultat_suivi = QLabel("")
        self.label_resultat_suivi.setObjectName("texteSecondaire")
        self.label_resultat_suivi.setWordWrap(True)
        form_layout.addWidget(self.label_resultat_suivi)

        layout.addWidget(cadre_form)

        titre_historique = QLabel("Historique")
        titre_historique.setObjectName("titreCarte")
        layout.addWidget(titre_historique)

        self.table_suivi = QTableWidget()
        colonnes_suivi = ["Date", "Type", "Exercice / Appareil", "Charge / Distance",
                           "Séries / Durée", "RPE / FC moy.", "Douleur / Calories",
                           "Proposition / Intensité", "Décision"]
        self.table_suivi.setColumnCount(len(colonnes_suivi))
        self.table_suivi.setHorizontalHeaderLabels(colonnes_suivi)
        configurer_table_redimensionnable(self.table_suivi)
        self.table_suivi.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table_suivi.setMinimumHeight(300)
        layout.addWidget(self.table_suivi)

        self.onglets.addTab(page_scroll, "📝 Suivi & adaptation")

    def _basculer_type_seance(self):
        self.pile_type_seance.setCurrentIndex(self.combo_type_seance.currentIndex())

    def _basculer_type_intensite(self):
        self.pile_intensite.setCurrentIndex(self.combo_type_intensite.currentIndex())

    def _construire_onglet_mobilite(self):
        page = QWidget()
        page_scroll = QScrollArea()
        page_scroll.setWidgetResizable(True)
        page_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        page_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        page_scroll.setFrameShape(QFrame.Shape.NoFrame)
        page_scroll.setWidget(page)

        layout = QVBoxLayout(page)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(12)

        titre_planning = QLabel("Routine hebdomadaire")
        titre_planning.setObjectName("titreCarte")
        layout.addWidget(titre_planning)

        self.table_planning_mobilite = QTableWidget()
        colonnes_p = ["Jour", "Durée", "Bloc", "Contenu", "Intensité", "Moment"]
        self.table_planning_mobilite.setColumnCount(len(colonnes_p))
        self.table_planning_mobilite.setHorizontalHeaderLabels(colonnes_p)
        configurer_table_redimensionnable(self.table_planning_mobilite)
        self.table_planning_mobilite.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table_planning_mobilite.setMaximumHeight(280)
        layout.addWidget(self.table_planning_mobilite)

        titre_exercices = QLabel("Exercices (mobilité & proprioception)")
        titre_exercices.setObjectName("titreCarte")
        layout.addWidget(titre_exercices)

        self.table_mobilite = QTableWidget()
        colonnes_m = ["Catégorie", "Exercice", "Moment / Objectif", "Zone",
                      "Bloc 1", "Bloc 2", "Bloc 3", "Bloc 4", "Bloc 5", "Bloc 6", "Progression"]
        self.table_mobilite.setColumnCount(len(colonnes_m))
        self.table_mobilite.setHorizontalHeaderLabels(colonnes_m)
        configurer_table_redimensionnable(self.table_mobilite)
        self.table_mobilite.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table_mobilite.setMinimumHeight(300)
        layout.addWidget(self.table_mobilite)

        titre_consignes = QLabel("Consignes")
        titre_consignes.setObjectName("titreCarte")
        layout.addWidget(titre_consignes)

        consignes = QLabel(
            "• Avant entraînement : mobilité dynamique, ne pas fatiguer le muscle.\n"
            "• Étirements : tension douce, jamais de douleur ; plutôt après ou à distance de l'effort.\n"
            "• Proprioception : qualité d'appui avant quantité, près d'un support sécurisé.\n"
            "• Progression : une seule variable à la fois (durée, amplitude, instabilité ou complexité).\n"
            "• Fatigue : si jambes lourdes, réduire la proprioception.\n"
            "• Douleur vive ou articulaire : arrêter et adapter."
        )
        consignes.setObjectName("texteSecondaire")
        consignes.setWordWrap(True)
        layout.addWidget(consignes)

        self.onglets.addTab(page_scroll, "🧘 Mobilité & Proprioception")

    def actualiser_tout(self):
        athlete_id = self.combo_athlete.currentData()

        self.table_plan.setRowCount(0)
        self.combo_exercice.clear()
        self.table_suivi.setRowCount(0)
        self.table_planning_mobilite.setRowCount(0)
        self.table_mobilite.setRowCount(0)

        if athlete_id is None:
            return

        conn = connexion()
        cur = conn.cursor()

        cur.execute(
            "SELECT groupe_seance, exercice, charge_depart_kg, bloc1, bloc2, bloc3, bloc4, bloc5, bloc6 "
            "FROM musculation_exercices WHERE athlete_id=? ORDER BY groupe_seance, id",
            (athlete_id,),
        )
        lignes = cur.fetchall()
        self.table_plan.setRowCount(len(lignes))
        for i, ligne in enumerate(lignes):
            for j, valeur in enumerate(ligne):
                self.table_plan.setItem(i, j, QTableWidgetItem("" if valeur is None else str(valeur)))
            self.combo_exercice.addItem(ligne[1])

        cur.execute(
            "SELECT date, type_seance, exercice, charge_kg, series, rpe, douleur, "
            "charge_proposee, decision, appareil, duree_min, type_intensite, "
            "valeur_intensite, distance_km, fc_moyenne, calories, groupe_musculaire "
            "FROM musculation_suivi WHERE athlete_id=? ORDER BY date DESC",
            (athlete_id,),
        )
        lignes_suivi = cur.fetchall()
        self.table_suivi.setRowCount(len(lignes_suivi))
        for i, ligne in enumerate(lignes_suivi):
            for j, valeur in enumerate(self._formater_ligne_suivi(ligne)):
                self.table_suivi.setItem(i, j, QTableWidgetItem(valeur))

        cur.execute(
            "SELECT jour, duree, bloc, contenu, intensite, moment FROM planning_mobilite "
            "WHERE athlete_id=?",
            (athlete_id,),
        )
        lignes_planning = cur.fetchall()
        self.table_planning_mobilite.setRowCount(len(lignes_planning))
        for i, ligne in enumerate(lignes_planning):
            for j, valeur in enumerate(ligne):
                self.table_planning_mobilite.setItem(i, j, QTableWidgetItem("" if valeur is None else str(valeur)))

        cur.execute(
            "SELECT categorie, exercice, moment_ou_objectif, zone, bloc1, bloc2, bloc3, bloc4, "
            "bloc5, bloc6, progression FROM mobilite_exercices WHERE athlete_id=? ORDER BY categorie, id",
            (athlete_id,),
        )
        lignes_mobilite = cur.fetchall()
        self.table_mobilite.setRowCount(len(lignes_mobilite))
        for i, ligne in enumerate(lignes_mobilite):
            for j, valeur in enumerate(ligne):
                self.table_mobilite.setItem(i, j, QTableWidgetItem("" if valeur is None else str(valeur)))

        self.table_plan.resizeColumnsToContents()
        self.table_suivi.resizeColumnsToContents()
        self.table_planning_mobilite.resizeColumnsToContents()
        self.table_mobilite.resizeColumnsToContents()

        conn.close()

    def _formater_ligne_suivi(self, ligne):
        """Met en forme une ligne d'historique (Renforcement ou Cardio machine)
        pour l'affichage dans le tableau, colonne par colonne."""
        (date_val, type_seance, exercice, charge_kg, series, rpe, douleur,
         charge_proposee, decision, appareil, duree_min, type_intensite,
         valeur_intensite, distance_km, fc_moyenne, calories, groupe_musculaire) = ligne

        if type_seance == "Cardio machine":
            intensite_txt = ""
            if valeur_intensite not in (None, ""):
                intensite_txt = f"{type_intensite} : {valeur_intensite}"
            return [
                "" if date_val is None else str(date_val),
                "🏃 Cardio machine",
                "" if appareil is None else str(appareil),
                "" if distance_km is None else f"{distance_km} km",
                "" if duree_min is None else f"{duree_min} min",
                "" if fc_moyenne is None else f"{fc_moyenne} bpm",
                "" if calories is None else f"{calories} kcal",
                intensite_txt,
                "",
            ]

        serie_txt = "" if series is None else f"{series} séries"
        if duree_min:
            serie_txt = f"{serie_txt} ({duree_min:.0f} min)" if serie_txt else f"{duree_min:.0f} min"
        type_txt = "🏋️ Renforcement"
        if groupe_musculaire:
            type_txt = f"🏋️ Renforcement — {groupe_musculaire}"

        return [
            "" if date_val is None else str(date_val),
            type_txt,
            "" if exercice is None else str(exercice),
            "" if charge_kg is None else f"{charge_kg} kg",
            serie_txt,
            "" if rpe is None else str(rpe),
            "" if douleur is None else str(douleur),
            "" if charge_proposee is None else f"{charge_proposee} kg",
            "" if decision is None else str(decision),
        ]

    def enregistrer_suivi(self):
        athlete_id = self.combo_athlete.currentData()
        if athlete_id is None:
            QMessageBox.warning(self, "Athlète requis", "Sélectionne un athlète.")
            return

        date_iso = self.champ_date.date().toString("yyyy-MM-dd")
        type_seance = self.combo_type_seance.currentData()

        conn = connexion()
        cur = conn.cursor()

        if type_seance == "Cardio machine":
            appareil = self.combo_appareil.currentText()
            duree = self.champ_duree.value()
            distance = self.champ_distance.value()
            fc_moyenne = self.champ_fc_moyenne.value() or None
            calories = self.champ_calories.value() or None

            if self.combo_type_intensite.currentIndex() == 0:
                type_intensite = "Résistance"
                valeur_intensite = f"Niveau {self.champ_resistance.value()}"
            else:
                type_intensite = "Vitesse"
                valeur_intensite = f"{self.champ_vitesse.value()} km/h"

            cur.execute(
                """INSERT INTO musculation_suivi
                   (athlete_id, date, type_seance, appareil, duree_min, type_intensite,
                    valeur_intensite, distance_km, fc_moyenne, calories)
                   VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (athlete_id, date_iso, type_seance, appareil, duree, type_intensite,
                 valeur_intensite, distance, fc_moyenne, calories),
            )
            conn.commit()
            conn.close()

            self.label_resultat_suivi.setText(
                f"✅ Enregistré : {appareil} — {duree} min, {distance} km, "
                f"{type_intensite.lower()} {valeur_intensite}."
            )
            self.actualiser_tout()
            return

        exercice = self.combo_exercice.currentText()
        if not exercice:
            conn.close()
            QMessageBox.warning(self, "Exercice requis", "Sélectionne un exercice.")
            return

        charge = self.champ_charge.value()
        series = self.champ_series.value()
        reps = self.champ_reps.text().strip()
        rpe = self.champ_rpe.value()
        douleur = self.champ_douleur.value()
        groupe_musculaire = self.combo_groupe_musculaire.currentText()
        duree = self.champ_duree_renfo.value() or None

        charge_proposee, decision = proposer_charge_suivante(charge, rpe, douleur)

        cur.execute(
            """INSERT INTO musculation_suivi
               (athlete_id, date, type_seance, exercice, charge_kg, series, reps_prevues,
                rpe, douleur, charge_proposee, decision, groupe_musculaire, duree_min)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (athlete_id, date_iso, type_seance, exercice, charge, series, reps, rpe, douleur,
             charge_proposee, decision, groupe_musculaire, duree),
        )
        id_seance_muscu = cur.lastrowid
        conn.commit()
        conn.close()

        self.label_resultat_suivi.setText(
            f"✅ Enregistré. Charge proposée pour la prochaine séance : {charge_proposee} kg — {decision}"
        )
        self.actualiser_tout()

        if douleur >= 5:
            self._proposer_creation_blessure(athlete_id, date_iso, exercice, groupe_musculaire, douleur, id_seance_muscu)

    def _proposer_creation_blessure(self, athlete_id, date_iso, exercice, groupe_musculaire, douleur, id_seance_muscu):
        reponse = QMessageBox.question(
            self, "Douleur élevée",
            f"Douleur de {douleur}/10 enregistrée sur « {exercice} ». "
            "Veux-tu créer une fiche de suivi dans « Blessures », déjà reliée à cette séance "
            "(tu pourras compléter le type et la gravité juste après) ?",
        )
        if reponse != QMessageBox.StandardButton.Yes:
            return

        conn = connexion()
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO blessures
               (athlete_id, date_debut, zone_corporelle, cause, statut, musculation_suivi_id)
               VALUES (?,?,?,?,?,?)""",
            (athlete_id, date_iso, groupe_musculaire or "Non précisée",
             f"Musculation — {exercice}", "En cours", id_seance_muscu),
        )
        conn.commit()
        conn.close()

        QMessageBox.information(
            self, "Fiche créée",
            "Fiche blessure créée dans « Blessures », reliée à cette séance — "
            "complète le type et la gravité là-bas."
        )
