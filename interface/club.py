"""
Espace Club (Trail Hub Center, étape 4.1) : le club, ses adhérents et
leurs licences FFA, les cotisations, les groupes, l'import HelloAsso ou
SI-FFA. Un adhérent est une fiche Personne avec le rôle « licencié » : la
même personne peut être coureur dans Trail Hub, parent d'un enfant du club
ou bénévole, sans être saisie deux fois.

Fenêtre « 🏟️ Club », six onglets : Tableau de bord, Adhérents, Groupes,
Cotisations, Import, Le club. Aucune requête SQL ici : tout passe par
noyau/donnees/club.py et noyau/donnees/personnes.py.
"""

import html
from datetime import date
from pathlib import Path

from PySide6.QtCore import Qt, QDate, QLocale
from PySide6.QtGui import QColor, QGuiApplication
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QDateEdit, QDialog, QDialogButtonBox, QDoubleSpinBox, QFileDialog,
    QFormLayout, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMessageBox,
    QPushButton, QTableWidget, QTableWidgetItem, QTextEdit, QVBoxLayout,
)

from noyau.donnees import club as dclub, personnes as dper
from noyau.club import categories as cat, adhesions as regles, imports as imp
from interface.conteneur_onglets import ConteneurOnglets
from interface.ecran_liste import configurer_table_redimensionnable, obtenir_style_ecran
from interface.forme_evolution import _EcranAthlete

FRANCAIS = QLocale(QLocale.Language.French, QLocale.Country.France)
VERT, ORANGE, ROUGE, GRIS = "#2E7D32", "#E65100", "#C62828", "#757575"


def _euros(v):
    t = f"{v or 0:,.2f}".replace(",", " ").replace(".", ",")
    return (t[:-3] if t.endswith(",00") else t) + " €"


def _jour(d):
    try:
        return date.fromisoformat(str(d)[:10]).strftime("%d/%m/%Y") if d else ""
    except ValueError:
        return str(d)


NOMS_CHAMPS = {"nom": "nom", "prenom": "prénom", "date_naissance": "naissance", "sexe": "sexe", "email": "e-mail",
               "telephone": "téléphone", "adresse": "adresse", "code_postal": "code postal", "ville": "ville",
               "numero_licence": "n° de licence", "type_licence": "licence", "cotisation": "montant",
               "paiement_date": "date du paiement", "paiement_mode": "mode de paiement",
               "contact_urgence_nom": "personne à prévenir", "contact_urgence_tel": "son téléphone",
               "statut_commande": "statut de la commande"}


def _court(manque):
    """Version courte d'un manque du dossier pour la colonne du tableau."""
    return {"pièce de santé (certificat ou questionnaire)": "santé", "numéro de licence FFA": "n° de licence",
            "montant de la cotisation": "montant"}.get(manque, manque)


def _bouton(texte, principal=False):
    b = QPushButton(texte)
    b.setObjectName("boutonPrincipal" if principal else "boutonSecondaire")
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    return b


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


def _montant():
    s = QDoubleSpinBox()
    s.setLocale(FRANCAIS)
    s.setRange(0, 10000)
    s.setDecimals(2)
    s.setSuffix(" €")
    return s


def _date_facultative(valeur=None):
    """(case à cocher, champ date) : la case décochée = pas de date."""
    case = QCheckBox()
    champ = QDateEdit(QDate.currentDate())
    champ.setCalendarPopup(True)
    champ.setDisplayFormat("dd/MM/yyyy")
    if valeur:
        case.setChecked(True)
        champ.setDate(QDate.fromString(str(valeur)[:10], "yyyy-MM-dd"))
    champ.setEnabled(case.isChecked())
    case.toggled.connect(champ.setEnabled)
    return case, champ


def _valeur_date(case, champ):
    return champ.date().toString("yyyy-MM-dd") if case.isChecked() else None


def _style_cases(widget):
    from interface.theme import PALETTE, obtenir_couleur_accent
    accent = obtenir_couleur_accent()
    widget.setStyleSheet(widget.styleSheet() + (
        " QCheckBox { background: transparent; spacing: 8px; }"
        f" QCheckBox::indicator {{ width: 16px; height: 16px; border: 1px solid {PALETTE['texte_discret']};"
        f" border-radius: 4px; background: {PALETTE['carte_haute']}; }}"
        f" QCheckBox::indicator:checked {{ background: {accent}; border-color: {accent}; }}"
        f" QCheckBox::indicator:indeterminate {{ background: {PALETTE['texte_discret']}; }}"))


# ======================================================================
# Base des onglets : un sélecteur de saison au lieu de l'athlète
# ======================================================================

class _EcranClub(_EcranAthlete):

    def __init__(self, titre, sous_titre, athlete_id_initial=None):
        super().__init__(titre, sous_titre, athlete_id_initial)
        for i in range(self.barre.count()):
            w = self.barre.itemAt(i).widget()
            if w is not None:
                w.hide()
        self.combo_club = QComboBox()
        self.combo_club.setMinimumWidth(220)
        self.combo_club.setToolTip("Association : chacune a ses adhérents, groupes, tarifs, reçus et agenda")
        self.combo_section = QComboBox()
        self.combo_section.setToolTip("Section de l'association (ou toute l'association)")
        self.combo_saison = QComboBox()
        self.barre.insertWidget(0, QLabel("🏟️"))
        self.barre.insertWidget(1, self.combo_club)
        self.barre.insertWidget(2, self.combo_section)
        self.barre.insertWidget(3, QLabel("Saison :"))
        self.barre.insertWidget(4, self.combo_saison)

    def _finaliser(self):
        self._ajouter_carte_ia()
        self.setStyleSheet(obtenir_style_ecran() + "#carteForm QLabel { background: transparent; }")
        _style_cases(self)
        self._remplir_saisons()
        self.combo_saison.currentIndexChanged.connect(lambda _i: self.actualiser())
        self.combo_club.currentIndexChanged.connect(self._club_change)
        self.combo_section.currentIndexChanged.connect(self._section_change)
        self.actualiser()

    @property
    def club_id(self):
        return dclub.club_id_ou_creer()

    @property
    def section_id(self):
        return self.combo_section.currentData()

    def adhesions(self, saison=None):
        """Adhésions de l'association courante, limitées à la section choisie."""
        return dclub.adhesions(self.club_id, saison or self.saison, section_id=self.section_id)

    def groupes_visibles(self, avec_inactifs=False):
        return dclub.groupes(self.club_id, avec_inactifs, self.section_id)

    def dans_section(self, seance):
        """Une séance de l'agenda appartient à la section choisie (séance sans groupe : toute l'association)."""
        if not self.section_id or not seance.get("groupe_id"):
            return True
        return seance["groupe_id"] in {g["id"] for g in self.groupes_visibles(True)}

    def _club_change(self, _i=None):
        cid = self.combo_club.currentData()
        if cid and cid != dclub.club_courant_id():
            dclub.choisir_club(cid)
        self._tout_rafraichir()

    def _section_change(self, _i=None):
        dclub.choisir_section(self.club_id, self.section_id)
        self._tout_rafraichir()

    def _tout_rafraichir(self):
        f = self._fenetre()
        for e in (f.ecrans if f else [self]):
            e._remplir_saisons()
            e.actualiser()

    @property
    def saison(self):
        return self.combo_saison.currentData() or cat.saison_de()

    def _remplir_saisons(self):
        actuelle = self.combo_saison.currentData()
        s = dclub.saisons(self.club_id)
        suivante = cat.saison_suivante(cat.saison_de())
        if suivante not in s and date.today().month >= 6:
            s.insert(0, suivante)
        self.combo_saison.blockSignals(True)
        self.combo_saison.clear()
        for x in s:
            self.combo_saison.addItem(x + ("  (en cours)" if x == cat.saison_de() else ""), x)
        i = self.combo_saison.findData(actuelle or cat.saison_de())
        self.combo_saison.setCurrentIndex(max(0, i))
        self.combo_saison.blockSignals(False)
        cid = self.club_id
        self.combo_club.blockSignals(True)
        self.combo_club.clear()
        for c in dclub.clubs():
            self.combo_club.addItem(c["nom"], c["id"])
        self.combo_club.setCurrentIndex(max(0, self.combo_club.findData(cid)))
        self.combo_club.blockSignals(False)
        self.combo_section.blockSignals(True)
        self.combo_section.clear()
        secs = dclub.sections(cid)
        self.combo_section.addItem("Toute l'association", None)
        for x in secs:
            self.combo_section.addItem(f"Section {x['nom']}", x["id"])
        self.combo_section.setCurrentIndex(max(0, self.combo_section.findData(dclub.section_courante(cid))))
        self.combo_section.setVisible(bool(secs))
        self.combo_section.blockSignals(False)

    def showEvent(self, e):
        super().showEvent(e)
        if getattr(self, "_vu", False):
            self._remplir_saisons()
            self.actualiser()
        self._vu = True

    def _fenetre(self):
        w = self.parent()
        while w is not None and not isinstance(w, ClubFenetre):
            w = w.parent()
        return w


# ======================================================================
# Fiche adhérent (personne + adhésion de la saison + groupes)
# ======================================================================

class DialogueAdherent(QDialog):

    def __init__(self, parent, club_id, saison, adhesion=None):
        super().__init__(parent)
        self.club_id, self.saison, self.adh = club_id, saison, adhesion
        self.personne_id = adhesion["personne_id"] if adhesion else None
        self.setWindowTitle(("Adhérent — " if adhesion else "Nouvel adhérent — ") + saison)
        self.setStyleSheet(obtenir_style_ecran())
        _style_cases(self)
        self.resize(980, 760)
        a = adhesion or {}
        f = dper.fiche(self.personne_id) if self.personne_id else {}
        lay = QVBoxLayout(self)
        if not adhesion:
            ligne = QHBoxLayout()
            self.combo_existant = QComboBox()
            self.combo_existant.addItem("— nouvelle personne —", None)
            deja = {x["personne_id"] for x in dclub.adhesions(club_id, saison)}           # toute l'association
            for p in dper.lister():
                if p["id"] not in deja:
                    self.combo_existant.addItem(f"{p['nom']} {p['prenom']}" + (f" ({p['age']} ans)" if p["age"] else "")
                                                + (" · " + ", ".join(dper.LIBELLE_ROLE[r] for r in p["roles"]) if p["roles"] else ""),
                                                p["id"])
            self.combo_existant.currentIndexChanged.connect(self._personne_existante)
            ligne.addWidget(QLabel("Déjà dans Trail Hub :"))
            ligne.addWidget(self.combo_existant, 1)
            lay.addLayout(ligne)
        grille = QGridLayout()
        grille.setHorizontalSpacing(24)
        # --- la personne
        fp = QFormLayout()
        self.nom, self.prenom = QLineEdit(f.get("nom") or ""), QLineEdit(f.get("prenom") or "")
        self.c_naiss, self.naissance = _date_facultative(f.get("date_naissance"))
        self.naissance.setMinimumDate(QDate(1900, 1, 1))
        self.naissance.setMaximumDate(QDate.currentDate())
        ln = QHBoxLayout()
        ln.addWidget(self.c_naiss)
        ln.addWidget(self.naissance, 1)
        self.label_cat = QLabel("")
        self.label_cat.setObjectName("texteSecondaire")
        ln.addWidget(self.label_cat)
        self.sexe = QComboBox()
        for code, lib in ((None, "—"), ("F", "Femme"), ("H", "Homme")):
            self.sexe.addItem(lib, code)
        self.sexe.setCurrentIndex(max(0, self.sexe.findData(f.get("sexe"))))
        self.email, self.tel = QLineEdit(f.get("email") or ""), QLineEdit(f.get("telephone") or "")
        self.adresse, self.cp, self.ville = (QLineEdit(f.get("adresse") or ""), QLineEdit(f.get("code_postal") or ""),
                                             QLineEdit(f.get("ville") or ""))
        self.urg_nom, self.urg_tel = QLineEdit(f.get("contact_urgence_nom") or ""), QLineEdit(f.get("contact_urgence_tel") or "")
        for lib, w in (("Nom", self.nom), ("Prénom", self.prenom), ("Naissance", ln), ("Sexe", self.sexe),
                       ("E-mail", self.email), ("Téléphone", self.tel), ("Adresse", self.adresse),
                       ("Code postal", self.cp), ("Ville", self.ville), ("À prévenir", self.urg_nom),
                       ("Son téléphone", self.urg_tel)):
            fp.addRow(lib, w)
        # --- l'adhésion
        fa = QFormLayout()
        self.type_lic = QComboBox()
        self.type_lic.addItem("—", None)
        for code, lib, _c in cat.TYPES_LICENCE:
            self.type_lic.addItem(lib, code)
        self.type_lic.setCurrentIndex(max(0, self.type_lic.findData(a.get("type_licence"))))
        self.num_lic = QLineEdit(a.get("numero_licence") or "")
        self.num_lic.setPlaceholderText("donné par la FFA à la prise de licence")
        self.c_dlic, self.date_lic = _date_facultative(a.get("date_licence"))
        ldl = QHBoxLayout()
        ldl.addWidget(self.c_dlic)
        ldl.addWidget(self.date_lic, 1)
        self.statut = QComboBox()
        for code, lib in regles.STATUTS:
            self.statut.addItem(lib, code)
        self.statut.setCurrentIndex(max(0, self.statut.findData(a.get("statut") or "en_cours")))
        self.sante = QComboBox()
        self.sante.addItem("— pas encore fournie —", None)
        for code, lib in regles.SANTE:
            self.sante.addItem(lib, code)
        self.sante.setCurrentIndex(max(0, self.sante.findData(a.get("sante_type"))))
        self.c_dsante, self.date_sante = _date_facultative(a.get("sante_date"))
        lds = QHBoxLayout()
        lds.addWidget(self.c_dsante)
        lds.addWidget(self.date_sante, 1)
        self.autorisation = QCheckBox("Autorisation parentale signée")
        self.autorisation.setChecked(bool(a.get("autorisation_parentale")))
        self.image = QCheckBox("Droit à l'image accordé")
        self.image.setTristate(True)
        di = a.get("droit_image")
        self.image.setCheckState(Qt.CheckState.PartiallyChecked if di is None else
                                 Qt.CheckState.Checked if di else Qt.CheckState.Unchecked)
        self.tarif = QComboBox()
        self.tarif.addItem("— tarif —", None)
        self.section = QComboBox()
        self.section.addItem("Toute l'association", None)
        for x in dclub.sections(club_id):
            self.section.addItem(x["nom"], x["id"])
        self.section.setCurrentIndex(max(0, self.section.findData(a.get("section_id") if adhesion
                                                                 else getattr(parent, "section_id", None))))
        self._tarifs = dclub.tarifs_de(club_id, saison, self.section.currentData())
        for t in self._tarifs:
            self.tarif.addItem(f"{t['libelle']} ({_euros(t['montant'])})", t["libelle"])
        if a.get("tarif") and self.tarif.findData(a["tarif"]) < 0:
            self.tarif.addItem(a["tarif"], a["tarif"])
        self.tarif.setCurrentIndex(max(0, self.tarif.findData(a.get("tarif"))))
        self.cotisation, self.paye = _montant(), _montant()
        self.cotisation.setValue(a.get("cotisation") or 0)
        self.paye.setValue(a.get("montant_paye") or 0)
        self.mode = QComboBox()
        self.mode.addItem("—", None)
        self.mode.addItems(regles.MODES_PAIEMENT)
        if a.get("paiement_mode"):
            if self.mode.findText(a["paiement_mode"]) < 0:
                self.mode.addItem(a["paiement_mode"])
            self.mode.setCurrentText(a["paiement_mode"])
        self.c_dpay, self.date_pay = _date_facultative(a.get("paiement_date"))
        ldp = QHBoxLayout()
        ldp.addWidget(self.c_dpay)
        ldp.addWidget(self.date_pay, 1)
        self.notes = QLineEdit(a.get("notes") or "")
        if self.section.count() > 1:
            fa.addRow("Section", self.section)
        for lib, w in (("Licence", self.type_lic), ("N° de licence", self.num_lic), ("Prise de licence", ldl),
                       ("Statut", self.statut), ("Santé", self.sante), ("Date de la pièce", lds), ("", self.autorisation),
                       ("", self.image), ("Tarif", self.tarif), ("Cotisation", self.cotisation), ("Déjà payé", self.paye),
                       ("Paiement", self.mode), ("Date du paiement", ldp), ("Notes", self.notes)):
            fa.addRow(lib, w)
        t1, t2 = QLabel("La personne"), QLabel(f"Son adhésion {saison}")
        t1.setObjectName("titreCarte")
        t2.setObjectName("titreCarte")
        grille.addWidget(t1, 0, 0)
        grille.addWidget(t2, 0, 1)
        grille.addLayout(fp, 1, 0)
        grille.addLayout(fa, 1, 1)
        lay.addLayout(grille)
        tg = QLabel("Groupes")
        tg.setObjectName("titreCarte")
        lay.addWidget(tg)
        self.liste_groupes = QListWidget()
        self.liste_groupes.setMaximumHeight(64)
        self.liste_groupes.setFlow(QListWidget.Flow.LeftToRight)
        self.liste_groupes.setWrapping(True)
        mes = set(dclub.groupes_de(self.personne_id)) if self.personne_id else set()
        for g in dclub.groupes(club_id):
            it = QListWidgetItem(g["nom"])
            it.setData(Qt.ItemDataRole.UserRole, g["id"])
            it.setFlags(it.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            it.setCheckState(Qt.CheckState.Checked if g["id"] in mes else Qt.CheckState.Unchecked)
            self.liste_groupes.addItem(it)
        if not self.liste_groupes.count():
            lay.addWidget(QLabel("Pas encore de groupe : crée-les dans l'onglet Groupes."))
        else:
            lay.addWidget(self.liste_groupes)
        self.label_dossier = QLabel("")
        self.label_dossier.setWordWrap(True)
        self.label_dossier.setTextFormat(Qt.TextFormat.RichText)
        lay.addWidget(self.label_dossier)
        boutons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        boutons.button(QDialogButtonBox.StandardButton.Save).setText("Enregistrer")
        boutons.button(QDialogButtonBox.StandardButton.Cancel).setText("Annuler")
        boutons.accepted.connect(self.accept)
        boutons.rejected.connect(self.reject)
        lay.addWidget(boutons)
        self.tarif.currentIndexChanged.connect(self._tarif_choisi)
        for w in (self.type_lic, self.sante, self.statut):
            w.currentIndexChanged.connect(lambda _i: self._etat())
        for w in (self.num_lic,):
            w.textChanged.connect(lambda _t: self._etat())
        for w in (self.cotisation, self.paye):
            w.valueChanged.connect(lambda _v: self._etat())
        self.c_naiss.toggled.connect(lambda _b: self._etat())
        self.naissance.dateChanged.connect(lambda _d: self._etat())
        self.autorisation.toggled.connect(lambda _b: self._etat())
        self.type_lic.currentIndexChanged.connect(self._tarif_par_licence)
        self._etat()

    def _personne_existante(self):
        pid = self.combo_existant.currentData()
        f = dper.fiche(pid) if pid else {}
        for w, k in ((self.nom, "nom"), (self.prenom, "prenom"), (self.email, "email"), (self.tel, "telephone"),
                     (self.adresse, "adresse"), (self.cp, "code_postal"), (self.ville, "ville"),
                     (self.urg_nom, "contact_urgence_nom"), (self.urg_tel, "contact_urgence_tel")):
            w.setText(f.get(k) or "")
        self.sexe.setCurrentIndex(max(0, self.sexe.findData(f.get("sexe"))))
        self.c_naiss.setChecked(bool(f.get("date_naissance")))
        if f.get("date_naissance"):
            self.naissance.setDate(QDate.fromString(f["date_naissance"], "yyyy-MM-dd"))
        self.personne_id = pid
        # ses groupes et sa dernière adhésion, pour un renouvellement rapide
        if pid:
            mes = set(dclub.groupes_de(pid))
            for i in range(self.liste_groupes.count()):
                it = self.liste_groupes.item(i)
                it.setCheckState(Qt.CheckState.Checked if it.data(Qt.ItemDataRole.UserRole) in mes else Qt.CheckState.Unchecked)
            avant = dclub.adhesions_de_la_personne(pid)
            if avant:
                self.type_lic.setCurrentIndex(max(0, self.type_lic.findData(avant[0]["type_licence"])))
                self.num_lic.setText(avant[0]["numero_licence"] or "")
        self._etat()

    def _tarif_choisi(self):
        lib = self.tarif.currentData()
        t = next((x for x in self._tarifs if x["libelle"] == lib), None)
        if t:
            self.cotisation.setValue(t["montant"])

    def _tarif_par_licence(self):
        if self.tarif.currentData() is None:
            t = regles.tarif_pour(self._tarifs, self.type_lic.currentData())
            if t:
                self.tarif.setCurrentIndex(max(0, self.tarif.findData(t["libelle"])))

    def personne(self):
        return {"nom": self.nom.text().strip(), "prenom": self.prenom.text().strip(),
                "date_naissance": _valeur_date(self.c_naiss, self.naissance), "sexe": self.sexe.currentData(),
                "email": self.email.text().strip() or None, "telephone": self.tel.text().strip() or None,
                "adresse": self.adresse.text().strip() or None, "code_postal": self.cp.text().strip() or None,
                "ville": self.ville.text().strip() or None, "contact_urgence_nom": self.urg_nom.text().strip() or None,
                "contact_urgence_tel": self.urg_tel.text().strip() or None}

    def adhesion(self):
        st = self.image.checkState()
        return {"type_licence": self.type_lic.currentData(), "numero_licence": self.num_lic.text().strip() or None,
                "date_licence": _valeur_date(self.c_dlic, self.date_lic), "statut": self.statut.currentData(),
                "sante_type": self.sante.currentData(), "sante_date": _valeur_date(self.c_dsante, self.date_sante),
                "autorisation_parentale": 1 if self.autorisation.isChecked() else 0,
                "droit_image": None if st == Qt.CheckState.PartiallyChecked else (1 if st == Qt.CheckState.Checked else 0),
                "tarif": self.tarif.currentData(), "cotisation": self.cotisation.value(),
                "montant_paye": self.paye.value(), "paiement_mode": self.mode.currentData() if self.mode.currentIndex() > 0
                and self.mode.currentData() else (self.mode.currentText() if self.mode.currentIndex() > 0 else None),
                "paiement_date": _valeur_date(self.c_dpay, self.date_pay), "notes": self.notes.text().strip(),
                "section_id": self.section.currentData()}

    def groupes(self):
        return [self.liste_groupes.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.liste_groupes.count())
                if self.liste_groupes.item(i).checkState() == Qt.CheckState.Checked]

    def _etat(self):
        p, a = self.personne(), self.adhesion()
        c = cat.categorie(p["date_naissance"], self.saison)
        self.label_cat.setText(f"{c['libelle']} ({c['code']}, {c['u']})" if c else "")
        mineur = dper.est_mineur(p["date_naissance"])
        self.autorisation.setVisible(mineur)
        d = regles.dossier({**a, **p, "mineur": mineur, "saison": self.saison}, self.saison)
        if d["complet"]:
            txt = f"<b style='color:{VERT}'>Dossier complet.</b>"
        else:
            txt = f"<b style='color:{ORANGE}'>Il manque :</b> " + ", ".join(html.escape(m) for m in d["manques"]) + "."
        if d["avertissements"]:
            txt += "<br><span style='color:#9E9E9E'>" + " ".join(html.escape(x[0].upper() + x[1:].rstrip(".")) + "."
                                                                for x in d["avertissements"]) + "</span>"
        self.label_dossier.setText(txt)

    def accept(self):
        p = self.personne()
        if not p["nom"]:
            QMessageBox.warning(self, "Adhérent", "Le nom est obligatoire.")
            return
        try:
            if self.personne_id is None:
                doublons = dper.doublons_possibles(p["nom"], p["prenom"], p["date_naissance"])
                if doublons:
                    d = doublons[0]
                    rep = QMessageBox.question(
                        self, "Personne déjà connue",
                        f"{d['prenom']} {d['nom']} existe déjà dans Trail Hub. Utiliser sa fiche (recommandé, "
                        "pas de doublon) ?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
                        | QMessageBox.StandardButton.Cancel)
                    if rep == QMessageBox.StandardButton.Cancel:
                        return
                    if rep == QMessageBox.StandardButton.Yes:
                        self.personne_id = d["id"]
            if self.personne_id is None:
                self.personne_id = dper.creer(p, ["licencie"])
            else:
                dper.modifier(self.personne_id, p)
            dclub.enregistrer_adhesion(self.club_id, self.personne_id, self.saison, self.adhesion(),
                                       self.adh["id"] if self.adh else None, (self.adh or {}).get("maj"))
            dclub.definir_groupes(self.personne_id, self.groupes(), self.club_id)
        except (dper.ErreurPersonne, dclub.ErreurClub) as e:
            QMessageBox.warning(self, "Adhérent", str(e))
            return
        super().accept()


# ======================================================================
# Onglet 1 — Tableau de bord
# ======================================================================

class TableauDeBordClub(_EcranClub):

    def __init__(self, athlete_id_initial=None):
        super().__init__("🏟️  Club : tableau de bord",
                         "La saison d'un coup d'œil : effectif, catégories, dossiers à compléter, cotisations, "
                         "renouvellements.", athlete_id_initial)
        ligne = QHBoxLayout()
        ligne.setSpacing(15)
        self.cartes = {}
        for cle, titre in (("effectif", "Adhérents"), ("renouv", "Renouvellements"), ("incomplets", "Dossiers incomplets"),
                           ("cotis", "Cotisations encaissées"), ("mineurs", "Jeunes (moins de 18 ans)")):
            self.cartes[cle] = self._carte(titre)
            ligne.addWidget(self.cartes[cle], 1)
        self.principal.addLayout(ligne)
        cadre, lc = _cadre("À faire")
        self.label_alertes = QLabel("")
        self.label_alertes.setWordWrap(True)
        self.label_alertes.setTextFormat(Qt.TextFormat.RichText)
        lc.addWidget(self.label_alertes)
        self.principal.addWidget(cadre)
        cadre, lc = _cadre("Prochaines séances")
        self.table_proch = _table(["Date", "Horaire", "Séance", "Groupe", "Lieu", "Entraîneur"], 150)
        lc.addWidget(self.table_proch)
        self.principal.addWidget(cadre)
        lignes = QHBoxLayout()
        cadre, lc = _cadre("Par catégorie FFA")
        self.table_cat = _table(["Catégorie", "Nés", "Femmes", "Hommes", "Total"], 200)
        self.table_cat.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        lc.addWidget(self.table_cat)
        lignes.addWidget(cadre, 3)
        cadre, lc = _cadre("Par licence")
        self.table_lic = _table(["Licence", "Adhérents"], 200)
        lc.addWidget(self.table_lic)
        lignes.addWidget(cadre, 2)
        self.principal.addLayout(lignes)
        cadre, lc = _cadre("Pas encore renouvelés (adhérents de la saison précédente)")
        self.table_nr = _table(["Nom", "Prénom", "Catégorie", "Licence", "E-mail", "Téléphone"], 150)
        self.table_nr.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        lc.addWidget(self.table_nr)
        b = QHBoxLayout()
        r1 = _bouton("🔁 Renouveler la sélection")
        r1.clicked.connect(lambda: self._renouveler(True))
        r2 = _bouton("🔁 Renouveler tout le monde")
        r2.clicked.connect(lambda: self._renouveler(False))
        cp = _bouton("✉️ Copier leurs e-mails")
        cp.clicked.connect(self._copier_emails)
        for w in (r1, r2, cp):
            b.addWidget(w)
        b.addStretch()
        lc.addLayout(b)
        self.principal.addWidget(cadre)
        self.principal.addStretch()
        self._nr = []
        self._finaliser()

    def actualiser(self):
        s = self.saison
        adh = self.adhesions(s)
        prec = self.adhesions(cat.saison_precedente(s))
        ch = regles.chiffres(adh, prec, s)
        c = self.cartes
        c["effectif"].valeur.setText(str(ch["effectif"]))
        c["effectif"].detail.setText(f"{ch['nouveaux']} nouveau{'x' if ch['nouveaux'] > 1 else ''} · {ch['sexes'].get('F', 0)} femmes, "
                                     f"{ch['sexes'].get('H', 0)} hommes")
        c["renouv"].valeur.setText(f"{ch['taux_renouvellement']} %" if ch["taux_renouvellement"] is not None else "—")
        c["renouv"].detail.setText(f"{ch['renouveles']} sur {len(prec)} de {cat.saison_precedente(s)}" if prec else
                                   "pas d'adhérents la saison précédente")
        c["incomplets"].valeur.setText(str(ch["incomplets"]))
        c["incomplets"].detail.setText("licence, santé, autorisation ou paiement")
        c["cotis"].valeur.setText(_euros(ch["cotisations_payees"]))
        c["cotis"].detail.setText(f"sur {_euros(ch['cotisations_dues'])} · reste {_euros(ch['reste'])}")
        c["mineurs"].valeur.setText(str(ch["mineurs"]))
        c["mineurs"].detail.setText("autorisation parentale obligatoire")
        al = regles.alertes(adh, ch, s)
        from noyau.donnees import agenda_club as dag
        from noyau.club import agenda as ag
        from datetime import timedelta
        if s == cat.saison_de():
            auj = date.today()
            assid = dag.assiduite(self.club_id, auj - timedelta(days=60), auj)
            noms = {pid: f"{r.get('prenom', '')} {r.get('nom', '')}".strip() for pid, r in assid.items()}
            if self.section_id:
                membres = {a["personne_id"] for a in adh}
                assid = {pid: r for pid, r in assid.items() if pid in membres}
                noms = {pid: n for pid, n in noms.items() if pid in membres}
            al += ag.alertes_presences(assid, noms, len([x for x in dag.sans_appel(self.club_id) if self.dans_section(x)]))
        from interface.club_agenda import _date_courte, _horaire
        proch = [x for x in dag.prochaines(self.club_id, 12) if self.dans_section(x)][:6]
        tp = self.table_proch
        tp.setRowCount(len(proch))
        for i, x in enumerate(proch):
            for j, v in enumerate((_date_courte(x["date"]), _horaire(x), x["titre"], x["groupe"] or "Tout le club",
                                   x["lieu"] or "", x["entraineur"] or "")):
                tp.setItem(i, j, QTableWidgetItem(v))
        tp.resizeColumnsToContents()
        self.label_alertes.setText("<ul>" + "".join(f"<li>{html.escape(x)}</li>" for x in al) + "</ul>" if al
                                   else f"<span style='color:{VERT}'>Rien à signaler pour {s}.</span>")
        # catégories
        t = self.table_cat
        par = {}
        for a in adh:
            if a["statut"] == "annulee":
                continue
            code = a["categorie"]["code"] if a["categorie"] else "?"
            par.setdefault(code, {"F": 0, "H": 0, "?": 0})
            par[code][(a["sexe"] or "?")[:1] if (a["sexe"] or "?")[:1] in "FH" else "?"] += 1
        codes = sorted(par, key=lambda x: cat.ORDRE.get(x, 99))
        t.setRowCount(len(codes))
        for i, code in enumerate(codes):
            if code in cat.LIBELLE:
                deb, fin = cat.annees_de_la_categorie(code, s)
                nes = (f"{deb}–{fin}" if deb and fin else f"{fin} et avant" if fin else f"{deb} et après")
            else:
                nes = "date inconnue"
            n = par[code]
            for j, v in enumerate((cat.LIBELLE.get(code, "Inconnue"), nes, str(n["F"]), str(n["H"]),
                                   str(n["F"] + n["H"] + n["?"]))):
                t.setItem(i, j, QTableWidgetItem(v))
        t.resizeColumnsToContents()
        t.setFixedHeight(max(200, t.horizontalHeader().height() + sum(t.rowHeight(i) for i in range(t.rowCount())) + 6))
        t2 = self.table_lic
        lic = sorted(ch["licences"].items(), key=lambda x: -x[1])
        t2.setRowCount(len(lic))
        for i, (code, n) in enumerate(lic):
            t2.setItem(i, 0, QTableWidgetItem(cat.LIBELLE_LICENCE.get(code, "Non renseignée")))
            t2.setItem(i, 1, QTableWidgetItem(str(n)))
        t2.resizeColumnsToContents()
        # non renouvelés
        nr = set(ch.get("non_renouveles") or [])
        self._nr = [a for a in prec if a["personne_id"] in nr]
        t3 = self.table_nr
        t3.setRowCount(len(self._nr))
        for i, a in enumerate(self._nr):
            c2 = cat.categorie(a["date_naissance"], s)
            for j, v in enumerate((a["nom"], a["prenom"], c2["code"] if c2 else "", cat.LIBELLE_LICENCE.get(a["type_licence"], ""),
                                   a["email"] or "", a["telephone"] or "")):
                t3.setItem(i, j, QTableWidgetItem(v))
        t3.resizeColumnsToContents()

    def _renouveler(self, selection):
        if selection:
            lignes = sorted({i.row() for i in self.table_nr.selectedIndexes()})
            ids = {self._nr[l]["personne_id"] for l in lignes if l < len(self._nr)}
            if not ids:
                QMessageBox.information(self, "Renouveler", "Sélectionne d'abord des adhérents dans la liste.")
                return
        else:
            ids = None
        n = dclub.renouveler(self.club_id, cat.saison_precedente(self.saison), self.saison, ids)
        QMessageBox.information(self, "Renouveler", f"{n} adhésion(s) créée(s) pour {self.saison}, avec la même licence "
                                "et le tarif de la saison. Santé, autorisation parentale et paiement sont à compléter.")
        self.actualiser()

    def _copier_emails(self):
        emails = sorted({a["email"] for a in self._nr if a.get("email")})
        QGuiApplication.clipboard().setText("; ".join(emails))
        QMessageBox.information(self, "E-mails", f"{len(emails)} adresse(s) copiée(s) : colle-les dans ton message "
                                "(en copie cachée).")


# ======================================================================
# Onglet 2 — Adhérents
# ======================================================================

class AdherentsClub(_EcranClub):
    COLONNES = ["Nom", "Prénom", "Cat.", "Licence", "N° licence", "Groupes", "Santé", "Cotisation", "Dossier"]

    def __init__(self, athlete_id_initial=None):
        super().__init__("👥  Adhérents", "Les licenciés et adhérents de la saison, leur dossier et leur cotisation. "
                         "Chacun est une fiche Personne : coureur, parent ou bénévole sans double saisie.",
                         athlete_id_initial)
        f = QHBoxLayout()
        self.recherche = QLineEdit()
        self.recherche.setPlaceholderText("Rechercher (nom, prénom, ville, e-mail, n° de licence)")
        self.f_groupe = QComboBox()
        self.f_etat = QComboBox()
        for code, lib in (("tous", "Tous les dossiers"), ("incomplets", "Dossiers incomplets"), ("impayes", "Cotisation à payer"),
                          ("mineurs", "Moins de 18 ans"), ("annulees", "Adhésions annulées")):
            self.f_etat.addItem(lib, code)
        self.recherche.textChanged.connect(lambda _t: self._remplir())
        self.f_groupe.currentIndexChanged.connect(lambda _i: self._remplir())
        self.f_etat.currentIndexChanged.connect(lambda _i: self._remplir())
        f.addWidget(self.recherche, 2)
        f.addWidget(self.f_groupe, 1)
        f.addWidget(self.f_etat, 1)
        self.principal.addLayout(f)
        b = QHBoxLayout()
        for texte, fn, p in (("➕ Nouvel adhérent", self._nouveau, True), ("✏️ Fiche", self._modifier, False),
                             ("💶 Paiement", self._paiement, False), ("🧾 Reçu PDF", self._recu, False),
                             ("📤 Export tableur", self._export, False), ("✉️ Copier les e-mails", self._emails, False),
                             ("🗑 Retirer de la saison", self._retirer, False)):
            w = _bouton(texte, p)
            w.clicked.connect(fn)
            b.addWidget(w)
        b.addStretch()
        self.principal.addLayout(b)
        self.compte = QLabel("")
        self.compte.setObjectName("texteSecondaire")
        self.principal.addWidget(self.compte)
        self.table = _table(self.COLONNES, 520)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.cellDoubleClicked.connect(lambda _r, _c: self._modifier())
        self.principal.addWidget(self.table)
        self.principal.addStretch()
        self._adh, self._vues = [], []
        self._finaliser()

    def actualiser(self):
        actuel = self.f_groupe.currentData()
        self.f_groupe.blockSignals(True)
        self.f_groupe.clear()
        self.f_groupe.addItem("Tous les groupes", None)
        for g in self.groupes_visibles():
            self.f_groupe.addItem(g["nom"], g["id"])
        self.f_groupe.setCurrentIndex(max(0, self.f_groupe.findData(actuel)))
        self.f_groupe.blockSignals(False)
        self._adh = self.adhesions()
        self._remplir()

    def _remplir(self):
        q = imp._cle(self.recherche.text())
        g = self.f_groupe.currentData()
        membres = set(dclub.membres_du_groupe(g)) if g else None
        etat = self.f_etat.currentData()
        vues = []
        for a in self._adh:
            if membres is not None and a["personne_id"] not in membres:
                continue
            if etat == "annulees" and a["statut"] != "annulee":
                continue
            if etat != "annulees" and a["statut"] == "annulee" and etat != "tous":
                continue
            if etat == "incomplets" and a["dossier"]["complet"]:
                continue
            if etat == "impayes" and a["reste"] <= 0.005:
                continue
            if etat == "mineurs" and not a["mineur"]:
                continue
            if q and q not in imp._cle(f"{a['nom']} {a['prenom']} {a['prenom']} {a['nom']} {a['ville'] or ''} "
                                       f"{a['email'] or ''} {a['numero_licence'] or ''}"):
                continue
            vues.append(a)
        self._vues = vues
        t = self.table
        t.setRowCount(len(vues))
        for i, a in enumerate(vues):
            c = a["categorie"]
            d = a["dossier"]
            cot = (f"{_euros(a['montant_paye'])} / {_euros(a['cotisation'])}" if a["cotisation"] else "—")
            vals = [a["nom"], a["prenom"], c["code"] if c else "?", cat.LIBELLE_LICENCE.get(a["type_licence"], "—"),
                    a["numero_licence"] or "", a["groupes"] or "", regles.LIBELLE_SANTE.get(a["sante_type"], "à fournir"),
                    cot, "✅ complet" if d["complet"] else "⚠️ " + ", ".join(_court(m) for m in d["manques"])]
            if a["statut"] == "annulee":
                vals[-1] = "annulée"
            for j, v in enumerate(vals):
                it = QTableWidgetItem(v)
                if j == 8:
                    it.setForeground(QColor(GRIS if a["statut"] == "annulee" else VERT if d["complet"] else ORANGE))
                    if d["avertissements"]:
                        it.setToolTip("\n".join(d["avertissements"]))
                if j == 7 and a["reste"] > 0.005:
                    it.setForeground(QColor(ROUGE))
                t.setItem(i, j, it)
        t.resizeColumnsToContents()
        if t.columnWidth(8) > 420:
            t.setColumnWidth(8, 420)
        n_actifs = sum(1 for a in self._adh if a["statut"] != "annulee")
        self.compte.setText(f"{len(vues)} affiché(s) sur {n_actifs} adhérent(s) en {self.saison}.")

    def _selection(self):
        lignes = sorted({i.row() for i in self.table.selectedIndexes()})
        return [self._vues[l] for l in lignes if l < len(self._vues)]

    def _nouveau(self):
        d = DialogueAdherent(self, self.club_id, self.saison)
        if d.exec():
            self._remplir_saisons()
            self.actualiser()

    def _modifier(self):
        sel = self._selection()
        if sel:
            d = DialogueAdherent(self, self.club_id, self.saison, sel[0])
            if d.exec():
                self.actualiser()

    def _paiement(self):
        sel = self._selection()
        if not sel:
            return
        a = sel[0]
        d = QDialog(self)
        d.setWindowTitle(f"Paiement — {a['prenom']} {a['nom']}")
        d.setStyleSheet(obtenir_style_ecran())
        f = QFormLayout(d)
        m = _montant()
        m.setValue(a["reste"] or 0)
        mode = QComboBox()
        mode.addItems(regles.MODES_PAIEMENT)
        jour = QDateEdit(QDate.currentDate())
        jour.setCalendarPopup(True)
        jour.setDisplayFormat("dd/MM/yyyy")
        f.addRow(QLabel(f"Cotisation {_euros(a['cotisation'])}, déjà payé {_euros(a['montant_paye'])}."))
        f.addRow("Montant reçu", m)
        f.addRow("Mode", mode)
        f.addRow("Date", jour)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(d.accept)
        bb.rejected.connect(d.reject)
        f.addRow(bb)
        if not d.exec():
            return
        try:
            recu = dclub.enregistrer_paiement(a["id"], m.value(), mode.currentText(), jour.date().toString("yyyy-MM-dd"))
        except dclub.ErreurClub as e:
            QMessageBox.warning(self, "Paiement", str(e))
            return
        self.actualiser()
        if recu:
            QMessageBox.information(self, "Paiement", f"Cotisation soldée : reçu n° {recu} (bouton « Reçu PDF »).")

    def _recu(self):
        sel = self._selection()
        if not sel:
            return
        a = dclub.adhesion(sel[0]["id"])
        if not a["recu_numero"]:
            QMessageBox.information(self, "Reçu", "Le reçu s'établit quand la cotisation est entièrement payée.")
            return
        chemin, _ = QFileDialog.getSaveFileName(self, "Reçu de cotisation",
                                                f"Recu {a['recu_numero']} {a['prenom']} {a['nom']}.pdf", "PDF (*.pdf)")
        if not chemin:
            return
        from interface.club_pdf import rendre_recu
        rendre_recu(chemin, dclub.club_principal(), a)
        from PySide6.QtGui import QDesktopServices
        from PySide6.QtCore import QUrl
        QDesktopServices.openUrl(QUrl.fromLocalFile(chemin))

    def _export(self):
        chemin, _ = QFileDialog.getSaveFileName(self, "Exporter les adhérents", f"Adherents {self.saison}.csv", "CSV (*.csv)")
        if chemin:
            Path(chemin).write_text(dclub.export_csv(self._vues), encoding="utf-8")
            QMessageBox.information(self, "Export", f"{len(self._vues)} adhérent(s) exporté(s) : le fichier s'ouvre dans "
                                    "Excel, Numbers ou LibreOffice.")

    def _emails(self):
        emails = sorted({a["email"] for a in (self._selection() or self._vues) if a.get("email")})
        QGuiApplication.clipboard().setText("; ".join(emails))
        QMessageBox.information(self, "E-mails", f"{len(emails)} adresse(s) copiée(s) (la sélection, ou toute la liste "
                                "affichée) : colle-les en copie cachée.")

    def _retirer(self):
        sel = self._selection()
        if not sel:
            return
        noms = ", ".join(f"{a['prenom']} {a['nom']}" for a in sel[:5]) + ("…" if len(sel) > 5 else "")
        rep = QMessageBox.question(self, "Retirer", f"Retirer {noms} de la saison {self.saison} ? Leur fiche Personne "
                                   "et leurs autres saisons sont gardées. (Pour garder une trace, mets plutôt le statut "
                                   "« Annulée » dans la fiche.)")
        if rep == QMessageBox.StandardButton.Yes:
            for a in sel:
                dclub.supprimer_adhesion(a["id"])
            self.actualiser()


# ======================================================================
# Onglet 3 — Groupes
# ======================================================================

class GroupesClub(_EcranClub):

    def __init__(self, athlete_id_initial=None):
        super().__init__("🧑‍🤝‍🧑  Groupes d'entraînement", "Les groupes du club (adultes route, trail, école d'athlé…), "
                         "leur entraîneur et leurs membres. Ils serviront à l'agenda et à l'appel des présences.",
                         athlete_id_initial)
        b = QHBoxLayout()
        for texte, fn, p in (("➕ Nouveau groupe", self._nouveau, True), ("✏️ Modifier", self._modifier, False),
                             ("🗑 Supprimer", self._supprimer, False)):
            w = _bouton(texte, p)
            w.clicked.connect(fn)
            b.addWidget(w)
        b.addStretch()
        self.principal.addLayout(b)
        self.table = _table(["Groupe", "Entraîneur", "Membres", "Description"], 220)
        self.table.itemSelectionChanged.connect(self._membres)
        self.table.cellDoubleClicked.connect(lambda _r, _c: self._modifier())
        self.principal.addWidget(self.table)
        cadre, lc = _cadre("Membres du groupe (adhérents de la saison)")
        self.liste = QListWidget()
        self.liste.setMinimumHeight(260)
        lc.addWidget(self.liste)
        b2 = QHBoxLayout()
        enr = _bouton("💾 Enregistrer les membres", True)
        enr.clicked.connect(self._enregistrer_membres)
        b2.addWidget(enr)
        b2.addStretch()
        lc.addLayout(b2)
        self.principal.addWidget(cadre)
        self.principal.addStretch()
        self._groupes = []
        self._finaliser()

    def actualiser(self):
        self._groupes = self.groupes_visibles(avec_inactifs=True)
        t = self.table
        actuel = t.currentRow()
        t.setRowCount(len(self._groupes))
        for i, g in enumerate(self._groupes):
            for j, v in enumerate((g["nom"] + ("" if g["actif"] else " (inactif)"), g["entraineur"] or "—",
                                   str(g["nb_membres"]), g["description"] or "")):
                t.setItem(i, j, QTableWidgetItem(v))
        t.resizeColumnsToContents()
        if self._groupes:
            t.selectRow(actuel if 0 <= actuel < len(self._groupes) else 0)
        self._membres()

    def _courant(self):
        i = self.table.currentRow()
        return self._groupes[i] if 0 <= i < len(self._groupes) else None

    def _membres(self):
        self.liste.clear()
        g = self._courant()
        if not g:
            return
        membres = set(dclub.membres_du_groupe(g["id"]))
        for a in self.adhesions():
            if a["statut"] == "annulee":
                continue
            c = a["categorie"]
            it = QListWidgetItem(f"{a['nom']} {a['prenom']}" + (f"  ·  {c['code']}" if c else ""))
            it.setData(Qt.ItemDataRole.UserRole, a["personne_id"])
            it.setFlags(it.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            it.setCheckState(Qt.CheckState.Checked if a["personne_id"] in membres else Qt.CheckState.Unchecked)
            self.liste.addItem(it)

    def _enregistrer_membres(self):
        g = self._courant()
        if not g:
            return
        for i in range(self.liste.count()):
            it = self.liste.item(i)
            pid = it.data(Qt.ItemDataRole.UserRole)
            actuels = set(dclub.groupes_de(pid))
            if it.checkState() == Qt.CheckState.Checked:
                actuels.add(g["id"])
            else:
                actuels.discard(g["id"])
            dclub.definir_groupes(pid, actuels, self.club_id)
        self.actualiser()

    def _dialogue(self, g=None):
        d = QDialog(self)
        d.setWindowTitle("Groupe")
        d.setStyleSheet(obtenir_style_ecran())
        _style_cases(d)
        f = QFormLayout(d)
        nom = QLineEdit((g or {}).get("nom") or "")
        desc = QLineEdit((g or {}).get("description") or "")
        ent = QComboBox()
        ent.addItem("—", None)
        for p in dper.lister():
            ent.addItem(f"{p['prenom']} {p['nom']}", p["id"])
        ent.setCurrentIndex(max(0, ent.findData((g or {}).get("entraineur_id"))))
        actif = QCheckBox("Groupe actif")
        actif.setChecked(bool((g or {}).get("actif", 1)))
        sec = QComboBox()
        sec.addItem("Toute l'association", None)
        for x in dclub.sections(self.club_id):
            sec.addItem(x["nom"], x["id"])
        sec.setCurrentIndex(max(0, sec.findData((g or {}).get("section_id") if g else self.section_id)))
        f.addRow("Nom", nom)
        if sec.count() > 1:
            f.addRow("Section", sec)
        f.addRow("Entraîneur", ent)
        f.addRow("Description", desc)
        f.addRow("", actif)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(d.accept)
        bb.rejected.connect(d.reject)
        f.addRow(bb)
        if d.exec():
            try:
                dclub.enregistrer_groupe(self.club_id, {"nom": nom.text(), "description": desc.text(),
                                                        "entraineur_id": ent.currentData(), "actif": actif.isChecked(),
                                                        "section_id": sec.currentData()},
                                         g["id"] if g else None)
            except dclub.ErreurClub as e:
                QMessageBox.warning(self, "Groupe", str(e))
            self.actualiser()

    def _nouveau(self):
        self._dialogue()

    def _modifier(self):
        g = self._courant()
        if g:
            self._dialogue(g)

    def _supprimer(self):
        g = self._courant()
        if g and QMessageBox.question(self, "Supprimer", f"Supprimer le groupe « {g['nom']} » ? Ses membres restent "
                                      "adhérents.") == QMessageBox.StandardButton.Yes:
            dclub.supprimer_groupe(g["id"])
            self.actualiser()


# ======================================================================
# Onglet 4 — Cotisations
# ======================================================================

class CotisationsClub(_EcranClub):

    def __init__(self, athlete_id_initial=None):
        super().__init__("💶  Cotisations", "Les tarifs de la saison et ce qu'il reste à encaisser. Un tarif peut être "
                         "lié à un type de licence : il est proposé tout seul dans la fiche de l'adhérent.",
                         athlete_id_initial)
        cadre, lc = _cadre("Tarifs de la saison")
        self.table_t = _table(["Tarif", "Licence", "Montant"], 160)
        lc.addWidget(self.table_t)
        b = QHBoxLayout()
        for texte, fn, p in (("➕ Tarif", self._tarif, True), ("✏️ Modifier", self._modifier_tarif, False),
                             ("🗑 Supprimer", self._supprimer_tarif, False),
                             ("📋 Reprendre ceux de la saison précédente", self._copier, False)):
            w = _bouton(texte, p)
            w.clicked.connect(fn)
            b.addWidget(w)
        b.addStretch()
        lc.addLayout(b)
        self.principal.addWidget(cadre)
        cadre, lc = _cadre("Reste à encaisser")
        self.label = QLabel("")
        lc.addWidget(self.label)
        self.table_r = _table(["Nom", "Prénom", "Tarif", "Cotisation", "Payé", "Reste", "E-mail"], 220)
        lc.addWidget(self.table_r)
        b2 = QHBoxLayout()
        rel = _bouton("✉️ Copier le message de relance")
        rel.clicked.connect(self._relance)
        b2.addWidget(rel)
        b2.addStretch()
        lc.addLayout(b2)
        self.principal.addWidget(cadre)
        cadre, lc = _cadre("Paiements de la saison par mode")
        self.table_m = _table(["Mode", "Adhésions", "Montant"], 120)
        lc.addWidget(self.table_m)
        self.principal.addWidget(cadre)
        self.principal.addStretch()
        self._tarifs, self._impayes = [], []
        self._finaliser()

    def actualiser(self):
        self._tarifs = dclub.tarifs_de(self.club_id, self.saison, self.section_id)
        t = self.table_t
        t.setRowCount(len(self._tarifs))
        for i, x in enumerate(self._tarifs):
            for j, v in enumerate((x["libelle"], cat.LIBELLE_LICENCE.get(x["type_licence"], "toutes"), _euros(x["montant"]))):
                t.setItem(i, j, QTableWidgetItem(v))
        t.resizeColumnsToContents()
        adh = [a for a in self.adhesions() if a["statut"] != "annulee"]
        self._impayes = [a for a in adh if a["reste"] > 0.005]
        t = self.table_r
        t.setRowCount(len(self._impayes))
        for i, a in enumerate(self._impayes):
            for j, v in enumerate((a["nom"], a["prenom"], a["tarif"] or "", _euros(a["cotisation"]), _euros(a["montant_paye"]),
                                   _euros(a["reste"]), a["email"] or "")):
                t.setItem(i, j, QTableWidgetItem(v))
        t.resizeColumnsToContents()
        sans = sum(1 for a in adh if not a["cotisation"])
        self.label.setText(f"{len(self._impayes)} adhérent(s), {_euros(sum(a['reste'] for a in self._impayes))} à encaisser"
                           + (f" · {sans} adhésion(s) sans montant de cotisation." if sans else "."))
        modes = {}
        for a in adh:
            if a["montant_paye"]:
                m = a["paiement_mode"] or "Non précisé"
                modes.setdefault(m, [0, 0.0])
                modes[m][0] += 1
                modes[m][1] += a["montant_paye"]
        t = self.table_m
        t.setRowCount(len(modes))
        for i, (m, (n, s)) in enumerate(sorted(modes.items(), key=lambda x: -x[1][1])):
            for j, v in enumerate((m, str(n), _euros(s))):
                t.setItem(i, j, QTableWidgetItem(v))
        t.resizeColumnsToContents()

    def _dialogue_tarif(self, t=None):
        d = QDialog(self)
        d.setWindowTitle(f"Tarif {self.saison}")
        d.setStyleSheet(obtenir_style_ecran())
        f = QFormLayout(d)
        lib = QLineEdit((t or {}).get("libelle") or "")
        lib.setPlaceholderText("ex. Adulte compétition, Jeune, Famille 2e enfant")
        lic = QComboBox()
        lic.addItem("Toutes les licences", None)
        for code, l, _c in cat.TYPES_LICENCE:
            lic.addItem(l, code)
        lic.setCurrentIndex(max(0, lic.findData((t or {}).get("type_licence"))))
        m = _montant()
        m.setValue((t or {}).get("montant") or 0)
        sec = QComboBox()
        sec.addItem("Toute l'association", None)
        for x in dclub.sections(self.club_id):
            sec.addItem(x["nom"], x["id"])
        sec.setCurrentIndex(max(0, sec.findData((t or {}).get("section_id") if t else self.section_id)))
        f.addRow("Nom", lib)
        if sec.count() > 1:
            f.addRow("Section", sec)
        f.addRow("Licence", lic)
        f.addRow("Montant", m)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(d.accept)
        bb.rejected.connect(d.reject)
        f.addRow(bb)
        if d.exec():
            try:
                dclub.enregistrer_tarif(self.club_id, self.saison, lib.text(), m.value(), lic.currentData(),
                                        t["id"] if t else None, sec.currentData())
            except dclub.ErreurClub as e:
                QMessageBox.warning(self, "Tarif", str(e))
            self.actualiser()

    def _tarif(self):
        self._dialogue_tarif()

    def _modifier_tarif(self):
        i = self.table_t.currentRow()
        if 0 <= i < len(self._tarifs):
            self._dialogue_tarif(self._tarifs[i])

    def _supprimer_tarif(self):
        i = self.table_t.currentRow()
        if 0 <= i < len(self._tarifs):
            dclub.supprimer_tarif(self._tarifs[i]["id"])
            self.actualiser()

    def _copier(self):
        n = dclub.copier_tarifs(self.club_id, cat.saison_precedente(self.saison), self.saison)
        QMessageBox.information(self, "Tarifs", f"{n} tarif(s) repris de {cat.saison_precedente(self.saison)}.")
        self.actualiser()

    def _relance(self):
        c = dclub.club_principal() or {}
        emails = "; ".join(sorted({a["email"] for a in self._impayes if a.get("email")}))
        texte = (f"Destinataires (copie cachée) : {emails}\n\nObjet : Cotisation {self.saison} — {c.get('nom', 'club')}\n\n"
                 f"Bonjour,\n\nSauf erreur de notre part, ta cotisation {self.saison} au club n'est pas encore "
                 "entièrement réglée. Tu peux nous la remettre au prochain entraînement ou la régler en ligne.\n\n"
                 f"Merci et à bientôt,\n{c.get('president') or 'Le bureau'}")
        QGuiApplication.clipboard().setText(texte)
        QMessageBox.information(self, "Relance", "Message et adresses copiés : colle-les dans ta messagerie.")


# ======================================================================
# Onglet 5 — Import
# ======================================================================

class ImportClub(_EcranClub):

    def __init__(self, athlete_id_initial=None):
        super().__init__("📥  Importer des adhérents", "Un export HelloAsso, la liste des licenciés du SI-FFA ou "
                         "n'importe quel tableau (CSV, Excel) avec une colonne Nom et une colonne Prénom. Les personnes "
                         "déjà connues sont complétées, jamais en double.", athlete_id_initial)
        b = QHBoxLayout()
        ch = _bouton("📂 Choisir un fichier…", True)
        ch.clicked.connect(self._choisir)
        self.source = QComboBox()
        for code, lib in (("helloasso", "HelloAsso"), ("si_ffa", "SI-FFA"), ("import", "Autre fichier")):
            self.source.addItem(lib, code)
        self.b_importer = _bouton("✅ Importer dans la saison")
        self.b_importer.clicked.connect(self._importer)
        self.b_importer.setEnabled(False)
        b.addWidget(ch)
        b.addWidget(QLabel("Provenance :"))
        b.addWidget(self.source)
        b.addWidget(self.b_importer)
        b.addStretch()
        self.principal.addLayout(b)
        self.label = QLabel("")
        self.label.setWordWrap(True)
        self.label.setTextFormat(Qt.TextFormat.RichText)
        self.principal.addWidget(self.label)
        self.table = _table(["Nom", "Prénom", "Naissance", "Licence", "N° licence", "Cotisation", "Déjà connu ?", "Remarque"],
                            420)
        self.principal.addWidget(self.table)
        self.principal.addStretch()
        self._analyse = None
        self._finaliser()

    def actualiser(self):
        pass

    def _choisir(self):
        chemin, _ = QFileDialog.getOpenFileName(self, "Fichier d'adhérents", "", "Tableaux (*.csv *.txt *.xlsx)")
        if chemin:
            self.charger(chemin)

    def charger(self, chemin):
        try:
            lignes = imp.lire_tableau(Path(chemin).read_bytes(), chemin)
        except (OSError, ValueError) as e:
            QMessageBox.warning(self, "Import", str(e))
            return
        a = imp.analyser(lignes)
        self._analyse = a
        if "helloasso" in Path(chemin).name.lower() or "commande" in " ".join(a["colonnes"].values()).lower():
            self.source.setCurrentIndex(0)
        t = self.table
        t.setRowCount(len(a["lignes"]))
        for i, l in enumerate(a["lignes"]):
            p, ad = l["personne"], l["adhesion"]
            connu = dclub._chercher_personne(p, ad.get("numero_licence"))
            vals = [p["nom"], p["prenom"], _jour(p["date_naissance"]), cat.LIBELLE_LICENCE.get(ad["type_licence"], ad.get("tarif") or ""),
                    ad["numero_licence"] or "", _euros(ad["cotisation"]) if ad["cotisation"] else "",
                    "oui, fiche complétée" if connu else "nouveau", "; ".join(l["erreurs"])]
            for j, v in enumerate(vals):
                t.setItem(i, j, QTableWidgetItem(v))
        t.resizeColumnsToContents()
        reconnues = ", ".join(f"{NOMS_CHAMPS.get(k, k)} ← « {v} »" for k, v in a["colonnes"].items())
        self.label.setText(f"<b>{len(a['lignes'])} adhérent(s)</b> lus dans {html.escape(Path(chemin).name)}, pour la "
                           f"saison <b>{self.saison}</b> (change-la en haut si besoin).<br>Colonnes reconnues : "
                           f"{html.escape(reconnues)}." + (f"<br>Ignorées : {html.escape(', '.join(a['non_reconnues']))}."
                                                           if a["non_reconnues"] else "")
                           + "<br>Les commandes remboursées ou annulées sont écartées.")
        self.b_importer.setEnabled(bool(a["lignes"]))

    def _importer(self):
        if not self._analyse:
            return
        r = dclub.importer(self.club_id, self.saison, self._analyse["lignes"], self.source.currentData(), self.section_id)
        txt = (f"{r['adhesions']} adhésion(s) {self.saison} créée(s) · {r['crees']} nouvelle(s) fiche(s) · "
               f"{r['completes']} fiche(s) complétée(s) · {r['deja']} déjà inscrit(s) cette saison.")
        if r["erreurs"]:
            txt += "\n\nÀ revoir :\n" + "\n".join(r["erreurs"][:15])
        QMessageBox.information(self, "Import", txt)
        self._remplir_saisons()
        f = self._fenetre()
        if f:
            for e in f.ecrans:
                e.actualiser()


# ======================================================================
# Onglet 6 — Le club
# ======================================================================

class ReglagesClub(_EcranClub):

    def __init__(self, athlete_id_initial=None):
        super().__init__("⚙️  Le club", "Les informations de l'association, reprises sur les reçus et les documents "
                         "des courses ; les autres associations gérées et les sections. La zone de vacances (selon "
                         "l'académie) sert à l'agenda.",
                         athlete_id_initial)
        cadre, lc = _cadre("Identité de l'association")
        f = QFormLayout()
        self.champs = {}
        for cle, lib in (("nom", "Nom"), ("sigle", "Sigle"), ("numero_ffa", "N° d'affiliation FFA"),
                         ("ligue", "Ligue"), ("comite", "Comité départemental"), ("president", "Président(e)"),
                         ("adresse", "Adresse"), ("code_postal", "Code postal"), ("ville", "Ville"), ("email", "E-mail"),
                         ("telephone", "Téléphone"), ("site", "Site internet")):
            w = QLineEdit()
            self.champs[cle] = w
            f.addRow(lib, w)
        self.zone = QComboBox()
        from noyau.club import agenda as ag
        for z in ag.ZONES:
            self.zone.addItem(f"Zone {z} : " + ", ".join(ag.ZONE_PAR_ACADEMIE[z]), z)
        f.addRow("Vacances scolaires", self.zone)
        self.type_structure = QComboBox()
        for code, lib in dclub.TYPES_STRUCTURE:
            self.type_structure.addItem(lib, code)
        f.insertRow(1, "Type d'association", self.type_structure)
        self.affiliation = QLineEdit()
        self.affiliation.setPlaceholderText("ex. FFA, FFRandonnée, FSGT, UFOLEP, aucune")
        f.insertRow(3, "Affiliation", self.affiliation)
        self.notes = QTextEdit()
        self.notes.setMaximumHeight(80)
        f.addRow("Notes", self.notes)
        lc.addLayout(f)
        b = QHBoxLayout()
        enr = _bouton("💾 Enregistrer", True)
        enr.clicked.connect(self._enregistrer)
        b.addWidget(enr)
        b.addStretch()
        lc.addLayout(b)
        self.principal.addWidget(cadre)
        # --- plusieurs associations
        cadre, lc = _cadre("Associations gérées dans Trail Hub")
        aide = QLabel("Chaque association a ses adhérents, ses groupes, ses tarifs, ses reçus, son agenda et ses "
                      "événements. Une personne inscrite dans deux associations garde une seule fiche, avec une "
                      "adhésion dans chacune. Le choix en haut de chaque écran dit sur quelle association on travaille.")
        aide.setWordWrap(True)
        aide.setObjectName("texteSecondaire")
        lc.addWidget(aide)
        self.table_clubs = _table(["Association", "Type", "Affiliation", "Ville", "Adhérents (saison)", "Sections"], 150)
        lc.addWidget(self.table_clubs)
        b = QHBoxLayout()
        for t, fn, p in (("➕ Nouvelle association", self._nouvelle_association, False),
                         ("✔️ Travailler sur celle-ci", self._choisir_association, False),
                         ("🗑️ Supprimer", self._supprimer_association, False)):
            w = _bouton(t, p)
            w.clicked.connect(fn)
            b.addWidget(w)
        b.addStretch()
        lc.addLayout(b)
        self.principal.addWidget(cadre)
        # --- sections
        cadre, lc = _cadre("Sections de cette association")
        aide = QLabel("Une section (trail, running, marche nordique, école d'athlé…) garde ses adhérents, ses groupes "
                      "et ses tarifs à part dans la même association : même bureau, même comptabilité.")
        aide.setWordWrap(True)
        aide.setObjectName("texteSecondaire")
        lc.addWidget(aide)
        self.table_sections = _table(["Section", "Discipline", "Responsable", "Adhérents (saison)", "Groupes", "Active"], 150)
        lc.addWidget(self.table_sections)
        b = QHBoxLayout()
        for t, fn, p in (("➕ Section", self._nouvelle_section, False), ("✏️ Modifier", self._modifier_section, False),
                         ("🗑️ Supprimer", self._supprimer_section, False)):
            w = _bouton(t, p)
            w.clicked.connect(fn)
            b.addWidget(w)
        b.addStretch()
        lc.addLayout(b)
        self.principal.addWidget(cadre)
        self.principal.addStretch()
        self._clubs, self._sections = [], []
        self._finaliser()

    def actualiser(self):
        c = dclub.club_principal() or {}
        for k, w in self.champs.items():
            w.setText(c.get(k) or "")
        self.notes.setPlainText(c.get("notes") or "")
        self.zone.setCurrentIndex(max(0, self.zone.findData(c.get("zone_vacances") or "B")))
        self.type_structure.setCurrentIndex(max(0, self.type_structure.findData(c.get("type_structure") or "club_ffa")))
        self.affiliation.setText(c.get("affiliation") or "")
        self._clubs = dclub.clubs()
        t = self.table_clubs
        t.setRowCount(len(self._clubs))
        for r, x in enumerate(self._clubs):
            n = len([a for a in dclub.adhesions(x["id"], self.saison) if a["statut"] != "annulee"])
            for j, v in enumerate(((("▶ " if x["id"] == c.get("id") else "") + x["nom"]),
                                   dclub.LIBELLE_STRUCTURE.get(x.get("type_structure") or "club_ffa", ""),
                                   x.get("affiliation") or "", x.get("ville") or "", str(n),
                                   ", ".join(s["nom"] for s in dclub.sections(x["id"])))):
                t.setItem(r, j, QTableWidgetItem(v))
        t.resizeColumnsToContents()
        self._sections = dclub.sections(self.club_id, avec_inactives=True)
        t = self.table_sections
        t.setRowCount(len(self._sections))
        adh = [a for a in dclub.adhesions(self.club_id, self.saison) if a["statut"] != "annulee"]
        grp = dclub.groupes(self.club_id, True)
        for r, x in enumerate(self._sections):
            for j, v in enumerate((x["nom"], x.get("discipline") or "", x.get("responsable") or "",
                                   str(sum(1 for a in adh if a["section_id"] == x["id"])),
                                   ", ".join(g["nom"] for g in grp if g["section_id"] == x["id"]),
                                   "oui" if x["actif"] else "non")):
                t.setItem(r, j, QTableWidgetItem(v))
        t.resizeColumnsToContents()

    def _spec_association(self):
        return [("texte", "nom", "Nom", None), ("choix", "type_structure", "Type", {"choix": dclub.TYPES_STRUCTURE}),
                ("texte", "affiliation", "Affiliation", {"aide": "FFA, FFRandonnée, aucune…"}),
                ("texte", "ville", "Ville", None), ("texte", "president", "Président(e)", None)]

    def _nouvelle_association(self):
        from interface.organisation_logistique import DialogueChamps
        d = DialogueChamps(self, "Nouvelle association", self._spec_association(), {"type_structure": "association_trail"},
                           lambda ch: dclub.enregistrer_club(ch))
        if d.exec():
            if QMessageBox.question(self, "Association", "Travailler maintenant sur cette association ?") == \
                    QMessageBox.StandardButton.Yes:
                dclub.choisir_club(d.resultat)
            self._tout_rafraichir()

    def _choisir_association(self):
        r = self.table_clubs.currentRow()
        if 0 <= r < len(self._clubs):
            dclub.choisir_club(self._clubs[r]["id"])
            self._tout_rafraichir()

    def _supprimer_association(self):
        r = self.table_clubs.currentRow()
        if not 0 <= r < len(self._clubs):
            return
        x = self._clubs[r]
        if QMessageBox.question(self, "Association", f"Supprimer « {x['nom']} » ?") != QMessageBox.StandardButton.Yes:
            return
        try:
            dclub.supprimer_club(x["id"])
        except dclub.ErreurClub as e:
            QMessageBox.warning(self, "Association", str(e))
            return
        self._tout_rafraichir()

    def _spec_section(self):
        resp = [(None, "—")] + [(a["personne_id"], f"{a['prenom'] or ''} {a['nom']}".strip())
                                for a in dclub.adhesions(self.club_id, self.saison)]
        return [("texte", "nom", "Nom de la section", {"aide": "Trail, Running, Marche nordique…"}),
                ("texte", "discipline", "Discipline", None), ("choix", "responsable_id", "Responsable", {"choix": resp}),
                ("long", "description", "Description", None), ("case", "actif", "Active", {"texte": "oui"})]

    def _nouvelle_section(self):
        from interface.organisation_logistique import DialogueChamps
        d = DialogueChamps(self, "Nouvelle section", self._spec_section(), {"actif": True},
                           lambda ch: dclub.enregistrer_section(self.club_id, ch))
        if d.exec():
            self._tout_rafraichir()

    def _modifier_section(self):
        from interface.organisation_logistique import DialogueChamps
        r = self.table_sections.currentRow()
        if 0 <= r < len(self._sections):
            x = self._sections[r]
            d = DialogueChamps(self, "Section", self._spec_section(), x,
                               lambda ch: dclub.enregistrer_section(self.club_id, ch, x["id"]))
            if d.exec():
                self._tout_rafraichir()

    def _supprimer_section(self):
        r = self.table_sections.currentRow()
        if 0 <= r < len(self._sections):
            x = self._sections[r]
            if QMessageBox.question(self, "Section", f"Supprimer la section « {x['nom']} » ? Ses adhérents, groupes et "
                                    "tarifs restent dans l'association.") == QMessageBox.StandardButton.Yes:
                dclub.supprimer_section(x["id"])
                self._tout_rafraichir()

    def _enregistrer(self):
        v = {k: w.text() for k, w in self.champs.items()}
        v["notes"] = self.notes.toPlainText()
        v["zone_vacances"] = self.zone.currentData()
        v["type_structure"] = self.type_structure.currentData()
        v["affiliation"] = self.affiliation.text()
        try:
            dclub.enregistrer_club(v, self.club_id)
        except dclub.ErreurClub as e:
            QMessageBox.warning(self, "Club", str(e))
            return
        self._tout_rafraichir()
        QMessageBox.information(self, "Club", "Informations de l'association enregistrées.")


# ======================================================================
# Fenêtre
# ======================================================================

class ClubFenetre(ConteneurOnglets):

    def __init__(self, athlete_id_initial=None):
        from interface.club_agenda import AgendaClub, PresencesClub                       # étape 4.2
        from interface.club_profils import LicenciesClub, SeancesPartageesClub, EntraineursClub   # étape 4.3
        from interface.club_kids import KidsClub                                                  # chantier D
        super().__init__(
            titre="Club",
            onglets=[("📊 Tableau de bord", TableauDeBordClub), ("👥 Adhérents", AdherentsClub),
                     ("🏅 Licenciés", LicenciesClub), ("🧑‍🤝‍🧑 Groupes", GroupesClub), ("📅 Agenda", AgendaClub),
                     ("✅ Présences", PresencesClub), ("📚 Séances", SeancesPartageesClub),
                     ("🧑‍🏫 Entraîneurs", EntraineursClub), ("🧒 Kids", KidsClub), ("💶 Cotisations", CotisationsClub),
                     ("📥 Import", ImportClub), ("⚙️ Le club", ReglagesClub)],
            athlete_id_initial=athlete_id_initial,
        )
        (self.tableau, self.adherents, self.licencies, self.groupes, self.agenda, self.presences, self.seances,
         self.entraineurs, self.kids, self.cotisations, self.import_, self.reglages) = self.ecrans

