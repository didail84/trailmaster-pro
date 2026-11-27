"""
Fenêtre « ⭐ Défis en famille » : un objectif commun (kilomètres ou
sorties) sur une période, la part de chacun, des badges, et un grand
affichage simple (mode enfant) pour le plus jeune.

Calculs : noyau/donnees/defis.py.
"""

from datetime import date, timedelta

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QMessageBox, QProgressBar, QVBoxLayout, QFrame

from noyau.donnees import defis as F
from interface.conteneur_onglets import ConteneurOnglets
from interface.forme_evolution import _EcranAthlete
from interface.calendrier_competitions import _bouton, _cadre, _table, _style_cases
from interface.organisation_logistique import DialogueChamps, _remplir, _ligne_choisie
from interface.theme import obtenir_couleur_accent


class DefisEcran(_EcranAthlete):

    def __init__(self, athlete_id_initial=None):
        super().__init__("⭐  Défis en famille",
                         "Des kilomètres (ou des sorties) à faire ensemble. Les sorties des coureurs du logiciel "
                         "comptent toutes seules ; pour les enfants, note leurs balades à la main.",
                         athlete_id_initial)
        h = QHBoxLayout()
        self.choix = QComboBox()
        self.choix.currentIndexChanged.connect(self._afficher)
        h.addWidget(QLabel("Défi"))
        h.addWidget(self.choix, 1)
        for texte, f, principal in (("Nouveau défi…", self._nouveau, True), ("Ajouter un participant…", self._participant, False),
                                    ("Noter une sortie…", self._noter, False), ("Grand affichage", self._grand, False),
                                    ("Supprimer", self._supprimer, False)):
            b = _bouton(texte, principal)
            b.clicked.connect(f)
            h.addWidget(b)
        self.principal.addLayout(h)

        cadre, lc = _cadre("Où on en est")
        self.titre = QLabel("")
        self.titre.setStyleSheet("font-size: 22px; font-weight: 700;")
        lc.addWidget(self.titre)
        self.barre = QProgressBar()
        self.barre.setRange(0, 100)
        self.barre.setTextVisible(True)
        self.barre.setMinimumHeight(28)
        lc.addWidget(self.barre)
        self.detail = QLabel("")
        self.detail.setWordWrap(True)
        self.detail.setObjectName("texteSecondaire")
        lc.addWidget(self.detail)
        self.badges = QLabel("")
        self.badges.setStyleSheet("font-size: 16px;")
        lc.addWidget(self.badges)
        self.principal.addWidget(cadre)

        cadre, lc = _cadre("La part de chacun")
        self.table = _table(["Participant", "Sorties du logiciel", "Noté à la main", "Total"], 260)
        lc.addWidget(self.table)
        self.principal.addWidget(cadre, 1)
        self._defis, self._etat = [], None
        self._finaliser()
        _style_cases(self)

    def actualiser(self, *_):
        garde = self.choix.currentData()
        self._defis = F.lister()
        self.choix.blockSignals(True)
        self.choix.clear()
        for d in self._defis:
            self.choix.addItem(f"{d['nom']} ({'terminé' if d['termine'] else f'encore {d['jours_restants']} j'})", d["id"])
        if garde is not None and self.choix.findData(garde) >= 0:
            self.choix.setCurrentIndex(self.choix.findData(garde))
        self.choix.blockSignals(False)
        self._afficher()

    def _afficher(self, *_):
        did = self.choix.currentData()
        self._etat = F.etat(did) if did is not None else None
        e = self._etat
        if not e:
            self.titre.setText("Aucun défi pour l'instant")
            self.barre.setValue(0)
            self.detail.setText("Exemple : 100 km en famille en décembre, chacun sa part.")
            self.badges.setText("")
            self.table.setRowCount(0)
            return
        unite = "km" if e["mesure"] == "km" else "sorties"
        self.titre.setText(e["nom"])
        self.barre.setValue(e["pct"])
        self.barre.setFormat(f"{str(e['total']).replace('.', ',')} / {e['objectif']:g} {unite} ({e['pct']} %)")
        self.barre.setStyleSheet(f"QProgressBar::chunk {{ background: {obtenir_couleur_accent()}; border-radius: 6px; }}")
        self.detail.setText(f"Du {e['debut']} au {e['fin']} · " + ("Défi terminé." if e["termine"] else
                            f"Encore {str(e['reste']).replace('.', ',')} {unite} en {e['jours_restants']} jours."))
        self.badges.setText("   ".join(("★ " if b["obtenu"] else "☆ ") + b["nom"] for b in e["badges"]))
        _remplir(self.table, [(p["prenom"], f"{p['auto']:g}".replace(".", ","), f"{p['main']:g}".replace(".", ","),
                               f"{p['total']:g} {unite}".replace(".", ",")) for p in e["participants"]])

    def _nouveau(self):
        d0 = date.today()
        spec = [("texte", "nom", "Nom du défi", {"aide": "100 km en famille"}),
                ("choix", "mesure", "On compte", {"choix": [("km", "Les kilomètres"), ("sorties", "Les sorties")]}),
                ("reel", "objectif", "Objectif", {"decimales": 0, "max": 100000}),
                ("date", "debut", "Début", None), ("date", "fin", "Fin", None),
                ("texte", "participants", "Participants (prénoms séparés par des virgules)", {"aide": "Didier, Léa, Lucas"})]

        def ok(c):
            noms = [x.strip() for x in (c["participants"] or "").split(",") if x.strip()]
            parts = [{"prenom": n, "athlete_id": self.athlete_id if i == 0 and self.athlete_id else None}
                     for i, n in enumerate(noms)]
            return F.creer(c["nom"], c["objectif"], c["debut"], c["fin"], c["mesure"] or "km", participants=parts)
        dlg = DialogueChamps(self, "Nouveau défi en famille", spec,
                             {"nom": "100 km en famille", "mesure": "km", "objectif": 100, "debut": d0.isoformat(),
                              "fin": (d0 + timedelta(days=30)).isoformat()}, enregistrer=ok)
        if dlg.exec():
            self.actualiser()

    def _participant(self):
        if not self._etat:
            return
        spec = [("texte", "prenom", "Prénom", None),
                ("choix", "lien", "Ses sorties", {"choix": [("main", "Notées à la main"),
                                                              ("coureur", "Celles du coureur sélectionné en haut")]})]
        did = self._etat["id"]
        dlg = DialogueChamps(self, "Ajouter un participant", spec, {"lien": "main"},
                             enregistrer=lambda c: F.ajouter_participant(
                                 did, c["prenom"], self.athlete_id if c["lien"] == "coureur" else None))
        if dlg.exec():
            self._afficher()

    def _noter(self):
        if not self._etat or not self._etat["participants"]:
            return
        p = _ligne_choisie(self.table, self._etat["participants"]) or self._etat["participants"][-1]
        spec = [("choix", "pid", "Qui", {"choix": [(x["id"], x["prenom"]) for x in self._etat["participants"]]}),
                ("reel", "valeur", "Kilomètres" if self._etat["mesure"] == "km" else "Sorties", {"decimales": 1, "max": 1000}),
                ("date", "jour", "Le", None), ("texte", "note", "Note", {"aide": "balade au bord de la Sorgue"})]
        dlg = DialogueChamps(self, "Noter une sortie", spec, {"pid": p["id"], "jour": date.today().isoformat()},
                             enregistrer=lambda c: F.noter(c["pid"], c["valeur"], c["jour"], c["note"]))
        if dlg.exec():
            self._afficher()

    def _supprimer(self):
        if self._etat and QMessageBox.question(self, "Supprimer", f"Supprimer le défi « {self._etat['nom']} » ?") \
                == QMessageBox.StandardButton.Yes:
            F.supprimer(self._etat["id"])
            self.actualiser()

    def _grand(self):
        if self._etat:
            GrandAffichage(self._etat, self).exec()


class GrandAffichage(__import__("PySide6.QtWidgets", fromlist=["QDialog"]).QDialog):
    """Mode enfant : grosse montagne qui se remplit, gros chiffres, étoiles."""

    def __init__(self, etat, parent=None):
        super().__init__(parent)
        self.setWindowTitle(etat["nom"])
        self.resize(820, 560)
        lay = QVBoxLayout(self)
        lay.setSpacing(18)
        t = QLabel(etat["nom"])
        t.setAlignment(Qt.AlignmentFlag.AlignCenter)
        t.setStyleSheet("font-size: 34px; font-weight: 800;")
        lay.addWidget(t)
        montagne = QFrame()
        montagne.setMinimumHeight(260)
        pct = etat["pct"]
        montagne.setStyleSheet(
            "QFrame { border-radius: 24px; background: qlineargradient(x1:0, y1:1, x2:0, y2:0, "
            f"stop:0 {obtenir_couleur_accent()}, stop:{max(0.01, pct / 100):.2f} {obtenir_couleur_accent()}, "
            f"stop:{min(0.99, pct / 100 + 0.01):.2f} #DDE3DE, stop:1 #DDE3DE); }}")
        ml = QVBoxLayout(montagne)
        chiffre = QLabel(f"{pct} %")
        chiffre.setAlignment(Qt.AlignmentFlag.AlignCenter)
        chiffre.setStyleSheet("font-size: 96px; font-weight: 900; color: #17201C; background: transparent;")
        ml.addWidget(chiffre)
        lay.addWidget(montagne, 1)
        et = QLabel("  ".join("★" if b["obtenu"] else "☆" for b in etat["badges"]))
        et.setAlignment(Qt.AlignmentFlag.AlignCenter)
        et.setStyleSheet(f"font-size: 64px; color: {obtenir_couleur_accent()};")
        lay.addWidget(et)
        unite = "km" if etat["mesure"] == "km" else "sorties"
        s = QLabel("   ".join(f"{p['prenom']} : {p['total']:g}" for p in etat["participants"]) + f"  ({unite})")
        s.setAlignment(Qt.AlignmentFlag.AlignCenter)
        s.setWordWrap(True)
        s.setStyleSheet("font-size: 24px; font-weight: 600;")
        lay.addWidget(s)


class DefisFamilleFenetre(ConteneurOnglets):

    def __init__(self, athlete_id_initial=None):
        super().__init__(titre="Défis en famille", onglets=[("⭐ Défis", DefisEcran)], athlete_id_initial=athlete_id_initial)
        self.ecran = self.ecrans[0]
