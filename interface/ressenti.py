"""
S8 — Ressenti en 3 clics après la sortie : effort, jambes, humeur.
Chaque ligne a trois gros boutons ; dès que les trois réponses sont
données, le ressenti s'enregistre tout seul.
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QButtonGroup, QFrame,
)

import data.metriques as met
from interface.theme import PALETTE, obtenir_couleur_accent
from interface.outils_ui import notifier

ICONES = {
    "effort": {1: "😌", 2: "🙂", 3: "🥵"},
    "jambes": {1: "🪶", 2: "🦵", 3: "🪨"},
    "humeur": {1: "😐", 2: "🙂", 3: "🤩"},
}


class DialogueRessenti(QDialog):

    def __init__(self, activite_id, athlete_id, titre_sortie="", parent=None, apres=None):
        super().__init__(parent)
        self.activite_id, self.athlete_id, self._apres = activite_id, athlete_id, apres
        self.setWindowTitle("Comment c'était ?")
        self.setMinimumWidth(460)
        accent = obtenir_couleur_accent()
        self.setStyleSheet(
            f"QDialog {{ background-color: {PALETTE['fond_secondaire']}; }}"
            f"QLabel {{ color: {PALETTE['texte']}; }}"
            f"QPushButton[choix='1'] {{ background-color: {PALETTE['carte']}; color: {PALETTE['texte']};"
            f" border: 1px solid {PALETTE['bordure']}; border-radius: 10px; padding: 12px 6px; font-size: 14px; }}"
            f"QPushButton[choix='1']:hover {{ border-color: {accent}; }}"
            f"QPushButton[choix='1']:checked {{ background-color: {accent}; color: white; border-color: {accent}; font-weight: 700; }}"
        )
        lay = QVBoxLayout(self)
        lay.setSpacing(12)
        t = QLabel(f"<b>Comment c'était ?</b><br><span style='color:{PALETTE['texte_secondaire']}'>{titre_sortie}</span>")
        lay.addWidget(t)
        self.groupes, self.valeurs = {}, {}
        existant = met.ressenti_de_sortie(activite_id) or {}
        for cle, (libelle, options) in met.LIBELLES_RESSENTI.items():
            lay.addWidget(QLabel(libelle))
            ligne = QHBoxLayout()
            groupe = QButtonGroup(self)
            groupe.setExclusive(True)
            for valeur, texte in options.items():
                b = QPushButton(f"{ICONES[cle][valeur]}  {texte}")
                b.setProperty("choix", "1")
                b.setCheckable(True)
                b.setCursor(Qt.CursorShape.PointingHandCursor)
                b.clicked.connect(lambda _c=False, k=cle, v=valeur: self._choisir(k, v))
                if existant.get(cle) == valeur:
                    b.setChecked(True)
                    self.valeurs[cle] = valeur
                groupe.addButton(b)
                ligne.addWidget(b)
            self.groupes[cle] = groupe
            lay.addLayout(ligne)
        bas = QHBoxLayout()
        bas.addStretch()
        passer = QPushButton("Plus tard")
        passer.clicked.connect(self.reject)
        bas.addWidget(passer)
        lay.addLayout(bas)

    def _choisir(self, cle, valeur):
        self.valeurs[cle] = valeur
        if len(self.valeurs) == 3:
            met.enregistrer_ressenti(self.activite_id, self.athlete_id, self.valeurs["effort"],
                                     self.valeurs["jambes"], self.valeurs["humeur"])
            self.accept()
            notifier("Ressenti enregistré", parent=self.parentWidget())
            if self._apres:
                self._apres()


def texte_ressenti(r):
    """« 🥵 Dur · 🪨 Jambes lourdes · 🤩 Super » (ou None)."""
    if not r:
        return None
    morceaux = []
    for cle, (libelle, options) in met.LIBELLES_RESSENTI.items():
        v = r.get(cle)
        if v:
            morceaux.append(f"{ICONES[cle][v]} {libelle} : {options[v].lower()}")
    return " · ".join(morceaux) or None


class BandeauRessenti(QFrame):
    """Petite carte à poser dans une fiche de sortie."""

    def __init__(self, activite_id, athlete_id, titre_sortie="", parent=None):
        super().__init__(parent)
        self.setObjectName("carteForm")
        self.activite_id, self.athlete_id, self.titre_sortie = activite_id, athlete_id, titre_sortie
        lay = QHBoxLayout(self)
        self.label = QLabel()
        self.label.setWordWrap(True)
        self.bouton = QPushButton()
        self.bouton.clicked.connect(self._ouvrir)
        lay.addWidget(self.label, 1)
        lay.addWidget(self.bouton)
        self.rafraichir()

    def rafraichir(self):
        r = met.ressenti_de_sortie(self.activite_id)
        t = texte_ressenti(r)
        self.label.setText(f"💬 Ressenti : {t}" if t else "💬 Ressenti : pas encore noté")
        self.bouton.setText("Modifier" if t else "Noter en 3 clics")

    def _ouvrir(self):
        DialogueRessenti(self.activite_id, self.athlete_id, self.titre_sortie, self.window(), self.rafraichir).exec()
        self.rafraichir()
