"""
Petits outils d'interface partagés (v98) :
  - notifier()  : bulle de confirmation discrète qui s'efface seule (U8)
  - PaletteCommandes : fenêtre « Cmd/Ctrl+K » pour tout faire au clavier (U4)
  - installer_raccourcis() : raccourcis clavier du tableau de bord (U9)
"""

from PySide6.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve, QEvent
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication, QLabel, QDialog, QVBoxLayout, QLineEdit, QListWidget, QListWidgetItem,
    QGraphicsOpacityEffect, QWidget,
)

from interface.theme import PALETTE, POLICE_TEXTE, obtenir_couleur_accent


# ---------------------------------------------------------------------
# U8 — notifications douces
# ---------------------------------------------------------------------

class Toast(QLabel):
    """Bulle posée en bas de la fenêtre, avec fondu à l'apparition et à
    la disparition. Ne prend jamais le focus et ne bloque rien."""

    def __init__(self, parent, texte, type_message="ok", duree_ms=2600):
        super().__init__(texte, parent)
        couleurs = {
            "ok": obtenir_couleur_accent(),
            "info": PALETTE["texte_secondaire"],
            "alerte": "#E8A33D",
            "erreur": "#E5534B",
        }
        bord = couleurs.get(type_message, couleurs["ok"])
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setStyleSheet(
            f"background-color: {PALETTE['carte']}; color: {PALETTE['texte']};"
            f"border: 1px solid {bord}; border-left: 5px solid {bord};"
            f"border-radius: 10px; padding: 11px 18px; font-family: '{POLICE_TEXTE}'; font-size: 13px;"
        )
        self.setWordWrap(True)
        self.setMaximumWidth(520)
        self.adjustSize()
        self._effet = QGraphicsOpacityEffect(self)
        self._effet.setOpacity(0.0)
        self.setGraphicsEffect(self._effet)
        self._anim = QPropertyAnimation(self._effet, b"opacity", self)
        self._duree = duree_ms
        self._placer()
        self.show()
        self.raise_()
        self._animer(0.0, 1.0, 180)
        QTimer.singleShot(duree_ms, self._disparaitre)

    def _placer(self):
        p = self.parentWidget()
        if p is None:
            return
        self.adjustSize()
        self.move(max(10, (p.width() - self.width()) // 2), max(10, p.height() - self.height() - 28))

    def _animer(self, de, vers, ms):
        self._anim.stop()
        self._anim.setDuration(ms)
        self._anim.setStartValue(de)
        self._anim.setEndValue(vers)
        self._anim.setEasingCurve(QEasingCurve.Type.InOutQuad)
        self._anim.start()

    def _disparaitre(self):
        try:
            self._animer(1.0, 0.0, 300)
            self._anim.finished.connect(self.deleteLater)
        except RuntimeError:
            pass


def _fenetre_cible(parent=None):
    if parent is not None:
        return parent.window()
    actif = QApplication.activeWindow()
    if actif is not None:
        return actif
    for w in QApplication.topLevelWidgets():
        if w.isVisible():
            return w
    return None


def notifier(texte, type_message="ok", parent=None, duree_ms=2600):
    """Affiche une confirmation douce. Sans fenêtre visible (tests,
    démarrage), ne fait rien — jamais d'erreur."""
    fen = _fenetre_cible(parent)
    if fen is None:
        return None
    try:
        return Toast(fen, texte, type_message, duree_ms)
    except RuntimeError:
        return None


# ---------------------------------------------------------------------
# U4 — palette de commandes
# ---------------------------------------------------------------------

def _normaliser(texte):
    import unicodedata
    texte = unicodedata.normalize("NFD", str(texte or "").lower())
    return "".join(c for c in texte if unicodedata.category(c) != "Mn")


class PaletteCommandes(QDialog):
    """Champ de saisie + liste filtrée. `commandes` = liste de
    (libellé, mots_clés, fonction). `chercheur(texte)` (facultatif)
    renvoie des commandes supplémentaires (ex. sorties trouvées)."""

    def __init__(self, parent, commandes, chercheur=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setModal(True)
        self.resize(560, 420)
        self._commandes = commandes
        self._chercheur = chercheur
        self._affichees = []
        accent = obtenir_couleur_accent()
        self.setStyleSheet(
            f"QDialog {{ background-color: {PALETTE['fond_secondaire']}; border: 1px solid {accent}; border-radius: 12px; }}"
            f"QLineEdit {{ background-color: {PALETTE['carte']}; color: {PALETTE['texte']}; border: 1px solid {PALETTE['bordure']};"
            f" border-radius: 8px; padding: 10px 12px; font-size: 15px; }}"
            f"QListWidget {{ background: transparent; color: {PALETTE['texte']}; border: none; font-size: 13.5px; outline: none; }}"
            f"QListWidget::item {{ padding: 8px 10px; border-radius: 7px; }}"
            f"QListWidget::item:selected {{ background-color: {accent}; color: white; }}"
        )
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 14, 14, 14)
        lay.setSpacing(8)
        self.champ = QLineEdit()
        self.champ.setPlaceholderText("Tape une action, un écran ou un nom de sortie…   (Échap pour fermer)")
        self.champ.textChanged.connect(self._filtrer)
        self.liste = QListWidget()
        self.liste.itemActivated.connect(lambda _i: self._valider())
        self.liste.itemClicked.connect(lambda _i: self._valider())
        lay.addWidget(self.champ)
        lay.addWidget(self.liste, 1)
        self.champ.installEventFilter(self)
        self._filtrer("")

    def eventFilter(self, obj, event):
        if obj is self.champ and event.type() == QEvent.Type.KeyPress:
            cle = event.key()
            if cle in (Qt.Key.Key_Down, Qt.Key.Key_Up):
                n = self.liste.count()
                if n:
                    delta = 1 if cle == Qt.Key.Key_Down else -1
                    self.liste.setCurrentRow((self.liste.currentRow() + delta) % n)
                return True
            if cle in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                self._valider()
                return True
        return super().eventFilter(obj, event)

    def _filtrer(self, texte):
        t = _normaliser(texte).strip()
        mots = t.split()
        trouves = []
        for libelle, cles, fonction in self._commandes:
            cible = _normaliser(f"{libelle} {cles}")
            if all(m in cible for m in mots):
                trouves.append((libelle, fonction))
        if self._chercheur and len(t) >= 2:
            try:
                trouves.extend(self._chercheur(texte.strip()) or [])
            except Exception:
                pass
        self._affichees = trouves[:60]
        self.liste.clear()
        for libelle, _f in self._affichees:
            QListWidgetItem(libelle, self.liste)
        if self._affichees:
            self.liste.setCurrentRow(0)

    def _valider(self):
        ligne = self.liste.currentRow()
        if 0 <= ligne < len(self._affichees):
            fonction = self._affichees[ligne][1]
            self.accept()
            QTimer.singleShot(0, fonction)

    def showEvent(self, e):
        super().showEvent(e)
        p = self.parentWidget()
        if p is not None:
            g = p.window().geometry()
            self.move(g.center().x() - self.width() // 2, g.top() + 90)
        self.champ.setFocus()


# ---------------------------------------------------------------------
# U9 — raccourcis clavier
# ---------------------------------------------------------------------

AIDE_RACCOURCIS = [
    ("Ctrl/Cmd + K", "Palette de commandes (tout faire au clavier)"),
    ("Ctrl/Cmd + N", "Nouvelle activité"),
    ("Ctrl/Cmd + F", "Recherche globale"),
    ("Ctrl/Cmd + 1 … 9", "Aller à un écran du menu (1 = Aujourd'hui, 2 = Tableau de bord, 3 = Historique…)"),
    ("Échap", "Revenir à l'écran Aujourd'hui"),
    ("Alt + ← / Alt + →", "Sortie précédente / suivante (dans une fiche de sortie)"),
    ("Ctrl/Cmd + /", "Afficher cette aide"),
]


def installer_raccourcis(fenetre, actions):
    """actions = dict {séquence: fonction}. Les raccourcis sont liés à
    la fenêtre (actifs partout dedans)."""
    crees = []
    for sequence, fonction in actions.items():
        sc = QShortcut(QKeySequence(sequence), fenetre)
        sc.setContext(Qt.ShortcutContext.WindowShortcut)
        sc.activated.connect(fonction)
        crees.append(sc)
    return crees
