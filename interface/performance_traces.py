"""
Écrans « Performance trail » de la v98, tous calculés à partir des traces
GPS de tes sorties (data/analyse_traces.py), en arrière-plan pour ne pas
figer le logiciel :

  - MonteesVAM          (P1) classement des montées, VAM, catégories
  - AllureAjustee       (P2) allure réelle et allure ramenée à plat
  - ResistanceFatigue   (P3) perte d'efficacité au fil des heures
  - EfficaciteCourse    (P5) mètres par battement dans le temps
  - TerrainPente        (P9) vitesse selon la pente
  - MeteoPerformance    (P10) performance selon la température
  - FormeDistance       (P4) préparation pour une course visée
"""

import statistics
from datetime import date

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout, QVBoxLayout, QLabel, QComboBox, QPushButton, QSpinBox, QDoubleSpinBox, QFrame,
    QProgressDialog, QApplication, QMessageBox,
)

import data.analyse_traces as at
import data.metriques as met
from interface.arriere_plan import executer
from interface.courbe_widget import CourbeBarres
from interface.cockpit import Anneau, couleur_score
from interface.forme_evolution import _EcranAthlete
from interface.apercu_widgets import virgule
from interface.outils_ui import notifier
from interface.vma import _table, _remplir, duree_texte

VERT, ORANGE, ROUGE, BLEU, VIOLET = "#66BB6A", "#FFA726", "#EF5350", "#42A5F5", "#AB47BC"
PERIODES = [("3 mois", 92), ("6 mois", 183), ("1 an", 365), ("2 ans", 730)]


def allure_txt(v):
    if v is None:
        return "—"
    m = int(v)
    s = round((v - m) * 60)
    if s == 60:
        m, s = m + 1, 0
    return f"{m}:{s:02d}"


def _jour_fr(iso):
    try:
        return date.fromisoformat(str(iso)[:10]).strftime("%d/%m/%y")
    except ValueError:
        return str(iso)[:10]


class _EcranTraces(_EcranAthlete):
    """_EcranAthlete + sélecteur de période + calcul en arrière-plan."""

    PERIODE_DEFAUT = "1 an"

    def __init__(self, titre, sous_titre, athlete_id_initial=None, avec_periode=True):
        super().__init__(titre, sous_titre, athlete_id_initial)
        self.combo_periode = None
        if avec_periode:
            self.combo_periode = QComboBox()
            for lib, _ in PERIODES:
                self.combo_periode.addItem(lib)
            self.combo_periode.setCurrentText(self.PERIODE_DEFAUT)
            self.combo_periode.currentIndexChanged.connect(self.actualiser)
            self.barre.insertWidget(2, QLabel("Période :"))
            self.barre.insertWidget(3, self.combo_periode)
        self.label_calcul = QLabel("")
        self.label_calcul.setObjectName("texteSecondaire")
        self.barre.addWidget(self.label_calcul)
        self._version_calcul = 0

    @property
    def nb_jours(self):
        return dict(PERIODES)[self.combo_periode.currentText()] if self.combo_periode else 365

    def _lancer(self, fonction, rappel, *args, cle=None):
        """Calcul en arrière-plan ; ignore les réponses périmées (si l'on
        a changé d'athlète/période entre-temps)."""
        self._version_calcul += 1
        version = self._version_calcul
        self.label_calcul.setText("⏳ Calcul en cours…")

        def retour(resultat, erreur):
            if version != self._version_calcul:
                return
            self.label_calcul.setText("")
            if erreur is not None:
                self.label_calcul.setText(f"Calcul impossible : {erreur}")
                return
            rappel(resultat)

        executer(fonction, retour, *args, proprietaire=self, cle_cache=cle)

    def _fc_cible(self):
        from data.metriques import _athlete
        fc_max = _athlete(self.athlete_id).get("fc_max") or 185
        return int(round(fc_max * 0.75 / 5) * 5)


# ----------------------------------------------------------------------
# P1 — Montées et VAM
# ----------------------------------------------------------------------

class MonteesVAM(_EcranTraces):

    def __init__(self, athlete_id_initial=None):
        super().__init__(
            "🏔️  Montées et VAM",
            "La VAM (vitesse ascensionnelle moyenne) est le dénivelé que tu grimpes en une heure : c'est "
            "LA mesure de ta force en côte, indépendante de la pente. Les catégories suivent le principe "
            "de Strava (longueur × pente) : Cat. 4 pour une petite côte, HC pour un monstre.",
            athlete_id_initial)
        self.combo_min = QComboBox()
        for lib, v in (("≥ 50 m de D+", 50), ("≥ 100 m", 100), ("≥ 200 m", 200)):
            self.combo_min.addItem(lib, v)
        self.combo_min.setCurrentIndex(1)
        self.combo_min.currentIndexChanged.connect(self._afficher)
        self.barre.insertWidget(4, self.combo_min)

        ligne = QHBoxLayout()
        ligne.setSpacing(15)
        self.cartes = {}
        for cle, titre in (("meilleure", "Meilleure VAM"), ("nb", "Montées détectées"), ("plus_grosse", "Plus grosse montée")):
            self.cartes[cle] = self._carte(titre)
            ligne.addWidget(self.cartes[cle], 1)
        self.principal.addLayout(ligne)
        self.cadre = self._cadre_courbe("VAM de ta meilleure montée, mois par mois",
                                        "Plus la courbe monte, plus tu grimpes vite. Un trou = pas de montée assez longue ce mois-là.", 240)
        self.cadre.courbe.echelle_ajustee = True
        self.principal.addWidget(self.cadre)
        t = QLabel("Classement des montées (par VAM)")
        t.setObjectName("titreCarte")
        self.principal.addWidget(t)
        self.table = _table(["Date", "Sortie", "Longueur", "D+", "Pente moy.", "Pente max", "Durée", "VAM", "Catégorie"], 300)
        self.principal.addWidget(self.table)
        self.principal.addStretch()
        self._donnees = []
        self._finaliser()

    def actualiser(self):
        a = self.athlete_id
        self._donnees = []
        self._afficher()
        if a is None:
            return
        self._lancer(at.analyses_sur_periode, self._recu, a, self.nb_jours, ("Trail", "Course", "Randonnée"),
                     cle=("montees", a, self.nb_jours))

    def _recu(self, donnees):
        self._donnees = donnees
        self._afficher()

    def _afficher(self):
        mini = self.combo_min.currentData() or 100
        lignes = []
        for s in self._donnees:
            for m in s["analyse"]["montees"]:
                if m["gain_m"] >= mini:
                    lignes.append((s, m))
        avec_vam = sorted([x for x in lignes if x[1]["vam"]], key=lambda x: -x[1]["vam"])
        for c in self.cartes.values():
            c.valeur.setText("—")
            c.detail.setText("")
        if avec_vam:
            s, m = avec_vam[0]
            self.cartes["meilleure"].valeur.setText(f"{m['vam']} m/h")
            self.cartes["meilleure"].detail.setText(f"{m['gain_m']} m à {virgule(m['pente_pct'], 1)} % · {_jour_fr(s['date'])}")
            grosse = max(lignes, key=lambda x: x[1]["gain_m"])
            self.cartes["plus_grosse"].valeur.setText(f"{grosse[1]['gain_m']} m D+")
            self.cartes["plus_grosse"].detail.setText(f"{grosse[1]['longueur_m'] / 1000:.1f} km · {_jour_fr(grosse[0]['date'])}".replace(".", ","))
        self.cartes["nb"].valeur.setText(str(len(lignes)))
        self.cartes["nb"].detail.setText(f"sur {len(self._donnees)} sortie(s) analysée(s)")

        par_mois = {}
        for s, m in avec_vam:
            cle = s["date"][:7]
            par_mois[cle] = max(par_mois.get(cle, 0), m["vam"])
        mois = sorted(par_mois)
        self.cadre.courbe.definir_series([
            {"nom": "Meilleure VAM du mois (m/h)", "couleur": ORANGE,
             "valeurs": [(f"{k[5:]}/{k[2:4]}", par_mois[k]) for k in mois]}] if len(mois) >= 2 else [])

        lignes_tab = []
        for s, m in avec_vam[:60]:
            lignes_tab.append((_jour_fr(s["date"]), (s["nom"] or "")[:30], f"{m['longueur_m']} m", f"{m['gain_m']} m",
                               f"{m['pente_pct']} %", f"{m['pente_max_pct']} %", duree_texte(m["duree_s"]),
                               f"{m['vam']} m/h", m["categorie"] or "—"))
        _remplir(self.table, lignes_tab)


# ----------------------------------------------------------------------
# P2 — Allure ajustée à la pente
# ----------------------------------------------------------------------

class AllureAjustee(_EcranTraces):

    def __init__(self, athlete_id_initial=None):
        super().__init__(
            "⚙️  Allure ajustée à la pente",
            "En montée tu vas moins vite, en descente plus vite : l'allure ajustée ramène chaque mètre à "
            "« ce que ça aurait donné à plat » (modèle de coût énergétique). Elle permet de comparer une sortie "
            "vallonnée à une sortie plate.",
            athlete_id_initial, avec_periode=False)
        self.combo_sortie = QComboBox()
        self.combo_sortie.setMinimumWidth(380)
        self.barre.insertWidget(2, QLabel("Sortie :"))
        self.barre.insertWidget(3, self.combo_sortie)
        ligne = QHBoxLayout()
        ligne.setSpacing(15)
        self.cartes = {}
        for cle, titre in (("reelle", "Allure réelle"), ("ajustee", "Allure ajustée (à plat)"), ("gain", "Effet du relief")):
            self.cartes[cle] = self._carte(titre)
            ligne.addWidget(self.cartes[cle], 1)
        self.principal.addLayout(ligne)
        self.cadre = self._cadre_courbe("Allure le long de la sortie (min/km)",
                                        "Plus bas = plus rapide. L'écart entre les deux courbes, c'est le relief.", 260)
        self.cadre.courbe.echelle_ajustee = True
        self.principal.addWidget(self.cadre)
        t = QLabel("Kilomètre par kilomètre")
        t.setObjectName("titreCarte")
        self.principal.addWidget(t)
        self.table = _table(["Km", "Allure", "Allure ajustée", "D+", "FC moy."], 260)
        self.principal.addWidget(self.table)
        self.principal.addStretch()
        self._ids = []
        self._finaliser()
        self.combo_sortie.currentIndexChanged.connect(self._charger_sortie)

    def actualiser(self):
        a = self.athlete_id
        self.combo_sortie.blockSignals(True)
        self.combo_sortie.clear()
        if a is not None:
            for s in met.activites_periode(a, date.fromordinal(date.today().toordinal() - 400), types=("Trail", "Course", "Randonnée", "VTT", "Vélo", "Route"))[::-1]:
                if s["distance"] >= 3 and s["duree"] > 900:
                    self.combo_sortie.addItem(f"{_jour_fr(s['date'])} · {(s['nom'] or s['type'])[:34]} · {s['distance']:.1f} km".replace(".", ","), s["id"])
                if self.combo_sortie.count() >= 80:
                    break
        self.combo_sortie.blockSignals(False)
        self._charger_sortie()

    def _charger_sortie(self):
        for c in self.cartes.values():
            c.valeur.setText("—")
            c.detail.setText("")
        self.cadre.courbe.definir_series([])
        _remplir(self.table, [])
        sid = self.combo_sortie.currentData()
        if sid is None:
            return

        def calcul(i):
            pts = met.trace_de_activite(i)
            return {"gap": at.allure_ajustee(pts), "courbe": at.courbes_allure(pts)} if pts else None

        self._lancer(calcul, self._recu, sid, cle=("gap", sid))

    def _recu(self, r):
        if not r or not r["gap"]:
            self.cartes["reelle"].detail.setText("Cette sortie n'a pas de trace avec l'heure de chaque point.")
            return
        g = r["gap"]
        self.cartes["reelle"].valeur.setText(f"{allure_txt(g['allure'])} /km")
        self.cartes["ajustee"].valeur.setText(f"{allure_txt(g['allure_ajustee'])} /km")
        if g["gain_pct"] is not None:
            self.cartes["gain"].valeur.setText(f"{'+' if g['gain_pct'] > 0 else '−'}{virgule(abs(g['gain_pct']), 1)} %")
            self.cartes["gain"].detail.setText("le relief t'a coûté plus d'effort que le plat" if g["gain_pct"] > 1
                                               else "relief sans effet notable")
        c = r["courbe"]
        if c:
            self.cadre.courbe.definir_series([
                {"nom": "Allure réelle", "couleur": BLEU, "valeurs": [(f"{k:.1f} km".replace(".", ","), a) for k, a, _g, _h in c],
                 "format": lambda v: allure_txt(v) + " /km"},
                {"nom": "Allure ajustée", "couleur": ORANGE, "valeurs": [(f"{k:.1f} km".replace(".", ","), ag) for k, _a, ag, _h in c],
                 "format": lambda v: allure_txt(v) + " /km"},
            ])
        _remplir(self.table, [(s["km"], allure_txt(s["allure"]), allure_txt(s["allure_ajustee"]), f"{s['d_plus']} m",
                               s["fc"] or "—") for s in g["splits"]])


# ----------------------------------------------------------------------
# P3 — Résistance à la fatigue
# ----------------------------------------------------------------------

class ResistanceFatigue(_EcranTraces):
    PERIODE_DEFAUT = "1 an"

    def __init__(self, athlete_id_initial=None):
        super().__init__(
            "🔋  Résistance à la fatigue",
            "Sur les sorties de plus d'1 h 30, on mesure ton efficacité (vitesse ramenée à plat ÷ fréquence "
            "cardiaque) par blocs de 30 minutes, à partir de la 10e minute. Moins tu perds, mieux tu tiens la durée.",
            athlete_id_initial)
        ligne = QHBoxLayout()
        ligne.setSpacing(15)
        self.cartes = {}
        for cle, titre in (("mediane", "Efficacité typique en fin de sortie (vs début)"), ("nb", "Sorties longues analysées"),
                           ("tendance", "Tendance")):
            self.cartes[cle] = self._carte(titre)
            ligne.addWidget(self.cartes[cle], 1)
        self.principal.addLayout(ligne)
        self.cadre = self._cadre_courbe("Efficacité moyenne selon le temps écoulé",
                                        "100 % = ton efficacité au début (10e-40e minute). Chaque point = un bloc de 30 minutes.", 240)
        self.cadre.courbe.echelle_ajustee = True
        self.principal.addWidget(self.cadre)
        self.note = QLabel("")
        self.note.setObjectName("texteSecondaire")
        self.note.setWordWrap(True)
        self.principal.addWidget(self.note)
        self.table = _table(["Date", "Sortie", "Durée", "Blocs", "Efficacité en fin de sortie (vs début)"], 260)
        self.principal.addWidget(self.table)
        self.principal.addStretch()
        self._finaliser()

    def actualiser(self):
        a = self.athlete_id
        for c in self.cartes.values():
            c.valeur.setText("—")
            c.detail.setText("")
        self.cadre.courbe.definir_series([])
        self.note.setText("")
        _remplir(self.table, [])
        if a is None:
            return
        self._lancer(at.analyses_sur_periode, self._recu, a, self.nb_jours, ("Trail", "Course", "Randonnée"),
                     cle=("dura", a, self.nb_jours))

    def _recu(self, donnees):
        longues = [s for s in donnees if s["analyse"]["durabilite"]]
        self.cartes["nb"].valeur.setText(str(len(longues)))
        self.cartes["nb"].detail.setText("sorties ≥ 1 h 30 avec FC et heure")
        if not longues:
            self.note.setText("Aucune sortie de plus d'1 h 30 avec fréquence cardiaque et heure de chaque point sur la période.")
            return
        baisses = [s["analyse"]["durabilite"]["baisse_finale_pct"] for s in longues]
        med = statistics.median(baisses)
        self.cartes["mediane"].valeur.setText(f"{'+' if med > 0 else '−' if med < 0 else ''}{virgule(abs(med), 1)} %")
        lecture = ("Très bonne résistance" if med > -5 else "Perte normale" if med > -12 else "Perte marquée : travaille les sorties longues")
        self.cartes["mediane"].detail.setText(lecture)
        par_bloc = {}
        for s in longues:
            for b in s["analyse"]["durabilite"]["blocs"]:
                par_bloc.setdefault(b["debut_min"], []).append(100 + b["pct"])
        cles = sorted(k for k, v in par_bloc.items() if len(v) >= 2)
        self.cadre.courbe.definir_series([
            {"nom": "Efficacité (%)", "couleur": VERT,
             "valeurs": [(f"{k} min", round(statistics.mean(par_bloc[k]), 1)) for k in cles]}] if len(cles) >= 2 else [])
        if len(longues) >= 4:
            recents = [s["analyse"]["durabilite"]["baisse_finale_pct"] for s in longues[:len(longues) // 2]]
            anciens = [s["analyse"]["durabilite"]["baisse_finale_pct"] for s in longues[len(longues) // 2:]]
            ecart = statistics.mean(recents) - statistics.mean(anciens)
            self.cartes["tendance"].valeur.setText("↗ mieux" if ecart > 2 else "↘ moins bien" if ecart < -2 else "= stable")
            self.cartes["tendance"].detail.setText("sorties récentes vs plus anciennes")
        self.note.setText("Repère : une perte de moins de 5 % sur 2 h est excellente ; au-delà de 12 %, la durée te coûte cher "
                          "(sorties longues, ravitaillement, allure de départ trop rapide).")
        _remplir(self.table, [(_jour_fr(s["date"]), (s["nom"] or "")[:30], duree_texte(s["duree"]),
                               len(s["analyse"]["durabilite"]["blocs"]),
                               f"{virgule(s['analyse']['durabilite']['baisse_finale_pct'], 1)} %") for s in longues[:40]])


# ----------------------------------------------------------------------
# P5 — Efficacité de course
# ----------------------------------------------------------------------

class EfficaciteCourse(_EcranTraces):
    PERIODE_DEFAUT = "1 an"

    def __init__(self, athlete_id_initial=None):
        super().__init__(
            "⚡  Efficacité de course",
            "Combien de mètres (ramenés à plat) tu parcours à chaque battement de cœur : si ce chiffre monte, "
            "tu vas plus vite pour le même effort — c'est le meilleur signe de progrès en endurance. "
            "Le 2e graphique donne ton allure ajustée quand ta FC est à un niveau précis.",
            athlete_id_initial)
        self.spin_fc = QSpinBox()
        self.spin_fc.setRange(100, 190)
        self.spin_fc.setSuffix(" bpm")
        self.spin_fc.setValue(140)
        self.spin_fc.valueChanged.connect(self._refaire)
        self.barre.insertWidget(4, QLabel("FC de référence :"))
        self.barre.insertWidget(5, self.spin_fc)
        ligne = QHBoxLayout()
        ligne.setSpacing(15)
        self.cartes = {}
        for cle, titre in (("recent", "Efficacité récente (3 mois)"), ("evolution", "Évolution vs 3 mois avant"),
                           ("allure", "Allure à la FC de référence")):
            self.cartes[cle] = self._carte(titre)
            ligne.addWidget(self.cartes[cle], 1)
        self.principal.addLayout(ligne)
        self.c_eff = self._cadre_courbe("Mètres par battement, mois par mois", None, 240)
        self.c_eff.courbe.echelle_ajustee = True
        self.c_eff.courbe.remplissage = True
        self.principal.addWidget(self.c_eff)
        self.c_all = self._cadre_courbe("Allure ajustée à la FC de référence (min/km)",
                                        "Plus bas = plus rapide pour le même effort cardiaque.", 240)
        self.c_all.courbe.echelle_ajustee = True
        self.principal.addWidget(self.c_all)
        self.principal.addStretch()
        self._donnees = []
        self._initialise = False
        self._finaliser()

    def _refaire(self):
        if self._initialise:
            self.actualiser()

    def actualiser(self):
        a = self.athlete_id
        if a is None:
            self._donnees = []
            self._afficher()
            return
        if not self._initialise:
            self._initialise = True
            self.spin_fc.blockSignals(True)
            self.spin_fc.setValue(self._fc_cible())
            self.spin_fc.blockSignals(False)
        fc = self.spin_fc.value()
        self._lancer(at.analyses_sur_periode, self._recu, a, max(self.nb_jours, 365), ("Trail", "Course"), fc,
                     cle=("eff", a, max(self.nb_jours, 365), fc))

    def _recu(self, donnees):
        self._donnees = donnees
        self._afficher()

    def _afficher(self):
        for c in self.cartes.values():
            c.valeur.setText("—")
            c.detail.setText("")
        self.c_eff.courbe.definir_series([])
        self.c_all.courbe.definir_series([])
        mois_eff, mois_all = {}, {}
        limite = date.fromordinal(date.today().toordinal() - self.nb_jours).isoformat()
        for s in self._donnees:
            e = s["analyse"]["efficacite"]
            if not e or s["date"][:10] < limite:
                continue
            mois_eff.setdefault(s["date"][:7], []).append(e["m_par_battement"])
            if e["allure_ajustee_fc"]:
                mois_all.setdefault(s["date"][:7], []).append(e["allure_ajustee_fc"])
        cles = sorted(mois_eff)
        if len(cles) >= 2:
            self.c_eff.courbe.definir_series([{"nom": "Mètres / battement", "couleur": VERT,
                                               "valeurs": [(f"{k[5:]}/{k[2:4]}", round(statistics.mean(mois_eff[k]), 3)) for k in cles]}])
        cm = sorted(mois_all)
        if len(cm) >= 2:
            self.c_all.courbe.definir_series([{"nom": "Allure ajustée", "couleur": BLEU,
                                               "valeurs": [(f"{k[5:]}/{k[2:4]}", round(statistics.mean(mois_all[k]), 3)) for k in cm],
                                               "format": lambda v: allure_txt(v) + " /km"}])
        aujourd = date.today().toordinal()
        def vals(debut_j, fin_j):
            return [s["analyse"]["efficacite"]["m_par_battement"] for s in self._donnees if s["analyse"]["efficacite"]
                    and aujourd - fin_j <= date.fromisoformat(s["date"][:10]).toordinal() < aujourd - debut_j]
        r, p = vals(0, 92), vals(92, 184)
        if r:
            self.cartes["recent"].valeur.setText(f"{virgule(statistics.mean(r), 2)} m/bat.")
            self.cartes["recent"].detail.setText(f"{len(r)} sortie(s)")
        if r and p:
            ev = (statistics.mean(r) / statistics.mean(p) - 1) * 100
            self.cartes["evolution"].valeur.setText(f"{'+' if ev > 0 else '−'}{virgule(abs(ev), 1)} %")
            self.cartes["evolution"].detail.setText("tu es plus efficace" if ev > 1 else "moins efficace" if ev < -1 else "stable")
        al = [s["analyse"]["efficacite"]["allure_ajustee_fc"] for s in self._donnees if s["analyse"]["efficacite"]
              and s["analyse"]["efficacite"]["allure_ajustee_fc"]][:6]
        if al:
            self.cartes["allure"].valeur.setText(f"{allure_txt(statistics.mean(al))} /km")
            self.cartes["allure"].detail.setText(f"à {self.spin_fc.value()} bpm (6 dernières sorties)")


# ----------------------------------------------------------------------
# P9 — Vitesse selon la pente
# ----------------------------------------------------------------------

class TerrainPente(_EcranTraces):

    def __init__(self, athlete_id_initial=None):
        super().__init__(
            "⛰️  Vitesse selon le terrain",
            "À quelle allure tu cours (ou marches) selon la pente : plat, faux plats, montées raides, descentes. "
            "Ça montre où tu perds ou gagnes du temps — et sert à préparer une course.",
            athlete_id_initial)
        self.cadre = QFrame()
        self.cadre.setObjectName("carteForm")
        lay = QVBoxLayout(self.cadre)
        t = QLabel("Vitesse moyenne par type de pente (km/h)")
        t.setObjectName("titreCarte")
        self.barres = CourbeBarres()
        self.barres.setMinimumHeight(260)
        lay.addWidget(t)
        lay.addWidget(self.barres)
        self.principal.addWidget(self.cadre)
        self.table = _table(["Terrain", "Part du parcours", "Distance", "Allure", "Vitesse", "FC moy."], 300)
        self.principal.addWidget(self.table)
        self.note = QLabel("")
        self.note.setObjectName("texteSecondaire")
        self.note.setWordWrap(True)
        self.principal.addWidget(self.note)
        self.principal.addStretch()
        self._finaliser()

    def actualiser(self):
        a = self.athlete_id
        self.barres.definir_donnees([])
        _remplir(self.table, [])
        self.note.setText("")
        if a is None:
            return
        self._lancer(at.analyses_sur_periode, self._recu, a, self.nb_jours, ("Trail", "Course", "Randonnée"),
                     cle=("pente", a, self.nb_jours))

    def _recu(self, donnees):
        cumul = at.fusionner_cumuls([s["analyse"]["pente"] for s in donnees])
        res = at.resume_pente(cumul)
        if not res:
            self.note.setText("Pas assez de sorties avec trace chronométrée sur cette période.")
            return
        self.barres.definir_donnees([(r["classe"].split(" (")[0][:14], round(r["vitesse_kmh"], 1)) for r in res],
                                    libelle="Vitesse", unite="km/h")
        _remplir(self.table, [(r["classe"], f"{r['part_distance_pct']} %", f"{r['distance_km']} km", allure_txt(r["allure_min_km"]) + " /km",
                               f"{virgule(r['vitesse_kmh'], 1)} km/h", r["fc"] or "—") for r in res])
        plat = next((r for r in res if r["classe"].startswith("Plat")), None)
        mont = next((r for r in res if r["classe"].startswith("Montée (5")), None)
        if plat and mont:
            self.note.setText(f"Dans les montées de 5 à 12 %, tu vas à {round(mont['vitesse_kmh'] / plat['vitesse_kmh'] * 100)} % "
                              "de ta vitesse à plat.")


# ----------------------------------------------------------------------
# P10 — Météo et performance
# ----------------------------------------------------------------------

class MeteoPerformance(_EcranTraces):

    def __init__(self, athlete_id_initial=None):
        super().__init__(
            "🌦️  Météo et performance",
            "Ton allure (ramenée à plat) et ta FC selon la température du jour. La chaleur coûte cher : ce tableau "
            "te dit combien, pour toi.", athlete_id_initial)
        self.cadre = QFrame()
        self.cadre.setObjectName("carteForm")
        lay = QVBoxLayout(self.cadre)
        t = QLabel("Écart d'allure par tranche de température (par rapport à 10–20 °C)")
        t.setObjectName("titreCarte")
        self.barres = CourbeBarres()
        self.barres.setMinimumHeight(250)
        lay.addWidget(t)
        lay.addWidget(self.barres)
        self.principal.addWidget(self.cadre)
        self.table = _table(["Température", "Sorties", "Allure (à plat)", "Écart", "FC moy."], 260)
        self.principal.addWidget(self.table)
        self.note = QLabel("")
        self.note.setObjectName("texteSecondaire")
        self.note.setWordWrap(True)
        self.principal.addWidget(self.note)
        self.bouton = QPushButton("🌡️ Compléter la météo de mes sorties (internet)")
        self.bouton.setObjectName("boutonPrincipal")
        self.bouton.clicked.connect(self._completer)
        self.principal.addWidget(self.bouton, 0, Qt.AlignmentFlag.AlignLeft)
        self.principal.addStretch()
        self._finaliser()

    def _completer(self):
        if self.athlete_id is None:
            return
        dlg = QProgressDialog("Récupération de la météo…", None, 0, 40, self)
        dlg.setWindowModality(Qt.WindowModality.WindowModal)
        dlg.setMinimumDuration(0)

        def prog(n, total):
            dlg.setMaximum(max(total, 1))
            dlg.setValue(n)
            QApplication.processEvents()

        ok, ko, err = met.completer_meteo(self.athlete_id, nb_jours=min(self.nb_jours, 365), limite=60, progression=prog)
        dlg.close()
        if ok:
            notifier(f"Météo ajoutée pour {ok} sortie(s)", parent=self)
        elif ko:
            QMessageBox.information(self, "Météo", f"Impossible de récupérer la météo ({err}). Vérifie ta connexion.")
        self.actualiser()

    def actualiser(self):
        a = self.athlete_id
        self.barres.definir_donnees([])
        _remplir(self.table, [])
        self.note.setText("")
        if a is None:
            return
        r = met.performance_selon_temperature(a, self.nb_jours)
        tr = r["tranches"]
        if not tr:
            self.note.setText(f"Aucune sortie avec température connue ({r['nb_total']} course(s)/trail(s) sur la période). "
                              "Clique sur le bouton pour récupérer la météo de tes sorties.")
            return
        self.barres.definir_donnees([(x["tranche"].replace(" °C", "°"), x["ecart_pct"] or 0) for x in tr],
                                    libelle="Écart d'allure", unite="%")
        _remplir(self.table, [(x["tranche"], x["n"], allure_txt(x["allure_eq"]) + " /km",
                               "—" if x["ecart_pct"] is None else f"{'+' if x['ecart_pct'] > 0 else '−'}{virgule(abs(x['ecart_pct']), 1)} %",
                               x["fc_moy"] or "—") for x in tr])
        chaud = [x for x in tr if x["tranche"] in ("25–30 °C", "> 30 °C") and x["ecart_pct"]]
        txt = f"{r['nb_sorties_meteo']} sortie(s) sur {r['nb_total']} ont une température."
        if chaud:
            txt += f" Au-dessus de 25 °C tu perds environ {round(statistics.mean(x['ecart_pct'] for x in chaud))} % d'allure."
        self.note.setText(txt + " (Écart positif = plus lent.)")


# ----------------------------------------------------------------------
# P4 — Forme pour la distance visée
# ----------------------------------------------------------------------

class FormeDistance(_EcranAthlete):

    def __init__(self, athlete_id_initial=None):
        super().__init__(
            "🎯  Forme pour ma course",
            "Choisis une course (ou une distance) : on compare ton entraînement des 8 dernières semaines à ce que cette "
            "course demande. C'est une estimation indicative — pas une prédiction de chrono.",
            athlete_id_initial)
        self.combo_course = QComboBox()
        self.combo_course.setMinimumWidth(320)
        self.spin_km = QDoubleSpinBox()
        self.spin_km.setRange(3, 330)
        self.spin_km.setDecimals(1)
        self.spin_km.setSuffix(" km")
        self.spin_km.setValue(30)
        self.spin_d = QSpinBox()
        self.spin_d.setRange(0, 25000)
        self.spin_d.setSingleStep(100)
        self.spin_d.setSuffix(" m D+")
        self.spin_d.setValue(1200)
        for w in (self.spin_km, self.spin_d):
            w.valueChanged.connect(self._calculer)
        self.combo_course.currentIndexChanged.connect(self._course_choisie)
        self.barre.insertWidget(2, QLabel("Course :"))
        self.barre.insertWidget(3, self.combo_course)
        self.barre.insertWidget(4, self.spin_km)
        self.barre.insertWidget(5, self.spin_d)

        corps = QHBoxLayout()
        self.anneau = Anneau(taille=190, epaisseur=18)
        corps.addWidget(self.anneau, 0, Qt.AlignmentFlag.AlignTop)
        droite = QVBoxLayout()
        self.titre = QLabel("")
        self.titre.setObjectName("titreCarte")
        self.titre.setWordWrap(True)
        droite.addWidget(self.titre)
        self.lignes = QVBoxLayout()
        droite.addLayout(self.lignes)
        self.conseil = QLabel("")
        self.conseil.setWordWrap(True)
        self.conseil.setObjectName("texteSecondaire")
        droite.addWidget(self.conseil)
        droite.addStretch()
        corps.addLayout(droite, 1)
        self.principal.addLayout(corps)
        self.principal.addStretch()
        self._courses = []
        self._finaliser()

    def actualiser(self):
        self.combo_course.blockSignals(True)
        self.combo_course.clear()
        self.combo_course.addItem("Distance libre…", None)
        self._courses = met.courses_a_venir(self.athlete_id) if self.athlete_id else []
        for c in self._courses:
            self.combo_course.addItem(f"{_jour_fr(c['date'])} · {c['nom'][:40]} · {c['distance_km']:g} km", c)
        self.combo_course.blockSignals(False)
        self._calculer()

    def _course_choisie(self):
        c = self.combo_course.currentData()
        if c:
            for w, v in ((self.spin_km, c["distance_km"]), (self.spin_d, c["denivele_m"] or 0)):
                w.blockSignals(True)
                w.setValue(v)
                w.blockSignals(False)
        self._calculer()

    def _calculer(self):
        a = self.athlete_id
        while self.lignes.count():
            it = self.lignes.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        if a is None:
            self.anneau.definir(None)
            return
        c = self.combo_course.currentData()
        r = met.forme_pour_distance(a, self.spin_km.value(), self.spin_d.value(), c["date"] if c else None)
        etiquette = {"loin": "Encore loin", "construction": "En construction", "bonne_voie": "Sur la bonne voie", "pret": "Prêt !"}[r["niveau"]]
        self.anneau.definir(r["score"], f"{r['score']} %", etiquette)
        quand = f" · dans {r['semaines_restantes']} semaine(s)" if r["semaines_restantes"] is not None else ""
        self.titre.setText(f"{self.spin_km.value():g} km / {self.spin_d.value()} m D+ — {r['effort_km']:g} km-effort{quand}".replace(".", ","))
        from interface.cockpit import JaugeBarre
        for cr in r["criteres"]:
            l = QLabel(f"{cr['nom']} : {virgule(cr['valeur'], 1 if cr['valeur'] < 10 else 0)} / {virgule(cr['cible'], 0)} {cr['unite']}")
            l.setObjectName("texteSecondaire")
            j = JaugeBarre()
            j.definir(cr["ratio"] * 100, couleur=couleur_score(cr["ratio"] * 100))
            self.lignes.addWidget(l)
            self.lignes.addWidget(j)
        self.conseil.setText(r["conseil"] or "Tous les voyants sont au vert : garde la régularité et soigne la récupération.")
