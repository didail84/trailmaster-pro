"""
Vue calendrier du Sommeil — en plus du tableau classique de l'écran
Sommeil, une vue mensuelle avec les heures de coucher/lever déjà
enregistrées pour chaque jour (remplies automatiquement ou à la main),
pour voir le rythme de la semaine d'un coup d'œil plutôt que ligne par
ligne dans le tableau.
"""

import calendar
from datetime import date

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QPushButton, QFrame,
)

from data.database import connexion
from interface.theme import (
    PALETTE, POLICE_TITRE, POLICE_TEXTE, POLICE_TEXTE_DEMI,
    obtenir_couleur_accent, obtenir_couleur_accent_douce,
)


NOMS_JOURS = ["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"]
NOMS_MOIS = [
    "Janvier", "Février", "Mars", "Avril", "Mai", "Juin",
    "Juillet", "Août", "Septembre", "Octobre", "Novembre", "Décembre",
]


class CalendrierSommeil(QDialog):

    def __init__(self, athlete_id, parent=None):
        super().__init__(parent)
        self.athlete_id = athlete_id
        self.setWindowTitle("TrailMaster Pro – Calendrier du sommeil")
        self.resize(950, 650)

        aujourd_hui = date.today()
        self.annee_affichee = aujourd_hui.year
        self.mois_affiche = aujourd_hui.month

        self.setStyleSheet(f"""
            QDialog {{ background-color: {PALETTE['fond']}; }}
            QLabel {{ color: {PALETTE['texte']}; font-family: '{POLICE_TEXTE}', sans-serif; }}
            #titreMois {{
                font-family: '{POLICE_TITRE}', sans-serif;
                font-size: 18px;
                font-weight: 700;
            }}
            #boutonNav {{
                background-color: {PALETTE['carte']};
                border: 1px solid {PALETTE['bordure']};
                border-radius: 8px;
                padding: 6px 14px;
                color: {PALETTE['texte']};
            }}
            #boutonNav:hover {{
                background-color: {obtenir_couleur_accent_douce(0.18)};
            }}
            #enteteJour {{
                color: {PALETTE['texte_secondaire']};
                font-size: 12px;
                font-weight: 600;
            }}
            #celluleJour {{
                background-color: {PALETTE['carte']};
                border: 1px solid {PALETTE['bordure']};
                border-radius: 8px;
            }}
            #celluleJourAujourdhui {{
                background-color: {obtenir_couleur_accent_douce(0.16)};
                border: 1px solid {obtenir_couleur_accent()};
                border-radius: 8px;
            }}
            #celluleVide {{
                background-color: transparent;
                border: none;
            }}
            #numeroJour {{
                font-family: '{POLICE_TEXTE_DEMI}', sans-serif;
                font-size: 13px;
            }}
            #detailSommeil {{
                color: {PALETTE['texte_secondaire']};
                font-size: 11px;
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(12)

        barre_nav = QHBoxLayout()
        bouton_precedent = QPushButton("←  Mois précédent")
        bouton_precedent.setObjectName("boutonNav")
        bouton_precedent.setCursor(Qt.CursorShape.PointingHandCursor)
        bouton_precedent.clicked.connect(self._mois_precedent)

        self.titre_mois = QLabel()
        self.titre_mois.setObjectName("titreMois")
        self.titre_mois.setAlignment(Qt.AlignmentFlag.AlignCenter)

        bouton_suivant = QPushButton("Mois suivant  →")
        bouton_suivant.setObjectName("boutonNav")
        bouton_suivant.setCursor(Qt.CursorShape.PointingHandCursor)
        bouton_suivant.clicked.connect(self._mois_suivant)

        barre_nav.addWidget(bouton_precedent)
        barre_nav.addWidget(self.titre_mois, 1)
        barre_nav.addWidget(bouton_suivant)
        layout.addLayout(barre_nav)

        self.grille = QGridLayout()
        self.grille.setSpacing(6)
        layout.addLayout(self.grille, 1)

        self._construire_calendrier()

    def _mois_precedent(self):
        self.mois_affiche -= 1
        if self.mois_affiche < 1:
            self.mois_affiche = 12
            self.annee_affichee -= 1
        self._construire_calendrier()

    def _mois_suivant(self):
        self.mois_affiche += 1
        if self.mois_affiche > 12:
            self.mois_affiche = 1
            self.annee_affichee += 1
        self._construire_calendrier()

    def _donnees_du_mois(self):
        premier_jour = date(self.annee_affichee, self.mois_affiche, 1)
        dernier_num_jour = calendar.monthrange(self.annee_affichee, self.mois_affiche)[1]
        dernier_jour = date(self.annee_affichee, self.mois_affiche, dernier_num_jour)

        conn = connexion()
        cur = conn.cursor()
        if self.athlete_id is not None:
            cur.execute(
                "SELECT date, heure_coucher, heure_lever, duree_heures FROM sommeil "
                "WHERE athlete_id=? AND date >= ? AND date <= ?",
                (self.athlete_id, premier_jour.isoformat(), dernier_jour.isoformat()),
            )
        else:
            cur.execute(
                "SELECT date, heure_coucher, heure_lever, duree_heures FROM sommeil "
                "WHERE date >= ? AND date <= ?",
                (premier_jour.isoformat(), dernier_jour.isoformat()),
            )
        resultat = {}
        for jour_str, coucher, lever, duree in cur.fetchall():
            resultat[str(jour_str)[:10]] = (coucher, lever, duree)
        conn.close()
        return resultat

    def _construire_calendrier(self):
        while self.grille.count():
            item = self.grille.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

        self.titre_mois.setText(f"{NOMS_MOIS[self.mois_affiche - 1]} {self.annee_affichee}")

        for colonne, nom_jour in enumerate(NOMS_JOURS):
            label = QLabel(nom_jour)
            label.setObjectName("enteteJour")
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.grille.addWidget(label, 0, colonne)

        donnees = self._donnees_du_mois()
        aujourd_hui = date.today()

        semaines = calendar.monthcalendar(self.annee_affichee, self.mois_affiche)
        for num_semaine, semaine in enumerate(semaines, start=1):
            for colonne, jour_num in enumerate(semaine):
                if jour_num == 0:
                    cellule = QFrame()
                    cellule.setObjectName("celluleVide")
                    self.grille.addWidget(cellule, num_semaine, colonne)
                    continue

                jour_date = date(self.annee_affichee, self.mois_affiche, jour_num)
                est_aujourdhui = jour_date == aujourd_hui

                cellule = QFrame()
                cellule.setObjectName("celluleJourAujourdhui" if est_aujourdhui else "celluleJour")
                cellule.setMinimumHeight(70)
                cellule_layout = QVBoxLayout(cellule)
                cellule_layout.setContentsMargins(8, 6, 8, 6)
                cellule_layout.setSpacing(2)

                numero = QLabel(str(jour_num))
                numero.setObjectName("numeroJour")
                cellule_layout.addWidget(numero)

                info = donnees.get(jour_date.isoformat())
                if info:
                    coucher, lever, duree = info
                    texte = f"{coucher or '?'} → {lever or '?'}"
                    if duree:
                        texte += f"\n{duree:.1f} h"
                    detail = QLabel(texte)
                    detail.setObjectName("detailSommeil")
                    cellule_layout.addWidget(detail)

                cellule_layout.addStretch()
                self.grille.addWidget(cellule, num_semaine, colonne)

        for colonne in range(7):
            self.grille.setColumnStretch(colonne, 1)


def ouvrir_calendrier_sommeil(parent, athlete_id):
    dialogue = CalendrierSommeil(athlete_id, parent)
    dialogue.exec()
