from pathlib import Path

from PySide6.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QLabel,
    QPushButton,
    QFrame,
    QGraphicsDropShadowEffect,
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QPainter, QPixmap, QLinearGradient, QColor

from interface.theme import (
    charger_polices, obtenir_couleur_accent, obtenir_couleur_accent_douce, eclaircir, PALETTE,
    POLICE_TITRE_EXTRA, POLICE_TITRE, POLICE_TEXTE, dossier_racine_ressources,
)
from interface.logo_widget import LogoMontagne
from interface.tableau_bord import TableauBord
from interface.verification_maj import VerificationMajThread, proposer_mise_a_jour


CHEMIN_PHOTO_DEMARRAGE = (
    dossier_racine_ressources() / "ressources" / "images" / "demarrage_fond.jpg"
)


class FondPhoto(QWidget):
    """Fond plein cadre pour l'écran de démarrage : une photo (recadrée
    façon 'cover', comme un fond d'écran) avec un voile sombre dégradé
    par-dessus pour que le texte du logiciel reste lisible quel que
    soit l'endroit de la photo qu'il recouvre.

    Si le fichier photo est absent (installation sans le dossier
    ressources/images complet), retombe simplement sur le fond uni de
    la charte graphique — jamais d'erreur ni d'écran vide."""

    def __init__(self, chemin_image, parent=None):
        super().__init__(parent)
        self._pixmap_source = QPixmap(str(chemin_image)) if Path(chemin_image).is_file() else QPixmap()

    def paintEvent(self, event):
        peintre = QPainter(self)
        peintre.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        zone = self.rect()

        if not self._pixmap_source.isNull():
            pixmap_ajuste = self._pixmap_source.scaled(
                zone.size(),
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation,
            )
            x = max(0, (pixmap_ajuste.width() - zone.width()) // 2)
            y = max(0, (pixmap_ajuste.height() - zone.height()) // 2)
            peintre.drawPixmap(
                0, 0, zone.width(), zone.height(),
                pixmap_ajuste, x, y, zone.width(), zone.height(),
            )
        else:
            peintre.fillRect(zone, QColor(PALETTE["fond"]))

        # Voile sombre dégradé (plus léger en haut, opaque en bas) —
        # garantit la lisibilité du texte quelle que soit la photo.
        degrade = QLinearGradient(0, 0, 0, zone.height())
        degrade.setColorAt(0.0, QColor(10, 12, 15, 70))
        degrade.setColorAt(0.42, QColor(10, 12, 15, 130))
        degrade.setColorAt(0.62, QColor(10, 12, 15, 195))
        degrade.setColorAt(1.0, QColor(8, 10, 13, 245))
        peintre.fillRect(zone, degrade)

        peintre.end()


class Accueil(QMainWindow):
    def __init__(self):
        super().__init__()

        charger_polices()

        self.setWindowTitle("TrailMaster Pro")
        self.resize(1000, 700)

        central = FondPhoto(CHEMIN_PHOTO_DEMARRAGE)
        self.setCentralWidget(central)

        layout = QVBoxLayout(central)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(24)

        logo = LogoMontagne(76)
        conteneur_logo = QWidget()
        conteneur_logo_layout = QVBoxLayout(conteneur_logo)
        conteneur_logo_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        conteneur_logo_layout.addWidget(logo)

        titre = QLabel("TRAILMASTER")
        titre.setAlignment(Qt.AlignmentFlag.AlignCenter)
        titre.setStyleSheet(f"""
            font-family: '{POLICE_TITRE_EXTRA}';
            font-size: 38px;
            font-weight: 800;
            letter-spacing: 4px;
            color: {PALETTE['texte']};
        """)
        ombre_titre = QGraphicsDropShadowEffect()
        ombre_titre.setBlurRadius(22)
        ombre_titre.setOffset(0, 2)
        ombre_titre.setColor(QColor(0, 0, 0, 200))
        titre.setGraphicsEffect(ombre_titre)

        badge_pro = QLabel("PRO")
        badge_pro.setAlignment(Qt.AlignmentFlag.AlignCenter)
        accent = obtenir_couleur_accent()
        badge_pro.setStyleSheet(f"""
            font-family: '{POLICE_TITRE}';
            font-size: 12px;
            font-weight: 700;
            letter-spacing: 3px;
            color: {accent};
            background-color: {obtenir_couleur_accent_douce(0.12)};
            border: 1px solid {accent};
            border-radius: 999px;
            padding: 5px 18px;
        """)

        sous_titre = QLabel("Suivi d'entraînement trail running")
        sous_titre.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sous_titre.setStyleSheet(f"""
            font-family: '{POLICE_TEXTE}';
            font-size: 14.5px;
            color: {PALETTE['texte_secondaire']};
        """)

        bouton = QPushButton("Entrer dans TrailMaster")
        bouton.setMinimumSize(300, 52)
        bouton.setCursor(Qt.CursorShape.PointingHandCursor)
        bouton.clicked.connect(self.ouvrir_tableau_bord)
        bouton.setStyleSheet(f"""
            QPushButton {{
                background-color: {accent};
                color: white;
                border: none;
                border-radius: 10px;
                font-family: '{POLICE_TEXTE}';
                font-size: 14.5px;
                font-weight: 600;
                padding: 12px;
            }}
            QPushButton:hover {{
                background-color: {eclaircir(accent)};
            }}
        """)

        pied = QLabel("100% hors-ligne · vos données restent sur votre ordinateur")
        pied.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pied.setStyleSheet(f"""
            font-family: '{POLICE_TEXTE}';
            font-size: 11.5px;
            color: #4A535A;
        """)

        layout.addWidget(conteneur_logo)
        layout.addWidget(titre)
        layout.addWidget(badge_pro, alignment=Qt.AlignmentFlag.AlignCenter)
        layout.addSpacing(6)
        layout.addWidget(sous_titre)
        layout.addSpacing(24)
        layout.addWidget(bouton, alignment=Qt.AlignmentFlag.AlignCenter)
        layout.addSpacing(30)
        layout.addWidget(pied)

        # Vérification d'une mise à jour disponible — en arrière-plan,
        # ne retarde jamais l'affichage de cet écran de démarrage, et
        # reste totalement silencieuse si pas de réseau ou pas de
        # nouvelle version.
        self._fil_verification_maj = VerificationMajThread()
        self._fil_verification_maj.resultat_disponible.connect(self._mise_a_jour_detectee)
        QTimer.singleShot(400, self._fil_verification_maj.start)

    def _mise_a_jour_detectee(self, resultat):
        if resultat:
            proposer_mise_a_jour(self, resultat)

    def ouvrir_tableau_bord(self):
        self.tableau_bord = TableauBord()
        self.tableau_bord.show()
        self.close()
