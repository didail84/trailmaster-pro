from PySide6.QtWidgets import (
    QMainWindow,
    QWidget,
    QHBoxLayout,
    QVBoxLayout,
    QLabel,
    QPushButton,
    QComboBox,
    QFrame,
    QScrollArea,
    QMessageBox,
    QStackedWidget,
    QApplication,
)

from PySide6.QtCore import Qt, QTimer, QEvent
from PySide6.QtGui import QPixmap

from interface.resultats_courses import ResultatsCourses
from interface.meteo_ecran import MeteoEcran
from interface.historique_activites import HistoriqueActivites
from interface.suivi_direct import SuiviDirect
from interface.cartes_et_traces import CartesEtTraces
from interface.photos_ecran import Photos
from interface.analyses_et_forme import AnalysesEtForme
from interface.performance_et_bilans import PerformanceTrail, BilansObjectifs
from interface.planification import Planification
from interface.suivi import Suivi
from interface.courses_calendrier import CoursesCalendrier
from interface.alimentation import AlimentationFenetre
from interface.materiel_course import MaterielCourse
from interface.import_et_synchro import ImportEtSynchro
from interface.renforcement import Renforcement
from interface.compte import Compte
from interface.recherche_globale import RechercheGlobale
from interface.sparkline import Sparkline
from interface.dashboard_widgets import obtenir_configuration_dashboard, WIDGETS_DISPONIBLES
from interface.theme import (
    obtenir_couleur_accent, eclaircir, obtenir_couleur_accent_douce, charger_polices,
    PALETTE, POLICE_TITRE, POLICE_TITRE_DEMI, POLICE_TEXTE, couleur_pour_pourcentage,
)
from interface.logo_widget import LogoMontagne
from interface.aujourdhui import EcranAujourdhui
from interface.verification_maj import texte_version, VerificationMajThread, proposer_mise_a_jour
from interface.outils_ui import notifier, PaletteCommandes, installer_raccourcis, AIDE_RACCOURCIS
from interface.courbe_widget import CourbeBarres
from interface.courbe_multiligne import CourbeMultiLignes
from interface.coach import (
    calculer_acwr,
    calculer_score_forme_jour,
    calculer_serie_forme,
    obtenir_charges_journalieres,
    obtenir_charges_periode,
    obtenir_mesure_periode,
    obtenir_date_premiere_activite,
    generer_alertes,
    serie_rythme_vie_actif,
    serie_resultats_courses,
    obtenir_indicateurs_couleur,
    PERIODES_DISPONIBLES,
    MESURES_CUMULABLES,
)
from data.database import (
    obtenir_athletes, obtenir_parametre, definir_parametre, obtenir_athlete_par_id,
    affichage_simplifie_actif,
)
import json
from interface.photo_athlete import pixmap_circulaire
from interface.apercu_widgets import ApercuCartes, ApercuCourbe, DernieresSorties
from interface.detail_sortie import DialogueDetailSortie
from interface.detail_carte import DialogueDetailCarte, DialogueAlertes, FiltreClicCarte

class TableauBord(QMainWindow):
    def __init__(self):
        super().__init__()

        charger_polices()

        self.setWindowTitle("TrailMaster Pro - Tableau de bord")
        self.resize(1200, 800)

        self.athlete_actif_id = None

        # Fenêtres secondaires déjà ouvertes (clé -> instance) — un
        # deuxième clic sur le même bouton de menu ramène la fenêtre
        # existante au premier plan au lieu d'en ouvrir une deuxième.
        self._fenetres_ouvertes = {}
        # U1 — fenêtre unique : boutons du menu, bouton cliqué, bouton par écran
        self._boutons_menu = []
        self._bouton_clique = None
        self._cle_vers_bouton = {}

        # Widget principal
        central = QWidget()
        self.setCentralWidget(central)

        # Layout principal horizontal
        layout_principal = QHBoxLayout(central)
        layout_principal.setContentsMargins(0, 0, 0, 0)
        layout_principal.setSpacing(0)

        # =========================
        # MENU LATERAL
        # =========================

        menu = QFrame()
        menu.setObjectName("menu")

        menu_layout = QVBoxLayout(menu)
        menu_layout.setContentsMargins(16, 24, 16, 22)
        menu_layout.setSpacing(4)

        entete_logo = QHBoxLayout()
        entete_logo.setSpacing(9)
        entete_logo.addWidget(LogoMontagne(26))
        logo = QLabel("TRAILMASTER")
        logo.setObjectName("logo")
        entete_logo.addWidget(logo)
        entete_logo.addStretch()
        menu_layout.addLayout(entete_logo)

        sous_logo = QLabel("PRO")
        sous_logo.setObjectName("sousLogo")
        menu_layout.addWidget(sous_logo)
        menu_layout.addSpacing(20)

        # Recherche globale — accessible en permanence en haut du menu,
        # en dehors des groupes (elle cherche à travers toutes les
        # catégories, elle n'appartient à aucune en particulier).
        bouton_recherche = QPushButton("🔎  Rechercher partout…")
        bouton_recherche.setObjectName("boutonRechercheGlobale")
        bouton_recherche.setCursor(Qt.CursorShape.PointingHandCursor)
        bouton_recherche.clicked.connect(self.ouvrir_recherche_globale)
        menu_layout.addWidget(bouton_recherche)
        menu_layout.addSpacing(14)

        # Boutons du menu, groupés par section — même organisation que
        # les écrans réels, pour que le menu serve de plan du logiciel.
        groupes = [
            ("ENTRAÎNEMENT", [
                ("☀️  Aujourd'hui", self.ouvrir_aujourdhui, True),
                ("🏠  Tableau de bord", self.ouvrir_tableau_de_bord, False),
                ("📓  Journal", self.ouvrir_journal, False),
                ("📋  Historique des activités", self.ouvrir_historique_activites, False),
                ("📡  Suivi en direct", self.ouvrir_suivi_direct, False),
                ("🗺️  Cartes && Traces", self.ouvrir_cartes_et_traces, False),
                ("📷  Photos", self.ouvrir_photos, False),
                ("📅  Planification", self.ouvrir_planification, False),
                ("💪  Renforcement && Mobilité", self.ouvrir_renforcement, False),
            ]),
            ("ANALYSE", [
                ("📊  Analyses && Forme", self.ouvrir_analyses_et_forme, False),
                ("🏔️  Performance trail", self.ouvrir_performance_trail, False),
                ("📆  Bilans && objectifs", self.ouvrir_bilans_objectifs, False),
                ("📋  Suivi", self.ouvrir_suivi, False),
                ("🏆  Résultats de courses", self.ouvrir_resultats_courses, False),
                ("🏁  Courses à venir", self.ouvrir_courses_calendrier, False),
                ("🎒  Matériel pour une course", self.ouvrir_materiel_course, False),
            ]),
            ("OUTILS", [
                ("🌦️  Météo", self.ouvrir_meteo, False),
                ("🍎  Alimentation", self.ouvrir_alimentation, False),
                ("📥  Import && Synchro", self.ouvrir_import_et_synchro, False),
            ]),
            ("COMPTE", [
                ("👤  Athlètes", self.ouvrir_athletes, False),
                ("⚙️  Réglages", self.ouvrir_reglages, False),
            ]),
        ]

        # Groupes du menu repliables/dépliables (accordéon) — l'état
        # ouvert/fermé de chaque groupe est mémorisé (Réglages ne s'en
        # occupe pas, c'est purement un confort de navigation) pour
        # rester tel quel d'une session à l'autre. Cela ne change rien
        # au comportement des boutons eux-mêmes : ils continuent
        # d'ouvrir leur fenêtre dans une fenêtre séparée comme avant,
        # seul l'affichage de la liste dans le menu se replie.
        self._groupes_conteneurs = {}
        self._groupes_ouverts = {}
        etats_ouverts = self._charger_etats_groupes_menu()

        for nom_groupe, items in groupes:
            ouvert = etats_ouverts.get(nom_groupe, True)

            bouton_groupe = QPushButton(f"{'▾' if ouvert else '▸'}  {nom_groupe}")
            bouton_groupe.setObjectName("boutonGroupeMenu")
            bouton_groupe.setCursor(Qt.CursorShape.PointingHandCursor)
            menu_layout.addWidget(bouton_groupe)

            conteneur_groupe = QWidget()
            conteneur_layout = QVBoxLayout(conteneur_groupe)
            conteneur_layout.setContentsMargins(0, 0, 0, 0)
            conteneur_layout.setSpacing(4)

            for texte, gestionnaire, actif in items:
                bouton = QPushButton(texte)
                bouton.setObjectName("boutonMenuActif" if actif else "boutonMenu")
                bouton.setCursor(Qt.CursorShape.PointingHandCursor)
                if gestionnaire is not None:
                    bouton.clicked.connect(
                        lambda _checked=False, b=bouton, g=gestionnaire: self._clic_menu(b, g)
                    )
                self._boutons_menu.append(bouton)
                conteneur_layout.addWidget(bouton)

            conteneur_groupe.setVisible(ouvert)
            menu_layout.addWidget(conteneur_groupe)

            self._groupes_conteneurs[nom_groupe] = conteneur_groupe
            self._groupes_ouverts[nom_groupe] = ouvert
            bouton_groupe.clicked.connect(
                lambda _checked=False, nom=nom_groupe, b=bouton_groupe: self._basculer_groupe_menu(nom, b)
            )

        menu_layout.addStretch()

        carte_athlete_menu = QFrame()
        carte_athlete_menu.setObjectName("carteAthleteMenu")
        carte_athlete_menu_layout = QVBoxLayout(carte_athlete_menu)
        carte_athlete_menu_layout.setContentsMargins(12, 10, 12, 10)
        # U7 — interrupteur Simple / Complet
        self.bouton_mode = QPushButton()
        self.bouton_mode.setObjectName("boutonModeAffichage")
        self.bouton_mode.setCursor(Qt.CursorShape.PointingHandCursor)
        self.bouton_mode.clicked.connect(self.basculer_mode_affichage)
        carte_athlete_menu_layout.addWidget(self.bouton_mode)
        self._rafraichir_bouton_mode()

        # U10 — vraie version + mise à jour en un clic
        version = QLabel(f"TrailMaster Pro · {texte_version()}")
        version.setObjectName("version")
        carte_athlete_menu_layout.addWidget(version)
        self.bouton_maj = QPushButton("Vérifier les mises à jour")
        self.bouton_maj.setObjectName("boutonMajMenu")
        self.bouton_maj.setCursor(Qt.CursorShape.PointingHandCursor)
        self.bouton_maj.clicked.connect(self.verifier_maj_maintenant)
        carte_athlete_menu_layout.addWidget(self.bouton_maj)
        self._resultat_maj = None
        self._fil_maj = None
        menu_layout.addWidget(carte_athlete_menu)

        # =========================
        # ZONE PRINCIPALE
        # =========================

        contenu = QFrame()
        contenu.setObjectName("contenu")

        contenu_layout = QVBoxLayout(contenu)
        contenu_layout.setContentsMargins(40, 35, 40, 35)
        contenu_layout.setSpacing(20)

        titre = QLabel("Tableau de bord")
        titre.setObjectName("titre")

        bienvenue = QLabel(
            "Bienvenue dans TrailMaster Pro — centre de pilotage de l'entraînement."
        )
        bienvenue.setObjectName("bienvenue")

        contenu_layout.addWidget(titre)
        contenu_layout.addWidget(bienvenue)
        contenu_layout.addSpacing(10)

        # =========================
        # SÉLECTEUR D'ATHLÈTE ACTIF
        # =========================

        barre_athlete = QHBoxLayout()
        label_athlete = QLabel("Athlète actif :")
        label_athlete.setObjectName("labelAthleteActif")

        self.combo_athlete_actif = QComboBox()
        self.combo_athlete_actif.setObjectName("comboAthleteActif")
        self.combo_athlete_actif.addItem("Tous les athlètes", None)
        for a in obtenir_athletes():
            self.combo_athlete_actif.addItem(f"{a[2]} {a[1]}", a[0])

        athlete_par_defaut_id = obtenir_parametre("athlete_par_defaut")
        if athlete_par_defaut_id:
            for i in range(self.combo_athlete_actif.count()):
                if str(self.combo_athlete_actif.itemData(i)) == str(athlete_par_defaut_id):
                    self.combo_athlete_actif.setCurrentIndex(i)
                    break
        elif self.combo_athlete_actif.count() > 1:
            # aucun athlète par défaut : on affiche le premier plutôt qu'un tableau vide
            self.combo_athlete_actif.setCurrentIndex(1)
        self.athlete_actif_id = self.combo_athlete_actif.currentData()

        self.combo_athlete_actif.currentIndexChanged.connect(
            self.changer_athlete_actif
        )

        barre_athlete.addWidget(label_athlete)
        barre_athlete.addWidget(self.combo_athlete_actif)
        barre_athlete.addStretch()

        contenu_layout.addLayout(barre_athlete)
        contenu_layout.addSpacing(10)

        # =========================
        # CARTES DU TABLEAU DE BORD (configurables depuis Réglages)
        # =========================

        self._construire_widgets_dashboard(contenu_layout)
        self._installer_raccourcis()
        QTimer.singleShot(2500, lambda: self.verifier_maj_maintenant(silencieux=True))

        # Ajout au layout principal
        menu_scroll = QScrollArea()
        menu_scroll.setObjectName("menuScroll")
        menu_scroll.setWidget(menu)
        menu_scroll.setWidgetResizable(True)
        menu_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        menu_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        menu_scroll.setFixedWidth(240)
        menu_scroll.setFrameShape(QFrame.Shape.NoFrame)
        menu_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        contenu_scroll = QScrollArea()
        contenu_scroll.setObjectName("contenuScroll")
        contenu_scroll.setWidget(contenu)
        contenu_scroll.setWidgetResizable(True)
        contenu_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        contenu_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        contenu_scroll.setFrameShape(QFrame.Shape.NoFrame)
        contenu_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        # U1 — une seule fenêtre : pile de pages (Aujourd'hui, Tableau de
        # bord, puis chaque écran ouvert depuis le menu).
        self.pile = QStackedWidget()
        athletes_liste = [(a[0], f"{a[2]} {a[1]}") for a in obtenir_athletes()]
        self.page_aujourdhui = EcranAujourdhui(
            self._navigation_aujourdhui(), athletes_liste, self.athlete_actif_id
        )
        self.page_chargement = QLabel("Chargement…")
        self.page_chargement.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.page_chargement.setStyleSheet(f"font-size:18px; color:{PALETTE['texte_secondaire']};")
        self.contenu_scroll = contenu_scroll
        self.pile.addWidget(self.page_aujourdhui)
        self.pile.addWidget(contenu_scroll)
        self.pile.addWidget(self.page_chargement)
        self.pile.setCurrentWidget(self.page_aujourdhui)

        layout_principal.addWidget(menu_scroll)
        layout_principal.addWidget(self.pile, 1)
        QTimer.singleShot(1200, self._ajustement_matin)
        QTimer.singleShot(7000, self._synchro_garmin_auto)

        # =========================
        # STYLE
        # =========================

        feuille_style = """
            QMainWindow {
                background-color: PALETTE_FOND;
            }

            QWidget {
                font-family: 'POLICE_TEXTE', 'Segoe UI', sans-serif;
            }

            #menu {
                background-color: PALETTE_FOND_SECONDAIRE;
                border-right: 1px solid PALETTE_BORDURE;
            }

            #menuScroll {
                background-color: PALETTE_FOND_SECONDAIRE;
                border: none;
                border-right: 1px solid PALETTE_BORDURE;
            }

            #contenu {
                background-color: PALETTE_FOND;
            }

            #contenuScroll {
                background-color: PALETTE_FOND;
                border: none;
            }

            QScrollBar:vertical, QScrollBar:horizontal {
                background-color: transparent;
                width: 10px;
                height: 10px;
                margin: 0px;
            }

            QScrollBar::handle:vertical, QScrollBar::handle:horizontal {
                background-color: PALETTE_BORDURE;
                border-radius: 5px;
                min-height: 30px;
                min-width: 30px;
            }

            QScrollBar::handle:vertical:hover, QScrollBar::handle:horizontal:hover {
                background-color: #384048;
            }

            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical,
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
                height: 0px;
                width: 0px;
            }

            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical,
            QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {
                background: none;
            }

            #logo {
                color: PALETTE_TEXTE;
                font-family: 'POLICE_TITRE_EXTRA';
                font-size: 15.5px;
                font-weight: 800;
            }

            #sousLogo {
                color: ACCENT_COLOR;
                font-family: 'POLICE_TITRE';
                font-size: 11px;
                font-weight: 700;
                letter-spacing: 2px;
                padding-left: 2px;
            }

            #labelGroupeMenu {
                color: #4A535A;
                font-size: 10.5px;
                font-weight: 700;
                padding: 14px 8px 5px 8px;
            }

            #boutonRechercheGlobale {
                background-color: PALETTE_CARTE;
                color: PALETTE_TEXTE_SECONDAIRE;
                border: 1px solid PALETTE_BORDURE;
                border-radius: 9px;
                text-align: left;
                padding: 9px 10px;
                font-size: 12.5px;
            }

            #boutonRechercheGlobale:hover {
                color: PALETTE_TEXTE;
                border-color: ACCENT_DOUCE;
            }

            #boutonGroupeMenu {
                background-color: transparent;
                color: #4A535A;
                border: none;
                text-align: left;
                font-size: 10.5px;
                font-weight: 700;
                padding: 14px 8px 5px 8px;
            }

            #boutonGroupeMenu:hover {
                color: PALETTE_TEXTE_SECONDAIRE;
            }

            #boutonMenu {
                background-color: transparent;
                color: PALETTE_TEXTE_SECONDAIRE;
                border: none;
                border-radius: 9px;
                text-align: left;
                padding: 9px 10px;
                font-size: 13px;
            }

            #boutonMenu:hover {
                background-color: PALETTE_CARTE;
                color: PALETTE_TEXTE;
            }

            #boutonMenuActif {
                background-color: ACCENT_DOUCE;
                color: PALETTE_TEXTE;
                border: none;
                border-radius: 9px;
                text-align: left;
                padding: 9px 10px;
                font-size: 13px;
                font-weight: 600;
            }

            #boutonModeAffichage {
                background-color: PALETTE_FOND;
                color: PALETTE_TEXTE;
                border: 1px solid PALETTE_BORDURE;
                border-radius: 8px;
                padding: 7px 8px;
                font-size: 12px;
                font-weight: 600;
            }

            #boutonModeAffichage:hover {
                border-color: ACCENT_COLOR;
            }

            #boutonMajMenu {
                background: transparent;
                color: PALETTE_TEXTE_SECONDAIRE;
                border: none;
                text-align: left;
                padding: 4px 2px;
                font-size: 11px;
            }

            #boutonMajMenu:hover {
                color: ACCENT_COLOR;
            }

            #carteAthleteMenu {
                background-color: PALETTE_CARTE;
                border: 1px solid PALETTE_BORDURE_DOUCE;
                border-radius: 12px;
                margin-top: 8px;
            }

            #titre {
                color: PALETTE_TEXTE;
                font-family: 'POLICE_TITRE';
                font-size: 26px;
                font-weight: 700;
            }

            #bienvenue {
                color: PALETTE_TEXTE_SECONDAIRE;
                font-size: 13.5px;
            }

            #labelAthleteActif {
                color: PALETTE_TEXTE_SECONDAIRE;
                font-size: 13px;
            }

            #comboAthleteActif {
                background-color: PALETTE_CARTE;
                color: PALETTE_TEXTE;
                border: 1px solid PALETTE_BORDURE;
                border-radius: 8px;
                padding: 7px 10px;
                min-width: 220px;
            }

            #comboAthleteActif QAbstractItemView {
                background-color: PALETTE_CARTE;
                color: PALETTE_TEXTE;
                selection-background-color: ACCENT_COLOR;
            }

            #comboPeriode {
                background-color: PALETTE_CARTE_HAUTE;
                color: PALETTE_TEXTE;
                border: 1px solid PALETTE_BORDURE;
                border-radius: 8px;
                padding: 5px 10px;
                min-width: 140px;
            }

            #comboPeriode QAbstractItemView {
                background-color: PALETTE_CARTE_HAUTE;
                color: PALETTE_TEXTE;
                selection-background-color: ACCENT_COLOR;
            }

            #carte {
                background-color: PALETTE_CARTE;
                border: 1px solid PALETTE_BORDURE;
                border-radius: 16px;
            }

            #carte:hover {
                border-color: ACCENT_COLOR;
            }

            #carteGrande {
                background-color: PALETTE_CARTE;
                border: 1px solid PALETTE_BORDURE;
                border-radius: 14px;
            }

            #titreCarte {
                color: PALETTE_TEXTE_DISCRET;
                font-size: 11px;
                font-weight: 700;
            }

            #valeurCarte {
                color: PALETTE_TEXTE;
                font-family: 'POLICE_TITRE';
                font-size: 32px;
                font-weight: 800;
            }

            #texteSecondaire {
                color: PALETTE_TEXTE_SECONDAIRE;
                font-size: 12px;
            }

            #version {
                color: #4A535A;
                font-size: 11px;
            }
        """

        accent = obtenir_couleur_accent()
        self.setStyleSheet(
            feuille_style
            .replace("ACCENT_DOUCE", obtenir_couleur_accent_douce(0.16))
            .replace("ACCENT_COLOR", accent)
            .replace("ACCENT_HOVER", eclaircir(accent))
            .replace("PALETTE_FOND_SECONDAIRE", PALETTE["fond_secondaire"])
            .replace("PALETTE_FOND", PALETTE["fond"])
            .replace("PALETTE_CARTE_HAUTE", PALETTE["carte_haute"])
            .replace("PALETTE_CARTE", PALETTE["carte"])
            .replace("PALETTE_BORDURE_DOUCE", PALETTE["bordure_douce"])
            .replace("PALETTE_BORDURE", PALETTE["bordure"])
            .replace("PALETTE_TEXTE_SECONDAIRE", PALETTE["texte_secondaire"])
            .replace("PALETTE_TEXTE_DISCRET", PALETTE["texte_discret"])
            .replace("PALETTE_TEXTE", PALETTE["texte"])
            .replace("POLICE_TITRE_EXTRA", "Sora ExtraBold")
            .replace("POLICE_TITRE", POLICE_TITRE)
            .replace("POLICE_TEXTE", POLICE_TEXTE)
        )

        self.actualiser_dashboard()

    # ------------------------------------------------------------
    # CONSTRUCTION DYNAMIQUE DES CARTES (configurable dans Réglages)
    # ------------------------------------------------------------

    CONSTRUCTEURS_WIDGETS = {
        "alertes_proactives": "_construire_carte_alertes_proactives",
        "apercu_cartes": "_construire_apercu_cartes",
        "apercu_courbe": "_construire_apercu_courbe",
        "dernieres_sorties": "_construire_dernieres_sorties",
        "fiche_coureur": "_construire_fiche_coureur",
        "charge_semaine": "_construire_carte_charge_semaine",
        "entrainements_semaine": "_construire_carte_entrainements",
        "forme": "_construire_carte_forme",
        "acwr": "_construire_carte_acwr",
        "indice_forme": "_construire_carte_indice_forme",
        "distance_cumulee": "_construire_carte_distance_cumulee",
        "denivele_cumule": "_construire_carte_denivele_cumule",
        "duree_cumulee": "_construire_carte_duree_cumulee",
        "graphique_charge": "_construire_graphique_charge",
        "graphique_sur_mesure": "_construire_graphique_sur_mesure",
        "mini_forme_fatigue": "_construire_mini_forme_fatigue",
        "tableau_croise": "_construire_tableau_croise",
    }

    # Périodes rapides proposées sur les petites cartes cumulées — un
    # sous-ensemble de PERIODES_DISPONIBLES, la carte étant trop petite
    # pour afficher un sélecteur aussi long que sur le grand graphique.
    PERIODES_CARTES_CUMULEES = [
        ("Semaine", 7), ("Mois", 30), ("Année", 365), ("Tout", None),
    ]

    def _construire_widgets_dashboard(self, contenu_layout):
        configuration = obtenir_configuration_dashboard()

        ligne_courante = None
        nb_dans_ligne = 0

        for widget_id in configuration:
            info = WIDGETS_DISPONIBLES.get(widget_id)
            nom_methode = self.CONSTRUCTEURS_WIDGETS.get(widget_id)
            if not info or not nom_methode:
                continue

            widget = getattr(self, nom_methode)()
            self._rendre_cliquable(widget_id, widget)

            if info["type"] == "carte":
                if ligne_courante is None or nb_dans_ligne >= 3:
                    ligne_courante = QHBoxLayout()
                    ligne_courante.setSpacing(15)
                    contenu_layout.addLayout(ligne_courante)
                    contenu_layout.addSpacing(20)
                    nb_dans_ligne = 0
                ligne_courante.addWidget(widget)
                nb_dans_ligne += 1
            else:  # "grand"
                ligne_courante = None
                nb_dans_ligne = 0
                contenu_layout.addWidget(widget, 1)
                contenu_layout.addSpacing(20)

    def _construire_apercu_cartes(self):
        self.apercu_cartes = ApercuCartes()
        return self.apercu_cartes

    def _construire_apercu_courbe(self):
        self.apercu_courbe = ApercuCourbe()
        return self.apercu_courbe

    def _construire_dernieres_sorties(self):
        self.apercu_dernieres_sorties = DernieresSorties(
            ouvrir_fiche=self._ouvrir_fiche_sortie,
            ouvrir_historique=self.ouvrir_historique_activites,
        )
        return self.apercu_dernieres_sorties

    def _ouvrir_fiche_sortie(self, activite_id):
        dialogue = DialogueDetailSortie(
            activite_id, self.athlete_actif_id, self,
            au_enregistrement=self.actualiser_dashboard,
        )
        dialogue.exec()

    def _actualiser_apercu(self):
        for nom in ("apercu_cartes", "apercu_courbe", "apercu_dernieres_sorties"):
            bloc = getattr(self, nom, None)
            if bloc is not None:
                try:
                    bloc.actualiser(self.athlete_actif_id)
                except Exception as erreur:   # un bloc en échec ne doit pas bloquer le tableau de bord
                    print(f"[Aperçu] {nom} : {erreur}")

    def _rendre_cliquable(self, widget_id, widget):
        # Les blocs « Aperçu » sont déjà interactifs (survol, clic sur une sortie)
        if widget_id in ("apercu_cartes", "apercu_courbe", "dernieres_sorties"):
            return
        """Un clic sur une carte ouvre sa fenêtre de détail (explication,
        graphique, bouton vers la page complète)."""
        FiltreClicCarte(widget, lambda: self.ouvrir_detail_carte(widget_id))

    def ouvrir_detail_carte(self, widget_id):
        if widget_id == "fiche_coureur":
            self.ouvrir_athletes()
            return
        if widget_id == "alertes_proactives":
            fenetre = DialogueAlertes(self.athlete_actif_id, self._ouvrir_page_depuis_detail, self)
        else:
            fenetre = DialogueDetailCarte(
                widget_id, self.athlete_actif_id, self._ouvrir_page_depuis_detail, self
            )
        fenetre.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        fenetre.show()

    def _ouvrir_page_depuis_detail(self, nom_methode, onglet=None):
        methode = getattr(self, nom_methode, None)
        if methode is None:
            return
        methode()
        if onglet is not None:
            fenetre = self._fenetres_ouvertes.get("analyses_forme")
            if fenetre is not None:
                fenetre.selectionner_onglet(onglet)

    def _construire_carte_charge_semaine(self):
        self.carte_charge_semaine = self.creer_carte(
            "CHARGE SEMAINE", "0", "Charge (7 derniers jours)", avec_sparkline=True
        )
        return self.carte_charge_semaine

    def _construire_carte_entrainements(self):
        self.carte_entrainements = self.creer_carte("ENTRAÎNEMENTS", "0", "Cette semaine")
        return self.carte_entrainements

    def _construire_carte_forme(self):
        self.carte_forme = self.creer_carte("FORME", "--", "Données à venir", avec_sparkline=True)
        return self.carte_forme

    def _construire_carte_acwr(self):
        self.carte_acwr = self.creer_carte("ACWR", "--", "Charge aiguë / chronique")
        return self.carte_acwr

    def _construire_carte_indice_forme(self):
        self.carte_indice_forme = self.creer_carte(
            "INDICE DE FORME", "--", "Charge, sommeil et blessure combinés (score/100)"
        )
        return self.carte_indice_forme

    def _construire_carte_cumulee(self, titre, attribut):
        """Petite carte avec un sélecteur de période rapide (Semaine/
        Mois/Année/Tout), utilisée pour les 3 mesures cumulées
        (distance, dénivelé, durée). `attribut` est le nom sous lequel
        la carte et son sélecteur seront retrouvés dans actualiser_dashboard."""

        carte = QFrame()
        carte.setObjectName("carte")
        carte.setMinimumHeight(130)

        layout = QVBoxLayout(carte)
        layout.setContentsMargins(18, 18, 18, 18)

        ligne_titre = QHBoxLayout()
        titre_label = QLabel(titre)
        titre_label.setObjectName("titreCarte")
        combo_periode = QComboBox()
        combo_periode.setObjectName("comboPeriode")
        for label, _ in self.PERIODES_CARTES_CUMULEES:
            combo_periode.addItem(label)
        combo_periode.setCurrentText("Mois")
        combo_periode.currentIndexChanged.connect(self.actualiser_dashboard)
        ligne_titre.addWidget(titre_label)
        ligne_titre.addStretch()
        ligne_titre.addWidget(combo_periode)

        valeur_label = QLabel("--")
        valeur_label.setObjectName("valeurCarte")
        description_label = QLabel("")
        description_label.setObjectName("texteSecondaire")

        layout.addLayout(ligne_titre)
        layout.addWidget(valeur_label)
        layout.addWidget(description_label)
        layout.addStretch()

        carte.combo_periode = combo_periode
        carte.valeur_label = valeur_label
        carte.description_label = description_label

        setattr(self, attribut, carte)
        return carte

    def _construire_carte_distance_cumulee(self):
        return self._construire_carte_cumulee("DISTANCE CUMULÉE", "carte_distance_cumulee")

    def _construire_carte_denivele_cumule(self):
        return self._construire_carte_cumulee("DÉNIVELÉ D+ CUMULÉ", "carte_denivele_cumule")

    def _construire_carte_duree_cumulee(self):
        return self._construire_carte_cumulee("TEMPS CUMULÉ", "carte_duree_cumulee")

    def _construire_graphique_charge(self):
        zone_analyse = QFrame()
        zone_analyse.setObjectName("carteGrande")

        analyse_layout = QVBoxLayout(zone_analyse)

        barre_analyse_titre = QHBoxLayout()
        analyse_titre = QLabel("Évolution de la charge d'entraînement")
        analyse_titre.setObjectName("titreCarte")

        self.combo_periode_charge = QComboBox()
        self.combo_periode_charge.setObjectName("comboPeriode")
        for label, _ in PERIODES_DISPONIBLES:
            self.combo_periode_charge.addItem(label)
        self.combo_periode_charge.setCurrentText("1 mois")
        self.combo_periode_charge.currentIndexChanged.connect(self.actualiser_dashboard)

        barre_analyse_titre.addWidget(analyse_titre)
        barre_analyse_titre.addStretch()
        barre_analyse_titre.addWidget(self.combo_periode_charge)

        analyse_layout.addLayout(barre_analyse_titre)

        self.courbe_dashboard = CourbeBarres()
        analyse_layout.addWidget(self.courbe_dashboard)

        return zone_analyse

    def _construire_graphique_sur_mesure(self):
        zone = QFrame()
        zone.setObjectName("carteGrande")

        zone_layout = QVBoxLayout(zone)

        barre_titre = QHBoxLayout()
        titre = QLabel("Graphique polyvalent")
        titre.setObjectName("titreCarte")

        self.combo_mesure_sur_mesure = QComboBox()
        self.combo_mesure_sur_mesure.setObjectName("comboPeriode")
        for cle, info in MESURES_CUMULABLES.items():
            self.combo_mesure_sur_mesure.addItem(info["libelle"], cle)
        self.combo_mesure_sur_mesure.currentIndexChanged.connect(self.actualiser_dashboard)

        self.combo_periode_sur_mesure = QComboBox()
        self.combo_periode_sur_mesure.setObjectName("comboPeriode")
        for label, _ in PERIODES_DISPONIBLES:
            self.combo_periode_sur_mesure.addItem(label)
        self.combo_periode_sur_mesure.setCurrentText("1 mois")
        self.combo_periode_sur_mesure.currentIndexChanged.connect(self.actualiser_dashboard)

        barre_titre.addWidget(titre)
        barre_titre.addStretch()
        barre_titre.addWidget(self.combo_mesure_sur_mesure)
        barre_titre.addWidget(self.combo_periode_sur_mesure)
        zone_layout.addLayout(barre_titre)

        self.label_total_sur_mesure = QLabel("")
        self.label_total_sur_mesure.setObjectName("texteSecondaire")
        zone_layout.addWidget(self.label_total_sur_mesure)

        self.courbe_sur_mesure = CourbeBarres()
        zone_layout.addWidget(self.courbe_sur_mesure)

        return zone

    COULEUR_NIVEAU_ALERTE = {
        "critique": "#EF5350", "attention": "#F9A825", "info": "#42A5F5", "ok": "#66BB6A",
    }
    ICONE_NIVEAU_ALERTE = {"critique": "🛑", "attention": "⚠️", "info": "ℹ️", "ok": "✅"}

    def _construire_carte_alertes_proactives(self):
        zone = QFrame()
        zone.setObjectName("carteGrande")

        zone_layout = QVBoxLayout(zone)
        titre = QLabel("⚡ Alertes proactives — à surveiller maintenant")
        titre.setObjectName("titreCarte")
        zone_layout.addWidget(titre)

        legende = QLabel(
            "🟢 Vert : tranquille · 🟡 Jaune : à surveiller · 🟠 Orange : attention · "
            "🔴 Rouge : risque élevé · ⚫ Noir : seuil critique dépassé"
        )
        legende.setObjectName("texteSecondaire")
        legende.setWordWrap(True)
        zone_layout.addWidget(legende)

        self.zone_alertes_dashboard = QVBoxLayout()
        self.zone_alertes_dashboard.setSpacing(6)
        zone_layout.addLayout(self.zone_alertes_dashboard)

        return zone

    def _ligne_alerte_dashboard(self, alerte):
        cadre = QFrame()
        layout = QHBoxLayout(cadre)
        layout.setContentsMargins(0, 0, 0, 0)
        icone = QLabel(self.ICONE_NIVEAU_ALERTE.get(alerte["niveau"], "ℹ️"))
        message = QLabel(alerte["message"])
        message.setWordWrap(True)

        # Quand un pourcentage de risque précis est disponible (ACWR,
        # sommeil...), on affine la couleur sur l'échelle à 5 niveaux
        # vert/jaune/orange/rouge/noir plutôt que le simple aplat par
        # niveau (critique/attention/info/ok).
        couleur, _ = couleur_pour_pourcentage(alerte.get("pourcentage"))
        if couleur is None:
            couleur = self.COULEUR_NIVEAU_ALERTE.get(alerte["niveau"], "#B8B8B8")
        message.setStyleSheet(f"color: {couleur};")
        layout.addWidget(icone)
        layout.addWidget(message, 1)
        return cadre

    def _construire_mini_forme_fatigue(self):
        zone = QFrame()
        zone.setObjectName("carteGrande")

        zone_layout = QVBoxLayout(zone)

        titre = QLabel("Fitness / Fatigue / Forme (30 derniers jours)")
        titre.setObjectName("titreCarte")
        zone_layout.addWidget(titre)

        self.courbe_mini_forme = CourbeMultiLignes()
        self.courbe_mini_forme.setMinimumHeight(160)
        zone_layout.addWidget(self.courbe_mini_forme)

        return zone

    def _construire_tableau_croise(self):
        zone = QFrame()
        zone.setObjectName("carteGrande")

        zone_layout = QVBoxLayout(zone)
        titre = QLabel("Tableau croisé — forme, rythme de vie, courses (30 derniers jours)")
        titre.setObjectName("titreCarte")
        zone_layout.addWidget(titre)
        note = QLabel(
            "Forme (ligne verte), jours de rythme de vie actif (violet) et jours de course "
            "(orange) superposés — pour repérer d'un coup d'œil comment ils se recoupent, "
            "plutôt que de naviguer entre plusieurs écrans."
        )
        note.setObjectName("texteSecondaire")
        note.setWordWrap(True)
        zone_layout.addWidget(note)

        self.courbe_croisee = CourbeMultiLignes()
        self.courbe_croisee.setMinimumHeight(180)
        zone_layout.addWidget(self.courbe_croisee)

        return zone

    def _construire_fiche_coureur(self):
        carte = QFrame()
        carte.setObjectName("carte")
        carte.setMinimumHeight(130)

        layout = QVBoxLayout(carte)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(8)

        ligne_haut = QHBoxLayout()

        label_photo = QLabel()
        label_photo.setFixedSize(56, 56)
        label_photo.setStyleSheet("background-color: #20262B; border-radius: 28px;")
        label_photo.setScaledContents(True)

        bloc_nom = QVBoxLayout()
        bloc_nom.setSpacing(2)
        label_nom = QLabel("—")
        label_nom.setObjectName("valeurCarte")
        label_niveau = QLabel("")
        label_niveau.setObjectName("texteSecondaire")
        bloc_nom.addWidget(label_nom)
        bloc_nom.addWidget(label_niveau)

        ligne_haut.addWidget(label_photo)
        ligne_haut.addLayout(bloc_nom)
        ligne_haut.addStretch()
        layout.addLayout(ligne_haut)

        label_stats = QLabel("")
        label_stats.setObjectName("texteSecondaire")
        label_stats.setWordWrap(True)
        layout.addWidget(label_stats)
        layout.addStretch()

        carte.label_photo = label_photo
        carte.label_nom = label_nom
        carte.label_niveau = label_niveau
        carte.label_stats = label_stats

        self.carte_fiche_coureur = carte
        return carte

    def creer_carte(self, titre, valeur, description, avec_sparkline=False):
        carte = QFrame()
        carte.setObjectName("carte")
        carte.setMinimumHeight(130)

        layout = QVBoxLayout(carte)
        layout.setContentsMargins(18, 18, 18, 18)

        titre_label = QLabel(titre)
        titre_label.setObjectName("titreCarte")

        valeur_label = QLabel(valeur)
        valeur_label.setObjectName("valeurCarte")

        description_label = QLabel(description)
        description_label.setObjectName("texteSecondaire")

        layout.addWidget(titre_label)
        layout.addWidget(valeur_label)
        layout.addWidget(description_label)

        carte.valeur_label = valeur_label
        carte.description_label = description_label
        carte.sparkline = None

        if avec_sparkline:
            sparkline = Sparkline(couleur=obtenir_couleur_accent())
            layout.addWidget(sparkline)
            carte.sparkline = sparkline

        layout.addStretch()

        return carte

    def _appliquer_couleur_carte(self, carte, couleur):
        """Teinte une carte du tableau de bord (liseré gauche + valeur en
        couleur) selon le niveau de risque du critère qu'elle affiche —
        vert/jaune/orange/rouge/noir, voir interface/theme.py."""

        if couleur is None:
            carte.setStyleSheet("")
            carte.valeur_label.setStyleSheet("")
            return
        carte.setStyleSheet(f"border-left: 5px solid {couleur};")
        carte.valeur_label.setStyleSheet(f"color: {couleur};")
    
    CLE_PARAMETRE_GROUPES_MENU = "menu_groupes_ouverts"

    def _charger_etats_groupes_menu(self):
        brut = obtenir_parametre(self.CLE_PARAMETRE_GROUPES_MENU)
        if not brut:
            return {}
        try:
            return json.loads(brut)
        except (ValueError, TypeError):
            return {}

    def _basculer_groupe_menu(self, nom_groupe, bouton_groupe):
        # État suivi explicitement (self._groupes_ouverts) plutôt que via
        # conteneur.isVisible() : cette dernière ne reflète l'affichage
        # réel qu'une fois la fenêtre montrée (show()), pas avant.
        conteneur = self._groupes_conteneurs[nom_groupe]
        ouvert = not self._groupes_ouverts.get(nom_groupe, True)
        conteneur.setVisible(ouvert)
        bouton_groupe.setText(f"{'▾' if ouvert else '▸'}  {nom_groupe}")
        self._groupes_ouverts[nom_groupe] = ouvert

        etats = self._charger_etats_groupes_menu()
        etats[nom_groupe] = ouvert
        definir_parametre(self.CLE_PARAMETRE_GROUPES_MENU, json.dumps(etats))

    def _vider_zone_alertes_dashboard(self):
        while self.zone_alertes_dashboard.count():
            item = self.zone_alertes_dashboard.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

    def changer_athlete_actif(self):
        self.athlete_actif_id = self.combo_athlete_actif.currentData()
        self._invalider_ecrans()
        self.page_aujourdhui.definir_athlete(self.athlete_actif_id)
        self.actualiser_dashboard()

    def actualiser_dashboard(self):
        self._actualiser_apercu()
        if self.athlete_actif_id is None:
            if hasattr(self, "carte_fiche_coureur"):
                self.carte_fiche_coureur.label_nom.setText("—")
                self.carte_fiche_coureur.label_niveau.setText("Sélectionnez un athlète")
                self.carte_fiche_coureur.label_stats.setText("")
                self.carte_fiche_coureur.label_photo.setPixmap(QPixmap())
            if hasattr(self, "carte_charge_semaine"):
                self.carte_charge_semaine.valeur_label.setText("--")
                self.carte_charge_semaine.description_label.setText("Sélectionnez un athlète")
                self._appliquer_couleur_carte(self.carte_charge_semaine, None)
            if hasattr(self, "carte_entrainements"):
                self.carte_entrainements.valeur_label.setText("--")
                self.carte_entrainements.description_label.setText("Sélectionnez un athlète")
            if hasattr(self, "carte_forme"):
                self.carte_forme.valeur_label.setText("--")
                self.carte_forme.description_label.setText("Sélectionnez un athlète")
                self._appliquer_couleur_carte(self.carte_forme, None)
            if hasattr(self, "carte_acwr"):
                self.carte_acwr.valeur_label.setText("--")
                self.carte_acwr.description_label.setText("Sélectionnez un athlète")
                self._appliquer_couleur_carte(self.carte_acwr, None)
            if hasattr(self, "carte_indice_forme"):
                self.carte_indice_forme.valeur_label.setText("--")
                self.carte_indice_forme.description_label.setText("Sélectionnez un athlète")
                self._appliquer_couleur_carte(self.carte_indice_forme, None)
            for attribut in ("carte_distance_cumulee", "carte_denivele_cumule", "carte_duree_cumulee"):
                if hasattr(self, attribut):
                    carte = getattr(self, attribut)
                    carte.valeur_label.setText("--")
                    carte.description_label.setText("Sélectionnez un athlète")
            if hasattr(self, "courbe_dashboard"):
                self.courbe_dashboard.definir_donnees([])
            if hasattr(self, "courbe_sur_mesure"):
                self.courbe_sur_mesure.definir_donnees([])
                self.label_total_sur_mesure.setText("Sélectionnez un athlète")
            if hasattr(self, "courbe_mini_forme"):
                self.courbe_mini_forme.definir_series([])
            if hasattr(self, "courbe_croisee"):
                self.courbe_croisee.definir_series([])
            if hasattr(self, "zone_alertes_dashboard"):
                self._vider_zone_alertes_dashboard()
            return

        if hasattr(self, "carte_fiche_coureur"):
            athlete = obtenir_athlete_par_id(self.athlete_actif_id)
            if athlete:
                colonnes = [
                    "id", "nom", "prenom", "age", "sexe", "taille", "poids",
                    "fc_repos", "fc_max", "fc_seuil", "vma", "vo2max",
                    "niveau", "date_creation", "photo_path",
                ]
                a = dict(zip(colonnes, athlete))

                self.carte_fiche_coureur.label_nom.setText(f"{a['prenom']} {a['nom']}")
                self.carte_fiche_coureur.label_niveau.setText(a["niveau"] or "")
                self.carte_fiche_coureur.label_stats.setText(
                    f"VO₂max {a['vo2max'] or '--'} · FC max {a['fc_max'] or '--'} · "
                    f"Seuil {a['fc_seuil'] or '--'}\n"
                    f"Poids {a['poids'] or '--'} kg · Taille {a['taille'] or '--'} cm · "
                    f"Âge {a['age'] or '--'} ans"
                )

                pixmap = pixmap_circulaire(a["photo_path"], taille=56)
                self.carte_fiche_coureur.label_photo.setPixmap(pixmap if pixmap else QPixmap())

        if hasattr(self, "zone_alertes_dashboard"):
            self._vider_zone_alertes_dashboard()
            alertes = [a for a in generer_alertes(self.athlete_actif_id) if a["niveau"] in ("critique", "attention")]
            if not alertes:
                self.zone_alertes_dashboard.addWidget(
                    self._ligne_alerte_dashboard({"niveau": "ok", "message": "Rien à signaler — charge et forme sous contrôle."})
                )
            else:
                for alerte in alertes:
                    self.zone_alertes_dashboard.addWidget(self._ligne_alerte_dashboard(alerte))

        acwr_info = calculer_acwr(self.athlete_actif_id)
        charges = obtenir_charges_journalieres(self.athlete_actif_id, nb_jours=35)
        indicateurs = obtenir_indicateurs_couleur(self.athlete_actif_id)

        charge_semaine = round(sum(c for _, c in charges[-7:]), 1)
        entrainements_semaine = sum(1 for _, c in charges[-7:] if c > 0)

        if hasattr(self, "carte_charge_semaine"):
            self.carte_charge_semaine.valeur_label.setText(str(charge_semaine))
            self.carte_charge_semaine.description_label.setText(
                f"Charge (7 derniers jours) · {indicateurs['charge']['valeur']} jour(s) à forte charge sur 5"
            )
            if self.carte_charge_semaine.sparkline is not None:
                self.carte_charge_semaine.sparkline.definir_donnees([c for _, c in charges[-14:]], [str(d) for d, _ in charges[-14:]])
            self._appliquer_couleur_carte(self.carte_charge_semaine, indicateurs["charge"]["couleur"])

        if hasattr(self, "carte_entrainements"):
            self.carte_entrainements.valeur_label.setText(str(entrainements_semaine))
            self.carte_entrainements.description_label.setText("Jours actifs cette semaine")

        if hasattr(self, "carte_forme"):
            self.carte_forme.valeur_label.setText(
                acwr_info["interpretation"].split(" —")[0].split(",")[0]
            )
            self.carte_forme.description_label.setText(acwr_info["interpretation"])
            if self.carte_forme.sparkline is not None:
                serie_recente = calculer_serie_forme(self.athlete_actif_id, nb_jours=14)
                self.carte_forme.sparkline.definir_donnees([j["forme"] for j in serie_recente], [str(j.get("date", "")) for j in serie_recente])
            self._appliquer_couleur_carte(self.carte_forme, indicateurs["acwr"]["couleur"])

        if hasattr(self, "carte_acwr"):
            self.carte_acwr.valeur_label.setText(
                str(acwr_info["acwr"]) if acwr_info["acwr"] is not None else "--"
            )
            self.carte_acwr.description_label.setText("Charge aiguë (7j) / chronique (28j)")
            self._appliquer_couleur_carte(self.carte_acwr, indicateurs["acwr"]["couleur"])

        if hasattr(self, "carte_indice_forme"):
            forme_jour = calculer_score_forme_jour(self.athlete_actif_id)
            self.carte_indice_forme.valeur_label.setText(f"{forme_jour['score']}/100")
            self.carte_indice_forme.description_label.setText(forme_jour["interpretation"])
            self._appliquer_couleur_carte(self.carte_indice_forme, indicateurs["forme_jour"]["couleur"])

        for mesure, attribut in (
            ("distance", "carte_distance_cumulee"),
            ("denivele", "carte_denivele_cumule"),
            ("duree", "carte_duree_cumulee"),
        ):
            if hasattr(self, attribut):
                carte = getattr(self, attribut)
                label_periode = carte.combo_periode.currentText()
                nb_jours = dict(self.PERIODES_CARTES_CUMULEES).get(label_periode)
                if nb_jours is None:  # "Tout"
                    premiere_date = obtenir_date_premiere_activite(self.athlete_actif_id)
                    from datetime import date as _date
                    nb_jours = (_date.today() - premiere_date).days + 1 if premiere_date else 30
                _, _, total = obtenir_mesure_periode(self.athlete_actif_id, mesure, nb_jours)
                unite = {"distance": " km", "denivele": " m", "duree": " h"}[mesure]
                carte.valeur_label.setText(f"{total}{unite}")
                carte.description_label.setText(f"Sur : {label_periode.lower()}")

        if hasattr(self, "courbe_dashboard"):
            donnees_courbe, seuil = self._donnees_courbe_periode(acwr_info["charge_chronique"])
            self.courbe_dashboard.definir_donnees(donnees_courbe, seuil=seuil, libelle="Charge")

        if hasattr(self, "courbe_sur_mesure"):
            mesure = self.combo_mesure_sur_mesure.currentData()
            label_periode = self.combo_periode_sur_mesure.currentText()
            nb_jours = dict(PERIODES_DISPONIBLES).get(label_periode)
            if nb_jours is None:  # "Tout l'historique"
                premiere_date = obtenir_date_premiere_activite(self.athlete_actif_id)
                from datetime import date as _date
                nb_jours = (_date.today() - premiere_date).days + 1 if premiere_date else 35
            points, _, total = obtenir_mesure_periode(self.athlete_actif_id, mesure, nb_jours)
            info_mesure = MESURES_CUMULABLES.get(mesure, {})
            self.courbe_sur_mesure.definir_donnees(points, libelle=info_mesure.get("libelle", mesure))
            self.label_total_sur_mesure.setText(
                f"Total sur la période : {total} — {info_mesure.get('libelle', mesure)}"
            )

        if hasattr(self, "courbe_mini_forme"):
            serie_forme = calculer_serie_forme(self.athlete_actif_id, nb_jours=30)
            self.courbe_mini_forme.definir_series([
                {
                    "nom": "Fitness", "couleur": "#42A5F5",
                    "valeurs": [(j["date"].strftime("%d/%m"), j["fitness"]) for j in serie_forme],
                },
                {
                    "nom": "Fatigue", "couleur": "#EF5350",
                    "valeurs": [(j["date"].strftime("%d/%m"), j["fatigue"]) for j in serie_forme],
                },
                {
                    "nom": "Forme", "couleur": "#66BB6A",
                    "valeurs": [(j["date"].strftime("%d/%m"), j["forme"]) for j in serie_forme],
                },
            ])

        if hasattr(self, "courbe_croisee"):
            serie_forme_30 = calculer_serie_forme(self.athlete_actif_id, nb_jours=30)
            rythme_30 = serie_rythme_vie_actif(nb_jours=30)
            courses_30 = serie_resultats_courses(self.athlete_actif_id, nb_jours=30)
            valeur_max_forme = max((j["forme"] for j in serie_forme_30), default=5) or 5
            echelle = max(abs(valeur_max_forme), 5)
            self.courbe_croisee.definir_series([
                {
                    "nom": "Forme", "couleur": "#66BB6A",
                    "valeurs": [(j["date"].strftime("%d/%m"), j["forme"]) for j in serie_forme_30],
                },
                {
                    "nom": "Rythme de vie actif", "couleur": "#AB47BC",
                    "valeurs": [(j.strftime("%d/%m"), echelle if a else 0) for j, a in rythme_30],
                },
                {
                    "nom": "Jour de course", "couleur": "#FFA726",
                    "valeurs": [(j.strftime("%d/%m"), echelle if a else 0) for j, a in courses_30],
                },
            ])

    def _donnees_courbe_periode(self, charge_chronique):
        """Calcule les points du graphique de charge pour la période
        choisie dans le sélecteur (agrégation jour/semaine/mois/trimestre
        automatique selon la durée — voir interface/coach.py)."""

        label_periode = self.combo_periode_charge.currentText()
        nb_jours = dict(PERIODES_DISPONIBLES).get(label_periode)

        if nb_jours is None:  # "Tout l'historique"
            premiere_date = obtenir_date_premiere_activite(self.athlete_actif_id)
            if premiere_date:
                from datetime import date
                nb_jours = (date.today() - premiere_date).days + 1
            else:
                nb_jours = 35

        points, _ = obtenir_charges_periode(self.athlete_actif_id, nb_jours)

        # Le seuil (ligne d'alerte à 1.5x la charge chronique) n'a de sens
        # que pour une vue rapprochée en jours ; sur des barres hebdo/mensuelles
        # agrégées, il perdrait sa signification et brouillerait la lecture.
        seuil = charge_chronique * 1.5 if (charge_chronique and nb_jours <= 35) else None

        return points, seuil

    def _ouvrir_ou_activer(self, cle, fabrique):
        """Ramène au premier plan la fenêtre déjà ouverte sous cette clé,
        ou en crée une nouvelle si elle n'existe pas (ou plus)."""

        if obtenir_parametre("fenetre_unique", "1") == "1":
            return self._ouvrir_dans_la_fenetre(cle, fabrique)

        fenetre_existante = self._fenetres_ouvertes.get(cle)
        if fenetre_existante is not None:
            try:
                fenetre_existante.show()
                fenetre_existante.raise_()
                fenetre_existante.activateWindow()
                return fenetre_existante
            except RuntimeError:
                pass  # fenêtre détruite côté Qt — on en recrée une

        nouvelle_fenetre = fabrique()
        nouvelle_fenetre.show()
        self._fenetres_ouvertes[cle] = nouvelle_fenetre
        return nouvelle_fenetre

    def _ouvrir_dans_la_fenetre(self, cle, fabrique):
        """U1 — l'écran s'affiche dans la fenêtre principale (créé une
        fois, puis réutilisé) au lieu d'une fenêtre séparée."""
        from shiboken6 import isValid
        page = self._fenetres_ouvertes.get(cle)
        if page is not None and not isValid(page):
            page = None
        if page is None:
            self.pile.setCurrentWidget(self.page_chargement)
            QApplication.processEvents()
            page = fabrique()
            page.setWindowFlags(Qt.WindowType.Widget)
            page.setMinimumSize(0, 0)
            page.installEventFilter(self)
            self.pile.addWidget(page)
            self._fenetres_ouvertes[cle] = page
        if self._bouton_clique is not None:
            self._cle_vers_bouton[cle] = self._bouton_clique
        self.pile.setCurrentWidget(page)
        page.show()
        self._marquer_menu(self._cle_vers_bouton.get(cle))
        self._bouton_clique = None
        return page

    def eventFilter(self, obj, ev):
        # Un écran qui se « ferme » (bouton Fermer, Échap…) ramène à Aujourd'hui.
        if ev.type() == QEvent.Type.Close and obj in self._fenetres_ouvertes.values():
            ev.ignore()
            self.ouvrir_aujourdhui()
            return True
        return super().eventFilter(obj, ev)

    def _clic_menu(self, bouton, gestionnaire):
        self._bouton_clique = bouton
        gestionnaire()
        self._bouton_clique = None

    def _marquer_menu(self, bouton):
        for b in self._boutons_menu:
            nom = "boutonMenuActif" if b is bouton else "boutonMenu"
            if b.objectName() != nom:
                b.setObjectName(nom)
                b.style().unpolish(b)
                b.style().polish(b)

    def _navigation_aujourdhui(self):
        """Actions des blocs cliquables de l'écran Aujourd'hui (U5)."""
        def onglet(methode, i):
            return lambda: (methode(), self._fenetres_ouvertes.get(
                {"ouvrir_analyses_et_forme": "analyses_forme", "ouvrir_planification": "planification"}[methode.__name__]
            ).selectionner_onglet(i))

        def sortie():
            d = self.page_aujourdhui._donnees
            if d and d.get("derniere"):
                self._ouvrir_fiche_sortie(d["derniere"]["id"])

        def ressenti(sr):
            from interface.ressenti import DialogueRessenti
            DialogueRessenti(sr["id"], self.page_aujourdhui.athlete_id, sr["nom"], parent=self,
                             apres=self.page_aujourdhui.actualiser).exec()

        def athlete_change(id_):
            i = self.combo_athlete_actif.findData(id_)
            if i >= 0 and self.combo_athlete_actif.currentIndex() != i:
                self.combo_athlete_actif.setCurrentIndex(i)

        return {
            "nouvelle": self.nouvelle_activite,
            "palette": self.ouvrir_palette_commandes,
            "sante": onglet(self.ouvrir_analyses_et_forme, 5),
            "charge": onglet(self.ouvrir_analyses_et_forme, 6),
            "alertes": onglet(self.ouvrir_analyses_et_forme, 6),
            "plan": onglet(self.ouvrir_planification, 1),
            "bilans": self.ouvrir_bilans_objectifs,
            "courses": self.ouvrir_courses_calendrier,
            "sortie": sortie,
            "ressenti": ressenti,
            "athlete_change": athlete_change,
        }

    def _synchro_garmin_auto(self):
        """v99 — synchro Garmin Connect automatique, une fois par jour, si activée.
        Silencieuse en cas d'échec (pas d'Internet, session expirée...)."""
        try:
            from data import garmin_connect as gc
            if not gc.synchro_auto_due():
                return
            gc.marquer_synchro_auto()
        except Exception:
            return
        athlete = self.athlete_actif_id
        if athlete is None:
            return

        def travail():
            return gc.synchroniser(athlete, 7, 7)

        def fini(res, erreur):
            if erreur or not res:
                return
            nouvelles = (res.get("sorties") or {}).get("nouvelles", 0)
            jours = (res.get("sante") or {}).get("jours", 0)
            notifier(f"Garmin Connect : {nouvelles} nouvelle(s) sortie(s), santé de {jours} jour(s) à jour.",
                     "info", parent=self, duree_ms=4500)
            try:
                self.page_aujourdhui.actualiser()
            except Exception:
                pass

        from interface import arriere_plan
        arriere_plan.executer(travail, fini, proprietaire=self)

    def _ajustement_matin(self):
        """E3 — ajustement automatique du plan, une fois par jour."""
        try:
            from interface.ajustement_matinal import ajustement_du_jour
            _res, message = ajustement_du_jour()
        except Exception:
            return
        if message:
            self.page_aujourdhui.afficher_message(message)
            self.page_aujourdhui.actualiser()
            notifier(message, "info", parent=self, duree_ms=4500)

    def ouvrir_aujourdhui(self):
        self.pile.setCurrentWidget(self.page_aujourdhui)
        self._marquer_menu(self._cle_vers_bouton.get("aujourdhui") or (self._boutons_menu[0] if self._boutons_menu else None))
        self.page_aujourdhui.actualiser()

    def ouvrir_athletes(self):
        fenetre = self._ouvrir_ou_activer(
            "compte", lambda: Compte(athlete_id_initial=self.athlete_actif_id)
        )
        fenetre.selectionner_onglet(0)
    def ouvrir_journal(self):
        from interface.journal import Journal
        self._ouvrir_ou_activer("journal", lambda: Journal(athlete_id_initial=self.athlete_actif_id))

    def ouvrir_historique_activites(self):
        self._ouvrir_ou_activer(
            "historique",
            lambda: HistoriqueActivites(athlete_id_initial=self.athlete_actif_id),
        )
    def ouvrir_suivi_direct(self):
        self._ouvrir_ou_activer(
            "suivi_direct",
            lambda: SuiviDirect(athlete_id_initial=self.athlete_actif_id),
        )
    def ouvrir_reglages(self):
        fenetre = self._ouvrir_ou_activer(
            "compte", lambda: Compte(athlete_id_initial=self.athlete_actif_id)
        )
        fenetre.selectionner_onglet(1)
    def ouvrir_resultats_courses(self):
        self._ouvrir_ou_activer(
            "resultats_courses",
            lambda: ResultatsCourses(athlete_id_initial=self.athlete_actif_id),
        )
    def ouvrir_courses_calendrier(self):
        self._ouvrir_ou_activer(
            "courses_calendrier",
            lambda: CoursesCalendrier(athlete_id_initial=self.athlete_actif_id),
        )
    def ouvrir_materiel_course(self):
        self._ouvrir_ou_activer(
            "materiel_course",
            lambda: MaterielCourse(athlete_id_initial=self.athlete_actif_id),
        )
    def ouvrir_meteo(self):
        self._ouvrir_ou_activer(
            "meteo", lambda: MeteoEcran(athlete_id_initial=self.athlete_actif_id)
        )
    def ouvrir_alimentation(self):
        self._ouvrir_ou_activer(
            "alimentation",
            lambda: AlimentationFenetre(athlete_id_initial=self.athlete_actif_id),
        )
    def ouvrir_photos(self):
        self._ouvrir_ou_activer(
            "photos", lambda: Photos(athlete_id_initial=self.athlete_actif_id)
        )
    def ouvrir_cartes_et_traces(self):
        self._ouvrir_ou_activer(
            "cartes", lambda: CartesEtTraces(athlete_id_initial=self.athlete_actif_id)
        )
    def ouvrir_analyses_et_forme(self):
        self._ouvrir_ou_activer(
            "analyses_forme",
            lambda: AnalysesEtForme(athlete_id_initial=self.athlete_actif_id),
        )
    def ouvrir_performance_trail(self):
        self._ouvrir_ou_activer(
            "performance_trail",
            lambda: PerformanceTrail(athlete_id_initial=self.athlete_actif_id),
        )
    def ouvrir_bilans_objectifs(self):
        self._ouvrir_ou_activer(
            "bilans_objectifs",
            lambda: BilansObjectifs(athlete_id_initial=self.athlete_actif_id),
        )
    def ouvrir_planification(self):
        self._ouvrir_ou_activer(
            "planification",
            lambda: Planification(athlete_id_initial=self.athlete_actif_id),
        )
    def ouvrir_renforcement(self):
        self._ouvrir_ou_activer(
            "renforcement", lambda: Renforcement(athlete_id_initial=self.athlete_actif_id)
        )
    def ouvrir_suivi(self):
        self._ouvrir_ou_activer(
            "suivi", lambda: Suivi(athlete_id_initial=self.athlete_actif_id)
        )
    def ouvrir_import_et_synchro(self):
        self._ouvrir_ou_activer(
            "import_synchro",
            lambda: ImportEtSynchro(athlete_id_initial=self.athlete_actif_id),
        )
    # ------------------------------------------------------------------
    # v98 — U7 mode Simple/Complet, U10 mise à jour, U4 palette, U9 raccourcis
    # ------------------------------------------------------------------

    def _rafraichir_bouton_mode(self):
        simple = affichage_simplifie_actif()
        self.bouton_mode.setText("Affichage : Simple  ⇄" if simple else "Affichage : Complet  ⇄")
        self.bouton_mode.setToolTip(
            "Simple : seulement l'essentiel. Complet : tous les détails et réglages avancés. "
            "Clique pour changer."
        )

    def basculer_mode_affichage(self):
        nouveau = not affichage_simplifie_actif()
        definir_parametre("affichage_simplifie", "1" if nouveau else "0")
        self._rafraichir_bouton_mode()
        # Les écrans déjà ouverts sont reconstruits au prochain affichage.
        self._invalider_ecrans()
        self.actualiser_dashboard()
        notifier("Affichage « Simple » activé" if nouveau else "Affichage « Complet » activé", parent=self)

    def basculer_fenetre_unique(self):
        nouveau = obtenir_parametre("fenetre_unique", "1") != "1"
        definir_parametre("fenetre_unique", "1" if nouveau else "0")
        self._invalider_ecrans()
        notifier("Tout s'ouvre dans la fenêtre principale" if nouveau else "Les écrans s'ouvrent dans des fenêtres séparées", parent=self)

    def _invalider_ecrans(self):
        """Ferme et oublie les écrans ouverts pour qu'ils soient recréés
        (prise en compte immédiate d'un réglage). Surchargé en v98 par
        la version fenêtre unique."""
        for cle, fen in list(self._fenetres_ouvertes.items()):
            try:
                if fen.parent() is self.pile:
                    fen.removeEventFilter(self)
                    self.pile.removeWidget(fen)
                    fen.deleteLater()
                else:
                    fen.close()
            except RuntimeError:
                pass
        self._fenetres_ouvertes.clear()
        if self.pile.currentWidget() is self.page_chargement or self.pile.currentIndex() < 0:
            self.pile.setCurrentWidget(self.page_aujourdhui)

    def verifier_maj_maintenant(self, silencieux=False):
        if self._resultat_maj:
            proposer_mise_a_jour(self, self._resultat_maj)
            return
        self.bouton_maj.setText("Vérification…")
        self._silencieux_maj = silencieux
        self._fil_maj = VerificationMajThread()
        self._fil_maj.resultat_disponible.connect(self._maj_verifiee)
        self._fil_maj.start()

    def _maj_verifiee(self, resultat):
        self._resultat_maj = resultat
        if resultat:
            self.bouton_maj.setText(f"⬆ Mettre à jour vers {resultat.get('nom')}")
            self.bouton_maj.setStyleSheet("color: #E8A33D; font-weight: 700;")
            notifier("Une nouvelle version est disponible", "alerte", parent=self)
        else:
            self.bouton_maj.setText("Vérifier les mises à jour")
            if not getattr(self, "_silencieux_maj", False):
                notifier("Tu as déjà la dernière version (ou pas de connexion)", "info", parent=self)

    def liste_commandes(self):
        """Commandes de la palette (libellé, mots-clés, fonction)."""
        c = []
        for libelle, mots, fonction in self._entrees_ecrans():
            c.append((f"Aller à  ·  {libelle}", mots, fonction))
        c += [
            ("Action  ·  Nouvelle activité", "ajouter creer saisir", self.nouvelle_activite),
            ("Action  ·  Importer des fichiers", "import fit gpx garmin", self.ouvrir_import_et_synchro),
            ("Action  ·  Fenêtre unique / fenêtres séparées", "fenetre unique separees", self.basculer_fenetre_unique),
            ("Action  ·  Basculer Simple / Complet", "affichage mode simple complet", self.basculer_mode_affichage),
            ("Action  ·  Vérifier les mises à jour", "version maj", self.verifier_maj_maintenant),
            ("Aide  ·  Raccourcis clavier", "aide clavier", self.afficher_aide_raccourcis),
        ]
        return c

    def _chercheur_palette(self, texte):
        from interface.recherche_globale import rechercher_partout
        sorties = []
        for categorie, nom, date, id_ in rechercher_partout(self.athlete_actif_id, texte)[:12]:
            if categorie == "Activité":
                sorties.append((f"Sortie  ·  {nom}   ({date[:10]})",
                                lambda i=id_: self._ouvrir_fiche_sortie(i)))
            else:
                sorties.append((f"{categorie}  ·  {nom}   ({date[:10]})", self.ouvrir_recherche_globale))
        return sorties

    def ouvrir_palette_commandes(self):
        PaletteCommandes(self, self.liste_commandes(), self._chercheur_palette).exec()

    def afficher_aide_raccourcis(self):
        texte = "\n".join(f"{k}   →   {v}" for k, v in AIDE_RACCOURCIS)
        QMessageBox.information(self, "Raccourcis clavier", texte)

    def nouvelle_activite(self):
        from interface.dialogue_nouvelle_activite import DialogueNouvelleActivite
        athlete = self.athlete_actif_id
        if athlete is None:
            athletes = obtenir_athletes()
            if not athletes:
                notifier("Crée d'abord un athlète", "alerte", parent=self)
                return
            athlete = athletes[0][0]

        def apres():
            self.actualiser_dashboard()
            notifier("Activité ajoutée", parent=self)

        DialogueNouvelleActivite(athlete, parent=self, au_enregistrement=apres).exec()

    def _entrees_ecrans(self):
        return [
            ("Aujourd'hui", "accueil jour matin", self.ouvrir_aujourdhui),
            ("Tableau de bord", "accueil dashboard", self.ouvrir_tableau_de_bord),
            ("Journal", "fil diaire notes photos", self.ouvrir_journal),
            ("Historique des activités", "sorties liste", self.ouvrir_historique_activites),
            ("Suivi en direct", "live", self.ouvrir_suivi_direct),
            ("Cartes & Traces", "carte parcours gpx", self.ouvrir_cartes_et_traces),
            ("Photos", "album images", self.ouvrir_photos),
            ("Planification", "plan calendrier seances", self.ouvrir_planification),
            ("Renforcement & Mobilité", "muscu", self.ouvrir_renforcement),
            ("Analyses & Forme", "fatigue charge vma sommeil hrv", self.ouvrir_analyses_et_forme),
            ("Performance trail", "montees vam allure pente fatigue efficacite terrain meteo", self.ouvrir_performance_trail),
            ("Bilans & objectifs", "totaux comparer objectifs annee simulateur", self.ouvrir_bilans_objectifs),
            ("Suivi", "poids sommeil blessures", self.ouvrir_suivi),
            ("Résultats de courses", "records", self.ouvrir_resultats_courses),
            ("Courses à venir", "calendrier courses", self.ouvrir_courses_calendrier),
            ("Matériel pour une course", "sac", self.ouvrir_materiel_course),
            ("Météo", "meteo", self.ouvrir_meteo),
            ("Alimentation", "nutrition", self.ouvrir_alimentation),
            ("Import & Synchro", "garmin strava", self.ouvrir_import_et_synchro),
            ("Athlètes", "profil", self.ouvrir_athletes),
            ("Réglages", "parametres options", self.ouvrir_reglages),
        ]

    def ouvrir_tableau_de_bord(self):
        self.pile.setCurrentWidget(self.contenu_scroll)
        self._marquer_menu(self._boutons_menu[1] if len(self._boutons_menu) > 1 else None)
        self.activateWindow()
        self.raise_()

    def _installer_raccourcis(self):
        actions = {
            "Ctrl+K": self.ouvrir_palette_commandes,
            "Ctrl+N": self.nouvelle_activite,
            "Ctrl+F": self.ouvrir_recherche_globale,
            "Ctrl+/": self.afficher_aide_raccourcis,
            "Esc": self._echap,
        }
        entrees = self._entrees_ecrans()
        for i, (_l, _m, fonction) in enumerate(entrees[:9], start=1):
            actions[f"Ctrl+{i}"] = fonction
        self._raccourcis = installer_raccourcis(self, actions)

    def _echap(self):
        if self.pile.currentWidget() is not self.page_aujourdhui:
            self.ouvrir_aujourdhui()

    def ouvrir_recherche_globale(self):
        self._ouvrir_ou_activer(
            "recherche_globale",
            lambda: RechercheGlobale(athlete_id_initial=self.athlete_actif_id),
        )