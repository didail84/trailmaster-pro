from PySide6.QtGui import QPixmap
from PySide6.QtCore import Qt

from PySide6.QtWidgets import (
    QMainWindow,
    QWidget,
    QHBoxLayout,
    QVBoxLayout,
    QLabel,
    QPushButton,
    QFrame,
    QLineEdit,
    QSpinBox,
    QDoubleSpinBox,
    QComboBox,
    QFormLayout,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QMessageBox,
    QAbstractItemView,
    QFileDialog,
)

from data.database import ajouter_athlete, definir_photo_athlete, connexion
from interface.photo_athlete import enregistrer_photo_athlete, chemin_photo_absolu, pixmap_circulaire
from interface.ecran_liste import configurer_table_redimensionnable
from interface.theme import (
    charger_polices, obtenir_couleur_accent, eclaircir, PALETTE,
    POLICE_TITRE, POLICE_TEXTE,
)


class Athletes(QMainWindow):

    def __init__(self, athlete_id_initial=None):
        # athlete_id_initial n'est pas utilisé ici (l'écran liste tous les
        # athlètes) — accepté pour rester compatible avec ConteneurOnglets,
        # qui instancie chaque onglet de la même façon.
        super().__init__()

        charger_polices()
        accent = obtenir_couleur_accent()
        accent_survol = eclaircir(accent)

        self.resize(1200, 800)
        self.setMinimumSize(950, 650)
        self.setWindowTitle("TrailMaster Pro - Athlètes")
        self._athlete_en_modification = None

        central = QWidget()
        self.setCentralWidget(central)

        layout_principal = QHBoxLayout(central)
        layout_principal.setContentsMargins(0, 0, 0, 0)
        layout_principal.setSpacing(0)

        menu = QFrame()
        menu.setFixedWidth(230)
        menu.setStyleSheet(f"QFrame {{ background: {PALETTE['fond_secondaire']}; border-right: 1px solid {PALETTE['bordure']}; }}")
        layout_principal.addWidget(menu)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        contenu = QWidget()
        contenu.setStyleSheet(f"""
            QWidget {{
                background-color: {PALETTE['fond']};
                color: {PALETTE['texte']};
                font-family: '{POLICE_TEXTE}', 'Segoe UI', sans-serif;
            }}
            QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
                background-color: {PALETTE['carte_haute']};
                border: 1px solid {PALETTE['bordure']};
                border-radius: 8px;
                padding: 8px;
                color: {PALETTE['texte']};
                min-height: 22px;
            }}
            QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {{
                border: 1px solid {accent};
            }}
            QLabel {{ color: {PALETTE['texte_att']}; }}
            QTableWidget {{
                background-color: {PALETTE['carte']};
                color: {PALETTE['texte_att']};
                border: 1px solid {PALETTE['bordure']};
                border-radius: 12px;
                gridline-color: {PALETTE['bordure_douce']};
            }}
            QHeaderView::section {{
                background-color: {PALETTE['carte_haute']};
                color: {PALETTE['texte_discret']};
                padding: 8px 6px;
                border: none;
                border-bottom: 1px solid {PALETTE['bordure']};
                font-weight: 600;
                font-size: 11.5px;
            }}
            QPushButton {{
                background-color: {PALETTE['carte_haute']};
                color: {PALETTE['texte_secondaire']};
                border: 1px solid {PALETTE['bordure']};
                border-radius: 7px;
                padding: 5px 9px;
            }}
            QPushButton:hover {{
                background-color: {PALETTE['bordure']};
                color: {PALETTE['texte']};
            }}
        """)
        scroll.setWidget(contenu)
        layout_principal.addWidget(scroll)

        self.contenu_layout = QVBoxLayout(contenu)
        self.contenu_layout.setContentsMargins(40, 35, 40, 35)
        self.contenu_layout.setSpacing(20)

        titre = QLabel("Athlètes")
        titre.setStyleSheet(
            f"font-family: '{POLICE_TITRE}'; font-size: 25px; font-weight: 700; color: {PALETTE['texte']};"
        )
        sous_titre = QLabel(
            "Création et gestion des profils sportifs TrailMaster Pro."
        )
        sous_titre.setStyleSheet(f"color: {PALETTE['texte_secondaire']}; font-size: 13.5px;")

        self.contenu_layout.addWidget(titre)
        self.contenu_layout.addWidget(sous_titre)
        self.contenu_layout.addSpacing(20)

        carte = QFrame()
        carte.setStyleSheet(f"""
            QFrame {{
                background-color: {PALETTE['carte']};
                border: 1px solid {PALETTE['bordure']};
                border-radius: 14px;
            }}
        """)
        formulaire = QFormLayout(carte)
        formulaire.setContentsMargins(30, 30, 30, 30)
        formulaire.setSpacing(15)

        self._photo_temp_path = None

        ligne_photo = QHBoxLayout()
        self.apercu_photo = QLabel("Aucune\nphoto")
        self.apercu_photo.setFixedSize(70, 70)
        self.apercu_photo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.apercu_photo.setStyleSheet(f"""
            QLabel {{
                background-color: {PALETTE['carte_haute']};
                border: 1px solid {PALETTE['bordure']};
                border-radius: 35px;
                color: {PALETTE['texte_discret']};
                font-size: 11px;
            }}
        """)
        self.apercu_photo.setScaledContents(True)

        bouton_photo = QPushButton("📷 Choisir une photo")
        bouton_photo.clicked.connect(self.choisir_photo)

        ligne_photo.addWidget(self.apercu_photo)
        ligne_photo.addWidget(bouton_photo)
        ligne_photo.addStretch()
        formulaire.addRow("Photo :", ligne_photo)

        self.nom = QLineEdit()
        self.prenom = QLineEdit()

        self.age = QSpinBox()
        self.age.setRange(5, 100)
        self.age.setValue(18)

        self.sexe = QComboBox()
        self.sexe.addItems(["Homme", "Femme", "Autre"])

        self.taille = QSpinBox()
        self.taille.setRange(100, 230)
        self.taille.setValue(170)
        self.taille.setSuffix(" cm")

        self.poids = QDoubleSpinBox()
        self.poids.setRange(20, 250)
        self.poids.setValue(70)
        self.poids.setSuffix(" kg")

        self.fc_repos = QSpinBox()
        self.fc_repos.setRange(30, 120)
        self.fc_repos.setValue(60)
        self.fc_repos.setSuffix(" bpm")

        self.fc_max = QSpinBox()
        self.fc_max.setRange(100, 230)
        self.fc_max.setValue(180)
        self.fc_max.setSuffix(" bpm")

        self.fc_seuil = QSpinBox()
        self.fc_seuil.setRange(80, 220)
        self.fc_seuil.setValue(160)
        self.fc_seuil.setSuffix(" bpm")

        self.vma = QDoubleSpinBox()
        self.vma.setRange(5, 30)
        self.vma.setValue(12)
        self.vma.setSuffix(" km/h")

        self.vo2max = QDoubleSpinBox()
        self.vo2max.setRange(10, 100)
        self.vo2max.setValue(40)
        self.vo2max.setSuffix(" ml/kg/min")

        self.niveau = QComboBox()
        self.niveau.addItems([
            "Débutant", "Loisir", "Intermédiaire",
            "Confirmé", "Compétiteur", "Élite"
        ])

        for label, widget in [
            ("Nom :", self.nom),
            ("Prénom :", self.prenom),
            ("Âge :", self.age),
            ("Sexe :", self.sexe),
            ("Taille :", self.taille),
            ("Poids :", self.poids),
            ("FC repos :", self.fc_repos),
            ("FC maximale :", self.fc_max),
            ("FC seuil :", self.fc_seuil),
            ("VMA :", self.vma),
            ("VO₂max :", self.vo2max),
            ("Niveau :", self.niveau),
        ]:
            formulaire.addRow(label, widget)

        self.contenu_layout.addWidget(carte)

        self.bouton_enregistrer = QPushButton("💾  ENREGISTRER L'ATHLÈTE")
        self.bouton_enregistrer.setFixedHeight(50)
        self.bouton_enregistrer.setStyleSheet(f"""
            QPushButton {{
                background-color: {accent};
                color: white;
                border: none;
                border-radius: 9px;
                font-size: 14px;
                font-weight: 600;
            }}
            QPushButton:hover {{ background-color: {accent_survol}; }}
        """)
        self.bouton_enregistrer.clicked.connect(self.enregistrer_athlete)
        self.contenu_layout.addWidget(self.bouton_enregistrer)

        titre_liste = QLabel("Athlètes enregistrés")
        titre_liste.setStyleSheet(f"""
            font-family: '{POLICE_TITRE}';
            color: {PALETTE['texte']};
            font-size: 17px;
            font-weight: 700;
            margin-top: 25px;
        """)
        self.contenu_layout.addWidget(titre_liste)

        self.table_athletes = QTableWidget()
        self.table_athletes.setColumnCount(13)
        self.table_athletes.setHorizontalHeaderLabels([
            "ID", "Nom", "Prénom", "Âge", "Sexe", "Taille", "Poids",
            "FC repos", "VMA", "Niveau", "Voir", "Modifier", "Supprimer"
        ])
        configurer_table_redimensionnable(self.table_athletes)
        self.table_athletes.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.table_athletes.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self.table_athletes.setColumnHidden(0, True)
        self.contenu_layout.addWidget(self.table_athletes)

        self.charger_athletes()

    def charger_athletes(self):
        conn = None
        try:
            conn = connexion()
            cur = conn.cursor()
            cur.execute("""
                SELECT id, nom, prenom, age, sexe, taille, poids,
                       fc_repos, vma, niveau
                FROM athletes
                ORDER BY id DESC
            """)
            athletes = cur.fetchall()

            self.table_athletes.setRowCount(len(athletes))

            for ligne, athlete in enumerate(athletes):
                for colonne, valeur in enumerate(athlete):
                    self.table_athletes.setItem(
                        ligne, colonne, QTableWidgetItem(str(valeur))
                    )

                athlete_id = athlete[0]

                voir = QPushButton("👁 Voir")
                voir.clicked.connect(
                    lambda checked=False, aid=athlete_id: self.voir_fiche(aid)
                )

                modifier = QPushButton("✏️ Modifier")
                modifier.clicked.connect(
                    lambda checked=False, aid=athlete_id:
                    self.modifier_athlete(aid)
                )

                supprimer = QPushButton("🗑️ Supprimer")
                supprimer.clicked.connect(
                    lambda checked=False, aid=athlete_id:
                    self.supprimer_athlete(aid)
                )

                self.table_athletes.setCellWidget(ligne, 10, voir)
                self.table_athletes.setCellWidget(ligne, 11, modifier)
                self.table_athletes.setCellWidget(ligne, 12, supprimer)

            self.table_athletes.resizeColumnsToContents()

        except Exception as e:
            QMessageBox.critical(
                self, "Erreur",
                f"Impossible de charger les athlètes.\n\n{e}"
            )
        finally:
            if conn is not None:
                conn.close()

    def enregistrer_athlete(self):
        nom = self.nom.text().strip()
        prenom = self.prenom.text().strip()

        if not nom or not prenom:
            QMessageBox.warning(
                self, "Informations manquantes",
                "Le nom et le prénom sont obligatoires."
            )
            return

        try:
            nouvel_id = ajouter_athlete(
                nom, prenom, self.age.value(), self.sexe.currentText(),
                self.taille.value(), self.poids.value(),
                self.fc_repos.value(), self.fc_max.value(),
                self.fc_seuil.value(), self.vma.value(),
                self.vo2max.value(), self.niveau.currentText()
            )

            if self._photo_temp_path and nouvel_id:
                enregistrer_photo_athlete(nouvel_id, self._photo_temp_path)

            self.charger_athletes()
            self.reinitialiser_formulaire()

            QMessageBox.information(
                self, "Athlète enregistré",
                f"{prenom} {nom} a été enregistré avec succès."
            )
        except Exception as e:
            QMessageBox.critical(
                self, "Erreur d'enregistrement",
                f"Impossible d'enregistrer l'athlète.\n\n{e}"
            )

    def voir_fiche(self, athlete_id):
        athlete = self._get_athlete(athlete_id)
        if not athlete:
            QMessageBox.warning(
                self, "Athlète introuvable",
                "Cet athlète n'existe plus dans la base de données."
            )
            self.charger_athletes()
            return

        (
            _, nom, prenom, age, sexe, taille, poids,
            fc_repos, fc_max, fc_seuil, vma, vo2max, niveau, photo_path
        ) = athlete

        texte = (
            f"<h2>👤 {prenom} {nom}</h2>"
            f"<b>Âge :</b> {age} ans<br>"
            f"<b>Sexe :</b> {sexe}<br>"
            f"<b>Taille :</b> {taille} cm<br>"
            f"<b>Poids :</b> {poids} kg<br><br>"
            f"<b>FC repos :</b> {fc_repos} bpm<br>"
            f"<b>FC maximale :</b> {fc_max} bpm<br>"
            f"<b>FC seuil :</b> {fc_seuil} bpm<br>"
            f"<b>VMA :</b> {vma} km/h<br>"
            f"<b>VO₂max :</b> {vo2max} ml/kg/min<br>"
            f"<b>Niveau :</b> {niveau}"
        )
        QMessageBox.information(self, "Fiche athlète", texte)

    def modifier_athlete(self, athlete_id):
        athlete = self._get_athlete(athlete_id)
        if not athlete:
            QMessageBox.warning(
                self, "Athlète introuvable",
                "Cet athlète n'existe plus dans la base de données."
            )
            self.charger_athletes()
            return

        (
            aid, nom, prenom, age, sexe, taille, poids,
            fc_repos, fc_max, fc_seuil, vma, vo2max, niveau, photo_path
        ) = athlete

        self._athlete_en_modification = aid
        self.nom.setText(nom)
        self.prenom.setText(prenom)
        self.age.setValue(age)
        self.sexe.setCurrentText(sexe)
        self.taille.setValue(taille)
        self.poids.setValue(poids)
        self.fc_repos.setValue(fc_repos)
        self.fc_max.setValue(fc_max)
        self.fc_seuil.setValue(fc_seuil)
        self.vma.setValue(vma)
        self.vo2max.setValue(vo2max)
        self.niveau.setCurrentText(niveau)

        # La photo déjà enregistrée (s'il y en a une) s'affiche tout de
        # suite dans l'aperçu — _photo_temp_path reste vide tant que la
        # personne n'en choisit pas une nouvelle, pour ne pas y toucher
        # si elle modifie juste d'autres champs.
        self._photo_temp_path = None
        pixmap_existant = pixmap_circulaire(photo_path, taille=70)
        if pixmap_existant:
            self.apercu_photo.setPixmap(pixmap_existant)
            self.apercu_photo.setText("")
        else:
            self.apercu_photo.setPixmap(QPixmap())
            self.apercu_photo.setText("Aucune\nphoto")

        try:
            self.bouton_enregistrer.clicked.disconnect()
        except (TypeError, RuntimeError):
            pass
        self.bouton_enregistrer.setText("💾  ENREGISTRER LES MODIFICATIONS")
        self.bouton_enregistrer.clicked.connect(self.enregistrer_modification)
        self.nom.setFocus()

    def enregistrer_modification(self):
        athlete_id = self._athlete_en_modification
        if athlete_id is None:
            self.enregistrer_athlete()
            return

        nom = self.nom.text().strip()
        prenom = self.prenom.text().strip()
        if not nom or not prenom:
            QMessageBox.warning(
                self, "Informations manquantes",
                "Le nom et le prénom sont obligatoires."
            )
            return

        conn = None
        try:
            conn = connexion()
            cur = conn.cursor()
            cur.execute("""
                UPDATE athletes
                SET nom=?, prenom=?, age=?, sexe=?, taille=?, poids=?,
                    fc_repos=?, fc_max=?, fc_seuil=?, vma=?, vo2max=?, niveau=?
                WHERE id=?
            """, (
                nom, prenom, self.age.value(), self.sexe.currentText(),
                self.taille.value(), self.poids.value(),
                self.fc_repos.value(), self.fc_max.value(),
                self.fc_seuil.value(), self.vma.value(),
                self.vo2max.value(), self.niveau.currentText(), athlete_id
            ))
            conn.commit()

            if self._photo_temp_path:
                enregistrer_photo_athlete(athlete_id, self._photo_temp_path)

            self._athlete_en_modification = None
            self.remettre_bouton_enregistrement()
            self.charger_athletes()
            self.reinitialiser_formulaire()

            QMessageBox.information(
                self, "Modification enregistrée",
                f"{prenom} {nom} a été modifié avec succès."
            )
        except Exception as e:
            QMessageBox.critical(
                self, "Erreur de modification",
                f"Impossible de modifier l'athlète.\n\n{e}"
            )
        finally:
            if conn is not None:
                conn.close()

    def supprimer_athlete(self, athlete_id):
        athlete = self._get_athlete(athlete_id)
        if not athlete:
            QMessageBox.warning(
                self, "Athlète introuvable",
                "Cet athlète n'existe plus dans la base de données."
            )
            self.charger_athletes()
            return

        nom, prenom = athlete[1], athlete[2]

        confirmation = QMessageBox.question(
            self,
            "Confirmer la suppression",
            f"Voulez-vous vraiment supprimer {prenom} {nom} ?\n\n"
            "Cette action est irréversible.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if confirmation != QMessageBox.StandardButton.Yes:
            return

        conn = None
        try:
            conn = connexion()
            cur = conn.cursor()
            cur.execute("DELETE FROM athletes WHERE id=?", (athlete_id,))
            conn.commit()

            self.charger_athletes()

            QMessageBox.information(
                self, "Athlète supprimé",
                f"{prenom} {nom} a été supprimé."
            )
        except Exception as e:
            QMessageBox.critical(
                self, "Erreur de suppression",
                f"Impossible de supprimer l'athlète.\n\n{e}"
            )
        finally:
            if conn is not None:
                conn.close()

    def _get_athlete(self, athlete_id):
        conn = None
        try:
            conn = connexion()
            cur = conn.cursor()
            cur.execute("""
                SELECT id, nom, prenom, age, sexe, taille, poids,
                       fc_repos, fc_max, fc_seuil, vma, vo2max, niveau, photo_path
                FROM athletes
                WHERE id=?
            """, (athlete_id,))
            return cur.fetchone()
        finally:
            if conn is not None:
                conn.close()

    def remettre_bouton_enregistrement(self):
        try:
            self.bouton_enregistrer.clicked.disconnect()
        except (TypeError, RuntimeError):
            pass
        self.bouton_enregistrer.setText("💾  ENREGISTRER L'ATHLÈTE")
        self.bouton_enregistrer.clicked.connect(self.enregistrer_athlete)

    def reinitialiser_formulaire(self):
        self.nom.clear()
        self.prenom.clear()
        self.age.setValue(18)
        self.taille.setValue(170)
        self.poids.setValue(70)
        self.fc_repos.setValue(60)
        self.fc_max.setValue(180)
        self.fc_seuil.setValue(160)
        self.vma.setValue(12)
        self.vo2max.setValue(40)
        self.sexe.setCurrentIndex(0)
        self.niveau.setCurrentIndex(0)
        self._photo_temp_path = None
        self.apercu_photo.setPixmap(QPixmap())
        self.apercu_photo.setText("Aucune\nphoto")

    def choisir_photo(self):
        chemin, _ = QFileDialog.getOpenFileName(
            self, "Choisir une photo", "", "Images (*.png *.jpg *.jpeg)"
        )
        if not chemin:
            return

        self._photo_temp_path = chemin
        pixmap = QPixmap(chemin)
        self.apercu_photo.setPixmap(pixmap)
        self.apercu_photo.setText("")
