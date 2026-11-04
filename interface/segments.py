import json

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QComboBox,
    QSpinBox,
    QPushButton,
    QFrame,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QLineEdit,
    QMessageBox,
    QScrollArea,
)
from noyau.donnees import activites as dact, parcours as dparc  # accès aux données

from data.database import connexion, creer_base_de_donnees, obtenir_athletes
from interface.ecran_liste import obtenir_style_ecran, configurer_table_redimensionnable
from interface.trace_widget import TraceCanvas
from noyau.traces.segments_utils import (
    extraire_reference_segment,
    detecter_occurrence,
    duree_occurrence_s,
)
from noyau.donnees import segments as dseg


def _formater_duree(secondes):
    if not secondes:
        return "—"
    secondes = int(secondes)
    m, s = divmod(secondes, 60)
    return f"{m}min{s:02d}"


class Segments(QMainWindow):

    def __init__(self, athlete_id_initial=None):
        super().__init__()

        creer_base_de_donnees()

        self.setWindowTitle("TrailMaster Pro – Segments précis")
        self.resize(1300, 900)
        self.setMinimumSize(1050, 700)

        self.parcours_disponibles = []
        self.segments_ids = []

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

        titre = QLabel("🎯  Segments précis")
        titre.setObjectName("titrePage")
        sous_titre = QLabel(
            "Découpe un tronçon précis d'une sortie et compare tes temps à chaque "
            "fois que tu l'as reparcouru — pas juste le même coin, le même tracé"
        )
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

        cadre_creation = QFrame()
        cadre_creation.setObjectName("carteForm")
        creation_layout = QVBoxLayout(cadre_creation)

        titre_creation = QLabel("Créer un segment à partir d'une sortie existante")
        titre_creation.setObjectName("titreCarte")
        creation_layout.addWidget(titre_creation)

        barre_creation = QHBoxLayout()
        self.combo_parcours = QComboBox()
        self.combo_parcours.currentIndexChanged.connect(self.previsualiser)

        self.champ_nom_segment = QLineEdit()
        self.champ_nom_segment.setPlaceholderText("Nom du segment")

        label_debut = QLabel("Début (%) :")
        self.spin_debut = QSpinBox()
        self.spin_debut.setRange(0, 95)
        self.spin_debut.setValue(0)
        self.spin_debut.valueChanged.connect(self.previsualiser)

        label_fin = QLabel("Fin (%) :")
        self.spin_fin = QSpinBox()
        self.spin_fin.setRange(5, 100)
        self.spin_fin.setValue(15)
        self.spin_fin.valueChanged.connect(self.previsualiser)

        barre_creation.addWidget(self.combo_parcours, 2)
        barre_creation.addWidget(self.champ_nom_segment, 1)
        barre_creation.addWidget(label_debut)
        barre_creation.addWidget(self.spin_debut)
        barre_creation.addWidget(label_fin)
        barre_creation.addWidget(self.spin_fin)
        creation_layout.addLayout(barre_creation)

        self.label_apercu = QLabel("Aperçu : —")
        self.label_apercu.setObjectName("texteSecondaire")
        creation_layout.addWidget(self.label_apercu)

        self.canvas_apercu = TraceCanvas()
        self.canvas_apercu.setMinimumHeight(220)
        creation_layout.addWidget(self.canvas_apercu)

        bouton_creer = QPushButton("🎯 Créer ce segment et chercher les passages")
        bouton_creer.setObjectName("boutonPrincipal")
        bouton_creer.setCursor(Qt.CursorShape.PointingHandCursor)
        bouton_creer.clicked.connect(self.creer_segment)
        creation_layout.addWidget(bouton_creer)

        principal.addWidget(cadre_creation)

        titre_liste = QLabel("Mes segments")
        titre_liste.setObjectName("titreCarte")
        principal.addWidget(titre_liste)

        self.table_segments = QTableWidget()
        self.table_segments.setColumnCount(5)
        self.table_segments.setHorizontalHeaderLabels(
            ["Nom", "Distance", "D+", "Passages trouvés", "Meilleur temps"]
        )
        configurer_table_redimensionnable(self.table_segments)
        self.table_segments.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table_segments.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table_segments.itemSelectionChanged.connect(self.afficher_classement)
        principal.addWidget(self.table_segments)

        barre_actions_segments = QHBoxLayout()
        bouton_rescanner = QPushButton("🔄 Rechercher de nouveaux passages")
        bouton_rescanner.setObjectName("boutonSecondaire")
        bouton_rescanner.clicked.connect(self.rescanner_segment)
        bouton_supprimer = QPushButton("Supprimer le segment sélectionné")
        bouton_supprimer.setObjectName("boutonSecondaire")
        bouton_supprimer.clicked.connect(self.supprimer_segment)
        barre_actions_segments.addWidget(bouton_rescanner)
        barre_actions_segments.addWidget(bouton_supprimer)
        barre_actions_segments.addStretch()
        principal.addLayout(barre_actions_segments)

        titre_classement = QLabel("Classement des passages")
        titre_classement.setObjectName("titreCarte")
        principal.addWidget(titre_classement)

        self.table_classement = QTableWidget()
        self.table_classement.setColumnCount(4)
        self.table_classement.setHorizontalHeaderLabels(["Rang", "Date", "Temps", "Écart au record"])
        configurer_table_redimensionnable(self.table_classement)
        self.table_classement.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        principal.addWidget(self.table_classement)

        self.setStyleSheet(obtenir_style_ecran())

        if athlete_id_initial is not None:
            for i in range(self.combo_athlete.count()):
                if self.combo_athlete.itemData(i) == athlete_id_initial:
                    self.combo_athlete.setCurrentIndex(i)
                    break

        self.combo_athlete.currentIndexChanged.connect(self.charger_parcours_et_segments)
        self.charger_parcours_et_segments()

    def charger_parcours_et_segments(self):
        athlete_id = self.combo_athlete.currentData()

        self.combo_parcours.blockSignals(True)
        self.combo_parcours.clear()
        self.parcours_disponibles = []

        if athlete_id is not None:
            self.parcours_disponibles = dparc.liste_courte(athlete_id, 200)
            for id_, nom, distance in self.parcours_disponibles:
                self.combo_parcours.addItem(f"{nom} ({distance} km)", id_)

        self.combo_parcours.blockSignals(False)
        self.previsualiser()
        self.charger_segments()

    def _points_parcours(self, parcours_id):
        trace_json = dparc.trace(parcours_id)
        if not trace_json:
            return None
        return json.loads(trace_json)

    def previsualiser(self):
        parcours_id = self.combo_parcours.currentData()
        if parcours_id is None:
            self.canvas_apercu.definir_trace([], [])
            self.label_apercu.setText("Aperçu : —")
            return

        points = self._points_parcours(parcours_id)
        if not points:
            return

        debut_idx = int(len(points) * self.spin_debut.value() / 100)
        fin_idx = int(len(points) * self.spin_fin.value() / 100)
        if fin_idx <= debut_idx:
            fin_idx = min(debut_idx + 2, len(points) - 1)

        sous_trace = points[debut_idx:fin_idx + 1]
        points_2d = [(p[0], p[1]) for p in sous_trace]
        altitudes = [p[2] for p in sous_trace]
        self.canvas_apercu.definir_trace(points_2d, altitudes)

        segment_test = extraire_reference_segment(points, debut_idx, fin_idx)
        if segment_test:
            self.label_apercu.setText(
                f"Aperçu : {segment_test['distance_km']} km, {segment_test['denivele_positif']} m D+"
            )
        else:
            self.label_apercu.setText("Aperçu : tronçon trop court (< 100 m)")

    def creer_segment(self):
        athlete_id = self.combo_athlete.currentData()
        parcours_id = self.combo_parcours.currentData()

        if athlete_id is None or parcours_id is None:
            QMessageBox.warning(self, "Sélection requise", "Choisis un athlète et une sortie.")
            return
        if not self.champ_nom_segment.text().strip():
            QMessageBox.warning(self, "Nom requis", "Donne un nom à ce segment.")
            return

        points = self._points_parcours(parcours_id)
        if not points:
            return

        debut_idx = int(len(points) * self.spin_debut.value() / 100)
        fin_idx = int(len(points) * self.spin_fin.value() / 100)
        segment = extraire_reference_segment(points, debut_idx, fin_idx)

        if not segment:
            QMessageBox.warning(
                self, "Tronçon trop court",
                "Le tronçon sélectionné fait moins de 100 m — choisis une plage plus large."
            )
            return

        segment_id = dseg.creer({
            "athlete_id": athlete_id,
            "nom": self.champ_nom_segment.text().strip(),
            "distance_km": segment["distance_km"],
            "denivele_positif": segment["denivele_positif"],
            "points_reference_json": json.dumps(segment["points_reference"]),
            "parcours_origine_id": parcours_id,
        })

        nb_trouves = self._rechercher_passages(segment_id, athlete_id, segment["points_reference"])

        QMessageBox.information(
            self, "Segment créé",
            f"Segment « {self.champ_nom_segment.text().strip()} » créé "
            f"({segment['distance_km']} km).\n\n{nb_trouves} passage(s) trouvé(s) dans tes sorties."
        )

        self.champ_nom_segment.clear()
        self.charger_segments()

    def _rechercher_passages(self, segment_id, athlete_id, points_reference):
        conn = connexion()
        cur = conn.cursor()
        tous_parcours = dparc.traces_et_activites(athlete_id)

        deja_trouves = dseg.parcours_deja_trouves(segment_id, cur=cur)

        nb_nouveaux = 0
        for parcours_id, trace_json, activite_id in tous_parcours:
            if parcours_id in deja_trouves or not trace_json:
                continue

            points = json.loads(trace_json)
            occurrence = detecter_occurrence(points_reference, points)
            if not occurrence:
                continue

            duree = duree_occurrence_s(points, occurrence[0], occurrence[1])
            if duree is None:
                continue

            date_activite = None
            if activite_id:
                ligne = dact.valeurs(activite_id, "date", cur=cur)
                date_activite = ligne[0] if ligne else None

            dseg.ajouter_passage(segment_id, parcours_id, activite_id, date_activite, duree, cur=cur)
            nb_nouveaux += 1

        conn.commit()
        conn.close()
        return nb_nouveaux

    def charger_segments(self):
        athlete_id = self.combo_athlete.currentData()
        self.table_segments.setRowCount(0)
        self.table_classement.setRowCount(0)

        if athlete_id is None:
            self.segments_ids = []
            return

        segments = dseg.lister(athlete_id)

        self.segments_ids = [s[0] for s in segments]
        self.table_segments.setRowCount(len(segments))
        for i, (id_, nom, distance, denivele) in enumerate(segments):
            nb_passages, meilleur = dseg.resume_passages(id_)

            self.table_segments.setItem(i, 0, QTableWidgetItem(nom))
            self.table_segments.setItem(i, 1, QTableWidgetItem(f"{distance} km"))
            self.table_segments.setItem(i, 2, QTableWidgetItem(f"{denivele} m"))
            self.table_segments.setItem(i, 3, QTableWidgetItem(str(nb_passages or 0)))
            self.table_segments.setItem(i, 4, QTableWidgetItem(_formater_duree(meilleur)))

        self.table_segments.resizeColumnsToContents()

    def afficher_classement(self):
        self.table_classement.setRowCount(0)
        ligne = self.table_segments.currentRow()
        if ligne < 0 or ligne >= len(self.segments_ids):
            return

        segment_id = self.segments_ids[ligne]

        efforts = dseg.classement(segment_id)

        if not efforts:
            return

        record = efforts[0][1]
        self.table_classement.setRowCount(len(efforts))
        for i, (date_, duree) in enumerate(efforts):
            ecart = duree - record
            self.table_classement.setItem(i, 0, QTableWidgetItem(f"#{i + 1}"))
            self.table_classement.setItem(i, 1, QTableWidgetItem(str(date_)[:16] if date_ else "—"))
            self.table_classement.setItem(i, 2, QTableWidgetItem(_formater_duree(duree)))
            self.table_classement.setItem(
                i, 3, QTableWidgetItem("Record" if i == 0 else f"+{_formater_duree(ecart)}")
            )

        self.table_classement.resizeColumnsToContents()

    def rescanner_segment(self):
        ligne = self.table_segments.currentRow()
        if ligne < 0:
            QMessageBox.information(self, "Sélection requise", "Sélectionne d'abord un segment.")
            return

        segment_id = self.segments_ids[ligne]
        athlete_id = self.combo_athlete.currentData()

        points_reference = dseg.points_reference(segment_id)

        nb_nouveaux = self._rechercher_passages(segment_id, athlete_id, points_reference)
        QMessageBox.information(self, "Recherche terminée", f"{nb_nouveaux} nouveau(x) passage(s) trouvé(s).")

        self.charger_segments()
        self.table_segments.selectRow(ligne)

    def supprimer_segment(self):
        ligne = self.table_segments.currentRow()
        if ligne < 0:
            QMessageBox.information(self, "Sélection requise", "Sélectionne d'abord un segment.")
            return

        confirmation = QMessageBox.question(
            self, "Confirmer la suppression",
            "Supprimer ce segment et tous ses passages enregistrés ?"
        )
        if confirmation != QMessageBox.StandardButton.Yes:
            return

        segment_id = self.segments_ids[ligne]
        dseg.supprimer(segment_id)

        self.charger_segments()
