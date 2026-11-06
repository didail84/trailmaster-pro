"""
Nutrition de course (Trail Hub Center, étape 3.3, bloc 12) : quatre onglets
de l'écran Alimentation.

  🏃 Mes produits de course : gels, barres, boissons, fait maison et
     génériques, avec leur Nutri-Score et ta tolérance ; ajout à la main
     ou par code-barres (Open Food Facts).
  🥣 Fait maison : recettes de barres, gels et boissons, calculées
     (glucides par portion, sodium, glucose:fructose, Nutri-Score, coût).
  ⚖️ Comparatif : 2 à 4 produits côte à côte.
  🩺 Tolérances et besoins : essais notés, verdict par produit, apport
     maximal toléré, besoins par heure et menu avec tes produits.

Aucune requête SQL ici : tout passe par noyau/donnees/nutrition_course.py
et les calculs par noyau/nutrition/.
"""

import html
from datetime import date

from PySide6.QtCore import Qt, QDate, QLocale, QRectF, Signal
from PySide6.QtGui import QColor, QPainter, QFont
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QDateEdit, QDialog, QDialogButtonBox, QDoubleSpinBox, QFormLayout,
    QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMessageBox, QPushButton,
    QSpinBox, QTableWidget, QTableWidgetItem, QTextEdit, QVBoxLayout, QWidget,
)

from noyau.donnees import nutrition_course as dnut
from noyau.nutrition import catalogue as cat, comparatif as cmp, nutriscore as ns, recettes as rc
from noyau.nutrition import tolerances as tol
from noyau.nutrition.ingredients import INGREDIENTS, MODELES, CATEGORIES_RECETTE
from noyau.course import ravitaillement as rav
from interface.ecran_liste import configurer_table_redimensionnable, obtenir_style_ecran
from interface.forme_evolution import _EcranAthlete


def _fr(v, d=0):
    if v is None:
        return "—"
    return f"{v:.{d}f}".replace(".", ",")


def _texte_couleur(fond):
    return "#111111" if fond in (ns.COULEURS["B"], ns.COULEURS["C"]) else "#FFFFFF"


class PastilleNutriScore(QWidget):
    """Lettre du Nutri-Score sur sa couleur (ou un tiret gris)."""

    def __init__(self, taille=30):
        super().__init__()
        self.lettre = None
        self.setFixedSize(taille, taille)

    def definir(self, lettre):
        self.lettre = lettre
        self.setToolTip(f"Nutri-Score {lettre}" if lettre else "Nutri-Score non calculé")
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        fond = ns.COULEURS.get(self.lettre, "#9E9E9E")
        p.setBrush(QColor(fond))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(QRectF(0, 0, self.width(), self.height()), 7, 7)
        p.setPen(QColor(_texte_couleur(fond)))
        f = QFont()
        f.setBold(True)
        f.setPixelSize(int(self.height() * 0.6))
        p.setFont(f)
        p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self.lettre or "–")


def _poser_nutriscore(table, ligne, colonne, lettre, texte=None):
    """Pastille de couleur dans une cellule (la feuille de style des tableaux ignore la couleur de fond
    d'une cellule), avec le texte à côté si besoin (« D (étiquette : C) »)."""
    it = QTableWidgetItem("")
    it.setData(Qt.ItemDataRole.UserRole + 1, lettre)
    table.setItem(ligne, colonne, it)
    boite = QWidget()
    boite.setStyleSheet("background: transparent;")
    l = QHBoxLayout(boite)
    l.setContentsMargins(6, 2, 6, 2)
    l.setSpacing(6)
    p = PastilleNutriScore(22)
    p.definir(lettre)
    l.addWidget(p)
    if texte and texte != lettre:
        t = QLabel(texte)
        t.setStyleSheet("background: transparent;")
        l.addWidget(t)
    l.addStretch()
    table.setCellWidget(ligne, colonne, boite)


FRANCAIS = QLocale(QLocale.Language.French, QLocale.Country.France)


def _decimal(mini=0.0, maxi=10000.0, decimales=1):
    s = QDoubleSpinBox()
    s.setLocale(FRANCAIS)
    s.setRange(mini, maxi)
    s.setDecimals(decimales)
    return s


def _spin(maxi=10000.0, decimales=1, suffixe=""):
    s = QDoubleSpinBox()
    s.setLocale(FRANCAIS)
    s.setRange(-1, maxi)
    s.setDecimals(decimales)
    s.setSpecialValueText("—")        # -1 = non renseigné
    s.setValue(-1)
    if suffixe:
        s.setSuffix(" " + suffixe)
    return s


def _val(spin):
    return None if spin.value() < 0 else spin.value()


def _table(colonnes, hauteur=300):
    t = QTableWidget(0, len(colonnes))
    t.setHorizontalHeaderLabels(colonnes)
    t.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    t.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    t.verticalHeader().setVisible(False)
    t.setMinimumHeight(hauteur)
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


def _bouton(texte, principal=False):
    b = QPushButton(texte)
    b.setObjectName("boutonPrincipal" if principal else "boutonSecondaire")
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    return b


def _tous_les_produits(athlete_id, avec_generiques=True):
    mes = dnut.produits(athlete_id)
    deja = {p["nom"] for p in mes if p.get("source") == "Générique"}
    gen = [dict(g) for g in cat.GENERIQUES if g["nom"] not in deja] if avec_generiques else []
    return mes + gen


def _bilan(athlete_id):
    ps = dnut.produits(athlete_id)
    return tol.bilan(ps, dnut.essais(athlete_id))


class _Onglet(_EcranAthlete):
    """Un onglet de la nutrition de course : se met à jour quand on y revient."""

    def showEvent(self, e):
        super().showEvent(e)
        if getattr(self, "_pret", False):
            self.actualiser()

    def _finaliser(self):
        super()._finaliser()
        self.setStyleSheet(self.styleSheet() + " #carteForm QCheckBox { background: transparent; }")
        self._pret = True


# ======================================================================
# Fiche produit (ajout / modification)
# ======================================================================

class DialogueProduit(QDialog):

    def __init__(self, parent=None, produit=None, titre="Produit de course"):
        super().__init__(parent)
        self.setWindowTitle(titre)
        self.setStyleSheet(obtenir_style_ecran())
        self.resize(620, 720)
        p = produit or {}
        lay = QVBoxLayout(self)
        form = QFormLayout()
        self.nom = QLineEdit(p.get("nom") or "")
        self.marque = QLineEdit(p.get("marque") or "")
        try:
            from interface.ecran_liste import ajouter_suggestions
            from noyau.donnees import annuaire as dan
            ajouter_suggestions(self.marque, lambda: dan.noms_de_marques("nutrition"))
        except Exception:                   # l'annuaire est facultatif pour saisir un produit
            pass
        self.categorie = QComboBox()
        self.categorie.addItems(cat.CATEGORIES)
        self.categorie.setCurrentText(p.get("categorie") or "Gel")
        self.type_ns = QComboBox()
        for code, lib in ns.TYPES:
            self.type_ns.addItem(lib, code)
        self.type_ns.setCurrentIndex(max(0, self.type_ns.findData(p.get("type_nutriscore") or "aliment")))
        self.portion = _spin(5000, 1)
        self.unite = QComboBox()
        self.unite.addItems(["g", "ml"])
        self.unite.setCurrentText(p.get("unite_portion") or "g")
        ligne_portion = QHBoxLayout()
        ligne_portion.addWidget(self.portion)
        ligne_portion.addWidget(self.unite)
        form.addRow("Nom", self.nom)
        form.addRow("Marque", self.marque)
        form.addRow("Catégorie", self.categorie)
        form.addRow("Type pour le Nutri-Score", self.type_ns)
        form.addRow("Portion", ligne_portion)
        note = QLabel("Valeurs pour 100 g, ou pour 100 ml pour une boisson telle que tu la bois (étiquette).")
        note.setObjectName("texteSecondaire")
        note.setWordWrap(True)
        form.addRow(note)
        self.champs = {}
        for cle, lib, suf in (("energie_kcal", "Énergie", "kcal"), ("glucides_g", "Glucides", "g"),
                              ("sucres_g", "dont sucres", "g"), ("fibres_g", "Fibres", "g"),
                              ("proteines_g", "Protéines", "g"), ("lipides_g", "Matières grasses", "g"),
                              ("ags_g", "dont acides gras saturés", "g"), ("sel_g", "Sel", "g")):
            s = _spin(1000, 2, suf)
            self.champs[cle] = s
            form.addRow(lib, s)
        self.fvl = QSpinBox()
        self.fvl.setRange(0, 100)
        self.fvl.setSuffix(" %")
        self.edulcorants = QCheckBox("Contient des édulcorants (boissons)")
        self.cafeine = QSpinBox()
        self.cafeine.setRange(0, 600)
        self.cafeine.setSuffix(" mg par portion")
        self.gf = QLineEdit(p.get("glucose_fructose") or "")
        self.gf.setPlaceholderText("ex. 1:0,8 ou 2:1 si l'étiquette l'indique")
        self.prix = _spin(100, 2, "€ par portion")
        self.code = QLineEdit(p.get("code_barre") or "")
        self.ns_off = QComboBox()
        self.ns_off.addItems(["—", "A", "B", "C", "D", "E"])
        self.ns_off.setCurrentText(p.get("nutriscore_officiel") or "—")
        self.notes = QLineEdit(p.get("notes") or "")
        form.addRow("Fruits, légumes, légumineuses", self.fvl)
        form.addRow("", self.edulcorants)
        form.addRow("Caféine", self.cafeine)
        form.addRow("Glucose:fructose", self.gf)
        form.addRow("Prix", self.prix)
        form.addRow("Code-barres", self.code)
        form.addRow("Nutri-Score de l'emballage", self.ns_off)
        form.addRow("Notes", self.notes)
        lay.addLayout(form)
        ligne = QHBoxLayout()
        self.pastille = PastilleNutriScore(34)
        self.label_ns = QLabel("")
        self.label_ns.setWordWrap(True)
        ligne.addWidget(self.pastille)
        ligne.addWidget(self.label_ns, 1)
        lay.addLayout(ligne)
        boutons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        boutons.button(QDialogButtonBox.StandardButton.Save).setText("Enregistrer")
        boutons.button(QDialogButtonBox.StandardButton.Cancel).setText("Annuler")
        boutons.accepted.connect(self.accept)
        boutons.rejected.connect(self.reject)
        lay.addWidget(boutons)
        # valeurs
        if p.get("portion") is not None:
            self.portion.setValue(p["portion"])
        for cle, s in self.champs.items():
            if p.get(cle) is not None:
                s.setValue(p[cle])
        self.fvl.setValue(int(p.get("fruits_legumes_pct") or 0))
        self.edulcorants.setChecked(bool(p.get("edulcorants")))
        self.cafeine.setValue(int(p.get("cafeine_mg") or 0))
        if p.get("prix_portion") is not None:
            self.prix.setValue(p["prix_portion"])
        for w in list(self.champs.values()) + [self.fvl]:
            w.valueChanged.connect(self._apercu)
        self.type_ns.currentIndexChanged.connect(self._apercu)
        self.edulcorants.toggled.connect(self._apercu)
        self._apercu()

    def valeurs(self):
        v = {"nom": self.nom.text().strip(), "marque": self.marque.text().strip() or None,
             "categorie": self.categorie.currentText(), "type_nutriscore": self.type_ns.currentData(),
             "portion": _val(self.portion), "unite_portion": self.unite.currentText(),
             "fruits_legumes_pct": self.fvl.value(), "edulcorants": 1 if self.edulcorants.isChecked() else 0,
             "cafeine_mg": self.cafeine.value(), "glucose_fructose": self.gf.text().strip() or None,
             "prix_portion": _val(self.prix), "code_barre": self.code.text().strip() or None,
             "nutriscore_officiel": None if self.ns_off.currentText() == "—" else self.ns_off.currentText(),
             "notes": self.notes.text().strip()}
        v.update({cle: _val(s) for cle, s in self.champs.items()})
        return v

    def _apercu(self):
        r = cat.nutriscore_de(self.valeurs())
        self.pastille.definir(r.get("lettre"))
        if r.get("lettre"):
            self.label_ns.setText(f"Nutri-Score calculé : {r['lettre']}"
                                  + (f" (score {r['score']})" if r.get("score") is not None else "")
                                  + (f". {r['note']}" if r.get("note") else "."))
        else:
            self.label_ns.setText(r.get("raison") or "")

    def accept(self):
        try:
            dnut._verifier(self.valeurs())
        except dnut.ErreurNutrition as e:
            QMessageBox.warning(self, "Produit", str(e))
            return
        super().accept()


class DialogueOpenFoodFacts(QDialog):
    """Cherche un produit par code-barres ou par nom ; renvoie le produit choisi (self.choix)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Chercher sur Open Food Facts")
        self.setStyleSheet(obtenir_style_ecran())
        self.resize(640, 520)
        self.choix = None
        self._resultats = []
        lay = QVBoxLayout(self)
        intro = QLabel("Tape le code-barres (8 à 14 chiffres sous le code-barres de l'emballage) ou la marque et le nom "
                       "du produit. Connexion Internet nécessaire ; seule ta recherche est envoyée à Open Food Facts, "
                       "base ouverte et collaborative : vérifie les valeurs avant d'enregistrer.")
        intro.setWordWrap(True)
        intro.setObjectName("texteSecondaire")
        lay.addWidget(intro)
        ligne = QHBoxLayout()
        self.saisie = QLineEdit()
        self.saisie.setPlaceholderText("3017620422003  ou  gel énergétique citron")
        b = _bouton("Chercher", True)
        b.clicked.connect(self._chercher)
        self.saisie.returnPressed.connect(self._chercher)
        ligne.addWidget(self.saisie, 1)
        ligne.addWidget(b)
        lay.addLayout(ligne)
        self.liste = QListWidget()
        self.liste.itemDoubleClicked.connect(lambda _i: self._utiliser())
        lay.addWidget(self.liste, 1)
        self.etat = QLabel("")
        self.etat.setWordWrap(True)
        lay.addWidget(self.etat)
        boutons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        boutons.button(QDialogButtonBox.StandardButton.Ok).setText("Utiliser ce produit")
        boutons.button(QDialogButtonBox.StandardButton.Cancel).setText("Annuler")
        boutons.accepted.connect(self._utiliser)
        boutons.rejected.connect(self.reject)
        lay.addWidget(boutons)

    def _chercher(self):
        from noyau.nutrition import open_food_facts as off
        texte = self.saisie.text().strip()
        self.liste.clear()
        self.etat.setText("Recherche…")
        self.repaint()
        try:
            if off.code_valide(texte):
                self._resultats = [off.chercher_code(texte)]
            else:
                self._resultats = off.chercher_nom(texte)
        except off.ErreurOpenFoodFacts as e:
            self._resultats = []
            self.etat.setText(str(e))
            return
        for r in self._resultats:
            g = cat.par_portion(r, "glucides_g")
            it = QListWidgetItem(f"{r['nom']}" + (f" — {r['marque']}" if r.get("marque") else "")
                                 + (f" · {_fr(g)} g de glucides par portion" if g else "")
                                 + (f" · Nutri-Score {r['nutriscore_officiel']}" if r.get("nutriscore_officiel") else ""))
            self.liste.addItem(it)
        self.etat.setText(f"{len(self._resultats)} produit(s) trouvé(s)." if self._resultats else "Aucun produit trouvé.")
        if self._resultats:
            self.liste.setCurrentRow(0)

    def _utiliser(self):
        i = self.liste.currentRow()
        if 0 <= i < len(self._resultats):
            self.choix = self._resultats[i]
            self.accept()


class DialogueEssai(QDialog):
    """Noter un essai de tolérance d'un produit."""

    def __init__(self, parent, produits, produit_id=None):
        super().__init__(parent)
        self.setWindowTitle("Noter un essai")
        self.setStyleSheet(obtenir_style_ecran())
        self.resize(560, 600)
        lay = QVBoxLayout(self)
        form = QFormLayout()
        self.produit = QComboBox()
        for p in produits:
            self.produit.addItem(p["nom"] + (f" ({p['marque']})" if p.get("marque") else ""), p["id"])
        if produit_id is not None:
            self.produit.setCurrentIndex(max(0, self.produit.findData(produit_id)))
        self.date = QDateEdit(QDate.currentDate())
        self.date.setCalendarPopup(True)
        self.date.setDisplayFormat("dd/MM/yyyy")
        self.contexte = QComboBox()
        self.contexte.addItems(dnut.CONTEXTES)
        self.duree = QSpinBox()
        self.duree.setRange(0, 3000)
        self.duree.setSuffix(" min")
        self.quantite = _decimal(0, 50, 1)
        self.quantite.setValue(1)
        self.quantite.setSuffix(" portion(s)")
        self.gh = _spin(150, 0, "g/h")
        self.temp = _spin(45, 0, "°C")
        self.ressenti = QComboBox()
        for code, lib in dnut.RESSENTIS:
            self.ressenti.addItem(lib, code)
        form.addRow("Produit", self.produit)
        form.addRow("Date", self.date)
        form.addRow("Contexte", self.contexte)
        form.addRow("Durée de la sortie", self.duree)
        form.addRow("Quantité prise", self.quantite)
        form.addRow("Glucides par heure (tout compris)", self.gh)
        form.addRow("Température", self.temp)
        form.addRow("Ressenti", self.ressenti)
        lay.addLayout(form)
        t = QLabel("Symptômes éventuels :")
        lay.addWidget(t)
        grille = QGridLayout()
        self.symptomes = []
        for i, s in enumerate(dnut.SYMPTOMES):
            c = QCheckBox(s)
            self.symptomes.append(c)
            grille.addWidget(c, i // 2, i % 2)
        lay.addLayout(grille)
        self.notes = QLineEdit()
        self.notes.setPlaceholderText("Notes (avec combien d'eau, à quel moment…)")
        lay.addWidget(self.notes)
        aide = QLabel("« Glucides par heure » : tout ce que tu as pris en glucides sur la sortie, divisé par sa durée. "
                      "C'est ce qui permet de suivre l'entraînement de ton ventre.")
        aide.setObjectName("texteSecondaire")
        aide.setWordWrap(True)
        lay.addWidget(aide)
        boutons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        boutons.button(QDialogButtonBox.StandardButton.Save).setText("Enregistrer l'essai")
        boutons.button(QDialogButtonBox.StandardButton.Cancel).setText("Annuler")
        boutons.accepted.connect(self.accept)
        boutons.rejected.connect(self.reject)
        lay.addWidget(boutons)

    def valeurs(self):
        return {"produit_id": self.produit.currentData(), "date": self.date.date().toString("yyyy-MM-dd"),
                "contexte": self.contexte.currentText(), "duree_min": self.duree.value() or None,
                "quantite": self.quantite.value() or None, "glucides_g_h": _val(self.gh), "temperature_c": _val(self.temp),
                "ressenti": self.ressenti.currentData(),
                "symptomes": [c.text() for c in self.symptomes if c.isChecked()], "notes": self.notes.text().strip()}


# ======================================================================
# Onglet 1 — Mes produits de course
# ======================================================================

class ProduitsCourse(_Onglet):
    COLONNES = ["★", "Produit", "Marque", "Catégorie", "Portion", "Glucides", "Sodium", "Caféine", "Prix",
                "Nutri-Score", "Ma tolérance"]
    comparer_demande = Signal(list)

    def __init__(self, athlete_id_initial=None):
        super().__init__("🏃  Mes produits de course",
                         "Tes gels, barres, boissons et recettes fait maison, avec ce qu'ils apportent par portion, "
                         "leur Nutri-Score et ce que ton ventre en pense. Les produits génériques donnent des valeurs "
                         "typiques : ajoute les tiens avec leur étiquette, ou par leur code-barres.",
                         athlete_id_initial)
        self._produits = []
        self._verdicts = {}
        filtres = QHBoxLayout()
        self.filtre = QComboBox()
        self.filtre.addItem("Toutes les catégories", None)
        for c in cat.CATEGORIES:
            self.filtre.addItem(c, c)
        self.filtre.currentIndexChanged.connect(self._remplir)
        self.avec_gen = QCheckBox("Afficher les produits génériques")
        self.avec_gen.setChecked(True)
        self.avec_gen.toggled.connect(self.actualiser)
        filtres.addWidget(self.filtre)
        filtres.addWidget(self.avec_gen)
        filtres.addStretch()
        self.principal.addLayout(filtres)

        boutons = QHBoxLayout()
        for texte, f, principal in (("➕ Ajouter un produit", self._ajouter, True),
                                    ("🔎 Chercher par code-barres ou nom…", self._open_food_facts, False),
                                    ("✏️ Modifier", self._modifier, False), ("★ Favori", self._favori, False),
                                    ("🩺 Noter un essai", self._essai, False),
                                    ("⚖️ Comparer la sélection", self._comparer, False),
                                    ("🗑 Supprimer", self._supprimer, False)):
            b = _bouton(texte, principal)
            b.clicked.connect(f)
            boutons.addWidget(b)
        boutons.addStretch()
        self.principal.addLayout(boutons)

        self.table = _table(self.COLONNES, 360)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.itemSelectionChanged.connect(self._detail)
        self.table.doubleClicked.connect(lambda _i: self._modifier())
        self.principal.addWidget(self.table)
        aide = QLabel("Sélectionne plusieurs produits (Ctrl ou ⌘ + clic) puis « Comparer la sélection ». "
                      "★ = produit favori : la Stratégie de course compose tes sacs d'assistance avec tes favoris et tes "
                      "produits validés.")
        aide.setObjectName("texteSecondaire")
        aide.setWordWrap(True)
        self.principal.addWidget(aide)

        cadre, lc = _cadre("Détail du produit")
        ligne = QHBoxLayout()
        self.pastille = PastilleNutriScore(46)
        self.label_detail = QLabel("Choisis un produit.")
        self.label_detail.setWordWrap(True)
        self.label_detail.setTextFormat(Qt.TextFormat.RichText)
        ligne.addWidget(self.pastille, 0, Qt.AlignmentFlag.AlignTop)
        ligne.addWidget(self.label_detail, 1)
        lc.addLayout(ligne)
        self.table_ns = _table(["Composante du Nutri-Score", "Pour 100 g ou 100 ml", "Points"], 250)
        lc.addWidget(self.table_ns)
        self.principal.addWidget(cadre)
        self.principal.addStretch()
        self._finaliser()

    def actualiser(self):
        a = self.athlete_id
        self._produits = _tous_les_produits(a, self.avec_gen.isChecked()) if a is not None else \
            [dict(g) for g in cat.GENERIQUES]
        self._verdicts = _bilan(a)["verdicts"] if a is not None else {}
        self._remplir()

    def _visibles(self):
        f = self.filtre.currentData()
        return [p for p in self._produits if f is None or p.get("categorie") == f]

    def _remplir(self):
        ps = self._visibles()
        t = self.table
        t.setRowCount(len(ps))
        for i, p in enumerate(ps):
            g = cat.par_portion(p, "glucides_g")
            na = cat.sodium_mg_portion(p)
            r = cat.nutriscore_de(p)
            v = self._verdicts.get(p["id"]) if not p.get("generique") else None
            valeurs = ["★" if p.get("favori") else "", p["nom"], p.get("marque") or "", p.get("categorie") or "",
                       cat.libelle_portion(p), f"{_fr(g)} g" if g is not None else "—",
                       f"{_fr(na)} mg" if na is not None else "—",
                       f"{p['cafeine_mg']:.0f} mg" if (p.get("cafeine_mg") or 0) >= 5 else "",
                       f"{_fr(p['prix_portion'], 2)} €" if p.get("prix_portion") else "—"]
            for j, val in enumerate(valeurs):
                it = QTableWidgetItem(val)
                it.setData(Qt.ItemDataRole.UserRole, p["id"])
                t.setItem(i, j, it)
            _poser_nutriscore(t, i, 9, r.get("lettre"),
                              f"étiquette {r['officiel']}" if r.get("officiel") and r["officiel"] != r.get("lettre") else None)
            it = QTableWidgetItem(v["libelle"] if v else "générique")
            if v:
                it.setForeground(QColor(tol.COULEUR_VERDICT[v["code"]]))
                it.setToolTip(v["detail"])
            t.setItem(i, 10, it)
        t.resizeColumnsToContents()
        self._detail()

    def _selection(self):
        lignes = sorted({i.row() for i in self.table.selectedIndexes()})
        ps = self._visibles()
        return [ps[l] for l in lignes if l < len(ps)]

    def _detail(self):
        sel = self._selection()
        if not sel:
            self.pastille.definir(None)
            self.label_detail.setText("Choisis un produit.")
            self.table_ns.setRowCount(0)
            return
        p = sel[0]
        r = cat.nutriscore_de(p)
        self.pastille.definir(r.get("lettre"))
        g = cat.par_portion(p, "glucides_g")
        morceaux = [f"<b>{html.escape(p['nom'])}</b>" + (f" — {html.escape(p['marque'])}" if p.get("marque") else ""),
                    f"Portion {cat.libelle_portion(p)} : {_fr(g)} g de glucides, "
                    f"{_fr(cat.par_portion(p, 'energie_kcal'))} kcal, {_fr(cat.sodium_mg_portion(p))} mg de sodium"
                    + (f", {p['cafeine_mg']:.0f} mg de caféine" if (p.get("cafeine_mg") or 0) >= 5 else "") + "."]
        if p.get("glucose_fructose"):
            morceaux.append(f"Glucose:fructose : {html.escape(p['glucose_fructose'])}.")
        p60 = cat.prix_pour_60g(p)
        if p60:
            morceaux.append(f"Coût pour 60 g de glucides (environ 1 h d'effort long) : {_fr(p60, 2)} €.")
        if r.get("lettre"):
            morceaux.append(f"Nutri-Score calculé : <b>{r['lettre']}</b>"
                            + (f" (score {r['score']})" if r.get("score") is not None else "")
                            + (f" ; étiquette : {r['officiel']}" if r.get("officiel") else "") + ".")
        else:
            morceaux.append(html.escape(r.get("raison") or ""))
        if r.get("note"):
            morceaux.append(f"<i>{html.escape(r['note'])}</i>")
        v = self._verdicts.get(p["id"]) if not p.get("generique") else None
        if v:
            morceaux.append(f"Ta tolérance : <b>{v['libelle']}</b> ({v['nb']} essai{'s' if v['nb'] > 1 else ''}) — "
                            f"{html.escape(v['detail'])}")
        if p.get("source"):
            morceaux.append(f"Source : {html.escape(p['source'])}.")
        self.label_detail.setText("<br>".join(morceaux))
        det = r.get("detail") or []
        self.table_ns.setRowCount(len(det))
        for i, (c, val, pts) in enumerate(det):
            for j, v_ in enumerate((c, val, f"{pts:+d}" if pts else "0")):
                self.table_ns.setItem(i, j, QTableWidgetItem(v_))
        self.table_ns.resizeColumnsToContents()

    # --- actions -------------------------------------------------
    def _verifier_athlete(self):
        if self.athlete_id is None:
            QMessageBox.information(self, "Produits", "Choisis d'abord un athlète en haut de l'écran.")
            return False
        return True

    def _ajouter(self, _x=False, depart=None):
        if not self._verifier_athlete():
            return
        d = DialogueProduit(self, depart, "Ajouter un produit")
        if d.exec():
            v = d.valeurs()
            if depart and depart.get("source"):
                v["source"] = depart["source"]
            try:
                existant = dnut.par_code_barre(self.athlete_id, v["code_barre"]) if v.get("code_barre") else None
                if existant:
                    dnut.modifier_produit(existant, v)
                else:
                    dnut.creer_produit(self.athlete_id, v)
            except dnut.ErreurNutrition as e:
                QMessageBox.warning(self, "Produit", str(e))
            self.actualiser()

    def _open_food_facts(self):
        if not self._verifier_athlete():
            return
        d = DialogueOpenFoodFacts(self)
        if d.exec() and d.choix:
            self._ajouter(depart=d.choix)

    def _modifier(self):
        sel = self._selection()
        if not sel:
            return
        p = sel[0]
        if p.get("generique"):
            if QMessageBox.question(self, "Produit générique",
                                    "Ce produit générique va être copié dans tes produits pour que tu puisses le "
                                    "modifier (prix, valeurs de ton produit…). Continuer ?") != QMessageBox.StandardButton.Yes:
                return
            p = dnut.produit(dnut.ajouter_generique(self.athlete_id, p["id"]))
        if p.get("recette_id"):
            QMessageBox.information(self, "Produit fait maison",
                                    "Ses valeurs viennent de sa recette : modifie-la dans l'onglet « Fait maison ». "
                                    "Tu peux changer ici son prix ou ses notes.")
        d = DialogueProduit(self, p, "Modifier le produit")
        if d.exec():
            try:
                dnut.modifier_produit(p["id"], d.valeurs())
            except dnut.ErreurNutrition as e:
                QMessageBox.warning(self, "Produit", str(e))
        self.actualiser()

    def _vrai_id(self, p):
        return dnut.ajouter_generique(self.athlete_id, p["id"]) if p.get("generique") else p["id"]

    def _favori(self):
        if not self._verifier_athlete():
            return
        for p in self._selection():
            dnut.definir_favori(self._vrai_id(p), not p.get("favori"))
        self.actualiser()

    def _essai(self):
        if not self._verifier_athlete():
            return
        sel = self._selection()
        pid = self._vrai_id(sel[0]) if sel else None
        d = DialogueEssai(self, dnut.produits(self.athlete_id), pid)
        if d.produit.count() == 0:
            QMessageBox.information(self, "Essai", "Ajoute d'abord un produit (ou choisis un générique).")
            return
        if d.exec():
            try:
                dnut.ajouter_essai(self.athlete_id, d.valeurs())
            except dnut.ErreurNutrition as e:
                QMessageBox.warning(self, "Essai", str(e))
        self.actualiser()

    def _comparer(self):
        sel = self._selection()
        if len(sel) < 2:
            QMessageBox.information(self, "Comparer", "Sélectionne 2 à 4 produits (Ctrl ou ⌘ + clic).")
            return
        self.comparer_demande.emit([p["id"] for p in sel[:4]])

    def _supprimer(self):
        sel = [p for p in self._selection() if not p.get("generique")]
        if not sel:
            return
        noms = ", ".join(p["nom"] for p in sel)
        if QMessageBox.question(self, "Supprimer", f"Supprimer {noms} et leurs essais notés ? "
                                "Les recettes liées sont gardées.") != QMessageBox.StandardButton.Yes:
            return
        for p in sel:
            dnut.supprimer_produit(p["id"])
        self.actualiser()


# ======================================================================
# Onglet 2 — Fait maison
# ======================================================================

class FaitMaison(_Onglet):

    def __init__(self, athlete_id_initial=None):
        super().__init__("🥣  Fait maison : barres, gels et boissons",
                         "Compose ta recette : le logiciel calcule les glucides par portion, le sodium, le rapport "
                         "glucose:fructose, la concentration d'une boisson, le Nutri-Score et le coût. Une recette "
                         "enregistrée rejoint tes produits pour la comparer et noter tes essais.",
                         athlete_id_initial)
        self._recette_id = None
        ligne = QHBoxLayout()
        self.liste = QComboBox()
        self.liste.currentIndexChanged.connect(self._charger_choisie)
        self.modele = QComboBox()
        self.modele.addItem("Partir d'une recette de départ…", None)
        for i, m in enumerate(MODELES):
            self.modele.addItem(f"{m[0]} ({m[1].lower()})", i)
        self.modele.currentIndexChanged.connect(self._depuis_modele)
        nouveau = _bouton("Nouvelle recette vide")
        nouveau.clicked.connect(self._nouvelle)
        ligne.addWidget(QLabel("Mes recettes :"))
        ligne.addWidget(self.liste, 1)
        ligne.addWidget(self.modele, 1)
        ligne.addWidget(nouveau)
        self.principal.addLayout(ligne)

        cadre, lc = _cadre("Recette")
        form = QHBoxLayout()
        self.nom = QLineEdit()
        self.nom.setPlaceholderText("Nom de la recette")
        self.categorie = QComboBox()
        self.categorie.addItems(CATEGORIES_RECETTE)
        self.portions = QSpinBox()
        self.portions.setRange(1, 100)
        self.portions.setSuffix(" portion(s)")
        form.addWidget(self.nom, 2)
        form.addWidget(self.categorie, 1)
        form.addWidget(self.portions)
        lc.addLayout(form)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Ingrédient", "Quantité (g ou ml)", "Prix (€/kg, facultatif)", ""])
        self.table.verticalHeader().setVisible(False)
        self.table.setMinimumHeight(300)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        for col, larg in enumerate((340, 170, 190, 54)):
            self.table.setColumnWidth(col, larg)
        self.table.horizontalHeader().setStretchLastSection(False)
        lc.addWidget(self.table)
        b = QHBoxLayout()
        ajout = _bouton("➕ Ingrédient")
        ajout.clicked.connect(lambda: self._ajouter_ligne("eau", 0))
        self.cible = QSpinBox()
        self.cible.setRange(5, 120)
        self.cible.setValue(25)
        self.cible.setSuffix(" g de glucides par portion")
        self.sucre_cible = QComboBox()
        for code in ("maltodextrine", "dextrose", "sucre", "miel", "fructose"):
            self.sucre_cible.addItem(INGREDIENTS[code]["nom"], code)
        viser = _bouton("Viser")
        viser.clicked.connect(self._viser)
        b.addWidget(ajout)
        b.addStretch()
        b.addWidget(QLabel("Atteindre"))
        b.addWidget(self.cible)
        b.addWidget(QLabel("avec"))
        b.addWidget(self.sucre_cible)
        b.addWidget(viser)
        lc.addLayout(b)
        self.preparation = QTextEdit()
        self.preparation.setPlaceholderText("Préparation")
        self.preparation.setMaximumHeight(90)
        self.conservation = QLineEdit()
        self.conservation.setPlaceholderText("Conservation")
        lc.addWidget(self.preparation)
        lc.addWidget(self.conservation)
        b2 = QHBoxLayout()
        enreg = _bouton("💾 Enregistrer la recette", True)
        enreg.clicked.connect(self._enregistrer)
        suppr = _bouton("🗑 Supprimer la recette")
        suppr.clicked.connect(self._supprimer)
        b2.addWidget(enreg)
        b2.addWidget(suppr)
        b2.addStretch()
        lc.addLayout(b2)
        self.principal.addWidget(cadre)

        cadre, lr = _cadre("Résultat")
        ligne = QHBoxLayout()
        ligne.setSpacing(15)
        self.cartes = {}
        for cle, titre in (("gluc", "Glucides par portion"), ("kcal", "Énergie par portion"), ("na", "Sodium par portion"),
                           ("gf", "Glucose:fructose"), ("cout", "Coût par portion")):
            self.cartes[cle] = self._carte(titre)
            ligne.addWidget(self.cartes[cle], 1)
        lr.addLayout(ligne)
        l2 = QHBoxLayout()
        self.pastille = PastilleNutriScore(46)
        self.label_resultat = QLabel("")
        self.label_resultat.setWordWrap(True)
        self.label_resultat.setTextFormat(Qt.TextFormat.RichText)
        l2.addWidget(self.pastille, 0, Qt.AlignmentFlag.AlignTop)
        l2.addWidget(self.label_resultat, 1)
        lr.addLayout(l2)
        note = QLabel("Valeurs moyennes des ingrédients (du type de la table Ciqual de l'Anses) : pour un produit précis, "
                      "choisis « Ingrédient libre » et recopie son étiquette. Teste toute recette à l'entraînement.")
        note.setObjectName("texteSecondaire")
        note.setWordWrap(True)
        lr.addWidget(note)
        self.principal.addWidget(cadre)
        self.principal.addStretch()
        self.portions.valueChanged.connect(self._calculer)
        self.categorie.currentIndexChanged.connect(self._calculer)
        self._finaliser()
        if self.table.rowCount() == 0:
            self.modele.setCurrentIndex(1)

    # --- lignes d'ingrédients -----------------------------------
    def _ajouter_ligne(self, code, g, prix=None, libre=None):
        r = self.table.rowCount()
        self.table.insertRow(r)
        combo = QComboBox()
        for c, v in INGREDIENTS.items():
            combo.addItem(v["nom"], c)
        combo.addItem("Ingrédient libre (mon étiquette)…", "libre")
        combo.setCurrentIndex(max(0, combo.findData(code if code in INGREDIENTS else "libre")))
        combo.setProperty("libre", libre)
        if libre:
            combo.setItemText(combo.count() - 1, f"Libre : {libre.get('nom', 'ingrédient')}")
        combo.currentIndexChanged.connect(lambda _i, c=combo: self._combo_change(c))
        qte = _decimal(0, 5000, 1)
        qte.setValue(g)
        qte.valueChanged.connect(self._calculer)
        px = _spin(500, 2, "€/kg")
        if prix is not None:
            px.setValue(prix)
        px.valueChanged.connect(self._calculer)
        suppr = QPushButton("✕")
        suppr.setObjectName("boutonSecondaire")
        suppr.clicked.connect(lambda _x=False, w=suppr: self._retirer(w))
        self.table.setCellWidget(r, 0, combo)
        self.table.setCellWidget(r, 1, qte)
        self.table.setCellWidget(r, 2, px)
        self.table.setCellWidget(r, 3, suppr)
        self.table.setRowHeight(r, 42)
        self._calculer()

    def _retirer(self, bouton):
        for r in range(self.table.rowCount()):
            if self.table.cellWidget(r, 3) is bouton:
                self.table.removeRow(r)
                break
        self._calculer()

    def _combo_change(self, combo):
        if combo.currentData() == "libre":
            d = DialogueProduit(self, combo.property("libre") or {"nom": "", "categorie": "Autre"},
                                "Ingrédient libre (valeurs pour 100 g)")
            if d.exec():
                v = d.valeurs()
                libre = {"nom": v["nom"] or "Ingrédient", "kcal": v.get("energie_kcal"),
                         "glucides_g": v.get("glucides_g"), "sucres_g": v.get("sucres_g"),
                         "fibres_g": v.get("fibres_g"), "proteines_g": v.get("proteines_g"),
                         "lipides_g": v.get("lipides_g"), "ags_g": v.get("ags_g"), "sel_g": v.get("sel_g"),
                         "glucose_g": None, "fructose_g": None}
                if libre["sucres_g"] is not None:      # sans détail, les sucres comptent moitié-moitié
                    reste = max(0.0, (libre["glucides_g"] or 0) - libre["sucres_g"])
                    libre["glucose_g"] = libre["sucres_g"] / 2 + reste
                    libre["fructose_g"] = libre["sucres_g"] / 2
                combo.setProperty("libre", libre)
                combo.setItemText(combo.count() - 1, f"Libre : {libre['nom']}")
            elif not combo.property("libre"):
                combo.setCurrentIndex(0)
        self._calculer()

    def _ingredients(self):
        res = []
        for r in range(self.table.rowCount()):
            combo, qte, px = (self.table.cellWidget(r, c) for c in range(3))
            if combo is None:
                continue
            item = {"g": qte.value()}
            if combo.currentData() == "libre":
                libre = combo.property("libre") or {}
                item["nom"] = libre.get("nom", "Ingrédient")
                item["valeurs"] = {k: v for k, v in libre.items() if k != "nom"}
            else:
                item["code"] = combo.currentData()
            if _val(px) is not None:
                item["prix_kg"] = _val(px)
            res.append(item)
        return res

    def _vider(self):
        self.table.setRowCount(0)

    # --- recettes --------------------------------------------------
    def actualiser(self):
        a = self.athlete_id
        actuel = self._recette_id
        self.liste.blockSignals(True)
        self.liste.clear()
        self.liste.addItem("— choisir —", None)
        for r in dnut.recettes(a):
            self.liste.addItem(f"{r['nom']} ({r['categorie'].lower()})", r["id"])
        i = self.liste.findData(actuel)
        self.liste.setCurrentIndex(i if i >= 0 else 0)
        self.liste.blockSignals(False)
        self._calculer()

    def _remplir(self, nom, categorie, portions, ingredients, preparation="", conservation=""):
        for w in (self.portions, self.categorie):
            w.blockSignals(True)
        self.nom.setText(nom)
        self.categorie.setCurrentText(categorie)
        self.portions.setValue(int(portions))
        for w in (self.portions, self.categorie):
            w.blockSignals(False)
        self._vider()
        for it in ingredients:
            libre = None
            if not it.get("code"):
                libre = {"nom": it.get("nom", "Ingrédient"), **(it.get("valeurs") or {})}
            self._ajouter_ligne(it.get("code") or "libre", it.get("g", 0), it.get("prix_kg"), libre)
        self.preparation.setPlainText(preparation or "")
        self.conservation.setText(conservation or "")
        self._calculer()

    def _depuis_modele(self):
        i = self.modele.currentData()
        if i is None:
            return
        nom, categorie, portions, ing, prep, cons = MODELES[i]
        self._recette_id = None
        self.liste.blockSignals(True)
        self.liste.setCurrentIndex(0)
        self.liste.blockSignals(False)
        self._remplir(nom, categorie, portions, [{"code": c, "g": g} for c, g in ing], prep, cons)
        self.modele.blockSignals(True)
        self.modele.setCurrentIndex(0)
        self.modele.blockSignals(False)

    def _nouvelle(self):
        self._recette_id = None
        self.liste.setCurrentIndex(0)
        self._remplir("", "Barre", 1, [{"code": "eau", "g": 0}])

    def _charger_choisie(self):
        rid = self.liste.currentData()
        if rid is None:
            return
        r = dnut.recette(rid)
        if not r:
            return
        self._recette_id = rid
        self._remplir(r["nom"], r["categorie"], r["nb_portions"], r["ingredients"], r.get("preparation"),
                      r.get("conservation"))

    def _viser(self):
        ajout = rc.ajuster_glucides(self._ingredients(), self.portions.value(), self.cible.value(),
                                    self.sucre_cible.currentData(), self.categorie.currentText())
        if not ajout:
            QMessageBox.information(self, "Fait maison", "La recette atteint déjà cette quantité de glucides par portion.")
            return
        code = self.sucre_cible.currentData()
        for r in range(self.table.rowCount()):
            combo, qte = self.table.cellWidget(r, 0), self.table.cellWidget(r, 1)
            if combo and combo.currentData() == code:
                qte.setValue(qte.value() + ajout)
                return
        self._ajouter_ligne(code, ajout)

    def _calculer(self):
        r = rc.calculer(self._ingredients(), self.portions.value(), self.categorie.currentText())
        self._resultat = r
        for c in self.cartes.values():
            c.valeur.setText("—")
            c.detail.setText("")
        if not r:
            self.pastille.definir(None)
            self.label_resultat.setText("Ajoute des ingrédients avec leur quantité.")
            return
        pp = r["par_portion"]
        c = self.cartes
        c["gluc"].valeur.setText(f"{_fr(pp['glucides_g'])} g")
        c["gluc"].detail.setText(f"dont sucres {_fr(pp['sucres_g'])} g · portion de {_fr(r['portion_g'])} g")
        c["kcal"].valeur.setText(f"{_fr(pp['kcal'])} kcal")
        c["kcal"].detail.setText(f"protéines {_fr(pp['proteines_g'], 1)} g · lipides {_fr(pp['lipides_g'], 1)} g · "
                                 f"fibres {_fr(pp['fibres_g'], 1)} g")
        c["na"].valeur.setText(f"{r['sodium_mg_portion']} mg")
        c["na"].detail.setText(f"sel {_fr(pp['sel_g'], 2)} g" + (f" · {_fr(pp['cafeine_mg'])} mg de caféine"
                                                                    if pp.get("cafeine_mg") else ""))
        c["gf"].valeur.setText(r["ratio_glucose_fructose"] or "—")
        c["gf"].detail.setText("1:0,5 à 1:0,8 conseillé au-delà de 60 g/h")
        c["cout"].valeur.setText(f"{_fr(r['cout_portion'], 2)} €" if r["cout_portion"] is not None else "—")
        c["cout"].detail.setText("prix de chaque ingrédient en €/kg" if r["cout_portion"] is None
                                 else f"{_fr(r['cout_total'], 2)} € la recette")
        nsr = r["nutriscore"]
        self.pastille.definir(nsr.get("lettre"))
        txt = []
        if r["concentration_g_l"] is not None:
            txt.append(f"Boisson : {r['total_g']} ml environ, {r['concentration_g_l']} g de glucides par litre, "
                       f"{round(r['sodium_mg_portion'] * r['nb_portions'] / (r['total_g'] / 1000)) if r['total_g'] else 0} "
                       "mg de sodium par litre.")
        txt.append(f"Recette entière : {r['total_g']} g, {_fr(r['total']['glucides_g'])} g de glucides.")
        if nsr.get("lettre"):
            txt.append(f"Nutri-Score {nsr['lettre']} (score {nsr['score']})" + (f" — {nsr['note']}" if nsr.get("note") else "."))
        if r["avertissements"]:
            txt.append("<ul>" + "".join(f"<li>{html.escape(a)}</li>" for a in r["avertissements"]) + "</ul>")
        self.label_resultat.setText("<br>".join(txt))

    def _enregistrer(self):
        if self.athlete_id is None:
            QMessageBox.information(self, "Fait maison", "Choisis d'abord un athlète en haut de l'écran.")
            return
        try:
            self._recette_id, _pid = dnut.enregistrer_recette(
                self.athlete_id, self._recette_id, self.nom.text(), self.categorie.currentText(), self.portions.value(),
                self._ingredients(), self.preparation.toPlainText().strip(), self.conservation.text().strip())
        except dnut.ErreurNutrition as e:
            QMessageBox.warning(self, "Fait maison", str(e))
            return
        self.actualiser()
        QMessageBox.information(self, "Fait maison", "Recette enregistrée. Elle apparaît aussi dans « Mes produits de "
                                "course » (marque « Fait maison ») pour la comparer et noter tes essais.")

    def _supprimer(self):
        if self._recette_id is None:
            return
        rep = QMessageBox.question(self, "Supprimer la recette",
                                   "Supprimer aussi le produit « Fait maison » lié et ses essais notés ?",
                                   QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
                                   | QMessageBox.StandardButton.Cancel)
        if rep == QMessageBox.StandardButton.Cancel:
            return
        dnut.supprimer_recette(self._recette_id, avec_produit=rep == QMessageBox.StandardButton.Yes)
        self._recette_id = None
        self.actualiser()


# ======================================================================
# Onglet 3 — Comparatif
# ======================================================================

class ComparatifProduits(_Onglet):

    def __init__(self, athlete_id_initial=None):
        super().__init__("⚖️  Comparatif de produits",
                         "Deux à quatre produits côte à côte : ce qu'ils apportent pendant l'effort, leur prix pour "
                         "une heure de course, ta tolérance, et leur Nutri-Score (lettres A à E) pour le quotidien.",
                         athlete_id_initial)
        self._produits = []
        self._preselection = []
        ligne = QHBoxLayout()
        self.combos = []
        for i in range(4):
            c = QComboBox()
            c.currentIndexChanged.connect(self._calculer)
            self.combos.append(c)
            ligne.addWidget(c, 1)
        self.principal.addLayout(ligne)
        self.table = _table(["Critère", "", "", "", ""], 560)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.principal.addWidget(self.table)
        cadre, lc = _cadre("En résumé")
        self.label = QLabel("")
        self.label.setWordWrap(True)
        self.label.setTextFormat(Qt.TextFormat.RichText)
        lc.addWidget(self.label)
        self.principal.addWidget(cadre)
        note = QLabel("Le Nutri-Score note l'alimentation de tous les jours pour 100 g ou 100 ml : un gel ou une pâte de "
                      "fruits sont presque toujours D ou E, c'est normal. Pour un ravitaillement, regarde d'abord les "
                      "glucides par portion, le sodium et ta tolérance.")
        note.setObjectName("texteSecondaire")
        note.setWordWrap(True)
        self.principal.addWidget(note)
        self.principal.addStretch()
        self._finaliser()

    def preselectionner(self, ids):
        self._preselection = list(ids)
        self.actualiser()

    def actualiser(self):
        a = self.athlete_id
        self._produits = _tous_les_produits(a) if a is not None else [dict(g) for g in cat.GENERIQUES]
        self._verdicts = _bilan(a)["verdicts"] if a is not None else {}
        choisis = self._preselection or [c.currentData() for c in self.combos]
        self._preselection = []
        for k, c in enumerate(self.combos):
            c.blockSignals(True)
            c.clear()
            c.addItem("— aucun —", None)
            for p in self._produits:
                c.addItem(p["nom"] + (f" ({p['marque']})" if p.get("marque") and p["marque"] != "Générique" else ""),
                          p["id"])
            voulu = choisis[k] if k < len(choisis) else None
            i = c.findData(voulu)
            if i < 0 and voulu is None and k < 2 and not any(choisis):
                i = k + 1               # par défaut : les deux premiers produits
            c.setCurrentIndex(max(0, i))
            c.blockSignals(False)
        self._calculer()

    def _calculer(self):
        par_id = {p["id"]: p for p in self._produits}
        ps = [par_id[c.currentData()] for c in self.combos if c.currentData() in par_id]
        if len(ps) < 2:
            self.table.setRowCount(0)
            self.label.setText("Choisis au moins deux produits.")
            return
        r = cmp.comparer(ps, getattr(self, "_verdicts", {}))
        t = self.table
        t.setColumnCount(1 + len(ps))
        t.setHorizontalHeaderLabels(["Critère"] + r["colonnes"])
        t.setRowCount(len(r["lignes"]))
        for i, (critere, vals) in enumerate(r["lignes"]):
            t.setItem(i, 0, QTableWidgetItem(critere))
            for j, v in enumerate(vals):
                if critere.startswith("Nutri-Score"):
                    _poser_nutriscore(t, i, j + 1, r["nutriscores"][j], v)
                else:
                    t.setItem(i, j + 1, QTableWidgetItem(v))
        t.resizeColumnsToContents()
        self.label.setText("<ul>" + "".join(f"<li>{html.escape(p)}</li>" for p in r["phrases"]) + "</ul>")


# ======================================================================
# Onglet 4 — Tolérances et besoins par heure
# ======================================================================

class TolerancesBesoins(_Onglet):

    def __init__(self, athlete_id_initial=None):
        super().__init__("🩺  Tolérances et besoins par heure",
                         "Note chaque essai d'un produit à l'entraînement : le logiciel tient le verdict de chaque "
                         "produit, ton apport de glucides le plus haut bien toléré, et compose ton menu heure par heure "
                         "avec tes produits validés.", athlete_id_initial)
        cadre, lc = _cadre("Besoins par heure")
        form = QHBoxLayout()
        self.duree = _decimal(0.5, 48, 1)
        self.duree.setValue(4)
        self.duree.setSuffix(" h d'effort")
        self.temp = QSpinBox()
        self.temp.setRange(-15, 45)
        self.temp.setValue(18)
        self.temp.setSuffix(" °C")
        self.intensite = QComboBox()
        for code, lib in (("facile", "Facile"), ("modere", "Modérée"), ("soutenu", "Soutenue")):
            self.intensite.addItem(lib, code)
        self.intensite.setCurrentIndex(1)
        self.sel = QCheckBox("Je transpire beaucoup (traces de sel)")
        for w in (self.duree, self.temp):
            w.valueChanged.connect(self._besoins)
        self.intensite.currentIndexChanged.connect(self._besoins)
        self.sel.toggled.connect(self._besoins)
        for w in (self.duree, self.temp, self.intensite, self.sel):
            form.addWidget(w)
        form.addStretch()
        lc.addLayout(form)
        ligne = QHBoxLayout()
        ligne.setSpacing(15)
        self.cartes = {}
        for cle, titre in (("g", "Glucides"), ("eau", "Eau"), ("na", "Sodium"), ("max", "Ton maximum bien toléré")):
            self.cartes[cle] = self._carte(titre)
            ligne.addWidget(self.cartes[cle], 1)
        lc.addLayout(ligne)
        self.label_ventre = QLabel("")
        self.label_ventre.setWordWrap(True)
        lc.addWidget(self.label_ventre)
        self.table_menu = _table(["Heure", "Avec tes produits", "Glucides", "Sodium"], 220)
        lc.addWidget(self.table_menu)
        self.label_menu = QLabel("")
        self.label_menu.setWordWrap(True)
        self.label_menu.setObjectName("texteSecondaire")
        lc.addWidget(self.label_menu)
        self.principal.addWidget(cadre)

        cadre, lc = _cadre("Verdict par produit")
        self.table_bilan = _table(["Produit", "Verdict", "Essais", "Pourquoi"], 220)
        lc.addWidget(self.table_bilan)
        self.principal.addWidget(cadre)

        cadre, lc = _cadre("Mes essais")
        b = QHBoxLayout()
        ajout = _bouton("🩺 Noter un essai", True)
        ajout.clicked.connect(self._ajouter)
        suppr = _bouton("🗑 Supprimer l'essai")
        suppr.clicked.connect(self._supprimer)
        b.addWidget(ajout)
        b.addWidget(suppr)
        b.addStretch()
        lc.addLayout(b)
        self.table_essais = _table(["Date", "Produit", "Contexte", "Durée", "Glucides/h", "Ressenti", "Symptômes",
                                    "Notes"], 260)
        lc.addWidget(self.table_essais)
        self.principal.addWidget(cadre)
        note = QLabel("Repères de nutrition sportive généralement admis, à tester à l'entraînement : ce n'est pas un avis "
                      "médical. En cas de troubles digestifs répétés, parles-en à un médecin ou à un diététicien du sport.")
        note.setObjectName("texteSecondaire")
        note.setWordWrap(True)
        self.principal.addWidget(note)
        self.principal.addStretch()
        self._finaliser()

    def actualiser(self):
        a = self.athlete_id
        self._produits = dnut.produits(a)
        self._essais = dnut.essais(a)
        self._bilan = tol.bilan(self._produits, self._essais)
        self._poids = 70
        if a is not None:
            from noyau.donnees import sante as dsante, athletes as dath
            p = dsante.dernier_poids(a)
            p = p[0] if isinstance(p, (tuple, list)) else p
            self._poids = p or dath.valeur(a, "poids") or 70
        v = self._bilan["verdicts"]
        ps = sorted(self._produits, key=lambda p: [c for c, _l, _k in tol.VERDICTS].index(v[p["id"]]["code"]))
        self.table_bilan.setRowCount(len(ps))
        for i, p in enumerate(ps):
            d = v[p["id"]]
            it = QTableWidgetItem(d["libelle"])
            it.setForeground(QColor(tol.COULEUR_VERDICT[d["code"]]))
            for j, val in enumerate((p["nom"], None, str(d["nb"]), d["detail"])):
                self.table_bilan.setItem(i, j, it if j == 1 else QTableWidgetItem(val))
        self.table_bilan.resizeColumnsToContents()
        es = self._essais
        self.table_essais.setRowCount(len(es))
        for i, e in enumerate(es):
            vals = (date.fromisoformat(e["date"][:10]).strftime("%d/%m/%Y") if e.get("date") else "", e["produit"],
                    e.get("contexte") or "", f"{e['duree_min']:.0f} min" if e.get("duree_min") else "",
                    f"{e['glucides_g_h']:.0f} g/h" if e.get("glucides_g_h") else "",
                    dnut.LIBELLE_RESSENTI.get(e["ressenti"], e["ressenti"]), e.get("symptomes") or "", e.get("notes") or "")
            for j, val in enumerate(vals):
                it = QTableWidgetItem(val)
                it.setData(Qt.ItemDataRole.UserRole, e["id"])
                self.table_essais.setItem(i, j, it)
        self.table_essais.resizeColumnsToContents()
        self._besoins()

    def _besoins(self):
        if not hasattr(self, "_bilan"):
            return
        plan = rav.plan_ravitaillement(self.duree.value(), self.temp.value(), self._poids,
                                       self.intensite.currentData(), self.sel.isChecked())
        c = self.cartes
        c["g"].valeur.setText(f"{plan['glucides_g_h']} g/h")
        c["g"].detail.setText(f"{plan['totaux']['glucides_g']} g sur {_fr(self.duree.value(), 1)} h")
        c["eau"].valeur.setText(f"{plan['eau_ml_h']} ml/h")
        c["eau"].detail.setText(f"{_fr(plan['totaux']['eau_l'], 1)} L au total")
        c["na"].valeur.setText(f"{plan['sodium_mg_h']} mg/h")
        c["na"].detail.setText(f"{plan['totaux']['sodium_mg']} mg au total")
        mx = self._bilan["max_g_h_tolere"]
        c["max"].valeur.setText(f"{mx:.0f} g/h" if mx else "—")
        c["max"].detail.setText("d'après tes essais notés « bien toléré »" if mx else
                                "note tes glucides par heure à chaque essai")
        self.label_ventre.setText(tol.entrainement_du_ventre(mx, plan["glucides_g_h"]) or "")
        menu = tol.menu_avec_mes_produits(plan, self._produits, self._bilan["verdicts"])
        self.table_menu.setRowCount(len(menu))
        for i, l in enumerate(menu):
            for j, v in enumerate((f"{l['heure']}", tol.texte_ligne_menu(l), f"{l['glucides_g']} / {l['cible_g']} g",
                                   f"{l['sodium_mg']} / {l['sodium_cible_mg']} mg")):
                self.table_menu.setItem(i, j, QTableWidgetItem(v))
        self.table_menu.resizeColumnsToContents()
        if menu:
            self.label_menu.setText("Menu composé avec tes produits favoris (★) et validés ; les pastilles complètent le "
                                    "sodium. " + " ".join(plan["notes"]))
        else:
            self.label_menu.setText("Marque tes produits préférés d'une ★ dans « Mes produits de course » (ou valide-les "
                                    "par tes essais) : le menu heure par heure se composera avec eux. "
                                    + " ".join(plan["notes"]))

    def _ajouter(self):
        if self.athlete_id is None:
            QMessageBox.information(self, "Essai", "Choisis d'abord un athlète en haut de l'écran.")
            return
        if not self._produits:
            QMessageBox.information(self, "Essai", "Ajoute d'abord un produit dans « Mes produits de course ».")
            return
        d = DialogueEssai(self, self._produits)
        if d.exec():
            try:
                dnut.ajouter_essai(self.athlete_id, d.valeurs())
            except dnut.ErreurNutrition as e:
                QMessageBox.warning(self, "Essai", str(e))
        self.actualiser()

    def _supprimer(self):
        it = self.table_essais.item(self.table_essais.currentRow(), 0) if self.table_essais.currentRow() >= 0 else None
        if not it:
            return
        if QMessageBox.question(self, "Supprimer", "Supprimer cet essai ?") == QMessageBox.StandardButton.Yes:
            dnut.supprimer_essai(it.data(Qt.ItemDataRole.UserRole))
            self.actualiser()
