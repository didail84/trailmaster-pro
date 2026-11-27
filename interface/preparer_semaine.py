"""
Dialogue « Préparer ma semaine » : les séances prévues des 7 prochains
jours, placées dans tes créneaux libres (Google Agenda via les connecteurs
Claude). Tu peux changer une heure, décocher une séance, puis tout envoyer
d'un coup : montre, agenda et playlist.

Calculs : noyau/entrainement/semaine_auto.py.
"""

from datetime import date, datetime

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QCheckBox, QDialog, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QTableWidget,
                               QTableWidgetItem, QVBoxLayout)

from noyau.entrainement import semaine_auto as S
from interface.calendrier_competitions import _bouton, _style_cases
from interface.theme import PALETTE

JOURS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]


class DialoguePreparerSemaine(QDialog):

    def __init__(self, athlete_id, parent=None):
        super().__init__(parent)
        self.athlete_id = athlete_id
        self.setWindowTitle("Préparer ma semaine")
        self.resize(820, 560)
        lay = QVBoxLayout(self)
        t = QLabel("Préparer ma semaine")
        t.setStyleSheet("font-size: 22px; font-weight: 700;")
        lay.addWidget(t)
        intro = QLabel("Les séances prévues des 7 prochains jours, placées dans tes créneaux libres (au plus près de "
                       f"ton heure préférée, {S.heure_preferee()}). Change une heure si besoin, puis envoie tout.")
        intro.setWordWrap(True)
        intro.setStyleSheet(f"color: {PALETTE['texte_secondaire']};")
        lay.addWidget(intro)
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["", "Jour", "Séance", "Heure", "Remarque"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.verticalHeader().setVisible(False)
        lay.addWidget(self.table, 1)
        h = QHBoxLayout()
        self.c_montre, self.c_agenda, self.c_playlist = (QCheckBox("Sur la montre"), QCheckBox("Dans l'agenda"),
                                                         QCheckBox("Avec sa playlist"))
        for c in (self.c_montre, self.c_agenda, self.c_playlist):
            c.setChecked(True)
            h.addWidget(c)
        h.addStretch()
        lay.addLayout(h)
        self.note = QLabel("Running Workout en compte gratuit : 4 séances par mois envoyées sur la montre. "
                           "Les playlists demandent Spotify Premium.")
        self.note.setWordWrap(True)
        self.note.setStyleSheet(f"color: {PALETTE['texte_discret']}; font-size: 12px;")
        lay.addWidget(self.note)
        b = QHBoxLayout()
        b.addStretch()
        annuler = _bouton("Fermer")
        annuler.clicked.connect(self.reject)
        self.envoyer = _bouton("Tout envoyer", True)
        self.envoyer.setObjectName("boutonPrincipal")
        self.envoyer.clicked.connect(self._envoyer)
        b.addWidget(annuler)
        b.addWidget(self.envoyer)
        lay.addLayout(b)
        self._props = S.proposition(athlete_id)
        self._remplir()
        from interface.ecran_liste import obtenir_style_ecran
        self.setStyleSheet(obtenir_style_ecran() + f"QDialog {{ background: {PALETTE['fond']}; }} QLabel {{ background: transparent; color: {PALETTE['texte']}; }}")
        _style_cases(self)

    def _remplir(self):
        self.table.setRowCount(len(self._props))
        for i, p in enumerate(self._props):
            case = QTableWidgetItem()
            case.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable)
            case.setCheckState(Qt.CheckState.Checked)
            self.table.setItem(i, 0, case)
            j = date.fromisoformat(p["jour"])
            for col, texte in ((1, f"{JOURS[j.weekday()]} {j.day}/{j.month}"),
                               (2, f"{p['seance']['nom']} ({p['duree_min']} min)"), (4, p["remarque"])):
                it = QTableWidgetItem(texte)
                it.setFlags(Qt.ItemFlag.ItemIsEnabled)
                self.table.setItem(i, col, it)
            champ = QLineEdit(p["heure"])
            champ.setMaxLength(5)
            self.table.setCellWidget(i, 3, champ)
        self.table.verticalHeader().setDefaultSectionSize(44)
        for col, w in ((0, 40), (1, 130), (2, 280), (3, 100)):
            self.table.setColumnWidth(col, w)
        if not self._props:
            self.envoyer.setEnabled(False)
            self.note.setText("Aucune séance prévue ces 7 prochains jours : crée-les dans Planification ou "
                              "Fractionné, puis reviens ici.")

    def _envoyer(self):
        choisies = []
        for i, p in enumerate(self._props):
            if self.table.item(i, 0).checkState() != Qt.CheckState.Checked:
                continue
            h = self.table.cellWidget(i, 3).text().strip()
            try:
                datetime.strptime(h, "%H:%M")
            except ValueError:
                QMessageBox.warning(self, "Heure", f"Heure illisible pour « {p['seance']['nom']} » : écris par exemple 18:30.")
                return
            q = dict(p)
            q["heure"] = h
            q["fin"] = S._hhmm(S._minutes(h) + p["duree_min"])
            choisies.append(q)
        if not choisies:
            return
        r = S.appliquer(self.athlete_id, choisies, self.c_montre.isChecked(), self.c_agenda.isChecked(),
                        self.c_playlist.isChecked())
        from noyau.connecteurs import pont as P
        envoye = P.ecrire_demandes() if P.dossier() else None
        texte = f"{r['demandes']} demande(s) préparée(s) pour Claude."
        texte += (" Elles partent au prochain passage du pont (chaque matin)." if envoye is not None else
                  " Choisis le dossier partagé (Connecteurs Claude > Pont) pour qu'elles partent.")
        if r["erreurs"]:
            texte += "\n\nÀ revoir :\n" + "\n".join(r["erreurs"])
        QMessageBox.information(self, "Semaine préparée", texte)
        self.accept()
