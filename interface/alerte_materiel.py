"""
Dialogue « Alerte matériel » : chaussures qui approchent de leur fin de
vie, modèles équivalents à comparer et liens de recherche de prix.

Calculs : noyau/materiel/alerte.py.
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QLabel, QScrollArea, QVBoxLayout, QWidget

from noyau.materiel import alerte as A
from interface.calendrier_competitions import _bouton, _style_cases
from interface.theme import PALETTE


class DialogueAlerteMateriel(QDialog):

    def __init__(self, athlete_id, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Chaussures")
        self.resize(640, 520)
        lay = QVBoxLayout(self)
        t = QLabel("Chaussures à surveiller")
        t.setStyleSheet("font-size: 22px; font-weight: 700;")
        lay.addWidget(t)
        zone = QScrollArea()
        zone.setWidgetResizable(True)
        corps = QWidget()
        cl = QVBoxLayout(corps)
        al = A.alertes(athlete_id)
        if not al:
            l = QLabel(f"Aucune paire au-delà de {A.seuil()} km. Le seuil se règle dans Réglages > Notifications.")
            l.setWordWrap(True)
            cl.addWidget(l)
        for a in al:
            titre = QLabel(f"{a['nom']} — {a['km']} km "
                           f"({'à changer' if a['niveau'] == 'changer' else 'bientôt à changer'}, repère {a['seuil']} km)")
            titre.setStyleSheet("font-size: 16px; font-weight: 700;")
            titre.setWordWrap(True)
            cl.addWidget(titre)
            fam = QLabel(f"Famille : {a['famille']}. Modèles proches à comparer (pistes, pas une recommandation d'achat) :")
            fam.setWordWrap(True)
            fam.setStyleSheet(f"color: {PALETTE['texte_secondaire']};")
            cl.addWidget(fam)
            for e in a["equivalents"]:
                liens = " · ".join(f'<a href="{u}">{n}</a>' for n, u in e["liens"])
                l = QLabel(f"<b>{e['modele']}</b> — prix : {liens}")
                l.setTextFormat(Qt.TextFormat.RichText)
                l.setOpenExternalLinks(True)
                cl.addWidget(l)
        cl.addStretch(1)
        zone.setWidget(corps)
        lay.addWidget(zone, 1)
        note = QLabel("Les prix ne sont pas lus automatiquement : chaque lien ouvre une recherche sur un comparateur.")
        note.setWordWrap(True)
        note.setStyleSheet(f"color: {PALETTE['texte_discret']}; font-size: 12px;")
        lay.addWidget(note)
        b = _bouton("Fermer", True)
        b.clicked.connect(self.accept)
        lay.addWidget(b, 0, Qt.AlignmentFlag.AlignRight)
        from interface.ecran_liste import obtenir_style_ecran
        self.setStyleSheet(obtenir_style_ecran() + f"QDialog {{ background: {PALETTE['fond']}; }} QLabel {{ background: transparent; color: {PALETTE['texte']}; }}")
        _style_cases(self)
