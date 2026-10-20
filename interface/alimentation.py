"""
Onglet Alimentation : contenu de référence (pas un journal de suivi,
voir interface/nutrition.py pour le journal des repas) —

  1. Fiches fruits & légumes : calories, saison, conseils de
     consommation pour un coureur.
  2. Aliments pour courir : meilleurs aliments transportables par
     catégorie (compotes, barres, viande, yaourts, biscuits).

Contenu rédigé une fois dans data/reference_alimentation.py,
consultable/filtrable ici — pas de mise à jour automatique, comme le
calendrier de courses.
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QComboBox, QListWidget, QListWidgetItem, QTextEdit, QSplitter,
    QScrollArea, QFrame, QTabWidget, QPushButton,
)

from data.reference_alimentation import FICHES_FRUITS_LEGUMES, ALIMENTS_COURSE, SAISONS
from interface.theme import (
    PALETTE, POLICE_TITRE, POLICE_TEXTE, POLICE_TEXTE_DEMI, charger_polices,
    obtenir_couleur_accent, obtenir_couleur_accent_douce,
)


def _style_page():
    return f"""
        QWidget {{
            background-color: {PALETTE['fond']};
            color: {PALETTE['texte']};
            font-family: '{POLICE_TEXTE}', sans-serif;
        }}
        #titrePage {{
            font-family: '{POLICE_TITRE}', sans-serif;
            font-size: 20px;
            font-weight: 700;
        }}
        #sousTitrePage {{
            color: {PALETTE['texte_secondaire']};
            font-size: 12.5px;
        }}
        QLineEdit, QComboBox {{
            background-color: {PALETTE['carte']};
            border: 1px solid {PALETTE['bordure']};
            border-radius: 8px;
            padding: 6px 10px;
            color: {PALETTE['texte']};
        }}
        QListWidget {{
            background-color: {PALETTE['carte']};
            border: 1px solid {PALETTE['bordure']};
            border-radius: 8px;
            padding: 4px;
        }}
        QListWidget::item {{
            padding: 8px 6px;
            border-radius: 6px;
        }}
        QListWidget::item:selected {{
            background-color: {obtenir_couleur_accent_douce(0.25)};
            color: {PALETTE['texte']};
        }}
        #cartefiche {{
            background-color: {PALETTE['carte']};
            border: 1px solid {PALETTE['bordure']};
            border-radius: 10px;
        }}
        #nomFiche {{
            font-family: '{POLICE_TEXTE_DEMI}', sans-serif;
            font-size: 17px;
        }}
        #metaFiche {{
            color: {obtenir_couleur_accent()};
            font-weight: 600;
            font-size: 12.5px;
        }}
        #conseilFiche {{
            color: {PALETTE['texte_secondaire']};
            font-size: 13px;
        }}
    """


class _FichesFruitsLegumes(QWidget):
    """Fiches fruits & légumes : liste filtrable à gauche, détail à droite."""

    def __init__(self, athlete_id_initial=None):
        super().__init__()
        self._fiches = FICHES_FRUITS_LEGUMES

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)

        titre = QLabel("🍎  Fiches fruits & légumes")
        titre.setObjectName("titrePage")
        sous_titre = QLabel(
            "Calories, saison et conseils de consommation pour tirer le meilleur "
            "parti de chaque fruit ou légume courant."
        )
        sous_titre.setObjectName("sousTitrePage")
        sous_titre.setWordWrap(True)
        layout.addWidget(titre)
        layout.addWidget(sous_titre)

        barre_filtres = QHBoxLayout()
        self.champ_recherche = QLineEdit()
        self.champ_recherche.setPlaceholderText("Rechercher un fruit ou légume…")
        self.champ_recherche.textChanged.connect(self._rafraichir_liste)

        self.combo_categorie = QComboBox()
        self.combo_categorie.addItems(["Toutes catégories", "Fruit", "Légume"])
        self.combo_categorie.currentIndexChanged.connect(self._rafraichir_liste)

        self.combo_saison = QComboBox()
        self.combo_saison.addItem("Toutes saisons")
        self.combo_saison.addItems(SAISONS)
        self.combo_saison.currentIndexChanged.connect(self._rafraichir_liste)

        barre_filtres.addWidget(self.champ_recherche, 2)
        barre_filtres.addWidget(self.combo_categorie, 1)
        barre_filtres.addWidget(self.combo_saison, 1)
        layout.addLayout(barre_filtres)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        self.liste = QListWidget()
        self.liste.setMinimumWidth(280)
        self.liste.currentItemChanged.connect(self._afficher_detail)
        splitter.addWidget(self.liste)

        self.carte_detail = QFrame()
        self.carte_detail.setObjectName("cartefiche")
        detail_layout = QVBoxLayout(self.carte_detail)
        detail_layout.setContentsMargins(20, 18, 20, 18)
        detail_layout.setSpacing(8)

        self.label_nom = QLabel("—")
        self.label_nom.setObjectName("nomFiche")
        self.label_meta = QLabel("")
        self.label_meta.setObjectName("metaFiche")
        self.label_conseil = QLabel("")
        self.label_conseil.setObjectName("conseilFiche")
        self.label_conseil.setWordWrap(True)

        detail_layout.addWidget(self.label_nom)
        detail_layout.addWidget(self.label_meta)
        detail_layout.addSpacing(6)
        detail_layout.addWidget(self.label_conseil)
        detail_layout.addStretch()

        splitter.addWidget(self.carte_detail)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)
        layout.addWidget(splitter, 1)

        self._rafraichir_liste()

    def _fiches_filtrees(self):
        texte = self.champ_recherche.text().strip().lower()
        categorie = self.combo_categorie.currentText()
        saison = self.combo_saison.currentText()

        resultat = []
        for fiche in self._fiches:
            if texte and texte not in fiche["nom"].lower():
                continue
            if categorie != "Toutes catégories" and fiche["categorie"] != categorie:
                continue
            if saison != "Toutes saisons" and saison not in fiche["saisons"] and "Toute l'année" not in fiche["saisons"]:
                continue
            resultat.append(fiche)
        return resultat

    def _rafraichir_liste(self):
        self.liste.clear()
        for fiche in self._fiches_filtrees():
            icone = "🍎" if fiche["categorie"] == "Fruit" else "🥦"
            item = QListWidgetItem(f"{icone}  {fiche['nom']}")
            item.setData(Qt.ItemDataRole.UserRole, fiche)
            self.liste.addItem(item)
        if self.liste.count() > 0:
            self.liste.setCurrentRow(0)
        else:
            self.label_nom.setText("Aucun résultat")
            self.label_meta.setText("")
            self.label_conseil.setText("")

    def _afficher_detail(self, item, _precedent=None):
        if item is None:
            return
        fiche = item.data(Qt.ItemDataRole.UserRole)
        self.label_nom.setText(fiche["nom"])
        saisons = ", ".join(fiche["saisons"])
        self.label_meta.setText(f"{fiche['categorie']} · {fiche['calories']} kcal / 100 g · Saison : {saisons}")
        self.label_conseil.setText(fiche["conseil"])


class _AlimentsPourCourir(QWidget):
    """Meilleurs aliments transportables pour courir, par catégorie."""

    def __init__(self, athlete_id_initial=None):
        super().__init__()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)

        titre = QLabel("🥖  Aliments pour courir")
        titre.setObjectName("titrePage")
        sous_titre = QLabel(
            "Les meilleurs aliments transportables pour les sorties longues, par catégorie."
        )
        sous_titre.setObjectName("sousTitrePage")
        sous_titre.setWordWrap(True)
        layout.addWidget(titre)
        layout.addWidget(sous_titre)

        zone_defilement = QScrollArea()
        zone_defilement.setWidgetResizable(True)
        zone_defilement.setFrameShape(QFrame.Shape.NoFrame)

        conteneur = QWidget()
        conteneur_layout = QVBoxLayout(conteneur)
        conteneur_layout.setSpacing(16)

        for categorie, produits in ALIMENTS_COURSE.items():
            carte_categorie = QFrame()
            carte_categorie.setObjectName("cartefiche")
            cat_layout = QVBoxLayout(carte_categorie)
            cat_layout.setContentsMargins(18, 14, 18, 14)
            cat_layout.setSpacing(10)

            label_categorie = QLabel(categorie)
            label_categorie.setObjectName("nomFiche")
            cat_layout.addWidget(label_categorie)

            for produit in produits:
                ligne = QHBoxLayout()
                nom_note = QLabel(f"{produit['note']}  {produit['nom']}")
                nom_note.setStyleSheet(f"font-weight: 600; color: {PALETTE['texte']};")
                nom_note.setWordWrap(True)
                ligne.addWidget(nom_note)
                cat_layout.addLayout(ligne)

                raison = QLabel(produit["raison"])
                raison.setObjectName("conseilFiche")
                raison.setWordWrap(True)
                cat_layout.addWidget(raison)

            conteneur_layout.addWidget(carte_categorie)

        conteneur_layout.addStretch()
        zone_defilement.setWidget(conteneur)
        layout.addWidget(zone_defilement, 1)


class Alimentation(QTabWidget):
    """Regroupe les deux fiches de référence dans un onglet unique,
    utilisable directement comme onglet ou comme fenêtre autonome."""

    def __init__(self, athlete_id_initial=None):
        super().__init__()
        self.setDocumentMode(True)
        self.setStyleSheet(_style_page())
        self.addTab(_FichesFruitsLegumes(athlete_id_initial), "🍎 Fruits & légumes")
        self.addTab(_AlimentsPourCourir(athlete_id_initial), "🥖 Aliments pour courir")


class AlimentationFenetre(QMainWindow):
    """Fenêtre autonome (accessible depuis le menu principal) contenant
    l'onglet Alimentation, avec le même bouton retour que les autres
    écrans du logiciel."""

    def __init__(self, athlete_id_initial=None):
        super().__init__()
        charger_polices()
        self.setWindowTitle("TrailMaster Pro – Alimentation")
        self.resize(1350, 950)
        self.setMinimumSize(1050, 700)

        central = QWidget()
        layout = QVBoxLayout(central)
        layout.setContentsMargins(12, 8, 12, 0)
        layout.setSpacing(0)
        central.setStyleSheet(_style_page())

        bouton_retour = QPushButton("← Aujourd'hui")
        bouton_retour.setObjectName("boutonRetourTableauBord")
        bouton_retour.setCursor(Qt.CursorShape.PointingHandCursor)
        bouton_retour.clicked.connect(self.close)
        layout.addWidget(bouton_retour, 0, Qt.AlignmentFlag.AlignLeft)

        self.onglets = Alimentation(athlete_id_initial=athlete_id_initial)
        layout.addWidget(self.onglets)

        self.setCentralWidget(central)
