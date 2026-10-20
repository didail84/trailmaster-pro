import json

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
    QDoubleSpinBox,
    QDateEdit,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QFrame,
    QMessageBox,
    QScrollArea,
    QDialog,
    QDialogButtonBox,
)

from data.database import connexion, creer_base_de_donnees, obtenir_athletes
from interface.ecran_liste import obtenir_style_ecran, configurer_table_redimensionnable
from interface.conformite import (
    calculer_score_conformite,
    distance_totale_prevue_km,
    duree_totale_prevue_min,
)
from interface.carte_reelle import CarteReelle
from interface.comparaison_courses import (
    comparer_seance_realisee, enregistrer_comparaison, tendance_ecart_allure,
)


TYPES_SEANCE = [
    "Endurance fondamentale", "Fractionné", "Côtes", "Sortie longue", "Récupération",
    "Musculation", "Course de préparation", "Vélo", "Tapis incliné", "Randonnée", "Autre",
]
TYPES_ETAPE = ["Échauffement", "Effort", "Récupération", "Retour au calme"]


class Seances(QMainWindow):

    def __init__(self, athlete_id_initial=None):
        super().__init__()

        creer_base_de_donnees()

        self.setWindowTitle("TrailMaster Pro – Séances structurées")
        self.resize(1300, 880)
        self.setMinimumSize(1050, 700)

        self.etapes_en_cours = []
        self.seances_ids = []

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

        titre = QLabel("🏋️  Séances structurées")
        titre.setObjectName("titrePage")
        sous_titre = QLabel(
            "Prépare une séance à l'avance (échauffement, effort, récupération...) "
            "et compare-la à ce que tu as réellement fait"
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
        self.combo_athlete.addItem("Tous les athlètes", None)
        for a in self.athletes:
            self.combo_athlete.addItem(f"{a[2]} {a[1]}", a[0])
        barre.addWidget(label_athlete)
        barre.addWidget(self.combo_athlete)
        barre.addStretch()
        principal.addLayout(barre)

        # ------------------------------------------------------------
        # FORMULAIRE DE CRÉATION
        # ------------------------------------------------------------

        cadre_form = QFrame()
        cadre_form.setObjectName("carteForm")
        form_layout = QVBoxLayout(cadre_form)

        titre_form = QLabel("Nouvelle séance")
        titre_form.setObjectName("titreCarte")
        form_layout.addWidget(titre_form)

        entete_form = QFormLayout()
        self.champ_nom = QLineEdit()
        self.champ_nom.setPlaceholderText("Ex. 6x800m au seuil")
        self.combo_type_seance = QComboBox()
        self.combo_type_seance.addItems(TYPES_SEANCE)
        self.champ_date_prevue = QDateEdit()
        self.champ_date_prevue.setCalendarPopup(True)
        self.champ_date_prevue.setDate(QDate.currentDate())

        self.combo_parcours = QComboBox()
        self.combo_parcours.addItem("Aucun", None)

        entete_form.addRow("Nom :", self.champ_nom)
        entete_form.addRow("Type :", self.combo_type_seance)
        entete_form.addRow("Date prévue :", self.champ_date_prevue)
        entete_form.addRow("Parcours prévu (optionnel) :", self.combo_parcours)
        form_layout.addLayout(entete_form)

        # --- Constructeur d'étapes ---
        titre_etapes = QLabel("Étapes de la séance")
        titre_etapes.setObjectName("titreCarte")
        form_layout.addWidget(titre_etapes)

        barre_etape = QHBoxLayout()
        self.combo_type_etape = QComboBox()
        self.combo_type_etape.addItems(TYPES_ETAPE)
        self.combo_mode_etape = QComboBox()
        self.combo_mode_etape.addItems(["Durée (min)", "Distance (km)"])
        self.champ_valeur_etape = QDoubleSpinBox()
        self.champ_valeur_etape.setRange(0.1, 500)
        self.champ_valeur_etape.setValue(10)
        self.champ_allure_cible = QLineEdit()
        self.champ_allure_cible.setPlaceholderText("Allure cible mm:ss (optionnel)")
        self.champ_allure_cible.setMaximumWidth(160)
        self.champ_fc_cible = QSpinBox()
        self.champ_fc_cible.setRange(0, 220)
        self.champ_fc_cible.setSpecialValueText("FC cible ?")
        self.champ_fc_cible.setMaximumWidth(100)

        bouton_ajouter_etape = QPushButton("+ Ajouter l'étape")
        bouton_ajouter_etape.setObjectName("boutonSecondaire")
        bouton_ajouter_etape.setCursor(Qt.CursorShape.PointingHandCursor)
        bouton_ajouter_etape.clicked.connect(self.ajouter_etape)

        barre_etape.addWidget(self.combo_type_etape)
        barre_etape.addWidget(self.combo_mode_etape)
        barre_etape.addWidget(self.champ_valeur_etape)
        barre_etape.addWidget(self.champ_allure_cible)
        barre_etape.addWidget(self.champ_fc_cible)
        barre_etape.addWidget(bouton_ajouter_etape)
        form_layout.addLayout(barre_etape)

        self.table_etapes = QTableWidget()
        self.table_etapes.setColumnCount(5)
        self.table_etapes.setHorizontalHeaderLabels(
            ["Type", "Mode", "Valeur", "Allure cible", "FC cible"]
        )
        configurer_table_redimensionnable(self.table_etapes)
        self.table_etapes.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table_etapes.setMaximumHeight(180)
        form_layout.addWidget(self.table_etapes)

        barre_actions_etapes = QHBoxLayout()
        bouton_dupliquer = QPushButton("Dupliquer l'étape sélectionnée")
        bouton_dupliquer.setObjectName("boutonSecondaire")
        bouton_dupliquer.clicked.connect(self.dupliquer_etape)
        bouton_retirer = QPushButton("Retirer l'étape sélectionnée")
        bouton_retirer.setObjectName("boutonSecondaire")
        bouton_retirer.clicked.connect(self.retirer_etape)
        barre_actions_etapes.addWidget(bouton_dupliquer)
        barre_actions_etapes.addWidget(bouton_retirer)
        barre_actions_etapes.addStretch()
        form_layout.addLayout(barre_actions_etapes)

        self.label_totaux = QLabel("Total prévu : —")
        self.label_totaux.setObjectName("texteSecondaire")
        form_layout.addWidget(self.label_totaux)

        bouton_enregistrer = QPushButton("💾 Enregistrer la séance")
        bouton_enregistrer.setObjectName("boutonPrincipal")
        bouton_enregistrer.setCursor(Qt.CursorShape.PointingHandCursor)
        bouton_enregistrer.clicked.connect(self.enregistrer_seance)
        form_layout.addWidget(bouton_enregistrer)

        principal.addWidget(cadre_form)

        # ------------------------------------------------------------
        # LISTE DES SÉANCES
        # ------------------------------------------------------------

        titre_liste = QLabel("Séances")
        titre_liste.setObjectName("titreCarte")
        principal.addWidget(titre_liste)

        self.table_seances = QTableWidget()
        self.table_seances.setColumnCount(7)
        self.table_seances.setHorizontalHeaderLabels(
            ["Nom", "Type", "Date prévue", "Statut", "Score", "Détail prévu", "Parcours prévu"]
        )
        configurer_table_redimensionnable(self.table_seances)
        self.table_seances.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table_seances.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        principal.addWidget(self.table_seances)

        barre_actions_seances = QHBoxLayout()
        bouton_lier = QPushButton("🔗 Lier une activité réalisée")
        bouton_lier.setObjectName("boutonPrincipal")
        bouton_lier.clicked.connect(self.lier_activite)
        bouton_voir_parcours = QPushButton("🗺️ Voir le parcours prévu")
        bouton_voir_parcours.setObjectName("boutonSecondaire")
        bouton_voir_parcours.clicked.connect(self.voir_parcours)
        bouton_supprimer_seance = QPushButton("Supprimer la séance sélectionnée")
        bouton_supprimer_seance.setObjectName("boutonSecondaire")
        bouton_supprimer_seance.clicked.connect(self.supprimer_seance)
        bouton_comparer_cibles = QPushButton("📊 Comparer aux cibles (allure/FC)")
        bouton_comparer_cibles.setObjectName("boutonSecondaire")
        bouton_comparer_cibles.clicked.connect(self.comparer_aux_cibles)
        barre_actions_seances.addWidget(bouton_lier)
        barre_actions_seances.addWidget(bouton_voir_parcours)
        barre_actions_seances.addWidget(bouton_comparer_cibles)
        bouton_fenix = QPushButton("⌚ Envoyer à la montre (fichier FIT)")
        bouton_fenix.setObjectName("boutonSecondaire")
        bouton_fenix.setToolTip("Crée la séance sélectionnée au format Garmin : copie-la dans GARMIN/NewFiles de la montre branchée en USB.")
        bouton_fenix.clicked.connect(self.exporter_vers_montre)
        barre_actions_seances.addWidget(bouton_fenix)
        barre_actions_seances.addWidget(bouton_supprimer_seance)
        barre_actions_seances.addStretch()
        principal.addLayout(barre_actions_seances)

        self.setStyleSheet(obtenir_style_ecran())

        if athlete_id_initial is not None:
            for i in range(self.combo_athlete.count()):
                if self.combo_athlete.itemData(i) == athlete_id_initial:
                    self.combo_athlete.setCurrentIndex(i)
                    break

        self.combo_athlete.currentIndexChanged.connect(self.charger_seances)
        self.combo_athlete.currentIndexChanged.connect(self.charger_parcours_disponibles)
        self.charger_parcours_disponibles()
        self.charger_seances()

    def charger_parcours_disponibles(self):
        athlete_id = self.combo_athlete.currentData()
        self.combo_parcours.clear()
        self.combo_parcours.addItem("Aucun", None)

        if athlete_id is None:
            return

        conn = connexion()
        cur = conn.cursor()
        cur.execute(
            "SELECT id, nom, distance_km FROM parcours_gpx WHERE athlete_id=? "
            "ORDER BY date_ajout DESC LIMIT 300",
            (athlete_id,),
        )
        for id_, nom, distance in cur.fetchall():
            self.combo_parcours.addItem(f"{nom} ({distance} km)", id_)
        conn.close()

    # ------------------------------------------------------------
    # CONSTRUCTION DES ÉTAPES
    # ------------------------------------------------------------

    def ajouter_etape(self):
        mode = "duree" if self.combo_mode_etape.currentIndex() == 0 else "distance"
        etape = {
            "type": self.combo_type_etape.currentText(),
            "mode": mode,
            "valeur": self.champ_valeur_etape.value(),
            "allure_cible": self.champ_allure_cible.text().strip() or None,
            "fc_cible": self.champ_fc_cible.value() or None,
        }
        self.etapes_en_cours.append(etape)
        self._rafraichir_table_etapes()

    def dupliquer_etape(self):
        ligne = self.table_etapes.currentRow()
        if ligne < 0:
            return
        self.etapes_en_cours.append(dict(self.etapes_en_cours[ligne]))
        self._rafraichir_table_etapes()

    def retirer_etape(self):
        ligne = self.table_etapes.currentRow()
        if ligne < 0:
            return
        del self.etapes_en_cours[ligne]
        self._rafraichir_table_etapes()

    def _rafraichir_table_etapes(self):
        self.table_etapes.setRowCount(len(self.etapes_en_cours))
        for i, e in enumerate(self.etapes_en_cours):
            mode_texte = "Durée (min)" if e["mode"] == "duree" else "Distance (km)"
            self.table_etapes.setItem(i, 0, QTableWidgetItem(e["type"]))
            self.table_etapes.setItem(i, 1, QTableWidgetItem(mode_texte))
            self.table_etapes.setItem(i, 2, QTableWidgetItem(str(e["valeur"])))
            self.table_etapes.setItem(i, 3, QTableWidgetItem(e["allure_cible"] or "—"))
            self.table_etapes.setItem(i, 4, QTableWidgetItem(str(e["fc_cible"]) if e["fc_cible"] else "—"))
        self.table_etapes.resizeColumnsToContents()

        distance = distance_totale_prevue_km(self.etapes_en_cours)
        duree = duree_totale_prevue_min(self.etapes_en_cours)
        morceaux = []
        if distance:
            morceaux.append(f"{distance} km")
        if duree:
            morceaux.append(f"{duree} min")
        self.label_totaux.setText("Total prévu : " + (" / ".join(morceaux) if morceaux else "—"))

    # ------------------------------------------------------------
    # ENREGISTREMENT / LISTE
    # ------------------------------------------------------------

    def enregistrer_seance(self):
        athlete_id = self.combo_athlete.currentData()
        if athlete_id is None:
            QMessageBox.warning(
                self, "Athlète requis",
                "Sélectionnez un athlète précis (pas « Tous ») avant d'enregistrer."
            )
            return
        if not self.champ_nom.text().strip():
            QMessageBox.warning(self, "Nom requis", "Donne un nom à cette séance.")
            return
        if not self.etapes_en_cours:
            QMessageBox.warning(self, "Étapes requises", "Ajoute au moins une étape à la séance.")
            return

        conn = connexion()
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO seances_structurees (
                athlete_id, nom, type_seance, date_prevue, statut, etapes_json, parcours_id
            ) VALUES (?, ?, ?, ?, 'Prévue', ?, ?)
            """,
            (
                athlete_id,
                self.champ_nom.text().strip(),
                self.combo_type_seance.currentText(),
                self.champ_date_prevue.date().toString("yyyy-MM-dd"),
                json.dumps(self.etapes_en_cours),
                self.combo_parcours.currentData(),
            ),
        )
        conn.commit()
        conn.close()

        self.champ_nom.clear()
        self.etapes_en_cours = []
        self.combo_parcours.setCurrentIndex(0)
        self._rafraichir_table_etapes()

        QMessageBox.information(self, "Enregistrée", "La séance a été enregistrée.")
        self.charger_seances()

    def charger_seances(self):
        athlete_id = self.combo_athlete.currentData()

        conn = connexion()
        cur = conn.cursor()
        colonnes_sql = (
            "s.id, s.nom, s.type_seance, s.date_prevue, s.statut, s.score_conformite, "
            "s.etapes_json, s.parcours_id, p.nom, p.distance_km, s.commentaire_replanification"
        )
        if athlete_id is None:
            cur.execute(
                f"SELECT {colonnes_sql} FROM seances_structurees s "
                "LEFT JOIN parcours_gpx p ON s.parcours_id = p.id "
                "ORDER BY s.date_prevue DESC"
            )
        else:
            cur.execute(
                f"SELECT {colonnes_sql} FROM seances_structurees s "
                "LEFT JOIN parcours_gpx p ON s.parcours_id = p.id "
                "WHERE s.athlete_id=? ORDER BY s.date_prevue DESC",
                (athlete_id,),
            )
        lignes = cur.fetchall()
        conn.close()

        self.seances_ids = [l[0] for l in lignes]
        self.parcours_ids = [l[7] for l in lignes]
        self.table_seances.setRowCount(len(lignes))
        for i, (id_, nom, type_seance, date_prevue, statut, score, etapes_json,
                parcours_id, parcours_nom, parcours_distance,
                commentaire_replanification) in enumerate(lignes):
            etapes = json.loads(etapes_json) if etapes_json else []
            distance = distance_totale_prevue_km(etapes)
            duree = duree_totale_prevue_min(etapes)
            morceaux = []
            if distance:
                morceaux.append(f"{distance} km")
            if duree:
                morceaux.append(f"{duree} min")
            detail = " / ".join(morceaux) if morceaux else "—"

            parcours_texte = f"{parcours_nom} ({parcours_distance} km)" if parcours_id else "—"

            nom_affiche = ("🔄 " + nom) if commentaire_replanification else nom
            item_nom = QTableWidgetItem(nom_affiche)
            if commentaire_replanification:
                item_nom.setToolTip(
                    "Ajustée par la replanification automatique :\n" + commentaire_replanification
                )
            self.table_seances.setItem(i, 0, item_nom)
            self.table_seances.setItem(i, 1, QTableWidgetItem(type_seance or ""))
            self.table_seances.setItem(i, 2, QTableWidgetItem(date_prevue or ""))
            self.table_seances.setItem(i, 3, QTableWidgetItem(statut or ""))
            self.table_seances.setItem(i, 4, QTableWidgetItem(str(score) if score is not None else "—"))
            self.table_seances.setItem(i, 5, QTableWidgetItem(detail))
            self.table_seances.setItem(i, 6, QTableWidgetItem(parcours_texte))
        self.table_seances.resizeColumnsToContents()

    def exporter_vers_montre(self):
        """E2 — écrit la séance sélectionnée en .fit (dossier NewFiles de la
        montre si on la trouve, sinon dossier choisi)."""
        from pathlib import Path
        from PySide6.QtWidgets import QFileDialog
        from data.export_fit_seance import encoder_seance, nom_fichier
        from interface.outils_ui import notifier
        ligne = self.table_seances.currentRow()
        if ligne < 0:
            QMessageBox.information(self, "Sélection requise", "Sélectionne d'abord une séance.")
            return
        conn = connexion()
        cur = conn.cursor()
        cur.execute("SELECT nom, etapes_json FROM seances_structurees WHERE id=?", (self.seances_ids[ligne],))
        r = cur.fetchone()
        conn.close()
        etapes = json.loads(r[1]) if r and r[1] else []
        if not etapes:
            QMessageBox.information(self, "Séance vide", "Cette séance n'a pas d'étapes à envoyer.")
            return
        cible = None
        for racine in (list(Path("/Volumes").glob("*")) + list(Path("/media").glob("*/*")) + [Path(f"{l}:/") for l in "DEFGHIJ"]):
            try:
                if (racine / "GARMIN").is_dir():
                    cible = racine / "GARMIN" / "NewFiles"
                    break
            except OSError:
                continue
        if cible is None:
            dossier = QFileDialog.getExistingDirectory(
                self, "Montre non détectée — choisis le dossier GARMIN/NewFiles (ou un dossier de ton choix)")
            if not dossier:
                return
            cible = Path(dossier)
        try:
            cible.mkdir(parents=True, exist_ok=True)
            chemin = cible / nom_fichier(r[0])
            chemin.write_bytes(encoder_seance(r[0], etapes))
        except (OSError, ValueError) as e:
            QMessageBox.warning(self, "Envoi impossible", str(e))
            return
        notifier("Séance écrite pour la montre", parent=self)
        QMessageBox.information(
            self, "Séance prête",
            f"Fichier créé : {chemin}\n\nDébranche la montre : la séance apparaît dans Entraînement > Séances "
            "(sur la Fenix : Entraînement → Séances).")

    def supprimer_seance(self):
        ligne = self.table_seances.currentRow()
        if ligne < 0:
            QMessageBox.information(self, "Sélection requise", "Sélectionne d'abord une séance.")
            return

        confirmation = QMessageBox.question(
            self, "Confirmer la suppression", "Supprimer définitivement cette séance ?"
        )
        if confirmation != QMessageBox.StandardButton.Yes:
            return

        id_seance = self.seances_ids[ligne]
        conn = connexion()
        cur = conn.cursor()
        cur.execute("DELETE FROM seances_structurees WHERE id=?", (id_seance,))
        conn.commit()
        conn.close()

        self.charger_seances()

    # ------------------------------------------------------------
    # PARCOURS PRÉVU
    # ------------------------------------------------------------

    def voir_parcours(self):
        ligne = self.table_seances.currentRow()
        if ligne < 0:
            QMessageBox.information(self, "Sélection requise", "Sélectionne d'abord une séance.")
            return

        parcours_id = self.parcours_ids[ligne]
        if parcours_id is None:
            QMessageBox.information(
                self, "Aucun parcours",
                "Cette séance n'a pas de parcours prévu attaché — "
                "choisis-en un dans le formulaire lors de la création d'une séance."
            )
            return

        athlete_id = self.combo_athlete.currentData()
        if athlete_id is None:
            id_seance = self.seances_ids[ligne]
            conn = connexion()
            cur = conn.cursor()
            cur.execute("SELECT athlete_id FROM seances_structurees WHERE id=?", (id_seance,))
            ligne_athlete = cur.fetchone()
            conn.close()
            athlete_id = ligne_athlete[0] if ligne_athlete else None

        self.fenetre_carte_parcours = CarteReelle(
            athlete_id_initial=athlete_id, parcours_id_initial=parcours_id
        )
        self.fenetre_carte_parcours.show()

    # ------------------------------------------------------------
    # LIAISON À UNE ACTIVITÉ RÉALISÉE
    # ------------------------------------------------------------

    def lier_activite(self):
        ligne = self.table_seances.currentRow()
        if ligne < 0:
            QMessageBox.information(self, "Sélection requise", "Sélectionne d'abord une séance.")
            return

        id_seance = self.seances_ids[ligne]

        conn = connexion()
        cur = conn.cursor()
        cur.execute("SELECT athlete_id, etapes_json FROM seances_structurees WHERE id=?", (id_seance,))
        athlete_id, etapes_json = cur.fetchone()
        etapes = json.loads(etapes_json) if etapes_json else []

        cur.execute(
            "SELECT id, date, type, distance, duree FROM activites "
            "WHERE athlete_id=? ORDER BY date DESC LIMIT 30",
            (athlete_id,),
        )
        activites_recentes = cur.fetchall()
        conn.close()

        if not activites_recentes:
            QMessageBox.information(
                self, "Aucune activité",
                "Aucune activité récente trouvée pour cet athlète."
            )
            return

        dialogue = DialogueChoixActivite(activites_recentes, self)
        if dialogue.exec() != QDialog.DialogCode.Accepted or dialogue.activite_choisie is None:
            return

        activite_id, date_, type_, distance, duree = dialogue.activite_choisie
        duree_min = (duree or 0) / 60

        resultat = calculer_score_conformite(etapes, distance, duree_min)

        conn = connexion()
        cur = conn.cursor()
        cur.execute(
            "UPDATE seances_structurees SET statut=?, activite_id=?, score_conformite=? WHERE id=?",
            (
                "Réalisée",
                activite_id,
                resultat["score"] if resultat else None,
                id_seance,
            ),
        )
        conn.commit()
        conn.close()

        if resultat:
            QMessageBox.information(
                self, "Score calculé",
                f"{resultat['interpretation']} — score {resultat['score']}/100\n\n"
                f"Prévu : {resultat['distance_prevue'] or '—'} km / {resultat['duree_prevue'] or '—'} min\n"
                f"Réalisé : {distance} km / {round(duree_min)} min"
            )
        else:
            QMessageBox.information(
                self, "Activité liée",
                "Activité liée, mais le score n'a pas pu être calculé "
                "(aucune étape ne permettait de déduire une distance ou une durée cible)."
            )

        self.charger_seances()

    # ------------------------------------------------------------
    # COMPARAISON CIBLE / RÉALISÉ (recalibrage des prédictions Riegel)
    # ------------------------------------------------------------

    def comparer_aux_cibles(self):
        ligne = self.table_seances.currentRow()
        if ligne < 0:
            QMessageBox.information(self, "Sélection requise", "Sélectionne d'abord une séance.")
            return

        id_seance = self.seances_ids[ligne]
        comparaison = comparer_seance_realisee(id_seance)
        if comparaison is None:
            QMessageBox.information(
                self, "Comparaison impossible",
                "Cette séance n'a pas de cible d'allure/FC exploitable, ou aucune activité "
                "n'y est liée — lie d'abord une activité réalisée."
            )
            return

        enregistrer_comparaison(comparaison)
        tendance = tendance_ecart_allure(comparaison["athlete_id"])

        message = comparaison["texte"]
        if tendance is not None:
            sens = "plus lentement" if tendance > 0 else "plus vite"
            message += (
                f"\n\nTendance sur les dernières comparaisons enregistrées : en moyenne "
                f"{abs(tendance)}% {sens} que les cibles calculées — un signal utile pour "
                "juger si les allures proposées par le logiciel sont réalistes pour toi."
            )

        QMessageBox.information(self, "Comparaison cible / réalisé", message)


class DialogueChoixActivite(QDialog):
    """Petite fenêtre de sélection d'une activité récente parmi une liste."""

    def __init__(self, activites, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Choisir l'activité réalisée")
        self.resize(500, 400)
        self.activite_choisie = None

        layout = QVBoxLayout(self)

        self.liste = QTableWidget()
        self.liste.setColumnCount(4)
        self.liste.setHorizontalHeaderLabels(["Date", "Type", "Distance (km)", "Durée"])
        configurer_table_redimensionnable(self.liste)
        self.liste.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.liste.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.liste.setRowCount(len(activites))

        self.activites = activites
        for i, (id_, date_, type_, distance, duree) in enumerate(activites):
            duree_texte = f"{round((duree or 0) / 60)} min" if duree else "—"
            self.liste.setItem(i, 0, QTableWidgetItem(str(date_)[:16]))
            self.liste.setItem(i, 1, QTableWidgetItem(type_ or ""))
            self.liste.setItem(i, 2, QTableWidgetItem(str(distance or 0)))
            self.liste.setItem(i, 3, QTableWidgetItem(duree_texte))
        self.liste.resizeColumnsToContents()

        layout.addWidget(self.liste)

        boutons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        boutons.accepted.connect(self._valider)
        boutons.rejected.connect(self.reject)
        layout.addWidget(boutons)

    def _valider(self):
        ligne = self.liste.currentRow()
        if ligne < 0:
            QMessageBox.information(self, "Sélection requise", "Sélectionne une activité.")
            return
        self.activite_choisie = self.activites[ligne]
        self.accept()
