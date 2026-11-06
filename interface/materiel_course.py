"""
Matériel pour une course (Trail Hub Center, étape 3.4, bloc 13) : le
matériel obligatoire d'une course comparé à ce que tu possèdes.

Deux onglets :
  🎒 Pour une course : la liste du règlement de la course (collée depuis le
     site officiel et lue automatiquement), ou à défaut le repère standard
     selon la distance et les conditions ; chaque ligne est comparée à ton
     équipement (✅ je l'ai, ⚠️ à vérifier, ❌ il me manque), avec le poids
     du sac, la liste de ce qui manque, les cases « dans le sac » et la
     checklist à imprimer.
  🧰 Mon équipement : ton matériel avec ce qu'un règlement contrôle
     (contenance des flasques, colonne d'eau de la veste, lumens, poids,
     contrôle des batteries).

À distinguer de l'écran « Matériel » du Suivi, qui suit l'usure des
chaussures au kilomètre : c'est la même table, vue sous un autre angle.
Aucune requête SQL ici : tout passe par noyau/donnees/equipement.py.
"""

import html
from datetime import date

from PySide6.QtCore import Qt, QDate, QLocale, QUrl
from PySide6.QtGui import QColor, QDesktopServices, QGuiApplication
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QDateEdit, QDialog, QDialogButtonBox, QDoubleSpinBox, QFileDialog,
    QFormLayout, QFrame, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton, QSpinBox, QTableWidget,
    QTableWidgetItem, QTextEdit, QVBoxLayout,
)

from noyau.donnees import equipement as deq
from noyau.materiel import comparaison as cmp
from noyau.materiel.equipements import (
    EQUIPEMENTS, FAMILLES, CARACTERISTIQUES, NIVEAUX, LIBELLE_NIVEAU, analyser_reglement, repere_standard,
    libelle_valeur,
)
from interface.conteneur_onglets import ConteneurOnglets
from interface.ecran_liste import configurer_table_redimensionnable, obtenir_style_ecran
from interface.forme_evolution import _EcranAthlete

MOIS_VERS_SAISON = {
    12: "Hiver", 1: "Hiver", 2: "Hiver",
    3: "Printemps", 4: "Printemps", 5: "Printemps",
    6: "Été", 7: "Été", 8: "Été",
    9: "Automne", 10: "Automne", 11: "Automne",
}
COULEUR_STATUT = {"ok": "#2E7D32", "verifier": "#E65100", "manque": "#C62828", "manuel": "#757575"}
FRANCAIS = QLocale(QLocale.Language.French, QLocale.Country.France)


def _fr(v, d=1):
    if v is None:
        return "—"
    t = f"{v:.{d}f}".replace(".", ",")
    return t[:-2] if t.endswith(",0") else t


def _bouton(texte, principal=False):
    b = QPushButton(texte)
    b.setObjectName("boutonPrincipal" if principal else "boutonSecondaire")
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    return b


def _table(colonnes, hauteur=320):
    t = QTableWidget(0, len(colonnes))
    t.setHorizontalHeaderLabels(colonnes)
    t.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    t.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    t.verticalHeader().setVisible(False)
    t.setMinimumHeight(hauteur)
    t.setWordWrap(True)
    configurer_table_redimensionnable(t)
    return t


def _cadre(titre):
    c = QFrame()
    c.setObjectName("carteForm")
    l = QVBoxLayout(c)
    t = QLabel(titre)
    t.setObjectName("titreCarte")
    l.addWidget(t)
    return c, l


def _combo_equipement(code=None, avec_aucun=True):
    c = QComboBox()
    if avec_aucun:
        c.addItem("— non reconnu —", None)
    for fam in FAMILLES:
        for e in EQUIPEMENTS.values():
            if e["famille"] == fam:
                c.addItem(f"{e['nom']}  ·  {fam}", e["code"])
    c.setCurrentIndex(max(0, c.findData(code)))
    return c


def _decimal(maxi, decimales=1):
    s = QDoubleSpinBox()
    s.setLocale(FRANCAIS)
    s.setRange(0, maxi)
    s.setDecimals(decimales)
    s.setSpecialValueText("—")
    return s


# ======================================================================
# Dialogue : un objet de mon équipement
# ======================================================================

class DialogueEquipement(QDialog):

    def __init__(self, parent=None, objet=None, code=None):
        super().__init__(parent)
        self.setWindowTitle("Mon matériel")
        self.setStyleSheet(obtenir_style_ecran())
        self.resize(560, 560)
        o = objet or {}
        car = o.get("caracteristiques") or {}
        lay = QVBoxLayout(self)
        form = QFormLayout()
        self.equipement = _combo_equipement(o.get("equipement") or code)
        self.nom = QLineEdit(o.get("nom") or (EQUIPEMENTS[code]["nom"] if code else ""))
        self.nom.setPlaceholderText("ex. Frontale 400 lumens, veste Gore-Tex…")
        self.quantite = QSpinBox()
        self.quantite.setRange(1, 20)
        self.quantite.setValue(int(o.get("quantite") or 1))
        self.poids = _decimal(10000, 0)
        self.poids.setSuffix(" g")
        if o.get("poids_g") is not None:
            self.poids.setValue(float(o["poids_g"]))
        self.label_carac = QLabel("Caractéristique")
        self.carac = _decimal(100000, 2)
        self.coutures = QCheckBox("Coutures étanches")
        self.capuche = QCheckBox("Capuche")
        self.coutures.setTristate(True)
        self.capuche.setTristate(True)
        for case, cle in ((self.coutures, "coutures_etanches"), (self.capuche, "capuche")):
            v = car.get(cle)
            case.setCheckState(Qt.CheckState.Checked if v is True else Qt.CheckState.Unchecked if v is False
                               else Qt.CheckState.PartiallyChecked)
        self._car = car
        self.controle = QDateEdit(QDate.currentDate())
        self.controle.setCalendarPopup(True)
        self.controle.setDisplayFormat("dd/MM/yyyy")
        self.avec_controle = QCheckBox("Batterie ou piles contrôlées le")
        if o.get("controle_le"):
            self.avec_controle.setChecked(True)
            self.controle.setDate(QDate.fromString(str(o["controle_le"])[:10], "yyyy-MM-dd"))
        ligne_controle = QHBoxLayout()
        ligne_controle.addWidget(self.avec_controle)
        ligne_controle.addWidget(self.controle)
        self.statut = QComboBox()
        self.statut.addItems(["Actif", "À surveiller", "Retiré"])
        self.statut.setCurrentText(o.get("statut") or "Actif")
        self.notes = QLineEdit(o.get("notes") or "")
        form.addRow("Équipement", self.equipement)
        form.addRow("Nom", self.nom)
        form.addRow("Quantité", self.quantite)
        form.addRow("Poids (l'unité)", self.poids)
        form.addRow(self.label_carac, self.carac)
        form.addRow("", self.coutures)
        form.addRow("", self.capuche)
        form.addRow("", ligne_controle)
        form.addRow("État", self.statut)
        form.addRow("Notes", self.notes)
        lay.addLayout(form)
        self.conseil = QLabel("")
        self.conseil.setObjectName("texteSecondaire")
        self.conseil.setWordWrap(True)
        lay.addWidget(self.conseil)
        aide = QLabel("Case grisée = « je ne sais pas » : la comparaison te demandera de vérifier.")
        aide.setObjectName("texteSecondaire")
        aide.setWordWrap(True)
        lay.addWidget(aide)
        boutons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        boutons.button(QDialogButtonBox.StandardButton.Save).setText("Enregistrer")
        boutons.button(QDialogButtonBox.StandardButton.Cancel).setText("Annuler")
        boutons.accepted.connect(self.accept)
        boutons.rejected.connect(self.reject)
        lay.addWidget(boutons)
        self.equipement.currentIndexChanged.connect(self._type_change)
        self._type_change()

    def _type_change(self):
        code = self.equipement.currentData()
        e = EQUIPEMENTS.get(code)
        carac = e["carac"] if e else None
        self.label_carac.setVisible(bool(carac))
        self.carac.setVisible(bool(carac))
        if carac:
            lib, unite, _c = CARACTERISTIQUES[carac]
            self.label_carac.setText(lib + (" (l'unité)" if CARACTERISTIQUES[carac][2] else ""))
            self.carac.setSuffix(" " + unite)
            self.carac.setDecimals(2 if unite == "L" else 0)
            v = self._car.get(carac)
            self.carac.setValue(float(v) if v not in (None, "") else 0)
        controle = code in cmp.A_CONTROLER
        self.avec_controle.setVisible(controle)
        self.controle.setVisible(controle)
        veste = code == "veste_impermeable"
        self.coutures.setVisible(veste)
        self.capuche.setVisible(veste)
        self.conseil.setText(e["conseil"] if e else "Relie-le à un équipement pour qu'il compte dans les comparaisons.")
        if not self.nom.text().strip() and e:
            self.nom.setText(e["nom"])

    def valeurs(self):
        code = self.equipement.currentData()
        car = {}
        e = EQUIPEMENTS.get(code)
        if e and e["carac"] and self.carac.value() > 0:
            car[e["carac"]] = self.carac.value()
        if code == "veste_impermeable":
            for case, cle in ((self.coutures, "coutures_etanches"), (self.capuche, "capuche")):
                st = case.checkState()
                if st != Qt.CheckState.PartiallyChecked:
                    car[cle] = st == Qt.CheckState.Checked
        return {"equipement": code, "nom": self.nom.text().strip(), "quantite": self.quantite.value(),
                "poids_g": self.poids.value() or None, "caracteristiques": car,
                "controle_le": self.controle.date().toString("yyyy-MM-dd") if self.avec_controle.isChecked() else None,
                "statut": self.statut.currentText(), "notes": self.notes.text().strip()}

    def accept(self):
        if not self.nom.text().strip():
            QMessageBox.warning(self, "Mon matériel", "Donne un nom à ce matériel.")
            return
        super().accept()


# ======================================================================
# Dialogue : la liste du règlement d'une course
# ======================================================================

class DialogueReglement(QDialog):
    """Colle la liste du règlement : le logiciel la lit, tu corriges, tu enregistres."""

    def __init__(self, parent, nom_course, lignes=None):
        super().__init__(parent)
        self.setWindowTitle(f"Règlement – {nom_course}")
        self.setStyleSheet(obtenir_style_ecran())
        self.resize(1100, 780)
        lay = QVBoxLayout(self)
        intro = QLabel("Copie la liste du matériel depuis le règlement ou la page officielle de la course et colle-la "
                       "ci-dessous, puis « Lire la liste ». Les rubriques « Matériel conseillé » ou « Selon la météo » "
                       "sont reconnues. Vérifie chaque ligne avant d'enregistrer : le règlement officiel fait foi.")
        intro.setWordWrap(True)
        intro.setObjectName("texteSecondaire")
        lay.addWidget(intro)
        self.texte = QTextEdit()
        self.texte.setPlaceholderText("Matériel obligatoire :\n- Réserve d'eau de 1,5 L minimum\n- Deux lampes frontales "
                                      "avec piles de rechange\n- Couverture de survie\n…\nMatériel conseillé :\n- Bâtons")
        self.texte.setMaximumHeight(200)
        lay.addWidget(self.texte)
        b = QHBoxLayout()
        lire = _bouton("🔎 Lire la liste", True)
        lire.clicked.connect(self._lire)
        ajout = _bouton("➕ Ajouter une ligne")
        ajout.clicked.connect(lambda: self._ajouter({"libelle": "", "equipement": None, "niveau": "obligatoire",
                                                     "quantite": 1, "valeur_min": None}))
        suppr = _bouton("🗑 Retirer la ligne")
        suppr.clicked.connect(self._retirer)
        b.addWidget(lire)
        b.addWidget(ajout)
        b.addWidget(suppr)
        b.addStretch()
        lay.addLayout(b)
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["Ligne du règlement", "Équipement reconnu", "Niveau", "Quantité",
                                              "Exigence chiffrée"])
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        for col, larg in enumerate((420, 270, 150, 90, 140)):
            self.table.setColumnWidth(col, larg)
        lay.addWidget(self.table, 1)
        self.etat = QLabel("")
        self.etat.setWordWrap(True)
        lay.addWidget(self.etat)
        boutons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        boutons.button(QDialogButtonBox.StandardButton.Save).setText("Enregistrer la liste")
        boutons.button(QDialogButtonBox.StandardButton.Cancel).setText("Annuler")
        boutons.accepted.connect(self.accept)
        boutons.rejected.connect(self.reject)
        lay.addWidget(boutons)
        for l in lignes or []:
            self._ajouter(l)

    def _ajouter(self, l):
        r = self.table.rowCount()
        self.table.insertRow(r)
        self.table.setItem(r, 0, QTableWidgetItem(l.get("libelle") or ""))
        combo = _combo_equipement(l.get("equipement"))
        niveau = QComboBox()
        for code, lib in NIVEAUX:
            niveau.addItem(lib, code)
        niveau.setCurrentIndex(max(0, niveau.findData(l.get("niveau") or "obligatoire")))
        qte = QSpinBox()
        qte.setRange(1, 20)
        qte.setValue(int(l.get("quantite") or 1))
        val = _decimal(100000, 2)
        if l.get("valeur_min"):
            val.setValue(float(l["valeur_min"]))

        def unite(_i=None, c=combo, v=val):
            e = EQUIPEMENTS.get(c.currentData())
            carac = e["carac"] if e else None
            v.setEnabled(bool(carac))
            v.setSuffix(" " + CARACTERISTIQUES[carac][1] if carac else "")
            v.setDecimals(2 if carac == "volume_l" else 0)
        combo.currentIndexChanged.connect(unite)
        unite()
        for col, w in ((1, combo), (2, niveau), (3, qte), (4, val)):
            self.table.setCellWidget(r, col, w)
        self.table.setRowHeight(r, 40)

    def _retirer(self):
        r = self.table.currentRow()
        if r >= 0:
            self.table.removeRow(r)

    def _lire(self):
        lignes = analyser_reglement(self.texte.toPlainText())
        if not lignes:
            self.etat.setText("Rien à lire : colle d'abord la liste du règlement.")
            return
        self.table.setRowCount(0)
        for l in lignes:
            self._ajouter(l)
        inconnues = sum(1 for l in lignes if not l["equipement"])
        self.etat.setText(f"{len(lignes)} lignes lues, {len(lignes) - inconnues} reconnues."
                          + (f" {inconnues} non reconnues : choisis l'équipement ou laisse-les à cocher toi-même."
                             if inconnues else ""))

    def lignes(self):
        res = []
        for r in range(self.table.rowCount()):
            it = self.table.item(r, 0)
            lib = it.text().strip() if it else ""
            if not lib:
                continue
            combo, niveau, qte, val = (self.table.cellWidget(r, c) for c in (1, 2, 3, 4))
            res.append({"libelle": lib, "equipement": combo.currentData(), "niveau": niveau.currentData(),
                        "quantite": qte.value(), "valeur_min": val.value() if val.isEnabled() and val.value() else None})
        return res


# ======================================================================
# Onglet 1 — Pour une course
# ======================================================================

class MaterielPourCourse(_EcranAthlete):
    COLONNES = ["Dans le sac", "État", "Matériel demandé", "Niveau", "Exigence", "Mon matériel", "Détail"]

    def __init__(self, athlete_id_initial=None):
        super().__init__("🎒  Matériel pour une course",
                         "Le matériel obligatoire de ta course comparé à ce que tu possèdes. Colle la liste du "
                         "règlement officiel : elle est lue automatiquement. Sans règlement, un repère selon la "
                         "distance et les conditions sert de base. Chaque organisateur fixe sa liste : le règlement "
                         "officiel fait foi.", athlete_id_initial)
        self._courses, self._liste, self._resultat, self._course = [], [], None, None
        self._bloque = False
        cadre, lc = _cadre("Course")
        ligne = QHBoxLayout()
        self.combo_course = QComboBox()
        self.combo_course.currentIndexChanged.connect(self._course_changee)
        ligne.addWidget(QLabel("Course :"))
        ligne.addWidget(self.combo_course, 1)
        lc.addLayout(ligne)
        ligne = QHBoxLayout()
        self.distance = QDoubleSpinBox()
        self.distance.setLocale(FRANCAIS)
        self.distance.setRange(0, 400)
        self.distance.setDecimals(1)
        self.distance.setValue(30)
        self.distance.setSuffix(" km")
        self.deniv = QSpinBox()
        self.deniv.setRange(0, 15000)
        self.deniv.setSingleStep(100)
        self.deniv.setValue(1200)
        self.deniv.setSuffix(" m D+")
        self.saison = QComboBox()
        self.saison.addItems(["Printemps", "Été", "Automne", "Hiver"])
        self.nuit = QCheckBox("Portion de nuit")
        self.altitude = QCheckBox("Haute montagne")
        for w in (self.distance, self.deniv):
            w.valueChanged.connect(self._recalculer)
        self.saison.currentIndexChanged.connect(self._recalculer)
        self.nuit.toggled.connect(self._recalculer)
        self.altitude.toggled.connect(self._recalculer)
        for w in (self.distance, self.deniv, self.saison, self.nuit, self.altitude):
            ligne.addWidget(w)
        ligne.addStretch()
        self.ligne_repere = ligne
        lc.addLayout(ligne)
        self.label_source = QLabel("")
        self.label_source.setWordWrap(True)
        self.label_source.setTextFormat(Qt.TextFormat.RichText)
        lc.addWidget(self.label_source)
        b = QHBoxLayout()
        self.b_coller = _bouton("📋 Coller le règlement…", True)
        self.b_coller.clicked.connect(self._coller)
        self.b_modifier = _bouton("✏️ Modifier la liste")
        self.b_modifier.clicked.connect(self._modifier_liste)
        self.b_lien = _bouton("🔗 Ouvrir la page de la course")
        self.b_lien.clicked.connect(self._ouvrir_lien)
        b_manque = _bouton("🛒 Ce qui manque")
        b_manque.clicked.connect(self._liste_de_courses)
        b_pdf = _bouton("🖨 Checklist PDF")
        b_pdf.clicked.connect(self._pdf)
        self.b_vider = _bouton("↺ Vider le sac")
        self.b_vider.clicked.connect(self._vider)
        for w in (self.b_coller, self.b_modifier, self.b_lien, b_manque, b_pdf, self.b_vider):
            b.addWidget(w)
        b.addStretch()
        lc.addLayout(b)
        self.principal.addWidget(cadre)

        ligne = QHBoxLayout()
        ligne.setSpacing(15)
        self.cartes = {}
        for cle, titre in (("pret", "Obligatoire prêt"), ("manque", "Il me manque"), ("verifier", "À vérifier"),
                           ("poids", "Poids du sac obligatoire"), ("sac", "Déjà dans le sac")):
            self.cartes[cle] = self._carte(titre)
            ligne.addWidget(self.cartes[cle], 1)
        self.principal.addLayout(ligne)
        self.resume = QLabel("")
        self.resume.setWordWrap(True)
        self.principal.addWidget(self.resume)
        self.table = _table(self.COLONNES, 520)
        self.table.cellDoubleClicked.connect(self._double_clic)
        self.table.itemChanged.connect(self._case_sac)
        self.principal.addWidget(self.table)
        aide = QLabel("Double-clique sur une ligne « Il me manque » ou « À vérifier » pour ajouter ou compléter ce "
                      "matériel dans « Mon équipement ». Les cases « Dans le sac » servent la veille de la course "
                      "(liste du règlement enregistrée seulement).")
        aide.setObjectName("texteSecondaire")
        aide.setWordWrap(True)
        self.principal.addWidget(aide)
        self.principal.addStretch()
        self._finaliser()

    # ------------------------------------------------------------
    def preselectionner(self, course):
        """course : dict {id?, nom, date, distance_km, denivele_m, type_terrain} (écran Courses à venir)."""
        i = self.combo_course.findData(course.get("id")) if course.get("id") is not None else -1
        if i >= 0:
            self.combo_course.setCurrentIndex(i)
        else:
            self.combo_course.setCurrentIndex(0)
            self._appliquer_conditions(course)
            self._recalculer()

    def actualiser(self):
        a = self.athlete_id
        actuel = self.combo_course.currentData()
        self._courses = deq.courses(a)
        self.combo_course.blockSignals(True)
        self.combo_course.clear()
        self.combo_course.addItem("— Sans course : repère selon la distance —", None)
        aujourdhui = date.today().isoformat()
        for c in self._courses:
            futur = not c["date"] or str(c["date"])[:10] >= aujourdhui
            self.combo_course.addItem(("" if futur else "(passée) ") + f"{c['nom']}"
                                      + (f" — {str(c['date'])[:10]}" if c["date"] else "")
                                      + (f" · {_fr(c['distance_km'])} km" if c["distance_km"] else "")
                                      + (" · règlement ✓" if c["nb_lignes"] else ""), c["id"])
        i = self.combo_course.findData(actuel)
        if i < 0 and actuel is None:
            futurs = [k + 1 for k, c in enumerate(self._courses) if not c["date"] or str(c["date"])[:10] >= aujourdhui]
            i = futurs[0] if futurs else 0
        self.combo_course.setCurrentIndex(max(0, i))
        self.combo_course.blockSignals(False)
        self._course_changee()

    def _course_changee(self):
        cid = self.combo_course.currentData()
        self._course = next((c for c in self._courses if c["id"] == cid), None)
        if self._course:
            self._appliquer_conditions(self._course)
        self._recalculer()

    def _appliquer_conditions(self, c):
        self._bloque = True
        if c.get("distance_km") is not None:
            self.distance.setValue(float(c["distance_km"]))
        if c.get("denivele_m") is not None:
            self.deniv.setValue(int(c["denivele_m"]))
        nom, terrain = (c.get("nom") or "").lower(), (c.get("type_terrain") or "").lower()
        self.nuit.setChecked("nocturne" in nom or "nuit" in nom or (c.get("distance_km") or 0) >= 80)
        self.altitude.setChecked((c.get("denivele_m") or 0) >= 3000 or "haute montagne" in terrain)
        d = str(c.get("date") or "")
        if len(d) >= 7 and d[5:7].isdigit():
            self.saison.setCurrentText(MOIS_VERS_SAISON.get(int(d[5:7]), "Printemps"))
        self._bloque = False

    def _recalculer(self, *_):
        if self._bloque:
            return
        c = self._course
        officielle = deq.liste_de_la_course(c["id"]) if c else []
        self._officielle = bool(officielle)
        if officielle:
            self._liste = officielle
            verif, source = deq.infos_reglement(c["id"])
            self.label_source.setText(f"<b>Liste du règlement</b> ({html.escape(source or 'saisie')}, enregistrée le "
                                      f"{date.fromisoformat(verif[:10]).strftime('%d/%m/%Y') if verif else '?'}) : "
                                      f"{len(officielle)} lignes. Revérifie-la quelques jours avant la course : "
                                      "les organisateurs l'adaptent à la météo.")
        else:
            self._liste = repere_standard(self.distance.value(), self.deniv.value(), self.nuit.isChecked(),
                                          self.altitude.isChecked(), self.saison.currentText())
            self.label_source.setText("<b>Repère standard</b> selon la distance, le D+ et les conditions (pas encore de "
                                      "règlement enregistré" + (" pour cette course" if c else "") + "). "
                                      + ("Colle la liste du règlement officiel pour une comparaison exacte."
                                         if c else "Choisis une course pour enregistrer son règlement."))
        for w in (self.distance, self.deniv, self.saison, self.nuit, self.altitude):
            w.setEnabled(not officielle)
        self.b_coller.setEnabled(c is not None)
        self.b_modifier.setEnabled(c is not None)
        self.b_lien.setEnabled(bool(c and c.get("lien")))
        self.b_vider.setEnabled(bool(officielle))
        from noyau.nutrition.tolerances import produits_course_de
        self._resultat = cmp.comparer(self._liste, deq.equipements(self.athlete_id), c.get("date") if c else None,
                                      produits_course_de(self.athlete_id))
        self._afficher()

    def _afficher(self):
        r = self._resultat
        oblig = [l for l in r["lignes"] if l["niveau"] == "obligatoire"]
        nb = lambda st: sum(1 for l in oblig if l["statut"] == st)
        c = self.cartes
        c["pret"].valeur.setText(f"{r['pret_pct']} %" if r["pret_pct"] is not None else "—")
        c["pret"].detail.setText(f"{nb('ok')} sur {len(oblig)} éléments obligatoires")
        c["manque"].valeur.setText(str(len(r["manquants"])))
        meteo = sum(1 for l in r["manquants"] if l["niveau"] == "meteo")
        c["manque"].detail.setText(f"dont {meteo} selon la météo" if meteo else "matériel obligatoire")
        c["verifier"].valeur.setText(str(len(r["a_verifier"])))
        c["verifier"].detail.setText("caractéristique, état ou batterie à contrôler")
        c["poids"].valeur.setText(f"{_fr(r['poids_g'] / 1000, 2)} kg" if r["poids_g"] else "—")
        c["poids"].detail.setText(f"{r['poids_incomplet']} objet(s) sans poids renseigné" if r["poids_incomplet"]
                                  else "d'après les poids de ton équipement")
        dans = sum(1 for l in r["lignes"] if l.get("dans_le_sac"))
        c["sac"].valeur.setText(f"{dans} / {len(r['lignes'])}" if self._officielle else "—")
        c["sac"].detail.setText("cases cochées" if self._officielle else "avec la liste du règlement")
        self.resume.setText(r["resume"])
        t = self.table
        t.blockSignals(True)
        t.setRowCount(len(r["lignes"]))
        for i, l in enumerate(r["lignes"]):
            case = QTableWidgetItem("")
            if self._officielle:
                case.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
                case.setCheckState(Qt.CheckState.Checked if l.get("dans_le_sac") else Qt.CheckState.Unchecked)
            else:
                case.setFlags(Qt.ItemFlag.ItemIsEnabled)
            case.setData(Qt.ItemDataRole.UserRole, l.get("id"))
            t.setItem(i, 0, case)
            st = QTableWidgetItem(f"{cmp.ICONE_STATUT[l['statut']]} {cmp.LIBELLE_STATUT[l['statut']]}")
            st.setForeground(QColor(COULEUR_STATUT[l["statut"]]))
            t.setItem(i, 1, st)
            code = l.get("equipement")
            exig = libelle_valeur(code, l.get("valeur_min"))
            if (l.get("quantite") or 1) > 1:
                exig = (f"× {l['quantite']}" + (f", {exig}" if exig else ""))
            vals = [l["libelle"], LIBELLE_NIVEAU.get(l["niveau"], l["niveau"]), exig,
                    ", ".join(o for o in l["objets"] if o), l["detail"]]
            for j, v in enumerate(vals):
                it = QTableWidgetItem(v)
                if j == 0 and l.get("precision"):
                    it.setToolTip(l["precision"])
                t.setItem(i, j + 2, it)
        t.resizeColumnsToContents()
        for col, maxi in ((2, 330), (5, 240), (6, 360)):
            if t.columnWidth(col) > maxi:
                t.setColumnWidth(col, maxi)
        t.resizeRowsToContents()
        # tout le tableau visible d'un coup : c'est la page entière qui défile
        hauteur = t.horizontalHeader().height() + sum(t.rowHeight(k) for k in range(t.rowCount())) + 6
        t.setMinimumHeight(max(200, hauteur))
        t.setMaximumHeight(max(200, hauteur))
        t.blockSignals(False)

    # --- actions -----------------------------------------------------
    def _case_sac(self, item):
        if item.column() != 0 or not self._officielle:
            return
        lid = item.data(Qt.ItemDataRole.UserRole)
        if lid is not None:
            deq.cocher_sac(lid, item.checkState() == Qt.CheckState.Checked)
            self._recalculer()

    def _vider(self):
        if self._course and QMessageBox.question(self, "Vider le sac", "Décocher toutes les cases « Dans le sac » ?") \
                == QMessageBox.StandardButton.Yes:
            deq.vider_sac(self._course["id"])
            self._recalculer()

    def _coller(self):
        self._dialogue_liste([])

    def _modifier_liste(self):
        self._dialogue_liste(self._liste)

    def _dialogue_liste(self, lignes):
        if not self._course:
            QMessageBox.information(self, "Règlement", "Choisis d'abord une course enregistrée (écran Courses à venir).")
            return
        d = DialogueReglement(self, self._course["nom"], lignes)
        if d.exec():
            try:
                deq.enregistrer_liste(self.athlete_id, self._course["id"], d.lignes(),
                                      "Règlement officiel" if d.texte.toPlainText().strip() or self._officielle
                                      else "Repère modifié")
            except deq.ErreurEquipement as e:
                QMessageBox.warning(self, "Règlement", str(e))
            self.actualiser()

    def _ouvrir_lien(self):
        lien = (self._course or {}).get("lien")
        if lien:
            QDesktopServices.openUrl(QUrl(lien if "://" in lien else "https://" + lien))

    def _liste_de_courses(self):
        texte = cmp.texte_liste_de_courses(self._resultat, (self._course or {}).get("nom", ""))
        try:
            QGuiApplication.clipboard().setText(texte)
            copie = "\n\n(Copié dans le presse-papiers.)"
        except Exception:
            copie = ""
        QMessageBox.information(self, "Ce qui manque", texte + copie)

    def _double_clic(self, ligne, _col):
        if not self._resultat or ligne >= len(self._resultat["lignes"]):
            return
        l = self._resultat["lignes"][ligne]
        code = l.get("equipement")
        if not code:
            return
        objets = [o for o in deq.equipements(self.athlete_id) if o.get("equipement") == code]
        d = DialogueEquipement(self, objets[0] if objets and l["statut"] == "verifier" else None, code)
        if d.exec():
            try:
                if objets and l["statut"] == "verifier":
                    deq.modifier_equipement(objets[0]["id"], d.valeurs())
                else:
                    deq.creer_equipement(self.athlete_id, d.valeurs())
            except deq.ErreurEquipement as e:
                QMessageBox.warning(self, "Mon matériel", str(e))
            self._recalculer()

    def _pdf(self):
        nom = (self._course or {}).get("nom") or f"Course de {_fr(self.distance.value())} km"
        chemin, _ = QFileDialog.getSaveFileName(self, "Checklist du sac", f"Checklist sac - {nom}.pdf", "PDF (*.pdf)")
        if not chemin:
            return
        from interface.roadbook_fiche import rendre_checklist_materiel_pdf
        rendre_checklist_materiel_pdf(chemin, nom, (self._course or {}).get("date"), self._resultat,
                                      "Liste du règlement" if self._officielle else "Repère standard")
        QDesktopServices.openUrl(QUrl.fromLocalFile(chemin))

    def showEvent(self, e):
        super().showEvent(e)
        if hasattr(self, "_resultat") and self._resultat is not None:
            self._recalculer()


# ======================================================================
# Onglet 2 — Mon équipement
# ======================================================================

class MonEquipement(_EcranAthlete):
    COLONNES = ["Équipement", "Nom", "Quantité", "Poids", "Caractéristiques", "Batterie contrôlée", "État"]

    def __init__(self, athlete_id_initial=None):
        super().__init__("🧰  Mon équipement",
                         "Ton matériel avec ce qu'un règlement contrôle : contenance des flasques, colonne d'eau de la "
                         "veste, puissance de la frontale, poids, date de contrôle des batteries. Les chaussures et sacs "
                         "de l'écran Matériel apparaissent aussi.", athlete_id_initial)
        b = QHBoxLayout()
        for texte, f, principal in (("➕ Ajouter", self._ajouter, True), ("✏️ Modifier", self._modifier, False),
                                    ("🔗 Reconnaître d'après les noms", self._relier, False),
                                    ("🔋 Batteries contrôlées aujourd'hui", self._controle, False),
                                    ("🗑 Supprimer", self._supprimer, False)):
            w = _bouton(texte, principal)
            w.clicked.connect(f)
            b.addWidget(w)
        b.addStretch()
        self.principal.addLayout(b)
        self.table = _table(self.COLONNES, 520)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.doubleClicked.connect(lambda _i: self._modifier())
        self.principal.addWidget(self.table)
        self.label = QLabel("")
        self.label.setObjectName("texteSecondaire")
        self.label.setWordWrap(True)
        self.principal.addWidget(self.label)
        self.principal.addStretch()
        self._objets = []
        self._finaliser()

    def actualiser(self):
        self._objets = deq.equipements(self.athlete_id, avec_retires=True)
        t = self.table
        t.setRowCount(len(self._objets))
        for i, o in enumerate(self._objets):
            e = EQUIPEMENTS.get(o.get("equipement"))
            car = o.get("caracteristiques") or {}
            morceaux = []
            if e and e["carac"] and car.get(e["carac"]) is not None:
                morceaux.append(libelle_valeur(e["code"], float(car[e["carac"]])))
            for cle, lib in (("coutures_etanches", "coutures étanches"), ("capuche", "capuche")):
                if cle in car:
                    morceaux.append(("" if car[cle] else "sans ") + lib)
            vals = [f"{e['nom']} · {e['famille']}" if e else f"— ({o.get('type') or 'non reconnu'})", o["nom"],
                    str(o.get("quantite") or 1), f"{_fr(o['poids_g'], 0)} g" if o.get("poids_g") else "—",
                    ", ".join(morceaux),
                    date.fromisoformat(str(o["controle_le"])[:10]).strftime("%d/%m/%Y") if o.get("controle_le") else "",
                    o.get("statut") or "Actif"]
            for j, v in enumerate(vals):
                it = QTableWidgetItem(v)
                if not e and j == 0:
                    it.setForeground(QColor("#757575"))
                t.setItem(i, j, it)
        t.resizeColumnsToContents()
        relies = [o for o in self._objets if o.get("equipement") and (o.get("statut") or "") != "Retiré"]
        poids = sum((o.get("poids_g") or 0) * (o.get("quantite") or 1) for o in relies)
        self.label.setText(f"{len(relies)} objets reconnus comme équipement de course"
                           + (f", {_fr(poids / 1000, 2)} kg au total." if poids else ".")
                           + " Un objet « non reconnu » ne compte pas dans les comparaisons : modifie-le pour choisir "
                             "son équipement.")

    def _selection(self):
        lignes = sorted({i.row() for i in self.table.selectedIndexes()})
        return [self._objets[l] for l in lignes if l < len(self._objets)]

    def _ajouter(self):
        if self.athlete_id is None:
            QMessageBox.information(self, "Mon matériel", "Choisis d'abord un athlète en haut de l'écran.")
            return
        d = DialogueEquipement(self)
        if d.exec():
            try:
                deq.creer_equipement(self.athlete_id, d.valeurs())
            except deq.ErreurEquipement as e:
                QMessageBox.warning(self, "Mon matériel", str(e))
            self.actualiser()

    def _modifier(self):
        sel = self._selection()
        if not sel:
            return
        d = DialogueEquipement(self, sel[0])
        if d.exec():
            try:
                deq.modifier_equipement(sel[0]["id"], d.valeurs())
            except deq.ErreurEquipement as e:
                QMessageBox.warning(self, "Mon matériel", str(e))
            self.actualiser()

    def _relier(self):
        n = deq.relier_automatiquement(self.athlete_id)
        self.actualiser()
        QMessageBox.information(self, "Mon matériel", f"{n} objet(s) reconnu(s) d'après leur nom." if n else
                                "Aucun nouvel objet reconnu : modifie-les un par un pour choisir leur équipement.")

    def _controle(self):
        sel = self._selection()
        if sel:
            deq.batteries_controlees([o["id"] for o in sel])
            self.actualiser()

    def _supprimer(self):
        sel = self._selection()
        if not sel:
            return
        noms = ", ".join(o["nom"] for o in sel)
        if QMessageBox.question(self, "Supprimer", f"Supprimer {noms} ? Il disparaît aussi de l'écran Matériel.") \
                == QMessageBox.StandardButton.Yes:
            for o in sel:
                deq.supprimer_equipement(o["id"])
            self.actualiser()

    def showEvent(self, e):
        super().showEvent(e)
        if self._objets is not None and hasattr(self, "table"):
            self.actualiser()


# ======================================================================
# Fenêtre
# ======================================================================

class MaterielCourse(ConteneurOnglets):

    def __init__(self, athlete_id_initial=None, course_preselectionnee=None):
        """course_preselectionnee : dict optionnel {id, nom, distance_km, denivele_m, type_terrain, date}
        pour ouvrir l'écran directement sur une course de l'onglet Courses à venir."""
        super().__init__(
            titre="Matériel pour une course",
            onglets=[("🎒 Pour une course", MaterielPourCourse), ("🧰 Mon équipement", MonEquipement)],
            athlete_id_initial=athlete_id_initial,
        )
        self.pour_course, self.mon_equipement = self.ecrans
        if course_preselectionnee:
            self.pour_course.preselectionner(course_preselectionnee)
