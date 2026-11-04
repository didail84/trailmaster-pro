"""
Carte « 🤖 Analyse IA » (v106, automatique depuis Trail Hub Center) — posée en bas d'un écran
de résultats. Le logiciel construit le dossier de chiffres de l'écran, puis l'IA le lit (ou un
résumé local sans clé).

Depuis Trail Hub Center, l'analyse se lance toute seule à l'ouverture de l'écran et quand on
change d'athlète (Réglages > Analyse IA > « Analyses automatiques »). Elle attend que les
chiffres de l'écran aient fini de se charger, et ne rappelle pas l'IA tant qu'ils ne changent
pas : l'analyse déjà faite est reprise du cache, sans consommer de quota. Tout écran, présent
ou futur, qui pose cette carte en profite sans rien ajouter.
"""

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QFrame, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QMessageBox

from data.database import obtenir_parametre, definir_parametre
from data import analyse_ecran as ae

CLE_CONSENTEMENT = "ia_ecrans_consentement"      # "1" accepté, "-1" refusé (plus redemandé à l'ouverture)
LIBELLE_SOURCE = {
    "ia": "Analyse générée par l'IA à partir des chiffres de cet écran.",
    "cache": "Analyse déjà générée : les chiffres n'ont pas changé, aucun nouvel appel.",
    "local": "Résumé calculé en local (aucune clé IA configurée : Réglages > Analyse IA).",
    "refus": "Résumé calculé en local : tu as choisi de ne pas envoyer les chiffres des écrans à l'IA "
             "(clique sur « Analyser avec l'IA » pour changer d'avis).",
}
DELAI_STABILITE_MS = 1200     # intervalle entre deux lectures du dossier
ESSAIS_STABILITE = 5          # au plus ~6 s d'attente que l'écran ait fini de se remplir


def analyses_automatiques_actives():
    from noyau.ia.analyse_auto import actif
    return actif()


class CarteAnalyseIA(QFrame):

    def __init__(self, sujet, titre, athlete_getter, dossier_getter, parent=None):
        super().__init__(parent)
        self.setObjectName("carteForm")
        self.sujet, self.titre = sujet, titre
        self._athlete, self._dossier = athlete_getter, dossier_getter
        self._tache = None
        self._branche = False
        self._derniere_empreinte = None      # dossier déjà analysé (automatiquement ou non)
        self._empreinte_precedente = None    # pour attendre que le dossier soit stable
        self._essais = 0
        self._minuterie = QTimer(self)
        self._minuterie.setSingleShot(True)
        self._minuterie.setInterval(DELAI_STABILITE_MS)
        self._minuterie.timeout.connect(self._verifier_auto)

        lay = QVBoxLayout(self)
        entete = QHBoxLayout()
        t = QLabel(f"🤖 Analyse IA — {titre}")
        t.setObjectName("titreCarte")
        entete.addWidget(t)
        entete.addStretch()
        self.bouton = QPushButton("Analyser")
        self.bouton.setObjectName("boutonPrincipal")
        self.bouton.clicked.connect(lambda: self.lancer(False, manuel=True))
        self.bouton_regen = QPushButton("Régénérer")
        self.bouton_regen.setVisible(False)
        self.bouton_regen.clicked.connect(lambda: self.lancer(True, manuel=True))
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
        self._maj_bouton()

    def _maj_bouton(self):
        auto = analyses_automatiques_actives()
        self.bouton.setText("Analyser maintenant" if auto else "Analyser")
        if auto and not self.texte.isVisible():
            self.note.setText("L'analyse se lance automatiquement dès que les chiffres de l'écran sont prêts.")

    # ------------------------------------------------------------ automatique
    def showEvent(self, event):
        super().showEvent(event)
        if not self._branche:
            self._branche = True
            fenetre = self.window()
            combo = getattr(fenetre, "combo_athlete", None)
            if combo is not None and hasattr(combo, "currentIndexChanged"):
                combo.currentIndexChanged.connect(lambda *_: self.programmer_auto())
        self.programmer_auto()

    def programmer_auto(self):
        """Relance l'attente de stabilité, puis l'analyse si le dossier a changé."""
        if not analyses_automatiques_actives():
            return
        self._empreinte_precedente = None
        self._essais = 0
        self._minuterie.start()

    def _verifier_auto(self):
        if not self.isVisible() or self._tache is not None and self._tache.isRunning():
            return
        a = self._athlete()
        if a is None:
            return
        try:
            dossier = self._dossier()
        except Exception:
            return
        if not dossier:
            return
        empreinte = (a, ae._empreinte(self.sujet, dossier))
        self._essais += 1
        if empreinte != self._empreinte_precedente and self._essais < ESSAIS_STABILITE:
            self._empreinte_precedente = empreinte   # l'écran se remplit encore : on attend
            self._minuterie.start()
            return
        if empreinte == self._derniere_empreinte:
            return                                   # déjà analysé tel quel
        self.lancer(False, dossier=dossier)

    # ------------------------------------------------------------
    def _consentement(self, manuel):
        if not ae.cle_ia_disponible():
            return True
        etat = obtenir_parametre(CLE_CONSENTEMENT, "0")
        if etat == "1":
            return True
        if etat == "-1" and not manuel:
            return False
        rep = QMessageBox.question(
            self, "Envoyer les chiffres des écrans à l'IA ?",
            "Pour rédiger l'analyse, les chiffres de cet écran (poids, sommeil, charge, performances…) sont "
            "envoyés au service IA que tu as configuré (Gemini ou Groq). Aucun nom ni identifiant n'est envoyé.\n\n"
            "Autoriser pour tous les écrans ? Les analyses se feront ensuite automatiquement à l'ouverture.")
        if rep == QMessageBox.StandardButton.Yes:
            definir_parametre(CLE_CONSENTEMENT, "1")
            return True
        definir_parametre(CLE_CONSENTEMENT, "-1")
        return False

    def lancer(self, forcer=False, manuel=False, dossier=None):
        a = self._athlete()
        if a is None:
            self._afficher("Sélectionne un athlète.", "local", erreur=True)
            return
        try:
            dossier = dossier if dossier is not None else self._dossier()
        except Exception as e:
            self._afficher(f"Impossible de préparer les chiffres : {e}", "local", erreur=True)
            return
        self._derniere_empreinte = (a, ae._empreinte(self.sujet, dossier))
        autorise = self._consentement(manuel)
        self.bouton.setEnabled(False)
        self.bouton_regen.setEnabled(False)
        self.note.setText("Analyse en cours…")
        from interface.tache_ia import TacheAnalyseIA
        if autorise:
            travail = lambda: ae.analyser(a, self.sujet, dossier, forcer)
        else:
            travail = lambda: (ae.resume_local(self.sujet, dossier), "refus")
        self._tache = TacheAnalyseIA(travail, self)
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
        if source == "refus":
            self.bouton.setText("Analyser avec l'IA")
        self.note.setText("" if erreur else LIBELLE_SOURCE.get(source, ""))
