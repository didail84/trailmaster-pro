"""
Écran « Diagnostic de parcours » (Trail Hub Center, étape 3.2), onglet de
Cartes & Traces : la difficulté d'un tracé (km-effort, catégorie ITRA,
pentes, D+ par quart, montées, technicité estimée) et, au choix, sa
comparaison avec un second tracé. Tous les calculs viennent de
noyau/traces/diagnostic_parcours.py ; aucune requête ici.
"""

import html
import json

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (
    QHBoxLayout, QVBoxLayout, QLabel, QPushButton, QComboBox, QFrame, QFileDialog, QMessageBox,
    QTableWidget, QTableWidgetItem, QWidget, QAbstractItemView,
)

from noyau.donnees import parcours as dparc
from noyau.traces import diagnostic_parcours as dg
from interface.forme_evolution import _EcranAthlete
from interface.ecran_liste import configurer_table_redimensionnable

BLEU, ORANGE = "#42A5F5", "#FFA726"
# Couleurs des classes de pente, de la descente raide (bleu foncé) au très raide (rouge)
COULEURS_PENTE = {"descente_raide": "#1565C0", "descente": "#64B5F6", "plat": "#8D99A3",
                  "montee": "#FFCA28", "montee_raide": "#FB8C00", "tres_raide": "#E53935"}


def _fr(v, d=1):
    return f"{v:.{d}f}".replace(".", ",")


class BarreRepartition(QWidget):
    """Barre horizontale empilée : part de la distance dans chaque classe de pente."""

    def __init__(self):
        super().__init__()
        self.repartition = []
        self.setMinimumHeight(26)
        self.setMaximumHeight(26)

    def definir(self, repartition):
        self.repartition = repartition or []
        lignes = [f"{r['libelle']} : {_fr(r['pct'], 0)} % ({_fr(r['km'])} km)" for r in self.repartition if r["pct"]]
        self.setToolTip("\n".join(lignes))
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        x, w = 0.0, self.width()
        for r in self.repartition:
            if r["pct"] <= 0:
                continue
            larg = w * r["pct"] / 100
            p.fillRect(int(x), 0, max(1, int(larg) - 2), self.height(), QColor(COULEURS_PENTE[r["code"]]))
            if larg > 34:
                p.setPen(QColor("#FFFFFF" if r["code"] in ("descente_raide", "tres_raide") else "#111111"))
                p.drawText(int(x), 0, int(larg) - 2, self.height(), Qt.AlignmentFlag.AlignCenter, f"{r['pct']:.0f} %")
            x += larg


class DiagnosticParcours(_EcranAthlete):
    ANALYSE_IA = None

    def __init__(self, athlete_id_initial=None):
        super().__init__(
            "📐  Diagnostic de parcours",
            "La difficulté d'un tracé lue sur sa trace : km-effort et catégorie ITRA, pentes, répartition du D+, "
            "montées, technicité estimée. Choisis un second tracé pour les comparer.",
            athlete_id_initial)
        self._traces = {"A": None, "B": None}
        self._diags = {"A": None, "B": None}
        self._combos = {}
        self._labels = {}
        for cle, titre in (("A", "Parcours"), ("B", "Comparer avec (facultatif)")):
            ligne = QHBoxLayout()
            lab = QLabel(titre + " :")
            lab.setMinimumWidth(190)
            combo = QComboBox()
            combo.currentIndexChanged.connect(lambda _i, c=cle: self._parcours_choisi(c))
            bouton = QPushButton("📂 Charger un GPX…")
            bouton.clicked.connect(lambda _x=False, c=cle: self._charger_gpx(c))
            ligne.addWidget(lab)
            ligne.addWidget(combo, 1)
            ligne.addWidget(bouton)
            self.principal.addLayout(ligne)
            self._combos[cle] = combo

        ligne = QHBoxLayout()
        ligne.setSpacing(15)
        self.cartes = {}
        for cle, titre in (("effort", "Km-effort"), ("itra", "Catégorie ITRA"), ("terrain", "Terrain"),
                           ("temps", "Ton temps estimé"), ("tech", "Technicité estimée")):
            self.cartes[cle] = self._carte(titre)
            ligne.addWidget(self.cartes[cle], 1)
        self.principal.addLayout(ligne)

        self.resume = QLabel("")
        self.resume.setWordWrap(True)
        self.principal.addWidget(self.resume)

        self.cadre_profil = self._cadre_courbe("Profil", "Altitude lissée en fonction de la distance.", 240)
        self.cadre_profil.courbe.remplissage = True
        self.cadre_profil.courbe.echelle_ajustee = True
        self.principal.addWidget(self.cadre_profil)

        cadre = QFrame()
        cadre.setObjectName("carteForm")
        lc = QVBoxLayout(cadre)
        t = QLabel("Répartition de la distance par pente")
        t.setObjectName("titreCarte")
        lc.addWidget(t)
        self.barres, self.noms_barres = {}, {}
        for cle in ("A", "B"):
            n = QLabel("")
            n.setObjectName("texteSecondaire")
            b = BarreRepartition()
            lc.addWidget(n)
            lc.addWidget(b)
            self.barres[cle], self.noms_barres[cle] = b, n
        legende = QLabel("  ".join(f'<span style="color:{COULEURS_PENTE[c]}">■</span> {html.escape(lib)}'
                                   for *_x, lib, c in dg.CLASSES_PENTE))
        legende.setTextFormat(Qt.TextFormat.RichText)
        legende.setWordWrap(True)
        legende.setObjectName("texteSecondaire")
        lc.addWidget(legende)
        self.label_quarts = QLabel("")
        self.label_quarts.setWordWrap(True)
        self.label_quarts.setTextFormat(Qt.TextFormat.RichText)
        lc.addWidget(self.label_quarts)
        self.principal.addWidget(cadre)

        cadre = QFrame()
        cadre.setObjectName("carteForm")
        lm = QVBoxLayout(cadre)
        t = QLabel("Montées et descentes principales")
        t.setObjectName("titreCarte")
        lm.addWidget(t)
        self.table_montees = QTableWidget(0, 6)
        self.table_montees.setHorizontalHeaderLabels(["", "Départ (km)", "Longueur", "Dénivelé", "Pente moyenne", "Pente max"])
        self.table_montees.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table_montees.verticalHeader().setVisible(False)
        self.table_montees.setMinimumHeight(220)
        configurer_table_redimensionnable(self.table_montees)
        lm.addWidget(self.table_montees)
        self.label_tech = QLabel("")
        self.label_tech.setWordWrap(True)
        self.label_tech.setTextFormat(Qt.TextFormat.RichText)
        lm.addWidget(self.label_tech)
        self.principal.addWidget(cadre)

        self.cadre_comparaison = QFrame()
        self.cadre_comparaison.setObjectName("carteForm")
        lcmp = QVBoxLayout(self.cadre_comparaison)
        t = QLabel("Comparaison des deux tracés")
        t.setObjectName("titreCarte")
        lcmp.addWidget(t)
        self.label_comparaison = QLabel("")
        self.label_comparaison.setWordWrap(True)
        lcmp.addWidget(self.label_comparaison)
        self.table_cmp = QTableWidget(0, 4)
        self.table_cmp.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table_cmp.verticalHeader().setVisible(False)
        self.table_cmp.setMinimumHeight(420)
        configurer_table_redimensionnable(self.table_cmp)
        lcmp.addWidget(self.table_cmp)
        self.principal.addWidget(self.cadre_comparaison)

        note = QLabel("Repères tirés du tracé : un GPS ne voit ni les cailloux ni les racines. Km-effort = km + D+/100 ; "
                      "catégories ITRA : XXS < 25, XS < 45, S < 75, M < 115, L < 155, XL < 210, XXL au-delà.")
        note.setObjectName("texteSecondaire")
        note.setWordWrap(True)
        self.principal.addWidget(note)
        self.principal.addStretch()
        self._finaliser()

    # ------------------------------------------------------------
    def actualiser(self):
        a = self.athlete_id
        for cle, combo in self._combos.items():
            actuel = combo.currentData()
            combo.blockSignals(True)
            combo.clear()
            combo.addItem("— choisir un parcours —" if cle == "A" else "— aucun —", None)
            if a is not None:
                for id_, nom, km in dparc.liste_courte(a, par_id=True):
                    combo.addItem(f"{nom}" + (f" — {km:.1f} km".replace(".", ",") if km else ""), ("parcours", id_))
            if self._traces[cle] and self._traces[cle][0] == "gpx":
                combo.addItem(f"📂 {self._traces[cle][1]}", ("gpx", None))
            i = combo.findData(actuel)
            combo.setCurrentIndex(i if i >= 0 else 0)
            combo.blockSignals(False)
        self._calculer()

    def _parcours_choisi(self, cle):
        donnee = self._combos[cle].currentData()
        if donnee is None:
            self._traces[cle] = None
        elif donnee[0] == "parcours":
            brut = dparc.trace(donnee[1])
            try:
                pts = json.loads(brut) if brut else []
            except ValueError:
                pts = []
            self._traces[cle] = ("parcours", self._combos[cle].currentText().split(" — ")[0], pts)
        self._calculer()

    def _charger_gpx(self, cle):
        chemin, _ = QFileDialog.getOpenFileName(self, "Choisir un tracé GPX", "", "Tracés GPX (*.gpx)")
        if not chemin:
            return
        from noyau.traces.gpx_utils import parser_gpx
        from pathlib import Path
        try:
            pts = parser_gpx(chemin)["points"]
        except Exception as e:
            QMessageBox.warning(self, "GPX illisible", f"Ce fichier n'a pas pu être lu : {e}")
            return
        self._traces[cle] = ("gpx", Path(chemin).stem, [list(p[:3]) for p in pts])
        self.actualiser()
        combo = self._combos[cle]
        combo.setCurrentIndex(combo.findData(("gpx", None)))
        self._calculer()

    # ------------------------------------------------------------
    def _calculer(self):
        for cle in ("A", "B"):
            t = self._traces[cle]
            self._diags[cle] = dg.diagnostiquer(t[2], t[1]) if t else None
        a, b = self._diags["A"], self._diags["B"]
        for c in self.cartes.values():
            c.valeur.setText("—")
            c.detail.setText("")
        if self._traces["A"] and not a:
            self.resume.setText("Ce tracé n'a pas d'altitude exploitable (ou il est trop court) : diagnostic impossible.")
        else:
            self.resume.setText(dg.resume(a) if a else "Choisis un parcours de ta bibliothèque ou charge un GPX.")
        self._afficher_cartes(a, b)
        self._afficher_profil(a, b)
        for cle in ("A", "B"):
            d = self._diags[cle]
            self.barres[cle].setVisible(bool(d))
            self.noms_barres[cle].setVisible(bool(d))
            if d:
                self.barres[cle].definir(d["repartition_pentes"])
                self.noms_barres[cle].setText(d["nom"] or cle)
        if a:
            q = " · ".join(f"km {_fr(x['km_debut'], 0)}–{_fr(x['km_fin'], 0)} : <b>+{x['dplus']}</b> / −{x['dmoins']} m"
                           for x in a["quarts"])
            self.label_quarts.setText(f"D+ par quart ({a['nom'] or 'parcours'}) : {q}<br>"
                                      f"{a['part_dplus_seconde_moitie_pct']} % du D+ dans la seconde moitié : "
                                      f"{a['placement_denivele']}.")
        else:
            self.label_quarts.setText("")
        self._afficher_montees(a)
        self._afficher_comparaison(a, b)

    def _afficher_cartes(self, a, b):
        if not a:
            return
        c = self.cartes
        c["effort"].valeur.setText(_fr(a["km_effort"], 0))
        c["effort"].detail.setText(f"{_fr(a['distance_km'])} km · D+ {a['dplus_m']} m · D− {a['dmoins_m']} m"
                                   + (f"<br>« {b['nom']} » : {_fr(b['km_effort'], 0)}" if b else ""))
        c["itra"].valeur.setText(a["categorie_itra"])
        c["itra"].detail.setText("catégorie de course selon le km-effort" + (f"<br>« {b['nom']} » : {b['categorie_itra']}" if b else ""))
        c["terrain"].valeur.setText(a["terrain"])
        c["terrain"].detail.setText(f"{a['dplus_par_km']} m de D+ par km · altitude {a['alt_min']} à {a['alt_max']} m")
        c["tech"].valeur.setText(f"{_fr(a['note_technicite'])} / 5")
        c["tech"].detail.setText("estimée depuis le tracé (pentes raides, descentes, lacets, altitude)")
        ath = self.athlete_id
        if ath is not None:
            from noyau.course.strategie import duree_apprise
            from noyau.course.roadbook import texte_duree
            d = duree_apprise(ath, a["distance_km"], a["dplus_m"])
            if d:
                txt = f"appris sur {d['nb_sorties']} sorties"
                if b:
                    db_ = duree_apprise(ath, b["distance_km"], b["dplus_m"])
                    if db_:
                        txt += f"<br>« {b['nom']} » : {texte_duree(db_['secondes'])}"
                c["temps"].valeur.setText(texte_duree(d["secondes"]))
                c["temps"].detail.setText(txt + (" · ⚠️ bien plus long que tes sorties" if d["extrapolation"] else ""))
            else:
                c["temps"].detail.setText("pas assez de sorties Trail/Course pour l'apprendre")

    def _afficher_profil(self, a, b):
        series = []
        if a:
            fin = max(a["distance_km"], b["distance_km"] if b else 0)
            pas = max(0.1, round(fin / 300, 2))
            n = int(fin / pas) + 1

            def grille(d):
                prof, j, vals = d["profil"], 0, []
                for i in range(n):
                    km = i * pas
                    if km > d["distance_km"] + 1e-6:
                        vals.append((_fr(km), None))
                        continue
                    while j < len(prof) - 2 and prof[j + 1][0] < km:
                        j += 1
                    vals.append((_fr(km), prof[j][1]))
                return vals
            series.append({"nom": f"{a['nom'] or 'A'} (m)", "couleur": BLEU, "valeurs": grille(a)})
            if b:
                series.append({"nom": f"{b['nom'] or 'B'} (m)", "couleur": ORANGE, "valeurs": grille(b)})
        self.cadre_profil.courbe.remplissage = len(series) == 1
        self.cadre_profil.courbe.definir_series(series)

    def _afficher_montees(self, a):
        t = self.table_montees
        lignes = ([("⬆️", m["km_debut"], m["longueur_m"], f"+{m['gain_m']} m", m["pente_pct"], m["pente_max_pct"],
                    m.get("categorie")) for m in sorted(a["montees"], key=lambda x: x["km_debut"])] +
                  [("⬇️", m["km_debut"], m["longueur_m"], f"−{m['perte_m']} m", -m["pente_pct"], -m["pente_max_pct"], None)
                   for m in sorted(a["descentes"], key=lambda x: x["km_debut"])]) if a else []
        t.setRowCount(len(lignes))
        for i, (s, km, lg, dz, pm, px, cat) in enumerate(lignes):
            for j, v in enumerate([s + (f" {cat}" if cat else ""), _fr(km), f"{_fr(lg / 1000)} km", dz,
                                   f"{_fr(pm)} %", f"{_fr(px)} %"]):
                t.setItem(i, j, QTableWidgetItem(v))
        t.resizeColumnsToContents()
        if not a:
            self.label_tech.setText("")
            return
        lignes_tech = "".join(f"<li>{x}</li>" for x in a["technicite"]) or "<li>Rien de particulier : tracé plutôt courant.</li>"
        self.label_tech.setText(
            f"Pente la plus raide tenue : {_fr(a['pente_max_200m_pct'] or 0, 0)} % sur 200 m, "
            f"{_fr(a['pente_max_1km_pct'] or 0, 0)} % sur 1 km ; descente la plus raide : "
            f"{_fr(a['descente_max_200m_pct'] or 0, 0)} % sur 200 m. Sinuosité {_fr(a['sinuosite'] or 1, 2)}."
            f"<ul>{lignes_tech}</ul>")

    def _afficher_comparaison(self, a, b):
        self.cadre_comparaison.setVisible(bool(a and b))
        if not (a and b):
            return
        c = dg.comparer(a, b)
        self.label_comparaison.setText(" ".join(c["phrases"]))
        t = self.table_cmp
        t.setHorizontalHeaderLabels(["Mesure", a["nom"] or "A", b["nom"] or "B", "Écart (2e − 1er)"])
        t.setRowCount(len(c["lignes"]))
        for i, ligne in enumerate(c["lignes"]):
            for j, v in enumerate(ligne):
                t.setItem(i, j, QTableWidgetItem(v))
        t.resizeColumnsToContents()
