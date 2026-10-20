"""
Écran « ☁️ Garmin Connect » : synchronisation automatique des sorties et de
la santé (sommeil, VFC, FC de repos, Body Battery, stress, SpO₂, etc.) depuis
le compte Garmin Connect, sans câble USB. Voir data/garmin_connect.py.
"""

from datetime import date, timedelta

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QPushButton,
    QFrame, QLineEdit, QMessageBox, QScrollArea, QCheckBox, QProgressBar,
    QTableWidget, QTableWidgetItem,
)

from data import garmin_connect as gc
from data.database import connexion, obtenir_athletes, obtenir_parametre, definir_parametre
from interface import arriere_plan
from interface.ecran_liste import obtenir_style_ecran, configurer_table_redimensionnable

# (libellé, jours de sorties, jours de santé)
PROFONDEURS = [
    ("Récent (14 jours)", 14, 14),
    ("30 jours", 30, 30),
    ("90 jours", 90, 90),
    ("1 an", 365, 365),
    ("Tout l'historique (long : plusieurs heures possibles)", 7300, 2000),
]


def lignes_sante_recentes(athlete_id, nb=14):
    """Derniers jours de santé en base (lecture seule) pour le tableau de l'écran."""
    conn = connexion()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT r.date, r.fc_repos, r.hrv_nuit_ms, r.hrv_statut, r.sommeil_duree_h, r.sommeil_score,
               r.body_battery_max, r.stress_moyen, r.spo2_moyenne,
               g.pas, g.readiness_score, g.statut_entrainement, g.vo2max
        FROM recuperation_quotidienne r
        LEFT JOIN garmin_quotidien g ON g.athlete_id=r.athlete_id AND g.date=r.date
        WHERE r.athlete_id=? ORDER BY r.date DESC LIMIT ?
        """,
        (athlete_id, nb),
    )
    lignes = cur.fetchall()
    conn.close()
    return lignes


class GarminEcran(QMainWindow):

    def __init__(self, athlete_id_initial=None):
        super().__init__()
        self.setWindowTitle("TrailMaster Pro – Garmin Connect")
        self.resize(1000, 820)
        self.setMinimumSize(760, 600)
        self.etat = {}
        self.en_cours = False
        self.minuteur = QTimer(self)
        self.minuteur.setInterval(300)
        self.minuteur.timeout.connect(self._maj_progression)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.setCentralWidget(scroll)
        central = QWidget()
        scroll.setWidget(central)
        principal = QVBoxLayout(central)
        principal.setContentsMargins(25, 20, 25, 20)
        principal.setSpacing(15)

        titre = QLabel("☁️ Garmin Connect (synchro automatique)")
        titre.setObjectName("titrePage")
        sous = QLabel(
            "Ta montre envoie ses données à Garmin Connect par Bluetooth via ton téléphone ; "
            "TrailMaster va les chercher ici, sans câble USB : sorties (avec trace GPS), sommeil, "
            "VFC, FC de repos, Body Battery, stress, SpO₂, pas, disponibilité d'entraînement, VO₂max, poids."
        )
        sous.setObjectName("sousTitrePage")
        sous.setWordWrap(True)
        principal.addWidget(titre)
        principal.addWidget(sous)

        barre = QHBoxLayout()
        lab = QLabel("Athlète :")
        lab.setObjectName("labelChamp")
        self.combo_athlete = QComboBox()
        for a in obtenir_athletes():
            self.combo_athlete.addItem(f"{a[2]} {a[1]}", a[0])
        if athlete_id_initial is not None:
            for i in range(self.combo_athlete.count()):
                if self.combo_athlete.itemData(i) == athlete_id_initial:
                    self.combo_athlete.setCurrentIndex(i)
        self.combo_athlete.currentIndexChanged.connect(self._rafraichir_tableau)
        barre.addWidget(lab)
        barre.addWidget(self.combo_athlete)
        barre.addStretch()
        principal.addLayout(barre)

        # ---- 1. Connexion
        cadre1 = QFrame()
        cadre1.setObjectName("carteForm")
        l1 = QVBoxLayout(cadre1)
        t1 = QLabel("1️⃣ Compte Garmin Connect")
        t1.setObjectName("titreCarte")
        l1.addWidget(t1)
        self.label_statut = QLabel("")
        self.label_statut.setObjectName("texteSecondaire")
        self.label_statut.setWordWrap(True)
        l1.addWidget(self.label_statut)
        self.champ_email = QLineEdit(gc.email_enregistre())
        self.champ_email.setPlaceholderText("Adresse e-mail du compte Garmin Connect")
        self.champ_mdp = QLineEdit()
        self.champ_mdp.setPlaceholderText("Mot de passe Garmin Connect")
        self.champ_mdp.setEchoMode(QLineEdit.EchoMode.Password)
        self.champ_mdp.returnPressed.connect(self.se_connecter)
        self.bouton_connecter = QPushButton("🔐 Se connecter à Garmin Connect")
        self.bouton_connecter.setObjectName("boutonPrincipal")
        self.bouton_connecter.clicked.connect(self.se_connecter)
        self.bouton_deconnecter = QPushButton("Se déconnecter (oublier mon mot de passe)")
        self.bouton_deconnecter.setObjectName("boutonSecondaire")
        self.bouton_deconnecter.clicked.connect(self.se_deconnecter)
        l1.addWidget(self.champ_email)
        l1.addWidget(self.champ_mdp)
        l1.addWidget(self.bouton_connecter)
        l1.addWidget(self.bouton_deconnecter)
        note = QLabel(
            "Ton mot de passe n'est jamais écrit dans la base TrailMaster : il reste dans le "
            "trousseau de ton ordinateur (Windows / macOS), avec des jetons de connexion. "
            "Garmin ne fournit pas d'accès officiel pour un logiciel personnel : cette connexion "
            "imite le site web et peut cesser de marcher si Garmin le modifie. L'import par USB ou "
            "par export de données reste disponible dans ce cas."
        )
        note.setObjectName("texteSecondaire")
        note.setWordWrap(True)
        l1.addWidget(note)
        principal.addWidget(cadre1)

        # ---- 2. Synchro
        cadre2 = QFrame()
        cadre2.setObjectName("carteForm")
        l2 = QVBoxLayout(cadre2)
        t2 = QLabel("2️⃣ Synchronisation")
        t2.setObjectName("titreCarte")
        l2.addWidget(t2)

        ligne = QHBoxLayout()
        ligne.addWidget(QLabel("Période à récupérer :"))
        self.combo_profondeur = QComboBox()
        for lib, _js, _jh in PROFONDEURS:
            self.combo_profondeur.addItem(lib)
        ligne.addWidget(self.combo_profondeur, 1)
        l2.addLayout(ligne)

        self.case_sorties = QCheckBox("Sorties (trace GPS, FC, dénivelé) — jamais de doublon")
        self.case_sorties.setChecked(True)
        self.case_sante = QCheckBox(
            "Santé : sommeil, VFC, FC de repos, Body Battery, stress, SpO₂, pas, disponibilité, VO₂max, poids"
        )
        self.case_sante.setChecked(True)
        self.case_auto = QCheckBox("Synchroniser automatiquement une fois par jour à l'ouverture de TrailMaster")
        self.case_auto.setChecked(obtenir_parametre("garmin_synchro_auto", "0") == "1")
        self.case_auto.toggled.connect(
            lambda v: definir_parametre("garmin_synchro_auto", "1" if v else "0"))
        for c in (self.case_sorties, self.case_sante, self.case_auto):
            l2.addWidget(c)

        boutons = QHBoxLayout()
        self.bouton_sync = QPushButton("🔄 Synchroniser maintenant")
        self.bouton_sync.setObjectName("boutonPrincipal")
        self.bouton_sync.clicked.connect(self.synchroniser)
        self.bouton_annuler = QPushButton("⏹ Annuler")
        self.bouton_annuler.setObjectName("boutonSecondaire")
        self.bouton_annuler.clicked.connect(self._annuler)
        self.bouton_annuler.setEnabled(False)
        boutons.addWidget(self.bouton_sync, 1)
        boutons.addWidget(self.bouton_annuler)
        l2.addLayout(boutons)

        self.barre = QProgressBar()
        self.barre.setVisible(False)
        l2.addWidget(self.barre)
        self.label_progression = QLabel("")
        self.label_progression.setObjectName("texteSecondaire")
        l2.addWidget(self.label_progression)
        self.label_resultat = QLabel("")
        self.label_resultat.setWordWrap(True)
        l2.addWidget(self.label_resultat)
        principal.addWidget(cadre2)

        # ---- 3. Derniers jours
        t3 = QLabel("Derniers jours de santé enregistrés")
        t3.setObjectName("titreCarte")
        principal.addWidget(t3)
        self.table = QTableWidget()
        colonnes = ["Date", "FC repos", "VFC nuit (ms)", "Statut VFC", "Sommeil (h)", "Score sommeil",
                    "Body Battery max", "Stress", "SpO₂ %", "Pas", "Dispo. entraînement", "Statut", "VO₂max"]
        self.table.setColumnCount(len(colonnes))
        self.table.setHorizontalHeaderLabels(colonnes)
        configurer_table_redimensionnable(self.table)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setMinimumHeight(320)
        principal.addWidget(self.table)

        self.setStyleSheet(obtenir_style_ecran())
        self._maj_statut()
        self._rafraichir_tableau()

    # ------------------------------------------------------------
    def _athlete(self):
        return self.combo_athlete.currentData()

    def _maj_statut(self):
        if gc.est_connecte():
            derniere = gc.derniere_synchro_texte()
            email = gc.email_enregistre()
            self.label_statut.setText(
                f"✅ Connecté{' : ' + email if email else ''}. "
                + (f"Dernière synchronisation : {derniere}." if derniere else "Pas encore synchronisé.")
            )
        else:
            self.label_statut.setText("Non connecté. Entre l'adresse e-mail et le mot de passe de ton compte Garmin Connect.")
        connecte = gc.est_connecte()
        self.champ_email.setVisible(not connecte)
        self.champ_mdp.setVisible(not connecte)
        self.bouton_connecter.setVisible(not connecte)
        self.bouton_deconnecter.setVisible(connecte)
        self.bouton_sync.setEnabled(connecte and not self.en_cours)

    def _rafraichir_tableau(self):
        athlete = self._athlete()
        lignes = lignes_sante_recentes(athlete) if athlete is not None else []
        self.table.setRowCount(len(lignes))

        def txt(v, fmt="{}"):
            return "—" if v in (None, "") else fmt.format(v)

        for i, r in enumerate(lignes):
            valeurs = [
                date.fromisoformat(r[0]).strftime("%d/%m/%Y") if r[0] else "—",
                txt(r[1]), txt(r[2], "{:.0f}"), txt(r[3]), txt(r[4], "{:.1f}"), txt(r[5]),
                txt(r[6]), txt(r[7]), txt(r[8], "{:.0f}"), txt(r[9]),
                txt(r[10]), txt(r[11]), txt(r[12], "{:.1f}"),
            ]
            for j, v in enumerate(valeurs):
                self.table.setItem(i, j, QTableWidgetItem(v))
        self.table.resizeColumnsToContents()

    # ------------------------------------------------------------
    def se_connecter(self):
        email = self.champ_email.text().strip()
        mdp = self.champ_mdp.text()
        self.bouton_connecter.setEnabled(False)
        self.label_statut.setText("Connexion en cours…")

        def travail():
            gc.se_connecter(email, mdp)
            return True

        def fini(res, erreur):
            self.bouton_connecter.setEnabled(True)
            self.champ_mdp.clear()
            if erreur:
                QMessageBox.warning(self, "Connexion impossible", str(erreur))
            self._maj_statut()

        arriere_plan.executer(travail, fini, proprietaire=self)

    def se_deconnecter(self):
        gc.se_deconnecter()
        self.champ_email.setText("")
        self.label_resultat.setText("")
        self._maj_statut()

    def synchroniser(self):
        athlete = self._athlete()
        if athlete is None:
            QMessageBox.warning(self, "Athlète requis", "Sélectionne un athlète.")
            return
        if not (self.case_sorties.isChecked() or self.case_sante.isChecked()):
            QMessageBox.information(self, "Rien à faire", "Coche au moins « Sorties » ou « Santé ».")
            return
        _lib, js, jh = PROFONDEURS[self.combo_profondeur.currentIndex()]
        self.etat = {"msg": "Démarrage…", "fait": 0, "total": 0, "annuler": False}
        self.en_cours = True
        self.bouton_sync.setEnabled(False)
        self.bouton_annuler.setEnabled(True)
        self.barre.setVisible(True)
        self.barre.setRange(0, 0)
        self.label_resultat.setText("")
        self.minuteur.start()
        etat = self.etat
        avec_sorties = self.case_sorties.isChecked()
        avec_sante = self.case_sante.isChecked()

        def travail():
            return gc.synchroniser(athlete, js, jh, avec_sorties, avec_sante, etat)

        arriere_plan.executer(travail, self._fini, proprietaire=self)

    def _annuler(self):
        self.etat["annuler"] = True
        self.label_progression.setText("Annulation en cours…")

    def _maj_progression(self):
        total, fait = self.etat.get("total", 0), self.etat.get("fait", 0)
        if total:
            self.barre.setRange(0, total)
            self.barre.setValue(min(fait, total))
        phase = {"sorties": "Sorties", "sante": "Santé"}.get(self.etat.get("phase"), "")
        self.label_progression.setText(
            (f"{phase} — " if phase else "") + self.etat.get("msg", "")
            + (f"  ({fait}/{total})" if total else "")
        )

    def _fini(self, res, erreur):
        self.minuteur.stop()
        self.en_cours = False
        self.barre.setVisible(False)
        self.label_progression.setText("")
        self.bouton_annuler.setEnabled(False)
        if erreur:
            self.label_resultat.setStyleSheet("color:#c0392b;")
            self.label_resultat.setText(f"⚠️ {erreur}")
        else:
            self.label_resultat.setStyleSheet("")
            self.label_resultat.setText(gc.resume_texte(res))
        self._maj_statut()
        self._rafraichir_tableau()
