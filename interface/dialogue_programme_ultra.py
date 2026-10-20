"""
Dialogue de génération d'un "Programme Ultra long terme" — objectif à
plusieurs mois/années (ex. un ultra de 60 km dans 2 ans), construit par
blocs progressifs à partir de l'entraînement réel déjà effectué. Voir
interface/generateur_ultra.py pour le détail du moteur.
"""

import json

from PySide6.QtCore import Qt, QDate
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QFormLayout,
    QLabel,
    QPushButton,
    QComboBox,
    QLineEdit,
    QSpinBox,
    QDateEdit,
    QTableWidget,
    QTableWidgetItem,
    QScrollArea,
    QWidget,
    QMessageBox,
)

from data.database import connexion
from interface.ecran_liste import obtenir_style_ecran, configurer_table_redimensionnable
from interface.generateur_plan import FACTEUR_NIVEAU, date_seance
from interface.generateur_ultra import generer_programme_ultra


JOURS_SEMAINE = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]


class DialogueProgrammeUltra(QDialog):

    def __init__(self, athlete_id, parent=None):
        super().__init__(parent)
        self.athlete_id = athlete_id
        self.programme = None  # (semaines, baseline, blocs_info)

        self.setWindowTitle("Programme Ultra long terme")
        self.resize(950, 800)

        conteneur_scroll = QScrollArea()
        conteneur_scroll.setWidgetResizable(True)
        conteneur_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        conteneur_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        central = QWidget()
        conteneur_scroll.setWidget(central)

        principal_ext = QVBoxLayout(self)
        principal_ext.setContentsMargins(0, 0, 0, 0)
        principal_ext.addWidget(conteneur_scroll)

        principal = QVBoxLayout(central)
        principal.setContentsMargins(20, 20, 20, 20)
        principal.setSpacing(12)

        titre = QLabel("🏔️ Programme Ultra long terme")
        titre.setObjectName("titreCarte")
        principal.addWidget(titre)

        note = QLabel(
            "Construit un programme progressif jusqu'à la distance visée, par blocs "
            "successifs se terminant chacun sur une course repère de plus en plus longue "
            "(ex. 15 → 24 → 33 → 42 → 51 → 60 km), avec musculation intégrée, une sortie "
            "longue le week-end, une séance spécifique de semaine plafonnée à ~45-60 min, "
            "et des courses de préparation régulières (allure/FC/temps visé calculés à "
            "partir de tes records). Le volume de départ est estimé à partir de ce que tu "
            "as réellement couru récemment — pas une valeur générique.\n\n"
            "Une fois enregistré, ce programme reste modifiable séance par séance, et "
            "ajustable semaine après semaine via « Replanifier automatiquement »."
        )
        note.setObjectName("texteSecondaire")
        note.setWordWrap(True)
        principal.addWidget(note)

        form = QFormLayout()

        self.champ_nom = QLineEdit("Objectif Ultra")

        self.champ_distance = QLineEdit("60")
        self.champ_distance.setPlaceholderText("Distance finale en km, ex. 60")

        self.spin_annees = QSpinBox()
        self.spin_annees.setRange(1, 4)
        self.spin_annees.setValue(2)
        self.spin_annees.setSuffix(" an(s)")

        self.combo_niveau = QComboBox()
        self.combo_niveau.addItems(list(FACTEUR_NIVEAU.keys()))
        self.combo_niveau.setCurrentText("Intermédiaire")

        self.champ_date_debut = QDateEdit()
        self.champ_date_debut.setCalendarPopup(True)
        self.champ_date_debut.setDate(QDate.currentDate())

        self.combo_jour_longue = QComboBox()
        self.combo_jour_longue.addItems(JOURS_SEMAINE)
        self.combo_jour_longue.setCurrentIndex(6)  # dimanche

        self.combo_jour_specifique = QComboBox()
        self.combo_jour_specifique.addItems(JOURS_SEMAINE)
        self.combo_jour_specifique.setCurrentIndex(3)  # jeudi

        self.spin_musculation = QSpinBox()
        self.spin_musculation.setRange(0, 4)
        self.spin_musculation.setValue(3)
        self.spin_musculation.setSuffix(" x / semaine")

        self.champ_allure = QLineEdit()
        self.champ_allure.setPlaceholderText("mm:ss / km — laisse vide pour une estimation auto")

        form.addRow("Nom du programme :", self.champ_nom)
        form.addRow("Distance finale visée (km) :", self.champ_distance)
        form.addRow("Horizon :", self.spin_annees)
        form.addRow("Niveau :", self.combo_niveau)
        form.addRow("Date de début :", self.champ_date_debut)
        form.addRow("Jour de la sortie longue :", self.combo_jour_longue)
        form.addRow("Jour de la séance spécifique :", self.combo_jour_specifique)
        form.addRow("Musculation :", self.spin_musculation)
        form.addRow("Allure objectif finale (optionnel) :", self.champ_allure)

        principal.addLayout(form)

        note_jours = QLabel(
            "Le jour de la sortie longue est fixe dans le programme généré (dimanche par "
            "défaut) — le repli du samedi que tu utilises certaines semaines n'est pas "
            "automatisé, mais tu peux déplacer une séance ponctuellement dans l'écran "
            "« Séances structurées ». Musculation placée en priorité les jours déjà courus "
            "dans la semaine (comme ton rythme réel : midi en semaine)."
        )
        note_jours.setObjectName("texteSecondaire")
        note_jours.setWordWrap(True)
        principal.addWidget(note_jours)

        barre_boutons = QHBoxLayout()
        bouton_apercu = QPushButton("👁 Générer l'aperçu")
        bouton_apercu.setObjectName("boutonSecondaire")
        bouton_apercu.clicked.connect(self.generer_apercu)
        self.bouton_enregistrer = QPushButton("💾 Enregistrer ce programme")
        self.bouton_enregistrer.setObjectName("boutonPrincipal")
        self.bouton_enregistrer.setEnabled(False)
        self.bouton_enregistrer.clicked.connect(self.enregistrer_programme)
        barre_boutons.addWidget(bouton_apercu)
        barre_boutons.addWidget(self.bouton_enregistrer)
        principal.addLayout(barre_boutons)

        self.label_baseline = QLabel("")
        self.label_baseline.setObjectName("texteSecondaire")
        self.label_baseline.setWordWrap(True)
        principal.addWidget(self.label_baseline)

        titre_blocs = QLabel("Blocs du programme")
        titre_blocs.setObjectName("titreCarte")
        principal.addWidget(titre_blocs)

        self.table_blocs = QTableWidget()
        self.table_blocs.setColumnCount(5)
        self.table_blocs.setHorizontalHeaderLabels(
            ["Bloc", "Semaines", "Course repère", "Volume pic/semaine", "Cible de la course repère"]
        )
        configurer_table_redimensionnable(self.table_blocs)
        self.table_blocs.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table_blocs.setMinimumHeight(180)
        principal.addWidget(self.table_blocs)

        titre_courses = QLabel("Toutes les courses de préparation prévues")
        titre_courses.setObjectName("titreCarte")
        principal.addWidget(titre_courses)

        self.table_courses = QTableWidget()
        self.table_courses.setColumnCount(3)
        self.table_courses.setHorizontalHeaderLabels(["Semaine", "Date", "Course"])
        configurer_table_redimensionnable(self.table_courses)
        self.table_courses.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table_courses.setMinimumHeight(160)
        principal.addWidget(self.table_courses)

        self.setStyleSheet(obtenir_style_ecran())

    # ------------------------------------------------------------
    def _parametres_valides(self):
        try:
            distance_finale = float(self.champ_distance.text().strip().replace(",", "."))
            if distance_finale <= 0:
                raise ValueError
        except ValueError:
            QMessageBox.warning(self, "Distance invalide", "Indique une distance finale en km (ex. 60).")
            return None
        return distance_finale

    def generer_apercu(self):
        distance_finale = self._parametres_valides()
        if distance_finale is None:
            return

        nb_semaines = self.spin_annees.value() * 52
        date_debut = self.champ_date_debut.date().toPython()

        semaines, baseline, blocs = generer_programme_ultra(
            self.athlete_id,
            distance_finale_km=distance_finale,
            nb_semaines=nb_semaines,
            date_debut=date_debut,
            jour_sortie_longue=self.combo_jour_longue.currentIndex(),
            jour_seance_specifique=self.combo_jour_specifique.currentIndex(),
            nb_musculation_semaine=self.spin_musculation.value(),
            allure_objectif_finale_texte=self.champ_allure.text().strip() or None,
            niveau=self.combo_niveau.currentText(),
        )
        self.programme = (semaines, baseline, blocs, date_debut)

        if baseline["volume_hebdo_moyen_km"] is not None:
            self.label_baseline.setText(
                f"Point de départ estimé à partir de tes sorties réelles depuis "
                f"{baseline['nb_semaines_donnees']} semaines : {baseline['volume_hebdo_moyen_km']} km/semaine "
                f"en moyenne, plus longue sortie {baseline['plus_longue_recente_km']} km."
            )
        else:
            self.label_baseline.setText(
                "Pas assez de sorties récentes enregistrées pour estimer ton point de départ réel "
                "— le programme démarre sur une base prudente par défaut."
            )

        self.table_blocs.setRowCount(len(blocs))
        for i, b in enumerate(blocs):
            self.table_blocs.setItem(i, 0, QTableWidgetItem(b["nom"]))
            self.table_blocs.setItem(i, 1, QTableWidgetItem(str(b["nb_semaines"])))
            self.table_blocs.setItem(i, 2, QTableWidgetItem(f"{b['distance_repere_km']:g} km"))
            self.table_blocs.setItem(i, 3, QTableWidgetItem(f"{b['volume_pic_km']} km"))
            self.table_blocs.setItem(i, 4, QTableWidgetItem(b["cibles"]["texte"]))
        self.table_blocs.resizeColumnsToContents()

        courses = []
        for s in semaines:
            for seance in s["seances"]:
                if seance["type_seance"] == "Course de préparation":
                    d = date_seance(date_debut, s["indice"], seance["jour_offset"])
                    courses.append((s["indice"], d, seance["nom"]))

        self.table_courses.setRowCount(len(courses))
        for i, (indice, d, nom) in enumerate(courses):
            self.table_courses.setItem(i, 0, QTableWidgetItem(f"Semaine {indice}"))
            self.table_courses.setItem(i, 1, QTableWidgetItem(d.strftime("%d/%m/%Y")))
            self.table_courses.setItem(i, 2, QTableWidgetItem(nom))
        self.table_courses.resizeColumnsToContents()

        self.bouton_enregistrer.setEnabled(True)

    def enregistrer_programme(self):
        if not self.programme:
            QMessageBox.information(self, "Aperçu requis", "Génère d'abord l'aperçu du programme.")
            return
        if not self.champ_nom.text().strip():
            QMessageBox.warning(self, "Nom requis", "Donne un nom à ce programme.")
            return

        semaines, baseline, blocs, date_debut = self.programme
        distance_finale = self._parametres_valides()
        if distance_finale is None:
            return

        nb_semaines = len(semaines)
        date_fin = date_seance(date_debut, nb_semaines, self.combo_jour_longue.currentIndex())

        conn = connexion()
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO plans_entrainement (
                athlete_id, nom, distance_cible, niveau, nb_semaines,
                jours_par_semaine, allure_objectif, date_debut, date_course
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                self.athlete_id,
                self.champ_nom.text().strip(),
                f"Ultra {distance_finale:g} km (objectif {self.spin_annees.value()} an(s))",
                self.combo_niveau.currentText(),
                nb_semaines,
                None,
                self.champ_allure.text().strip() or None,
                date_debut.strftime("%Y-%m-%d"),
                date_fin.strftime("%Y-%m-%d"),
            ),
        )
        plan_id = cur.lastrowid

        for semaine in semaines:
            for seance in semaine["seances"]:
                date_prevue = date_seance(date_debut, semaine["indice"], seance["jour_offset"])
                cur.execute(
                    """
                    INSERT INTO seances_structurees (
                        athlete_id, nom, type_seance, date_prevue, statut, etapes_json, plan_id
                    ) VALUES (?, ?, ?, ?, 'Prévue', ?, ?)
                    """,
                    (
                        self.athlete_id,
                        f"S{semaine['indice']} [{semaine['bloc']}] — {seance['nom']}",
                        seance["type_seance"],
                        date_prevue.strftime("%Y-%m-%d"),
                        json.dumps(seance["etapes"]),
                        plan_id,
                    ),
                )

        conn.commit()
        conn.close()

        nb_seances = sum(len(s["seances"]) for s in semaines)
        QMessageBox.information(
            self, "Programme enregistré",
            f"« {self.champ_nom.text().strip()} » a été enregistré : {nb_seances} séances sur "
            f"{nb_semaines} semaines, du {date_debut.strftime('%d/%m/%Y')} au "
            f"{date_fin.strftime('%d/%m/%Y')}.\n\n"
            "Retrouve-les dans « Séances structurées », et utilise « Replanifier "
            "automatiquement » régulièrement pour ajuster la suite selon ce qui est "
            "vraiment réalisé."
        )
        self.accept()
