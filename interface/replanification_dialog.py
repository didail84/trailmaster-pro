"""
Fenêtre de la replanification automatique — présente le diagnostic
(séances ratées, ACWR, forme, FC), les changements proposés, et laisse
choisir d'appliquer ou non, avec un commentaire IA optionnel.
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextEdit,
    QCheckBox,
    QMessageBox,
    QListWidget,
    QListWidgetItem,
)

from interface.ecran_liste import obtenir_style_ecran
from interface.replanification import (
    proposer_replanification,
    appliquer_replanification,
    historique_replanifications,
)
from interface.ia_coach import commenter_replanification, cle_api_configuree, ErreurAnalyseIA
from interface.tache_ia import TacheAnalyseIA


class DialogueReplanification(QDialog):

    def __init__(self, plan_id, athlete_id, nom_plan, parent=None):
        super().__init__(parent)
        self.plan_id = plan_id
        self.athlete_id = athlete_id
        self.resume_ia_genere = None

        self.setWindowTitle(f"Replanification automatique — {nom_plan}")
        self.resize(820, 700)

        principal = QVBoxLayout(self)

        titre = QLabel("🔄 Replanification automatique")
        titre.setObjectName("titrePage")
        principal.addWidget(titre)

        self.diagnostic, self.niveau, self.raisons, self.propositions = proposer_replanification(
            plan_id, athlete_id
        )

        # --- Diagnostic ---
        titre_diag = QLabel("Diagnostic")
        titre_diag.setObjectName("titreCarte")
        principal.addWidget(titre_diag)

        libelles_niveau = {
            "alleger_fort": "🔴 Allègement important",
            "alleger_leger": "🟠 Allègement léger",
            "reprise_progressive": "🟡 Reprise progressive",
            "stable": "🟢 Plan maintenu tel quel",
        }
        label_niveau = QLabel(libelles_niveau.get(self.niveau, self.niveau))
        label_niveau.setObjectName("titreCarte")
        principal.addWidget(label_niveau)

        texte_raisons = "\n".join(f"• {r}" for r in self.raisons)
        label_raisons = QLabel(texte_raisons)
        label_raisons.setObjectName("texteSecondaire")
        label_raisons.setWordWrap(True)
        principal.addWidget(label_raisons)

        # --- Changements proposés ---
        titre_changements = QLabel(
            f"Changements proposés ({len(self.propositions)})"
            if self.propositions else "Aucun changement proposé"
        )
        titre_changements.setObjectName("titreCarte")
        principal.addWidget(titre_changements)

        self.liste_changements = QListWidget()
        self.liste_changements.setMinimumHeight(180)
        for prop in self.propositions:
            item = QListWidgetItem(f"• {prop['commentaire']}")
            self.liste_changements.addItem(item)
        principal.addWidget(self.liste_changements)

        # --- Commentaire IA optionnel ---
        self.case_ia = QCheckBox(
            "Générer aussi un commentaire du coach IA (reformulation, optionnel — "
            "nécessite internet)"
        )
        self.case_ia.setEnabled(cle_api_configuree() and bool(self.propositions))
        if not cle_api_configuree():
            self.case_ia.setText(self.case_ia.text() + " — aucune clé API configurée")
        principal.addWidget(self.case_ia)

        self.zone_ia = QTextEdit()
        self.zone_ia.setReadOnly(True)
        self.zone_ia.setVisible(False)
        self.zone_ia.setMaximumHeight(160)
        principal.addWidget(self.zone_ia)

        # --- Historique des passages précédents ---
        historique = historique_replanifications(plan_id)
        if historique:
            titre_historique = QLabel(f"Historique ({len(historique)} passage(s) précédent(s))")
            titre_historique.setObjectName("titreCarte")
            principal.addWidget(titre_historique)
            derniers = historique[:3]
            texte_historique = "\n".join(
                f"• {date_gen[:10]} — {niveau} ({nb} séance(s) modifiée(s))"
                for date_gen, niveau, resume, resume_ia, nb in derniers
            )
            label_historique = QLabel(texte_historique)
            label_historique.setObjectName("texteSecondaire")
            label_historique.setWordWrap(True)
            principal.addWidget(label_historique)

        # --- Boutons ---
        barre_boutons = QHBoxLayout()
        self.bouton_appliquer = QPushButton(
            "✅ Appliquer ces changements" if self.propositions
            else "✅ Enregistrer ce diagnostic (aucun changement)"
        )
        self.bouton_appliquer.setObjectName("boutonPrincipal")
        self.bouton_appliquer.clicked.connect(self._appliquer)
        bouton_annuler = QPushButton("Annuler")
        bouton_annuler.setObjectName("boutonSecondaire")
        bouton_annuler.clicked.connect(self.reject)
        barre_boutons.addWidget(bouton_annuler)
        barre_boutons.addStretch()
        barre_boutons.addWidget(self.bouton_appliquer)
        principal.addLayout(barre_boutons)

        self.setStyleSheet(obtenir_style_ecran())

    def _appliquer(self):
        if self.case_ia.isChecked() and self.case_ia.isEnabled() and self.resume_ia_genere is None:
            # On génère d'abord le commentaire IA (en tâche de fond), puis on
            # applique réellement une fois qu'il est revenu (ou a échoué).
            self.bouton_appliquer.setEnabled(False)
            self.bouton_appliquer.setText("⏳ Génération du commentaire IA...")

            resume_diagnostic = " ; ".join(self.raisons)
            resume_changements = "\n".join(p["commentaire"] for p in self.propositions) or (
                "Aucun changement — le plan reste tel quel."
            )

            self._tache_ia = TacheAnalyseIA(
                lambda: commenter_replanification(resume_diagnostic, resume_changements)
            )
            self._tache_ia.reussite.connect(self._commentaire_ia_recu)
            self._tache_ia.echec.connect(self._commentaire_ia_echoue)
            self._tache_ia.start()
            return

        self._enregistrer_et_fermer()

    def _commentaire_ia_recu(self, texte):
        self.resume_ia_genere = texte
        self.zone_ia.setPlainText(texte)
        self.zone_ia.setVisible(True)
        self._enregistrer_et_fermer()

    def _commentaire_ia_echoue(self, message):
        QMessageBox.warning(
            self, "Commentaire IA indisponible",
            f"Le commentaire IA n'a pas pu être généré ({message}).\n\n"
            "Le diagnostic local (toujours fiable) sera quand même enregistré."
        )
        self.resume_ia_genere = ""
        self._enregistrer_et_fermer()

    def _enregistrer_et_fermer(self):
        appliquer_replanification(
            self.plan_id, self.athlete_id, self.niveau, self.raisons,
            self.propositions, resume_ia=self.resume_ia_genere or None,
        )
        self.accept()
