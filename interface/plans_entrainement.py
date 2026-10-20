import json
from datetime import date, timedelta

from PySide6.QtCore import Qt, QDate
from PySide6.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QFormLayout,
    QLabel,
    QPushButton,
    QComboBox,
    QLineEdit,
    QSpinBox,
    QDateEdit,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QFrame,
    QMessageBox,
    QScrollArea,
    QFileDialog,
    QInputDialog,
)

from data.database import connexion, creer_base_de_donnees, obtenir_athletes, affichage_simplifie_actif
from interface.ecran_liste import obtenir_style_ecran, configurer_table_redimensionnable
from interface.generateur_plan import (
    generer_plan,
    date_seance,
    PARAMETRES_DISTANCE,
    FACTEUR_NIVEAU,
    NOMS_JOURS,
)
from interface.records import calculer_records, calculer_predictions, DISTANCES_REFERENCE
from interface.replanification_dialog import DialogueReplanification
from interface.dialogue_programme_ultra import DialogueProgrammeUltra
from interface.export_ics import generer_ics
from interface.generateur_ultra import obtenir_blocs_plan, generer_rapport_bloc


# Correspondance entre les distances de ce module et les libellés
# utilisés par interface/records.py, pour la suggestion d'allure.
CORRESPONDANCE_RECORDS = {
    "10 km": "10 km",
    "Semi-marathon": "Semi-marathon",
    "Marathon": "Marathon",
}


def _prochain_lundi():
    aujourdhui = date.today()
    delta = (7 - aujourdhui.weekday()) % 7
    return aujourdhui + timedelta(days=delta or 7)


class PlansEntrainement(QMainWindow):

    def __init__(self, athlete_id_initial=None):
        super().__init__()

        creer_base_de_donnees()

        self.setWindowTitle("TrailMaster Pro – Plans d'entraînement")
        self.resize(1300, 900)
        self.setMinimumSize(1050, 700)

        self.plan_apercu = None
        self.plans_ids = []

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

        titre = QLabel("📅  Plans d'entraînement")
        titre.setObjectName("titrePage")
        sous_titre = QLabel(
            "Génère un plan complet par objectif (10 km, semi, marathon, trail...) — "
            "périodisation base/développement/affûtage, volume progressif"
        )
        sous_titre.setObjectName("sousTitrePage")
        principal.addWidget(titre)
        principal.addWidget(sous_titre)

        # ------------------------------------------------------------
        # FORMULAIRE DE GÉNÉRATION
        # ------------------------------------------------------------

        cadre_form = QFrame()
        cadre_form.setObjectName("carteForm")
        form_layout = QVBoxLayout(cadre_form)

        barre_titre_form = QHBoxLayout()
        titre_form = QLabel("Nouveau plan")
        titre_form.setObjectName("titreCarte")
        barre_titre_form.addWidget(titre_form)
        barre_titre_form.addStretch()
        bouton_programme_ultra = QPushButton("🏔️ Programme Ultra long terme (2 ans)")
        bouton_programme_ultra.setObjectName("boutonSecondaire")
        bouton_programme_ultra.clicked.connect(self.ouvrir_programme_ultra)
        barre_titre_form.addWidget(bouton_programme_ultra)
        form_layout.addLayout(barre_titre_form)

        note_ultra = QLabel(
            "Pour un objectif à plusieurs mois/années (ex. un ultra-trail dans 2 ans) avec "
            "progression par étapes, musculation intégrée et courses de préparation — plutôt "
            "que le formulaire ci-dessous, pensé pour un plan classique de quelques semaines."
        )
        note_ultra.setObjectName("texteSecondaire")
        note_ultra.setWordWrap(True)
        form_layout.addWidget(note_ultra)

        if affichage_simplifie_actif():
            bouton_programme_ultra.setVisible(False)
            note_ultra.setVisible(False)

        entete_form = QFormLayout()

        self.combo_athlete = QComboBox()
        self.athletes = obtenir_athletes()
        self.combo_athlete.addItem("Sélectionner...", None)
        for a in self.athletes:
            self.combo_athlete.addItem(f"{a[2]} {a[1]}", a[0])

        self.champ_nom = QLineEdit()
        self.champ_nom.setPlaceholderText("Ex. Préparation semi de printemps")

        self.combo_distance = QComboBox()
        self.combo_distance.addItems(list(PARAMETRES_DISTANCE.keys()))

        self.combo_niveau = QComboBox()
        self.combo_niveau.addItems(list(FACTEUR_NIVEAU.keys()))
        self.combo_niveau.setCurrentText("Intermédiaire")

        self.spin_semaines = QSpinBox()
        self.spin_semaines.setRange(4, 24)
        self.spin_semaines.setValue(12)

        self.spin_jours = QSpinBox()
        self.spin_jours.setRange(3, 6)
        self.spin_jours.setValue(4)

        barre_allure = QHBoxLayout()
        self.champ_allure = QLineEdit()
        self.champ_allure.setPlaceholderText("mm:ss / km, ex. 5:30")
        bouton_suggerer = QPushButton("Suggérer depuis mes records")
        bouton_suggerer.setObjectName("boutonSecondaire")
        bouton_suggerer.clicked.connect(self.suggerer_allure)
        barre_allure.addWidget(self.champ_allure)
        barre_allure.addWidget(bouton_suggerer)

        self.champ_date_debut = QDateEdit()
        self.champ_date_debut.setCalendarPopup(True)
        self.champ_date_debut.setDate(QDate(_prochain_lundi()))

        entete_form.addRow("Athlète :", self.combo_athlete)
        entete_form.addRow("Nom du plan :", self.champ_nom)
        entete_form.addRow("Objectif :", self.combo_distance)
        entete_form.addRow("Niveau :", self.combo_niveau)
        entete_form.addRow("Durée (semaines) :", self.spin_semaines)
        entete_form.addRow("Jours d'entraînement/semaine :", self.spin_jours)
        entete_form.addRow("Allure objectif :", barre_allure)
        entete_form.addRow("Date de début (lundi) :", self.champ_date_debut)

        form_layout.addLayout(entete_form)

        barre_boutons_generation = QHBoxLayout()
        bouton_apercu = QPushButton("👁 Aperçu du plan")
        bouton_apercu.setObjectName("boutonSecondaire")
        bouton_apercu.clicked.connect(self.generer_apercu)
        self.bouton_enregistrer_plan = QPushButton("💾 Enregistrer ce plan")
        self.bouton_enregistrer_plan.setObjectName("boutonPrincipal")
        self.bouton_enregistrer_plan.setEnabled(False)
        self.bouton_enregistrer_plan.clicked.connect(self.enregistrer_plan)
        barre_boutons_generation.addWidget(bouton_apercu)
        barre_boutons_generation.addWidget(self.bouton_enregistrer_plan)
        form_layout.addLayout(barre_boutons_generation)

        # --- Aperçu semaine par semaine ---
        self.table_apercu = QTableWidget()
        self.table_apercu.setColumnCount(5)
        self.table_apercu.setHorizontalHeaderLabels(
            ["Semaine", "Phase", "Volume prévu", "Sortie longue", "Séances"]
        )
        configurer_table_redimensionnable(self.table_apercu)
        self.table_apercu.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table_apercu.setMinimumHeight(260)
        form_layout.addWidget(self.table_apercu)

        principal.addWidget(cadre_form)

        # ------------------------------------------------------------
        # PLANS EXISTANTS
        # ------------------------------------------------------------

        titre_liste = QLabel("Plans enregistrés")
        titre_liste.setObjectName("titreCarte")
        principal.addWidget(titre_liste)

        self.table_plans = QTableWidget()
        self.table_plans.setColumnCount(6)
        self.table_plans.setHorizontalHeaderLabels(
            ["Nom", "Objectif", "Niveau", "Semaines", "Début", "Séances réalisées"]
        )
        configurer_table_redimensionnable(self.table_plans)
        self.table_plans.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table_plans.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        principal.addWidget(self.table_plans)

        barre_actions_plan = QHBoxLayout()
        bouton_supprimer_plan = QPushButton("Supprimer le plan sélectionné (et ses séances)")
        bouton_supprimer_plan.setObjectName("boutonSecondaire")
        bouton_supprimer_plan.clicked.connect(self.supprimer_plan)
        bouton_replanifier = QPushButton("🔄 Replanifier automatiquement")
        bouton_replanifier.setObjectName("boutonPrincipal")
        bouton_replanifier.clicked.connect(self.ouvrir_replanification)
        bouton_export_ics = QPushButton("📆 Exporter calendrier (.ics)")
        bouton_export_ics.setObjectName("boutonSecondaire")
        bouton_export_ics.clicked.connect(self.exporter_calendrier)
        bouton_rapport_bloc = QPushButton("📄 Rapport de bloc")
        bouton_rapport_bloc.setObjectName("boutonSecondaire")
        bouton_rapport_bloc.clicked.connect(self.generer_rapport_bloc_selectionne)
        barre_actions_plan.addWidget(bouton_supprimer_plan)
        barre_actions_plan.addWidget(bouton_replanifier)
        barre_actions_plan.addWidget(bouton_export_ics)
        barre_actions_plan.addWidget(bouton_rapport_bloc)
        principal.addLayout(barre_actions_plan)

        note_export_ics = QLabel(
            "« Exporter calendrier » génère un fichier .ics avec les séances à venir du plan "
            "sélectionné (ou de tous tes plans si aucun n'est sélectionné) — importable dans "
            "Google Calendar, Apple Calendar ou tout autre agenda, pour les consulter depuis "
            "ton téléphone."
        )
        note_export_ics.setObjectName("texteSecondaire")
        note_export_ics.setWordWrap(True)
        principal.addWidget(note_export_ics)

        note_replanification = QLabel(
            "« Replanifier automatiquement » regarde les séances ratées, ta charge "
            "d'entraînement (ACWR) et ta fréquence cardiaque récente, puis ajuste les "
            "séances à venir du plan sélectionné (volume, intensité, ou rattrapage d'une "
            "séance manquée) — jamais les séances déjà passées. Toujours expliqué en clair, "
            "avec un commentaire IA optionnel en plus."
        )
        note_replanification.setObjectName("texteSecondaire")
        note_replanification.setWordWrap(True)
        principal.addWidget(note_replanification)

        if affichage_simplifie_actif():
            bouton_replanifier.setVisible(False)
            note_replanification.setVisible(False)

        note_finale = QLabel(
            "Les séances générées apparaissent ensuite dans l'écran « Séances structurées », "
            "où tu peux les lier à une activité réalisée pour obtenir un score de conformité."
        )
        note_finale.setObjectName("texteSecondaire")
        note_finale.setWordWrap(True)
        principal.addWidget(note_finale)

        self.setStyleSheet(obtenir_style_ecran())

        if athlete_id_initial is not None:
            for i in range(self.combo_athlete.count()):
                if self.combo_athlete.itemData(i) == athlete_id_initial:
                    self.combo_athlete.setCurrentIndex(i)
                    break

        self.combo_athlete.currentIndexChanged.connect(self.charger_plans)
        self.charger_plans()

    def ouvrir_programme_ultra(self):
        athlete_id = self.combo_athlete.currentData()
        if athlete_id is None:
            QMessageBox.information(
                self, "Athlète requis",
                "Sélectionne d'abord un athlète précis (pas « Tous »)."
            )
            return

        dialogue = DialogueProgrammeUltra(athlete_id, parent=self)
        if dialogue.exec():
            self.charger_plans()

    def ouvrir_replanification(self):
        ligne = self.table_plans.currentRow()
        if ligne < 0:
            QMessageBox.information(
                self, "Sélection requise",
                "Sélectionne d'abord un plan dans la liste ci-dessous."
            )
            return

        plan_id = self.plans_ids[ligne]
        athlete_id = self.combo_athlete.currentData()
        if athlete_id is None:
            QMessageBox.information(
                self, "Athlète requis",
                "Sélectionne un athlète précis (pas « Tous ») pour replanifier."
            )
            return

        nom_plan = self.table_plans.item(ligne, 0).text()
        dialogue = DialogueReplanification(plan_id, athlete_id, nom_plan, parent=self)
        if dialogue.exec():
            self.charger_plans()

    def exporter_calendrier(self):
        athlete_id = self.combo_athlete.currentData()
        if athlete_id is None:
            QMessageBox.information(
                self, "Athlète requis",
                "Sélectionne un athlète précis (pas « Tous ») pour exporter son calendrier."
            )
            return

        ligne = self.table_plans.currentRow()
        plan_id = self.plans_ids[ligne] if ligne >= 0 else None

        contenu = generer_ics(athlete_id, plan_id=plan_id)
        if "BEGIN:VEVENT" not in contenu:
            QMessageBox.information(
                self, "Rien à exporter",
                "Aucune séance à venir trouvée pour cet export."
            )
            return

        chemin, _ = QFileDialog.getSaveFileName(
            self, "Enregistrer le calendrier", "trailmaster_seances.ics", "Calendrier (*.ics)"
        )
        if not chemin:
            return

        with open(chemin, "w", encoding="utf-8") as f:
            f.write(contenu)

        QMessageBox.information(
            self, "Export terminé",
            f"Calendrier enregistré : {chemin}\n\nImporte ce fichier dans ton application "
            "de calendrier habituelle (Google Calendar, Apple Calendar...)."
        )

    def generer_rapport_bloc_selectionne(self):
        athlete_id = self.combo_athlete.currentData()
        ligne = self.table_plans.currentRow()
        if athlete_id is None or ligne < 0:
            QMessageBox.information(
                self, "Sélection requise",
                "Sélectionne un athlète précis et un plan dans la liste."
            )
            return

        plan_id = self.plans_ids[ligne]
        blocs = obtenir_blocs_plan(plan_id)
        if not blocs:
            QMessageBox.information(
                self, "Pas de bloc détecté",
                "Ce plan n'est pas structuré par blocs (fonctionnalité réservée au "
                "Programme Ultra long terme)."
            )
            return

        nom_bloc, ok = QInputDialog.getItem(
            self, "Choisir un bloc", "Bloc :", blocs, 0, False
        )
        if not ok:
            return

        rapport = generer_rapport_bloc(plan_id, athlete_id, nom_bloc)

        conn = connexion()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO rapports_bloc (plan_id, athlete_id, nom_bloc, contenu) VALUES (?, ?, ?, ?)",
            (plan_id, athlete_id, nom_bloc, rapport),
        )
        conn.commit()
        conn.close()

        QMessageBox.information(self, f"Rapport — {nom_bloc}", rapport)

    # ------------------------------------------------------------
    def suggerer_allure(self):
        athlete_id = self.combo_athlete.currentData()
        if athlete_id is None:
            QMessageBox.information(self, "Athlète requis", "Sélectionne d'abord un athlète.")
            return

        label_record = CORRESPONDANCE_RECORDS.get(self.combo_distance.currentText())
        if not label_record:
            QMessageBox.information(
                self, "Pas de suggestion disponible",
                "Aucune prédiction n'est calculée pour les distances de trail — "
                "saisis directement ton allure visée."
            )
            return

        records = calculer_records(athlete_id)
        record = records.get(label_record)
        if record:
            minutes = int(record["allure_min_km"])
            secondes = round((record["allure_min_km"] - minutes) * 60)
            self.champ_allure.setText(f"{minutes}:{secondes:02d}")
            return

        predictions = calculer_predictions(records)
        prediction = predictions.get(label_record)
        if prediction:
            allure = (prediction["duree_s"] / 60) / dict(DISTANCES_REFERENCE)[label_record]
            minutes = int(allure)
            secondes = round((allure - minutes) * 60)
            self.champ_allure.setText(f"{minutes}:{secondes:02d}")
        else:
            QMessageBox.information(
                self, "Pas assez de données",
                "Pas encore de record ni de prédiction pour cette distance — "
                "saisis directement ton allure visée."
            )

    def generer_apercu(self):
        if not self.champ_allure.text().strip():
            reponse = QMessageBox.question(
                self, "Allure non renseignée",
                "Aucune allure objectif n'est saisie : les séances n'auront pas d'allure "
                "cible (seulement des distances). Continuer quand même ?"
            )
            if reponse != QMessageBox.StandardButton.Yes:
                return

        self.plan_apercu = generer_plan(
            distance_cible=self.combo_distance.currentText(),
            nb_semaines=self.spin_semaines.value(),
            niveau=self.combo_niveau.currentText(),
            jours_par_semaine=self.spin_jours.value(),
            allure_objectif_texte=self.champ_allure.text().strip(),
        )

        self.table_apercu.setRowCount(len(self.plan_apercu))
        for i, semaine in enumerate(self.plan_apercu):
            phase_texte = semaine["phase"].capitalize()
            if semaine["recuperation"]:
                phase_texte += " (récup.)"
            noms_seances = ", ".join(s["nom"] for s in semaine["seances"])
            longue = next(
                (s["etapes"][0]["valeur"] for s in semaine["seances"] if s["nom"] == "Sortie longue"),
                None,
            )

            self.table_apercu.setItem(i, 0, QTableWidgetItem(f"Semaine {semaine['indice']}"))
            self.table_apercu.setItem(i, 1, QTableWidgetItem(phase_texte))
            self.table_apercu.setItem(i, 2, QTableWidgetItem(f"{semaine['volume_km']} km"))
            self.table_apercu.setItem(i, 3, QTableWidgetItem(f"{longue} km" if longue else "—"))
            self.table_apercu.setItem(i, 4, QTableWidgetItem(noms_seances))

        self.table_apercu.resizeColumnsToContents()
        self.bouton_enregistrer_plan.setEnabled(True)

    def enregistrer_plan(self):
        athlete_id = self.combo_athlete.currentData()
        if athlete_id is None:
            QMessageBox.warning(self, "Athlète requis", "Sélectionne un athlète.")
            return
        if not self.champ_nom.text().strip():
            QMessageBox.warning(self, "Nom requis", "Donne un nom à ce plan.")
            return
        if not self.plan_apercu:
            QMessageBox.information(self, "Aperçu requis", "Génère d'abord l'aperçu du plan.")
            return

        date_debut = self.champ_date_debut.date().toPython()

        conn = connexion()
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO plans_entrainement (
                athlete_id, nom, distance_cible, niveau, nb_semaines,
                jours_par_semaine, allure_objectif, date_debut
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                athlete_id,
                self.champ_nom.text().strip(),
                self.combo_distance.currentText(),
                self.combo_niveau.currentText(),
                self.spin_semaines.value(),
                self.spin_jours.value(),
                self.champ_allure.text().strip() or None,
                date_debut.strftime("%Y-%m-%d"),
            ),
        )
        plan_id = cur.lastrowid

        for semaine in self.plan_apercu:
            for seance in semaine["seances"]:
                date_prevue = date_seance(date_debut, semaine["indice"], seance["jour_offset"])
                cur.execute(
                    """
                    INSERT INTO seances_structurees (
                        athlete_id, nom, type_seance, date_prevue, statut, etapes_json, plan_id
                    ) VALUES (?, ?, ?, ?, 'Prévue', ?, ?)
                    """,
                    (
                        athlete_id,
                        f"S{semaine['indice']} — {seance['nom']}",
                        seance["type_seance"],
                        date_prevue.strftime("%Y-%m-%d"),
                        json.dumps(seance["etapes"]),
                        plan_id,
                    ),
                )

        conn.commit()
        conn.close()

        nb_seances = sum(len(s["seances"]) for s in self.plan_apercu)
        QMessageBox.information(
            self, "Plan enregistré",
            f"Le plan « {self.champ_nom.text().strip()} » a été enregistré avec {nb_seances} séances, "
            f"du {date_debut.strftime('%d/%m/%Y')} à la semaine {self.spin_semaines.value()}.\n\n"
            "Retrouve-les dans l'écran « Séances structurées »."
        )

        self.plan_apercu = None
        self.bouton_enregistrer_plan.setEnabled(False)
        self.table_apercu.setRowCount(0)
        self.champ_nom.clear()
        self.charger_plans()

    # ------------------------------------------------------------
    def charger_plans(self):
        athlete_id = self.combo_athlete.currentData()

        conn = connexion()
        cur = conn.cursor()
        if athlete_id is None:
            cur.execute(
                "SELECT id, nom, distance_cible, niveau, nb_semaines, date_debut "
                "FROM plans_entrainement ORDER BY date_creation DESC"
            )
        else:
            cur.execute(
                "SELECT id, nom, distance_cible, niveau, nb_semaines, date_debut "
                "FROM plans_entrainement WHERE athlete_id=? ORDER BY date_creation DESC",
                (athlete_id,),
            )
        plans = cur.fetchall()

        self.plans_ids = [p[0] for p in plans]
        self.table_plans.setRowCount(len(plans))
        for i, (id_, nom, distance_cible, niveau, nb_semaines, date_debut) in enumerate(plans):
            cur.execute(
                "SELECT COUNT(*), SUM(CASE WHEN statut='Réalisée' THEN 1 ELSE 0 END) "
                "FROM seances_structurees WHERE plan_id=?",
                (id_,),
            )
            total, realisees = cur.fetchone()
            realisees = realisees or 0

            self.table_plans.setItem(i, 0, QTableWidgetItem(nom))
            self.table_plans.setItem(i, 1, QTableWidgetItem(distance_cible or ""))
            self.table_plans.setItem(i, 2, QTableWidgetItem(niveau or ""))
            self.table_plans.setItem(i, 3, QTableWidgetItem(str(nb_semaines)))
            self.table_plans.setItem(i, 4, QTableWidgetItem(date_debut or ""))
            self.table_plans.setItem(i, 5, QTableWidgetItem(f"{realisees} / {total}"))

        self.table_plans.resizeColumnsToContents()
        conn.close()

    def supprimer_plan(self):
        ligne = self.table_plans.currentRow()
        if ligne < 0:
            QMessageBox.information(self, "Sélection requise", "Sélectionne d'abord un plan.")
            return

        confirmation = QMessageBox.question(
            self, "Confirmer la suppression",
            "Supprimer ce plan et TOUTES ses séances (y compris déjà réalisées) ?"
        )
        if confirmation != QMessageBox.StandardButton.Yes:
            return

        plan_id = self.plans_ids[ligne]
        conn = connexion()
        cur = conn.cursor()
        cur.execute("DELETE FROM seances_structurees WHERE plan_id=?", (plan_id,))
        cur.execute("DELETE FROM plans_entrainement WHERE id=?", (plan_id,))
        conn.commit()
        conn.close()

        self.charger_plans()
