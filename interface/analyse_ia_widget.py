"""
Carte « 🤖 Analyser » (v106) — à poser en bas d'un écran de résultats. Au clic : le logiciel
construit le dossier de chiffres de l'écran, puis l'IA le lit (ou un résumé local sans clé).
Les analyses sont gardées en mémoire tant que les chiffres ne changent pas.
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QMessageBox

from data.database import obtenir_parametre, definir_parametre
from data import analyse_ecran as ae

CLE_CONSENTEMENT = "ia_ecrans_consentement"
LIBELLE_SOURCE = {
    "ia": "Analyse générée par l'IA à partir des chiffres de cet écran.",
    "cache": "Analyse déjà générée : les chiffres n'ont pas changé, aucun nouvel appel.",
    "local": "Résumé calculé en local (aucune clé IA configurée : Réglages > Analyse IA).",
}


class CarteAnalyseIA(QFrame):

    def __init__(self, sujet, titre, athlete_getter, dossier_getter, parent=None):
        super().__init__(parent)
        self.setObjectName("carteForm")
        self.sujet, self.titre = sujet, titre
        self._athlete, self._dossier = athlete_getter, dossier_getter
        self._tache = None
        lay = QVBoxLayout(self)
        entete = QHBoxLayout()
        t = QLabel(f"🤖 Analyse IA — {titre}")
        t.setObjectName("titreCarte")
        entete.addWidget(t)
        entete.addStretch()
        self.bouton = QPushButton("Analyser")
        self.bouton.setObjectName("boutonPrincipal")
        self.bouton.clicked.connect(lambda: self.lancer(False))
        self.bouton_regen = QPushButton("Régénérer")
        self.bouton_regen.setVisible(False)
        self.bouton_regen.clicked.connect(lambda: self.lancer(True))
        entete.addWidget(self.bouton)
        entete.addWidget(self.bouton_regen)
        lay.addLayout(entete)
        self.texte = QLabel("")
        self.texte.setWordWrap(True)
        self.texte.setTextFormat(Qt.TextFormat.MarkdownText)
        self.texte.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.texte.setVisible(False)
        lay.addWidget(self.texte)
        self.note = QLabel("L'IA lit uniquement les chiffres calculés par TrailMaster et n'en invente aucun.")
        self.note.setObjectName("texteSecondaire")
        self.note.setWordWrap(True)
        lay.addWidget(self.note)

    # ------------------------------------------------------------
    def _consentement(self):
        if obtenir_parametre(CLE_CONSENTEMENT, "0") == "1" or not ae.cle_ia_disponible():
            return True
        rep = QMessageBox.question(
            self, "Envoyer les chiffres de cet écran à l'IA ?",
            "Pour rédiger l'analyse, les chiffres de cet écran (poids, sommeil, charge, performances…) sont "
            "envoyés au service IA que tu as configuré (Gemini ou Groq). Aucun nom ni identifiant n'est envoyé.\n\n"
            "Autoriser pour tous les écrans ?")
        if rep == QMessageBox.StandardButton.Yes:
            definir_parametre(CLE_CONSENTEMENT, "1")
            return True
        return False

    def lancer(self, forcer=False):
        a = self._athlete()
        if a is None:
            self._afficher("Sélectionne un athlète.", "local", erreur=True)
            return
        try:
            dossier = self._dossier()
        except Exception as e:
            self._afficher(f"Impossible de préparer les chiffres : {e}", "local", erreur=True)
            return
        if not self._consentement():
            return
        self.bouton.setEnabled(False)
        self.bouton_regen.setEnabled(False)
        self.note.setText("Analyse en cours…")
        from interface.tache_ia import TacheAnalyseIA
        self._tache = TacheAnalyseIA(lambda: ae.analyser(a, self.sujet, dossier, forcer), self)
        self._tache.reussite.connect(self._fini)
        self._tache.echec.connect(lambda m: self._afficher(m, "local", erreur=True))
        self._tache.start()

    def _fini(self, resultat):
        texte, source = resultat
        self._afficher(texte, source)

    def _afficher(self, texte, source, erreur=False):
        self.bouton.setEnabled(True)
        self.bouton_regen.setEnabled(True)
        self.texte.setVisible(True)
        self.texte.setText(texte)
        self.bouton_regen.setVisible(not erreur and source in ("ia", "cache"))
        self.note.setText("" if erreur else LIBELLE_SOURCE.get(source, ""))
