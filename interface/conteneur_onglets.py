"""
Petit conteneur générique à onglets : regroupe plusieurs écrans
existants (chacun un QMainWindow autonome) dans une seule fenêtre,
sans avoir à modifier le code de chaque écran — un QMainWindow est
lui-même un QWidget, il peut donc être ajouté tel quel comme onglet.
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMainWindow, QTabWidget, QWidget, QVBoxLayout, QPushButton

from interface.theme import (
    obtenir_couleur_accent, obtenir_couleur_accent_douce, eclaircir, charger_polices,
    PALETTE, POLICE_TEXTE,
)


_STYLE_ONGLETS_MODELE = """
    #fondOnglets {
        background-color: PALETTE_FOND;
    }
    QTabWidget::pane {
        border: none;
        background-color: PALETTE_FOND;
    }
    QTabBar::tab {
        background-color: PALETTE_CARTE;
        color: PALETTE_TEXTE_SECONDAIRE;
        font-family: 'POLICE_TEXTE', 'Segoe UI', sans-serif;
        font-weight: 500;
        padding: 10px 18px;
        margin-right: 4px;
        border-top-left-radius: 9px;
        border-top-right-radius: 9px;
    }
    QTabBar::tab:selected {
        background-color: ACCENT_DOUCE;
        color: PALETTE_TEXTE;
        font-weight: 600;
    }
    QTabBar::tab:hover {
        color: PALETTE_TEXTE;
    }
    #boutonRetourTableauBord {
        background-color: transparent;
        color: PALETTE_TEXTE_SECONDAIRE;
        border: none;
        font-family: 'POLICE_TEXTE', sans-serif;
        font-size: 12.5px;
        padding: 8px 12px 4px 12px;
        text-align: left;
    }
    #boutonRetourTableauBord:hover {
        color: ACCENT_HOVER;
    }
"""


def _obtenir_style_onglets():
    return (
        _STYLE_ONGLETS_MODELE
        .replace("ACCENT_DOUCE", obtenir_couleur_accent_douce(0.20))
        .replace("ACCENT_HOVER", eclaircir(obtenir_couleur_accent()))
        .replace("PALETTE_FOND", PALETTE["fond"])
        .replace("PALETTE_CARTE", PALETTE["carte"])
        .replace("PALETTE_TEXTE_SECONDAIRE", PALETTE["texte_secondaire"])
        .replace("PALETTE_TEXTE", PALETTE["texte"])
        .replace("POLICE_TEXTE", POLICE_TEXTE)
    )


class ConteneurOnglets(QMainWindow):

    def __init__(self, titre, onglets, athlete_id_initial=None, onglet_initial=0):
        """onglets : liste de (label, classe_ecran) — chaque classe est
        instanciée avec athlete_id_initial=athlete_id_initial.
        onglet_initial : index de l'onglet affiché à l'ouverture (0 par
        défaut, le premier)."""

        super().__init__()
        charger_polices()
        self.setWindowTitle(f"TrailMaster Pro – {titre}")
        self.resize(1350, 950)
        self.setMinimumSize(1050, 700)

        central = QWidget()
        central.setObjectName("fondOnglets")
        layout = QVBoxLayout(central)
        layout.setContentsMargins(12, 8, 12, 0)
        layout.setSpacing(0)

        bouton_retour = QPushButton("← Aujourd'hui")
        bouton_retour.setObjectName("boutonRetourTableauBord")
        bouton_retour.setCursor(Qt.CursorShape.PointingHandCursor)
        bouton_retour.clicked.connect(self.close)
        layout.addWidget(bouton_retour, 0, Qt.AlignmentFlag.AlignLeft)

        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        layout.addWidget(self.tabs)

        central.setStyleSheet(_obtenir_style_onglets())
        self.setCentralWidget(central)

        self.ecrans = []
        for label, classe_ecran in onglets:
            ecran = classe_ecran(athlete_id_initial=athlete_id_initial)
            self.tabs.addTab(ecran, label)
            self.ecrans.append(ecran)

        if 0 <= onglet_initial < self.tabs.count():
            self.tabs.setCurrentIndex(onglet_initial)

    def selectionner_onglet(self, index):
        """Bascule sur l'onglet donné — utile quand une fenêtre déjà
        ouverte est ramenée au premier plan depuis un bouton de menu
        différent de celui qui l'a créée (ex. Compte : Athlètes / Réglages)."""
        if 0 <= index < self.tabs.count():
            self.tabs.setCurrentIndex(index)
