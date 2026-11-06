"""
Annuaire trail (module « annuaire ») : clubs d'athlétisme, de running et de
trail, sections et écoles de trail, organisateurs de courses, magasins et
marques. Une base de référence est livrée (région PACA pour commencer) ;
tu la complètes, la corriges, notes tes favoris. Les marques et magasins
servent aussi à la saisie du matériel.

Fenêtre « 📒 Annuaire », trois onglets : Clubs et écoles, Magasins, Marques.
Aucune requête SQL ici : tout passe par noyau/donnees/annuaire.py.
"""

import html
from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QColor, QDesktopServices
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QFrame, QGridLayout,
    QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPlainTextEdit, QPushButton, QTableWidget, QTableWidgetItem,
    QVBoxLayout,
)

from noyau.donnees import annuaire as dan
from noyau.annuaire import regles as R
from interface.conteneur_onglets import ConteneurOnglets
from interface.ecran_liste import configurer_table_redimensionnable, obtenir_style_ecran
from interface.forme_evolution import _EcranAthlete


def _bouton(texte, principal=False):
    b = QPushButton(texte)
    b.setObjectName("boutonPrincipal" if principal else "boutonSecondaire")
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    return b


def _style_cases(widget):
    from interface.theme import PALETTE, obtenir_couleur_accent
    a = obtenir_couleur_accent()
    widget.setStyleSheet(widget.styleSheet() + (
        " QCheckBox { background: transparent; spacing: 8px; }"
        f" QCheckBox::indicator {{ width: 16px; height: 16px; border: 1px solid {PALETTE['texte_discret']};"
        f" border-radius: 4px; background: {PALETTE['carte_haute']}; }}"
        f" QCheckBox::indicator:checked {{ background: {a}; border-color: {a}; }}"))


# ======================================================================
# Fiche (ajout / correction)
# ======================================================================

class DialogueFiche(QDialog):

    def __init__(self, parent, type_defaut, fiche=None):
        super().__init__(parent)
        f = fiche or {}
        self.fiche_id = f.get("id")
        self.setWindowTitle("Fiche de l'annuaire" if fiche else "Ajouter à l'annuaire")
        self.setStyleSheet(obtenir_style_ecran())
        _style_cases(self)
        self.resize(600, 620)
        lay = QVBoxLayout(self)
        if f.get("reference"):
            avis = QLabel("Fiche de la base livrée avec le logiciel. Si tu la corriges, ta version est gardée : les mises "
                          "à jour de la base ne l'écraseront plus.")
            avis.setWordWrap(True)
            avis.setObjectName("texteSecondaire")
            lay.addWidget(avis)
        form = QFormLayout()
        self.type = QComboBox()
        types = (["marque"] if type_defaut == "marque" else ["magasin"] if type_defaut == "magasin" else list(R.TYPES_CLUBS))
        for t in types:
            self.type.addItem(R.LIBELLE_TYPE[t], t)
        self.type.setCurrentIndex(max(0, self.type.findData(f.get("type") or type_defaut)))
        self.nom, self.sigle = QLineEdit(f.get("nom") or ""), QLineEdit(f.get("sigle") or "")
        self.enseigne = QLineEdit(f.get("enseigne") or "")
        self.enseigne.setPlaceholderText("ex. Running Conseil, Terre de Running, Indépendant")
        self.categorie = QComboBox()
        self.categorie.addItem("—", None)
        for c, l in R.CATEGORIES_MAGASIN:
            self.categorie.addItem(l, c)
        self.categorie.setCurrentIndex(max(0, self.categorie.findData(f.get("categorie"))))
        self.commune, self.cp = QLineEdit(f.get("commune") or ""), QLineEdit(f.get("code_postal") or "")
        self.adresse = QLineEdit(f.get("adresse") or "")
        self.site = QLineEdit(f.get("site") or "")
        self.site.setPlaceholderText("https://…")
        self.affiliation = QComboBox()
        self.affiliation.addItem("—", None)
        self.affiliation.addItems(R.AFFILIATIONS)
        if f.get("affiliation"):
            if self.affiliation.findText(f["affiliation"]) < 0:
                self.affiliation.addItem(f["affiliation"])
            self.affiliation.setCurrentText(f["affiliation"])
        self.pays, self.groupe = QLineEdit(f.get("pays") or ""), QLineEdit(f.get("groupe") or "")
        self.cases = {}
        grille = QGridLayout()
        for i, (c, l) in enumerate(R.CATEGORIES_MARQUE):
            k = QCheckBox(l.split(" (")[0])
            k.setChecked(c in (f.get("categories") or []))
            self.cases[c] = k
            grille.addWidget(k, i // 2, i % 2)
        self.notes = QLineEdit(f.get("notes") or "")
        self.mes_notes = QPlainTextEdit(f.get("mes_notes") or "")
        self.mes_notes.setPlaceholderText("Tes notes : bon accueil, essai de chaussures sur tapis, remise licenciés, "
                                          "horaires d'entraînement…")
        self.mes_notes.setMaximumHeight(90)
        self.favori = QCheckBox("Dans mes favoris")
        self.favori.setChecked(bool(f.get("favori")))
        self._lignes = {}
        for cle, lib, w in (("type", "Type", self.type), ("nom", "Nom", self.nom), ("sigle", "Sigle", self.sigle),
                            ("enseigne", "Enseigne", self.enseigne), ("categorie", "Catégorie", self.categorie),
                            ("commune", "Commune", self.commune), ("cp", "Code postal", self.cp),
                            ("adresse", "Adresse", self.adresse), ("site", "Site internet", self.site),
                            ("affiliation", "Fédération", self.affiliation), ("pays", "Pays", self.pays),
                            ("groupe", "Groupe", self.groupe), ("categories", "Produits", grille),
                            ("notes", "Remarque", self.notes), ("mes_notes", "Mes notes", self.mes_notes),
                            ("favori", "", self.favori)):
            form.addRow(lib, w)
            self._lignes[cle] = w
        self.form = form
        lay.addLayout(form)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        bb.button(QDialogButtonBox.StandardButton.Save).setText("Enregistrer")
        bb.button(QDialogButtonBox.StandardButton.Cancel).setText("Annuler")
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)
        self.type.currentIndexChanged.connect(lambda _i: self._visibles())
        self._visibles()

    def _visibles(self):
        t = self.type.currentData()
        marque, magasin = t == "marque", t == "magasin"
        montrer = {"sigle": not marque and not magasin, "enseigne": magasin, "categorie": magasin,
                   "commune": not marque, "cp": not marque, "adresse": not marque, "affiliation": t in R.TYPES_CLUBS,
                   "pays": marque, "groupe": marque, "categories": marque}
        for cle, vis in montrer.items():
            self.form.setRowVisible(self._lignes[cle], vis)

    def champs(self):
        t = self.type.currentData()
        return {"type": t, "nom": self.nom.text(), "sigle": self.sigle.text(), "enseigne": self.enseigne.text(),
                "categorie": self.categorie.currentData() if t == "magasin" else None, "commune": self.commune.text(),
                "code_postal": self.cp.text(), "adresse": self.adresse.text(), "site": self.site.text(),
                "affiliation": self.affiliation.currentText() if self.affiliation.currentIndex() > 0 else None,
                "pays": self.pays.text(), "groupe": self.groupe.text(),
                "categories": [c for c, k in self.cases.items() if k.isChecked()] if t == "marque" else None,
                "notes": self.notes.text(), "mes_notes": self.mes_notes.toPlainText().strip() or None,
                "favori": self.favori.isChecked()}

    def accept(self):
        c = self.champs()
        try:
            fid = dan.enregistrer(c, self.fiche_id)
            dan.definir_favori(fid, c["favori"])
        except dan.ErreurAnnuaire as e:
            QMessageBox.warning(self, "Annuaire", str(e))
            return
        super().accept()


# ======================================================================
# Onglet générique
# ======================================================================

class _EcranAnnuaire(_EcranAthlete):
    TYPES = ()
    TYPE_DEFAUT = "club_athle"
    COLONNES = ()

    def __init__(self, titre, sous_titre, athlete_id_initial=None, garder_athlete=False):
        super().__init__(titre, sous_titre, athlete_id_initial)
        if not garder_athlete:
            for i in range(self.barre.count()):
                w = self.barre.itemAt(i).widget()
                if w is not None:
                    w.hide()
        self.avertissement = QLabel("")
        self.avertissement.setWordWrap(True)
        self.avertissement.setObjectName("texteSecondaire")
        self.principal.addWidget(self.avertissement)
        f = QHBoxLayout()
        self.recherche = QLineEdit()
        self.recherche.setPlaceholderText("Rechercher (nom, commune, enseigne, pays, tes notes)")
        self.f_type = QComboBox()
        self.f_dep = QComboBox()
        self.f_cat = QComboBox()
        self.f_fav = QCheckBox("Mes favoris")
        f.addWidget(self.recherche, 3)
        for w in (self.f_type, self.f_dep, self.f_cat):
            f.addWidget(w, 1)
        f.addWidget(self.f_fav)
        self.principal.addLayout(f)
        b = QHBoxLayout()
        for texte, fn, p in (("➕ Ajouter", self._ajouter, True), ("✏️ Fiche", self._modifier, False),
                             ("⭐ Favori", self._favori, False), ("🌐 Site ou recherche", self._site, False),
                             ("✅ Vérifiée aujourd'hui", self._verifiee, False), ("🗑 Retirer", self._retirer, False),
                             ("📥 Importer un tableau", self._importer, False), ("📤 Exporter", self._exporter, False)):
            w = _bouton(texte, p)
            w.clicked.connect(fn)
            b.addWidget(w)
        b.addStretch()
        self.principal.addLayout(b)
        self.compte = QLabel("")
        self.compte.setObjectName("texteSecondaire")
        self.principal.addWidget(self.compte)
        self.table = QTableWidget(0, len(self.COLONNES))
        self.table.setHorizontalHeaderLabels(list(self.COLONNES))
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.verticalHeader().setVisible(False)
        self.table.setMinimumHeight(460)
        configurer_table_redimensionnable(self.table)
        self.table.cellDoubleClicked.connect(lambda _r, _c: self._modifier())
        self.table.itemSelectionChanged.connect(self._detail)
        self.principal.addWidget(self.table)
        cadre = QFrame()
        cadre.setObjectName("carteForm")
        lc = QVBoxLayout(cadre)
        self.label_detail = QLabel("Choisis une fiche pour voir le détail.")
        self.label_detail.setWordWrap(True)
        self.label_detail.setTextFormat(Qt.TextFormat.RichText)
        self.label_detail.setOpenExternalLinks(True)
        lc.addWidget(self.label_detail)
        self.principal.addWidget(cadre)
        self.principal.addStretch()
        self._toutes, self._vues = [], []
        self._preparer_filtres()
        self.recherche.textChanged.connect(lambda _t: self._remplir())
        for w in (self.f_type, self.f_dep, self.f_cat):
            w.currentIndexChanged.connect(lambda _i: self._remplir())
        self.f_fav.toggled.connect(lambda _b: self._remplir())
        self._finaliser()
        _style_cases(self)

    def _preparer_filtres(self):
        self.f_type.addItem("Tous les types", None)
        for t in self.TYPES:
            self.f_type.addItem(R.LIBELLE_TYPE[t], t)
        self.f_type.setVisible(len(self.TYPES) > 1)
        self.f_dep.addItem("Tous les départements", None)
        for c, n in R.DEPARTEMENTS:
            self.f_dep.addItem(f"{c} · {n}", c)
        self.f_cat.setVisible(False)

    def actualiser(self, *_):
        try:
            dan.synchroniser()
        except Exception:                          # la référence manque ou est abîmée : l'annuaire reste utilisable
            pass
        self._toutes = dan.fiches(self.TYPES)
        try:
            ref = R.lire_reference()
            texte = ref.get("avertissement_marques") if self.TYPES == ("marque",) else ref["avertissement"]
            self.avertissement.setText("ℹ️ " + (texte or ""))
        except (OSError, ValueError):
            self.avertissement.setText("")
        self._remplir()

    def _filtrees(self):
        t = self.f_type.currentData()
        return R.filtrer(self._toutes, types=(t,) if t else None, departement=self.f_dep.currentData(),
                         categorie=self.f_cat.currentData(), recherche=self.recherche.text(),
                         favoris=self.f_fav.isChecked())

    def _valeurs(self, f):
        return []

    def _remplir(self):
        self._vues = self._filtrees()
        t = self.table
        t.setRowCount(len(self._vues))
        for i, f in enumerate(self._vues):
            for j, v in enumerate(self._valeurs(f)):
                it = QTableWidgetItem(v)
                if j == 0 and f["favori"]:
                    it.setForeground(QColor("#F9A825"))
                t.setItem(i, j, it)
        t.resizeColumnsToContents()
        for j in range(t.columnCount()):
            if t.columnWidth(j) > 360:
                t.setColumnWidth(j, 360)
        self.compte.setText(f"{len(self._vues)} fiche(s) affichée(s) sur {len(self._toutes)}.")
        self._detail()

    def _courante(self):
        i = self.table.currentRow()
        return self._vues[i] if 0 <= i < len(self._vues) and self.table.selectedItems() else None

    def _detail(self):
        f = self._courante()
        if not f:
            self.label_detail.setText("Choisis une fiche pour voir le détail.")
            return
        e = html.escape
        lignes = [f"<b style='font-size:15px'>{'⭐ ' if f['favori'] else ''}{e(f['nom'])}</b>"
                  + (f" ({e(f['sigle'])})" if f.get("sigle") else "") + f" · {e(R.LIBELLE_TYPE[f['type']])}"]
        if f["type"] == "marque":
            lignes.append(" · ".join(x for x in (f.get("pays"), f.get("groupe") and f"groupe {f['groupe']}",
                                                 ", ".join(R.LIBELLE_CATEGORIE_MARQUE[c].split(' (')[0].lower()
                                                           for c in f["categories"])) if x))
        else:
            lieu = " ".join(x for x in (f.get("adresse"), f.get("code_postal"), f.get("commune")) if x)
            if lieu:
                lignes.append(e(lieu) + (f" · {e(R.NOM_DEPARTEMENT.get(f.get('departement'), ''))}"
                                         if f.get("departement") else ""))
            if f.get("enseigne"):
                lignes.append(f"Enseigne : {e(f['enseigne'])}" + (f" · {e(R.LIBELLE_CATEGORIE_MAGASIN.get(f.get('categorie'), ''))}"
                                                                  if f.get("categorie") else ""))
            if f.get("affiliation"):
                lignes.append(f"Fédération : {e(f['affiliation'])}")
        lien = f.get("site") or R.recherche_web(f)
        lignes.append(f"<a style='color:#4FC3F7' href='{e(lien)}'>{'Site internet' if f.get('site') else 'Chercher sur le web'}</a>")
        if f.get("notes"):
            lignes.append(f"<i>{e(f['notes'])}</i>")
        if f.get("mes_notes"):
            lignes.append(f"📝 {e(f['mes_notes'])}")
        lignes.append(f"<span style='color:#9E9E9E'>Source : {e(f.get('source') or '—')}"
                      + (f" · vérifiée le {e(f['verifie_le'])}" if f.get("verifie_le") else " · pas encore vérifiée")
                      + (" · corrigée par toi" if f.get("modifie") else "") + "</span>")
        self.label_detail.setText("<br>".join(lignes))

    # --- actions
    def _ajouter(self):
        if DialogueFiche(self, self.f_type.currentData() or self.TYPE_DEFAUT).exec():
            self.actualiser()

    def _modifier(self):
        f = self._courante()
        if f and DialogueFiche(self, f["type"], f).exec():
            self.actualiser()

    def _favori(self):
        f = self._courante()
        if f:
            dan.definir_favori(f["id"], not f["favori"])
            self.actualiser()

    def _site(self):
        f = self._courante()
        if f:
            QDesktopServices.openUrl(QUrl(f.get("site") or R.recherche_web(f)))

    def _verifiee(self):
        f = self._courante()
        if f:
            dan.marquer_verifiee(f["id"])
            self.actualiser()

    def _retirer(self):
        f = self._courante()
        if not f:
            return
        msg = (f"Retirer « {f['nom']} » de ton annuaire ? " + ("Fiche de la base livrée : elle est masquée et ne reviendra "
               "pas aux mises à jour." if f["reference"] else "Ta fiche sera supprimée."))
        if QMessageBox.question(self, "Retirer", msg) == QMessageBox.StandardButton.Yes:
            dan.supprimer(f["id"])
            self.actualiser()

    def _importer(self):
        chemin, _ = QFileDialog.getOpenFileName(self, "Importer un tableau", "", "Tableaux (*.csv *.txt)")
        if not chemin:
            return
        fiches, erreurs = R.lire_csv(Path(chemin).read_bytes())
        r = dan.importer(fiches)
        txt = f"{r['ajoutees']} fiche(s) ajoutée(s), {r['completees']} complétée(s)."
        if erreurs:
            txt += "\n\nÀ revoir :\n" + "\n".join(erreurs[:15])
        txt += ("\n\nColonnes reconnues : type (club, trail, école, section, organisateur, magasin, marque), nom, sigle, "
                "enseigne, categorie, commune, code_postal, adresse, site, affiliation, pays, categories.")
        QMessageBox.information(self, "Import", txt)
        self.actualiser()

    def _exporter(self):
        chemin, _ = QFileDialog.getSaveFileName(self, "Exporter", "Annuaire trail.csv", "CSV (*.csv)")
        if chemin:
            Path(chemin).write_text(R.vers_csv(self._vues), encoding="utf-8")
            QMessageBox.information(self, "Export", f"{len(self._vues)} fiche(s) exportée(s) (la liste affichée).")


class ClubsAnnuaire(_EcranAnnuaire):
    TYPES = R.TYPES_CLUBS
    COLONNES = ("Nom", "Sigle", "Type", "Commune", "Dép.", "Fédération", "Source")

    def __init__(self, athlete_id_initial=None):
        super().__init__("🏃  Clubs, écoles et sections trail", "Clubs d'athlétisme, de running et de trail, sections trail, "
                         "écoles de trail et organisateurs de courses.", athlete_id_initial)

    def _valeurs(self, f):
        return [f["nom"], f.get("sigle") or "", R.LIBELLE_TYPE[f["type"]], f.get("commune") or "—",
                f.get("departement") or "", f.get("affiliation") or "", (f.get("source") or "").split(" (")[0]]


class MagasinsAnnuaire(_EcranAnnuaire):
    TYPES = ("magasin",)
    TYPE_DEFAUT = "magasin"
    COLONNES = ("Magasin", "Enseigne", "Catégorie", "Adresse", "Commune", "Dép.")

    def __init__(self, athlete_id_initial=None):
        super().__init__("🏬  Magasins", "Spécialistes running et trail, magasins outdoor et grandes surfaces de sport "
                         "avec un rayon running.", athlete_id_initial)

    def _preparer_filtres(self):
        super()._preparer_filtres()
        self.f_cat.addItem("Toutes les catégories", None)
        for c, l in R.CATEGORIES_MAGASIN:
            self.f_cat.addItem(l, c)
        self.f_cat.setVisible(True)
        self.f_cat.setCurrentIndex(0)

    def _valeurs(self, f):
        return [f["nom"], f.get("enseigne") or "", R.LIBELLE_CATEGORIE_MAGASIN.get(f.get("categorie"), ""),
                f.get("adresse") or "", f.get("commune") or "", f.get("departement") or ""]


class MarquesAnnuaire(_EcranAnnuaire):
    TYPES = ("marque",)
    TYPE_DEFAUT = "marque"
    COLONNES = ("Marque", "Pays", "Produits", "Groupe", "Dans ton matériel")

    def __init__(self, athlete_id_initial=None):
        super().__init__("🏷️  Marques", "Chaussures, textile, sacs, bâtons, frontales, montres, nutrition et accessoires. "
                         "Elles sont proposées quand tu saisis ton matériel.", athlete_id_initial, garder_athlete=True)

    def _preparer_filtres(self):
        super()._preparer_filtres()
        self.f_dep.setVisible(False)
        self.f_cat.addItem("Tous les produits", None)
        for c, l in R.CATEGORIES_MARQUE:
            self.f_cat.addItem(l.split(" (")[0], c)
        self.f_cat.setVisible(True)

    def actualiser(self, *_):
        self._chez_moi = dan.materiel_par_marque(self.combo_athlete.currentData())
        super().actualiser()

    def _valeurs(self, f):
        n = {k.lower(): v for k, v in (self._chez_moi or {}).items()}.get(f["nom"].lower())
        return [f["nom"], f.get("pays") or "", ", ".join(R.LIBELLE_CATEGORIE_MARQUE[c].split(" (")[0].lower()
                                                           for c in f["categories"]),
                f.get("groupe") or "", f"{n} objet(s)" if n else ""]


class AnnuaireFenetre(ConteneurOnglets):

    def __init__(self, athlete_id_initial=None):
        super().__init__(titre="Annuaire trail",
                         onglets=[("🏃 Clubs et écoles", ClubsAnnuaire), ("🏬 Magasins", MagasinsAnnuaire),
                                  ("🏷️ Marques", MarquesAnnuaire)],
                         athlete_id_initial=athlete_id_initial)
        self.clubs, self.magasins, self.marques = self.ecrans
