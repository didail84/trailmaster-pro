"""
E10 — Page de suivi à ouvrir sur le téléphone : un seul fichier HTML
autonome (données intégrées, aucun serveur, rien n'est envoyé nulle part),
à transférer par AirDrop, mail, iCloud/Drive ou câble, puis à ouvrir dans
le navigateur du téléphone.
"""

import json
import re
from datetime import date
from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QLabel, QPushButton, QFileDialog

from data.database import connexion
from interface.forme_evolution import _EcranAthlete
from interface.outils_ui import notifier

MODELE = Path(__file__).with_name("modele_suivi_telephone.html")


def generer_page(athlete_id):
    from interface.vo2max import estimer_vo2max
    conn = connexion()
    cur = conn.cursor()
    cur.execute("SELECT date, nom, type, distance, denivele, duree, frequence_cardiaque_moyenne, allure_moyenne, vo2max "
                "FROM activites WHERE athlete_id=? ORDER BY date", (athlete_id,))
    acts = []
    for d, n, t, di, de, du, fc, al, vo in cur.fetchall():
        v = None
        if t in ("Trail", "Course") and (di or 0) >= 3 and (du or 0) > 0 and du / di >= 230:
            v = vo if vo else estimer_vo2max(di, du)
        acts.append([str(d)[:10], t, round(di or 0, 2), round(de or 0), round(du or 0), fc or 0,
                     round(al, 2) if al else 0, v or 0, (n or "")[:40]])
    try:
        cur.execute("SELECT date, poids_kg, etat_jambes, fatigue_jambes, fatigue_generale, notes FROM suivi_corporel "
                    "WHERE athlete_id=? ORDER BY date", (athlete_id,))
        suivi = [list(r) for r in cur.fetchall()]
    except Exception:
        suivi = []
    conn.close()
    donnees = json.dumps({"acts": acts, "suivi": suivi}, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    return MODELE.read_text(encoding="utf-8").replace("__DATA__", donnees)


class PageTelephone(_EcranAthlete):

    def __init__(self, athlete_id_initial=None):
        super().__init__("📱  Page pour le téléphone",
                         "Crée un fichier unique (données incluses) à ouvrir sur ton téléphone : sorties, forme, évolution. "
                         "Rien n'est envoyé sur Internet.", athlete_id_initial)
        mode = QLabel("Comment l'avoir sur le téléphone ?\n"
                      "• iPhone : envoie-toi le fichier par AirDrop ou par mail, ou enregistre-le dans iCloud Drive, puis ouvre-le depuis l'app Fichiers (Safari).\n"
                      "• Android : envoie-le par mail / Drive, ou copie-le par câble, puis ouvre-le avec Chrome.\n"
                      "À refaire quand tu veux actualiser les données.")
        mode.setWordWrap(True)
        mode.setObjectName("texteSecondaire")
        self.principal.addWidget(mode)
        self.etat = QLabel("")
        b = QPushButton("📱 Créer la page de suivi…")
        b.setObjectName("boutonPrincipal")
        b.clicked.connect(self._creer)
        self.principal.addWidget(b)
        self.principal.addWidget(self.etat)
        self.principal.addStretch(1)
        self._finaliser()

    def actualiser(self):
        pass

    def _creer(self):
        a = self.athlete_id
        if a is None:
            self.etat.setText("Choisis d'abord un athlète.")
            return
        defaut = str(Path.home() / f"TrailMaster_suivi_{date.today().isoformat()}.html")
        chemin, _ = QFileDialog.getSaveFileName(self, "Enregistrer la page", defaut, "Page web (*.html)")
        if not chemin:
            return
        Path(chemin).write_text(generer_page(a), encoding="utf-8")
        self.etat.setText(f"Page créée : {chemin}")
        notifier("Page de suivi créée", parent=self)
        QDesktopServices.openUrl(QUrl.fromLocalFile(chemin))
