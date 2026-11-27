"""
Panneau de détail (interface commune v109) : un clic sur une sortie
l'ouvre à droite de la fenêtre, sans quitter la page en cours — chiffres
clés, ressenti, dernière analyse (Claude ou règles), et un bouton vers la
fiche complète. Échap ou ✕ le ferme.

Barre d'état : en bas de la fenêtre, l'état du pont avec Claude, les
demandes en attente et la version.
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QScrollArea, QVBoxLayout, QWidget

from noyau.donnees import base
from interface.theme import PALETTE, obtenir_couleur_accent


def resume_sortie(activite_id):
    l = base.lire_un("SELECT id, nom, date, type, distance, denivele, duree, frequence_cardiaque_moyenne, source, "
                     "notes FROM activites WHERE id=?", (activite_id,))
    if not l:
        return None
    s = dict(zip(("id", "nom", "date", "type", "distance", "denivele", "duree", "fc", "source", "notes"), l))
    s["ressenti"] = None
    a = base.lire_un("SELECT contenu FROM analyses_ia WHERE activite_id=? ORDER BY date_generation DESC, id DESC LIMIT 1",
                     (activite_id,))
    s["analyse"] = a[0] if a else None
    return s


class PanneauDetail(QFrame):
    fiche_complete = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("panneauDetail")
        self.setFixedWidth(340)
        self.setVisible(False)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 18, 20, 18)
        h = QHBoxLayout()
        self.titre = QLabel("")
        self.titre.setWordWrap(True)
        self.titre.setStyleSheet(f"font-size: 18px; font-weight: 700; color: {PALETTE['texte']}; background: transparent;")
        fermer = QPushButton("✕")
        fermer.setFixedSize(36, 36)
        fermer.setToolTip("Fermer (Échap)")
        fermer.setAccessibleName("Fermer le panneau")
        fermer.clicked.connect(self.fermer)
        h.addWidget(self.titre, 1)
        h.addWidget(fermer, 0, Qt.AlignmentFlag.AlignTop)
        lay.addLayout(h)
        self.sous = QLabel("")
        self.sous.setWordWrap(True)
        self.sous.setStyleSheet(f"color: {PALETTE['texte_secondaire']}; background: transparent;")
        lay.addWidget(self.sous)
        zone = QScrollArea()
        zone.setWidgetResizable(True)
        zone.setFrameShape(QFrame.Shape.NoFrame)
        corps = QWidget()
        corps.setStyleSheet("background: transparent;")
        self.corps = QVBoxLayout(corps)
        self.corps.setSpacing(10)
        zone.setWidget(corps)
        zone.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        zone.viewport().setStyleSheet("background: transparent;")
        lay.addWidget(zone, 1)
        self.b_fiche = QPushButton("Ouvrir la fiche complète")
        self.b_fiche.setObjectName("boutonPrincipal")
        self.b_fiche.clicked.connect(lambda: self.fiche_complete.emit(self._id) if self._id else None)
        lay.addWidget(self.b_fiche)
        self._id = None
        QShortcut(QKeySequence(Qt.Key.Key_Escape), self, activated=self.fermer)
        acc = obtenir_couleur_accent()
        self.setStyleSheet(f"#panneauDetail {{ background: {PALETTE['carte']}; border-left: 1px solid {PALETTE['bordure']}; }}"
                           f"#panneauDetail QPushButton {{ min-height: 36px; border-radius: 9px; padding: 0 12px; "
                           f"background: {PALETTE['carte_haute']}; color: {PALETTE['texte']}; border: 1px solid {PALETTE['bordure']}; }}"
                           f"#panneauDetail QPushButton#boutonPrincipal {{ background: {acc}; color: #FFFFFF; border: none; "
                           f"font-weight: 600; min-height: 42px; }}")

    def _ligne(self, lib, val):
        w = QLabel(f"<span style='color:{PALETTE['texte_secondaire']}'>{lib}</span><br><b>{val}</b>")
        w.setTextFormat(Qt.TextFormat.RichText)
        w.setStyleSheet(f"color: {PALETTE['texte']}; background: transparent; font-size: 14px;")
        self.corps.addWidget(w)

    def montrer_sortie(self, activite_id):
        s = resume_sortie(activite_id)
        if not s:
            return False
        self._id = activite_id
        while self.corps.count():
            it = self.corps.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        self.titre.setText(s["nom"] or s["type"] or "Sortie")
        self.sous.setText(f"{str(s['date'])[:16].replace('T', ' ')} · {s['type'] or ''} · {s['source'] or 'saisie'}")
        mn = (s["duree"] or 0) // 60
        self._ligne("Distance et dénivelé", f"{(s['distance'] or 0):.1f} km · {s['denivele'] or 0} m D+".replace(".", ","))
        self._ligne("Durée", f"{mn // 60} h {mn % 60:02d}")
        if s["fc"]:
            self._ligne("Fréquence cardiaque moyenne", f"{s['fc']} bpm")
        if s["ressenti"]:
            self._ligne("Ressenti", str(s["ressenti"]))
        if s["analyse"]:
            t = QLabel(s["analyse"])
            t.setWordWrap(True)
            t.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            t.setStyleSheet(f"color: {PALETTE['texte']}; background: {PALETTE['carte_haute']}; border-radius: 10px; "
                            f"padding: 12px; border-left: 0; font-size: 13px;")
            titre = QLabel("Analyse")
            titre.setStyleSheet(f"color: {obtenir_couleur_accent()}; font-weight: 700; background: transparent;")
            self.corps.addWidget(titre)
            self.corps.addWidget(t)
        if s["notes"]:
            n = QLabel(s["notes"])
            n.setWordWrap(True)
            n.setStyleSheet(f"color: {PALETTE['texte_secondaire']}; background: transparent; font-size: 12px;")
            self.corps.addWidget(n)
        self.corps.addStretch(1)
        self.setVisible(True)
        return True

    def fermer(self):
        self.setVisible(False)
        self._id = None


class BarreEtat(QFrame):
    """Bas de la fenêtre : pont avec Claude, demandes en attente, version."""

    def __init__(self, version, parent=None):
        super().__init__(parent)
        self.setObjectName("barreEtat")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(16, 4, 16, 4)
        lay.setSpacing(18)
        self.pont = QLabel("")
        self.demandes = QLabel("")
        self.version = QLabel(version)
        for w in (self.pont, self.demandes):
            lay.addWidget(w)
        lay.addStretch(1)
        lay.addWidget(self.version)
        self.setStyleSheet("#barreEtat { background: #18211D; } #barreEtat QLabel { color: #AFC0B6; font-size: 12px; "
                           "background: transparent; }")
        self.actualiser()

    def actualiser(self, texte_pont=None):
        try:
            from noyau.connecteurs import pont as P
            from noyau.donnees import connecteurs as D
            d = P.dernier_passage()
            if not P.dossier():
                self.pont.setText("Pont avec Claude : dossier non choisi")
            else:
                self.pont.setText(f"Pont avec Claude : dernier passage {str(d)[11:16] if d else '—'}")
            n = len(D.demandes_en_attente())
            self.demandes.setText(f"{n} demande{'s' if n > 1 else ''} en attente" if n else "Aucune demande en attente")
        except Exception:
            self.pont.setText("")
            self.demandes.setText("")
        if texte_pont:
            self.pont.setToolTip(texte_pont)


def ouvrir_dans_panneau(widget, activite_id):
    """True si la sortie a été ouverte dans le panneau de détail de la fenêtre principale."""
    fen = widget.window() if widget is not None else None
    panneau = getattr(fen, "panneau_detail", None)
    return bool(panneau is not None and panneau.montrer_sortie(activite_id))
