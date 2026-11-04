"""
Écran « Personnes » (étape 2.2) : la fiche unique de chaque personne
connue de Trail Hub Center, avec ses rôles (coureur, licencié, enfant,
parent, entraîneur, bénévole, organisateur) et ses liens parent/enfant.

Aucune requête ici : tout passe par noyau/donnees/personnes.py.
"""

from PySide6.QtCore import Qt, QDate
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QLabel, QPushButton, QFrame, QLineEdit,
    QComboBox, QFormLayout, QScrollArea, QTableWidget, QTableWidgetItem, QHeaderView,
    QMessageBox, QAbstractItemView, QCheckBox, QGridLayout, QPlainTextEdit, QListWidget,
    QListWidgetItem,
)

from noyau.donnees import personnes as dpers
from interface.ecran_liste import obtenir_style_ecran, configurer_table_redimensionnable

SEXES = [("", "—"), ("H", "Homme"), ("F", "Femme")]
TOUS = "Tous les rôles"


class Personnes(QMainWindow):

    def __init__(self, athlete_id_initial=None):
        # athlete_id_initial : accepté pour ConteneurOnglets ; l'écran liste tout le monde
        super().__init__()
        self.setWindowTitle("Trail Hub Center – Personnes")
        self.resize(1250, 820)
        self.setMinimumSize(980, 640)
        self.personne_id = None

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.setCentralWidget(scroll)
        central = QWidget()
        scroll.setWidget(central)
        principal = QVBoxLayout(central)
        principal.setContentsMargins(25, 20, 25, 20)
        principal.setSpacing(14)

        titre = QLabel("👥  Personnes")
        titre.setObjectName("titrePage")
        sous = QLabel("Une seule fiche par personne, lue par tous les modules : coureur, licencié, enfant, "
                      "parent, entraîneur, bénévole, organisateur. Le profil sportif d'un coureur se règle "
                      "dans l'onglet Athlètes.")
        sous.setObjectName("sousTitrePage")
        sous.setWordWrap(True)
        principal.addWidget(titre)
        principal.addWidget(sous)

        self.resume = QLabel("")
        self.resume.setObjectName("texteSecondaire")
        principal.addWidget(self.resume)

        corps = QHBoxLayout()
        corps.setSpacing(16)
        principal.addLayout(corps, 1)

        # ---- liste
        gauche = QFrame()
        gauche.setObjectName("carteForm")
        lg = QVBoxLayout(gauche)
        filtres = QHBoxLayout()
        self.recherche = QLineEdit()
        self.recherche.setPlaceholderText("Rechercher un nom, une ville…")
        self.recherche.textChanged.connect(self.actualiser)
        self.combo_role = QComboBox()
        self.combo_role.addItem(TOUS, None)
        for code, lib in dpers.ROLES:
            self.combo_role.addItem(lib, code)
        self.combo_role.currentIndexChanged.connect(self.actualiser)
        filtres.addWidget(self.recherche, 1)
        filtres.addWidget(self.combo_role)
        lg.addLayout(filtres)
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["Nom", "Prénom", "Âge", "Rôles", "Ville"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.itemSelectionChanged.connect(self._selection)
        try:
            configurer_table_redimensionnable(self.table)
        except Exception:
            self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        lg.addWidget(self.table, 1)
        bouton_nouveau = QPushButton("＋  Nouvelle personne")
        bouton_nouveau.setObjectName("boutonPrincipal")
        bouton_nouveau.clicked.connect(self.nouvelle)
        lg.addWidget(bouton_nouveau)
        corps.addWidget(gauche, 5)

        # ---- fiche
        droite = QFrame()
        droite.setObjectName("carteForm")
        ld = QVBoxLayout(droite)
        self.titre_fiche = QLabel("Nouvelle personne")
        self.titre_fiche.setObjectName("titreCarte")
        ld.addWidget(self.titre_fiche)
        self.info_fiche = QLabel("")
        self.info_fiche.setObjectName("texteSecondaire")
        self.info_fiche.setWordWrap(True)
        ld.addWidget(self.info_fiche)

        form = QFormLayout()
        self.champ = {}
        for cle, lib in (("nom", "Nom *"), ("prenom", "Prénom"), ("email", "E-mail"), ("telephone", "Téléphone"),
                         ("adresse", "Adresse"), ("code_postal", "Code postal"), ("ville", "Ville")):
            e = QLineEdit()
            self.champ[cle] = e
            form.addRow(lib, e)
        self.naissance = QLineEdit()
        self.naissance.setPlaceholderText("jj/mm/aaaa")
        form.insertRow(2, "Date de naissance", self.naissance)
        self.sexe = QComboBox()
        for code, lib in SEXES:
            self.sexe.addItem(lib, code)
        form.insertRow(3, "Sexe", self.sexe)
        self.notes = QPlainTextEdit()
        self.notes.setFixedHeight(64)
        form.addRow("Notes", self.notes)
        ld.addLayout(form)

        lr = QLabel("Rôles")
        lr.setObjectName("labelChamp")
        ld.addWidget(lr)
        grille = QGridLayout()
        self.cases = {}
        for i, (code, lib) in enumerate(dpers.ROLES):
            c = QCheckBox(lib)
            self.cases[code] = c
            grille.addWidget(c, i // 4, i % 4)
        ld.addLayout(grille)

        ll = QLabel("Liens familiaux")
        ll.setObjectName("labelChamp")
        ld.addWidget(ll)
        self.liste_liens = QListWidget()
        self.liste_liens.setFixedHeight(80)
        ld.addWidget(self.liste_liens)
        ligne_lien = QHBoxLayout()
        self.combo_lien = QComboBox()
        self.combo_sens = QComboBox()
        self.combo_sens.addItem("est parent de", "parent_de")
        self.combo_sens.addItem("est enfant de", "enfant_de")
        bouton_lier = QPushButton("Relier")
        bouton_lier.clicked.connect(self._lier)
        bouton_delier = QPushButton("Retirer le lien")
        bouton_delier.clicked.connect(self._delier)
        ligne_lien.addWidget(self.combo_sens)
        ligne_lien.addWidget(self.combo_lien, 1)
        ligne_lien.addWidget(bouton_lier)
        ligne_lien.addWidget(bouton_delier)
        ld.addLayout(ligne_lien)

        boutons = QHBoxLayout()
        self.bouton_enregistrer = QPushButton("Enregistrer")
        self.bouton_enregistrer.setObjectName("boutonPrincipal")
        self.bouton_enregistrer.clicked.connect(self.enregistrer)
        self.bouton_supprimer = QPushButton("Supprimer la fiche")
        self.bouton_supprimer.setObjectName("boutonSecondaire")
        self.bouton_supprimer.clicked.connect(self.supprimer)
        boutons.addWidget(self.bouton_enregistrer)
        boutons.addStretch(1)
        boutons.addWidget(self.bouton_supprimer)
        ld.addLayout(boutons)
        ld.addStretch(1)
        corps.addWidget(droite, 6)

        from interface.theme import PALETTE, obtenir_couleur_accent
        self.setStyleSheet(
            obtenir_style_ecran() + "#carteForm QLabel, #carteForm QCheckBox { background: transparent; }"
            f"QCheckBox {{ spacing: 8px; padding: 3px 0; }}"
            f"QCheckBox::indicator {{ width: 16px; height: 16px; border: 1px solid {PALETTE['texte_discret']}; "
            f"border-radius: 4px; background: {PALETTE['carte_haute']}; }}"
            f"QCheckBox::indicator:checked {{ background: {obtenir_couleur_accent()}; border-color: {obtenir_couleur_accent()}; }}"
            f"QCheckBox:disabled {{ color: {PALETTE['texte_discret']}; }}")
        self.actualiser()
        self.nouvelle()

    # ------------------------------------------------------------
    def actualiser(self):
        compte = dpers.compter_par_role()
        self.resume.setText("  ·  ".join(f"{lib} : {compte[c]}" for c, lib in dpers.ROLES))
        personnes = dpers.lister(self.combo_role.currentData(), self.recherche.text())
        self.table.blockSignals(True)
        self.table.setRowCount(len(personnes))
        for i, p in enumerate(personnes):
            valeurs = [p["nom"], p["prenom"], "" if p["age"] is None else str(p["age"]),
                       ", ".join(dpers.LIBELLE_ROLE[r] for r in p["roles"]) or "—", p["ville"] or ""]
            for j, v in enumerate(valeurs):
                it = QTableWidgetItem(v)
                it.setData(Qt.ItemDataRole.UserRole, p["id"])
                self.table.setItem(i, j, it)
            if p["id"] == self.personne_id:
                self.table.selectRow(i)
        self.table.blockSignals(False)
        self._remplir_combo_liens()

    def _remplir_combo_liens(self):
        self.combo_lien.clear()
        for p in dpers.lister():
            if p["id"] != self.personne_id:
                self.combo_lien.addItem(f"{p['prenom']} {p['nom']}".strip(), p["id"])

    def _selection(self):
        lignes = self.table.selectionModel().selectedRows()
        if lignes:
            self.charger(self.table.item(lignes[0].row(), 0).data(Qt.ItemDataRole.UserRole))

    def nouvelle(self):
        self.personne_id = None
        self.table.clearSelection()
        for e in self.champ.values():
            e.clear()
        self.naissance.clear()
        self.sexe.setCurrentIndex(0)
        self.notes.clear()
        for c in self.cases.values():
            c.setChecked(False)
            c.setEnabled(True)
        self.liste_liens.clear()
        self.titre_fiche.setText("Nouvelle personne")
        self.info_fiche.setText("Coche « Coureur » pour lui créer aussi un profil sportif (sorties, forme, plans).")
        self.bouton_supprimer.setEnabled(False)
        self._remplir_combo_liens()

    def charger(self, personne_id):
        f = dpers.fiche(personne_id)
        if not f:
            self.nouvelle()
            return
        self.personne_id = personne_id
        for cle, e in self.champ.items():
            e.setText(f.get(cle) or "")
        n = f["date_naissance"]
        self.naissance.setText(QDate.fromString(n, "yyyy-MM-dd").toString("dd/MM/yyyy") if n else "")
        self.sexe.setCurrentIndex(max(0, self.sexe.findData(f["sexe"] or "")))
        self.notes.setPlainText(f.get("notes") or "")
        for code, c in self.cases.items():
            c.setChecked(code in f["roles"])
        # le rôle Coureur porte le profil sportif : il se retire depuis l'onglet Athlètes
        self.cases["coureur"].setEnabled(not f["athlete_id"])
        self.liste_liens.clear()
        for p in f["parents"]:
            it = QListWidgetItem(f"Enfant de {p['prenom']} {p['nom']}".strip())
            it.setData(Qt.ItemDataRole.UserRole, ("parent", p["id"]))
            self.liste_liens.addItem(it)
        for p in f["enfants"]:
            it = QListWidgetItem(f"Parent de {p['prenom']} {p['nom']}".strip())
            it.setData(Qt.ItemDataRole.UserRole, ("enfant", p["id"]))
            self.liste_liens.addItem(it)
        self.titre_fiche.setText(f"{f['prenom']} {f['nom']}".strip())
        morceaux = []
        if f["age"] is not None:
            morceaux.append(f"{f['age']} ans" + (" · mineur" if f["mineur"] else ""))
        morceaux.append("profil coureur : oui" if f["athlete_id"] else "pas de profil coureur")
        morceaux.append(f"identifiant universel {f['uuid']}")
        self.info_fiche.setText(" · ".join(morceaux))
        self.bouton_supprimer.setEnabled(not f["athlete_id"])
        self._remplir_combo_liens()

    def _champs(self):
        d = {k: e.text() for k, e in self.champ.items()}
        d["date_naissance"] = self.naissance.text()
        d["sexe"] = self.sexe.currentData() or ""
        d["notes"] = self.notes.toPlainText()
        return d

    def enregistrer(self):
        champs = self._champs()
        roles = [c for c, case in self.cases.items() if case.isChecked()]
        try:
            if self.personne_id is None:
                existants = dpers.doublons_possibles(champs["nom"], champs["prenom"], champs["date_naissance"] or None)
                if existants:
                    rep = QMessageBox.question(
                        self, "Cette personne existe peut-être déjà",
                        f"Il y a déjà une fiche « {champs['prenom']} {champs['nom']} ». Pour éviter un doublon, "
                        "ouvre plutôt cette fiche et ajoute-lui le rôle voulu.\n\nCréer quand même une nouvelle fiche ?")
                    if rep != QMessageBox.StandardButton.Yes:
                        self.charger(existants[0]["id"])
                        return
                self.personne_id = dpers.creer(champs, roles)
            else:
                dpers.modifier(self.personne_id, champs)
                dpers.definir_roles(self.personne_id, roles)
        except dpers.ErreurPersonne as e:
            QMessageBox.warning(self, "Fiche non enregistrée", str(e))
            return
        self.actualiser()
        self.charger(self.personne_id)

    def supprimer(self):
        if self.personne_id is None:
            return
        rep = QMessageBox.question(self, "Supprimer la fiche ?",
                                   f"Supprimer définitivement la fiche de {self.titre_fiche.text()}, ses rôles et ses liens ?")
        if rep != QMessageBox.StandardButton.Yes:
            return
        try:
            dpers.supprimer(self.personne_id)
        except dpers.ErreurPersonne as e:
            QMessageBox.warning(self, "Suppression impossible", str(e))
            return
        self.nouvelle()
        self.actualiser()

    def _lier(self):
        autre = self.combo_lien.currentData()
        if self.personne_id is None or autre is None:
            QMessageBox.information(self, "Relier", "Enregistre d'abord la fiche, puis choisis la personne à relier.")
            return
        try:
            if self.combo_sens.currentData() == "parent_de":
                dpers.lier_parent(self.personne_id, autre)
            else:
                dpers.lier_parent(autre, self.personne_id)
        except dpers.ErreurPersonne as e:
            QMessageBox.warning(self, "Lien non créé", str(e))
            return
        self.actualiser()
        self.charger(self.personne_id)

    def _delier(self):
        it = self.liste_liens.currentItem()
        if self.personne_id is None or it is None:
            return
        sens, autre = it.data(Qt.ItemDataRole.UserRole)
        if sens == "parent":
            dpers.delier_parent(autre, self.personne_id)
        else:
            dpers.delier_parent(self.personne_id, autre)
        self.charger(self.personne_id)
