"""
Écran « VMA & circuits ». Les calculs (VMA estimée, allures, circuits)
sont dans noyau/entrainement/vma.py ; ils restent importables d'ici
pour les écrans qui les utilisent déjà.
"""

from noyau.entrainement.vma import *  # noqa: F401,F403
from noyau.entrainement.vma import (  # noqa: F401
    _efforts_course, FENETRE_JOURS, NB_MEILLEURS,
    allure_texte, allures_reference, calculer_vma, duree_texte, lister_circuits, texte_evolution,
)
from noyau.donnees import athletes as dath  # accès aux données

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
from noyau.entrainement import estimations_basses  # noqa: E402


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

        # Pas des courbes : jour, semaine ou mois (Trail Hub Center)
        from noyau.outils.periodes import PAS, LIBELLE_PAS, DUREES
        barre_pas = QHBoxLayout()
        lp = QLabel("Courbes :")
        lp.setObjectName("labelChamp")
        self.combo_pas = QComboBox()
        for code in PAS:
            self.combo_pas.addItem(f"par {LIBELLE_PAS[code].lower()}", code)
        self.combo_pas.setCurrentIndex(PAS.index("mois"))
        self.combo_duree = QComboBox()
        self._durees = DUREES
        barre_pas.addWidget(lp)
        barre_pas.addWidget(self.combo_pas)
        barre_pas.addWidget(self.combo_duree)
        barre_pas.addStretch()
        self.principal.addLayout(barre_pas)
        self._remplir_durees()
        self.combo_pas.currentIndexChanged.connect(lambda *_: (self._remplir_durees(), self.actualiser()))
        self.combo_duree.currentIndexChanged.connect(lambda *_: self.actualiser() if self.combo_duree.count() else None)

        # Évolution de la VMA
        c1 = QFrame()
        c1.setObjectName("carteForm")
        l1 = QVBoxLayout(c1)
        t1 = QLabel("📈 Évolution de la VMA sur 24 mois")
        t1.setObjectName("titreCarte")
        self.titre_courbe_vma = t1
        self.note_methode = QLabel(
            "Ligne = VMA du moment : à chaque jour, semaine ou mois, moyenne des 3 meilleures sorties "
            "des 90 jours précédents. Points = meilleure sortie de la période (une sortie seule, "
            "souvent plus basse : elle n'est pas toujours un effort maximal). "
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

        # v102 — courbes d'estimations (VMA, VO2max, efficacité), « estimation basse »
        c1b = QFrame()
        c1b.setObjectName("carteForm")
        l1b = QVBoxLayout(c1b)
        t1b = QLabel("📉 Évolution des estimations — estimation basse")
        t1b.setObjectName("titreCarte")
        note_b = QLabel(estimations_basses.NOTE)
        note_b.setObjectName("texteSecondaire")
        note_b.setWordWrap(True)
        l1b.addWidget(t1b)
        l1b.addWidget(note_b)
        self.titres_estim, self.courbes_estim = [], []
        for _ in range(3):
            lt = QLabel("")
            lt.setObjectName("texteSecondaire")
            cb = CourbeMultiLignes()
            cb.echelle_ajustee = True
            cb.setMinimumHeight(180)
            l1b.addWidget(lt)
            l1b.addWidget(cb)
            self.titres_estim.append(lt)
            self.courbes_estim.append(cb)
        self.principal.addWidget(c1b)

        from interface.analyse_ia_widget import CarteAnalyseIA
        from data import analyse_ecran as _ae
        self.carte_ia = CarteAnalyseIA("vma", "VMA et VO₂max (estimations basses)",
                                       lambda: self.combo_athlete.currentData(),
                                       lambda: _ae.dossier_vma(self.combo_athlete.currentData()))
        self.principal.addWidget(self.carte_ia)

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

    def _remplir_durees(self):
        pas = self.combo_pas.currentData()
        self.combo_duree.blockSignals(True)
        self.combo_duree.clear()
        for libelle, nb in self._durees[pas]:
            self.combo_duree.addItem(libelle, nb)
        self.combo_duree.setCurrentIndex(len(self._durees[pas]) - 1 if pas != "jour" else 1)
        self.combo_duree.blockSignals(False)

    def _pas_et_nb(self):
        return self.combo_pas.currentData() or "mois", self.combo_duree.currentData()

    def _maj_estimations(self, athlete_id):
        pas, nb = self._pas_et_nb()
        series = estimations_basses.serie_estimations(athlete_id, pas=pas, nb=nb) if athlete_id else None
        defs = estimations_basses.definitions_courbes(series) if series else []
        for i, (lt, cb) in enumerate(zip(self.titres_estim, self.courbes_estim)):
            if i < len(defs):
                lt.setText(defs[i][0])
                cb.definir_series(defs[i][1])
            else:
                lt.setText("")
                cb.definir_series([])

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
            self._maj_estimations(None)
            for t in (self.table_allures, self.table_efforts, self.table_circuits, self.table_passages):
                t.setRowCount(0)
            self.courbe_chrono.definir_series([])
            self.courbe_allure.definir_series([])
            self.zone_kpi.addWidget(_carte_kpi("VMA", "—", "Sélectionne un athlète."))
            return

        pas, nb = self._pas_et_nb()
        res = calculer_vma(athlete_id, pas=pas, nb=nb)
        self.resultat = res
        unite = {"jour": "jour par jour", "semaine": "semaine par semaine", "mois": "mois par mois"}[pas]
        self.titre_courbe_vma.setText(f"📈 Évolution de la VMA, {unite} ({self.combo_duree.currentText()})")
        self._maj_estimations(athlete_id)
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
            series_vma = [{
                "nom": "VMA du moment (km/h)", "couleur": "#42A5F5",
                "valeurs": [(l, v) for l, v in res["serie"]],
            }]
            meilleure = res.get("serie_meilleure_sortie") or []
            if len(meilleure) == len(res["serie"]) and any(v is not None for _, v in meilleure):
                series_vma.append({"nom": "Meilleure sortie de la période (km/h)", "couleur": "#FFA726",
                                   "valeurs": meilleure, "points_seuls": True})
            self.courbe_vma.definir_series(series_vma)
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
        r = dath.valeurs(athlete_id, "vma")
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
        dath.definir_vma(athlete_id, v)
        self.actualiser()
