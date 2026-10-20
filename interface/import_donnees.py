import csv
from data.completer_activites import completer_activite
import hashlib
import re
import sqlite3
from datetime import datetime
from pathlib import Path

from data.database import creer_base_de_donnees, obtenir_athletes
from interface.theme import (
    obtenir_couleur_accent, eclaircir, obtenir_couleur_accent_douce,
    charger_polices, PALETTE, POLICE_TITRE, POLICE_TEXTE,
)
from interface.date_utils import normaliser_vers_iso
from interface.import_garmin_json import parser_export_garmin_json
from interface.ecran_liste import configurer_table_redimensionnable

from PySide6.QtCore import Qt

from PySide6.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QFileDialog,
    QTableWidget,
    QTableWidgetItem,
    QFrame,
    QMessageBox,
    QComboBox,
    QProgressBar,
    QScrollArea,
)


class ImportDonnees(QMainWindow):

    def __init__(self, athlete_id_initial=None):
        super().__init__()

        charger_polices()

        self.setWindowTitle("TrailMaster Pro – Import des données")
        self.resize(1150, 750)
        self.setMinimumSize(950, 650)

        self.base_dir = Path(__file__).resolve().parent.parent
        self.db_path = self.base_dir / "data" / "trailmaster.db"

        self.creer_tables()

        self.construire_interface()

        if athlete_id_initial is not None:
            for i in range(self.combo_athlete_import.count()):
                if self.combo_athlete_import.itemData(i) == athlete_id_initial:
                    self.combo_athlete_import.setCurrentIndex(i)
                    break

    # ==========================================================
    # BASE DE DONNÉES
    # ==========================================================

    def connexion(self):
        return sqlite3.connect(self.db_path)

    def creer_tables(self):
        # Le schéma (tables "activites" et "importations" incluses) est
        # désormais centralisé dans data/database.py — voir creer_base_de_donnees().
        creer_base_de_donnees()

    # ==========================================================
    # INTERFACE
    # ==========================================================

    def construire_interface(self):

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

        # ------------------------------------------------------
        # TITRE
        # ------------------------------------------------------

        titre = QLabel("📥 Import des données")

        titre.setStyleSheet(f"""
            QLabel {{
                font-family: '{POLICE_TITRE}';
                font-size: 25px;
                font-weight: 700;
                color: {PALETTE['texte']};
            }}
        """)

        sous_titre = QLabel(
            "Importation et normalisation des activités Garmin et Strava"
        )

        sous_titre.setStyleSheet(f"""
            QLabel {{
                font-size: 13.5px;
                color: {PALETTE['texte_secondaire']};
            }}
        """)

        principal.addWidget(titre)
        principal.addWidget(sous_titre)

        # ------------------------------------------------------
        # ZONE IMPORT
        # ------------------------------------------------------

        zone_import = QFrame()

        zone_import.setStyleSheet(f"""
            QFrame {{
                background-color: {PALETTE['carte']};
                border: 1px solid {PALETTE['bordure']};
                border-radius: 14px;
            }}
        """)

        zone_layout = QHBoxLayout(zone_import)

        zone_layout.setContentsMargins(20, 20, 20, 20)
        zone_layout.setSpacing(15)

        label_source = QLabel("Source :")

        label_source.setStyleSheet(f"""
            QLabel {{
                color: {PALETTE['texte']};
                font-weight: 600;
            }}
        """)

        self.combo_source = QComboBox()

        self.combo_source.addItems([
            "Détection automatique",
            "Garmin",
            "Strava",
        ])

        label_athlete = QLabel("Athlète :")
        label_athlete.setStyleSheet(f"""
            QLabel {{
                color: {PALETTE['texte']};
                font-weight: 600;
            }}
        """)

        self.combo_athlete_import = QComboBox()
        self.athletes_import = obtenir_athletes()
        self.combo_athlete_import.addItem("Sélectionner...", None)
        for a in self.athletes_import:
            self.combo_athlete_import.addItem(f"{a[2]} {a[1]}", a[0])

        bouton_import = QPushButton("📂 Choisir un fichier")

        bouton_import.clicked.connect(
            self.choisir_fichier
        )

        zone_layout.addWidget(label_source)
        zone_layout.addWidget(self.combo_source)
        zone_layout.addWidget(label_athlete)
        zone_layout.addWidget(self.combo_athlete_import)
        zone_layout.addStretch()

        bouton_sante = QPushButton("🩺 Importer la santé Garmin")
        bouton_sante.setToolTip(
            "Sommeil, FC de repos, HRV, Body Battery, stress : choisis le dossier (ou le .zip) "
            "de ton export Garmin Connect."
        )
        bouton_sante.clicked.connect(self.importer_sante_garmin)
        zone_layout.addWidget(bouton_sante)
        zone_layout.addWidget(bouton_import)

        principal.addWidget(zone_import)

        # ------------------------------------------------------
        # STATISTIQUES
        # ------------------------------------------------------

        statistiques = QHBoxLayout()

        self.carte_total = self.creer_carte(
            "ACTIVITÉS LUES",
            "0"
        )

        self.carte_nouvelles = self.creer_carte(
            "NOUVELLES",
            "0"
        )

        self.carte_doublons = self.creer_carte(
            "DOUBLONS",
            "0"
        )

        self.carte_erreurs = self.creer_carte(
            "ERREURS",
            "0"
        )

        statistiques.addWidget(self.carte_total)
        statistiques.addWidget(self.carte_nouvelles)
        statistiques.addWidget(self.carte_doublons)
        statistiques.addWidget(self.carte_erreurs)

        principal.addLayout(statistiques)

        # ------------------------------------------------------
        # PROGRESSION
        # ------------------------------------------------------

        self.progression = QProgressBar()

        self.progression.setValue(0)

        self.progression.setVisible(False)

        principal.addWidget(self.progression)

        # ------------------------------------------------------
        # JOURNAL
        # ------------------------------------------------------

        label_journal = QLabel("Journal de l'import")

        label_journal.setStyleSheet(f"""
            QLabel {{
                font-family: '{POLICE_TITRE}';
                color: {PALETTE['texte']};
                font-size: 15px;
                font-weight: 700;
            }}
        """)

        principal.addWidget(label_journal)

        self.table = QTableWidget()

        self.table.setColumnCount(7)

        self.table.setHorizontalHeaderLabels([
            "Date",
            "Nom",
            "Type",
            "Distance",
            "D+",
            "Durée",
            "Source",
        ])

        self.table.setAlternatingRowColors(True)
        configurer_table_redimensionnable(self.table)

        principal.addWidget(self.table)

        # ------------------------------------------------------
        # STYLE
        # ------------------------------------------------------

        feuille_style = f"""
            QScrollBar:vertical, QScrollBar:horizontal {{
                background-color: transparent;
                width: 10px;
                height: 10px;
                margin: 0px;
            }}
            QScrollBar::handle:vertical, QScrollBar::handle:horizontal {{
                background-color: {PALETTE['bordure']};
                border-radius: 5px;
                min-height: 30px;
                min-width: 30px;
            }}
            QScrollBar::handle:vertical:hover, QScrollBar::handle:horizontal:hover {{
                background-color: #384048;
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical,
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
                height: 0px;
                width: 0px;
            }}
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical,
            QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{
                background: none;
            }}

            QMainWindow {{
                background-color: {PALETTE['fond']};
            }}

            QWidget {{
                font-family: '{POLICE_TEXTE}', 'Segoe UI', sans-serif;
            }}

            QTableWidget {{
                background-color: {PALETTE['carte']};
                color: {PALETTE['texte_att']};
                border: 1px solid {PALETTE['bordure']};
                border-radius: 12px;
                gridline-color: {PALETTE['bordure_douce']};
                alternate-background-color: {PALETTE['carte_haute']};
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

            QComboBox {{
                background-color: {PALETTE['carte_haute']};
                color: {PALETTE['texte']};
                border: 1px solid {PALETTE['bordure']};
                border-radius: 8px;
                padding: 7px;
            }}

            QComboBox QAbstractItemView {{
                background-color: {PALETTE['carte_haute']};
                color: {PALETTE['texte']};
                selection-background-color: {{ACCENT_COLOR}};
            }}

            QPushButton {{
                background-color: {{ACCENT_COLOR}};
                color: white;
                border: none;
                border-radius: 9px;
                padding: 9px 18px;
                font-weight: 600;
            }}

            QPushButton:hover {{
                background-color: {{ACCENT_HOVER}};
            }}

            QProgressBar {{
                background-color: {PALETTE['carte_haute']};
                border: none;
                border-radius: 5px;
                height: 12px;
                color: transparent;
            }}

            QProgressBar::chunk {{
                background-color: {{ACCENT_COLOR}};
                border-radius: 5px;
            }}
        """

        accent = obtenir_couleur_accent()
        self.setStyleSheet(
            feuille_style.replace("{ACCENT_COLOR}", accent).replace("{ACCENT_HOVER}", eclaircir(accent))
        )

    # ==========================================================
    # CARTES
    # ==========================================================

    def creer_carte(self, titre, valeur):

        carte = QFrame()

        carte.setStyleSheet(f"""
            QFrame {{
                background-color: {PALETTE['carte']};
                border: 1px solid {PALETTE['bordure']};
                border-radius: 14px;
            }}
        """)

        layout = QVBoxLayout(carte)

        label_titre = QLabel(titre)

        label_titre.setStyleSheet(f"""
            QLabel {{
                color: {PALETTE['texte_discret']};
                font-size: 11px;
                font-weight: 600;
            }}
        """)

        label_valeur = QLabel(valeur)

        label_valeur.setStyleSheet(f"""
            QLabel {{
                font-family: '{POLICE_TITRE}';
                color: {PALETTE['texte']};
                font-size: 24px;
                font-weight: 700;
            }}
        """)

        layout.addWidget(label_titre)
        layout.addWidget(label_valeur)

        carte.valeur = label_valeur

        return carte

    # ==========================================================
    # CHOIX DU FICHIER
    # ==========================================================

    def choisir_fichier(self):

        if self.combo_athlete_import.currentData() is None:
            QMessageBox.warning(
                self, "Athlète requis",
                "Sélectionnez l'athlète à qui rattacher ces activités avant d'importer."
            )
            return

        fichier, _ = QFileDialog.getOpenFileName(
            self,
            "Choisir un fichier d'activités",
            "",
            "Fichiers d'activités (*.csv *.CSV *.json);;"
            "Export Garmin JSON (*.json);;"
            "Fichiers CSV (*.csv *.CSV);;"
            "Tous les fichiers (*)"
        )

        if not fichier:
            return

        if fichier.lower().endswith(".json"):
            self.importer_json_garmin(fichier)
            return

        source = self.detecter_source(fichier)

        if self.combo_source.currentText() != "Détection automatique":
            source = self.combo_source.currentText()

        self.importer_csv(
            fichier,
            source
        )

    # ==========================================================
    # IMPORT DE LA SANTÉ QUOTIDIENNE GARMIN (sommeil, FC repos, HRV…)
    # ==========================================================

    def importer_sante_garmin(self):
        from data.import_sante_garmin import importer_sante, LIBELLES_MESURES

        athlete_id = self.combo_athlete_import.currentData()
        if athlete_id is None:
            QMessageBox.warning(
                self, "Athlète requis",
                "Sélectionnez l'athlète à qui rattacher ces données avant d'importer."
            )
            return

        boite = QMessageBox(self)
        boite.setWindowTitle("Santé Garmin")
        boite.setText(
            "Que veux-tu importer ?\n\n"
            "• le DOSSIER de ton export Garmin Connect (déjà dézippé), ou\n"
            "• le fichier .ZIP tel que reçu de Garmin."
        )
        b_dossier = boite.addButton("📁 Un dossier", QMessageBox.ButtonRole.AcceptRole)
        b_zip = boite.addButton("🗜 Un fichier .zip", QMessageBox.ButtonRole.AcceptRole)
        boite.addButton("Annuler", QMessageBox.ButtonRole.RejectRole)
        boite.exec()

        if boite.clickedButton() is b_dossier:
            source = QFileDialog.getExistingDirectory(self, "Dossier de l'export Garmin")
        elif boite.clickedButton() is b_zip:
            source, _ = QFileDialog.getOpenFileName(
                self, "Export Garmin (.zip)", "", "Archive zip (*.zip);;Tous les fichiers (*)"
            )
        else:
            return
        if not source:
            return

        try:
            bilan = importer_sante(athlete_id, source)
        except Exception as erreur:
            QMessageBox.critical(
                self, "Import impossible", f"Impossible de lire cet export :\n\n{erreur}"
            )
            return

        if not bilan["jours"]:
            QMessageBox.information(
                self, "Santé Garmin",
                f"Aucune donnée de santé reconnue ({bilan['fichiers']} fichier(s) examiné(s)).\n\n"
                "Sur Garmin Connect, demande l'export complet (« Exporter vos données »), "
                "puis choisis le dossier ou le .zip reçu. Les fichiers utiles ont un nom du "
                "genre « …sleepData.json » ou « UDSFile_….json »."
            )
            return

        lignes = [
            f"{bilan['jours']} jour(s) trouvé(s), du {bilan['premier']} au {bilan['dernier']}",
            f"✅ {bilan['ajoutes']} jour(s) ajouté(s), {bilan['completes']} complété(s)",
            "",
            "Mesures trouvées (nombre de jours) :",
        ]
        for cle, n in sorted(bilan["mesures"].items(), key=lambda kv: -kv[1]):
            lignes.append(f"  • {LIBELLES_MESURES.get(cle, cle)} : {n}")
        if bilan["sommeil_copies"] or bilan["signaux_copies"]:
            lignes.append("")
            lignes.append(
                f"Reprises dans l'indice de forme : {bilan['sommeil_copies']} nuit(s) de sommeil, "
                f"{bilan['signaux_copies']} jour(s) de HRV/stress."
            )
        QMessageBox.information(self, "Santé Garmin importée", "\n".join(lignes))

    # ==========================================================
    # IMPORT DEPUIS L'EXPORT NATIF GARMIN CONNECT (JSON)
    # ==========================================================
    # Format bien plus complet que le CSV : type d'activité réel,
    # durée réelle, dénivelé réel et fréquence cardiaque — voir
    # interface/import_garmin_json.py.

    def importer_json_garmin(self, fichier):

        athlete_id = self.combo_athlete_import.currentData()

        self.progression.setVisible(True)
        self.progression.setValue(0)
        self.table.setRowCount(0)

        total = 0
        nouvelles = 0
        doublons = 0
        erreurs = 0
        completees = 0

        try:
            activites = parser_export_garmin_json(fichier)

            if not activites:
                QMessageBox.warning(
                    self, "Import",
                    "Aucune activité reconnue dans ce fichier "
                    "(format attendu : export *_summarizedActivities.json de Garmin Connect)."
                )
                return

            conn = self.connexion()
            cur = conn.cursor()

            for index, activite in enumerate(activites):
                total += 1
                try:
                    cur.execute(
                        "SELECT id FROM activites WHERE empreinte = ?",
                        (activite["empreinte"],),
                    )
                    existante = cur.fetchone()
                    if existante:
                        doublons += 1
                        # Activité déjà connue : on récupère au passage les
                        # paramètres que les anciennes versions ignoraient.
                        if completer_activite(cur, existante[0], activite):
                            completees += 1
                    else:
                        cur.execute(
                            """
                            INSERT INTO activites (
                                athlete_id, date, nom, type, distance, denivele, duree,
                                vitesse_moyenne, allure_moyenne, frequence_cardiaque_moyenne,
                                frequence_cardiaque_max, calories, source, fichier_source,
                                identifiant_externe, empreinte, notes,
                                denivele_negatif, vitesse_max, allure_max,
                                cadence_moyenne, vo2max
                            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                            """,
                            (
                                athlete_id, activite["date"], activite["nom"], activite["type"],
                                activite["distance"], activite["denivele"], activite["duree"],
                                activite["vitesse_moyenne"], activite["allure_moyenne"],
                                activite["frequence_cardiaque_moyenne"], activite["frequence_cardiaque_max"],
                                activite["calories"], activite["source"], activite["fichier_source"],
                                activite["identifiant_externe"], activite["empreinte"], activite["notes"],
                                activite.get("denivele_negatif"), activite.get("vitesse_max"),
                                activite.get("allure_max"), activite.get("cadence_moyenne"),
                                activite.get("vo2max"),
                            ),
                        )
                        nouvelles += 1
                        # Paramètres avancés (effet d'entraînement, zones de FC…)
                        completer_activite(cur, cur.lastrowid, activite)

                        self.ajouter_ligne_tableau({
                            "date": activite["date"],
                            "nom": activite["nom"],
                            "type": activite["type"],
                            "distance": activite["distance"],
                            "denivele": activite["denivele"],
                            "duree": activite["duree"],
                            "source": activite["source"],
                        })

                except Exception:
                    erreurs += 1

                self.progression.setValue(int(((index + 1) / len(activites)) * 100))

            conn.commit()

            cur.execute(
                "INSERT INTO importations (fichier, source, total, nouvelles, doublons, erreurs) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (Path(fichier).name, "Garmin (export JSON)", total, nouvelles, doublons, erreurs),
            )
            conn.commit()
            conn.close()

            self.mettre_a_jour_statistiques(total, nouvelles, doublons, erreurs)
            self.progression.setValue(100)

            QMessageBox.information(
                self, "Import terminé",
                f"Import de l'export Garmin JSON terminé.\n\n"
                f"Activités lues : {total}\n"
                f"Nouvelles : {nouvelles}\n"
                f"Déjà connues : {doublons}\n"
                f"   dont complétées (D−, vitesse max, cadence, VO₂max, effet d'entraînement, zones de FC…) : {completees}\n"
                f"Erreurs : {erreurs}"
            )

        except Exception as erreur:
            QMessageBox.critical(
                self, "Erreur d'import",
                f"Impossible d'importer ce fichier JSON :\n\n{erreur}"
            )

        finally:
            self.progression.setVisible(False)

    # ==========================================================
    # DÉTECTION SOURCE
    # ==========================================================

    def detecter_source(self, fichier):

        nom = Path(fichier).name.lower()

        if "strava" in nom:
            return "Strava"

        if "garmin" in nom:
            return "Garmin"

        try:

            with open(
                fichier,
                "r",
                encoding="utf-8-sig",
                errors="ignore"
            ) as f:

                contenu = f.read(10000).lower()

            if "strava" in contenu:
                return "Strava"

            if "garmin" in contenu:
                return "Garmin"

        except Exception:
            pass

        return "Garmin"

    # ==========================================================
    # IMPORT CSV
    # ==========================================================

    def importer_csv(self, fichier, source):

        self.progression.setVisible(True)
        self.progression.setValue(0)

        total = 0
        nouvelles = 0
        doublons = 0
        erreurs = 0
        completees = 0

        self.table.setRowCount(0)

        try:

            with open(
                fichier,
                "r",
                encoding="utf-8-sig",
                errors="replace",
                newline=""
            ) as f:

                lecteur = csv.DictReader(f)

                lignes = list(lecteur)

            nombre_lignes = len(lignes)

            if nombre_lignes == 0:

                QMessageBox.warning(
                    self,
                    "Import",
                    "Le fichier ne contient aucune activité."
                )

                return

            conn = self.connexion()
            cur = conn.cursor()

            for index, ligne in enumerate(lignes):

                total += 1

                try:

                    activite = self.normaliser_activite(
                        ligne,
                        source,
                        fichier
                    )

                    empreinte = self.creer_empreinte(
                        activite
                    )

                    activite["empreinte"] = empreinte

                    cur.execute("""
                        SELECT id
                        FROM activites
                        WHERE empreinte = ?
                    """, (empreinte,))

                    existe = cur.fetchone()

                    if existe:

                        doublons += 1
                        if completer_activite(cur, existe[0], {
                            "frequence_cardiaque_moyenne": activite["fc_moyenne"],
                            "frequence_cardiaque_max": activite["fc_max"],
                            "calories": activite["calories"],
                            "vitesse_moyenne": activite["vitesse_moyenne"],
                            "allure_moyenne": activite["allure_moyenne"],
                            "denivele_negatif": activite.get("denivele_negatif"),
                            "vitesse_max": activite.get("vitesse_max"),
                            "allure_max": activite.get("allure_max"),
                            "cadence_moyenne": activite.get("cadence_moyenne"),
                        }):
                            completees += 1

                    else:

                        cur.execute("""
                            INSERT INTO activites (
                                athlete_id,
                                date,
                                nom,
                                type,
                                distance,
                                denivele,
                                duree,
                                vitesse_moyenne,
                                allure_moyenne,
                                frequence_cardiaque_moyenne,
                                frequence_cardiaque_max,
                                calories,
                                source,
                                fichier_source,
                                identifiant_externe,
                                empreinte,
                                notes,
                                denivele_negatif,
                                vitesse_max,
                                allure_max,
                                cadence_moyenne
                            )
                            VALUES (
                                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                            )
                        """, (
                            activite["athlete_id"],
                            activite["date"],
                            activite["nom"],
                            activite["type"],
                            activite["distance"],
                            activite["denivele"],
                            activite["duree"],
                            activite["vitesse_moyenne"],
                            activite["allure_moyenne"],
                            activite["fc_moyenne"],
                            activite["fc_max"],
                            activite["calories"],
                            activite["source"],
                            activite["fichier_source"],
                            activite["identifiant_externe"],
                            activite["empreinte"],
                            activite["notes"],
                            activite.get("denivele_negatif"),
                            activite.get("vitesse_max"),
                            activite.get("allure_max"),
                            activite.get("cadence_moyenne"),
                        ))

                        nouvelles += 1

                        self.ajouter_ligne_tableau(
                            activite
                        )

                except Exception:
                    erreurs += 1

                progression = int(
                    ((index + 1) / nombre_lignes) * 100
                )

                self.progression.setValue(
                    progression
                )

            conn.commit()

            # --------------------------------------------------
            # HISTORIQUE DE L'IMPORT
            # --------------------------------------------------

            cur.execute("""
                INSERT INTO importations (
                    fichier,
                    source,
                    total,
                    nouvelles,
                    doublons,
                    erreurs
                )
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                Path(fichier).name,
                source,
                total,
                nouvelles,
                doublons,
                erreurs,
            ))

            conn.commit()
            conn.close()

            self.mettre_a_jour_statistiques(
                total,
                nouvelles,
                doublons,
                erreurs
            )

            self.progression.setValue(100)

            QMessageBox.information(
                self,
                "Import terminé",
                f"Import {source} terminé.\n\n"
                f"Activités lues : {total}\n"
                f"Nouvelles : {nouvelles}\n"
                f"Déjà connues : {doublons}\n"
                f"   dont complétées avec les paramètres manquants : {completees}\n"
                f"Erreurs : {erreurs}"
            )

        except Exception as erreur:

            QMessageBox.critical(
                self,
                "Erreur d'import",
                f"Impossible d'importer le fichier :\n\n{erreur}"
            )

        finally:

            self.progression.setVisible(False)

    # ==========================================================
    # NORMALISATION
    # ==========================================================

    def normaliser_activite(
        self,
        ligne,
        source,
        fichier
    ):

        def trouver(*noms):

            for nom in noms:

                for cle, valeur in ligne.items():

                    if cle is None:
                        continue

                    cle_normalisee = self.normaliser_nom(
                        cle
                    )

                    nom_normalise = self.normaliser_nom(
                        nom
                    )

                    if cle_normalisee == nom_normalise:

                        return valeur

            return ""

        date_brute = trouver(
            "Activity Date",
            "Date",
            "Date de l'activité",
            "Start Time",
            "Start Date"
        )

        date = self.normaliser_date(
            date_brute
        )

        nom = trouver(
            "Activity Name",
            "Activity",
            "Nom",
            "Name",
            "Title"
        )

        type_brut = trouver(
            "Activity Type",
            "Type",
            "Sport",
            "Activity"
        )

        type_activite = self.normaliser_type(
            type_brut
        )

        distance_brute = trouver(
            "Distance",
            "Distance (km)",
            "Distance (mi)"
        )

        distance = self.normaliser_distance(
            distance_brute,
            source,
            ligne
        )

        denivele_brut = trouver(
            "Elevation Gain",
            "Elevation Gain (m)",
            "Dénivelé",
            "D+",
            "Total Ascent"
        )

        denivele = self.nombre(
            denivele_brut
        )

        duree_brute = trouver(
            "Moving Time",
            "Elapsed Time",
            "Time",
            "Duration",
            "Durée"
        )

        duree = self.normaliser_duree(
            duree_brute
        )

        calories = self.nombre(
            trouver(
                "Calories",
                "Calories Burned"
            )
        )

        fc_moyenne = self.entier(
            trouver(
                "Average Heart Rate",
                "Avg HR",
                "Heart Rate",
                "FC moyenne"
            )
        )

        fc_max = self.entier(
            trouver(
                "Max Heart Rate",
                "Maximum Heart Rate",
                "FC max"
            )
        )

        vitesse = self.nombre(
            trouver(
                "Average Speed",
                "Avg Speed",
                "Vitesse moyenne"
            )
        )

        allure = self.nombre(
            trouver(
                "Average Pace",
                "Pace",
                "Allure moyenne"
            )
        )

        denivele_neg = self.nombre(
            trouver(
                "Elevation Loss", "Total Descent", "Descente totale",
                "Dénivelé négatif", "D-"
            )
        )

        vitesse_max_brute = self.nombre(
            trouver("Max Speed", "Vitesse maximale", "Vitesse max", "Max. Speed")
        )
        vitesse_max = None
        if vitesse_max_brute:
            # Les exports Strava donnent la vitesse max en m/s,
            # ceux de Garmin en km/h.
            vitesse_max = round(
                vitesse_max_brute * 3.6 if "strava" in str(source).lower() else vitesse_max_brute, 2
            )
            if not (0 < vitesse_max <= 80):
                vitesse_max = None
        allure_max = round(60 / vitesse_max, 2) if vitesse_max else None

        cadence = self.nombre(
            trouver(
                "Avg Run Cadence", "Average Cadence", "Cadence moyenne",
                "Cadence de course moyenne", "Avg Cadence"
            )
        )

        identifiant = trouver(
            "Activity ID",
            "Activity Id",
            "ID",
            "Activity ID"
        )

        return {
            "athlete_id": self.combo_athlete_import.currentData(),
            "date": date,
            "nom": nom,
            "type": type_activite,
            "distance": distance,
            "denivele": int(denivele),
            "duree": duree,
            "vitesse_moyenne": vitesse,
            "allure_moyenne": allure,
            "fc_moyenne": fc_moyenne,
            "fc_max": fc_max,
            "calories": calories,
            "source": source,
            "fichier_source": Path(fichier).name,
            "identifiant_externe": identifiant,
            "empreinte": "",
            "notes": "",
            "denivele_negatif": int(denivele_neg) if denivele_neg else None,
            "vitesse_max": vitesse_max,
            "allure_max": allure_max,
            "cadence_moyenne": (
                round(cadence * 2 if (cadence and cadence < 120 and type_activite in ("Trail", "Course")) else cadence)
                if cadence else None
            ),
        }

    # ==========================================================
    # NORMALISATION DES NOMS
    # ==========================================================

    def normaliser_nom(self, texte):

        texte = str(texte).strip().lower()

        texte = (
            texte.replace("é", "e")
            .replace("è", "e")
            .replace("ê", "e")
            .replace("à", "a")
            .replace("ù", "u")
            .replace("ç", "c")
        )

        texte = re.sub(
            r"[^a-z0-9]+",
            " ",
            texte
        )

        return texte.strip()

    # ==========================================================
    # DATE
    # ==========================================================

    def normaliser_date(self, valeur):
        # Délègue à interface/date_utils.py, qui gère en plus le format
        # français avec abréviations de mois (ex. "9 sept. 2022, 03:58:44")
        # — c'est ce format qui n'était pas reconnu ici auparavant et qui
        # faisait que les dates étaient stockées telles quelles, non triables.
        return normaliser_vers_iso(valeur)

    # ==========================================================
    # DISTANCE
    # ==========================================================

    def normaliser_distance(
        self,
        valeur,
        source,
        ligne
    ):

        if not valeur:
            return 0

        texte = str(valeur).strip()

        try:

            nombre = float(
                texte.replace(",", ".")
            )

        except ValueError:

            return 0

        # L'export Strava (activities.csv) donne la distance directement
        # en kilomètres, pas en mètres — confirmé par le parseur Strava
        # déjà validé sur de vrais fichiers exportés (voir import_strava.py).
        if source == "Strava":
            return nombre

        # Si le fichier indique explicitement les mètres.
        for cle in ligne.keys():

            cle_normalisee = self.normaliser_nom(
                cle
            )

            if "distance" in cle_normalisee and "m" in cle_normalisee:
                if "mi" not in cle_normalisee:
                    return nombre / 1000

        # Garmin : généralement déjà en kilomètres
        return nombre

    # ==========================================================
    # DURÉE
    # ==========================================================

    def normaliser_duree(self, valeur):

        if not valeur:
            return 0

        texte = str(valeur).strip()

        # secondes pures
        if texte.isdigit():

            return int(texte)

        # HH:MM:SS
        morceaux = texte.split(":")

        try:

            if len(morceaux) == 3:

                heures = int(morceaux[0])
                minutes = int(morceaux[1])
                secondes = int(
                    float(morceaux[2])
                )

                return (
                    heures * 3600
                    + minutes * 60
                    + secondes
                )

            if len(morceaux) == 2:

                minutes = int(morceaux[0])
                secondes = int(
                    float(morceaux[1])
                )

                return (
                    minutes * 60
                    + secondes
                )

        except ValueError:
            pass

        return 0

    # ==========================================================
    # NOMBRE
    # ==========================================================

    def nombre(self, valeur):

        if valeur is None:
            return 0

        texte = str(valeur).strip()

        if not texte:
            return 0

        texte = (
            texte.replace(",", ".")
            .replace("km", "")
            .replace("m", "")
            .strip()
        )

        try:
            return float(texte)
        except ValueError:
            return 0

    def entier(self, valeur):

        return int(
            self.nombre(valeur)
        )

    # ==========================================================
    # TYPE ACTIVITÉ
    # ==========================================================

    def normaliser_type(self, valeur):

        texte = str(valeur).lower()

        if "trail" in texte:
            return "Trail"

        if "run" in texte or "course" in texte:

            if "trail" in texte:
                return "Trail"

            return "Course"

        if "mountain bike" in texte:
            return "VTT"

        if "vtt" in texte:
            return "VTT"

        if "cycling" in texte or "bike" in texte or "ride" in texte:
            return "Vélo"

        if "hike" in texte or "randonn" in texte:
            return "Randonnée"

        if "walk" in texte:
            return "Marche"

        if "swim" in texte or "natation" in texte:
            return "Natation"

        return "Autre"

    # ==========================================================
    # EMPREINTE ANTI-DOUBLON
    # ==========================================================

    def creer_empreinte(self, activite):

        texte = "|".join([
            activite["date"],
            activite["type"],
            f"{activite['distance']:.3f}",
            str(activite["denivele"]),
            str(activite["duree"]),
        ])

        return hashlib.sha256(
            texte.encode("utf-8")
        ).hexdigest()

    # ==========================================================
    # TABLEAU
    # ==========================================================

    def ajouter_ligne_tableau(
        self,
        activite
    ):

        ligne = self.table.rowCount()

        self.table.insertRow(
            ligne
        )

        duree = activite["duree"]

        heures = duree // 3600
        minutes = (duree % 3600) // 60

        valeurs = [
            activite["date"],
            activite["nom"],
            activite["type"],
            f"{activite['distance']:.2f} km",
            f"{activite['denivele']} m",
            f"{heures}h {minutes:02d}",
            activite["source"],
        ]

        for colonne, valeur in enumerate(valeurs):

            self.table.setItem(
                ligne,
                colonne,
                QTableWidgetItem(
                    str(valeur)
                )
            )

        self.table.resizeColumnsToContents()

    # ==========================================================
    # STATISTIQUES
    # ==========================================================

    def mettre_a_jour_statistiques(
        self,
        total,
        nouvelles,
        doublons,
        erreurs
    ):

        self.carte_total.valeur.setText(
            str(total)
        )

        self.carte_nouvelles.valeur.setText(
            str(nouvelles)
        )

        self.carte_doublons.valeur.setText(
            str(doublons)
        )

        self.carte_erreurs.valeur.setText(
            str(erreurs)
        )