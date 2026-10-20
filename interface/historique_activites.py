import json
from datetime import date as _date, timedelta as _timedelta
import calendar as _calendar

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QLabel,
    QComboBox,
    QLineEdit,
    QFrame,
    QTableWidget,
    QTableWidgetItem,
    QStyledItemDelegate,
    QHeaderView,
    QScrollArea,
    QPushButton,
    QDialog,
    QCheckBox,
    QDialogButtonBox,
    QTextEdit,
    QApplication,
    QMessageBox,
    QMenu,
)

from data.database import (
    connexion, obtenir_athletes, obtenir_parametre, definir_parametre,
    supprimer_activite,
)
from interface.ecran_liste import (
    obtenir_style_ecran, configurer_table_redimensionnable, creer_bouton_retour_tableau_bord,
)
from interface.apercu_survol import installer_apercu_survol
from interface.date_utils import parser_date_flexible
from interface.coach import charge_activite_pour_athlete
from interface.vo2max import estimer_vo2max
from interface.ia_coach import analyser_sortie, cle_api_configuree
from interface.tache_ia import TacheAnalyseIA
from interface.detail_sortie import DialogueDetailSortie
from interface.dialogue_nouvelle_activite import DialogueNouvelleActivite
from interface.calendrier_activites import ouvrir_calendrier_activites
from interface.apercu_widgets import DelegatePastilleType


TYPES_FILTRE = ["Tous", "Trail", "Course", "VTT", "Vélo", "Randonnée", "Autre"]

CLE_PARAMETRE_COLONNES = "colonnes_historique_activites"

# Colonne "Date" toujours affichée en premier (ancre du tri par défaut),
# non proposée dans le sélecteur pour éviter de se retrouver sans aucun
# repère chronologique. Les autres sont toutes optionnelles.
#
# (clé, libellé affiché, type de formatage, champ correspondant en base
#  — None quand la valeur est calculée à la volée, ex. la charge TRIMP)
DEFINITION_COLONNES = [
    ("nom", "Nom", "texte", "nom"),
    ("type", "Type", "texte", "type"),
    ("distance", "Distance (km)", "nombre2", "distance"),
    ("denivele", "D+ (m)", "entier", "denivele"),
    ("denivele_negatif", "D− (m)", "entier", "denivele_negatif"),
    ("duree", "Durée / Chrono", "duree", "duree"),
    ("allure_moyenne", "Allure moyenne (/km)", "allure", "allure_moyenne"),
    ("allure_max", "Allure max (/km)", "allure", "allure_max"),
    ("vitesse_moyenne", "Vitesse moyenne (km/h)", "nombre2", "vitesse_moyenne"),
    ("vitesse_max", "Vitesse max (km/h)", "nombre2", "vitesse_max"),
    ("frequence_cardiaque_moyenne", "FC moyenne (bpm)", "entier", "frequence_cardiaque_moyenne"),
    ("frequence_cardiaque_max", "FC max (bpm)", "entier", "frequence_cardiaque_max"),
    ("calories", "Calories", "entier", "calories"),
    ("cadence_moyenne", "Cadence moyenne (spm)", "entier", "cadence_moyenne"),
    ("vo2max", "VO2max (mesuré/estimé)", "nombre1", "vo2max"),
    ("charge", "Charge (TRIMP)", "nombre1", None),
    ("source", "Source", "texte", "source"),
    ("notes", "Notes", "texte", "notes"),
]

COLONNES_PAR_DEFAUT = [
    "nom", "type", "distance", "denivele", "duree", "frequence_cardiaque_moyenne", "source",
]

CHAMPS_DB = [champ for (_, _, _, champ) in DEFINITION_COLONNES if champ is not None]


class ItemTrie(QTableWidgetItem):
    """QTableWidgetItem qui trie sur une valeur réelle (date, nombre)
    plutôt que sur le texte affiché — sinon "9" se retrouve après "10"
    et les dates ne se trient pas correctement selon leur format."""

    def __init__(self, texte, valeur_tri):
        super().__init__(texte)
        self.valeur_tri = valeur_tri

    def __lt__(self, autre):
        if isinstance(autre, ItemTrie):
            if self.valeur_tri is None:
                return True
            if autre.valeur_tri is None:
                return False
            return self.valeur_tri < autre.valeur_tri
        return super().__lt__(autre)


def _formater_duree(secondes):
    if not secondes:
        return "—"
    secondes = int(secondes)
    h, reste = divmod(secondes, 3600)
    m, s = divmod(reste, 60)
    return f"{h}h{m:02d}"


def _formater_allure(minutes_par_km):
    """Ex. 5.23 (min/km, format décimal existant) -> "5'14\"/km"."""
    if not minutes_par_km:
        return "—"
    minutes_par_km = float(minutes_par_km)
    minutes_entieres = int(minutes_par_km)
    secondes = round((minutes_par_km - minutes_entieres) * 60)
    if secondes == 60:
        minutes_entieres += 1
        secondes = 0
    return f"{minutes_entieres}'{secondes:02d}\"/km"


def _formater_valeur(cle_type, valeur):
    if valeur in (None, ""):
        return "—", (valeur if valeur is not None else None)

    if cle_type == "texte":
        return str(valeur), None
    if cle_type == "entier":
        return str(round(valeur)), valeur
    if cle_type == "nombre1":
        return f"{valeur:.1f}".replace(".", ","), valeur
    if cle_type == "nombre2":
        return f"{valeur:.2f}".replace(".", ","), valeur
    if cle_type == "duree":
        return _formater_duree(valeur), valeur
    if cle_type == "allure":
        return _formater_allure(valeur), valeur
    return str(valeur), None


class DialogueColonnes(QDialog):
    """Sélecteur de colonnes à afficher dans l'historique — coché/décoché
    librement, persistant d'une session à l'autre."""

    def __init__(self, colonnes_actives, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Colonnes affichées")
        self.setMinimumWidth(520)

        layout = QVBoxLayout(self)

        info = QLabel(
            "Choisis les colonnes à afficher dans l'historique des activités "
            "(« Date » reste toujours affichée en premier)."
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        barre_rapide = QHBoxLayout()
        bouton_tout = QPushButton("Tout cocher")
        bouton_tout.clicked.connect(self._tout_cocher)
        bouton_aucun = QPushButton("Tout décocher")
        bouton_aucun.clicked.connect(self._tout_decocher)
        bouton_defaut = QPushButton("Réinitialiser")
        bouton_defaut.clicked.connect(self._reinitialiser)
        barre_rapide.addWidget(bouton_tout)
        barre_rapide.addWidget(bouton_aucun)
        barre_rapide.addWidget(bouton_defaut)
        barre_rapide.addStretch()
        layout.addLayout(barre_rapide)

        grille = QGridLayout()
        self.cases = {}
        nb_colonnes_grille = 2
        for i, (cle, label, _type, _champ) in enumerate(DEFINITION_COLONNES):
            case = QCheckBox(label)
            case.setChecked(cle in colonnes_actives)
            self.cases[cle] = case
            grille.addWidget(case, i // nb_colonnes_grille, i % nb_colonnes_grille)
        layout.addLayout(grille)

        boutons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        boutons.accepted.connect(self.accept)
        boutons.rejected.connect(self.reject)
        layout.addWidget(boutons)

    def _tout_cocher(self):
        for case in self.cases.values():
            case.setChecked(True)

    def _tout_decocher(self):
        for case in self.cases.values():
            case.setChecked(False)

    def _reinitialiser(self):
        for cle, case in self.cases.items():
            case.setChecked(cle in COLONNES_PAR_DEFAUT)

    def colonnes_selectionnees(self):
        return [cle for cle, case in self.cases.items() if case.isChecked()]


class DialogueAnalyseIA(QDialog):
    """Affiche le compte rendu IA d'une sortie (depuis le cache en base,
    ou en le générant à la demande via l'API Gemini)."""

    def __init__(self, activite_id, athlete_id, nom_activite, parent=None):
        super().__init__(parent)
        self.activite_id = activite_id
        self.athlete_id = athlete_id

        self.setWindowTitle("🤖 Analyse IA de la sortie")
        self.resize(650, 550)

        layout = QVBoxLayout(self)

        titre = QLabel(f"Analyse de : {nom_activite or 'cette sortie'}")
        titre.setObjectName("titreCarte")
        titre.setWordWrap(True)
        layout.addWidget(titre)

        self.zone_texte = QTextEdit()
        self.zone_texte.setReadOnly(True)
        layout.addWidget(self.zone_texte, 1)

        barre = QHBoxLayout()
        self.bouton_regenerer = QPushButton("🔄 Régénérer l'analyse")
        self.bouton_regenerer.setObjectName("boutonSecondaire")
        self.bouton_regenerer.clicked.connect(lambda: self._lancer_analyse(forcer=True))
        barre.addWidget(self.bouton_regenerer)
        barre.addStretch()

        boutons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        boutons.rejected.connect(self.reject)
        boutons.accepted.connect(self.accept)
        barre.addWidget(boutons)
        layout.addLayout(barre)

        self._lancer_analyse(forcer=False)

    def _lancer_analyse(self, forcer):
        if not cle_api_configuree():
            self.zone_texte.setPlainText(
                "⚠️ Aucune clé API configurée.\n\n"
                "Va dans Réglages > Analyse IA des sorties pour renseigner une clé "
                "gratuite (Gemini et/ou Groq), puis reviens ici."
            )
            self.bouton_regenerer.setEnabled(False)
            return

        self.zone_texte.setPlainText(
            "⏳ Génération de l'analyse en cours... (nécessite une connexion internet — "
            "la fenêtre reste utilisable pendant l'attente)"
            if forcer else
            "⏳ Chargement de l'analyse..."
        )
        self.bouton_regenerer.setEnabled(False)

        self._tache_analyse = TacheAnalyseIA(
            lambda: analyser_sortie(self.activite_id, self.athlete_id, forcer_regeneration=forcer)
        )
        self._tache_analyse.reussite.connect(self._analyse_reussie)
        self._tache_analyse.echec.connect(self._analyse_echouee)
        self._tache_analyse.start()

    def _analyse_reussie(self, resultat):
        contenu, depuis_cache = resultat
        entete = "📦 Analyse déjà générée précédemment (mise en cache) :\n\n" if depuis_cache else ""
        self.zone_texte.setPlainText(entete + contenu)
        self.bouton_regenerer.setEnabled(True)

    def _analyse_echouee(self, message):
        self.zone_texte.setPlainText(f"⚠️ {message}")
        self.bouton_regenerer.setEnabled(True)
        self.bouton_regenerer.setEnabled(True)


class HistoriqueActivites(QMainWindow):

    def __init__(self, athlete_id_initial=None):
        super().__init__()

        self.setWindowTitle("TrailMaster Pro – Historique des activités")
        self.resize(1300, 850)
        self.setMinimumSize(1000, 650)

        self.colonnes_actives = self._charger_colonnes_actives()

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

        principal.addWidget(creer_bouton_retour_tableau_bord(self), 0, Qt.AlignmentFlag.AlignLeft)

        titre = QLabel("📋  Historique des activités")
        titre.setObjectName("titrePage")
        sous_titre = QLabel(
            "Toutes tes activités enregistrées (import manuel ou synchro Strava) — "
            "clique sur un en-tête de colonne pour trier, fais glisser le bord d'une "
            "colonne pour l'agrandir (barre de défilement en bas pour les autres), "
            "double-clique sur une sortie pour voir son détail complet"
        )
        sous_titre.setObjectName("sousTitrePage")
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

        label_type = QLabel("Type :")
        label_type.setObjectName("labelChamp")
        self.combo_type = QComboBox()
        self.combo_type.addItems(TYPES_FILTRE)

        label_recherche = QLabel("Recherche :")
        label_recherche.setObjectName("labelChamp")
        self.champ_recherche = QLineEdit()
        self.champ_recherche.setPlaceholderText("Nom de l'activité...")

        bouton_colonnes = QPushButton("🔧 Colonnes")
        bouton_colonnes.setObjectName("boutonSecondaire")
        bouton_colonnes.clicked.connect(self.ouvrir_selecteur_colonnes)

        bouton_analyse_ia = QPushButton("🤖 Analyse IA")
        bouton_analyse_ia.setObjectName("boutonPrincipal")
        bouton_analyse_ia.clicked.connect(self.ouvrir_analyse_ia)

        barre.addWidget(label_athlete)
        barre.addWidget(self.combo_athlete)
        barre.addSpacing(10)
        barre.addWidget(label_type)
        barre.addWidget(self.combo_type)
        barre.addSpacing(10)
        barre.addWidget(label_recherche)
        barre.addWidget(self.champ_recherche)
        barre.addStretch()
        barre.addWidget(bouton_colonnes)
        barre.addWidget(bouton_analyse_ia)
        principal.addLayout(barre)

        # ------------------------------------------------------------
        # SORTIES + JOURS DE REPOS (vue mois par mois)
        # ------------------------------------------------------------

        barre_repos = QHBoxLayout()

        self.case_jours_repos = QCheckBox(
            "🗓️ Regrouper avec les jours de repos (vue par mois)"
        )
        self.case_jours_repos.toggled.connect(self.basculer_mode_repos)
        barre_repos.addWidget(self.case_jours_repos)

        self.bouton_mois_precedent = QPushButton("←")
        self.bouton_mois_precedent.setObjectName("boutonSecondaire")
        self.bouton_mois_precedent.clicked.connect(self._mois_precedent)
        self.label_mois_repos = QLabel("")
        self.label_mois_repos.setObjectName("labelChamp")
        self.bouton_mois_suivant = QPushButton("→")
        self.bouton_mois_suivant.setObjectName("boutonSecondaire")
        self.bouton_mois_suivant.clicked.connect(self._mois_suivant)
        barre_repos.addWidget(self.bouton_mois_precedent)
        barre_repos.addWidget(self.label_mois_repos)
        barre_repos.addWidget(self.bouton_mois_suivant)

        barre_repos.addStretch()

        bouton_nouvelle_sortie = QPushButton("➕ Ajouter une sortie")
        bouton_nouvelle_sortie.setObjectName("boutonSecondaire")
        bouton_nouvelle_sortie.clicked.connect(self.ouvrir_nouvelle_sortie)
        barre_repos.addWidget(bouton_nouvelle_sortie)

        bouton_calendrier = QPushButton("📅 Voir le calendrier")
        bouton_calendrier.setObjectName("boutonPrincipal")
        bouton_calendrier.clicked.connect(self.ouvrir_calendrier)
        barre_repos.addWidget(bouton_calendrier)

        principal.addLayout(barre_repos)

        aujourd_hui = _date.today()
        self.annee_repos = aujourd_hui.year
        self.mois_repos = aujourd_hui.month
        self._actualiser_label_mois_repos()
        self._actualiser_visibilite_nav_mois(False)

        self.label_total = QLabel("—")
        self.label_total.setObjectName("texteSecondaire")
        principal.addWidget(self.label_total)

        self.table = QTableWidget()
        # Colonnes ET lignes redimensionnables à la main (au lieu de
        # comprimées pour tenir dans la largeur de la fenêtre) + défilement
        # latéral/vertical pour atteindre ce qui dépasse — plus confortable
        # dès que plusieurs colonnes optionnelles sont affichées ensemble.
        configurer_table_redimensionnable(self.table)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSortingEnabled(True)
        self.table.cellDoubleClicked.connect(self.ouvrir_detail_sortie)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self.ouvrir_menu_contextuel)
        principal.addWidget(self.table, 1)

        self._apercu = installer_apercu_survol(
            self.table, self._id_activite_pour_ligne, self._apercu_pour_activite
        )

        self.setStyleSheet(obtenir_style_ecran())

        if athlete_id_initial is not None:
            for i in range(self.combo_athlete.count()):
                if self.combo_athlete.itemData(i) == athlete_id_initial:
                    self.combo_athlete.setCurrentIndex(i)
                    break

        self.combo_athlete.currentIndexChanged.connect(self.charger_activites)
        self.combo_type.currentIndexChanged.connect(self.charger_activites)
        self.champ_recherche.textChanged.connect(self.charger_activites)

        self._reconstruire_entetes()
        self.charger_activites()

    def _charger_colonnes_actives(self):
        brut = obtenir_parametre(CLE_PARAMETRE_COLONNES)
        if not brut:
            return list(COLONNES_PAR_DEFAUT)
        try:
            colonnes = json.loads(brut)
        except (TypeError, ValueError):
            return list(COLONNES_PAR_DEFAUT)
        cles_valides = {cle for cle, _, _, _ in DEFINITION_COLONNES}
        colonnes = [c for c in colonnes if c in cles_valides]
        return colonnes or list(COLONNES_PAR_DEFAUT)

    def ouvrir_detail_sortie(self, ligne, colonne):
        athlete_id = self.combo_athlete.currentData()
        if athlete_id is None:
            return

        item_date = self.table.item(ligne, 0)
        activite_id = item_date.data(Qt.ItemDataRole.UserRole) if item_date else None
        if activite_id is None:
            # Ligne « Repos » (vue mois par mois) : la date du jour est
            # rangée à la place de l'id — on propose de saisir la sortie
            # manquante plutôt que de ne rien faire.
            jour_repos = item_date.data(Qt.ItemDataRole.UserRole + 2) if item_date else None
            if jour_repos:
                self._ouvrir_nouvelle_sortie_pour_jour(jour_repos)
            return

        dialogue = DialogueDetailSortie(
            activite_id, athlete_id, self, au_enregistrement=self.charger_activites
        )
        dialogue.exec()

    def _ouvrir_nouvelle_sortie_pour_jour(self, jour_iso):
        athlete_id = self.combo_athlete.currentData()
        if athlete_id is None:
            return
        dialogue = DialogueNouvelleActivite(
            athlete_id, date_iso=jour_iso, parent=self, au_enregistrement=self.charger_activites
        )
        dialogue.exec()

    def ouvrir_nouvelle_sortie(self):
        athlete_id = self.combo_athlete.currentData()
        if athlete_id is None:
            QMessageBox.information(self, "Athlète requis", "Sélectionne d'abord un athlète.")
            return
        dialogue = DialogueNouvelleActivite(
            athlete_id, parent=self, au_enregistrement=self.charger_activites
        )
        dialogue.exec()

    def ouvrir_calendrier(self):
        athlete_id = self.combo_athlete.currentData()
        if athlete_id is None:
            QMessageBox.information(self, "Athlète requis", "Sélectionne d'abord un athlète.")
            return
        ouvrir_calendrier_activites(self, athlete_id, au_changement=self.charger_activites)

    # ------------------------------------------------------------
    # VUE « SORTIES + JOURS DE REPOS » (mois par mois)
    # ------------------------------------------------------------

    def _actualiser_label_mois_repos(self):
        noms_mois = [
            "Janvier", "Février", "Mars", "Avril", "Mai", "Juin",
            "Juillet", "Août", "Septembre", "Octobre", "Novembre", "Décembre",
        ]
        self.label_mois_repos.setText(f"{noms_mois[self.mois_repos - 1]} {self.annee_repos}")

    def _actualiser_visibilite_nav_mois(self, visible):
        self.bouton_mois_precedent.setVisible(visible)
        self.bouton_mois_suivant.setVisible(visible)
        self.label_mois_repos.setVisible(visible)

    def basculer_mode_repos(self, actif):
        self._actualiser_visibilite_nav_mois(actif)
        # En vue « repos », le filtre par type et la recherche n'ont pas
        # de sens (un jour sans sortie du type choisi ne veut pas dire
        # qu'il n'y a pas eu de sortie d'un autre type) — on les
        # neutralise pendant que la case est cochée, sans perdre leur
        # valeur pour autant.
        self.combo_type.setEnabled(not actif)
        self.champ_recherche.setEnabled(not actif)
        if actif:
            aujourd_hui = _date.today()
            self.annee_repos = aujourd_hui.year
            self.mois_repos = aujourd_hui.month
            self._actualiser_label_mois_repos()
        self.charger_activites()

    def _mois_precedent(self):
        self.mois_repos -= 1
        if self.mois_repos < 1:
            self.mois_repos = 12
            self.annee_repos -= 1
        self._actualiser_label_mois_repos()
        self.charger_activites()

    def _mois_suivant(self):
        self.mois_repos += 1
        if self.mois_repos > 12:
            self.mois_repos = 1
            self.annee_repos += 1
        self._actualiser_label_mois_repos()
        self.charger_activites()

    def ouvrir_menu_contextuel(self, position):
        ligne = self.table.currentRow()
        if ligne < 0:
            return

        item_date = self.table.item(ligne, 0)
        activite_id = item_date.data(Qt.ItemDataRole.UserRole) if item_date else None

        menu = QMenu(self)
        if activite_id is None:
            jour_repos = item_date.data(Qt.ItemDataRole.UserRole + 2) if item_date else None
            action_ajouter = menu.addAction("➕ Ajouter une sortie ce jour")
            action_choisie = menu.exec(self.table.viewport().mapToGlobal(position))
            if action_choisie == action_ajouter and jour_repos:
                self._ouvrir_nouvelle_sortie_pour_jour(jour_repos)
            return

        action_supprimer = menu.addAction("🗑 Supprimer cette sortie")
        action_choisie = menu.exec(self.table.viewport().mapToGlobal(position))
        if action_choisie == action_supprimer:
            self.supprimer_sortie(ligne)

    def supprimer_sortie(self, ligne):
        item_date = self.table.item(ligne, 0)
        activite_id = item_date.data(Qt.ItemDataRole.UserRole) if item_date else None
        nom_activite = item_date.data(Qt.ItemDataRole.UserRole + 1) if item_date else None
        if activite_id is None:
            return

        confirmation = QMessageBox.question(
            self,
            "Confirmer la suppression",
            f"Voulez-vous vraiment supprimer la sortie « {nom_activite or item_date.text()} » ?\n\n"
            "La trace GPS, les efforts sur segments et le compte rendu IA associés "
            "seront supprimés avec elle. Une séance planifiée liée redeviendra "
            "\"Prévue\" plutôt que d'être supprimée.\n\n"
            "Cette action est irréversible.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if confirmation != QMessageBox.StandardButton.Yes:
            return

        try:
            supprimer_activite(activite_id)
            self.charger_activites()
        except Exception as e:
            QMessageBox.critical(
                self, "Erreur de suppression",
                f"Impossible de supprimer cette sortie.\n\n{e}"
            )

    def ouvrir_analyse_ia(self):
        athlete_id = self.combo_athlete.currentData()
        if athlete_id is None:
            QMessageBox.information(self, "Sélection requise", "Sélectionne d'abord un athlète.")
            return

        ligne = self.table.currentRow()
        if ligne < 0:
            QMessageBox.information(
                self, "Sélection requise",
                "Sélectionne d'abord une sortie dans le tableau (clique sur sa ligne)."
            )
            return

        item_date = self.table.item(ligne, 0)
        activite_id = item_date.data(Qt.ItemDataRole.UserRole) if item_date else None
        nom_activite = item_date.data(Qt.ItemDataRole.UserRole + 1) if item_date else None
        if activite_id is None:
            QMessageBox.information(self, "Erreur", "Impossible d'identifier cette sortie.")
            return

        dialogue = DialogueAnalyseIA(activite_id, athlete_id, nom_activite, self)
        dialogue.exec()

    def ouvrir_selecteur_colonnes(self):
        dialogue = DialogueColonnes(self.colonnes_actives, self)
        if dialogue.exec() == QDialog.DialogCode.Accepted:
            self.colonnes_actives = dialogue.colonnes_selectionnees()
            definir_parametre(CLE_PARAMETRE_COLONNES, json.dumps(self.colonnes_actives))
            self._reconstruire_entetes()
            self.charger_activites()

    def _reconstruire_entetes(self):
        colonnes_a_afficher = ["date"] + [
            cle for cle in self.colonnes_actives if cle != "date"
        ]
        self.colonnes_affichees = colonnes_a_afficher

        libelles = {cle: label for cle, label, _, _ in DEFINITION_COLONNES}
        libelles["date"] = "Date"

        entetes = [libelles[cle].upper() for cle in colonnes_a_afficher]
        self.table.setColumnCount(len(entetes))
        self.table.setHorizontalHeaderLabels(entetes)

        # Le type de sortie s'affiche en pastille colorée (Trail, Course…)
        if not hasattr(self, "_delegue_pastille"):
            self._delegue_pastille = DelegatePastilleType(self.table)
            self._delegue_standard = QStyledItemDelegate(self.table)
        for col, cle in enumerate(colonnes_a_afficher):
            self.table.setItemDelegateForColumn(
                col, self._delegue_pastille if cle == "type" else self._delegue_standard)

    def _id_activite_pour_ligne(self, ligne):
        item_date = self.table.item(ligne, 0)
        return item_date.data(Qt.ItemDataRole.UserRole) if item_date else None

    def _apercu_pour_activite(self, activite_id):
        conn = connexion()
        cur = conn.cursor()
        cur.execute("SELECT nom, date, type FROM activites WHERE id=?", (activite_id,))
        ligne = cur.fetchone()
        if not ligne:
            conn.close()
            return None
        nom, date, type_ = ligne

        cur.execute("SELECT trace_json FROM parcours_gpx WHERE activite_id=? LIMIT 1", (activite_id,))
        resultat = cur.fetchone()
        conn.close()

        points = json.loads(resultat[0]) if resultat and resultat[0] else []
        return (nom or type_ or "(sans nom)", date or "", points)

    def charger_activites(self):
        athlete_id = self.combo_athlete.currentData()
        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)

        if athlete_id is None:
            self.label_total.setText("Sélectionne un athlète.")
            self.table.setSortingEnabled(True)
            return

        mode_repos = self.case_jours_repos.isChecked()
        colonnes_sql = ", ".join(["id", "date"] + CHAMPS_DB)
        noms_colonnes = ["id", "date"] + CHAMPS_DB

        conn = connexion()
        cur = conn.cursor()

        if mode_repos:
            # Vue combinée sorties + repos : toujours « Tous » les types,
            # bornée au mois affiché, un jour sans aucune sortie devenant
            # une ligne « Repos ».
            premier_jour = _date(self.annee_repos, self.mois_repos, 1)
            dernier_num_jour = _calendar.monthrange(self.annee_repos, self.mois_repos)[1]
            dernier_jour = _date(self.annee_repos, self.mois_repos, dernier_num_jour)

            cur.execute(
                f"SELECT {colonnes_sql} FROM activites WHERE athlete_id=? AND date >= ? AND date <= ?",
                (athlete_id, premier_jour.isoformat(), f"{dernier_jour.isoformat()}T23:59:59"),
            )
            lignes = [list(l) for l in cur.fetchall()]
            conn.close()

            index_date = noms_colonnes.index("date")
            index_nom = noms_colonnes.index("nom")
            index_type = noms_colonnes.index("type")
            jours_presents = {str(l[index_date])[:10] for l in lignes}

            aujourd_hui = _date.today()
            fin_reelle = min(dernier_jour, aujourd_hui)
            jour = premier_jour
            while jour <= fin_reelle:
                jour_iso = jour.isoformat()
                if jour_iso not in jours_presents:
                    ligne_repos = [None] * len(noms_colonnes)
                    ligne_repos[index_date] = jour_iso
                    ligne_repos[index_nom] = "Repos"
                    ligne_repos[index_type] = "😴 Repos"
                    lignes.append(ligne_repos)
                jour += _timedelta(days=1)
        else:
            type_filtre = self.combo_type.currentText()
            recherche = self.champ_recherche.text().strip().lower()

            if type_filtre == "Tous":
                cur.execute(
                    f"SELECT {colonnes_sql} FROM activites WHERE athlete_id=?",
                    (athlete_id,),
                )
            else:
                cur.execute(
                    f"SELECT {colonnes_sql} FROM activites WHERE athlete_id=? AND type=?",
                    (athlete_id, type_filtre),
                )
            lignes = cur.fetchall()
            conn.close()

            if recherche:
                index_nom = noms_colonnes.index("nom")
                lignes = [l for l in lignes if recherche in (l[index_nom] or "").lower()]

        types_par_cle = {cle: type_ for cle, _, type_, _ in DEFINITION_COLONNES}

        self.table.setRowCount(len(lignes))
        for i, ligne in enumerate(lignes):
            valeurs = dict(zip(noms_colonnes, ligne))
            est_repos = valeurs.get("id") is None

            date_obj = parser_date_flexible(valeurs.get("date"))
            if est_repos:
                date_affichee = date_obj.strftime("%d/%m/%Y") if date_obj else (valeurs.get("date") or "—")
            else:
                date_affichee = date_obj.strftime("%d/%m/%Y %H:%M") if date_obj else (valeurs.get("date") or "—")

            # Colonne 0 = Date, toujours affichée (voir _reconstruire_entetes).
            # L'id et le nom de l'activité sont attachés à cet item (UserRole)
            # pour être retrouvés par ligne cliquée quel que soit l'ordre de
            # tri courant de la table. Pour une ligne « Repos » (vue par
            # mois), l'id reste vide et la date brute (jour) est rangée en
            # UserRole+2 pour pouvoir proposer d'y saisir la sortie oubliée.
            item_date = ItemTrie(date_affichee, date_obj)
            item_date.setData(Qt.ItemDataRole.UserRole, valeurs.get("id"))
            item_date.setData(Qt.ItemDataRole.UserRole + 1, valeurs.get("nom"))
            if est_repos:
                item_date.setData(Qt.ItemDataRole.UserRole + 2, valeurs.get("date"))
            self.table.setItem(i, 0, item_date)

            if est_repos:
                for col, cle in enumerate(self.colonnes_affichees):
                    if cle == "date":
                        continue
                    texte = "😴 Repos" if cle in ("nom", "type") else "—"
                    item = QTableWidgetItem(texte)
                    item.setForeground(Qt.GlobalColor.gray)
                    self.table.setItem(i, col, item)
                continue

            for col, cle in enumerate(self.colonnes_affichees):
                if cle == "date":
                    continue

                if cle == "charge":
                    activite = {
                        "type": valeurs.get("type"),
                        "distance": valeurs.get("distance"),
                        "duree": valeurs.get("duree"),
                        "frequence_cardiaque_moyenne": valeurs.get("frequence_cardiaque_moyenne"),
                    }
                    charge, _methode = charge_activite_pour_athlete(activite, athlete_id)
                    texte, valeur_tri = _formater_valeur("nombre1", charge if charge else None)
                    self.table.setItem(i, col, ItemTrie(texte, valeur_tri))
                    continue

                if cle == "vo2max":
                    # Valeur mesurée par la montre si l'import l'a fournie,
                    # sinon estimation à partir de la performance (formule
                    # Daniels & Gilbert, déjà utilisée dans Analyses & Forme) —
                    # plus fiable sur un effort proche du maximal que sur une
                    # sortie tranquille.
                    vo2max_valeur = valeurs.get("vo2max")
                    if vo2max_valeur is None:
                        vo2max_valeur = estimer_vo2max(valeurs.get("distance"), valeurs.get("duree"))
                    texte, valeur_tri = _formater_valeur("nombre1", vo2max_valeur)
                    self.table.setItem(i, col, ItemTrie(texte, valeur_tri))
                    continue

                valeur_brute = valeurs.get(cle)
                texte, valeur_tri = _formater_valeur(types_par_cle.get(cle, "texte"), valeur_brute)
                if types_par_cle.get(cle) == "texte":
                    self.table.setItem(i, col, QTableWidgetItem(texte))
                else:
                    self.table.setItem(i, col, ItemTrie(texte, valeur_tri))

        self.table.setSortingEnabled(True)
        self.table.sortItems(0, Qt.SortOrder.DescendingOrder)
        self.table.resizeColumnsToContents()

        if mode_repos:
            nb_sorties = sum(1 for l in lignes if dict(zip(noms_colonnes, l)).get("id") is not None)
            nb_repos = len(lignes) - nb_sorties
            self.label_total.setText(f"{nb_sorties} sortie(s) · {nb_repos} jour(s) de repos")
        else:
            self.label_total.setText(f"{len(lignes)} activité(s)")
