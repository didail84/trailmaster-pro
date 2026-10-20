from datetime import datetime

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QComboBox,
    QDoubleSpinBox,
    QSpinBox,
    QPushButton,
    QFrame,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QListWidget,
    QSplitter,
    QScrollArea,
)

from data.database import obtenir_athletes
from interface.ecran_liste import obtenir_style_ecran, configurer_table_redimensionnable
from interface.trace_widget import TraceCanvas
from interface.secteurs_utils import calculer_stats_secteurs


class Secteurs(QMainWindow):

    def __init__(self, athlete_id_initial=None):
        super().__init__()

        self.setWindowTitle("TrailMaster Pro – Secteurs d'entraînement")
        self.resize(1300, 850)
        self.setMinimumSize(1050, 700)

        self.secteurs_courants = []

        central = QWidget()
        conteneur_scroll = QScrollArea()
        conteneur_scroll.setWidgetResizable(True)
        conteneur_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        conteneur_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        conteneur_scroll.setFrameShape(QFrame.Shape.NoFrame)
        conteneur_scroll.setWidget(central)
        self.setCentralWidget(conteneur_scroll)

        principal = QVBoxLayout(central)
        principal.setContentsMargins(25, 20, 25, 20)
        principal.setSpacing(15)

        titre = QLabel("🧭  Secteurs d'entraînement")
        titre.setObjectName("titrePage")
        sous_titre = QLabel(
            "Quels coins fréquenter pour ta prochaine sortie — regroupement "
            "des traces GPX enregistrées (Trail, VTT, Randonnée, Course, Vélo)"
        )
        sous_titre.setObjectName("sousTitrePage")
        principal.addWidget(titre)
        principal.addWidget(sous_titre)

        # ------------------------------------------------------------
        # BARRE DE CONTRÔLE
        # ------------------------------------------------------------

        barre = QHBoxLayout()

        label_athlete = QLabel("Athlète :")
        label_athlete.setObjectName("labelChamp")
        self.combo_athlete = QComboBox()
        self.athletes = obtenir_athletes()
        self.combo_athlete.addItem("Sélectionner...", None)
        for a in self.athletes:
            self.combo_athlete.addItem(f"{a[2]} {a[1]}", a[0])

        label_distance = QLabel("Distance visée (km) :")
        label_distance.setObjectName("labelChamp")
        self.champ_distance = QDoubleSpinBox()
        self.champ_distance.setRange(0, 300)
        self.champ_distance.setDecimals(1)
        self.champ_distance.setSpecialValueText("Non précisé")

        label_denivele = QLabel("D+ visé (m) :")
        label_denivele.setObjectName("labelChamp")
        self.champ_denivele = QSpinBox()
        self.champ_denivele.setRange(0, 10000)
        self.champ_denivele.setSpecialValueText("Non précisé")

        bouton_analyser = QPushButton("🔍 Analyser mes secteurs")
        bouton_analyser.setObjectName("boutonPrincipal")
        bouton_analyser.setCursor(Qt.CursorShape.PointingHandCursor)
        bouton_analyser.clicked.connect(self.actualiser)

        barre.addWidget(label_athlete)
        barre.addWidget(self.combo_athlete)
        barre.addSpacing(15)
        barre.addWidget(label_distance)
        barre.addWidget(self.champ_distance)
        barre.addWidget(label_denivele)
        barre.addWidget(self.champ_denivele)
        barre.addStretch()
        barre.addWidget(bouton_analyser)

        principal.addLayout(barre)

        note = QLabel(
            "Score fraîcheur : secteurs peu/pas visités récemment, pour varier · "
            "Score profil : distance/D+ du secteur comparés à l'objectif ci-dessus · "
            "Score global = moyenne des deux"
        )
        note.setObjectName("texteSecondaire")
        note.setWordWrap(True)
        principal.addWidget(note)

        # ------------------------------------------------------------
        # TABLEAU DES SECTEURS
        # ------------------------------------------------------------

        self.table = QTableWidget()
        colonnes = [
            "Secteur", "Sorties", "Distance moy.", "D+ moy.",
            "Dernière visite", "Fraîcheur", "Profil", "Score global",
        ]
        self.table.setColumnCount(len(colonnes))
        self.table.setHorizontalHeaderLabels(colonnes)
        configurer_table_redimensionnable(self.table)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.itemSelectionChanged.connect(self.afficher_detail_secteur)
        principal.addWidget(self.table, 2)

        # ------------------------------------------------------------
        # DÉTAIL DU SECTEUR SÉLECTIONNÉ
        # ------------------------------------------------------------

        titre_detail = QLabel("Détail du secteur sélectionné")
        titre_detail.setObjectName("titreCarte")
        principal.addWidget(titre_detail)

        separateur = QSplitter(Qt.Orientation.Horizontal)

        self.liste_traces = QListWidget()
        self.liste_traces.setMaximumWidth(320)
        self.liste_traces.itemClicked.connect(self.afficher_trace)
        separateur.addWidget(self.liste_traces)

        cadre_canvas = QFrame()
        cadre_canvas.setObjectName("carteForm")
        canvas_layout = QVBoxLayout(cadre_canvas)
        self.canvas = TraceCanvas()
        canvas_layout.addWidget(self.canvas)
        separateur.addWidget(cadre_canvas)

        separateur.setStretchFactor(0, 1)
        separateur.setStretchFactor(1, 2)

        principal.addWidget(separateur, 2)

        self.setStyleSheet(obtenir_style_ecran())

        if athlete_id_initial is not None:
            for i in range(self.combo_athlete.count()):
                if self.combo_athlete.itemData(i) == athlete_id_initial:
                    self.combo_athlete.setCurrentIndex(i)
                    break

        self.actualiser()

    # ------------------------------------------------------------
    def actualiser(self):
        self.table.setRowCount(0)
        self.liste_traces.clear()
        self.canvas.definir_trace([], [])
        self.secteurs_courants = []

        athlete_id = self.combo_athlete.currentData()
        if athlete_id is None:
            return

        distance_visee = self.champ_distance.value() or None
        denivele_vise = self.champ_denivele.value() or None

        self.secteurs_courants = calculer_stats_secteurs(
            athlete_id, distance_visee_km=distance_visee, denivele_vise_m=denivele_vise
        )

        self.table.setRowCount(len(self.secteurs_courants))
        for i, secteur in enumerate(self.secteurs_courants):
            derniere = (
                secteur["derniere_visite"].strftime("%d/%m/%Y")
                if secteur["derniere_visite"] else "—"
            )
            valeurs = [
                secteur["nom"],
                str(secteur["nb_sorties"]),
                f"{secteur['distance_moyenne']} km",
                f"{secteur['denivele_moyen']} m",
                derniere,
                str(secteur["score_fraicheur"]),
                str(secteur["score_profil"]),
                str(secteur["score_global"]),
            ]
            for j, valeur in enumerate(valeurs):
                item = QTableWidgetItem(valeur)
                if j == len(valeurs) - 1:
                    couleur = self._couleur_score(secteur["score_global"])
                    item.setForeground(couleur)
                self.table.setItem(i, j, item)

        self.table.resizeColumnsToContents()

    def _couleur_score(self, score):
        from PySide6.QtGui import QColor
        if score >= 70:
            return QColor("#66BB6A")
        if score >= 40:
            return QColor("#F9A825")
        return QColor("#EF5350")

    def afficher_detail_secteur(self):
        self.liste_traces.clear()
        self.canvas.definir_trace([], [])

        ligne = self.table.currentRow()
        if ligne < 0 or ligne >= len(self.secteurs_courants):
            return

        secteur = self.secteurs_courants[ligne]
        for trace in sorted(secteur["traces"], key=lambda t: t["date"] or datetime.min, reverse=True):
            date_texte = trace["date"].strftime("%d/%m/%Y") if trace["date"] else "date inconnue"
            libelle = f"{date_texte} — {trace['nom']} ({trace['distance_km']} km, {trace['denivele_positif']} m D+)"
            self.liste_traces.addItem(libelle)

        self.liste_traces.setProperty("traces_secteur", secteur["traces"])

    def afficher_trace(self, item):
        ligne = self.table.currentRow()
        if ligne < 0 or ligne >= len(self.secteurs_courants):
            return

        secteur = self.secteurs_courants[ligne]
        index = self.liste_traces.row(item)
        traces_triees = sorted(secteur["traces"], key=lambda t: t["date"] or datetime.min, reverse=True)
        if index < 0 or index >= len(traces_triees):
            return

        trace = traces_triees[index]
        points_2d = [(p[0], p[1]) for p in trace["points"]]
        altitudes = [p[2] for p in trace["points"]]
        self.canvas.definir_trace(points_2d, altitudes)
