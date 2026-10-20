"""
Dialogue "Analyser la tactique de course" — ouvert depuis l'écran
Objectifs pour un objectif de type "Course". Voir
interface/tactique_course.py pour le détail du moteur (diagnostic local
à fond/en réserve + tactique rédigée par l'IA).
"""

from PySide6.QtCore import Qt
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
    QDoubleSpinBox,
    QTextEdit,
    QMessageBox,
    QScrollArea,
    QWidget,
)

from data.database import connexion
from interface.ecran_liste import obtenir_style_ecran
from interface.date_utils import parser_date_flexible
from interface.tache_ia import TacheAnalyseIA
from interface.tactique_course import (
    analyser_tactique_course, enregistrer_analyse_course, derniere_analyse_course,
)
from interface.ia_coach import cle_api_configuree


TYPES_TERRAIN = ["Trail", "Sentier technique", "Route", "Mixte", "Piste"]

STATUTS_TEXTE = {
    "a_fond": "🟢 À fond (course objectif)",
    "en_reserve": "🟡 En réserve (course de préparation)",
    "a_determiner": "⚪ À déterminer",
}


class DialogueTactiqueCourse(QDialog):

    def __init__(self, objectif_id, athlete_id, titre_objectif, date_cible_texte, parent=None):
        super().__init__(parent)
        self.objectif_id = objectif_id
        self.athlete_id = athlete_id
        self._tache = None

        self.setWindowTitle(f"Tactique de course — {titre_objectif}")
        self.resize(800, 850)

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

        titre = QLabel(f"🏁 {titre_objectif}")
        titre.setObjectName("titreCarte")
        principal.addWidget(titre)

        self.date_cible = parser_date_flexible(date_cible_texte)
        sous_titre = QLabel(
            f"Course le {self.date_cible.strftime('%d/%m/%Y')}" if self.date_cible
            else "Date de la course non renseignée dans l'objectif"
        )
        sous_titre.setObjectName("texteSecondaire")
        principal.addWidget(sous_titre)

        note = QLabel(
            "Le statut « à fond / en réserve » est déterminé localement (sans IA) à partir "
            "de ton programme d'entraînement en cours, ton ACWR et ta forme — l'IA n'ajoute "
            "que la tactique de course en langage naturel. Récupérer une page web est "
            "un essai au mieux (beaucoup de sites d'inscription ne s'y prêtent pas) : la "
            "saisie manuelle ci-dessous reste le plus fiable."
        )
        note.setObjectName("texteSecondaire")
        note.setWordWrap(True)
        principal.addWidget(note)

        if not cle_api_configuree():
            avertissement = QLabel(
                "⚠️ Aucune clé API Gemini/Groq configurée (Réglages) — le diagnostic local "
                "restera disponible mais la tactique rédigée par l'IA ne pourra pas être générée."
            )
            avertissement.setObjectName("texteSecondaire")
            avertissement.setWordWrap(True)
            principal.addWidget(avertissement)

        form = QFormLayout()

        self.champ_distance = QDoubleSpinBox()
        self.champ_distance.setRange(0, 400)
        self.champ_distance.setSuffix(" km")
        self.champ_distance.setDecimals(1)

        self.champ_denivele_pos = QSpinBox()
        self.champ_denivele_pos.setRange(0, 20000)
        self.champ_denivele_pos.setSuffix(" m")

        self.champ_denivele_neg = QSpinBox()
        self.champ_denivele_neg.setRange(0, 20000)
        self.champ_denivele_neg.setSuffix(" m")

        self.combo_terrain = QComboBox()
        self.combo_terrain.addItems(TYPES_TERRAIN)

        self.combo_intention = QComboBox()
        self.combo_intention.addItem("Je ne sais pas — dis-moi", None)
        self.combo_intention.addItem("Mon objectif principal (à fond)", "objectif")
        self.combo_intention.addItem("Une course de préparation/entraînement (en réserve)", "preparation")

        self.champ_url = QLineEdit()
        self.champ_url.setPlaceholderText("Lien de la page de la course (optionnel)")

        self.champ_notes = QTextEdit()
        self.champ_notes.setPlaceholderText(
            "Détails utiles que tu connais déjà : profil, cut-offs, ravitos, météo attendue..."
        )
        self.champ_notes.setMaximumHeight(80)

        form.addRow("Distance :", self.champ_distance)
        form.addRow("Dénivelé D+ :", self.champ_denivele_pos)
        form.addRow("Dénivelé D− :", self.champ_denivele_neg)
        form.addRow("Terrain :", self.combo_terrain)
        form.addRow("Cette course est :", self.combo_intention)
        form.addRow("Lien de la course :", self.champ_url)
        form.addRow("Notes :", self.champ_notes)

        principal.addLayout(form)

        self.bouton_generer = QPushButton("🤖 Générer l'analyse tactique")
        self.bouton_generer.setObjectName("boutonPrincipal")
        self.bouton_generer.clicked.connect(self.lancer_analyse)
        principal.addWidget(self.bouton_generer)

        self.label_statut = QLabel("")
        self.label_statut.setObjectName("titreCarte")
        self.label_statut.setWordWrap(True)
        principal.addWidget(self.label_statut)

        self.label_justification = QLabel("")
        self.label_justification.setObjectName("texteSecondaire")
        self.label_justification.setWordWrap(True)
        principal.addWidget(self.label_justification)

        self.zone_texte_ia = QTextEdit()
        self.zone_texte_ia.setReadOnly(True)
        self.zone_texte_ia.setMinimumHeight(280)
        principal.addWidget(self.zone_texte_ia)

        bouton_fermer = QPushButton("Fermer")
        bouton_fermer.setObjectName("boutonSecondaire")
        bouton_fermer.clicked.connect(self.accept)
        principal.addWidget(bouton_fermer, alignment=Qt.AlignmentFlag.AlignRight)

        self.setStyleSheet(obtenir_style_ecran())

        self._charger_derniere_analyse()

    def _charger_derniere_analyse(self):
        ligne = derniere_analyse_course(self.objectif_id)
        if not ligne:
            return
        (distance_km, denivele_positif, denivele_negatif, type_terrain, url_course,
         notes_course, recommandation, diagnostic_local, contenu_ia, date_generation) = ligne

        if distance_km:
            self.champ_distance.setValue(distance_km)
        if denivele_positif:
            self.champ_denivele_pos.setValue(denivele_positif)
        if denivele_negatif:
            self.champ_denivele_neg.setValue(denivele_negatif)
        if type_terrain and type_terrain in TYPES_TERRAIN:
            self.combo_terrain.setCurrentText(type_terrain)
        if url_course:
            self.champ_url.setText(url_course)
        if notes_course:
            self.champ_notes.setPlainText(notes_course)

        self.label_statut.setText(
            f"Dernière analyse ({date_generation[:10]}) : "
            + STATUTS_TEXTE.get(recommandation, recommandation or "—")
        )
        self.label_justification.setText(diagnostic_local or "")
        if contenu_ia:
            self.zone_texte_ia.setMarkdown(contenu_ia)

    def lancer_analyse(self):
        if self.date_cible is None:
            QMessageBox.warning(
                self, "Date manquante",
                "Renseigne d'abord une date cible sur cet objectif (dans l'écran Objectifs) "
                "pour pouvoir situer la course dans ton entraînement."
            )
            return
        if self.champ_distance.value() <= 0:
            QMessageBox.warning(self, "Distance manquante", "Indique la distance de la course.")
            return

        self.bouton_generer.setEnabled(False)
        self.bouton_generer.setText("⏳ Analyse en cours...")
        self.zone_texte_ia.setPlainText("Génération en cours (peut prendre jusqu'à une minute)...")
        self.label_statut.setText("")
        self.label_justification.setText("")

        distance_km = self.champ_distance.value()
        denivele_positif = self.champ_denivele_pos.value() or None
        denivele_negatif = self.champ_denivele_neg.value() or None
        type_terrain = self.combo_terrain.currentText()
        notes_course = self.champ_notes.toPlainText().strip() or None
        url_course = self.champ_url.text().strip() or None
        intention = self.combo_intention.currentData()
        date_course = self.date_cible.date()

        def _executer():
            return analyser_tactique_course(
                self.athlete_id, date_course, distance_km, denivele_positif, denivele_negatif,
                type_terrain, notes_course, url_course, intention,
            )

        self._parametres_analyse = (
            distance_km, denivele_positif, denivele_negatif, type_terrain, url_course, notes_course,
        )

        self._tache = TacheAnalyseIA(_executer)
        self._tache.reussite.connect(self._analyse_reussie)
        self._tache.echec.connect(self._analyse_echouee)
        self._tache.start()

    def _analyse_reussie(self, resultat):
        diagnostic, contenu_ia = resultat
        self.bouton_generer.setEnabled(True)
        self.bouton_generer.setText("🤖 Générer l'analyse tactique")

        self.label_statut.setText(STATUTS_TEXTE.get(diagnostic["statut_recommande"], "—"))
        justification = diagnostic["justification"]
        if diagnostic["alerte_charge"]:
            justification += f"\n⚠️ {diagnostic['alerte_charge']}"
        self.label_justification.setText(justification)
        self.zone_texte_ia.setMarkdown(contenu_ia)

        distance_km, denivele_positif, denivele_negatif, type_terrain, url_course, notes_course = (
            self._parametres_analyse
        )
        enregistrer_analyse_course(
            self.objectif_id, self.athlete_id, distance_km, denivele_positif, denivele_negatif,
            type_terrain, url_course, notes_course, diagnostic, contenu_ia,
        )

    def _analyse_echouee(self, message):
        self.bouton_generer.setEnabled(True)
        self.bouton_generer.setText("🤖 Générer l'analyse tactique")
        self.zone_texte_ia.setPlainText(f"Échec de l'analyse : {message}")
