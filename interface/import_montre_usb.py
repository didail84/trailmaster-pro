"""
Écran « Import depuis la montre USB ». La logique (recherche des .FIT,
correspondance avec les sorties, import et complétion) est dans
noyau/imports/montre_usb.py.
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QComboBox,
    QPushButton,
    QLineEdit,
    QFileDialog,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QCheckBox,
    QFrame,
    QScrollArea,
    QMessageBox,
)

from data.database import connexion, creer_base_de_donnees, obtenir_athletes
from interface.ecran_liste import obtenir_style_ecran, configurer_table_redimensionnable
from noyau.traces.fit_utils import parser_fit, parser_resume_session_fit
from noyau.traces.doublons import FENETRE_TEMPS_MINUTES
from noyau.outils.date_utils import parser_date_flexible
from noyau.imports.montre_usb import (  # noqa: F401
    SOUS_DOSSIERS_ACTIVITE_CANDIDATS, CHAMPS_COMPLETABLES,
    _lister_fit, trouver_fichiers_fit, _fit_datetime_vers_local, _trouver_activite_correspondante,
    _champs_manquants, analyser_dossier, _invalider_cache, importer_nouveau, completer_activite,
)


# ------------------------------------------------------------------
# ÉCRAN
# ------------------------------------------------------------------

LIBELLE_STATUT = {
    "nouveau": "🆕 Nouvelle activité",
    "a_completer": "🧩 À compléter",
    "complet": "✅ Déjà complet",
    "ignore": "⏭️ Ignoré",
}


class ImporterMontreUSB(QMainWindow):

    def __init__(self, athlete_id_initial=None):
        super().__init__()

        creer_base_de_donnees()

        self.setWindowTitle("TrailMaster Pro – Montre Garmin (USB)")
        self.resize(1250, 800)
        self.setMinimumSize(1000, 650)

        self.dossier_courant = None
        self.resultats_courants = []
        self.cases = []

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

        titre = QLabel("⌚ Montre Garmin (USB)")
        titre.setObjectName("titrePage")
        sous_titre = QLabel(
            "Branche ta montre en USB (elle apparaît comme une clé USB classique), choisis son "
            "dossier, et importe directement les sorties qui manquent — ou complète celles déjà "
            "enregistrées auxquelles il manque des informations (FC, D+, cadence, trace GPS...) "
            "tant qu'elles sont encore dans la mémoire de la montre. 100% local, aucune connexion "
            "internet ni compte Garmin nécessaire."
        )
        sous_titre.setObjectName("sousTitrePage")
        principal.addWidget(titre)
        principal.addWidget(sous_titre)

        barre = QHBoxLayout()
        label_athlete = QLabel("Athlète :")
        label_athlete.setObjectName("labelChamp")
        self.combo_athlete = QComboBox()
        for a in obtenir_athletes():
            self.combo_athlete.addItem(f"{a[2]} {a[1]}", a[0])
        if athlete_id_initial is not None:
            for i in range(self.combo_athlete.count()):
                if self.combo_athlete.itemData(i) == athlete_id_initial:
                    self.combo_athlete.setCurrentIndex(i)
                    break

        bouton_dossier = QPushButton("📂 Choisir le dossier de la montre")
        bouton_dossier.setObjectName("boutonSecondaire")
        bouton_dossier.clicked.connect(self.choisir_dossier)

        bouton_analyser = QPushButton("🔍 Analyser")
        bouton_analyser.setObjectName("boutonPrincipal")
        bouton_analyser.clicked.connect(self.analyser)

        barre.addWidget(label_athlete)
        barre.addWidget(self.combo_athlete)
        barre.addWidget(bouton_dossier)
        barre.addWidget(bouton_analyser)
        barre.addStretch()
        principal.addLayout(barre)

        self.champ_dossier = QLineEdit("")
        self.champ_dossier.setReadOnly(True)
        self.champ_dossier.setPlaceholderText("Aucun dossier choisi")
        principal.addWidget(self.champ_dossier)

        self.label_resultat = QLabel("—")
        self.label_resultat.setObjectName("texteSecondaire")
        self.label_resultat.setWordWrap(True)
        principal.addWidget(self.label_resultat)

        self.table = QTableWidget()
        colonnes = ["Traiter ?", "Fichier", "Date", "Type", "Distance (km)", "Statut", "Détail"]
        self.table.setColumnCount(len(colonnes))
        self.table.setHorizontalHeaderLabels(colonnes)
        configurer_table_redimensionnable(self.table)
        self.table.horizontalHeader().setSectionResizeMode(6, QHeaderView.ResizeMode.Stretch)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        principal.addWidget(self.table, 1)

        self.bouton_traiter = QPushButton("▶️ Traiter la sélection (importer / compléter)")
        self.bouton_traiter.setObjectName("boutonPrincipal")
        self.bouton_traiter.clicked.connect(self.traiter_selection)
        principal.addWidget(self.bouton_traiter)

        self.setStyleSheet(obtenir_style_ecran())

    def choisir_dossier(self):
        dossier = QFileDialog.getExistingDirectory(
            self, "Choisir le dossier de la montre (ou son dossier GARMIN/Activity)"
        )
        if dossier:
            self.dossier_courant = dossier
            self.champ_dossier.setText(dossier)

    def analyser(self):
        if not self.dossier_courant:
            QMessageBox.warning(self, "Dossier requis", "Choisis d'abord le dossier de la montre.")
            return

        athlete_id = self.combo_athlete.currentData()
        if athlete_id is None:
            QMessageBox.warning(self, "Athlète requis", "Sélectionne un athlète.")
            return

        self.resultats_courants = analyser_dossier(self.dossier_courant, athlete_id)
        self.table.setRowCount(0)
        self.cases = []

        if not self.resultats_courants:
            self.label_resultat.setText(
                "Aucun fichier .FIT trouvé dans ce dossier — vérifie que c'est bien le bon "
                "dossier de la montre (ou son sous-dossier GARMIN/Activity)."
            )
            return

        self.table.setRowCount(len(self.resultats_courants))
        for ligne, resultat in enumerate(self.resultats_courants):
            statut = resultat["statut"]
            case = QCheckBox()
            case.setChecked(statut in ("nouveau", "a_completer"))
            case.setEnabled(statut in ("nouveau", "a_completer"))
            self.table.setCellWidget(ligne, 0, case)
            self.cases.append(case)

            resume = resultat.get("resume", {})
            date_locale = resultat.get("date_locale")

            self.table.setItem(ligne, 1, QTableWidgetItem(resultat["chemin"].name))
            self.table.setItem(ligne, 2, QTableWidgetItem(date_locale.strftime("%d/%m/%Y %H:%M") if date_locale else "—"))
            self.table.setItem(ligne, 3, QTableWidgetItem(resume.get("type") or "—"))
            distance = resume.get("distance_km")
            self.table.setItem(ligne, 4, QTableWidgetItem(f"{distance:.2f}" if distance else "—"))
            self.table.setItem(ligne, 5, QTableWidgetItem(LIBELLE_STATUT.get(statut, statut)))

            if statut == "nouveau":
                detail = "Sera ajoutée comme nouvelle activité, avec sa trace GPS."
            elif statut == "a_completer":
                libelles = ", ".join(c[2] for c in resultat["champs_manquants"])
                detail = f"Complétera l'activité déjà enregistrée : {libelles}."
            elif statut == "complet":
                detail = "Déjà enregistrée et déjà complète — rien à faire."
            else:
                detail = resultat.get("raison", "")
            self.table.setItem(ligne, 6, QTableWidgetItem(detail))

        self.table.resizeColumnsToContents()
        nb_nouveau = sum(1 for r in self.resultats_courants if r["statut"] == "nouveau")
        nb_completer = sum(1 for r in self.resultats_courants if r["statut"] == "a_completer")
        self.label_resultat.setText(
            f"{len(self.resultats_courants)} fichier(s) .FIT trouvé(s) — {nb_nouveau} nouvelle(s) "
            f"activité(s), {nb_completer} à compléter."
        )

    def traiter_selection(self):
        a_traiter = [
            resultat for case, resultat in zip(self.cases, self.resultats_courants)
            if case.isChecked() and resultat["statut"] in ("nouveau", "a_completer")
        ]
        if not a_traiter:
            QMessageBox.information(self, "Rien à traiter", "Aucune ligne cochée.")
            return

        athlete_id = self.combo_athlete.currentData()
        nb_importees, nb_completees, nb_erreurs = 0, 0, 0

        for resultat in a_traiter:
            try:
                if resultat["statut"] == "nouveau":
                    importer_nouveau(
                        resultat["chemin"], athlete_id, resultat["resume"], resultat["date_locale"]
                    )
                    nb_importees += 1
                else:
                    completer_activite(
                        resultat["activite_id"], resultat["chemin"], resultat["champs_manquants"]
                    )
                    nb_completees += 1
            except Exception:
                nb_erreurs += 1

        message = f"{nb_importees} nouvelle(s) activité(s) importée(s), {nb_completees} complétée(s)."
        if nb_erreurs:
            message += f" {nb_erreurs} fichier(s) n'ont pas pu être traités."
        QMessageBox.information(self, "Terminé", message)

        self.analyser()
