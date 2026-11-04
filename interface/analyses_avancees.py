"""
v104 — trois écrans d'analyse poussée :
  • Contrôle des données : ce qui fausse les analyses, avec réparation de la FC ;
  • Meilleurs efforts : meilleure vitesse par durée et vitesse critique (estimation basse) ;
  • Conditions & intensité : effet de la chaleur et du sommeil, polarisation.
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QPushButton, QMessageBox, QFrame, QVBoxLayout, QHBoxLayout

from data import qualite_donnees as qd
from data import meilleurs_efforts as me
from data import impact_conditions as ic
from interface import arriere_plan
from interface.courbe_multiligne import CourbeMultiLignes
from interface.forme_evolution import _EcranAthlete
from interface.vma import _carte_kpi, _table, _remplir, allure_texte

COULEUR_GRAVITE = {"critique": "#EF5350", "attention": "#FFA726", "info": "#4C8DFF"}


def _cadre(titre):
    c = QFrame()
    c.setObjectName("carteForm")
    l = QVBoxLayout(c)
    t = QLabel(titre)
    t.setObjectName("titreCarte")
    l.addWidget(t)
    return c, l


def _texte(contenu=""):
    n = QLabel(contenu)
    n.setObjectName("texteSecondaire")
    n.setWordWrap(True)
    n.setTextFormat(Qt.TextFormat.RichText)
    return n


# ======================================================================
class ControleDonnees(_EcranAthlete):

    def __init__(self, athlete_id_initial=None):
        super().__init__("🧪 Contrôle des données",
                         "Ce qui fausse tes analyses : FC manquante, valeurs aberrantes, doublons, trous de santé.",
                         athlete_id_initial)
        self.zone_kpi = QHBoxLayout()
        self.principal.addLayout(self.zone_kpi)
        c, l = _cadre("Problèmes détectés")
        self.texte = _texte()
        l.addWidget(self.texte)
        self.bouton_reparer = QPushButton("🔧 Réparer les FC manquantes depuis les traces")
        self.bouton_reparer.clicked.connect(self.reparer)
        l.addWidget(self.bouton_reparer, 0, Qt.AlignmentFlag.AlignLeft)
        self.principal.addWidget(c)
        self.principal.addStretch()
        self._finaliser()

    def actualiser(self):
        while self.zone_kpi.count():
            w = self.zone_kpi.takeAt(0).widget()
            if w:
                w.deleteLater()
        a = self.combo_athlete.currentData()
        self.bouton_reparer.setVisible(False)
        if a is None:
            self.texte.setText("Sélectionne un athlète.")
            return
        res = qd.controler(a)
        self.resultat = res
        self.zone_kpi.addWidget(_carte_kpi("Qualité des données", f"{res['score']} / 100",
                                           f"{res['nb_sorties']} sorties de course analysées"))
        if not res["problemes"]:
            self.texte.setText("Aucun problème détecté. 👍")
            return
        morceaux = []
        for p in res["problemes"]:
            col = COULEUR_GRAVITE[p["gravite"]]
            morceaux.append(f"<p><b style='color:{col}'>●</b> {p['texte']}</p>")
            if p["details"]:
                morceaux.append("<ul>" + "".join(f"<li>{d}</li>" for d in p["details"]) + "</ul>")
            if p["code"] == "fc_absente" and p.get("recuperables"):
                self.bouton_reparer.setVisible(True)
        self.texte.setText("".join(morceaux))

    def reparer(self):
        a = self.combo_athlete.currentData()
        if a is None:
            return
        n = qd.reparer_fc(a)
        QMessageBox.information(self, "Réparation", f"{n} sortie(s) mise(s) à jour d'après leur trace.")
        self.actualiser()


# ======================================================================
class MeilleursEfforts(_EcranAthlete):
    ANALYSE_IA = ("efforts", "meilleurs efforts")

    def __init__(self, athlete_id_initial=None):
        super().__init__("⚡ Meilleurs efforts & vitesse critique",
                         "Ta meilleure vitesse (à plat équivalent) sur 1 min à 1 h, et ta vitesse critique — estimation basse.",
                         athlete_id_initial)
        self.zone_kpi = QHBoxLayout()
        self.principal.addLayout(self.zone_kpi)
        c, l = _cadre("Courbe durée → vitesse (estimation basse)")
        self.note = _texte("")
        self.courbe = CourbeMultiLignes()
        self.courbe.echelle_ajustee = True
        l.addWidget(self.note)
        l.addWidget(self.courbe)
        self.table = _table(["Durée", "Vitesse plat équivalent", "Allure", "Date", "Sortie"], 0, 9)
        l.addWidget(self.table)
        self.principal.addWidget(c)
        self.principal.addStretch()
        self._finaliser()

    def actualiser(self):
        a = self.combo_athlete.currentData()
        self._afficher([], None)
        if a is None:
            self.note.setText("Sélectionne un athlète.")
            return
        self.note.setText("Calcul en cours sur tes traces des 12 derniers mois…")
        arriere_plan.executer(me.meilleurs_par_duree, self._fin_calcul, a, proprietaire=self)

    def _fin_calcul(self, efforts, erreur):
        if erreur or efforts is None:
            self.note.setText("Calcul impossible : " + str(erreur))
            return
        self._afficher(efforts, me.vitesse_critique(efforts))

    def _dossier_ia(self):
        from data import analyse_ecran as ae
        return ae.dossier_efforts(getattr(self, "_efforts", None), getattr(self, "_cs", None))

    @staticmethod
    def _duree_txt(s):
        return f"{s // 60} min" if s < 3600 else f"{s // 3600} h"

    def _afficher(self, efforts, cs):
        self._efforts, self._cs = efforts, cs
        while self.zone_kpi.count():
            w = self.zone_kpi.takeAt(0).widget()
            if w:
                w.deleteLater()
        if not efforts:
            self.courbe.definir_series([])
            self.table.setRowCount(0)
            if self.combo_athlete.currentData() is not None and "Calcul" not in self.note.text():
                self.note.setText("Pas de trace avec temps exploitable sur les 12 derniers mois.")
            return
        self.note.setText(
            "Estimation basse : tes sorties sont rarement des efforts maximaux, donc ces vitesses sont des "
            "minimums. Seule l'évolution d'une période à l'autre est fiable. Vitesses corrigées de la pente.")
        self.courbe.definir_series([{
            "nom": "Meilleure vitesse (km/h) — estimation basse", "couleur": "#42A5F5",
            "valeurs": [(self._duree_txt(e["duree_s"]), round(e["vitesse_kmh"], 2)) for e in efforts]}])
        _remplir(self.table, [(self._duree_txt(e["duree_s"]), f"{e['vitesse_kmh']:.1f} km/h",
                               allure_texte(e["vitesse_kmh"]), e["date"], e["nom"]) for e in efforts])
        if cs:
            self.zone_kpi.addWidget(_carte_kpi("Vitesse critique — estimation basse", f"{cs['cs_kmh']:.1f} km/h",
                                               f"{allure_texte(cs['cs_kmh'])} · ajustement r² = {cs['r2']}"))
            self.zone_kpi.addWidget(_carte_kpi("Réserve D′ — estimation basse", f"{cs['d_prime_m']} m",
                                               "distance possible au-dessus de la vitesse critique"))
        else:
            self.zone_kpi.addWidget(_carte_kpi("Vitesse critique", "—",
                                               "Pas assez d'efforts de 3 à 30 min cohérents entre eux."))


# ======================================================================
class ConditionsIntensite(_EcranAthlete):
    ANALYSE_IA = ("conditions", "conditions et intensité")

    def __init__(self, athlete_id_initial=None):
        super().__init__("🌡️ Conditions & intensité",
                         "Effet de la chaleur et du sommeil sur ton efficacité, et répartition de ton intensité.",
                         athlete_id_initial)
        c1, l1 = _cadre("🌡️ Efficacité selon la température")
        self.note_t = _texte()
        self.table_t = _table(["Température", "Sorties", "Indice d'efficacité", "Écart vs ta médiane"], 0, 6)
        l1.addWidget(self.note_t)
        l1.addWidget(self.table_t)
        self.principal.addWidget(c1)
        c2, l2 = _cadre("😴 Efficacité selon le sommeil de la nuit")
        self.note_s = _texte()
        self.table_s = _table(["Sommeil", "Sorties", "Indice d'efficacité", "Écart vs ta médiane"], 0, 6)
        l2.addWidget(self.note_s)
        l2.addWidget(self.table_s)
        self.principal.addWidget(c2)
        c3, l3 = _cadre("🎚️ Répartition de l'intensité (6 dernières semaines)")
        self.note_p = _texte()
        self.table_p = _table(["Zone", "Part du temps"], 0, 6)
        l3.addWidget(self.note_p)
        l3.addWidget(self.table_p)
        self.principal.addWidget(c3)
        self.principal.addStretch()
        self._finaliser()

    @staticmethod
    def _lignes(res):
        return [(x["classe"], x["n"],
                 f"{x['indice']:.2f}".replace(".", ",") if x["indice"] is not None else "trop peu",
                 f"{x['ecart_pct']:+.1f} %" if x["ecart_pct"] is not None else "—") for x in res["lignes"]]

    def actualiser(self):
        a = self.combo_athlete.currentData()
        for t in (self.table_t, self.table_s, self.table_p):
            t.setRowCount(0)
        for n in (self.note_t, self.note_s, self.note_p):
            n.setText("Sélectionne un athlète." if a is None else "")
        if a is None:
            return
        t = ic.impact_temperature(a)
        if t:
            _remplir(self.table_t, self._lignes(t))
            self.note_t.setText(f"{t['nb']} sorties de course ≥ 5 km avec FC. Indice = km-effort/h ÷ FC × 100 : "
                                "plus il est haut, plus tu vas vite pour le même coût cardiaque. "
                                "Classes de moins de 3 sorties masquées.")
        else:
            self.note_t.setText("Pas assez de sorties avec FC (6 minimum).")
        s = ic.impact_sommeil(a)
        if s:
            _remplir(self.table_s, self._lignes(s))
            self.note_s.setText(f"{s['nb']} sorties avec une nuit mesurée par la montre ou saisie. "
                                "Une tendance, pas une preuve : d'autres facteurs jouent.")
        else:
            self.note_s.setText("Pas assez de sorties avec FC (6 minimum).")
        p = ic.polarisation(a)
        if p:
            noms = ["Zone 1", "Zone 2", "Zone 3", "Zone 4", "Zone 5"]
            _remplir(self.table_p, [(n, f"{v:.1f} %".replace(".", ",")) for n, v in zip(noms, p["pct"])])
            self.note_p.setText(f"<b>Profil {p['modele']}</b> — facile (Z1–Z2) {p['bas']} %, moyen (Z3) {p['moyen']} %, "
                                f"dur (Z4–Z5) {p['haut']} % sur {p['nb_sorties']} sorties. {p['lecture']}")
        else:
            self.note_p.setText("Pas de temps par zone sur cette période.")
