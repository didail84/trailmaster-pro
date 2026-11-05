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
    QListWidgetItem, QDialog, QDialogButtonBox, QFileDialog, QInputDialog,
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
        bouton_importer = QPushButton("📥  Importer un passeport coureur…")
        bouton_importer.clicked.connect(self.importer_passeport)
        lg.addWidget(bouton_importer)
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

        li = QLabel("Index de performance")
        li.setObjectName("labelChamp")
        ld.addWidget(li)
        self.liste_index = QListWidget()
        self.liste_index.setFixedHeight(80)
        ld.addWidget(self.liste_index)
        ligne_index = QHBoxLayout()
        self.combo_organisme = QComboBox()
        self.combo_organisme.addItems(dpers.ORGANISMES_INDEX)
        self.combo_organisme.setEditable(True)
        self.valeur_index = QLineEdit()
        self.valeur_index.setPlaceholderText("valeur")
        self.valeur_index.setFixedWidth(80)
        self.date_index = QLineEdit(QDate.currentDate().toString("dd/MM/yyyy"))
        self.date_index.setFixedWidth(110)
        bouton_index = QPushButton("Ajouter")
        bouton_index.clicked.connect(self._ajouter_index)
        bouton_retirer_index = QPushButton("Retirer")
        bouton_retirer_index.clicked.connect(self._retirer_index)
        for w in (self.combo_organisme, self.valeur_index, self.date_index, bouton_index, bouton_retirer_index):
            ligne_index.addWidget(w)
        ld.addLayout(ligne_index)

        boutons = QHBoxLayout()
        self.bouton_enregistrer = QPushButton("Enregistrer")
        self.bouton_enregistrer.setObjectName("boutonPrincipal")
        self.bouton_enregistrer.clicked.connect(self.enregistrer)
        self.bouton_supprimer = QPushButton("Supprimer la fiche")
        self.bouton_supprimer.setObjectName("boutonSecondaire")
        self.bouton_supprimer.clicked.connect(self.supprimer)
        boutons.addWidget(self.bouton_enregistrer)
        boutons.addStretch(1)
        self.bouton_exporter = QPushButton("📤  Exporter le passeport…")
        self.bouton_exporter.clicked.connect(self.exporter_passeport)
        boutons.addWidget(self.bouton_exporter)
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
        self.liste_index.clear()
        self.bouton_exporter.setEnabled(False)
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
        self.bouton_exporter.setEnabled(True)
        self.liste_index.clear()
        for i in dpers.index_de(personne_id):
            jour = QDate.fromString(i["date_releve"], "yyyy-MM-dd").toString("dd/MM/yyyy")
            valeur = f"{i['valeur']:g}".replace(".", ",")
            it = QListWidgetItem(f"{i['organisme']} : {valeur} au {jour}"
                                 + (f" ({i['categorie']})" if i["categorie"] != "Général" else "")
                                 + (f" · {i['source']}" if i["source"] else ""))
            it.setData(Qt.ItemDataRole.UserRole, i["id"])
            self.liste_index.addItem(it)
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

    # ------------------------------------------------------------ index
    def _ajouter_index(self):
        if self.personne_id is None:
            QMessageBox.information(self, "Index", "Enregistre d'abord la fiche.")
            return
        try:
            dpers.ajouter_index(self.personne_id, self.combo_organisme.currentText(), self.valeur_index.text(),
                                self.date_index.text())
        except dpers.ErreurPersonne as e:
            QMessageBox.warning(self, "Index non ajouté", str(e))
            return
        self.valeur_index.clear()
        self.charger(self.personne_id)

    def _retirer_index(self):
        it = self.liste_index.currentItem()
        if it is not None:
            dpers.supprimer_index(it.data(Qt.ItemDataRole.UserRole))
            self.charger(self.personne_id)

    # ------------------------------------------------------------ passeport coureur (étape 2.4)
    def exporter_passeport(self):
        from pathlib import Path
        from noyau import passeport as pp
        if self.personne_id is None:
            return
        dialogue = QDialog(self)
        dialogue.setWindowTitle("Exporter le passeport coureur")
        lay = QVBoxLayout(dialogue)
        intro = QLabel("Le passeport est un fichier que tu peux importer sur un autre ordinateur ou donner à ton club. "
                       "Les sorties et leurs traces n'y sont pas (elles voyagent avec la sauvegarde complète). "
                       "Choisis ce qu'il contient :")
        intro.setWordWrap(True)
        lay.addWidget(intro)
        cases = {}
        for cle, libelle in pp.LIBELLES_CONTENU.items():
            c = QCheckBox(libelle)
            c.setChecked(pp.CONTENU_PAR_DEFAUT[cle])
            cases[cle] = c
            lay.addWidget(c)
        boutons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        boutons.accepted.connect(dialogue.accept)
        boutons.rejected.connect(dialogue.reject)
        lay.addWidget(boutons)
        if dialogue.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            passeport = pp.exporter(self.personne_id, {k: c.isChecked() for k, c in cases.items()})
        except pp.ErreurPasseport as e:
            QMessageBox.warning(self, "Passeport", str(e))
            return
        chemin, _ = QFileDialog.getSaveFileName(self, "Enregistrer le passeport",
                                                str(Path.home() / pp.nom_de_fichier(passeport)),
                                                "Passeport coureur (*.json)")
        if not chemin:
            return
        try:
            pp.ecrire_fichier(chemin, passeport)
        except OSError as e:
            QMessageBox.warning(self, "Passeport", f"Impossible d'écrire le fichier : {e}")
            return
        n = {k: len(passeport.get(k, [])) for k in ("resultats", "index", "courses_a_venir", "objectifs")}
        QMessageBox.information(self, "Passeport enregistré",
                                f"Passeport enregistré :\n{chemin}\n\n{n['resultats']} résultat(s), {n['index']} index, "
                                f"{n['courses_a_venir']} course(s) à venir, {n['objectifs']} objectif(s).")

    def importer_passeport(self):
        from pathlib import Path
        from noyau import passeport as pp
        chemin, _ = QFileDialog.getOpenFileName(self, "Importer un passeport coureur", str(Path.home()),
                                                "Passeport coureur (*.json)")
        if not chemin:
            return
        try:
            passeport = pp.lire_fichier(chemin)
            ap = pp.apercu(passeport)
            cible = None
            if ap["etat"] == "ambigu":
                choix = {}
                for pid in ap["candidats"]:
                    f = dpers.fiche(pid)
                    lib = f"{f['prenom']} {f['nom']}".strip() + (f" — né(e) le {f['date_naissance']}" if f["date_naissance"] else "") \
                        + (f" — {f['ville']}" if f["ville"] else "") + f" (fiche n° {pid})"
                    choix[lib] = pid
                lib, ok = QInputDialog.getItem(self, "Quelle fiche compléter ?",
                                               "Plusieurs fiches portent ce nom. Laquelle correspond à ce passeport ?",
                                               list(choix), 0, False)
                if not ok:
                    return
                cible = choix[lib]
                ap = pp.apercu(passeport, cible)
            boite = QMessageBox(QMessageBox.Icon.Question, "Importer ce passeport ?",
                                "\n".join("• " + l for l in ap["lignes"]) + "\n\nRien n'est ajouté en double.")
            case = QCheckBox("Remplacer mon profil sportif par celui du passeport (sinon seules les cases vides sont complétées)")
            boite.setCheckBox(case)
            boite.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if boite.exec() != QMessageBox.StandardButton.Yes:
                return
            r = pp.importer(passeport, personne_id=cible, remplacer_profil=case.isChecked())
        except pp.ErreurPasseport as e:
            QMessageBox.warning(self, "Passeport non importé", str(e))
            return
        a = r["ajouts"]
        QMessageBox.information(self, "Passeport importé",
                                ("Nouvelle fiche créée." if r["cree"] else "Fiche existante complétée.")
                                + f"\n{a['resultats']} résultat(s), {a['index']} index, {a['courses_a_venir']} course(s) "
                                  f"à venir et {a['objectifs']} objectif(s) ajoutés.")
        self.actualiser()
        self.charger(r["personne_id"])
