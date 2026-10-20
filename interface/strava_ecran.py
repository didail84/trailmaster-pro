from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QComboBox,
    QPushButton,
    QFrame,
    QLineEdit,
    QMessageBox,
    QScrollArea,
)

from data.database import obtenir_athletes, obtenir_parametre, definir_parametre
from interface.ecran_liste import obtenir_style_ecran
from interface.strava_api import demarrer_flux_autorisation, verifier_code_recu, echanger_code_contre_jetons
from interface.strava_sync import synchroniser, sauvegarder_jetons


class StravaEcran(QMainWindow):

    def __init__(self, athlete_id_initial=None):
        super().__init__()

        self.setWindowTitle("TrailMaster Pro – Synchro Strava")
        self.resize(900, 750)
        self.setMinimumSize(750, 600)

        self.minuteur_oauth = None

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

        titre = QLabel("🔗  Synchro Strava")
        titre.setObjectName("titrePage")
        sous_titre = QLabel(
            "Récupère automatiquement tes nouvelles sorties depuis Strava — "
            "nécessite une connexion internet à chaque synchronisation"
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
        barre.addWidget(label_athlete)
        barre.addWidget(self.combo_athlete)
        barre.addStretch()
        principal.addLayout(barre)

        cadre_config = QFrame()
        cadre_config.setObjectName("carteForm")
        config_layout = QVBoxLayout(cadre_config)

        titre_config = QLabel("1️⃣ Configuration (une seule fois)")
        titre_config.setObjectName("titreCarte")
        config_layout.addWidget(titre_config)

        note_config = QLabel(
            "Crée une application gratuite sur strava.com/settings/api (domaine de "
            "rappel : \"localhost\"), puis colle ici le Client ID et le Client Secret fournis."
        )
        note_config.setObjectName("texteSecondaire")
        note_config.setWordWrap(True)
        config_layout.addWidget(note_config)

        self.champ_client_id = QLineEdit()
        self.champ_client_id.setPlaceholderText("Client ID")
        self.champ_client_id.setText(obtenir_parametre("strava_client_id", ""))

        self.champ_client_secret = QLineEdit()
        self.champ_client_secret.setPlaceholderText("Client Secret")
        self.champ_client_secret.setEchoMode(QLineEdit.EchoMode.Password)
        self.champ_client_secret.setText(obtenir_parametre("strava_client_secret", ""))

        bouton_enregistrer_config = QPushButton("💾 Enregistrer")
        bouton_enregistrer_config.setObjectName("boutonSecondaire")
        bouton_enregistrer_config.clicked.connect(self.enregistrer_configuration)

        config_layout.addWidget(self.champ_client_id)
        config_layout.addWidget(self.champ_client_secret)
        config_layout.addWidget(bouton_enregistrer_config)

        principal.addWidget(cadre_config)

        cadre_connexion = QFrame()
        cadre_connexion.setObjectName("carteForm")
        connexion_layout = QVBoxLayout(cadre_connexion)

        titre_connexion = QLabel("2️⃣ Connexion")
        titre_connexion.setObjectName("titreCarte")
        connexion_layout.addWidget(titre_connexion)

        self.label_statut_connexion = QLabel(self._texte_statut_connexion())
        self.label_statut_connexion.setObjectName("texteSecondaire")
        connexion_layout.addWidget(self.label_statut_connexion)

        self.bouton_connecter = QPushButton("🔐 Se connecter à Strava")
        self.bouton_connecter.setObjectName("boutonPrincipal")
        self.bouton_connecter.clicked.connect(self.lancer_connexion)
        connexion_layout.addWidget(self.bouton_connecter)

        principal.addWidget(cadre_connexion)

        cadre_sync = QFrame()
        cadre_sync.setObjectName("carteForm")
        sync_layout = QVBoxLayout(cadre_sync)

        titre_sync = QLabel("3️⃣ Synchronisation")
        titre_sync.setObjectName("titreCarte")
        sync_layout.addWidget(titre_sync)

        bouton_sync = QPushButton("🔄 Synchroniser maintenant")
        bouton_sync.setObjectName("boutonPrincipal")
        bouton_sync.clicked.connect(self.lancer_synchronisation)
        sync_layout.addWidget(bouton_sync)

        bouton_completer = QPushButton("🧩 Compléter mes anciennes sorties depuis Strava")
        bouton_completer.setToolTip(
            "Relit tout ton historique Strava et remplit les paramètres manquants "
            "(vitesse/allure moyenne et max, FC max, cadence) des sorties déjà "
            "importées — sans créer de doublon ni écraser tes valeurs."
        )
        bouton_completer.clicked.connect(lambda: self.lancer_synchronisation(historique_complet=True))
        sync_layout.addWidget(bouton_completer)

        self.label_resultat_sync = QLabel("")
        self.label_resultat_sync.setObjectName("texteSecondaire")
        self.label_resultat_sync.setWordWrap(True)
        sync_layout.addWidget(self.label_resultat_sync)

        principal.addWidget(cadre_sync)
        principal.addStretch()

        self.setStyleSheet(obtenir_style_ecran())

        if athlete_id_initial is not None:
            for i in range(self.combo_athlete.count()):
                if self.combo_athlete.itemData(i) == athlete_id_initial:
                    self.combo_athlete.setCurrentIndex(i)
                    break

    def _texte_statut_connexion(self):
        if obtenir_parametre("strava_access_token"):
            return "✅ Connecté à Strava."
        return "Non connecté."

    def enregistrer_configuration(self):
        client_id = self.champ_client_id.text().strip()
        client_secret = self.champ_client_secret.text().strip()

        if not client_id or not client_secret:
            QMessageBox.warning(self, "Champs requis", "Renseigne le Client ID et le Client Secret.")
            return

        definir_parametre("strava_client_id", client_id)
        definir_parametre("strava_client_secret", client_secret)
        QMessageBox.information(self, "Enregistré", "Configuration enregistrée.")

    def lancer_connexion(self):
        # Sauvegarde automatiquement ce qui est dans les champs — évite
        # de devoir cliquer "Enregistrer" séparément avant de se
        # connecter, et garantit que la connexion utilise toujours la
        # valeur actuellement affichée, pas une ancienne valeur oubliée.
        client_id = self.champ_client_id.text().strip()
        client_secret = self.champ_client_secret.text().strip()

        if not client_id or not client_secret:
            QMessageBox.warning(
                self, "Configuration requise",
                "Renseigne le Client ID et le Client Secret."
            )
            return

        definir_parametre("strava_client_id", client_id)
        definir_parametre("strava_client_secret", client_secret)

        self.bouton_connecter.setEnabled(False)
        self.bouton_connecter.setText("En attente d'autorisation dans le navigateur...")

        try:
            demarrer_flux_autorisation(client_id)
        except OSError as erreur:
            QMessageBox.critical(
                self, "Erreur",
                f"Impossible de démarrer le serveur local d'autorisation :\n{erreur}"
            )
            self._reinitialiser_bouton_connexion()
            return

        self.minuteur_oauth = QTimer(self)
        self.minuteur_oauth.timeout.connect(self._verifier_autorisation)
        self.minuteur_oauth.start(500)

    def _verifier_autorisation(self):
        code, erreur, termine = verifier_code_recu()
        if not termine:
            return

        self.minuteur_oauth.stop()

        if erreur:
            QMessageBox.warning(self, "Autorisation refusée", f"Strava a renvoyé une erreur : {erreur}")
            self._reinitialiser_bouton_connexion()
            return

        client_id = obtenir_parametre("strava_client_id")
        client_secret = obtenir_parametre("strava_client_secret")

        jetons, erreur = echanger_code_contre_jetons(client_id, client_secret, code)
        self._reinitialiser_bouton_connexion()

        if erreur:
            QMessageBox.critical(self, "Erreur", f"Impossible de finaliser la connexion :\n{erreur}")
            return

        sauvegarder_jetons(jetons)
        self.label_statut_connexion.setText(self._texte_statut_connexion())
        QMessageBox.information(self, "Connecté", "Connexion à Strava réussie !")

    def _reinitialiser_bouton_connexion(self):
        self.bouton_connecter.setEnabled(True)
        self.bouton_connecter.setText("🔐 Se connecter à Strava")

    def lancer_synchronisation(self, historique_complet=False):
        athlete_id = self.combo_athlete.currentData()
        if athlete_id is None:
            QMessageBox.warning(self, "Athlète requis", "Sélectionne un athlète.")
            return

        client_id = obtenir_parametre("strava_client_id")
        client_secret = obtenir_parametre("strava_client_secret")

        if not obtenir_parametre("strava_access_token"):
            QMessageBox.warning(self, "Non connecté", "Connecte-toi d'abord à Strava (étape 2).")
            return

        self.label_resultat_sync.setText("Synchronisation en cours...")

        def progression(i, total):
            self.label_resultat_sync.setText(f"Synchronisation en cours... {i}/{total}")
            self.label_resultat_sync.repaint()

        nb_nouvelles, nb_erreurs, erreur = synchroniser(
            athlete_id, client_id, client_secret, callback_progression=progression,
            historique_complet=bool(historique_complet),
        )

        if erreur:
            self.label_resultat_sync.setText(f"⚠️ {erreur}")
            return

        from interface.strava_sync import DERNIER_BILAN
        self.label_resultat_sync.setText(
            f"✅ {nb_nouvelles} nouvelle(s) activité(s) importée(s)"
            + (f", {DERNIER_BILAN['completees']} sortie(s) existante(s) complétée(s)"
               if DERNIER_BILAN["completees"] else "")
            + (f", {nb_erreurs} erreur(s)" if nb_erreurs else "")
        )
