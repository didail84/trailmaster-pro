"""
Écran "Bilan IA" — comptes rendus périodiques (semaine / mois / année)
générés par l'IA Gemini, complément du compte rendu par sortie
(interface/historique_activites.py) : voir interface/ia_coach.py pour
le détail du fonctionnement (gratuit, en ligne, données chiffrées
uniquement, mis en cache par période).
"""

from datetime import datetime

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
    QScrollArea,
    QTextEdit,
    QMessageBox,
    QApplication,
)

from data.database import obtenir_athletes
from interface.ecran_liste import obtenir_style_ecran
from interface.ia_coach import analyser_periode, cle_api_configuree
from interface.tache_ia import TacheAnalyseIA


PERIODES = [
    ("Semaine (en cours)", "semaine"),
    ("Mois (en cours)", "mois"),
    ("Année (en cours)", "annee"),
]


class BilanIA(QMainWindow):

    def __init__(self, athlete_id_initial=None):
        super().__init__()

        self.setWindowTitle("TrailMaster Pro – Bilan IA")
        self.resize(1300, 900)
        self.setMinimumSize(1000, 650)

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

        titre = QLabel("🤖  Bilan IA")
        titre.setObjectName("titrePage")
        sous_titre = QLabel(
            "Compte rendu périodique généré par l'IA (Gemini) : bilan, objectifs, progression "
            "et recommandations — nécessite une connexion internet et une clé API gratuite "
            "(Réglages > Analyse IA des sorties)"
        )
        sous_titre.setObjectName("sousTitrePage")
        sous_titre.setWordWrap(True)
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

        label_periode = QLabel("Période :")
        label_periode.setObjectName("labelChamp")
        self.combo_periode = QComboBox()
        for libelle, cle in PERIODES:
            self.combo_periode.addItem(libelle, cle)

        bouton_generer = QPushButton("🤖 Générer le bilan")
        bouton_generer.setObjectName("boutonPrincipal")
        bouton_generer.clicked.connect(lambda: self._lancer_analyse(forcer=False))

        self.bouton_regenerer = QPushButton("🔄 Régénérer")
        self.bouton_regenerer.setObjectName("boutonSecondaire")
        self.bouton_regenerer.clicked.connect(lambda: self._lancer_analyse(forcer=True))
        self.bouton_regenerer.setEnabled(False)

        barre.addWidget(label_athlete)
        barre.addWidget(self.combo_athlete)
        barre.addSpacing(10)
        barre.addWidget(label_periode)
        barre.addWidget(self.combo_periode)
        barre.addStretch()
        barre.addWidget(bouton_generer)
        barre.addWidget(self.bouton_regenerer)
        principal.addLayout(barre)

        self.label_periode_couverte = QLabel("")
        self.label_periode_couverte.setObjectName("texteSecondaire")
        principal.addWidget(self.label_periode_couverte)

        cadre_resultat = QFrame()
        cadre_resultat.setObjectName("carteForm")
        resultat_layout = QVBoxLayout(cadre_resultat)
        self.zone_texte = QTextEdit()
        self.zone_texte.setReadOnly(True)
        self.zone_texte.setMinimumHeight(450)
        self.zone_texte.setPlaceholderText(
            "Choisis un athlète et une période, puis clique sur « 🤖 Générer le bilan »."
        )
        resultat_layout.addWidget(self.zone_texte)
        principal.addWidget(cadre_resultat, 1)

        self.setStyleSheet(obtenir_style_ecran())

        if athlete_id_initial is not None:
            for i in range(self.combo_athlete.count()):
                if self.combo_athlete.itemData(i) == athlete_id_initial:
                    self.combo_athlete.setCurrentIndex(i)
                    break

    def _lancer_analyse(self, forcer):
        athlete_id = self.combo_athlete.currentData()
        if athlete_id is None:
            QMessageBox.information(self, "Sélection requise", "Sélectionne d'abord un athlète.")
            return

        if not cle_api_configuree():
            self.zone_texte.setPlainText(
                "⚠️ Aucune clé API configurée.\n\n"
                "Va dans Réglages > Analyse IA des sorties pour renseigner une clé gratuite "
                "(Gemini et/ou Groq), puis reviens ici."
            )
            self.bouton_regenerer.setEnabled(False)
            return

        type_periode = self.combo_periode.currentData()

        self.zone_texte.setPlainText(
            "⏳ Génération du bilan en cours... (nécessite une connexion internet — la "
            "fenêtre reste utilisable pendant l'attente)"
            if forcer else
            "⏳ Chargement du bilan..."
        )
        self.bouton_regenerer.setEnabled(False)

        self._tache_bilan = TacheAnalyseIA(
            lambda: analyser_periode(
                athlete_id, type_periode, date_ref=datetime.now().date(),
                forcer_regeneration=forcer,
            )
        )
        self._tache_bilan.reussite.connect(self._bilan_reussi)
        self._tache_bilan.echec.connect(self._bilan_echoue)
        self._tache_bilan.start()

    def _bilan_reussi(self, resultat):
        contenu, depuis_cache, debut, fin = resultat
        self.label_periode_couverte.setText(
            f"Période couverte : du {debut.strftime('%d/%m/%Y')} au {fin.strftime('%d/%m/%Y')}"
        )
        entete = "📦 Bilan déjà généré pour cette période (mise en cache) :\n\n" if depuis_cache else ""
        self.zone_texte.setPlainText(entete + contenu)
        self.bouton_regenerer.setEnabled(True)

    def _bilan_echoue(self, message):
        self.zone_texte.setPlainText(f"⚠️ {message}")
        self.bouton_regenerer.setEnabled(True)
