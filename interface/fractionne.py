"""
Fractionné (Trail Hub Center, étape 3.5, bloc 14) : court ou long, à plat
ou en côte.

Fenêtre « ⏱ Fractionné », quatre onglets :
  📚 Bibliothèque : les séances types et tes séances perso, filtrées court /
     long et à plat / en côte, avec les cibles calculées depuis ta VMA,
     l'envoi à la montre et l'ajout aux séances prévues ;
  ⏲ Minuteur : la séance minutée avec des bips, et un bouton « fin de
     répétition » qui relève tes temps sur la piste ;
  📝 Mes fractionnés : les fractionnés faits, saisis ou relevés dans la
     trace d'une sortie, avec leur analyse ;
  📈 Progression : l'évolution de chaque séance refaite.

Et deux points d'entrée dans le suivi : le détail d'une sortie et la
saisie d'une nouvelle sortie ont un menu déroulant pour choisir les
fractionnés faits pendant la séance (DialogueSaisieFractionne).
Aucune requête SQL ici : tout passe par noyau/donnees/fractionnes.py.
"""

import copy
import html
import math
import struct
import tempfile
from datetime import date
from pathlib import Path

from PySide6.QtCore import Qt, QDate, QElapsedTimer, QLocale, QTimer, QUrl
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QDateEdit, QDialog, QDialogButtonBox, QDoubleSpinBox, QFormLayout,
    QFrame, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton, QSpinBox, QTableWidget, QTableWidgetItem,
    QVBoxLayout,
)

from noyau.donnees import fractionnes as dfr
from noyau.entrainement import fractionne as fr
from interface.conteneur_onglets import ConteneurOnglets
from interface.ecran_liste import configurer_table_redimensionnable, obtenir_style_ecran
from interface.forme_evolution import _EcranAthlete

FRANCAIS = QLocale(QLocale.Language.French, QLocale.Country.France)
COULEUR_VERDICT = {"Dans la cible": "#2E7D32", "Plus vite que prévu": "#1565C0", "Plus lent que prévu": "#E65100"}


def _fr(v, d=1):
    if v is None:
        return "—"
    t = f"{v:.{d}f}".replace(".", ",")
    return t[:-2] if t.endswith(",0") else t


def _jour(d):
    try:
        return date.fromisoformat(str(d)[:10]).strftime("%d/%m/%Y")
    except ValueError:
        return str(d)[:10]


def _bouton(texte, principal=False):
    b = QPushButton(texte)
    b.setObjectName("boutonPrincipal" if principal else "boutonSecondaire")
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    return b


def _table(colonnes, hauteur=260):
    t = QTableWidget(0, len(colonnes))
    t.setHorizontalHeaderLabels(colonnes)
    t.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    t.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    t.verticalHeader().setVisible(False)
    t.setMinimumHeight(hauteur)
    configurer_table_redimensionnable(t)
    return t


def _ajuster_hauteur(t, mini=120, maxi=900):
    t.resizeRowsToContents()
    h = t.horizontalHeader().height() + sum(t.rowHeight(k) for k in range(t.rowCount())) + 6
    t.setMinimumHeight(max(mini, min(maxi, h)))
    t.setMaximumHeight(max(mini, min(maxi, h)))


def _cadre(titre):
    c = QFrame()
    c.setObjectName("carteForm")
    l = QVBoxLayout(c)
    t = QLabel(titre)
    t.setObjectName("titreCarte")
    l.addWidget(t)
    return c, l


def _spin_vma(valeur=None):
    s = QDoubleSpinBox()
    s.setLocale(FRANCAIS)
    s.setRange(8, 26)
    s.setDecimals(1)
    s.setSingleStep(0.1)
    s.setSuffix(" km/h de VMA")
    s.setValue(valeur or 15)
    return s


def libelle_seance(s):
    return f"{s['nom']}  ·  {fr.categorie(s)}" + ("  ·  perso" if s.get("perso") else "")


def remplir_combo_seances(combo, athlete_id, fmt=None, terrain=None, avec_vide=None):
    actuel = combo.currentData()
    combo.blockSignals(True)
    combo.clear()
    if avec_vide:
        combo.addItem(avec_vide, None)
    for s in dfr.seances_disponibles(athlete_id, fmt, terrain):
        combo.addItem(libelle_seance(s), s["code"])
    i = combo.findData(actuel)
    combo.setCurrentIndex(max(0, i))
    combo.blockSignals(False)


# ======================================================================
# Bips (son produit par le logiciel, sans fichier à fournir)
# ======================================================================

class Bips:
    """Bip court (décompte) et bip long (changement de phase). Silencieux si le son est indisponible."""

    def __init__(self):
        self._court = self._long = None
        try:
            from PySide6.QtMultimedia import QSoundEffect
            dossier = Path(tempfile.gettempdir())
            self._court = self._effet(QSoundEffect, dossier / "trailhub_bip_court.wav", 0.12, 880)
            self._long = self._effet(QSoundEffect, dossier / "trailhub_bip_long.wav", 0.6, 1320)
        except Exception:
            self._court = self._long = None

    @staticmethod
    def _wav(chemin, duree, freq, taux=22050):
        n = int(duree * taux)
        donnees = b"".join(struct.pack("<h", int(12000 * math.sin(2 * math.pi * freq * i / taux)
                                                 * min(1, (n - i) / 400, i / 200 + 0.01))) for i in range(n))
        entete = (b"RIFF" + struct.pack("<I", 36 + len(donnees)) + b"WAVEfmt " +
                  struct.pack("<IHHIIHH", 16, 1, 1, taux, taux * 2, 2, 16) + b"data" + struct.pack("<I", len(donnees)))
        chemin.write_bytes(entete + donnees)

    def _effet(self, classe, chemin, duree, freq):
        if not chemin.exists():
            self._wav(chemin, duree, freq)
        e = classe()
        e.setSource(QUrl.fromLocalFile(str(chemin)))
        e.setVolume(0.9)
        return e

    def court(self):
        if self._court:
            self._court.play()

    def long(self):
        if self._long:
            self._long.play()


# ======================================================================
# Saisie d'un fractionné fait (depuis le suivi d'une sortie ou l'onglet « Mes fractionnés »)
# ======================================================================

class DialogueSaisieFractionne(QDialog):
    """Temps de chaque répétition : saisis, relevés au minuteur ou retrouvés dans la trace de la sortie."""

    def __init__(self, parent, athlete_id, code=None, activite_id=None, realise=None, temps_minuteur=None,
                 vma=None):
        super().__init__(parent)
        self.athlete_id = athlete_id
        self.realise_id = realise["id"] if realise else None
        self.setWindowTitle("Fractionné fait")
        self.setStyleSheet(obtenir_style_ecran())
        self.resize(980, 820)
        self._structure = None
        lay = QVBoxLayout(self)
        form = QFormLayout()
        self.combo_seance = QComboBox()
        remplir_combo_seances(self.combo_seance, athlete_id)
        if realise and realise.get("modele"):
            i = self.combo_seance.findData(realise["modele"])
            if i < 0:                            # séance perso supprimée depuis : on garde sa copie
                self.combo_seance.addItem(realise["nom"] + "  ·  copie enregistrée", "__copie__")
                i = self.combo_seance.count() - 1
            self.combo_seance.setCurrentIndex(i)
        elif code:
            self.combo_seance.setCurrentIndex(max(0, self.combo_seance.findData(code)))
        self._copie = realise["structure"] if realise else None
        self.date = QDateEdit(QDate.currentDate())
        self.date.setCalendarPopup(True)
        self.date.setDisplayFormat("dd/MM/yyyy")
        self.combo_sortie = QComboBox()
        self.combo_sortie.addItem("— aucune sortie liée —", None)
        self._sorties = {}
        for id_, d, nom, typ, km, duree, trace in dfr.sorties_recentes(athlete_id, 90):
            self._sorties[id_] = (d, trace)
            self.combo_sortie.addItem(f"{_jour(d)} — {nom or typ or 'Sortie'}"
                                      + (f" · {_fr(km)} km" if km else "") + (" · trace GPS" if trace else ""), id_)
        if activite_id is not None and self.combo_sortie.findData(activite_id) < 0:
            s = dfr.sortie(activite_id)
            if s:
                self._sorties[s[0]] = (s[1], bool(dfr.points_de_la_sortie(s[0])))
                self.combo_sortie.addItem(f"{_jour(s[1])} — {s[2] or s[3] or 'Sortie'}", s[0])
        lien = realise.get("activite_id") if realise else activite_id
        self.combo_sortie.setCurrentIndex(max(0, self.combo_sortie.findData(lien)))
        vma_ref, source = (realise.get("vma_ref"), "enregistrée avec la séance") if realise and realise.get("vma_ref") \
            else dfr.vma_de_reference(athlete_id)
        self.vma = _spin_vma(vma or vma_ref)
        self.rpe = QSpinBox()
        self.rpe.setRange(0, 10)
        self.rpe.setSpecialValueText("—")
        self.rpe.setSuffix(" / 10")
        if realise and realise.get("rpe"):
            self.rpe.setValue(int(realise["rpe"]))
        form.addRow("Fractionné fait", self.combo_seance)
        form.addRow("Sortie", self.combo_sortie)
        form.addRow("Date", self.date)
        ligne_vma = QHBoxLayout()
        ligne_vma.addWidget(self.vma)
        self.label_vma = QLabel(f"({source})" if source else "(renseigne ta VMA dans ta fiche athlète)")
        self.label_vma.setObjectName("texteSecondaire")
        ligne_vma.addWidget(self.label_vma, 1)
        form.addRow("VMA de référence", ligne_vma)
        form.addRow("Difficulté ressentie", self.rpe)
        lay.addLayout(form)
        b = QHBoxLayout()
        self.b_trace = _bouton("📍 Retrouver les répétitions dans la trace")
        self.b_trace.clicked.connect(self._depuis_trace)
        b.addWidget(self.b_trace)
        b.addStretch()
        lay.addLayout(b)
        self.aide = QLabel("Saisis le temps (1:32 ou 92) des répétitions en distance, la distance (m) des répétitions "
                           "en durée. En côte, le D+ affine le calcul. Laisse vide une répétition non faite.")
        self.aide.setObjectName("texteSecondaire")
        self.aide.setWordWrap(True)
        lay.addWidget(self.aide)
        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(["N°", "Répétition", "Cible", "Temps réel", "Distance réelle (m)",
                                              "D+ (m)", "FC moy."])
        self.table.verticalHeader().setVisible(False)
        configurer_table_redimensionnable(self.table)
        self.table.itemChanged.connect(lambda _i: self._analyser())
        lay.addWidget(self.table, 1)
        self.label_analyse = QLabel("")
        self.label_analyse.setWordWrap(True)
        self.label_analyse.setTextFormat(Qt.TextFormat.RichText)
        lay.addWidget(self.label_analyse)
        self.notes = QLineEdit(realise.get("notes") if realise else "")
        self.notes.setPlaceholderText("Notes (piste, vent, chaleur, sensations…)")
        lay.addWidget(self.notes)
        boutons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        boutons.button(QDialogButtonBox.StandardButton.Save).setText("Enregistrer")
        boutons.button(QDialogButtonBox.StandardButton.Cancel).setText("Annuler")
        boutons.accepted.connect(self.accept)
        boutons.rejected.connect(self.reject)
        lay.addWidget(boutons)
        self.combo_seance.currentIndexChanged.connect(lambda _i: self._charger_seance())
        self.combo_sortie.currentIndexChanged.connect(self._sortie_changee)
        self.vma.valueChanged.connect(lambda _v: self._charger_seance(garder=True))
        self._charger_seance(realise["repetitions"] if realise else None, temps_minuteur=temps_minuteur)
        if realise:
            self.date.setDate(QDate.fromString(realise["date"][:10], "yyyy-MM-dd"))
        else:
            self._sortie_changee()

    # ------------------------------------------------------------
    def structure(self):
        code = self.combo_seance.currentData()
        if code == "__copie__":
            return copy.deepcopy(self._copie)
        return dfr.seance(code, self.athlete_id)

    def _sortie_changee(self):
        sid = self.combo_sortie.currentData()
        info = self._sorties.get(sid)
        if info and info[0]:
            self.date.setDate(QDate.fromString(str(info[0])[:10], "yyyy-MM-dd"))
        self.b_trace.setEnabled(bool(info and info[1]))
        self.b_trace.setToolTip("" if info and info[1] else "Choisis une sortie qui a une trace GPS.")

    def _charger_seance(self, valeurs=None, garder=False, temps_minuteur=None):
        if garder:
            valeurs = self.valeurs_repetitions()
        s = self.structure()
        self._structure = s
        self.table.blockSignals(True)
        self.table.setRowCount(0)
        if not s:
            self.table.blockSignals(False)
            return
        par_num = {v["numero"]: v for v in (valeurs or [])}
        for k, t in enumerate(temps_minuteur or []):
            par_num.setdefault(k + 1, {"numero": k + 1, "temps_s": t})
        cib = fr.cibles(s, self.vma.value())["lignes"]
        self.table.setRowCount(len(cib))
        for i, c in enumerate(cib):
            e = s["blocs"][c["bloc"]]["effort"]
            v = par_num.get(c["numero"], {})
            cible = (f"{fr.texte_temps(c['temps_s'])} ({c['allure']})" if e["mode"] == "distance"
                     else f"≈ {c['distance_m']} m ({c['allure']})")
            if s["terrain"] == "cote":
                cible += f", D+ ≈ {c['dplus_m']} m"
            fixes = [str(c["numero"]), c["libelle"] + (f" · série {c['serie'] + 1}" if (s['blocs'][c['bloc']].get('series') or 1) > 1 else ""),
                     cible]
            for j, txt in enumerate(fixes):
                it = QTableWidgetItem(txt)
                it.setFlags(Qt.ItemFlag.ItemIsEnabled)
                self.table.setItem(i, j, it)
            temps = v.get("temps_s")
            if temps is None and e["mode"] == "duree":
                temps = None
            vals = [fr.texte_temps(temps).replace(" s", "") if temps else "",
                    str(int(v["distance_m"])) if v.get("distance_m") else "",
                    str(int(v["dplus_m"])) if v.get("dplus_m") else "", str(int(v["fc"])) if v.get("fc") else ""]
            for j, txt in enumerate(vals):
                it = QTableWidgetItem(txt)
                if j == 0 and e["mode"] == "duree":
                    it.setToolTip(f"Facultatif : la durée prévue ({fr.libelle_effort(e)}) est prise par défaut.")
                if j == 2 and s["terrain"] != "cote":
                    it.setFlags(Qt.ItemFlag.ItemIsEnabled)
                self.table.setItem(i, 3 + j, it)
            self.table.item(i, 0).setData(Qt.ItemDataRole.UserRole, v.get("debut_s"))
        self.table.resizeColumnsToContents()
        self.table.setColumnWidth(3, max(self.table.columnWidth(3), 110))
        self.table.setColumnWidth(4, max(self.table.columnWidth(4), 140))
        self.table.blockSignals(False)
        self._analyser()

    def valeurs_repetitions(self):
        res = []
        for i in range(self.table.rowCount()):
            def lire(col):
                it = self.table.item(i, col)
                return it.text().strip() if it else ""
            num = int(lire(0) or 0)
            t = fr.lire_temps(lire(3))
            d = lire(4).replace(",", ".")
            dp = lire(5).replace(",", ".")
            fc = lire(6)
            r = {"numero": num, "temps_s": t,
                 "distance_m": float(d) if d.replace(".", "", 1).isdigit() else None,
                 "dplus_m": float(dp) if dp.replace(".", "", 1).isdigit() else None,
                 "fc": int(fc) if fc.isdigit() else None,
                 "debut_s": self.table.item(i, 0).data(Qt.ItemDataRole.UserRole) if self.table.item(i, 0) else None}
            s = self._structure
            if s:
                bloc = s["blocs"][next(c for c in fr.repetitions(s) if c["numero"] == num)["bloc"]]
                if bloc["effort"]["mode"] == "duree" and r["distance_m"] and not r["temps_s"]:
                    r["temps_s"] = bloc["effort"]["valeur"]
                if bloc["effort"]["mode"] == "distance" and r["temps_s"] and not r["distance_m"]:
                    r["distance_m"] = bloc["effort"]["valeur"]
            if r["temps_s"] or r["distance_m"]:
                res.append(r)
        return res

    def _analyser(self):
        if not self._structure:
            return
        a = fr.analyser(self._structure, self.vma.value(), self.valeurs_repetitions())
        if not a["nb"]:
            self.label_analyse.setText("<i>L'analyse apparaît dès le premier temps saisi.</i>")
            return
        couleur = COULEUR_VERDICT.get(a["verdict"], "#757575")
        texte = (f"<b style='color:{couleur}'>{a['verdict']}</b> — {a['nb']} répétitions, {_fr(a['pct_vma_moyen'])} % de "
                 f"VMA en moyenne ({'+' if a['ecart_moyen_pct'] >= 0 else ''}{_fr(a['ecart_moyen_pct'])} % par rapport à la "
                 f"cible), régularité {_fr(a['regularite_cv'])} %.")
        if a["conseils"]:
            texte += "<ul>" + "".join(f"<li>{html.escape(c)}</li>" for c in a["conseils"]) + "</ul>"
        est = fr.estimer_vma(self._structure, a)
        if est and abs(est - self.vma.value()) >= 0.4:
            texte += (f"<br>Ces répétitions correspondent à une VMA d'environ <b>{_fr(est)} km/h</b> "
                      f"(référence : {_fr(self.vma.value())}).")
        self.label_analyse.setText(texte)

    def _depuis_trace(self):
        sid = self.combo_sortie.currentData()
        pts = dfr.points_de_la_sortie(sid)
        if not pts or not self._structure:
            QMessageBox.information(self, "Trace", "Cette sortie n'a pas de trace GPS avec les temps.")
            return
        det = fr.detecter(pts, self._structure)
        if not det:
            QMessageBox.information(self, "Trace", "Aucune répétition retrouvée dans la trace : saisis les temps à la main.")
            return
        self._charger_seance(det)
        self._source = "trace"
        n = len(fr.repetitions(self._structure))
        QMessageBox.information(self, "Trace", f"{len(det)} répétitions sur {n} retrouvées dans la trace : les plus "
                                "rapides de la bonne longueur" + (", en pente corrigée" if self._structure["terrain"] == "cote" else "")
                                + ". Vérifie-les avant d'enregistrer (le GPS se trompe parfois de quelques mètres).")

    def accept(self):
        if not self._structure:
            QMessageBox.warning(self, "Fractionné", "Choisis le fractionné fait.")
            return
        code = self.combo_seance.currentData()
        try:
            self.realise_id = dfr.enregistrer_realise(
                self.athlete_id, self._structure, self.valeurs_repetitions(), self.date.date().toString("yyyy-MM-dd"),
                self.combo_sortie.currentData(), self.vma.value(), self.rpe.value() or None, self.notes.text().strip(),
                getattr(self, "_source", "saisie"), None if code == "__copie__" else code, self.realise_id)
        except dfr.ErreurFractionne as e:
            QMessageBox.warning(self, "Fractionné", str(e))
            return
        super().accept()


# ======================================================================
# Section « Fractionnés de cette séance » (détail d'une sortie)
# ======================================================================

class SectionFractionnesSortie(QFrame):
    """Le menu déroulant du suivi : choisis un fractionné fait pendant la sortie, puis ses temps."""

    def __init__(self, activite_id, athlete_id, parent=None):
        super().__init__(parent)
        self.setObjectName("carteForm")
        self.activite_id, self.athlete_id = activite_id, athlete_id
        lay = QVBoxLayout(self)
        t = QLabel("⏱️ Fractionnés de cette séance")
        t.setObjectName("titreCarte")
        lay.addWidget(t)
        ligne = QHBoxLayout()
        self.filtre = QComboBox()
        self.filtre.addItem("Tous", (None, None))
        for f_code, f_lib in fr.FORMATS:
            for t_code, t_lib in fr.TERRAINS:
                self.filtre.addItem(f"{f_lib} · {t_lib.lower()}", (f_code, t_code))
        self.combo = QComboBox()
        self.filtre.currentIndexChanged.connect(self._filtrer)
        ajout = _bouton("➕ Ajouter ce fractionné", True)
        ajout.clicked.connect(self._ajouter)
        ligne.addWidget(QLabel("Fractionné fait :"))
        ligne.addWidget(self.filtre)
        ligne.addWidget(self.combo, 1)
        ligne.addWidget(ajout)
        lay.addLayout(ligne)
        self.table = _table(["Fractionné", "Répétitions", "% VMA moyen", "Verdict", "Source"], 80)
        from PySide6.QtWidgets import QHeaderView
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.cellDoubleClicked.connect(lambda r, _c: self._modifier(r))
        lay.addWidget(self.table)
        b = QHBoxLayout()
        mod = _bouton("✏️ Modifier les temps")
        mod.clicked.connect(lambda: self._modifier(self.table.currentRow()))
        sup = _bouton("🗑 Retirer")
        sup.clicked.connect(self._supprimer)
        b.addWidget(mod)
        b.addWidget(sup)
        b.addStretch()
        lay.addLayout(b)
        self.label = QLabel("")
        self.label.setObjectName("texteSecondaire")
        self.label.setWordWrap(True)
        lay.addWidget(self.label)
        self._filtrer()
        self.actualiser()

    def _filtrer(self):
        fmt, terrain = self.filtre.currentData()
        remplir_combo_seances(self.combo, self.athlete_id, fmt, terrain)

    def actualiser(self):
        self._realises = dfr.realises(None, activite_id=self.activite_id)
        t = self.table
        t.setRowCount(len(self._realises))
        for i, r in enumerate(self._realises):
            a = fr.bilan_realise(r)
            vals = [r["nom"], f"{a['nb']} / {len(fr.repetitions(r['structure']))}",
                    f"{_fr(a.get('pct_vma_moyen'))} %" if a.get("nb") else "—", a["verdict"],
                    "relevé dans la trace" if r.get("source") == "trace" else "saisi"]
            for j, v in enumerate(vals):
                it = QTableWidgetItem(v)
                if j == 3:
                    it.setForeground(QColor(COULEUR_VERDICT.get(a["verdict"], "#757575")))
                t.setItem(i, j, it)
        t.resizeColumnsToContents()
        _ajuster_hauteur(t, 60, 300)
        self.label.setText("Choisis dans le menu le fractionné fait (tu peux en ajouter plusieurs : par exemple un "
                           "10 × 200 m puis un 3 × 1000 m). Les temps se saisissent ou se retrouvent dans la trace."
                           if not self._realises else "Double-clique sur une ligne pour revoir ou corriger ses temps.")

    def _ajouter(self):
        d = DialogueSaisieFractionne(self, self.athlete_id, self.combo.currentData(), self.activite_id)
        if d.exec():
            self.actualiser()

    def _modifier(self, ligne):
        if 0 <= ligne < len(self._realises):
            d = DialogueSaisieFractionne(self, self.athlete_id, realise=self._realises[ligne])
            if d.exec():
                self.actualiser()

    def _supprimer(self):
        ligne = self.table.currentRow()
        if 0 <= ligne < len(self._realises) and QMessageBox.question(
                self, "Retirer", f"Retirer « {self._realises[ligne]['nom']} » de cette sortie ?") \
                == QMessageBox.StandardButton.Yes:
            dfr.supprimer_realise(self._realises[ligne]["id"])
            self.actualiser()


# ======================================================================
# Création d'une séance perso
# ======================================================================

class DialogueSeancePerso(QDialog):

    def __init__(self, parent, structure=None):
        super().__init__(parent)
        self.setWindowTitle("Ma séance de fractionné")
        self.setStyleSheet(obtenir_style_ecran())
        self.resize(1000, 640)
        s = copy.deepcopy(structure) if structure else {
            "nom": "", "format": "court", "terrain": "plat", "echauffement_min": 20, "retour_calme_min": 10,
            "blocs": [{"series": 1, "repetitions": 8, "effort": {"mode": "distance", "valeur": 400}, "pct_vma": 100,
                       "pente_pct": 0, "recup": {"mode": "duree", "valeur": 90, "type": "trot"}, "recup_series_s": 0}]}
        lay = QVBoxLayout(self)
        form = QFormLayout()
        self.nom = QLineEdit(s["nom"] + (" (perso)" if structure and not structure.get("perso") else ""))
        self.format = QComboBox()
        for c, l in fr.FORMATS:
            self.format.addItem(l, c)
        self.format.setCurrentIndex(self.format.findData(s["format"]))
        self.terrain = QComboBox()
        for c, l in fr.TERRAINS:
            self.terrain.addItem(l, c)
        self.terrain.setCurrentIndex(self.terrain.findData(s["terrain"]))
        self.ech = QSpinBox()
        self.ech.setRange(0, 60)
        self.ech.setSuffix(" min")
        self.ech.setValue(int(s.get("echauffement_min") or 0))
        self.rac = QSpinBox()
        self.rac.setRange(0, 60)
        self.rac.setSuffix(" min")
        self.rac.setValue(int(s.get("retour_calme_min") or 0))
        self.description = QLineEdit(s.get("description") or "")
        form.addRow("Nom", self.nom)
        form.addRow("Format", self.format)
        form.addRow("Terrain", self.terrain)
        form.addRow("Échauffement", self.ech)
        form.addRow("Retour au calme", self.rac)
        form.addRow("Consignes", self.description)
        lay.addLayout(form)
        self.table = QTableWidget(0, 9)
        self.table.setHorizontalHeaderLabels(["Séries", "Répétitions", "En", "Distance (m) ou durée (s)", "% VMA",
                                              "Pente (%)", "Récup (s)", "Type de récup", "Entre séries (s)"])
        self.table.verticalHeader().setVisible(False)
        lay.addWidget(self.table, 1)
        b = QHBoxLayout()
        a = _bouton("➕ Bloc")
        a.clicked.connect(lambda: self._ajouter_bloc(None))
        r = _bouton("🗑 Retirer le bloc")
        r.clicked.connect(lambda: self.table.removeRow(self.table.currentRow()) if self.table.currentRow() >= 0 else None)
        b.addWidget(a)
        b.addWidget(r)
        b.addStretch()
        lay.addLayout(b)
        aide = QLabel("Un bloc = des répétitions identiques. Une pyramide se fait avec un bloc par marche.")
        aide.setObjectName("texteSecondaire")
        lay.addWidget(aide)
        boutons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        boutons.button(QDialogButtonBox.StandardButton.Save).setText("Enregistrer")
        boutons.button(QDialogButtonBox.StandardButton.Cancel).setText("Annuler")
        boutons.accepted.connect(self.accept)
        boutons.rejected.connect(self.reject)
        lay.addWidget(boutons)
        for bloc in s["blocs"]:
            self._ajouter_bloc(bloc)

    def _ajouter_bloc(self, bloc):
        bloc = bloc or {"series": 1, "repetitions": 6, "effort": {"mode": "distance", "valeur": 400}, "pct_vma": 100,
                        "pente_pct": 0, "recup": {"mode": "duree", "valeur": 90, "type": "trot"}, "recup_series_s": 0}
        r = self.table.rowCount()
        self.table.insertRow(r)

        def spin(mini, maxi, val, pas=1):
            s = QSpinBox()
            s.setRange(mini, maxi)
            s.setSingleStep(pas)
            s.setValue(int(val or 0))
            return s
        mode = QComboBox()
        mode.addItem("Distance", "distance")
        mode.addItem("Durée", "duree")
        mode.setCurrentIndex(mode.findData(bloc["effort"]["mode"]))
        typ = QComboBox()
        typ.addItems(fr.TYPES_RECUP)
        typ.setCurrentText(bloc["recup"].get("type") or "trot")
        widgets = [spin(1, 10, bloc.get("series") or 1), spin(1, 50, bloc["repetitions"]), mode,
                   spin(5, 10000, bloc["effort"]["valeur"], 50), spin(50, 130, bloc["pct_vma"]),
                   spin(0, 40, bloc.get("pente_pct") or 0), spin(0, 1200, bloc["recup"]["valeur"], 15), typ,
                   spin(0, 1200, bloc.get("recup_series_s") or 0, 30)]
        for c, w in enumerate(widgets):
            self.table.setCellWidget(r, c, w)
        self.table.setRowHeight(r, 40)

    def structure(self):
        blocs = []
        for r in range(self.table.rowCount()):
            w = [self.table.cellWidget(r, c) for c in range(9)]
            blocs.append({"series": w[0].value(), "repetitions": w[1].value(),
                          "effort": {"mode": w[2].currentData(), "valeur": w[3].value()}, "pct_vma": w[4].value(),
                          "pente_pct": w[5].value(), "recup": {"mode": "duree", "valeur": w[6].value(),
                                                               "type": w[7].currentText()},
                          "recup_series_s": w[8].value()})
        return {"nom": self.nom.text().strip(), "format": self.format.currentData(), "terrain": self.terrain.currentData(),
                "echauffement_min": self.ech.value(), "retour_calme_min": self.rac.value(), "blocs": blocs,
                "objectif": "", "description": self.description.text().strip()}

    def accept(self):
        err = fr.verifier_structure(self.structure())
        if err:
            QMessageBox.warning(self, "Séance", err)
            return
        super().accept()


# ======================================================================
# Onglet 1 — Bibliothèque
# ======================================================================

class BibliothequeFractionne(_EcranAthlete):

    def __init__(self, athlete_id_initial=None):
        super().__init__("📚  Fractionné : bibliothèque",
                         "Court ou long, à plat ou en côte : chaque séance avec ses cibles calculées depuis ta VMA. "
                         "En côte, la vitesse attendue tient compte de la pente.", athlete_id_initial)
        ligne = QHBoxLayout()
        self.f_format = QComboBox()
        self.f_format.addItem("Court et long", None)
        for c, l in fr.FORMATS:
            self.f_format.addItem(l, c)
        self.f_terrain = QComboBox()
        self.f_terrain.addItem("À plat et en côte", None)
        for c, l in fr.TERRAINS:
            self.f_terrain.addItem(l, c)
        self.vma = _spin_vma()
        self.label_vma = QLabel("")
        self.label_vma.setObjectName("texteSecondaire")
        for w in (self.f_format, self.f_terrain):
            w.currentIndexChanged.connect(self._remplir)
        self.vma.valueChanged.connect(self._detail)
        ligne.addWidget(self.f_format)
        ligne.addWidget(self.f_terrain)
        ligne.addSpacing(20)
        ligne.addWidget(self.vma)
        ligne.addWidget(self.label_vma, 1)
        self.principal.addLayout(ligne)
        self.table = _table(["Séance", "Catégorie", "Ce qu'on fait", "Durée totale", "Objectif"], 380)
        self.table.itemSelectionChanged.connect(self._detail)
        self.principal.addWidget(self.table)

        cadre, lc = _cadre("Détail et cibles")
        self.label_detail = QLabel("")
        self.label_detail.setWordWrap(True)
        self.label_detail.setTextFormat(Qt.TextFormat.RichText)
        lc.addWidget(self.label_detail)
        self.table_cibles = _table(["N°", "Répétition", "% VMA", "Temps cible", "Allure", "Distance attendue", "D+ attendu"], 120)
        lc.addWidget(self.table_cibles)
        b = QHBoxLayout()
        for texte, f, princ in (("▶ Minuteur", self._minuteur, True), ("📝 Saisir des temps", self._saisir, False),
                                ("⌚ Envoyer à la montre", self._montre, False),
                                ("📅 Ajouter aux séances prévues", self._prevoir, False),
                                ("✏️ Créer ma version", self._perso, False), ("🗑 Supprimer (perso)", self._supprimer, False)):
            w = _bouton(texte, princ)
            w.clicked.connect(f)
            b.addWidget(w)
        b.addStretch()
        lc.addLayout(b)
        self.principal.addWidget(cadre)

        cadre, lc = _cadre("Temps de passage selon ta VMA")
        self.table_passages = _table(["% VMA", "Allure", "100 m", "200 m", "300 m", "400 m", "1000 m"], 120)
        lc.addWidget(self.table_passages)
        self.principal.addWidget(cadre)
        self.principal.addStretch()
        self._seances = []
        self._finaliser()

    def actualiser(self):
        vma, source = dfr.vma_de_reference(self.athlete_id)
        self.vma.blockSignals(True)
        if vma:
            self.vma.setValue(vma)
        self.vma.blockSignals(False)
        self.label_vma.setText(f"VMA {source} : modifie-la ici pour tester d'autres allures." if source else
                               "Pas de VMA connue : renseigne-la dans ta fiche athlète (test VMA ou demi-Cooper).")
        self._remplir()

    def _remplir(self):
        self._seances = dfr.seances_disponibles(self.athlete_id, self.f_format.currentData(), self.f_terrain.currentData())
        t = self.table
        actuel = t.currentRow()
        t.setRowCount(len(self._seances))
        for i, s in enumerate(self._seances):
            c = fr.cibles(s, self.vma.value())
            vals = [s["nom"] + (" (perso)" if s.get("perso") else ""), fr.categorie(s), fr.resume(s),
                    fr.texte_temps(c["duree_totale_s"]), s.get("objectif") or ""]
            for j, v in enumerate(vals):
                t.setItem(i, j, QTableWidgetItem(v))
        t.resizeColumnsToContents()
        if t.columnWidth(2) > 460:
            t.setColumnWidth(2, 460)
        t.selectRow(actuel if 0 <= actuel < len(self._seances) else 0)
        self._detail()
        self._passages()

    def courante(self):
        i = self.table.currentRow()
        return self._seances[i] if 0 <= i < len(self._seances) else None

    def _detail(self):
        s = self.courante()
        self._passages()
        if not s:
            self.label_detail.setText("")
            self.table_cibles.setRowCount(0)
            return
        vma = self.vma.value()
        c = fr.cibles(s, vma)
        self.label_detail.setText(
            f"<b>{html.escape(s['nom'])}</b> — {fr.categorie(s)}<br>{html.escape(fr.resume(s))}<br>"
            f"{html.escape(s.get('description') or '')}<br>"
            f"Échauffement {s.get('echauffement_min') or 0} min, retour au calme {s.get('retour_calme_min') or 0} min · "
            f"{fr.texte_temps(c['temps_effort_s'])} d'effort, {_fr(c['distance_effort_m'] / 1000, 2)} km vite"
            + (f", ≈ {c['dplus_m']} m de D+" if c["dplus_m"] else "")
            + f" · séance complète ≈ {fr.texte_temps(c['duree_totale_s'])}.")
        t = self.table_cibles
        lignes = c["lignes"]
        # une ligne par bloc différent suffit quand les répétitions sont identiques
        vues, a_afficher = set(), []
        for l in lignes:
            cle = (l["bloc"], l["serie"]) if len(s["blocs"]) > 1 else ("tout",)
            if cle not in vues:
                vues.add(cle)
                a_afficher.append(l)
        t.setRowCount(len(a_afficher))
        for i, l in enumerate(a_afficher):
            bloc = s["blocs"][l["bloc"]]
            n = bloc["repetitions"] * (bloc.get("series") or 1) if len(s["blocs"]) == 1 else bloc["repetitions"]
            vals = [str(l["numero"]) if n == 1 else f"{l['numero']} à {l['numero'] + n - 1}", l["libelle"],
                    f"{l['pct_vma']:g} %", fr.texte_temps(l["temps_s"]), l["allure"] + (
                        f" (plat {l['allure_plat']})" if s["terrain"] == "cote" else ""),
                    f"{l['distance_m']} m", f"{l['dplus_m']} m" if l["dplus_m"] else "—"]
            for j, v in enumerate(vals):
                t.setItem(i, j, QTableWidgetItem(v))
        t.resizeColumnsToContents()
        _ajuster_hauteur(t, 80, 420)

    def _passages(self):
        t = self.table_passages
        lignes = fr.tableau_allures(self.vma.value())
        t.setRowCount(len(lignes))
        for i, (pct, allure, temps) in enumerate(lignes):
            for j, v in enumerate([f"{pct} %", allure] + [fr.texte_temps(x) for x in temps]):
                it = QTableWidgetItem(v)
                if pct == 100:
                    f = it.font()
                    f.setBold(True)
                    it.setFont(f)
                t.setItem(i, j, it)
        t.resizeColumnsToContents()
        _ajuster_hauteur(t, 80, 400)

    def _fenetre(self):
        w = self.parent()
        while w is not None and not isinstance(w, FractionneFenetre):
            w = w.parent()
        return w

    def _minuteur(self):
        s, f = self.courante(), self._fenetre()
        if s and f:
            f.minuteur.charger(s["code"], self.vma.value())
            f.tabs.setCurrentWidget(f.minuteur)

    def _saisir(self):
        s = self.courante()
        if s and self.athlete_id is not None:
            d = DialogueSaisieFractionne(self, self.athlete_id, s["code"], vma=self.vma.value())
            if d.exec():
                f = self._fenetre()
                if f:
                    f.mes.actualiser()

    def _montre(self):
        s = self.courante()
        if not s:
            return
        from PySide6.QtWidgets import QFileDialog
        from noyau.entrainement.export_fit_seance import encoder_seance, nom_fichier
        cible = None
        for racine in (list(Path("/Volumes").glob("*")) + list(Path("/media").glob("*/*"))
                       + [Path(f"{l}:/") for l in "DEFGHIJ"]):
            try:
                if (racine / "GARMIN").is_dir():
                    cible = racine / "GARMIN" / "NewFiles"
                    break
            except OSError:
                continue
        if cible is None:
            dossier = QFileDialog.getExistingDirectory(
                self, "Montre non détectée : choisis le dossier GARMIN/NewFiles (ou un dossier de ton choix)")
            if not dossier:
                return
            cible = Path(dossier)
        try:
            cible.mkdir(parents=True, exist_ok=True)
            chemin = cible / nom_fichier(s["nom"])
            chemin.write_bytes(encoder_seance(s["nom"], fr.etapes_montre(s, self.vma.value())))
        except (OSError, ValueError) as e:
            QMessageBox.warning(self, "Envoi impossible", str(e))
            return
        QMessageBox.information(self, "Séance prête", f"Fichier créé : {chemin}\n\nDébranche la montre : la séance "
                                "apparaît dans Entraînement > Séances. "
                                + ("Allure cible réglée sur chaque effort." if s["terrain"] == "plat" else
                                   "En côte, les efforts sont sans allure imposée (à la sensation)."))

    def _prevoir(self):
        s = self.courante()
        if not s or self.athlete_id is None:
            return
        d = QDialog(self)
        d.setWindowTitle("Ajouter aux séances prévues")
        d.setStyleSheet(obtenir_style_ecran())
        l = QFormLayout(d)
        jour = QDateEdit(QDate.currentDate().addDays(1))
        jour.setCalendarPopup(True)
        jour.setDisplayFormat("dd/MM/yyyy")
        l.addRow("Date", jour)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(d.accept)
        bb.rejected.connect(d.reject)
        l.addRow(bb)
        if not d.exec():
            return
        import json
        from noyau.donnees import seances as dseance
        dseance.creer({"athlete_id": self.athlete_id, "nom": s["nom"],
                       "type_seance": "Côtes" if s["terrain"] == "cote" else "Fractionné",
                       "date_prevue": jour.date().toString("yyyy-MM-dd"),
                       "etapes_json": json.dumps(fr.etapes_montre(s, self.vma.value()), ensure_ascii=False),
                       "notes": fr.resume(s)})
        QMessageBox.information(self, "Séance prévue", "Séance ajoutée à tes séances structurées (Planification).")

    def _perso(self):
        if self.athlete_id is None:
            return
        s = self.courante()
        d = DialogueSeancePerso(self, s)
        if d.exec():
            try:
                pid = int(s["code"].split(":")[1]) if s and s.get("perso") else None
                dfr.enregistrer_perso(self.athlete_id, d.structure(), pid)
            except dfr.ErreurFractionne as e:
                QMessageBox.warning(self, "Séance", str(e))
            self._remplir()

    def _supprimer(self):
        s = self.courante()
        if not s or not s.get("perso"):
            QMessageBox.information(self, "Supprimer", "Seules tes séances perso se suppriment.")
            return
        if QMessageBox.question(self, "Supprimer", f"Supprimer « {s['nom']} » ? Les fractionnés déjà faits avec "
                                "gardent leur copie.") == QMessageBox.StandardButton.Yes:
            dfr.supprimer_perso(int(s["code"].split(":")[1]))
            self._remplir()


# ======================================================================
# Onglet 2 — Minuteur à bips
# ======================================================================

class MinuteurFractionne(_EcranAthlete):

    def __init__(self, athlete_id_initial=None):
        super().__init__("⏲  Minuteur de fractionné",
                         "Lance la séance : un bip à chaque changement, trois bips courts avant la fin de chaque phase. "
                         "Sur piste, appuie sur « Fin de répétition » en passant la ligne : tes temps sont relevés.",
                         athlete_id_initial)
        ligne = QHBoxLayout()
        self.combo = QComboBox()
        self.vma = _spin_vma()
        self.son = QCheckBox("Bips")
        self.son.setChecked(True)
        self.sans_echauffement = QCheckBox("Sans échauffement ni retour au calme")
        ligne.addWidget(self.combo, 1)
        ligne.addWidget(self.vma)
        ligne.addWidget(self.son)
        ligne.addWidget(self.sans_echauffement)
        self.principal.addLayout(ligne)
        cadre = QFrame()
        cadre.setObjectName("cadreMinuteur")
        self.cadre_minuteur = cadre
        lc = QVBoxLayout(cadre)
        lc.setContentsMargins(20, 24, 20, 24)
        self.l_phase = QLabel("Prêt")
        self.l_temps = QLabel("0:00")
        self.l_cible = QLabel("")
        self.l_suivant = QLabel("")
        for w, taille, gras in ((self.l_phase, 30, True), (self.l_temps, 130, True), (self.l_cible, 22, False),
                                (self.l_suivant, 16, False)):
            w.setAlignment(Qt.AlignmentFlag.AlignCenter)
            w.setWordWrap(True)
            w.setStyleSheet(f"background: transparent; font-size: {taille}px; font-weight: {700 if gras else 400};")
            lc.addWidget(w)
        self._couleur_phase(None)
        self.principal.addWidget(cadre)
        b = QHBoxLayout()
        self.b_go = _bouton("▶ Démarrer", True)
        self.b_go.clicked.connect(self._demarrer_pause)
        self.b_tour = _bouton("⏱ Fin de répétition")
        self.b_tour.clicked.connect(self._fin_repetition)
        self.b_passer = _bouton("⏭ Phase suivante")
        self.b_passer.clicked.connect(self._suivante)
        self.b_stop = _bouton("⏹ Arrêter")
        self.b_stop.clicked.connect(self._arreter)
        self.b_saisir = _bouton("📝 Enregistrer les temps")
        self.b_saisir.clicked.connect(self._enregistrer)
        for w in (self.b_go, self.b_tour, self.b_passer, self.b_stop, self.b_saisir):
            b.addWidget(w)
        b.addStretch()
        self.principal.addLayout(b)
        self.table = _table(["Répétition", "Cible", "Temps relevé", "Écart"], 120)
        self.principal.addWidget(self.table)
        self.principal.addStretch()
        self._bips = None
        self._phases, self._i, self._temps_reps = [], -1, []
        self._chrono = QElapsedTimer()
        self._ecoule_avant = 0.0
        self._timer = QTimer(self)
        self._timer.setInterval(100)
        self._timer.timeout.connect(self._tic)
        self._dernier_bip = None
        self._en_route = False
        self.combo.currentIndexChanged.connect(lambda _i: self._preparer())
        self.vma.valueChanged.connect(lambda _v: self._preparer())
        self.sans_echauffement.toggled.connect(lambda _b: self._preparer())
        self._finaliser()
        from interface.theme import PALETTE, obtenir_couleur_accent
        accent = obtenir_couleur_accent()
        self.setStyleSheet(self.styleSheet() + (
            " QCheckBox { background: transparent; spacing: 8px; }"
            f" QCheckBox::indicator {{ width: 16px; height: 16px; border: 1px solid {PALETTE['texte_discret']};"
            f" border-radius: 4px; background: {PALETTE['carte_haute']}; }}"
            f" QCheckBox::indicator:checked {{ background: {accent}; border-color: {accent}; }}"))

    def actualiser(self):
        remplir_combo_seances(self.combo, self.athlete_id)
        vma, _s = dfr.vma_de_reference(self.athlete_id)
        if vma and not self._en_route:
            self.vma.blockSignals(True)
            self.vma.setValue(vma)
            self.vma.blockSignals(False)
        self._preparer()

    def charger(self, code, vma):
        self.combo.setCurrentIndex(max(0, self.combo.findData(code)))
        self.vma.setValue(vma)
        self._preparer()

    def _structure(self):
        return dfr.seance(self.combo.currentData(), self.athlete_id)

    def _preparer(self):
        if self._en_route:
            return
        s = self._structure()
        self._phases = fr.deroule(s, self.vma.value()) if s else []
        if self.sans_echauffement.isChecked():
            self._phases = [p for p in self._phases if p["phase"] not in ("echauffement", "retour")]
        self._i, self._temps_reps = -1, []
        self._ecoule_avant = 0.0
        total = sum(p["duree_s"] for p in self._phases)
        self.l_phase.setText("Prêt" if s else "Choisis une séance")
        self.l_temps.setText(self._horloge(total))
        self._couleur_phase(None)
        self.l_cible.setText(fr.resume(s) if s else "")
        self.l_suivant.setText(f"Durée prévue ≈ {fr.texte_temps(total)}" if total else "")
        self.b_go.setText("▶ Démarrer")
        self._maj_table()

    def _demarrer_pause(self):
        if not self._phases:
            return
        if self._bips is None and self.son.isChecked():
            self._bips = Bips()
        if self._timer.isActive():
            self._timer.stop()
            self._ecoule_avant += self._chrono.elapsed() / 1000
            self.b_go.setText("▶ Reprendre")
            return
        if self._i < 0:
            self._i = 0
            self._ecoule_avant = 0.0
            self._en_route = True
            self._bip(long=True)
        self._chrono.start()
        self._timer.start()
        self.b_go.setText("⏸ Pause")
        self._tic()

    def _couleur_phase(self, phase):
        fond = {"effort": "rgba(239, 83, 80, 0.22)", "recup": "rgba(66, 165, 245, 0.18)",
                "echauffement": "rgba(102, 187, 106, 0.16)", "retour": "rgba(102, 187, 106, 0.16)"}.get(phase,
                                                                                                   "rgba(127,127,127,0.10)")
        self.cadre_minuteur.setStyleSheet(f"#cadreMinuteur {{ background: {fond}; border-radius: 16px; }}")

    @staticmethod
    def _horloge(s):
        s = max(0, int(math.ceil(s)))
        h, r = divmod(s, 3600)
        m, sec = divmod(r, 60)
        return f"{h}:{m:02d}:{sec:02d}" if h else f"{m}:{sec:02d}"

    def _ecoule(self):
        return self._ecoule_avant + (self._chrono.elapsed() / 1000 if self._timer.isActive() else 0)

    def _bip(self, long=False):
        if not self.son.isChecked():
            return
        if self._bips is None:
            self._bips = Bips()
        (self._bips.long if long else self._bips.court)()

    def _tic(self):
        if not (0 <= self._i < len(self._phases)):
            return
        p = self._phases[self._i]
        reste = p["duree_s"] - self._ecoule()
        if reste <= 0:
            if p["phase"] == "effort" and p["mode"] == "duree":
                self._temps_reps.append((p["numero"], p["duree_s"]))
                self._maj_table()
            self._suivante()
            return
        s = math.ceil(reste)
        if s <= 3 and self._dernier_bip != (self._i, s):
            self._dernier_bip = (self._i, s)
            self._bip()
        self.l_phase.setText(p["libelle"])
        self._couleur_phase(p["phase"])
        self.l_temps.setText(self._horloge(reste))
        self.l_cible.setText(p.get("cible") or "")
        nxt = self._phases[self._i + 1]["libelle"] if self._i + 1 < len(self._phases) else "Fin de la séance"
        self.l_suivant.setText(f"Ensuite : {nxt}")

    def _fin_repetition(self):
        """Fin d'une répétition en distance : relève le temps et passe à la récupération."""
        if not (0 <= self._i < len(self._phases)) or not self._timer.isActive():
            return
        p = self._phases[self._i]
        if p["phase"] != "effort":
            return
        self._temps_reps.append((p["numero"], round(self._ecoule(), 1)))
        self._maj_table()
        self._suivante()

    def _suivante(self):
        if self._i < 0:
            return
        self._i += 1
        self._ecoule_avant = 0.0
        self._chrono.restart()
        if self._i >= len(self._phases):
            self._timer.stop()
            self._en_route = False
            self._bip(long=True)
            self.l_phase.setText("Séance terminée 👏")
            self._couleur_phase(None)
            self.l_temps.setText("0:00")
            self.l_cible.setText(f"{len(self._temps_reps)} temps relevés : « Enregistrer les temps » pour les garder.")
            self.l_suivant.setText("")
            self.b_go.setText("▶ Démarrer")
            return
        self._bip(long=True)
        self._tic()

    def _arreter(self):
        self._timer.stop()
        self._en_route = False
        temps = self._temps_reps
        self._preparer()
        self._temps_reps = temps
        self._maj_table()

    def _maj_table(self):
        s = self._structure()
        cib = {l["numero"]: l for l in fr.cibles(s, self.vma.value())["lignes"]} if s else {}
        t = self.table
        t.setRowCount(len(self._temps_reps))
        for i, (num, temps) in enumerate(self._temps_reps):
            c = cib.get(num, {})
            ecart = temps - c["temps_s"] if c else None
            vals = [f"{num} — {c.get('libelle', '')}", fr.texte_temps(c.get("temps_s")), fr.texte_temps(temps),
                    (("+" if ecart > 0 else "−") + _fr(abs(ecart)) + " s") if ecart is not None else ""]
            for j, v in enumerate(vals):
                t.setItem(i, j, QTableWidgetItem(v))
        t.resizeColumnsToContents()
        _ajuster_hauteur(t, 60, 500)

    def _enregistrer(self):
        if self.athlete_id is None or not self._structure():
            return
        temps = [None] * len(fr.repetitions(self._structure()))
        for num, t in self._temps_reps:
            if 1 <= num <= len(temps):
                temps[num - 1] = t
        valeurs = [{"numero": k + 1, "temps_s": t} for k, t in enumerate(temps) if t]
        d = DialogueSaisieFractionne(self, self.athlete_id, self.combo.currentData(), vma=self.vma.value())
        d._charger_seance(valeurs)
        if d.exec():
            self._temps_reps = []
            self._maj_table()
            w = self.parent()
            while w is not None and not isinstance(w, FractionneFenetre):
                w = w.parent()
            if w:
                w.mes.actualiser()


# ======================================================================
# Onglet 3 — Mes fractionnés
# ======================================================================

class MesFractionnes(_EcranAthlete):

    def __init__(self, athlete_id_initial=None):
        super().__init__("📝  Mes fractionnés",
                         "Les fractionnés faits, avec le temps de chaque répétition comparé à la cible. Ils se "
                         "choisissent aussi dans le détail d'une sortie (menu « Fractionné fait »).", athlete_id_initial)
        b = QHBoxLayout()
        for texte, f, p in (("➕ Saisir un fractionné fait", self._ajouter, True), ("✏️ Modifier", self._modifier, False),
                            ("🗑 Supprimer", self._supprimer, False)):
            w = _bouton(texte, p)
            w.clicked.connect(f)
            b.addWidget(w)
        b.addStretch()
        self.principal.addLayout(b)
        self.table = _table(["Date", "Fractionné", "Catégorie", "Répétitions", "% VMA moyen", "Écart à la cible",
                             "Régularité", "Verdict", "Sortie"], 300)
        self.table.itemSelectionChanged.connect(self._detail)
        self.table.cellDoubleClicked.connect(lambda _r, _c: self._modifier())
        self.principal.addWidget(self.table)
        cadre, lc = _cadre("Détail")
        self.label = QLabel("")
        self.label.setWordWrap(True)
        self.label.setTextFormat(Qt.TextFormat.RichText)
        lc.addWidget(self.label)
        self.table_reps = _table(["N°", "Répétition", "Cible", "Réalisé", "Allure", "% VMA", "Écart", "FC"], 120)
        lc.addWidget(self.table_reps)
        self.principal.addWidget(cadre)
        self.principal.addStretch()
        self._realises = []
        self._finaliser()

    def actualiser(self):
        self._realises = dfr.realises(self.athlete_id)
        t = self.table
        t.setRowCount(len(self._realises))
        for i, r in enumerate(self._realises):
            a = fr.bilan_realise(r)
            sortie = dfr.sortie(r["activite_id"]) if r.get("activite_id") else None
            vals = [date.fromisoformat(r["date"][:10]).strftime("%d/%m/%Y"), r["nom"], fr.categorie(r),
                    f"{a['nb']} / {len(fr.repetitions(r['structure']))}",
                    f"{_fr(a.get('pct_vma_moyen'))} %" if a.get("nb") else "—",
                    (f"{'+' if a['ecart_moyen_pct'] >= 0 else ''}{_fr(a['ecart_moyen_pct'])} %") if a.get("nb") else "—",
                    f"{_fr(a.get('regularite_cv'))} %" if a.get("nb") else "—", a["verdict"],
                    (sortie[2] or sortie[3] or "") if sortie else ""]
            for j, v in enumerate(vals):
                it = QTableWidgetItem(v)
                if j == 7:
                    it.setForeground(QColor(COULEUR_VERDICT.get(a["verdict"], "#757575")))
                t.setItem(i, j, it)
        t.resizeColumnsToContents()
        if self._realises and t.currentRow() < 0:
            t.selectRow(0)
        self._detail()

    def _courant(self):
        i = self.table.currentRow()
        return self._realises[i] if 0 <= i < len(self._realises) else None

    def _detail(self):
        r = self._courant()
        if not r:
            self.label.setText("Aucun fractionné enregistré pour l'instant." if not self._realises else "")
            self.table_reps.setRowCount(0)
            return
        a = fr.bilan_realise(r)
        txt = (f"<b>{html.escape(r['nom'])}</b> — {fr.categorie(r)}, le "
               f"{date.fromisoformat(r['date'][:10]).strftime('%d/%m/%Y')} · VMA de référence {_fr(r.get('vma_ref'))} km/h"
               + (f" · difficulté {r['rpe']}/10" if r.get("rpe") else ""))
        if a.get("nb"):
            txt += (f"<br><b style='color:{COULEUR_VERDICT.get(a['verdict'], '#757575')}'>{a['verdict']}</b> : "
                    f"{_fr(a['pct_vma_moyen'])} % de VMA en moyenne, régularité {_fr(a['regularite_cv'])} %, "
                    f"fin de séance {'+' if a['baisse_fin_pct'] >= 0 else ''}{_fr(a['baisse_fin_pct'])} %.")
            if a["conseils"]:
                txt += "<ul>" + "".join(f"<li>{html.escape(c)}</li>" for c in a["conseils"]) + "</ul>"
            est = fr.estimer_vma(r["structure"], a)
            if est and r.get("vma_ref") and abs(est - r["vma_ref"]) >= 0.4:
                txt += f"Ces répétitions correspondent à une VMA d'environ <b>{_fr(est)} km/h</b>."
        if r.get("notes"):
            txt += f"<br><i>{html.escape(r['notes'])}</i>"
        self.label.setText(txt)
        t = self.table_reps
        cib = {l["numero"]: l for l in fr.cibles(r["structure"], r.get("vma_ref") or 15)["lignes"]}
        t.setRowCount(len(a["lignes"]))
        for i, l in enumerate(a["lignes"]):
            c = cib[l["numero"]]
            mode = r["structure"]["blocs"][c["bloc"]]["effort"]["mode"]
            cible = fr.texte_temps(c["temps_s"]) if mode == "distance" else f"{c['distance_m']} m"
            fait = fr.texte_temps(l["temps_s"]) if mode == "distance" else f"{l['distance_m']} m"
            ecart = (("+" if l["ecart_s"] > 0 else "−") + _fr(abs(l["ecart_s"])) + " s") if l.get("ecart_s") is not None \
                else (("+" if l["ecart_m"] >= 0 else "−") + f"{abs(l['ecart_m'])} m")
            vals = [str(l["numero"]), c["libelle"], cible, fait + (f", D+ {int(l['dplus_m'])} m" if l.get("dplus_m") else ""),
                    l["allure"], f"{_fr(l['pct_vma'])} %", ecart, str(l["fc"]) if l.get("fc") else ""]
            for j, v in enumerate(vals):
                t.setItem(i, j, QTableWidgetItem(v))
        t.resizeColumnsToContents()
        _ajuster_hauteur(t, 80, 700)

    def _ajouter(self):
        if self.athlete_id is None:
            return
        d = DialogueSaisieFractionne(self, self.athlete_id)
        if d.exec():
            self.actualiser()

    def _modifier(self):
        r = self._courant()
        if r:
            d = DialogueSaisieFractionne(self, self.athlete_id, realise=r)
            if d.exec():
                self.actualiser()

    def _supprimer(self):
        r = self._courant()
        if r and QMessageBox.question(self, "Supprimer", f"Supprimer « {r['nom']} » du {r['date'][:10]} ?") \
                == QMessageBox.StandardButton.Yes:
            dfr.supprimer_realise(r["id"])
            self.actualiser()

    def showEvent(self, e):
        super().showEvent(e)
        if hasattr(self, "_realises"):
            self.actualiser()


# ======================================================================
# Onglet 4 — Progression
# ======================================================================

class ProgressionFractionne(_EcranAthlete):

    def __init__(self, athlete_id_initial=None):
        super().__init__("📈  Progression en fractionné",
                         "Chaque séance refaite au moins deux fois : vitesse moyenne des répétitions et % de VMA tenu, "
                         "séance après séance.", athlete_id_initial)
        ligne = QHBoxLayout()
        self.combo = QComboBox()
        self.combo.currentIndexChanged.connect(self._dessiner)
        ligne.addWidget(QLabel("Séance :"))
        ligne.addWidget(self.combo, 1)
        self.principal.addLayout(ligne)
        self.cadre_courbe = self._cadre_courbe("Vitesse moyenne des répétitions", "km/h, une valeur par séance faite.", 260)
        self.principal.addWidget(self.cadre_courbe)
        self.label = QLabel("")
        self.label.setWordWrap(True)
        self.principal.addWidget(self.label)
        self.table = _table(["Date", "Vitesse moyenne", "% VMA", "VMA de référence", "Verdict"], 120)
        self.principal.addWidget(self.table)
        self.principal.addStretch()
        self._prog = {}
        self._finaliser()

    def actualiser(self):
        self._prog = fr.progression(dfr.realises(self.athlete_id))
        actuel = self.combo.currentText()
        self.combo.blockSignals(True)
        self.combo.clear()
        for n in sorted(self._prog):
            self.combo.addItem(n)
        i = self.combo.findText(actuel)
        self.combo.setCurrentIndex(max(0, i))
        self.combo.blockSignals(False)
        self._dessiner()

    def _dessiner(self):
        pts = self._prog.get(self.combo.currentText(), [])
        courbe = self.cadre_courbe.courbe
        courbe.echelle_ajustee = True
        courbe.definir_series([{"nom": "Vitesse (km/h)", "couleur": "#42A5F5",
                                "valeurs": [(date.fromisoformat(p["date"][:10]).strftime("%d/%m/%y"), p["vitesse_kmh"])
                                            for p in pts]}] if pts else [])
        self.label.setText(fr.texte_progression(pts) if pts else
                           "Refais une même séance au moins deux fois pour voir ta progression.")
        t = self.table
        t.setRowCount(len(pts))
        for i, p in enumerate(reversed(pts)):
            for j, v in enumerate((date.fromisoformat(p["date"][:10]).strftime("%d/%m/%Y"), f"{_fr(p['vitesse_kmh'], 2)} km/h",
                                   f"{_fr(p['pct_vma'])} %", f"{_fr(p['vma_ref'])} km/h", p["verdict"])):
                t.setItem(i, j, QTableWidgetItem(v))
        t.resizeColumnsToContents()
        _ajuster_hauteur(t, 80, 500)

    def showEvent(self, e):
        super().showEvent(e)
        if hasattr(self, "_prog"):
            self.actualiser()


# ======================================================================
# Fenêtre
# ======================================================================

class FractionneFenetre(ConteneurOnglets):

    def __init__(self, athlete_id_initial=None):
        super().__init__(
            titre="Fractionné",
            onglets=[("📚 Bibliothèque", BibliothequeFractionne), ("⏲ Minuteur", MinuteurFractionne),
                     ("📝 Mes fractionnés", MesFractionnes), ("📈 Progression", ProgressionFractionne)],
            athlete_id_initial=athlete_id_initial,
        )
        self.bibliotheque, self.minuteur, self.mes, self.progression = self.ecrans
