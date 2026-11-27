"""
Fenêtre « ⚔️ Duel sur un parcours » : deux passages sur la même boucle,
comparés portion par portion (temps, montée, descente, FC), avec le
résumé de ce qui a été gagné ou perdu, et où.

Calculs : noyau/analyse/duel.py.
"""

from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QSpinBox

from noyau.analyse import duel as Du
from interface.conteneur_onglets import ConteneurOnglets
from interface.forme_evolution import _EcranAthlete
from interface.calendrier_competitions import _bouton, _cadre, _table, _style_cases
from interface.organisation_logistique import _remplir

VERT, ROUGE = "#2E7D32", "#C62828"


def _t(s):
    if s is None:
        return "—"
    s = int(round(s))
    h, m, r = s // 3600, (s % 3600) // 60, s % 60
    return f"{h} h {m:02d} min" if h else f"{m} min {r:02d} s"


def _e(s):
    if s is None:
        return "—"
    signe = "−" if s < 0 else "+"
    s = int(round(abs(s)))
    return f"{signe}{s // 60}:{s % 60:02d}" if s >= 60 else f"{signe}{s} s"


class DuelEcran(_EcranAthlete):

    def __init__(self, athlete_id_initial=None):
        super().__init__("⚔️  Duel sur un parcours",
                         "Choisis une sortie qui a une trace GPS : le logiciel retrouve les autres passages sur la même "
                         "boucle (même départ, même arrivée, distance proche) et les compare à distance égale.",
                         athlete_id_initial)
        cadre, lc = _cadre("Les deux passages")
        h = QHBoxLayout()
        self.combo_a = QComboBox()
        self.combo_b = QComboBox()
        self.portions = QSpinBox()
        self.portions.setRange(4, 30)
        self.portions.setValue(10)
        self.portions.setSuffix(" portions")
        for lib, w in (("Passage 1", self.combo_a), ("Passage 2", self.combo_b)):
            h.addWidget(QLabel(lib))
            h.addWidget(w, 1)
        h.addWidget(self.portions)
        b = _bouton("Comparer", True)
        b.clicked.connect(self._comparer)
        h.addWidget(b)
        lc.addLayout(h)
        self.resume = QLabel("")
        self.resume.setWordWrap(True)
        self.resume.setStyleSheet("font-size: 15px;")
        lc.addWidget(self.resume)
        self.principal.addWidget(cadre)

        h = QHBoxLayout()
        self.c_a = self._carte("Passage 1")
        self.c_b = self._carte("Passage 2")
        self.c_ecart = self._carte("Écart")
        for c in (self.c_a, self.c_b, self.c_ecart):
            h.addWidget(c, 1)
        self.principal.addLayout(h)

        cadre, lc = _cadre("Portion par portion")
        self.table = _table(["Portion", "Terrain", "Temps 1", "Temps 2", "Écart", "Montée", "Descente", "FC 1", "FC 2"], 380)
        lc.addWidget(self.table)
        self.principal.addWidget(cadre, 1)
        self.combo_a.currentIndexChanged.connect(self._jumeaux)
        self._traces = {}
        self._finaliser()
        _style_cases(self)

    def actualiser(self, *_):
        a = self.athlete_id
        self._traces = Du.traces_disponibles(a) if a is not None else {}
        self.combo_a.blockSignals(True)
        self.combo_a.clear()
        for aid, nom, d, n in Du.paires(a, self._traces) if a is not None else []:
            self.combo_a.addItem(f"{str(d)[:10]} · {nom}  ({n} autre{'s' if n > 1 else ''} passage{'s' if n > 1 else ''})", aid)
        self.combo_a.blockSignals(False)
        if not self.combo_a.count():
            self.resume.setText("Aucune boucle courue au moins deux fois avec une trace GPS. Importe tes traces "
                                "(Cartes et traces, ou synchro Garmin/Strava) pour lancer un duel.")
        self._jumeaux()

    def _jumeaux(self, *_):
        self.combo_b.clear()
        aid = self.combo_a.currentData()
        if aid is None:
            return
        for bid, nom, d in Du.candidats(self.athlete_id, aid, self._traces):
            self.combo_b.addItem(f"{str(d)[:10]} · {nom}", bid)

    def _comparer(self):
        a, b = self.combo_a.currentData(), self.combo_b.currentData()
        if a is None or b is None:
            return
        try:
            r = Du.comparer(self.athlete_id, a, b, self.portions.value(), self._traces)
        except ValueError as e:
            self.resume.setText(str(e))
            return
        self.resume.setText(r["resume"])
        for c, x in ((self.c_a, r["a"]), (self.c_b, r["b"])):
            c.valeur.setText(_t(x["temps_s"]))
            c.detail.setText(f"{str(x['date'])[:10]} · {str(x['km']).replace('.', ',')} km")
        e = r["ecart_total_s"]
        self.c_ecart.valeur.setText(_e(e))
        self.c_ecart.valeur.setStyleSheet(f"font-size: 24px; font-weight: 700; color: {VERT if (e or 0) < 0 else ROUGE};")
        self.c_ecart.detail.setText("Passage 2 plus rapide" if (e or 0) < 0 else "Passage 2 plus lent")
        lignes, coul = [], {}
        for i, p in enumerate(r["portions"]):
            if p["ecart_s"] is not None:
                coul[(i, 4)] = VERT if p["ecart_s"] < 0 else ROUGE
            lignes.append((f"km {str(p['km_debut']).replace('.', ',')} → {str(p['km_fin']).replace('.', ',')}", p["terrain"],
                           _t(p["a"]["temps_s"]), _t(p["b"]["temps_s"]), _e(p["ecart_s"]),
                           f"+{p['a']['montee_m']} m", f"−{p['a']['descente_m']} m",
                           str(p["a"]["fc"] or "—"), str(p["b"]["fc"] or "—")))
        _remplir(self.table, lignes, coul)


class DuelFenetre(ConteneurOnglets):

    def __init__(self, athlete_id_initial=None):
        super().__init__(titre="Duel sur un parcours", onglets=[("⚔️ Duel", DuelEcran)], athlete_id_initial=athlete_id_initial)
        self.ecran = self.ecrans[0]
