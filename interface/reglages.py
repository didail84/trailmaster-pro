import shutil
from datetime import datetime

from PySide6.QtCore import Qt, QTime, QDate
from PySide6.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QLabel,
    QPushButton,
    QComboBox,
    QFrame,
    QFileDialog,
    QMessageBox,
    QScrollArea,
    QListWidget,
    QListWidgetItem,
    QLineEdit,
    QTimeEdit,
    QSpinBox,
    QDoubleSpinBox,
    QDateEdit,
    QTableWidget,
    QTableWidgetItem,
    QCheckBox,
)

from data.database import (
    CHEMIN_BDD, obtenir_athletes, obtenir_parametre, definir_parametre,
    emplacement_synchronise_actuel, activer_synchronisation, desactiver_synchronisation,
    affichage_simplifie_actif,
)
from interface.ecran_liste import obtenir_style_ecran
from interface.theme import (
    COULEURS_ACCENT, obtenir_couleur_accent, definir_couleur_accent, obtenir_version_installee,
    obtenir_mode_couleur, definir_mode_couleur,
)
from interface.dashboard_widgets import (
    WIDGETS_DISPONIBLES,
    obtenir_configuration_dashboard,
    definir_configuration_dashboard,
)
from interface.ia_coach import (
    obtenir_cle_api, definir_cle_api, cle_api_configuree,
    obtenir_cle_api_groq, definir_cle_api_groq, cle_api_groq_configuree,
)
from interface.rythme_vie import (
    obtenir_rythme_vie, definir_rythme_vie, amplitude_journee_minutes,
    obtenir_exceptions_rythme_vie, ajouter_exception_rythme_vie, supprimer_exception_rythme_vie,
    obtenir_seuil_journee_longue_min, definir_seuil_journee_longue_min,
)
from interface.serveur_local import (
    demarrer_serveur_local, arreter_serveur_local, serveur_actif, adresse_ip_locale, PORT_DEFAUT,
    obtenir_port_configure, definir_port_configure,
)
from interface.suivi_direct import obtenir_port_suivi_configure, definir_port_suivi_configure
from interface.coach import (
    obtenir_objectif_sommeil_heures, definir_objectif_sommeil_heures,
    obtenir_sensibilite_alertes, definir_sensibilite_alertes, SEUILS_SENSIBILITE_ALERTES,
)
from interface.export_ics import (
    obtenir_heure_debut_defaut, definir_heure_debut_defaut,
    obtenir_duree_defaut_min, definir_duree_defaut_min,
)
from interface.recherche_globale import obtenir_nb_resultats_max, definir_nb_resultats_max
from interface.allure_critique import obtenir_tolerance as obtenir_tolerance_allure_critique, definir_tolerance as definir_tolerance_allure_critique


class Reglages(QMainWindow):

    def __init__(self, athlete_id_initial=None):
        super().__init__()

        self.setWindowTitle("TrailMaster Pro – Réglages")
        self.resize(900, 800)
        self.setMinimumSize(750, 600)

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

        titre = QLabel("⚙️  Réglages")
        titre.setObjectName("titrePage")
        sous_titre = QLabel("Apparence, sauvegarde et préférences générales")
        sous_titre.setObjectName("sousTitrePage")
        principal.addWidget(titre)
        principal.addWidget(sous_titre)

        # ------------------------------------------------------------
        # APPARENCE
        # ------------------------------------------------------------

        cadre_apparence = QFrame()
        cadre_apparence.setObjectName("carteForm")
        apparence_layout = QVBoxLayout(cadre_apparence)

        titre_apparence = QLabel("🎨 Couleur de l'application")
        titre_apparence.setObjectName("titreCarte")
        apparence_layout.addWidget(titre_apparence)

        note_apparence = QLabel(
            "S'applique aux nouvelles fenêtres ouvertes après le changement "
            "(les fenêtres déjà ouvertes gardent l'ancienne couleur)."
        )
        note_apparence.setObjectName("texteSecondaire")
        note_apparence.setWordWrap(True)
        apparence_layout.addWidget(note_apparence)

        barre_couleurs = QHBoxLayout()
        self.boutons_couleur = {}
        couleur_actuelle = obtenir_couleur_accent()

        for nom, hex_couleur in COULEURS_ACCENT.items():
            bouton = QPushButton(nom)
            bouton.setCursor(Qt.CursorShape.PointingHandCursor)
            bouton.setMinimumHeight(50)
            bouton.setCheckable(True)
            bouton.setChecked(hex_couleur == couleur_actuelle)
            bouton.setStyleSheet(self._style_bouton_couleur(hex_couleur))
            bouton.clicked.connect(lambda checked, n=nom: self.choisir_couleur(n))
            self.boutons_couleur[nom] = bouton
            barre_couleurs.addWidget(bouton)

        apparence_layout.addLayout(barre_couleurs)

        titre_mode = QLabel("Mode sombre / clair")
        titre_mode.setObjectName("titreCarte")
        apparence_layout.addWidget(titre_mode)

        note_mode = QLabel(
            "Même règle que la couleur : s'applique aux nouvelles fenêtres ouvertes "
            "après le changement."
        )
        note_mode.setObjectName("texteSecondaire")
        note_mode.setWordWrap(True)
        apparence_layout.addWidget(note_mode)

        barre_mode = QHBoxLayout()
        self.boutons_mode = {}
        mode_actuel = obtenir_mode_couleur()
        for nom in ("Sombre", "Clair"):
            bouton = QPushButton(nom)
            bouton.setCursor(Qt.CursorShape.PointingHandCursor)
            bouton.setMinimumHeight(38)
            bouton.setCheckable(True)
            bouton.setChecked(nom == mode_actuel)
            bouton.clicked.connect(lambda checked, n=nom: self.choisir_mode_couleur(n))
            self.boutons_mode[nom] = bouton
            barre_mode.addWidget(bouton)
        apparence_layout.addLayout(barre_mode)

        principal.addWidget(cadre_apparence)

        # ------------------------------------------------------------
        # SAUVEGARDE
        # ------------------------------------------------------------

        cadre_sauvegarde = QFrame()
        cadre_sauvegarde.setObjectName("carteForm")
        sauvegarde_layout = QVBoxLayout(cadre_sauvegarde)

        titre_sauvegarde = QLabel("💾 Base de données")
        titre_sauvegarde.setObjectName("titreCarte")
        sauvegarde_layout.addWidget(titre_sauvegarde)

        self.label_chemin_bdd = QLabel(f"Emplacement actuel : {CHEMIN_BDD}")
        self.label_chemin_bdd.setObjectName("texteSecondaire")
        self.label_chemin_bdd.setWordWrap(True)
        sauvegarde_layout.addWidget(self.label_chemin_bdd)

        barre_sauvegarde = QHBoxLayout()
        bouton_sauvegarder = QPushButton("💾 Sauvegarder maintenant")
        bouton_sauvegarder.setObjectName("boutonPrincipal")
        bouton_sauvegarder.setCursor(Qt.CursorShape.PointingHandCursor)
        bouton_sauvegarder.clicked.connect(self.sauvegarder_maintenant)

        bouton_restaurer = QPushButton("Restaurer une sauvegarde")
        bouton_restaurer.setObjectName("boutonSecondaire")
        bouton_restaurer.setCursor(Qt.CursorShape.PointingHandCursor)
        bouton_restaurer.clicked.connect(self.restaurer_sauvegarde)

        barre_sauvegarde.addWidget(bouton_sauvegarder)
        barre_sauvegarde.addWidget(bouton_restaurer)
        barre_sauvegarde.addStretch()
        sauvegarde_layout.addLayout(barre_sauvegarde)

        self.label_resultat_sauvegarde = QLabel("")
        self.label_resultat_sauvegarde.setObjectName("texteSecondaire")
        self.label_resultat_sauvegarde.setWordWrap(True)
        sauvegarde_layout.addWidget(self.label_resultat_sauvegarde)

        principal.addWidget(cadre_sauvegarde)

        # ------------------------------------------------------------
        # SYNCHRONISATION ENTRE ORDINATEURS (Mac + Windows, gratuite)
        # ------------------------------------------------------------

        cadre_sync = QFrame()
        cadre_sync.setObjectName("carteForm")
        sync_layout = QVBoxLayout(cadre_sync)

        titre_sync = QLabel("🔄 Synchronisation entre ordinateurs")
        titre_sync.setObjectName("titreCarte")
        sync_layout.addWidget(titre_sync)

        note_sync = QLabel(
            "Utilise le même coureur sur ton Mac ET ton PC Windows, gratuitement, sans "
            "compte à créer : choisis un dossier déjà synchronisé sur cet ordinateur par "
            "un service gratuit (iCloud Drive, Google Drive, OneDrive, Dropbox...) — "
            "TrailMaster Pro y installe sa base, et le même dossier synchronisé sur "
            "l'autre ordinateur y donne accès aux mêmes données.\n\n"
            "⚠️ N'utilise qu'UN SEUL ordinateur à la fois : ferme complètement "
            "TrailMaster Pro avant de basculer sur l'autre machine, pour laisser le temps "
            "au service de synchronisation de terminer le transfert (comme pour tout "
            "fichier partagé de cette façon, une utilisation simultanée sur les deux "
            "risquerait d'abîmer la base)."
        )
        note_sync.setObjectName("texteSecondaire")
        note_sync.setWordWrap(True)
        sync_layout.addWidget(note_sync)

        self.label_statut_sync = QLabel("")
        self.label_statut_sync.setObjectName("texteSecondaire")
        self.label_statut_sync.setWordWrap(True)
        sync_layout.addWidget(self.label_statut_sync)

        barre_sync = QHBoxLayout()
        bouton_activer_sync = QPushButton("📂 Choisir un dossier synchronisé...")
        bouton_activer_sync.setObjectName("boutonPrincipal")
        bouton_activer_sync.clicked.connect(self.activer_sync)

        self.bouton_desactiver_sync = QPushButton("⏹ Revenir à une base locale")
        self.bouton_desactiver_sync.setObjectName("boutonSecondaire")
        self.bouton_desactiver_sync.clicked.connect(self.desactiver_sync)

        barre_sync.addWidget(bouton_activer_sync)
        barre_sync.addWidget(self.bouton_desactiver_sync)
        barre_sync.addStretch()
        sync_layout.addLayout(barre_sync)

        self._actualiser_statut_sync()
        principal.addWidget(cadre_sync)

        # ------------------------------------------------------------
        # TABLEAU DE BORD (cartes affichées + ordre)
        # ------------------------------------------------------------

        cadre_dashboard = QFrame()
        cadre_dashboard.setObjectName("carteForm")
        dashboard_layout = QVBoxLayout(cadre_dashboard)

        titre_dashboard = QLabel("📊 Tableau de bord")
        titre_dashboard.setObjectName("titreCarte")
        dashboard_layout.addWidget(titre_dashboard)

        note_dashboard = QLabel(
            "Coche les cartes à afficher, sélectionne-en une et utilise Monter/Descendre "
            "pour changer son ordre. S'applique à la prochaine ouverture du tableau de bord."
        )
        note_dashboard.setObjectName("texteSecondaire")
        note_dashboard.setWordWrap(True)
        dashboard_layout.addWidget(note_dashboard)

        self.liste_widgets_dashboard = QListWidget()
        self.liste_widgets_dashboard.setMinimumHeight(180)
        self._remplir_liste_widgets_dashboard()
        dashboard_layout.addWidget(self.liste_widgets_dashboard)

        barre_dashboard = QHBoxLayout()
        bouton_monter = QPushButton("⬆ Monter")
        bouton_monter.setObjectName("boutonSecondaire")
        bouton_monter.clicked.connect(self.monter_widget_dashboard)
        bouton_descendre = QPushButton("⬇ Descendre")
        bouton_descendre.setObjectName("boutonSecondaire")
        bouton_descendre.clicked.connect(self.descendre_widget_dashboard)
        bouton_enregistrer_dashboard = QPushButton("💾 Enregistrer cette disposition")
        bouton_enregistrer_dashboard.setObjectName("boutonPrincipal")
        bouton_enregistrer_dashboard.clicked.connect(self.enregistrer_disposition_dashboard)

        barre_dashboard.addWidget(bouton_monter)
        barre_dashboard.addWidget(bouton_descendre)
        barre_dashboard.addStretch()
        barre_dashboard.addWidget(bouton_enregistrer_dashboard)
        dashboard_layout.addLayout(barre_dashboard)

        principal.addWidget(cadre_dashboard)

        # ------------------------------------------------------------
        # ANALYSE IA (compte rendu par sortie, Gemini)
        # ------------------------------------------------------------

        cadre_ia = QFrame()
        cadre_ia.setObjectName("carteForm")
        ia_layout = QVBoxLayout(cadre_ia)

        titre_ia = QLabel("🤖 Analyse IA des sorties")
        titre_ia.setObjectName("titreCarte")
        ia_layout.addWidget(titre_ia)

        note_ia = QLabel(
            "Compte rendu automatique (points positifs, points à travailler, conseil pour "
            "la séance suivante) généré par IA — gratuite, sans carte bancaire. Nécessite "
            "une connexion internet à chaque analyse (comme Météo ou Carte réelle) et au "
            "moins une clé API personnelle ci-dessous.\n\n"
            "Seules des données chiffrées de performance et de forme sont envoyées "
            "(distance, allure, FC, charge, sommeil...) — jamais ton nom ni tes données "
            "personnelles."
        )
        note_ia.setObjectName("texteSecondaire")
        note_ia.setWordWrap(True)
        ia_layout.addWidget(note_ia)

        # --- Gemini (fournisseur principal) ---

        label_gemini = QLabel("Gemini (Google) — aistudio.google.com/apikey")
        label_gemini.setObjectName("labelChamp")
        ia_layout.addWidget(label_gemini)

        ligne_cle = QHBoxLayout()
        label_cle = QLabel("Clé API :")
        label_cle.setObjectName("labelChamp")
        self.champ_cle_api = QLineEdit()
        self.champ_cle_api.setEchoMode(QLineEdit.EchoMode.Password)
        self.champ_cle_api.setPlaceholderText("Colle ta clé API Gemini ici...")
        self.champ_cle_api.setText(obtenir_cle_api() or "")

        bouton_afficher_cle = QPushButton("👁")
        bouton_afficher_cle.setCheckable(True)
        bouton_afficher_cle.setFixedWidth(36)
        bouton_afficher_cle.setObjectName("boutonSecondaire")
        bouton_afficher_cle.toggled.connect(self._basculer_visibilite_cle)

        bouton_enregistrer_cle = QPushButton("💾 Enregistrer")
        bouton_enregistrer_cle.setObjectName("boutonPrincipal")
        bouton_enregistrer_cle.clicked.connect(self.enregistrer_cle_api)

        ligne_cle.addWidget(label_cle)
        ligne_cle.addWidget(self.champ_cle_api, 1)
        ligne_cle.addWidget(bouton_afficher_cle)
        ligne_cle.addWidget(bouton_enregistrer_cle)
        ia_layout.addLayout(ligne_cle)

        # --- Groq (secours automatique) ---

        label_groq = QLabel(
            "Groq (secours automatique, recommandé) — console.groq.com/keys\n"
            "Si Gemini ne répond pas (surchargé), le logiciel bascule tout seul sur Groq "
            "sans rien te demander — deux clés gratuites valent mieux qu'une."
        )
        label_groq.setObjectName("labelChamp")
        label_groq.setWordWrap(True)
        ia_layout.addWidget(label_groq)

        ligne_cle_groq = QHBoxLayout()
        label_cle_groq = QLabel("Clé API :")
        label_cle_groq.setObjectName("labelChamp")
        self.champ_cle_api_groq = QLineEdit()
        self.champ_cle_api_groq.setEchoMode(QLineEdit.EchoMode.Password)
        self.champ_cle_api_groq.setPlaceholderText("Colle ta clé API Groq ici (optionnel)...")
        self.champ_cle_api_groq.setText(obtenir_cle_api_groq() or "")

        bouton_afficher_cle_groq = QPushButton("👁")
        bouton_afficher_cle_groq.setCheckable(True)
        bouton_afficher_cle_groq.setFixedWidth(36)
        bouton_afficher_cle_groq.setObjectName("boutonSecondaire")
        bouton_afficher_cle_groq.toggled.connect(self._basculer_visibilite_cle_groq)

        bouton_enregistrer_cle_groq = QPushButton("💾 Enregistrer")
        bouton_enregistrer_cle_groq.setObjectName("boutonPrincipal")
        bouton_enregistrer_cle_groq.clicked.connect(self.enregistrer_cle_api_groq)

        ligne_cle_groq.addWidget(label_cle_groq)
        ligne_cle_groq.addWidget(self.champ_cle_api_groq, 1)
        ligne_cle_groq.addWidget(bouton_afficher_cle_groq)
        ligne_cle_groq.addWidget(bouton_enregistrer_cle_groq)
        ia_layout.addLayout(ligne_cle_groq)

        self.label_statut_ia = QLabel(self._texte_statut_ia())
        self.label_statut_ia.setObjectName("texteSecondaire")
        self.label_statut_ia.setWordWrap(True)
        ia_layout.addWidget(self.label_statut_ia)

        principal.addWidget(cadre_ia)

        # ------------------------------------------------------------
        # RYTHME DE VIE (semaine) — pris en compte dans la forme du jour
        # ------------------------------------------------------------

        cadre_rythme = QFrame()
        cadre_rythme.setObjectName("carteForm")
        rythme_layout = QVBoxLayout(cadre_rythme)

        titre_rythme = QLabel("⏰ Rythme de vie (semaine)")
        titre_rythme.setObjectName("titreCarte")
        rythme_layout.addWidget(titre_rythme)

        note_rythme = QLabel(
            "Lever, trajets et horaires de travail des jours de semaine — une source de "
            "fatigue en dehors de l'entraînement, pas mesurée par les sorties ou le sommeil. "
            "Une fois renseigné, ce rythme est automatiquement intégré à l'indice de forme du "
            "jour les jours de semaine où la journée est longue, mentionné dans le diagnostic "
            "de replanification automatique, et transmis à l'IA pour ses commentaires."
        )
        note_rythme.setObjectName("texteSecondaire")
        note_rythme.setWordWrap(True)
        rythme_layout.addWidget(note_rythme)

        grille_rythme = QGridLayout()
        grille_rythme.setHorizontalSpacing(15)
        grille_rythme.setVerticalSpacing(8)

        rythme_actuel = obtenir_rythme_vie() or {}

        def _heure_ou_defaut(cle, defaut):
            valeur = rythme_actuel.get(cle)
            if valeur:
                try:
                    h, m = valeur.split(":")
                    return QTime(int(h), int(m))
                except (ValueError, AttributeError):
                    pass
            return defaut

        self.champ_lever = QTimeEdit(_heure_ou_defaut("lever", QTime(4, 30)))
        self.champ_lever.setDisplayFormat("HH:mm")
        self.champ_depart_domicile = QTimeEdit(_heure_ou_defaut("depart_domicile", QTime(5, 0)))
        self.champ_depart_domicile.setDisplayFormat("HH:mm")

        self.champ_duree_trajet = QSpinBox()
        self.champ_duree_trajet.setRange(0, 240)
        self.champ_duree_trajet.setSuffix(" min")
        self.champ_duree_trajet.setValue(int(rythme_actuel.get("duree_trajet_min") or 45))

        self.champ_depart_travail = QTimeEdit(_heure_ou_defaut("depart_travail", QTime(17, 0)))
        self.champ_depart_travail.setDisplayFormat("HH:mm")
        self.champ_arrivee_domicile = QTimeEdit(_heure_ou_defaut("arrivee_domicile", QTime(18, 0)))
        self.champ_arrivee_domicile.setDisplayFormat("HH:mm")

        champs_rythme = [
            ("Lever :", self.champ_lever),
            ("Départ de la maison :", self.champ_depart_domicile),
            ("Durée du trajet (aller) :", self.champ_duree_trajet),
            ("Départ du travail (soir) :", self.champ_depart_travail),
            ("Arrivée à la maison (soir) :", self.champ_arrivee_domicile),
        ]
        for i, (label, widget) in enumerate(champs_rythme):
            lbl = QLabel(label)
            lbl.setObjectName("labelChamp")
            grille_rythme.addWidget(lbl, i, 0)
            grille_rythme.addWidget(widget, i, 1)

        rythme_layout.addLayout(grille_rythme)

        self.label_amplitude_rythme = QLabel("")
        self.label_amplitude_rythme.setObjectName("texteSecondaire")
        rythme_layout.addWidget(self.label_amplitude_rythme)

        barre_rythme = QHBoxLayout()
        bouton_enregistrer_rythme = QPushButton("💾 Enregistrer le rythme de vie")
        bouton_enregistrer_rythme.setObjectName("boutonPrincipal")
        bouton_enregistrer_rythme.clicked.connect(self.enregistrer_rythme_vie)
        barre_rythme.addStretch()
        barre_rythme.addWidget(bouton_enregistrer_rythme)
        rythme_layout.addLayout(barre_rythme)

        self.champ_lever.timeChanged.connect(self._actualiser_amplitude_rythme)
        self.champ_arrivee_domicile.timeChanged.connect(self._actualiser_amplitude_rythme)
        self._actualiser_amplitude_rythme()

        principal.addWidget(cadre_rythme)

        # ------------------------------------------------------------
        # RYTHME DE VIE — PÉRIODES EXCEPTIONNELLES
        # ------------------------------------------------------------

        cadre_exceptions = QFrame()
        cadre_exceptions.setObjectName("carteForm")
        exceptions_layout = QVBoxLayout(cadre_exceptions)

        titre_exceptions = QLabel("🧳 Périodes exceptionnelles (déplacement, astreinte...)")
        titre_exceptions.setObjectName("titreCarte")
        exceptions_layout.addWidget(titre_exceptions)

        note_exceptions = QLabel(
            "Pour une fatigue ponctuelle en dehors du rythme habituel — s'applique tous les "
            "jours de la période (y compris le week-end), sans reconfigurer tout le rythme "
            "hebdomadaire ci-dessus."
        )
        note_exceptions.setObjectName("texteSecondaire")
        note_exceptions.setWordWrap(True)
        exceptions_layout.addWidget(note_exceptions)

        barre_ajout_exception = QHBoxLayout()
        self.champ_exception_debut = QDateEdit()
        self.champ_exception_debut.setCalendarPopup(True)
        self.champ_exception_debut.setDate(QDate.currentDate())
        self.champ_exception_fin = QDateEdit()
        self.champ_exception_fin.setCalendarPopup(True)
        self.champ_exception_fin.setDate(QDate.currentDate())
        self.champ_exception_motif = QLineEdit()
        self.champ_exception_motif.setPlaceholderText("Motif (ex. déplacement pro, astreinte...)")
        self.combo_exception_niveau = QComboBox()
        self.combo_exception_niveau.addItems(["Journée longue", "Fatigue forte"])
        bouton_ajouter_exception = QPushButton("+ Ajouter")
        bouton_ajouter_exception.setObjectName("boutonSecondaire")
        bouton_ajouter_exception.clicked.connect(self.ajouter_exception_rythme_vie)

        barre_ajout_exception.addWidget(QLabel("Du :"))
        barre_ajout_exception.addWidget(self.champ_exception_debut)
        barre_ajout_exception.addWidget(QLabel("au :"))
        barre_ajout_exception.addWidget(self.champ_exception_fin)
        barre_ajout_exception.addWidget(self.champ_exception_motif, 1)
        barre_ajout_exception.addWidget(self.combo_exception_niveau)
        barre_ajout_exception.addWidget(bouton_ajouter_exception)
        exceptions_layout.addLayout(barre_ajout_exception)

        self.table_exceptions = QTableWidget()
        self.table_exceptions.setColumnCount(4)
        self.table_exceptions.setHorizontalHeaderLabels(["Du", "Au", "Motif", "Niveau"])
        self.table_exceptions.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table_exceptions.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table_exceptions.setMaximumHeight(150)
        exceptions_layout.addWidget(self.table_exceptions)

        bouton_supprimer_exception = QPushButton("Supprimer la période sélectionnée")
        bouton_supprimer_exception.setObjectName("boutonSecondaire")
        bouton_supprimer_exception.clicked.connect(self.supprimer_exception_rythme_vie)
        exceptions_layout.addWidget(bouton_supprimer_exception)

        principal.addWidget(cadre_exceptions)
        self.charger_exceptions_rythme_vie()

        # ------------------------------------------------------------
        # ALERTES ET OBJECTIFS
        # ------------------------------------------------------------

        cadre_alertes = QFrame()
        cadre_alertes.setObjectName("carteForm")
        alertes_layout = QVBoxLayout(cadre_alertes)

        titre_alertes = QLabel("🚨 Alertes et objectifs")
        titre_alertes.setObjectName("titreCarte")
        alertes_layout.addWidget(titre_alertes)

        note_alertes = QLabel(
            "Quelques seuils utilisés dans les calculs de forme, d'alertes de charge et "
            "d'export, personnalisables ici plutôt que fixés dans le code."
        )
        note_alertes.setObjectName("texteSecondaire")
        note_alertes.setWordWrap(True)
        alertes_layout.addWidget(note_alertes)

        # --- Objectif de sommeil ---

        grille_alertes = QGridLayout()
        grille_alertes.setHorizontalSpacing(15)
        grille_alertes.setVerticalSpacing(10)
        ligne_grille = 0

        label_sommeil = QLabel("Objectif d'heures de sommeil :")
        label_sommeil.setObjectName("labelChamp")
        self.champ_objectif_sommeil = QDoubleSpinBox()
        self.champ_objectif_sommeil.setRange(5.0, 10.0)
        self.champ_objectif_sommeil.setSingleStep(0.5)
        self.champ_objectif_sommeil.setSuffix(" h")
        self.champ_objectif_sommeil.setValue(obtenir_objectif_sommeil_heures())
        grille_alertes.addWidget(label_sommeil, ligne_grille, 0)
        grille_alertes.addWidget(self.champ_objectif_sommeil, ligne_grille, 1)
        ligne_grille += 1

        label_journee_longue = QLabel("Seuil \"journée longue\" (rythme de vie) :")
        label_journee_longue.setObjectName("labelChamp")
        self.champ_journee_longue = QDoubleSpinBox()
        self.champ_journee_longue.setRange(8.0, 16.0)
        self.champ_journee_longue.setSingleStep(0.5)
        self.champ_journee_longue.setSuffix(" h")
        self.champ_journee_longue.setValue(obtenir_seuil_journee_longue_min() / 60)
        grille_alertes.addWidget(label_journee_longue, ligne_grille, 0)
        grille_alertes.addWidget(self.champ_journee_longue, ligne_grille, 1)
        ligne_grille += 1

        label_heure_ics = QLabel("Export calendrier — heure de départ par défaut :")
        label_heure_ics.setObjectName("labelChamp")
        heure_h, heure_m = obtenir_heure_debut_defaut()
        self.champ_heure_ics = QTimeEdit(QTime(heure_h, heure_m))
        self.champ_heure_ics.setDisplayFormat("HH:mm")
        grille_alertes.addWidget(label_heure_ics, ligne_grille, 0)
        grille_alertes.addWidget(self.champ_heure_ics, ligne_grille, 1)
        ligne_grille += 1

        label_duree_ics = QLabel("Export calendrier — durée par défaut :")
        label_duree_ics.setObjectName("labelChamp")
        self.champ_duree_ics = QSpinBox()
        self.champ_duree_ics.setRange(10, 300)
        self.champ_duree_ics.setSingleStep(5)
        self.champ_duree_ics.setSuffix(" min")
        self.champ_duree_ics.setValue(obtenir_duree_defaut_min())
        grille_alertes.addWidget(label_duree_ics, ligne_grille, 0)
        grille_alertes.addWidget(self.champ_duree_ics, ligne_grille, 1)
        ligne_grille += 1

        label_nb_resultats = QLabel("Recherche globale — résultats max par catégorie :")
        label_nb_resultats.setObjectName("labelChamp")
        self.champ_nb_resultats = QSpinBox()
        self.champ_nb_resultats.setRange(10, 500)
        self.champ_nb_resultats.setSingleStep(10)
        self.champ_nb_resultats.setValue(obtenir_nb_resultats_max())
        grille_alertes.addWidget(label_nb_resultats, ligne_grille, 0)
        grille_alertes.addWidget(self.champ_nb_resultats, ligne_grille, 1)
        ligne_grille += 1

        label_tolerance = QLabel("Allure critique — tolérance de durée :")
        label_tolerance.setObjectName("labelChamp")
        self.champ_tolerance_allure = QSpinBox()
        self.champ_tolerance_allure.setRange(5, 60)
        self.champ_tolerance_allure.setSingleStep(5)
        self.champ_tolerance_allure.setSuffix(" %")
        self.champ_tolerance_allure.setValue(round(obtenir_tolerance_allure_critique() * 100))
        grille_alertes.addWidget(label_tolerance, ligne_grille, 0)
        grille_alertes.addWidget(self.champ_tolerance_allure, ligne_grille, 1)
        ligne_grille += 1

        alertes_layout.addLayout(grille_alertes)

        # --- Sensibilité des alertes de charge ---

        titre_sensibilite = QLabel("Sensibilité des alertes de charge (ACWR, séances manquées)")
        titre_sensibilite.setObjectName("titreCarte")
        alertes_layout.addWidget(titre_sensibilite)

        note_sensibilite = QLabel(
            "Déplace ensemble les seuils qui déclenchent les alertes et la replanification "
            "automatique — Prudent alerte plus tôt, Tolérant laisse plus de marge."
        )
        note_sensibilite.setObjectName("texteSecondaire")
        note_sensibilite.setWordWrap(True)
        alertes_layout.addWidget(note_sensibilite)

        barre_sensibilite = QHBoxLayout()
        self.boutons_sensibilite = {}
        sensibilite_actuelle = obtenir_sensibilite_alertes()
        for nom in SEUILS_SENSIBILITE_ALERTES:
            bouton = QPushButton(nom)
            bouton.setCursor(Qt.CursorShape.PointingHandCursor)
            bouton.setMinimumHeight(38)
            bouton.setCheckable(True)
            bouton.setChecked(nom == sensibilite_actuelle)
            bouton.clicked.connect(lambda checked, n=nom: self.choisir_sensibilite_alertes(n))
            self.boutons_sensibilite[nom] = bouton
            barre_sensibilite.addWidget(bouton)
        alertes_layout.addLayout(barre_sensibilite)

        bouton_enregistrer_alertes = QPushButton("💾 Enregistrer ces réglages")
        bouton_enregistrer_alertes.setObjectName("boutonPrincipal")
        bouton_enregistrer_alertes.clicked.connect(self.enregistrer_alertes_et_objectifs)
        alertes_layout.addWidget(bouton_enregistrer_alertes, 0, Qt.AlignmentFlag.AlignRight)

        principal.addWidget(cadre_alertes)

        # ------------------------------------------------------------
        # CONSULTATION RÉSEAU LOCAL
        # ------------------------------------------------------------

        cadre_serveur = QFrame()
        cadre_serveur.setObjectName("carteForm")
        self.cadre_serveur = cadre_serveur
        serveur_layout = QVBoxLayout(cadre_serveur)

        titre_serveur = QLabel("📶 Consultation réseau local (mobile)")
        titre_serveur.setObjectName("titreCarte")
        serveur_layout.addWidget(titre_serveur)

        note_serveur = QLabel(
            "Démarre un petit serveur en lecture seule (forme, ACWR, charge, alertes) "
            "consultable depuis un navigateur mobile connecté au même Wi-Fi que cet "
            "ordinateur — pas une vraie application, aucun accès depuis l'extérieur du "
            "réseau local, aucune écriture possible depuis la page."
        )
        note_serveur.setObjectName("texteSecondaire")
        note_serveur.setWordWrap(True)
        serveur_layout.addWidget(note_serveur)

        barre_serveur = QHBoxLayout()
        self.combo_athlete_serveur = QComboBox()
        for a in obtenir_athletes():
            self.combo_athlete_serveur.addItem(f"{a[2]} {a[1]}", a[0])
        self.bouton_serveur_local = QPushButton("▶️ Démarrer")
        self.bouton_serveur_local.setObjectName("boutonPrincipal")
        self.bouton_serveur_local.clicked.connect(self.basculer_serveur_local)
        barre_serveur.addWidget(self.combo_athlete_serveur)
        barre_serveur.addWidget(self.bouton_serveur_local)
        serveur_layout.addLayout(barre_serveur)

        barre_port = QHBoxLayout()
        label_port = QLabel("Port (à changer seulement s'il est déjà utilisé) :")
        label_port.setObjectName("labelChamp")
        self.champ_port_serveur = QSpinBox()
        self.champ_port_serveur.setRange(1024, 65535)
        self.champ_port_serveur.setValue(obtenir_port_configure())
        bouton_enregistrer_port = QPushButton("💾 Enregistrer le port")
        bouton_enregistrer_port.clicked.connect(self.enregistrer_port_serveur)
        barre_port.addWidget(label_port)
        barre_port.addWidget(self.champ_port_serveur)
        barre_port.addWidget(bouton_enregistrer_port)
        barre_port.addStretch()
        serveur_layout.addLayout(barre_port)

        self.label_adresse_serveur = QLabel("")
        self.label_adresse_serveur.setObjectName("texteSecondaire")
        self.label_adresse_serveur.setWordWrap(True)
        self.label_adresse_serveur.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        serveur_layout.addWidget(self.label_adresse_serveur)

        principal.addWidget(cadre_serveur)
        self._actualiser_etat_serveur_local()
        cadre_serveur.setVisible(not affichage_simplifie_actif())

        # ------------------------------------------------------------
        # SUIVI EN DIRECT
        # ------------------------------------------------------------

        cadre_suivi = QFrame()
        cadre_suivi.setObjectName("carteForm")
        suivi_layout = QVBoxLayout(cadre_suivi)

        titre_suivi = QLabel("📡 Suivi en direct")
        titre_suivi.setObjectName("titreCarte")
        suivi_layout.addWidget(titre_suivi)

        note_suivi = QLabel(
            "Port utilisé par le suivi en direct d'une sortie depuis le téléphone du coureur "
            "(distinct du port de consultation ci-dessus) — à changer seulement s'il est déjà "
            "utilisé par un autre logiciel sur cet ordinateur. Se démarre et s'arrête depuis "
            "l'écran « Suivi en direct »."
        )
        note_suivi.setObjectName("texteSecondaire")
        note_suivi.setWordWrap(True)
        suivi_layout.addWidget(note_suivi)

        barre_port_suivi = QHBoxLayout()
        label_port_suivi = QLabel("Port :")
        label_port_suivi.setObjectName("labelChamp")
        self.champ_port_suivi = QSpinBox()
        self.champ_port_suivi.setRange(1024, 65535)
        self.champ_port_suivi.setValue(obtenir_port_suivi_configure())
        bouton_enregistrer_port_suivi = QPushButton("💾 Enregistrer le port")
        bouton_enregistrer_port_suivi.clicked.connect(self.enregistrer_port_suivi)
        barre_port_suivi.addWidget(label_port_suivi)
        barre_port_suivi.addWidget(self.champ_port_suivi)
        barre_port_suivi.addWidget(bouton_enregistrer_port_suivi)
        barre_port_suivi.addStretch()
        suivi_layout.addLayout(barre_port_suivi)

        principal.addWidget(cadre_suivi)

        # ------------------------------------------------------------
        # GÉNÉRAL
        # ------------------------------------------------------------

        cadre_general = QFrame()
        cadre_general.setObjectName("carteForm")
        general_layout = QVBoxLayout(cadre_general)

        titre_general = QLabel("👤 Général")
        titre_general.setObjectName("titreCarte")
        general_layout.addWidget(titre_general)

        ligne_athlete = QHBoxLayout()
        label_athlete = QLabel("Athlète sélectionné par défaut à l'ouverture :")
        label_athlete.setObjectName("labelChamp")

        self.combo_athlete_defaut = QComboBox()
        self.combo_athlete_defaut.addItem("Tous les athlètes", None)
        athlete_par_defaut_id = obtenir_parametre("athlete_par_defaut")
        for a in obtenir_athletes():
            self.combo_athlete_defaut.addItem(f"{a[2]} {a[1]}", a[0])
            if athlete_par_defaut_id is not None and str(a[0]) == str(athlete_par_defaut_id):
                self.combo_athlete_defaut.setCurrentIndex(self.combo_athlete_defaut.count() - 1)

        self.combo_athlete_defaut.currentIndexChanged.connect(self.changer_athlete_defaut)

        ligne_athlete.addWidget(label_athlete)
        ligne_athlete.addWidget(self.combo_athlete_defaut)
        ligne_athlete.addStretch()
        general_layout.addLayout(ligne_athlete)

        principal.addWidget(cadre_general)

        # ------------------------------------------------------------
        # AFFICHAGE
        # ------------------------------------------------------------

        cadre_affichage = QFrame()
        cadre_affichage.setObjectName("carteForm")
        affichage_layout = QVBoxLayout(cadre_affichage)

        titre_affichage = QLabel("🧭 Affichage")
        titre_affichage.setObjectName("titreCarte")
        affichage_layout.addWidget(titre_affichage)

        self.case_affichage_simplifie = QCheckBox(
            "Affichage simplifié (masque les fonctions avancées : Programme Ultra, "
            "Replanification automatique, Tactique de course, Serveur local, "
            "Découplage cardiaque)"
        )
        self.case_affichage_simplifie.setChecked(affichage_simplifie_actif())
        self.case_affichage_simplifie.toggled.connect(self.basculer_affichage_simplifie)
        affichage_layout.addWidget(self.case_affichage_simplifie)

        note_affichage = QLabel(
            "Rien n'est supprimé : ces fonctions restent dans le logiciel, simplement "
            "masquées pour alléger les écrans. Décoche à tout moment pour les retrouver. "
            "Les écrans déjà ouverts doivent être refermés puis rouverts pour refléter le "
            "changement."
        )
        note_affichage.setObjectName("texteSecondaire")
        note_affichage.setWordWrap(True)
        affichage_layout.addWidget(note_affichage)

        principal.addWidget(cadre_affichage)

        label_version = QLabel(f"Version installée : {obtenir_version_installee()}")
        label_version.setObjectName("texteSecondaire")
        label_version.setAlignment(Qt.AlignmentFlag.AlignCenter)
        principal.addWidget(label_version)

        principal.addStretch()

        self.setStyleSheet(obtenir_style_ecran())

    def _style_bouton_couleur(self, hex_couleur):
        return f"""
            QPushButton {{
                background-color: {hex_couleur};
                color: white;
                border: 3px solid transparent;
                border-radius: 8px;
                font-weight: bold;
            }}
            QPushButton:checked {{
                border: 3px solid white;
            }}
        """

    def choisir_couleur(self, nom):
        definir_couleur_accent(nom)
        for autre_nom, bouton in self.boutons_couleur.items():
            bouton.setChecked(autre_nom == nom)
        QMessageBox.information(
            self, "Couleur appliquée",
            f"Couleur « {nom} » enregistrée. Elle s'appliquera aux prochaines fenêtres "
            "que tu ouvriras (ferme et rouvre les écrans déjà affichés pour la voir)."
        )

    def choisir_mode_couleur(self, nom):
        definir_mode_couleur(nom)
        for autre_nom, bouton in self.boutons_mode.items():
            bouton.setChecked(autre_nom == nom)
        QMessageBox.information(
            self, "Mode appliqué",
            f"Mode « {nom} » enregistré. Il s'appliquera aux prochaines fenêtres "
            "que tu ouvriras (ferme et rouvre les écrans déjà affichés pour le voir)."
        )

    def choisir_sensibilite_alertes(self, nom):
        for autre_nom, bouton in self.boutons_sensibilite.items():
            bouton.setChecked(autre_nom == nom)

    def enregistrer_alertes_et_objectifs(self):
        definir_objectif_sommeil_heures(self.champ_objectif_sommeil.value())
        definir_seuil_journee_longue_min(round(self.champ_journee_longue.value() * 60))
        definir_heure_debut_defaut(self.champ_heure_ics.time().toString("HH:mm"))
        definir_duree_defaut_min(self.champ_duree_ics.value())
        definir_nb_resultats_max(self.champ_nb_resultats.value())
        definir_tolerance_allure_critique(self.champ_tolerance_allure.value() / 100)

        nom_sensibilite = next(
            (nom for nom, bouton in self.boutons_sensibilite.items() if bouton.isChecked()),
            "Standard",
        )
        definir_sensibilite_alertes(nom_sensibilite)

        QMessageBox.information(
            self, "Réglages enregistrés",
            "Les nouveaux réglages d'alertes et d'objectifs sont pris en compte "
            "immédiatement dans les prochains calculs (forme, alertes, export)."
        )

    def enregistrer_port_serveur(self):
        definir_port_configure(self.champ_port_serveur.value())
        QMessageBox.information(
            self, "Port enregistré",
            "Le nouveau port sera utilisé au prochain démarrage du serveur local "
            "(arrête-le puis redémarre-le s'il tourne déjà)."
        )

    def enregistrer_port_suivi(self):
        definir_port_suivi_configure(self.champ_port_suivi.value())
        QMessageBox.information(
            self, "Port enregistré",
            "Le nouveau port sera utilisé au prochain suivi en direct démarré."
        )

    def _actualiser_amplitude_rythme(self):
        rythme = {
            "lever": self.champ_lever.time().toString("HH:mm"),
            "arrivee_domicile": self.champ_arrivee_domicile.time().toString("HH:mm"),
        }
        amplitude = amplitude_journee_minutes(rythme)
        if amplitude is None:
            self.label_amplitude_rythme.setText("")
            return
        h, m = divmod(amplitude, 60)
        texte_amplitude = f"{h}h{m:02d}" if m else f"{h}h"
        self.label_amplitude_rythme.setText(
            f"Amplitude de la journée (lever → retour à la maison) : environ {texte_amplitude}."
        )

    def enregistrer_rythme_vie(self):
        rythme = {
            "lever": self.champ_lever.time().toString("HH:mm"),
            "depart_domicile": self.champ_depart_domicile.time().toString("HH:mm"),
            "duree_trajet_min": self.champ_duree_trajet.value(),
            "depart_travail": self.champ_depart_travail.time().toString("HH:mm"),
            "arrivee_domicile": self.champ_arrivee_domicile.time().toString("HH:mm"),
        }
        definir_rythme_vie(rythme)
        self._actualiser_amplitude_rythme()
        QMessageBox.information(
            self, "Rythme de vie enregistré",
            "Ton rythme de semaine a été enregistré. Il sera pris en compte dès le "
            "prochain calcul de l'indice de forme et des futurs commentaires IA."
        )

    def charger_exceptions_rythme_vie(self):
        exceptions = obtenir_exceptions_rythme_vie()
        self.exceptions_ids = [e[0] for e in exceptions]
        self.table_exceptions.setRowCount(len(exceptions))
        for i, (_id, date_debut, date_fin, motif, niveau) in enumerate(exceptions):
            self.table_exceptions.setItem(i, 0, QTableWidgetItem(date_debut or ""))
            self.table_exceptions.setItem(i, 1, QTableWidgetItem(date_fin or ""))
            self.table_exceptions.setItem(i, 2, QTableWidgetItem(motif or ""))
            self.table_exceptions.setItem(i, 3, QTableWidgetItem(niveau or ""))
        self.table_exceptions.resizeColumnsToContents()

    def ajouter_exception_rythme_vie(self):
        date_debut = self.champ_exception_debut.date().toString("yyyy-MM-dd")
        date_fin = self.champ_exception_fin.date().toString("yyyy-MM-dd")
        if self.champ_exception_fin.date() < self.champ_exception_debut.date():
            QMessageBox.warning(self, "Dates invalides", "La date de fin doit être après la date de début.")
            return

        ajouter_exception_rythme_vie(
            date_debut, date_fin,
            self.champ_exception_motif.text().strip() or None,
            self.combo_exception_niveau.currentText(),
        )
        self.champ_exception_motif.clear()
        self.charger_exceptions_rythme_vie()

    def supprimer_exception_rythme_vie(self):
        ligne = self.table_exceptions.currentRow()
        if ligne < 0:
            QMessageBox.information(self, "Sélection requise", "Sélectionne d'abord une période.")
            return
        supprimer_exception_rythme_vie(self.exceptions_ids[ligne])
        self.charger_exceptions_rythme_vie()

    def _actualiser_etat_serveur_local(self):
        if serveur_actif():
            self.bouton_serveur_local.setText("⏹️ Arrêter")
            self.label_adresse_serveur.setText(
                f"Actif : http://{adresse_ip_locale()}:{PORT_DEFAUT} — ouvre cette adresse "
                "depuis le navigateur de ton téléphone (même Wi-Fi)."
            )
        else:
            self.bouton_serveur_local.setText("▶️ Démarrer")
            self.label_adresse_serveur.setText("Serveur arrêté.")

    def basculer_serveur_local(self):
        if serveur_actif():
            arreter_serveur_local()
            self._actualiser_etat_serveur_local()
            return

        athlete_id = self.combo_athlete_serveur.currentData()
        if athlete_id is None:
            QMessageBox.information(self, "Athlète requis", "Ajoute d'abord un athlète.")
            return

        succes, message = demarrer_serveur_local(athlete_id)
        if not succes:
            QMessageBox.warning(self, "Impossible de démarrer", message)
        self._actualiser_etat_serveur_local()

    def sauvegarder_maintenant(self):
        horodatage = datetime.now().strftime("%Y%m%d_%H%M%S")
        nom_suggere = f"trailmaster_sauvegarde_{horodatage}.db"

        chemin_destination, _ = QFileDialog.getSaveFileName(
            self, "Enregistrer la sauvegarde", nom_suggere, "Base de données (*.db)"
        )
        if not chemin_destination:
            return

        try:
            shutil.copy2(CHEMIN_BDD, chemin_destination)
            self.label_resultat_sauvegarde.setText(f"✅ Sauvegarde enregistrée : {chemin_destination}")
        except Exception as erreur:
            self.label_resultat_sauvegarde.setText(f"⚠️ Échec de la sauvegarde : {erreur}")

    def restaurer_sauvegarde(self):
        chemin_source, _ = QFileDialog.getOpenFileName(
            self, "Choisir une sauvegarde à restaurer", "", "Base de données (*.db)"
        )
        if not chemin_source:
            return

        confirmation = QMessageBox.question(
            self, "Confirmer la restauration",
            "Cette action va REMPLACER toutes les données actuelles par celles de "
            "cette sauvegarde. Cette action est irréversible (sauf si tu as toi-même "
            "une sauvegarde de l'état actuel).\n\nContinuer ?"
        )
        if confirmation != QMessageBox.StandardButton.Yes:
            return

        try:
            shutil.copy2(chemin_source, CHEMIN_BDD)
            self.label_resultat_sauvegarde.setText(
                "✅ Sauvegarde restaurée. Ferme et relance complètement TrailMaster Pro "
                "pour que les données restaurées apparaissent partout correctement."
            )
        except Exception as erreur:
            self.label_resultat_sauvegarde.setText(f"⚠️ Échec de la restauration : {erreur}")

    def _actualiser_statut_sync(self):
        emplacement = emplacement_synchronise_actuel()
        if emplacement:
            self.label_statut_sync.setText(f"✅ Synchronisée via : {emplacement}")
            self.bouton_desactiver_sync.setEnabled(True)
        else:
            self.label_statut_sync.setText("Base locale à cet ordinateur (pas de synchronisation active).")
            self.bouton_desactiver_sync.setEnabled(False)

    def activer_sync(self):
        dossier = QFileDialog.getExistingDirectory(
            self, "Choisis un dossier déjà synchronisé (iCloud Drive, Google Drive, OneDrive...)"
        )
        if not dossier:
            return

        confirmation = QMessageBox.question(
            self, "Confirmer la synchronisation",
            "TrailMaster Pro va utiliser ce dossier pour sa base de données à partir du "
            "prochain démarrage. Assure-toi qu'il s'agit bien d'un dossier synchronisé par "
            "iCloud Drive, Google Drive, OneDrive ou un service équivalent (déjà installé "
            "sur cet ordinateur), et que ce même dossier sera utilisé sur l'autre "
            "ordinateur.\n\nContinuer ?"
        )
        if confirmation != QMessageBox.StandardButton.Yes:
            return

        try:
            message = activer_synchronisation(dossier)
        except Exception as erreur:
            QMessageBox.warning(self, "Échec", f"Impossible d'activer la synchronisation : {erreur}")
            return

        self._actualiser_statut_sync()
        QMessageBox.information(
            self, "Synchronisation activée",
            f"{message}\n\nFerme et relance complètement TrailMaster Pro pour que le "
            "changement prenne effet. Fais de même sur l'autre ordinateur en choisissant "
            "ce même dossier synchronisé dans ses propres Réglages."
        )

    def desactiver_sync(self):
        confirmation = QMessageBox.question(
            self, "Revenir à une base locale",
            "TrailMaster Pro arrêtera d'utiliser le dossier synchronisé au prochain "
            "démarrage et reviendra à une base propre à cet ordinateur. Le dossier "
            "synchronisé et son contenu ne sont pas supprimés (l'autre ordinateur, s'il "
            "l'utilise encore, n'est pas affecté).\n\nContinuer ?"
        )
        if confirmation != QMessageBox.StandardButton.Yes:
            return

        desactiver_synchronisation()
        self._actualiser_statut_sync()
        QMessageBox.information(
            self, "Synchronisation désactivée",
            "Ferme et relance complètement TrailMaster Pro pour revenir à la base locale."
        )

    def _texte_statut_ia(self):
        gemini_ok = cle_api_configuree() and bool((obtenir_cle_api() or "").strip())
        groq_ok = cle_api_groq_configuree()
        if gemini_ok and groq_ok:
            return "✅ Gemini + Groq (secours) configurés — l'analyse IA est disponible et doublement sécurisée."
        if gemini_ok:
            return (
                "✅ Gemini configuré — l'analyse IA est disponible. Ajoute aussi une clé "
                "Groq (gratuite) pour un secours automatique en cas de surcharge de Gemini."
            )
        if groq_ok:
            return "✅ Groq configuré — l'analyse IA est disponible."
        return "⚠️ Aucune clé enregistrée — l'analyse IA est désactivée tant qu'aucune n'est renseignée."

    def _basculer_visibilite_cle(self, visible):
        self.champ_cle_api.setEchoMode(
            QLineEdit.EchoMode.Normal if visible else QLineEdit.EchoMode.Password
        )

    def _basculer_visibilite_cle_groq(self, visible):
        self.champ_cle_api_groq.setEchoMode(
            QLineEdit.EchoMode.Normal if visible else QLineEdit.EchoMode.Password
        )

    def enregistrer_cle_api(self):
        cle = self.champ_cle_api.text().strip()
        definir_cle_api(cle)
        self.label_statut_ia.setText(self._texte_statut_ia())
        if cle:
            QMessageBox.information(
                self, "Clé enregistrée",
                "La clé API Gemini a été enregistrée. Tu peux maintenant utiliser "
                "« 🤖 Analyse IA » depuis l'historique des activités."
            )

    def enregistrer_cle_api_groq(self):
        cle = self.champ_cle_api_groq.text().strip()
        definir_cle_api_groq(cle)
        self.label_statut_ia.setText(self._texte_statut_ia())
        if cle:
            QMessageBox.information(
                self, "Clé enregistrée",
                "La clé API Groq a été enregistrée. Elle servira automatiquement de "
                "secours si Gemini est indisponible."
            )

    def changer_athlete_defaut(self):
        athlete_id = self.combo_athlete_defaut.currentData()
        definir_parametre("athlete_par_defaut", athlete_id if athlete_id is not None else "")

    # ------------------------------------------------------------
    # AFFICHAGE SIMPLIFIÉ
    # ------------------------------------------------------------

    def basculer_affichage_simplifie(self, actif):
        definir_parametre("affichage_simplifie", "1" if actif else "0")
        self.cadre_serveur.setVisible(not actif)

    # ------------------------------------------------------------
    # TABLEAU DE BORD
    # ------------------------------------------------------------

    def _remplir_liste_widgets_dashboard(self):
        self.liste_widgets_dashboard.clear()

        configuration_actuelle = obtenir_configuration_dashboard()
        ids_dans_ordre = list(configuration_actuelle)
        for widget_id in WIDGETS_DISPONIBLES:
            if widget_id not in ids_dans_ordre:
                ids_dans_ordre.append(widget_id)

        for widget_id in ids_dans_ordre:
            info = WIDGETS_DISPONIBLES[widget_id]
            item = QListWidgetItem(info["nom"])
            item.setData(Qt.ItemDataRole.UserRole, widget_id)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(
                Qt.CheckState.Checked if widget_id in configuration_actuelle
                else Qt.CheckState.Unchecked
            )
            self.liste_widgets_dashboard.addItem(item)

    def monter_widget_dashboard(self):
        ligne = self.liste_widgets_dashboard.currentRow()
        if ligne <= 0:
            return
        item = self.liste_widgets_dashboard.takeItem(ligne)
        self.liste_widgets_dashboard.insertItem(ligne - 1, item)
        self.liste_widgets_dashboard.setCurrentRow(ligne - 1)

    def descendre_widget_dashboard(self):
        ligne = self.liste_widgets_dashboard.currentRow()
        if ligne < 0 or ligne >= self.liste_widgets_dashboard.count() - 1:
            return
        item = self.liste_widgets_dashboard.takeItem(ligne)
        self.liste_widgets_dashboard.insertItem(ligne + 1, item)
        self.liste_widgets_dashboard.setCurrentRow(ligne + 1)

    def enregistrer_disposition_dashboard(self):
        ids_actifs = []
        for i in range(self.liste_widgets_dashboard.count()):
            item = self.liste_widgets_dashboard.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                ids_actifs.append(item.data(Qt.ItemDataRole.UserRole))

        if not ids_actifs:
            QMessageBox.warning(
                self, "Au moins une carte",
                "Coche au moins une carte, sinon le tableau de bord serait vide."
            )
            return

        definir_configuration_dashboard(ids_actifs)
        QMessageBox.information(
            self, "Disposition enregistrée",
            "La nouvelle disposition sera appliquée à la prochaine ouverture "
            "du tableau de bord."
        )
