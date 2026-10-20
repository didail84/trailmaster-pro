import json
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QComboBox,
    QLineEdit,
    QFileDialog,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QFrame,
    QMessageBox,
    QScrollArea,
    QDialog,
    QDoubleSpinBox,
    QFormLayout,
)

from data.database import connexion, creer_base_de_donnees, obtenir_athletes, affichage_simplifie_actif
from interface.gpx_utils import parser_gpx
from interface.fit_utils import parser_fit
from interface.trace_widget import TraceCanvas
from interface.ecran_liste import obtenir_style_ecran, configurer_table_redimensionnable
from interface.montees import detecter_montees
from interface.puissance import calculer_puissance_estimee
from interface.dynamique_course import calculer_decouplage_cardiaque, calculer_cadence_moyenne
from interface.pacing_segments import decouper_par_segments, calculer_pacing


class ParcoursGPX(QMainWindow):

    def __init__(self, athlete_id_initial=None):
        super().__init__()

        creer_base_de_donnees()

        self.setWindowTitle("TrailMaster Pro – Parcours GPX")
        self.resize(1250, 830)
        self.setMinimumSize(1000, 700)

        self.trace_courante = None
        self.fichier_courant = None
        self.parcours_ids = []
        self.activite_liee_id = None

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

        titre = QLabel("🗺️  Parcours GPX")
        titre.setObjectName("titrePage")
        sous_titre = QLabel(
            "Import et visualisation des traces GPX (Strava, Garmin, montres GPS...)"
        )
        sous_titre.setObjectName("sousTitrePage")
        principal.addWidget(titre)
        principal.addWidget(sous_titre)

        # ------------------------------------------------------------
        # BARRE ATHLÈTE + IMPORT
        # ------------------------------------------------------------

        barre = QHBoxLayout()
        label_athlete = QLabel("Athlète :")
        label_athlete.setObjectName("labelChamp")

        self.combo_athlete = QComboBox()
        self.athletes = obtenir_athletes()
        self.combo_athlete.addItem("Sélectionner...", None)
        for a in self.athletes:
            self.combo_athlete.addItem(f"{a[2]} {a[1]}", a[0])

        if athlete_id_initial is not None:
            for i in range(self.combo_athlete.count()):
                if self.combo_athlete.itemData(i) == athlete_id_initial:
                    self.combo_athlete.setCurrentIndex(i)
                    break

        bouton_importer = QPushButton("📂 Importer un fichier GPX")
        bouton_importer.setObjectName("boutonPrincipal")
        bouton_importer.setCursor(Qt.CursorShape.PointingHandCursor)
        bouton_importer.clicked.connect(self.importer_gpx)

        barre.addWidget(label_athlete)
        barre.addWidget(self.combo_athlete)
        barre.addStretch()
        barre.addWidget(bouton_importer)
        principal.addLayout(barre)

        # ------------------------------------------------------------
        # ZONE CENTRALE : CANVAS + STATISTIQUES
        # ------------------------------------------------------------

        zone = QHBoxLayout()
        zone.setSpacing(15)

        cadre_canvas = QFrame()
        cadre_canvas.setObjectName("carteForm")
        canvas_layout = QVBoxLayout(cadre_canvas)
        self.canvas = TraceCanvas()
        canvas_layout.addWidget(self.canvas)
        zone.addWidget(cadre_canvas, 3)

        cadre_stats = QFrame()
        cadre_stats.setObjectName("carteForm")
        cadre_stats.setFixedWidth(260)
        stats_layout = QVBoxLayout(cadre_stats)

        stats_titre = QLabel("Statistiques")
        stats_titre.setObjectName("titreCarte")
        stats_layout.addWidget(stats_titre)

        label_nom = QLabel("Nom du parcours :")
        label_nom.setObjectName("labelChamp")
        self.champ_nom = QLineEdit()
        self.champ_nom.setPlaceholderText("Nom du parcours")

        self.label_distance = QLabel("Distance : --")
        self.label_dplus = QLabel("D+ : --")
        self.label_dmoins = QLabel("D- : --")
        self.label_alt = QLabel("Altitude : --")
        self.label_puissance = QLabel("Puissance estimée : --")
        self.label_decouplage = QLabel("Découplage cardiaque : --")
        self.label_cadence = QLabel("Cadence moyenne : --")
        for lbl in (self.label_distance, self.label_dplus, self.label_dmoins,
                    self.label_alt, self.label_puissance, self.label_decouplage,
                    self.label_cadence):
            lbl.setObjectName("texteSecondaire")
            lbl.setWordWrap(True)

        stats_layout.addWidget(label_nom)
        stats_layout.addWidget(self.champ_nom)
        stats_layout.addWidget(self.label_distance)
        stats_layout.addWidget(self.label_dplus)
        stats_layout.addWidget(self.label_dmoins)
        stats_layout.addWidget(self.label_alt)
        stats_layout.addWidget(self.label_puissance)
        stats_layout.addWidget(self.label_cadence)
        stats_layout.addWidget(self.label_decouplage)
        stats_layout.addStretch()

        if affichage_simplifie_actif():
            self.label_decouplage.setVisible(False)

        bouton_enregistrer = QPushButton("💾 Enregistrer le parcours")
        bouton_enregistrer.setObjectName("boutonPrincipal")
        bouton_enregistrer.setCursor(Qt.CursorShape.PointingHandCursor)
        bouton_enregistrer.clicked.connect(self.enregistrer_parcours)
        stats_layout.addWidget(bouton_enregistrer)

        bouton_pacing = QPushButton("⏱️ Pacing segmenté")
        bouton_pacing.setObjectName("boutonSecondaire")
        bouton_pacing.setCursor(Qt.CursorShape.PointingHandCursor)
        bouton_pacing.clicked.connect(self.ouvrir_pacing_segmente)
        stats_layout.addWidget(bouton_pacing)

        zone.addWidget(cadre_stats)
        principal.addLayout(zone, 1)

        # ------------------------------------------------------------
        # MONTÉES DÉTECTÉES
        # ------------------------------------------------------------

        cadre_montees = QFrame()
        cadre_montees.setObjectName("carteForm")
        montees_layout = QVBoxLayout(cadre_montees)

        titre_montees = QLabel("⛰️ Montées détectées dans cette trace")
        titre_montees.setObjectName("titreCarte")
        montees_layout.addWidget(titre_montees)

        self.table_montees = QTableWidget()
        self.table_montees.setColumnCount(5)
        self.table_montees.setHorizontalHeaderLabels(
            ["Catégorie", "D+ (m)", "Distance (km)", "Pente moy.", "Altitude"]
        )
        configurer_table_redimensionnable(self.table_montees)
        self.table_montees.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table_montees.setMaximumHeight(180)
        montees_layout.addWidget(self.table_montees)

        principal.addWidget(cadre_montees)

        # ------------------------------------------------------------
        # LISTE DES PARCOURS ENREGISTRÉS
        # ------------------------------------------------------------

        titre_liste = QLabel("Parcours enregistrés (double-clic pour visualiser)")
        titre_liste.setObjectName("titreCarte")
        principal.addWidget(titre_liste)

        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels(
            ["Nom", "Ajouté le", "Distance (km)", "D+ (m)", "D- (m)", "Altitude min/max"]
        )
        configurer_table_redimensionnable(self.table)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.cellDoubleClicked.connect(self.charger_parcours_selectionne)
        principal.addWidget(self.table)

        bouton_supprimer = QPushButton("Supprimer le parcours sélectionné")
        bouton_supprimer.setObjectName("boutonSecondaire")
        bouton_supprimer.setCursor(Qt.CursorShape.PointingHandCursor)
        bouton_supprimer.clicked.connect(self.supprimer_parcours)
        principal.addWidget(bouton_supprimer)

        self.setStyleSheet(obtenir_style_ecran())

        self.charger_liste()

    # ------------------------------------------------------------
    def importer_gpx(self):
        chemin, _ = QFileDialog.getOpenFileName(
            self, "Choisir un fichier de trace", "",
            "Traces GPS (*.gpx *.fit);;Fichiers GPX (*.gpx);;Fichiers FIT (*.fit)"
        )
        if not chemin:
            return

        try:
            if chemin.lower().endswith(".fit"):
                resultat = parser_fit(chemin)
            else:
                resultat = parser_gpx(chemin)
        except Exception as erreur:
            QMessageBox.critical(
                self, "Erreur de lecture",
                f"Impossible de lire ce fichier :\n{erreur}"
            )
            return

        if not resultat["points"]:
            QMessageBox.warning(
                self, "Fichier vide",
                "Aucun point de trace GPS trouvé dans ce fichier "
                "(pour un .fit, il doit s'agir d'un enregistrement d'activité, "
                "pas d'un fichier de suivi quotidien ou de segment)."
            )
            return

        self.trace_courante = resultat
        self.fichier_courant = chemin

        points_2d = [(p[0], p[1]) for p in resultat["points"]]
        altitudes = [p[2] for p in resultat["points"]]
        self.canvas.definir_trace(points_2d, altitudes)

        self.champ_nom.setText(Path(chemin).stem)
        self.label_distance.setText(f"Distance : {resultat['distance_km']} km")
        self.label_dplus.setText(f"D+ : {resultat['denivele_positif']} m")
        self.label_dmoins.setText(f"D- : {resultat['denivele_negatif']} m")
        self.label_alt.setText(
            f"Altitude : {resultat['altitude_min']}–{resultat['altitude_max']} m"
        )

        duree_s = None
        if resultat.get("date_debut") and resultat.get("date_fin"):
            duree_s = (resultat["date_fin"] - resultat["date_debut"]).total_seconds()

        self._analyser_trace(resultat["points"], resultat["distance_km"], duree_s)

    def enregistrer_parcours(self):
        if self.trace_courante is None:
            QMessageBox.information(self, "Aucun tracé", "Importez d'abord un fichier GPX.")
            return

        athlete_id = self.combo_athlete.currentData()
        if athlete_id is None:
            QMessageBox.warning(
                self, "Athlète requis",
                "Sélectionnez un athlète avant d'enregistrer le parcours."
            )
            return

        nom = self.champ_nom.text().strip() or "Parcours sans nom"
        trace_json = json.dumps(self.trace_courante["points"])

        conn = connexion()
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO parcours_gpx (
                athlete_id, nom, fichier_source, distance_km,
                denivele_positif, denivele_negatif, altitude_min, altitude_max, trace_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                athlete_id,
                nom,
                self.fichier_courant,
                self.trace_courante["distance_km"],
                self.trace_courante["denivele_positif"],
                self.trace_courante["denivele_negatif"],
                self.trace_courante["altitude_min"],
                self.trace_courante["altitude_max"],
                trace_json,
            ),
        )
        conn.commit()
        conn.close()

        QMessageBox.information(self, "Enregistré", f"Le parcours « {nom} » a été enregistré.")
        self.charger_liste()

    def charger_liste(self):
        conn = connexion()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, nom, date_ajout, distance_km, denivele_positif, denivele_negatif,
                   altitude_min, altitude_max
            FROM parcours_gpx
            ORDER BY date_ajout DESC
            """
        )
        lignes = cur.fetchall()
        conn.close()

        self.parcours_ids = [l[0] for l in lignes]
        self.table.setRowCount(len(lignes))
        for i, (id_, nom, date_ajout, distance, dplus, dmoins, alt_min, alt_max) in enumerate(lignes):
            self.table.setItem(i, 0, QTableWidgetItem(nom or ""))
            self.table.setItem(i, 1, QTableWidgetItem((date_ajout or "")[:16]))
            self.table.setItem(i, 2, QTableWidgetItem(str(distance if distance is not None else 0)))
            self.table.setItem(i, 3, QTableWidgetItem(str(dplus if dplus is not None else 0)))
            self.table.setItem(i, 4, QTableWidgetItem(str(dmoins if dmoins is not None else 0)))
            self.table.setItem(
                i, 5,
                QTableWidgetItem(f"{alt_min if alt_min is not None else 0}–{alt_max if alt_max is not None else 0} m"),
            )
        self.table.resizeColumnsToContents()

    def charger_parcours_selectionne(self, ligne, colonne):
        id_parcours = self.parcours_ids[ligne]

        conn = connexion()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT p.trace_json, p.athlete_id, a.distance, a.duree
            FROM parcours_gpx p
            LEFT JOIN activites a ON p.activite_id = a.id
            WHERE p.id=?
            """,
            (id_parcours,),
        )
        resultat = cur.fetchone()
        conn.close()

        if not resultat or not resultat[0]:
            return

        trace_json, athlete_id, distance_activite, duree_activite = resultat
        points = json.loads(trace_json)
        points_2d = [(p[0], p[1]) for p in points]
        altitudes = [p[2] for p in points]
        self.canvas.definir_trace(points_2d, altitudes)
        self.trace_courante = {"points": points}

        self._analyser_trace(points, distance_activite, duree_activite, athlete_id)

    def supprimer_parcours(self):
        ligne = self.table.currentRow()
        if ligne < 0:
            QMessageBox.information(
                self, "Sélection requise",
                "Sélectionnez d'abord un parcours à supprimer."
            )
            return

        id_parcours = self.parcours_ids[ligne]
        confirmation = QMessageBox.question(
            self, "Confirmer la suppression", "Supprimer définitivement ce parcours ?"
        )
        if confirmation != QMessageBox.StandardButton.Yes:
            return

        conn = connexion()
        cur = conn.cursor()
        cur.execute("DELETE FROM parcours_gpx WHERE id=?", (id_parcours,))
        conn.commit()
        conn.close()

        self.charger_liste()

    # ------------------------------------------------------------
    def _analyser_trace(self, points, distance_km, duree_s, athlete_id=None):
        """Détecte les montées et estime la puissance moyenne pour la
        trace actuellement affichée. distance_km/duree_s viennent de
        préférence de l'activité liée (plus fiable) ; à défaut, de la
        trace elle-même (import pas encore enregistré)."""

        montees = detecter_montees(points)
        self.table_montees.setRowCount(len(montees))
        for i, m in enumerate(montees):
            self.table_montees.setItem(i, 0, QTableWidgetItem(m["categorie"]))
            self.table_montees.setItem(i, 1, QTableWidgetItem(str(m["denivele"])))
            self.table_montees.setItem(i, 2, QTableWidgetItem(str(m["distance_km"])))
            self.table_montees.setItem(i, 3, QTableWidgetItem(f"{m['pente_moyenne']} %"))
            self.table_montees.setItem(
                i, 4, QTableWidgetItem(f"{m['altitude_depart']} → {m['altitude_arrivee']} m")
            )
        self.table_montees.resizeColumnsToContents()

        poids_kg = None
        athlete_cible = athlete_id or self.combo_athlete.currentData()
        if athlete_cible:
            conn = connexion()
            cur = conn.cursor()
            cur.execute("SELECT poids FROM athletes WHERE id=?", (athlete_cible,))
            ligne_poids = cur.fetchone()
            conn.close()
            if ligne_poids and ligne_poids[0]:
                poids_kg = ligne_poids[0]

        puissance = calculer_puissance_estimee(points, distance_km, duree_s, poids_kg)
        if puissance is None:
            self.label_puissance.setText(
                "Puissance estimée : — (durée de la sortie inconnue)"
            )
        elif "puissance_watts" in puissance:
            self.label_puissance.setText(
                f"Puissance estimée : {puissance['puissance_watts']} W "
                f"({puissance['puissance_w_par_kg']} W/kg)"
            )
        else:
            self.label_puissance.setText(
                f"Puissance estimée : {puissance['puissance_w_par_kg']} W/kg "
                "(poids athlète inconnu)"
            )

        cadence = calculer_cadence_moyenne(points)
        if cadence:
            self.label_cadence.setText(f"Cadence moyenne : {cadence['cadence_spm']} pas/min")
        else:
            self.label_cadence.setText("Cadence moyenne : — (non enregistrée par l'appareil)")

        if not affichage_simplifie_actif():
            decouplage = calculer_decouplage_cardiaque(points)
            if decouplage:
                self.label_decouplage.setText(
                    f"Découplage cardiaque : {decouplage['decouplage_pct']} % — "
                    f"{decouplage['interpretation']}\n"
                    f"(FC {decouplage['fc_premiere']}→{decouplage['fc_seconde']} bpm, "
                    f"allure {decouplage['vitesse_premiere_kmh']}→{decouplage['vitesse_seconde_kmh']} km/h)"
                )
            else:
                self.label_decouplage.setText(
                    "Découplage cardiaque : — (FC par point indisponible ou sortie trop courte)"
                )

    # ------------------------------------------------------------
    # PACING SEGMENTÉ ("PacePro maison")
    # ------------------------------------------------------------

    def ouvrir_pacing_segmente(self):
        if not self.trace_courante or not self.trace_courante.get("points"):
            QMessageBox.information(
                self, "Aucun tracé",
                "Importe ou sélectionne d'abord un parcours avec une trace GPS."
            )
            return

        dialogue = DialoguePacingSegmente(self.trace_courante["points"], parent=self)
        dialogue.exec()


class DialoguePacingSegmente(QDialog):
    """Découpe la trace en segments de longueur fixe et propose une
    allure cible par segment selon la pente — voir interface/
    pacing_segments.py pour le détail (et ses limites documentées)."""

    def __init__(self, points, parent=None):
        super().__init__(parent)
        self.points = points
        self.setWindowTitle("Pacing segmenté")
        self.resize(650, 550)

        layout = QVBoxLayout(self)

        note = QLabel(
            "Approximation par segments de longueur fixe (pas une analyse seconde par "
            "seconde) : ajuste ton allure de référence \"plat\" selon la pente moyenne de "
            "chaque segment. Un repère indicatif, pas un chrono à respecter à la seconde près."
        )
        note.setObjectName("texteSecondaire")
        note.setWordWrap(True)
        layout.addWidget(note)

        formulaire = QFormLayout()
        self.champ_allure_plat = QLineEdit()
        self.champ_allure_plat.setPlaceholderText("mm:ss / km, ex. 5:30")
        self.spin_longueur_segment = QDoubleSpinBox()
        self.spin_longueur_segment.setRange(0.2, 10.0)
        self.spin_longueur_segment.setValue(1.0)
        self.spin_longueur_segment.setSuffix(" km")
        formulaire.addRow("Allure de référence (plat) :", self.champ_allure_plat)
        formulaire.addRow("Longueur des segments :", self.spin_longueur_segment)
        layout.addLayout(formulaire)

        bouton_calculer = QPushButton("Calculer le pacing")
        bouton_calculer.setObjectName("boutonPrincipal")
        bouton_calculer.clicked.connect(self.calculer)
        layout.addWidget(bouton_calculer)

        self.table_segments = QTableWidget()
        self.table_segments.setColumnCount(5)
        self.table_segments.setHorizontalHeaderLabels(
            ["Segment", "Distance", "Pente moy.", "Allure cible", "Temps cumulé"]
        )
        configurer_table_redimensionnable(self.table_segments)
        self.table_segments.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self.table_segments)

        self.label_total = QLabel("")
        self.label_total.setObjectName("texteSecondaire")
        layout.addWidget(self.label_total)

    def calculer(self):
        from interface.conformite import parser_allure

        allure_plat = parser_allure(self.champ_allure_plat.text().strip())
        if not allure_plat:
            QMessageBox.warning(self, "Allure requise", "Indique une allure de référence valide (mm:ss).")
            return

        segments = decouper_par_segments(self.points, self.spin_longueur_segment.value())
        if not segments:
            QMessageBox.information(self, "Trace trop courte", "Pas assez de points pour découper cette trace.")
            return

        segments_pacing, temps_total_texte = calculer_pacing(segments, allure_plat)

        self.table_segments.setRowCount(len(segments_pacing))
        for i, seg in enumerate(segments_pacing):
            h, reste = divmod(seg["temps_cumule_s"], 3600)
            m, s = divmod(reste, 60)
            temps_cumule_texte = f"{h}h{m:02d}" if h else f"{m}min{s:02d}"
            self.table_segments.setItem(i, 0, QTableWidgetItem(f"Km {i + 1}"))
            self.table_segments.setItem(i, 1, QTableWidgetItem(f"{seg['distance_km']} km"))
            self.table_segments.setItem(
                i, 2, QTableWidgetItem(f"{seg['pente_moyenne_pct']:+.1f} % (D+{seg['denivele_positif']}/D-{seg['denivele_negatif']})")
            )
            self.table_segments.setItem(i, 3, QTableWidgetItem(f"{seg['allure_cible_texte']}/km"))
            self.table_segments.setItem(i, 4, QTableWidgetItem(temps_cumule_texte))
        self.table_segments.resizeColumnsToContents()

        self.label_total.setText(f"Temps cible total estimé : {temps_total_texte}")
