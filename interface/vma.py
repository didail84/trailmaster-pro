"""
Estimation de la VMA (vitesse maximale aérobie) à partir des sorties
enregistrées, et suivi de l'évolution par circuit.

Méthode — pour chaque sortie Trail/Course d'au moins 3 km :
  1. Le dénivelé est converti en distance équivalente à plat :
     distance équivalente = km + D+ / 125  (125 m de D+ ≈ 1 km d'effort).
  2. On en déduit le VO2max de l'effort (formule de Daniels & Gilbert,
     la même que le reste du logiciel : interface/vo2max.py).
  3. La VMA est la vitesse à laquelle le coût en oxygène atteint ce
     VO2max (on résout la formule de Daniels pour la vitesse).

Une sortie tranquille donne une VMA trop basse (la formule suppose un
effort proche du maximum). La VMA du moment est donc la moyenne des
3 meilleures estimations des 90 derniers jours, pas la moyenne de toutes
les sorties. Les séances de fractionné/côtes prévues au planning ne sont
pas utilisées à part : si elles sont faites, elles apparaissent comme
sorties et tirent naturellement l'estimation vers le haut.

Le suivi par circuit regroupe les sorties qui portent le même nom
(« Saumane-de-Vaucluse Trail »...) et compare chrono, allure, vitesse,
distance et D+ dans le temps. Les noms génériques de l'application de
montre (« Morning Trail Run », « Course à pied le midi »...) ne sont pas
des circuits et sont ignorés.
"""

import math
import re
from datetime import date, timedelta
from statistics import mean, median

from data.database import connexion
from interface.vo2max import estimer_vo2max

FENETRE_JOURS = 90
NB_MEILLEURS = 3
DISTANCE_MIN_KM = 3.0
TYPES_COURSE = ("Trail", "Course")

_NOMS_GENERIQUES = re.compile(
    r"^(course à pied (le |dans |en )|morning |afternoon |lunch |evening |night )",
    re.IGNORECASE,
)


def vitesse_vma_depuis_vo2max(vo2max):
    """Vitesse (km/h) à laquelle le coût en oxygène de Daniels égale
    le VO2max donné."""
    a, b, c = 0.000104, 0.182258, -4.60 - vo2max
    delta = b * b - 4 * a * c
    if delta <= 0:
        return None
    v_m_min = (-b + math.sqrt(delta)) / (2 * a)
    return round(v_m_min * 0.06, 2)


def vma_depuis_effort(distance_km, denivele_m, duree_s):
    """VMA estimée (km/h) pour une sortie, ou None si inexploitable."""
    if not distance_km or distance_km < DISTANCE_MIN_KM or not duree_s or duree_s <= 0:
        return None
    denivele = min(denivele_m or 0, 60 * distance_km)  # coupe les D+ aberrants
    distance_eq = distance_km + denivele / 125
    allure_eq = duree_s / 60 / distance_eq
    if not 3.5 <= allure_eq <= 9:  # sous 3:30 /km : GPS ou durée erronés
        return None
    vo2 = estimer_vo2max(distance_eq, duree_s)
    if not vo2:
        return None
    return vitesse_vma_depuis_vo2max(vo2)


def allure_texte(vitesse_kmh):
    """Vitesse km/h -> « 4:52 /km »."""
    if not vitesse_kmh or vitesse_kmh <= 0:
        return "—"
    sec = int(round(3600 / vitesse_kmh))
    return f"{sec // 60}:{sec % 60:02d} /km"


def duree_texte(duree_s):
    if duree_s is None:
        return "—"
    duree_s = int(round(duree_s))
    h, reste = divmod(duree_s, 3600)
    m, s = divmod(reste, 60)
    return f"{h}h{m:02d}'{s:02d}" if h else f"{m}'{s:02d}"


def _efforts_course(athlete_id):
    conn = connexion()
    cur = conn.cursor()
    cur.execute(
        "SELECT date, nom, type, distance, denivele, duree FROM activites "
        "WHERE athlete_id=? AND type IN ('Trail','Course') AND distance >= ? AND duree > 0 "
        "ORDER BY date",
        (athlete_id, DISTANCE_MIN_KM),
    )
    lignes = cur.fetchall()
    conn.close()
    efforts = []
    for d, nom, t, dist, dp, duree in lignes:
        vma = vma_depuis_effort(dist, dp, duree)
        if vma:
            efforts.append({"date": str(d)[:10], "nom": nom or "", "type": t,
                            "km": dist, "dp": dp or 0, "duree": duree, "vma": vma})
    return efforts


def _vma_fenetre(efforts, fin_iso, jours=FENETRE_JOURS):
    debut = (date.fromisoformat(fin_iso) - timedelta(days=jours)).isoformat()
    valeurs = sorted(
        (e["vma"] for e in efforts if debut <= e["date"] <= fin_iso), reverse=True
    )
    if not valeurs:
        return None
    return round(mean(valeurs[:NB_MEILLEURS]), 1)


def calculer_vma(athlete_id):
    """Retourne un dict :
    - actuelle : VMA estimée à la date de la dernière sortie (km/h)
    - date_reference : cette date (ISO)
    - meilleurs : les NB_MEILLEURS meilleurs efforts de la fenêtre
    - record : meilleure VMA (moyenne des 3 meilleures) sur une fenêtre
      de 90 jours, toutes périodes confondues, avec sa date
    - serie : [(label_mois, vma_ou_None)] sur 24 mois
    - nb_efforts : nombre de sorties exploitables
    ou None s'il n'y a aucune sortie exploitable."""

    efforts = _efforts_course(athlete_id)
    if not efforts:
        return None

    derniere = efforts[-1]["date"]
    ref = derniere
    actuelle = _vma_fenetre(efforts, ref)

    debut = (date.fromisoformat(ref) - timedelta(days=FENETRE_JOURS)).isoformat()
    meilleurs = sorted(
        (e for e in efforts if debut <= e["date"] <= ref), key=lambda e: -e["vma"]
    )[:NB_MEILLEURS]

    # Record : on teste chaque fin de mois.
    record = None
    jour = date.fromisoformat(efforts[0]["date"]).replace(day=1)
    fin = date.fromisoformat(ref)
    while jour <= fin:
        suivant = (jour.replace(day=28) + timedelta(days=4)).replace(day=1)
        fin_mois = min(suivant - timedelta(days=1), fin).isoformat()
        v = _vma_fenetre(efforts, fin_mois)
        if v is not None and (record is None or v > record[0]):
            record = (v, fin_mois)
        jour = suivant

    # Série mensuelle sur 24 mois
    serie = []
    fin_dt = date.fromisoformat(ref)
    for i in range(23, -1, -1):
        annee = fin_dt.year
        mois = fin_dt.month - i
        while mois < 1:
            mois += 12
            annee -= 1
        premier = date(annee, mois, 1)
        dernier = (premier.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
        fin_mois = min(dernier, fin_dt).isoformat()
        serie.append((f"{mois:02d}/{str(annee)[2:]}", _vma_fenetre(efforts, fin_mois)))
    while serie and serie[0][1] is None:
        serie.pop(0)
    derniere_valeur = None
    remplie = []
    for label, v in serie:
        if v is None:
            v = derniere_valeur
        else:
            derniere_valeur = v
        remplie.append((label, v))

    return {
        "actuelle": actuelle,
        "date_reference": ref,
        "meilleurs": meilleurs,
        "record": record,
        "serie": remplie,
        "nb_efforts": len(efforts),
    }


def allures_reference(vma_kmh):
    """Allures conseillées à partir de la VMA : [(libellé, % VMA, allure)]."""
    return [
        (nom, pct, allure_texte(vma_kmh * pct / 100))
        for nom, pct in (
            ("Endurance fondamentale", 65),
            ("Allure marathon", 75),
            ("Seuil", 85),
            ("Allure 10 km", 90),
            ("VMA", 100),
        )
    ]


def _regression_pente(points):
    """Pente (unité/an) d'une régression linéaire sur [(jours, valeur)]."""
    n = len(points)
    if n < 3:
        return None
    mx = sum(p[0] for p in points) / n
    my = sum(p[1] for p in points) / n
    den = sum((p[0] - mx) ** 2 for p in points)
    if den == 0:
        return None
    return sum((p[0] - mx) * (p[1] - my) for p in points) / den * 365.25


def lister_circuits(athlete_id, nb_min=3):
    """Circuits (sorties de même nom, au moins nb_min fois), triés par
    nombre de passages. Seules les sorties dont la distance est à ±15 %
    de la distance médiane du circuit sont comparées (les parcours
    raccourcis ou prolongés ne faussent pas le chrono)."""

    conn = connexion()
    cur = conn.cursor()
    cur.execute(
        "SELECT date, nom, distance, denivele, duree, frequence_cardiaque_moyenne "
        "FROM activites WHERE athlete_id=? AND type IN ('Trail','Course') "
        "AND distance >= ? AND duree > 0 ORDER BY date",
        (athlete_id, DISTANCE_MIN_KM),
    )
    lignes = cur.fetchall()
    conn.close()

    groupes = {}
    for d, nom, dist, dp, duree, fc in lignes:
        nom = (nom or "").strip()
        if not nom or _NOMS_GENERIQUES.match(nom):
            continue
        groupes.setdefault(nom, []).append(
            {"date": str(d)[:10], "km": dist, "dp": dp or 0, "duree": duree, "fc": fc or 0}
        )

    circuits = []
    for nom, passages in groupes.items():
        med = median(p["km"] for p in passages)
        passages = [p for p in passages if 0.85 * med <= p["km"] <= 1.15 * med]
        if len(passages) < nb_min:
            continue
        for p in passages:
            p["allure_min_km"] = p["duree"] / 60 / p["km"]
            p["vitesse"] = p["km"] / (p["duree"] / 3600)
            p["vma"] = vma_depuis_effort(p["km"], p["dp"], p["duree"])

        chronos = [p["duree"] for p in passages]
        recents = chronos[-3:]
        avant = chronos[-6:-3]
        evol_recente = None
        if len(avant) == 3:
            evol_recente = (mean(recents) - mean(avant)) / mean(avant) * 100
        evol_totale = None
        if len(passages) >= 6:
            evol_totale = (mean(chronos[-3:]) - mean(chronos[:3])) / mean(chronos[:3]) * 100

        base = date.fromisoformat(passages[0]["date"])
        pente = _regression_pente(
            [((date.fromisoformat(p["date"]) - base).days, p["allure_min_km"]) for p in passages]
        )

        circuits.append({
            "nom": nom,
            "passages": passages,
            "nb": len(passages),
            "km": mean(p["km"] for p in passages),
            "dp": mean(p["dp"] for p in passages),
            "chrono_moyen": mean(chronos),
            "chrono_meilleur": min(chronos),
            "chrono_dernier": chronos[-1],
            "allure_moyenne": mean(p["allure_min_km"] for p in passages),
            "vitesse_moyenne": mean(p["vitesse"] for p in passages),
            "evol_recente_pct": evol_recente,   # < 0 : plus rapide
            "evol_totale_pct": evol_totale,
            "pente_allure_an": pente,            # min/km par an, < 0 : plus rapide
            "premiere": passages[0]["date"],
            "derniere": passages[-1]["date"],
        })

    circuits.sort(key=lambda c: (-c["nb"], c["nom"]))
    return circuits


def texte_evolution(pct):
    if pct is None:
        return "—"
    if abs(pct) < 1:
        return "= stable"
    return f"{'▼' if pct < 0 else '▲'} {abs(pct):.1f}".replace(".", ",") + f" % {'plus rapide' if pct < 0 else 'plus lent'}"


# ----------------------------------------------------------------------
#  Écran
# ----------------------------------------------------------------------

import re  # noqa: E402

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtGui import QColor  # noqa: E402
from PySide6.QtWidgets import (  # noqa: E402
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QFrame,
    QScrollArea, QTableWidget, QTableWidgetItem, QPushButton, QMessageBox, QHeaderView,
)

from data.database import obtenir_athletes  # noqa: E402
from interface.ecran_liste import obtenir_style_ecran, configurer_table_redimensionnable  # noqa: E402
from interface.courbe_multiligne import CourbeMultiLignes  # noqa: E402


def _carte_kpi(titre, valeur, note=""):
    cadre = QFrame()
    cadre.setObjectName("carteForm")
    lay = QVBoxLayout(cadre)
    t = QLabel(titre)
    t.setObjectName("texteSecondaire")
    v = QLabel(valeur)
    v.setStyleSheet("font-size: 24px; font-weight: 700;")
    lay.addWidget(t)
    lay.addWidget(v)
    if note:
        n = QLabel(note)
        n.setObjectName("texteSecondaire")
        n.setWordWrap(True)
        lay.addWidget(n)
    return cadre


def _table(colonnes, hauteur_min=0, lignes_max=0):
    """lignes_max > 0 : la table prend la hauteur de ses lignes (jusqu'à ce
    nombre), sans barre de défilement interne tant qu'elles tiennent."""
    tab = QTableWidget()
    tab.setColumnCount(len(colonnes))
    tab.setHorizontalHeaderLabels([c.upper() for c in colonnes])
    configurer_table_redimensionnable(tab)
    tab.verticalHeader().setVisible(False)
    tab.setShowGrid(False)
    tab._lignes_max = lignes_max
    en_tete = tab.horizontalHeader()
    en_tete.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
    en_tete.setStretchLastSection(True)
    tab.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
    tab.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
    if hauteur_min and not lignes_max:
        tab.setMinimumHeight(hauteur_min)
    return tab


_NOMBRE_DECIMAL = re.compile(r"^(\d+)\.(\d+)(\s.*)?$")
_DATE_ISO = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")
VERT_EVOL, AMBRE_EVOL, GRIS_EVOL = "#66BB6A", "#F9A825", "#9AA7AE"


def _texte_fr(val):
    """12.5 km/h -> 12,5 km/h ; 2026-08-25 -> 25/08/2026."""
    texte = str(val)
    m = _DATE_ISO.match(texte)
    if m:
        return f"{m.group(3)}/{m.group(2)}/{m.group(1)}"
    m = _NOMBRE_DECIMAL.match(texte)
    if m:
        return f"{m.group(1)},{m.group(2)}{m.group(3) or ''}"
    return texte


def _remplir(tab, lignes, colonnes_evolution=()):
    tab.setRowCount(len(lignes))
    for i, ligne in enumerate(lignes):
        for j, val in enumerate(ligne):
            item = QTableWidgetItem(_texte_fr(val))
            if j in colonnes_evolution:
                texte = str(val)
                couleur = (VERT_EVOL if "plus rapide" in texte
                           else AMBRE_EVOL if "plus lent" in texte else GRIS_EVOL)
                item.setForeground(QColor(couleur))
            tab.setItem(i, j, item)
    tab.resizeColumnsToContents()
    maximum = getattr(tab, "_lignes_max", 0)
    if maximum:
        visibles = min(max(len(lignes), 1), maximum)
        hauteur = tab.horizontalHeader().height() + visibles * tab.verticalHeader().defaultSectionSize() + 6
        tab.setFixedHeight(hauteur)


class VMACircuits(QMainWindow):

    def __init__(self, athlete_id_initial=None):
        super().__init__()
        self.setWindowTitle("TrailMaster Pro – VMA & circuits")
        self.resize(1300, 900)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.setCentralWidget(scroll)
        central = QWidget()
        scroll.setWidget(central)
        self.principal = QVBoxLayout(central)
        self.principal.setContentsMargins(25, 20, 25, 20)
        self.principal.setSpacing(15)

        titre = QLabel("🏃  VMA & circuits")
        titre.setObjectName("titrePage")
        sous = QLabel(
            "VMA estimée à partir de tes sorties, et évolution de tes chronos, allures, "
            "vitesses, distances et D+ sur chaque circuit"
        )
        sous.setObjectName("sousTitrePage")
        sous.setWordWrap(True)
        self.principal.addWidget(titre)
        self.principal.addWidget(sous)

        barre = QHBoxLayout()
        lab = QLabel("Athlète :")
        lab.setObjectName("labelChamp")
        self.combo_athlete = QComboBox()
        self.combo_athlete.addItem("Sélectionner...", None)
        for a in obtenir_athletes():
            self.combo_athlete.addItem(f"{a[2]} {a[1]}", a[0])
        barre.addWidget(lab)
        barre.addWidget(self.combo_athlete)
        barre.addStretch()
        self.principal.addLayout(barre)

        self.zone_kpi = QHBoxLayout()
        self.zone_kpi.setSpacing(15)
        self.principal.addLayout(self.zone_kpi)

        self.bouton_appliquer = QPushButton("Appliquer cette VMA au profil de l'athlète")
        self.bouton_appliquer.clicked.connect(self.appliquer_au_profil)
        self.principal.addWidget(self.bouton_appliquer, 0, Qt.AlignmentFlag.AlignLeft)

        # Évolution de la VMA
        c1 = QFrame()
        c1.setObjectName("carteForm")
        l1 = QVBoxLayout(c1)
        t1 = QLabel("📈 Évolution de la VMA sur 24 mois")
        t1.setObjectName("titreCarte")
        self.note_methode = QLabel(
            "Chaque point = moyenne des 3 meilleures sorties des 90 jours précédents. "
            "Le D+ est converti en distance à plat (125 m de D+ ≈ 1 km), puis la formule de "
            "Daniels donne le VO2max, puis la vitesse correspondante. Une sortie tranquille "
            "sous-estime la VMA : seuls tes meilleurs efforts comptent."
        )
        self.note_methode.setObjectName("texteSecondaire")
        self.note_methode.setWordWrap(True)
        self.courbe_vma = CourbeMultiLignes()
        l1.addWidget(t1)
        l1.addWidget(self.note_methode)
        l1.addWidget(self.courbe_vma)
        self.principal.addWidget(c1)

        # Allures + meilleurs efforts
        zone = QHBoxLayout()
        zone.setSpacing(15)
        c2 = QFrame()
        c2.setObjectName("carteForm")
        l2 = QVBoxLayout(c2)
        t2 = QLabel("🎯 Allures conseillées")
        t2.setObjectName("titreCarte")
        l2.addWidget(t2)
        self.table_allures = _table(["Effort", "% VMA", "Allure"], 0, 8)
        l2.addWidget(self.table_allures)
        c3 = QFrame()
        c3.setObjectName("carteForm")
        l3 = QVBoxLayout(c3)
        t3 = QLabel("🏅 Efforts retenus (90 derniers jours)")
        t3.setObjectName("titreCarte")
        l3.addWidget(t3)
        self.table_efforts = _table(["Date", "Sortie", "km", "D+", "Chrono", "VMA"], 0, 8)
        l3.addWidget(self.table_efforts)
        zone.addWidget(c2, 1)
        zone.addWidget(c3, 2)
        self.principal.addLayout(zone)

        # Circuits
        c4 = QFrame()
        c4.setObjectName("carteForm")
        l4 = QVBoxLayout(c4)
        t4 = QLabel("🗺️ Évolution par circuit")
        t4.setObjectName("titreCarte")
        n4 = QLabel(
            "Sorties du même nom (au moins 3 passages, distance à ±15 % du circuit). "
            "« Évolution récente » compare tes 3 derniers passages aux 3 précédents ; "
            "« depuis le début » compare les 3 derniers aux 3 premiers. "
            "Clique sur une ligne pour voir le détail."
        )
        n4.setObjectName("texteSecondaire")
        n4.setWordWrap(True)
        self.table_circuits = _table(
            ["Circuit", "Passages", "km", "D+", "Chrono moyen", "Meilleur",
             "Dernier", "Allure", "Vitesse", "Évol. récente",
             "Depuis le début"], 0, 24
        )
        self.table_circuits.itemSelectionChanged.connect(self._circuit_clique)
        l4.addWidget(t4)
        l4.addWidget(n4)
        l4.addWidget(self.table_circuits)
        self.principal.addWidget(c4)

        # Détail d'un circuit
        c5 = QFrame()
        c5.setObjectName("carteForm")
        l5 = QVBoxLayout(c5)
        self.titre_detail = QLabel("Détail du circuit")
        self.titre_detail.setObjectName("titreCarte")
        l5.addWidget(self.titre_detail)
        self.courbe_chrono = CourbeMultiLignes()
        self.courbe_allure = CourbeMultiLignes()
        for c in (self.courbe_vma, self.courbe_chrono, self.courbe_allure):
            c.echelle_ajustee = True
        self.courbe_vma.remplissage = True
        l5.addWidget(QLabel("Chrono (minutes) à chaque passage"))
        l5.addWidget(self.courbe_chrono)
        l5.addWidget(QLabel("Allure (min/km) à chaque passage — plus bas = plus rapide"))
        l5.addWidget(self.courbe_allure)
        self.table_passages = _table(
            ["Date", "km", "D+", "Chrono", "Allure", "Vitesse", "FC moy.", "VMA estimée"], 0, 15
        )
        l5.addWidget(self.table_passages)
        self.principal.addWidget(c5)

        self.setStyleSheet(obtenir_style_ecran())
        self.circuits = []
        self.resultat = None

        if athlete_id_initial is not None:
            for i in range(self.combo_athlete.count()):
                if self.combo_athlete.itemData(i) == athlete_id_initial:
                    self.combo_athlete.setCurrentIndex(i)
                    break
        self.combo_athlete.currentIndexChanged.connect(self.actualiser)
        self.actualiser()

    # ------------------------------------------------------------
    def _athlete(self):
        return self.combo_athlete.currentData()

    def _vider_kpi(self):
        while self.zone_kpi.count():
            w = self.zone_kpi.takeAt(0).widget()
            if w:
                w.deleteLater()

    def actualiser(self):
        self._vider_kpi()
        athlete_id = self._athlete()
        self.circuits = []
        self.resultat = None
        if athlete_id is None:
            self.bouton_appliquer.setEnabled(False)
            self.courbe_vma.definir_series([])
            for t in (self.table_allures, self.table_efforts, self.table_circuits, self.table_passages):
                t.setRowCount(0)
            self.courbe_chrono.definir_series([])
            self.courbe_allure.definir_series([])
            self.zone_kpi.addWidget(_carte_kpi("VMA", "—", "Sélectionne un athlète."))
            return

        res = calculer_vma(athlete_id)
        self.resultat = res
        profil = self._vma_profil(athlete_id)

        if not res or res["actuelle"] is None:
            self.bouton_appliquer.setEnabled(False)
            self.zone_kpi.addWidget(_carte_kpi(
                "VMA estimée", "—",
                "Pas de sortie Trail/Course d'au moins 3 km sur les 90 derniers jours."))
            self.zone_kpi.addWidget(_carte_kpi("VMA du profil", f"{profil:.1f} km/h" if profil else "—"))
            self.courbe_vma.definir_series([])
        else:
            self.bouton_appliquer.setEnabled(True)
            v = res["actuelle"]
            self.zone_kpi.addWidget(_carte_kpi(
                "VMA estimée", f"{v:.1f} km/h",
                f"au {res['date_reference']} · {allure_texte(v)}"))
            self.zone_kpi.addWidget(_carte_kpi(
                "VMA du profil", f"{profil:.1f} km/h" if profil else "—",
                "valeur saisie dans la fiche athlète"))
            if res["record"]:
                self.zone_kpi.addWidget(_carte_kpi(
                    "Meilleure VMA estimée", f"{res['record'][0]:.1f} km/h",
                    f"fenêtre de 90 jours se terminant le {res['record'][1]}"))
            self.zone_kpi.addWidget(_carte_kpi(
                "Sorties exploitées", str(res["nb_efforts"]), "Trail/Course ≥ 3 km"))
            self.courbe_vma.definir_series([{
                "nom": "VMA estimée (km/h)", "couleur": "#42A5F5",
                "valeurs": [(l, v) for l, v in res["serie"]],
            }])
            _remplir(self.table_allures, [
                (n, f"{p} %", a) for n, p, a in allures_reference(v)])
            _remplir(self.table_efforts, [
                (e["date"], e["nom"], f"{e['km']:.1f}", f"{e['dp']:.0f}",
                 duree_texte(e["duree"]), f"{e['vma']:.1f} km/h")
                for e in res["meilleurs"]])

        self.circuits = lister_circuits(athlete_id)
        _remplir(self.table_circuits, [
            (c["nom"], c["nb"], f"{c['km']:.1f}", f"{c['dp']:.0f}",
             duree_texte(c["chrono_moyen"]), duree_texte(c["chrono_meilleur"]),
             duree_texte(c["chrono_dernier"]), allure_texte(c["vitesse_moyenne"]),
             f"{c['vitesse_moyenne']:.1f} km/h",
             texte_evolution(c["evol_recente_pct"]), texte_evolution(c["evol_totale_pct"]))
            for c in self.circuits], colonnes_evolution=(9, 10))
        if self.circuits:
            self.table_circuits.selectRow(0)
        else:
            self._afficher_detail(None)

    def _vma_profil(self, athlete_id):
        conn = connexion()
        cur = conn.cursor()
        cur.execute("SELECT vma FROM athletes WHERE id=?", (athlete_id,))
        r = cur.fetchone()
        conn.close()
        return r[0] if r and r[0] else None

    def _circuit_clique(self):
        lignes = self.table_circuits.selectionModel().selectedRows()
        if lignes and 0 <= lignes[0].row() < len(self.circuits):
            self._afficher_detail(self.circuits[lignes[0].row()])

    def _afficher_detail(self, c):
        if c is None:
            self.titre_detail.setText("Détail du circuit")
            self.courbe_chrono.definir_series([])
            self.courbe_allure.definir_series([])
            self.table_passages.setRowCount(0)
            return
        p = c["passages"]
        pente = c["pente_allure_an"]
        txt = f"Détail : {c['nom']} — {c['nb']} passages, du {c['premiere']} au {c['derniere']}"
        if pente is not None:
            txt += f" · tendance {pente:+.2f} min/km par an"
        self.titre_detail.setText(txt)
        lab = [f"{x['date'][8:10]}/{x['date'][5:7]}/{x['date'][2:4]}" for x in p]
        self.courbe_chrono.definir_series([{
            "nom": "Chrono (min)", "couleur": "#66BB6A",
            "valeurs": [(l, round(x["duree"] / 60, 1)) for l, x in zip(lab, p)]}])
        self.courbe_allure.definir_series([{
            "nom": "Allure (min/km)", "couleur": "#F9A825",
            "valeurs": [(l, round(x["allure_min_km"], 2)) for l, x in zip(lab, p)]}])
        _remplir(self.table_passages, [
            (x["date"], f"{x['km']:.1f}", f"{x['dp']:.0f} m", duree_texte(x["duree"]),
             allure_texte(x["vitesse"]), f"{x['vitesse']:.1f} km/h",
             x["fc"] or "—", f"{x['vma']:.1f} km/h" if x["vma"] else "—")
            for x in reversed(p)])

    def appliquer_au_profil(self):
        athlete_id = self._athlete()
        if athlete_id is None or not self.resultat or self.resultat["actuelle"] is None:
            return
        v = round(self.resultat["actuelle"], 1)
        rep = QMessageBox.question(
            self, "Appliquer la VMA",
            f"Remplacer la VMA du profil par {v} km/h ?\n"
            "(Elle sert au calcul des zones et des plans d'entraînement.)")
        if rep != QMessageBox.StandardButton.Yes:
            return
        conn = connexion()
        cur = conn.cursor()
        cur.execute("UPDATE athletes SET vma=? WHERE id=?", (v, athlete_id))
        conn.commit()
        conn.close()
        self.actualiser()
