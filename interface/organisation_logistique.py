"""
Logistique d'une course (Trail Hub Center, étape 4.6) — cinq onglets de la
fenêtre « 🏁 Organisation » :
  - 📋 Démarches : le contexte de la course (voie publique, communes,
    Natura 2000, forêt, buvette…), la liste des démarches avec leur date
    limite (rétroplanning), le poste de secours, les courriers types ;
  - 🙋 Bénévoles : bénévoles du club et de l'extérieur, postes et
    créneaux, affectations, contrôles, convocations et liste des signaleurs ;
  - 🍌 Ravitaillements : position, type, épreuves, quantités calculées,
    liste de courses ;
  - 📦 Matériel : inventaire, prêts et locations, check-list ;
  - 🤝 Partenaires et budget : mécénat (reçus des dons), parrainage,
    subventions, budget prévisionnel et réalisé, seuil de rentabilité.
Aucune requête SQL ici : tout passe par noyau/donnees/logistique.py.
"""

from datetime import date
from pathlib import Path

from PySide6.QtCore import Qt, QDate, QUrl
from PySide6.QtGui import QColor, QDesktopServices, QGuiApplication
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDateEdit, QDialog, QDoubleSpinBox, QFileDialog, QFormLayout, QGridLayout, QHBoxLayout,
    QLabel, QLineEdit, QListWidget, QListWidgetItem, QMessageBox, QPlainTextEdit, QSpinBox, QTableWidgetItem,
    QVBoxLayout,
)

from noyau.donnees import logistique as dl, organisation as dor, club as dclub
from noyau.organisation import logistique as L
from interface.organisation import _EcranOrga, _boutons, _euros, VERT, ORANGE, ROUGE, GRIS
from interface.calendrier_competitions import _bouton, _cadre, _table, _style_cases
from interface import orga_pdf as P


def _item(v, couleur=None, gras=False):
    it = QTableWidgetItem("" if v is None else str(v))
    if couleur:
        it.setForeground(QColor(couleur))
    if gras:
        f = it.font()
        f.setBold(True)
        it.setFont(f)
    return it


def _remplir(table, lignes, couleurs=None):
    table.setRowCount(len(lignes))
    for r, l in enumerate(lignes):
        for c, v in enumerate(l):
            table.setItem(r, c, _item(v, (couleurs or {}).get((r, c)) or (couleurs or {}).get(r)))
    table.resizeColumnsToContents()


def _ligne_choisie(table, liste):
    r = table.currentRow()
    return liste[r] if 0 <= r < len(liste) else None


def _lignes_choisies(table, liste):
    rows = sorted({i.row() for i in table.selectedIndexes()})
    return [liste[r] for r in rows if r < len(liste)]


def _ouvrir_pdf(parent, nom, html, paysage=False):
    chemin, _ = QFileDialog.getSaveFileName(parent, "Enregistrer le PDF", nom, "PDF (*.pdf)")
    if chemin:
        P.rendre(chemin, Path(chemin).stem, html, paysage)
        QDesktopServices.openUrl(QUrl.fromLocalFile(chemin))
    return chemin


def _km(v):
    return "" if v is None else f"{v:g}"


# ======================================================================
# Dialogue générique : une liste de champs décrits
# ======================================================================

class DialogueChamps(QDialog):
    """spec : [(genre, clé, libellé, options)] ; genres : texte, long, entier, reel, euros, date, heure, choix,
    case, multi. enregistrer(champs) peut lever une erreur lisible : le dialogue reste ouvert."""

    def __init__(self, parent, titre, spec, valeurs=None, enregistrer=None, largeur=520):
        super().__init__(parent)
        self.setWindowTitle(titre)
        self.setMinimumWidth(largeur)
        self.spec, self.valeurs, self.enregistrer, self.resultat = spec, valeurs or {}, enregistrer, None
        lay = QVBoxLayout(self)
        form = QFormLayout()
        self.w = {}
        for genre, cle, lib, opt in spec:
            v = self.valeurs.get(cle)
            opt = opt or {}
            if genre == "texte":
                w = QLineEdit(v or "")
                w.setPlaceholderText(opt.get("aide", ""))
            elif genre == "long":
                w = QPlainTextEdit(v or "")
                w.setFixedHeight(opt.get("hauteur", 70))
            elif genre == "entier":
                w = QSpinBox()
                w.setRange(opt.get("min", 0), opt.get("max", 100000))
                w.setValue(int(v or opt.get("defaut", 0)))
            elif genre in ("reel", "euros"):
                w = QDoubleSpinBox()
                w.setRange(0, opt.get("max", 1000000))
                w.setDecimals(opt.get("decimales", 2 if genre == "euros" else 1))
                if genre == "euros":
                    w.setSuffix(" €")
                elif opt.get("suffixe"):
                    w.setSuffix(opt["suffixe"])
                w.setValue(float(v or 0))
            elif genre == "date":
                case = QCheckBox()
                d = QDateEdit(QDate.fromString(str(v)[:10], "yyyy-MM-dd") if v else QDate.currentDate())
                d.setCalendarPopup(True)
                d.setDisplayFormat("dd/MM/yyyy")
                case.setChecked(bool(v))
                d.setEnabled(bool(v))
                case.toggled.connect(d.setEnabled)
                h = QHBoxLayout()
                h.addWidget(case)
                h.addWidget(d, 1)
                form.addRow(lib, h)
                self.w[cle] = (genre, (case, d))
                continue
            elif genre == "heure":
                w = QLineEdit(v or "")
                w.setPlaceholderText("07:30")
                w.setMaximumWidth(90)
            elif genre == "choix":
                w = QComboBox()
                for code, l in opt["choix"]:
                    w.addItem(l, code)
                i = w.findData(v)
                w.setCurrentIndex(max(0, i if v is not None else w.findData(opt.get("defaut"))))
            elif genre == "case":
                w = QCheckBox(opt.get("texte", ""))
                w.setChecked(bool(v))
            elif genre == "multi":
                w = QListWidget()
                w.setFixedHeight(min(140, 28 * max(1, len(opt["choix"])) + 8))
                coches = set(v or [])
                for code, l in opt["choix"]:
                    it = QListWidgetItem(l)
                    it.setData(Qt.ItemDataRole.UserRole, code)
                    it.setFlags(it.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                    it.setCheckState(Qt.CheckState.Checked if code in coches else Qt.CheckState.Unchecked)
                    w.addItem(it)
            else:
                raise ValueError(genre)
            form.addRow(lib, w)
            self.w[cle] = (genre, w)
        lay.addLayout(form)
        self.message = QLabel("")
        self.message.setWordWrap(True)
        self.message.setStyleSheet(f"color: {ROUGE};")
        lay.addWidget(self.message)
        _boutons(self, lay)
        _style_cases(self)

    def champs(self):
        res = {}
        for cle, (genre, w) in self.w.items():
            if genre == "texte" or genre == "heure":
                res[cle] = w.text().strip() or None
            elif genre == "long":
                res[cle] = w.toPlainText().strip() or None
            elif genre == "entier":
                res[cle] = w.value()
            elif genre in ("reel", "euros"):
                res[cle] = w.value()
            elif genre == "date":
                case, d = w
                res[cle] = d.date().toString("yyyy-MM-dd") if case.isChecked() else None
            elif genre == "choix":
                res[cle] = w.currentData()
            elif genre == "case":
                res[cle] = w.isChecked()
            elif genre == "multi":
                res[cle] = [w.item(i).data(Qt.ItemDataRole.UserRole) for i in range(w.count())
                            if w.item(i).checkState() == Qt.CheckState.Checked]
        return res

    def accept(self):
        c = self.champs()
        if self.enregistrer:
            try:
                self.resultat = self.enregistrer(c)
            except (dl.ErreurLogistique, ValueError) as e:
                self.message.setText(str(e))
                return
        else:
            self.resultat = c
        super().accept()


class DialogueTexte(QDialog):
    """Texte à relire, copier ou mettre en PDF (courriers, adresses e-mail)."""

    def __init__(self, parent, titre, texte, nom_pdf=None):
        super().__init__(parent)
        self.setWindowTitle(titre)
        self.resize(720, 620)
        lay = QVBoxLayout(self)
        aide = QLabel("Tu peux corriger le texte ici ; ce qui est entre crochets [ ] est à compléter.")
        aide.setObjectName("texteSecondaire")
        lay.addWidget(aide)
        self.texte = QPlainTextEdit(texte)
        lay.addWidget(self.texte, 1)
        h = QHBoxLayout()
        cop = _bouton("📋 Copier", True)
        cop.clicked.connect(lambda: QGuiApplication.clipboard().setText(self.texte.toPlainText()))
        h.addWidget(cop)
        if nom_pdf:
            pdf = _bouton("📄 PDF")
            pdf.clicked.connect(lambda: _ouvrir_pdf(self, nom_pdf, P.html_courrier(self.texte.toPlainText())))
            h.addWidget(pdf)
        h.addStretch()
        fermer = _bouton("Fermer")
        fermer.clicked.connect(self.accept)
        h.addWidget(fermer)
        lay.addLayout(h)


# ======================================================================
# 📋 Démarches et rétroplanning
# ======================================================================

FILTRES_DEMARCHES = (("actives", "À suivre (hors sans objet)"), ("retard", "En retard"), ("bientot", "Dans les 15 jours"),
                     ("faites", "Faites"), ("toutes", "Toutes"))


class DemarchesOrga(_EcranOrga):

    def __init__(self, athlete_id_initial=None):
        super().__init__("📋  Démarches et rétroplanning", "Réponds aux questions sur ta course : le logiciel liste les "
                         "déclarations, autorisations et étapes à prévoir avec leur date limite. Rappels à jour de "
                         "novembre 2026 : vérifie toujours auprès de la mairie, de la préfecture et du comité FFA.",
                         athlete_id_initial)
        ligne = QHBoxLayout()
        self.cartes = {k: self._carte(t) for k, t in (("total", "Démarches"), ("retard", "En retard"),
                                                     ("bientot", "Dans les 15 jours"), ("dps", "Secours du public"))}
        for c in self.cartes.values():
            ligne.addWidget(c, 1)
        self.principal.addLayout(ligne)
        cadre, lc = _cadre("Ta course")
        grille = QGridLayout()
        self.q = {}
        r = c = 0
        for cle, lib in L.QUESTIONS:
            if isinstance(L.CONTEXTE_DEFAUT[cle], bool):
                w = QCheckBox(lib)
                grille.addWidget(w, r, c * 2, 1, 2)
            else:
                w = QSpinBox()
                w.setRange(0 if cle not in ("communes", "departements") else 1, 1000000)
                if cle == "prix_total":
                    w.setSuffix(" €")
                grille.addWidget(QLabel(lib), r, c * 2)
                grille.addWidget(w, r, c * 2 + 1)
            self.q[cle] = w
            c += 1
            if c == 2:
                r, c = r + 1, 0
        lc.addLayout(grille)
        hd = QHBoxLayout()
        self.dps_combos = {}
        for cle, niveaux, lib in (("dps_activite", L.NIVEAUX_ACTIVITE, "Public"),
                                  ("dps_environnement", L.NIVEAUX_ENVIRONNEMENT, "Site"),
                                  ("dps_delai", L.NIVEAUX_DELAI, "Délai des secours")):
            cb = QComboBox()
            for v, t in niveaux:
                cb.addItem(t, v)
            cb.setMinimumWidth(220)
            hd.addWidget(QLabel(lib + " :"))
            hd.addWidget(cb, 1)
            self.dps_combos[cle] = cb
        lc.addLayout(hd)
        b = QHBoxLayout()
        maj = _bouton("💾 Enregistrer et mettre à jour les démarches", True)
        maj.clicked.connect(self._enregistrer_contexte)
        b.addWidget(maj)
        self.info_ctx = QLabel("")
        self.info_ctx.setObjectName("texteSecondaire")
        self.info_ctx.setWordWrap(True)
        b.addWidget(self.info_ctx, 1)
        lc.addLayout(b)
        self.principal.addWidget(cadre)

        cadre, lc = _cadre("Rétroplanning")
        h = QHBoxLayout()
        self.filtre = QComboBox()
        for k, t in FILTRES_DEMARCHES:
            self.filtre.addItem(t, k)
        self.filtre.currentIndexChanged.connect(lambda _i: self._remplir())
        self.filtre_cat = QComboBox()
        self.filtre_cat.addItem("Toutes les catégories", None)
        for k in L.CATEGORIES:
            self.filtre_cat.addItem(k, k)
        self.filtre_cat.currentIndexChanged.connect(lambda _i: self._remplir())
        h.addWidget(self.filtre)
        h.addWidget(self.filtre_cat)
        h.addStretch()
        lc.addLayout(h)
        self.table = _table(["Échéance", "Quand", "Démarche", "Catégorie", "Auprès de", "Statut", "Notes"], 380)
        self.table.itemSelectionChanged.connect(self._detail)
        self.table.doubleClicked.connect(lambda _i: self._modifier())
        lc.addWidget(self.table)
        self.detail = QLabel("")
        self.detail.setWordWrap(True)
        self.detail.setObjectName("texteSecondaire")
        self.detail.setTextFormat(Qt.TextFormat.RichText)
        lc.addWidget(self.detail)
        b = QHBoxLayout()
        self.statut = QComboBox()
        for k, t in L.STATUTS:
            self.statut.addItem(t, k)
        app = _bouton("Changer le statut")
        app.clicked.connect(self._statut)
        aj = _bouton("➕ Ajouter une démarche")
        aj.clicked.connect(self._ajouter)
        mo = _bouton("✏️ Modifier")
        mo.clicked.connect(self._modifier)
        su = _bouton("🗑️ Supprimer")
        su.clicked.connect(self._supprimer)
        pdf = _bouton("📄 Rétroplanning (PDF)")
        pdf.clicked.connect(self._pdf)
        ics = _bouton("📅 Échéances (.ics)")
        ics.clicked.connect(self._ics)
        for w in (self.statut, app, aj, mo, su, pdf, ics):
            b.addWidget(w)
        b.addStretch()
        lc.addLayout(b)
        self.principal.addWidget(cadre)

        cadre, lc = _cadre("Courriers types")
        h = QHBoxLayout()
        self.courrier = QComboBox()
        for k, t in L.COURRIERS:
            self.courrier.addItem(t, k)
        self.destinataire = QLineEdit()
        self.destinataire.setPlaceholderText("Destinataire (ex. : Mairie de Gigondas)")
        ouv = _bouton("✉️ Préparer le courrier", True)
        ouv.clicked.connect(self._courrier)
        h.addWidget(self.courrier)
        h.addWidget(self.destinataire, 1)
        h.addWidget(ouv)
        lc.addLayout(h)
        self.principal.addWidget(cadre)
        self.principal.addStretch()
        self._ds, self._vues = [], []
        self._finir()

    # -- contexte
    def _charger_contexte(self, c):
        for cle, w in self.q.items():
            if isinstance(w, QCheckBox):
                w.setChecked(bool(c.get(cle)))
            else:
                w.setValue(int(c.get(cle) or 0))
        for cle, cb in self.dps_combos.items():
            cb.setCurrentIndex(max(0, cb.findData(c.get(cle))))

    def contexte_saisi(self):
        v = {cle: (w.isChecked() if isinstance(w, QCheckBox) else w.value()) for cle, w in self.q.items()}
        v.update({cle: cb.currentData() for cle, cb in self.dps_combos.items()})
        return v

    def _enregistrer_contexte(self):
        if not self.evenement_id:
            return
        dl.enregistrer_contexte(self.evenement_id, self.contexte_saisi())
        r = dl.generer_demarches(self.evenement_id)
        self.rafraichir()
        self.info_ctx.setText(f"{r['ajoutees']} démarche(s) ajoutée(s), {r['mises_a_jour']} mise(s) à jour, "
                              f"{r['retirees']} qui ne s'applique(nt) plus.")

    def rafraichir(self):
        ev = self.evenement_id
        for c in self.cartes.values():
            c.valeur.setText("—")
            c.detail.setText("")
        if not ev:
            self._ds = []
            self._remplir()
            return
        ctx = dl.contexte(ev)
        self._charger_contexte(ctx)
        if not dl.demarches(ev, brut=True):
            dl.generer_demarches(ev)
        self._ds = dl.demarches(ev)
        b = L.bilan_demarches(self._ds)
        self.cartes["total"].valeur.setText(f"{b['faites']} / {b['total']}")
        self.cartes["total"].detail.setText("faites ou sans objet")
        self.cartes["retard"].valeur.setText(str(b["en_retard"]))
        self.cartes["retard"].valeur.setStyleSheet(f"font-size: 24px; font-weight: 700; color: {ROUGE if b['en_retard'] else VERT};")
        self.cartes["retard"].detail.setText(f"{b['en_attente']} envoyée(s), réponse attendue")
        self.cartes["bientot"].valeur.setText(str(b["bientot"]))
        d = L.dps(ctx["spectateurs"], ctx["dps_activite"], ctx["dps_environnement"], ctx["dps_delai"])
        self.cartes["dps"].valeur.setText(d["dispositif"] if d["dispositif"] != "aucun" else "—")
        self.cartes["dps"].detail.setText(f"{ctx['spectateurs']} personnes, RIS {d['ris']:g} : {d['texte']} "
                                          "Coureurs : analyse à part avec l'association agréée.")
        self.info_ctx.setText(f"Département {ctx['departement'] or '?'} (code postal de l'événement), "
                              f"{ctx['participants']} coureurs attendus.")
        self._remplir()

    def _remplir(self):
        f, cat = self.filtre.currentData(), self.filtre_cat.currentData()
        garde = {"actives": lambda d: d["statut"] != "sans_objet", "retard": lambda d: d["etat"] == "en retard",
                 "bientot": lambda d: d["etat"] == "bientôt", "faites": lambda d: d["etat"] == "faite",
                 "toutes": lambda d: True}[f or "actives"]
        self._vues = [d for d in self._ds if garde(d) and (not cat or d["categorie"] == cat)]
        coul = {}
        for r, d in enumerate(self._vues):
            coul[r] = {"en retard": ROUGE, "bientôt": ORANGE, "faite": VERT, "refusée": ROUGE}.get(d["etat"]) \
                or (GRIS if d["statut"] == "sans_objet" else None)
        _remplir(self.table, [(P._jour(d["echeance"]), d["jalon"], d["titre"], d["categorie"] or "", d["autorite"] or "",
                               L.LIBELLE_STATUT.get(d["statut"], "") + (f" · {d['etat']}" if d["etat"] in ("en retard", "bientôt") else ""),
                               (d["notes"] or "")[:60]) for d in self._vues], coul)
        self.table.setColumnWidth(2, min(self.table.columnWidth(2), 380))
        self._detail()

    def _detail(self):
        d = _ligne_choisie(self.table, self._vues)
        if not d:
            self.detail.setText("Sélectionne une démarche pour voir les pièces à fournir et le conseil.")
            return
        import html as h
        self.detail.setText(f"<b>{h.escape(d['titre'])}</b><br>Pièces : {h.escape(d['pieces'] or '—')}"
                            + (f"<br>💡 {h.escape(d['conseil'])}" if d.get("conseil") else "")
                            + (f"<br>Envoyé le {P._jour(d['date_envoi'])}" if d.get("date_envoi") else "")
                            + (f" · réponse le {P._jour(d['date_reponse'])}" if d.get("date_reponse") else "")
                            + (f" · réf. {h.escape(d['reference'])}" if d.get("reference") else ""))

    def _spec(self):
        return [("texte", "titre", "Démarche", None), ("choix", "categorie", "Catégorie", {"choix": [(c, c) for c in L.CATEGORIES]}),
                ("texte", "autorite", "Auprès de", None), ("long", "pieces", "Pièces", None),
                ("date", "echeance", "Échéance", None), ("choix", "statut", "Statut", {"choix": L.STATUTS}),
                ("date", "date_envoi", "Envoyé le", None), ("date", "date_reponse", "Réponse le", None),
                ("texte", "reference", "Référence (récépissé, arrêté)", None), ("long", "notes", "Notes", None)]

    def _ajouter(self):
        if self.evenement_id:
            d = DialogueChamps(self, "Nouvelle démarche", self._spec(), {"categorie": "Administratif"},
                               lambda c: dl.enregistrer_demarche(self.evenement_id, c))
            if d.exec():
                self.rafraichir()

    def _modifier(self):
        x = _ligne_choisie(self.table, self._vues)
        if x:
            d = DialogueChamps(self, "Démarche", self._spec(), x, lambda c: dl.enregistrer_demarche(self.evenement_id, c, x["id"]))
            if d.exec():
                self.rafraichir()

    def _statut(self):
        xs = _lignes_choisies(self.table, self._vues)
        if xs:
            dl.changer_statut_demarches([x["id"] for x in xs], self.statut.currentData())
            self.rafraichir()

    def _supprimer(self):
        x = _ligne_choisie(self.table, self._vues)
        if x and QMessageBox.question(self, "Démarche", "Supprimer cette démarche ? (Une démarche réglementaire passe "
                                      "« sans objet ».)") == QMessageBox.StandardButton.Yes:
            dl.supprimer_demarche(x["id"])
            self.rafraichir()

    def _pdf(self):
        if self.evenement_id:
            _ouvrir_pdf(self, "Retroplanning.pdf", P.html_retroplanning(dor.evenement(self.evenement_id), self._ds), True)

    def _ics(self):
        if not self.evenement_id:
            return
        chemin, _ = QFileDialog.getSaveFileName(self, "Échéances", "Echeances de la course.ics", "Agenda (*.ics)")
        if chemin:
            Path(chemin).write_text(texte_ics(dor.evenement(self.evenement_id), self._ds), encoding="utf-8")
            QMessageBox.information(self, "Échéances", "Fichier enregistré : ouvre-le pour ajouter les échéances à ton agenda.")

    def _courrier(self):
        if not self.evenement_id:
            return
        ev = dor.evenement(self.evenement_id)
        objet, texte = L.courrier(self.courrier.currentData(), ev, dor.epreuves(self.evenement_id), dclub.club_principal(),
                                  {"nom": self.destinataire.text().strip() or None}, dl.contexte(self.evenement_id))
        DialogueTexte(self, self.courrier.currentText(), texte, f"{objet[8:50].strip()}.pdf").exec()


def texte_ics(ev, demarches):
    """Une échéance par démarche non faite (journée entière)."""
    lignes = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Trail Hub Center//Organisation//FR"]
    for d in demarches:
        if d["statut"] in L.FINIS or not d.get("echeance"):
            continue
        j = d["echeance"].replace("-", "")
        texte = f"{d['titre']} ({ev['nom']})".replace(",", "\\,").replace(";", "\\;")
        desc = f"Auprès de : {d.get('autorite') or ''}. Pièces : {d.get('pieces') or ''}".replace(",", "\\,").replace(";", "\\;")
        lignes += ["BEGIN:VEVENT", f"UID:thc-demarche-{d['id']}@trailhub", f"DTSTAMP:{date.today().strftime('%Y%m%d')}T000000Z",
                   f"DTSTART;VALUE=DATE:{j}", f"SUMMARY:{texte}", f"DESCRIPTION:{desc}", "END:VEVENT"]
    lignes.append("END:VCALENDAR")
    return "\r\n".join(lignes) + "\r\n"


# ======================================================================
# 🙋 Bénévoles, postes, affectations
# ======================================================================

class DialoguePersonnes(QDialog):
    """Adhérents du club à ajouter comme bénévoles."""

    def __init__(self, parent, deja):
        super().__init__(parent)
        self.setWindowTitle("Bénévoles du club")
        self.resize(460, 560)
        lay = QVBoxLayout(self)
        cid = (dclub.club_principal() or {}).get("id")
        saisons = dclub.saisons(cid) if cid else []
        self.liste = QListWidget()
        if cid and saisons:
            for a in dclub.adhesions(cid, saisons[0]):
                if a["statut"] == "annulee":
                    continue
                it = QListWidgetItem(f"{a['nom']} {a.get('prenom') or ''}".strip())
                it.setData(Qt.ItemDataRole.UserRole, a["personne_id"])
                it.setFlags(it.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                it.setCheckState(Qt.CheckState.Unchecked)
                if a["personne_id"] in deja:
                    it.setFlags(it.flags() & ~Qt.ItemFlag.ItemIsEnabled)
                    it.setText(it.text() + " (déjà bénévole)")
                self.liste.addItem(it)
        lay.addWidget(QLabel(f"Adhérents de la saison {saisons[0]} :" if saisons else
                             "Pas encore d'adhérents : ouvre le module Club ou ajoute les bénévoles à la main."))
        lay.addWidget(self.liste, 1)
        _boutons(self, lay, "Ajouter")

    def choisis(self):
        return [self.liste.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.liste.count())
                if self.liste.item(i).checkState() == Qt.CheckState.Checked]


class DialogueImportBenevoles(QDialog):

    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle("Importer des bénévoles")
        self.resize(640, 460)
        lay = QVBoxLayout(self)
        a = QLabel("Colle le tableau des réponses (formulaire HelloAsso, Google Forms, tableur) ou choisis un fichier "
                   "CSV. Colonnes reconnues : nom, prénom, téléphone, e-mail, date de naissance, permis, secouriste, "
                   "taille, disponibilités, poste souhaité. Les bénévoles déjà présents ne sont pas ajoutés deux fois.")
        a.setWordWrap(True)
        lay.addWidget(a)
        self.texte = QPlainTextEdit()
        lay.addWidget(self.texte, 1)
        f = _bouton("📂 Choisir un fichier…")
        f.clicked.connect(self._fichier)
        lay.addWidget(f)
        self.contenu, self.nom = None, "colle.csv"
        _boutons(self, lay, "Importer")

    def _fichier(self):
        chemin, _ = QFileDialog.getOpenFileName(self, "Fichier des bénévoles", "", "Tableaux (*.csv *.txt *.xlsx)")
        if chemin:
            self.contenu, self.nom = Path(chemin).read_bytes(), Path(chemin).name
            self.texte.setPlainText(f"Fichier choisi : {self.nom}")

    def donnees(self):
        return (self.contenu, self.nom) if self.contenu else (self.texte.toPlainText(), "colle.csv")


class BenevolesOrga(_EcranOrga):

    def __init__(self, athlete_id_initial=None):
        super().__init__("🙋  Bénévoles", "Les bénévoles du club et de l'extérieur, les postes et leurs créneaux, "
                         "les affectations. Le logiciel signale les postes à compléter, les conflits d'horaires et les "
                         "signaleurs qui doivent être majeurs avec le permis.", athlete_id_initial)
        ligne = QHBoxLayout()
        self.cartes = {k: self._carte(t) for k, t in (("benevoles", "Bénévoles"), ("pourvus", "Places pourvues"),
                                                     ("manques", "Postes à compléter"), ("alertes", "À vérifier"))}
        for c in self.cartes.values():
            ligne.addWidget(c, 1)
        self.principal.addLayout(ligne)
        cadre, lc = _cadre("Postes et créneaux")
        self.table_postes = _table(["Poste", "Type", "Jour", "Horaires", "Lieu", "Pourvu", "Bénévoles"], 300)
        self.table_postes.doubleClicked.connect(lambda _i: self._modifier_poste())
        lc.addWidget(self.table_postes)
        b = QHBoxLayout()
        for t, f, p in (("✨ Créer les postes types", self._postes_types, True), ("➕ Poste", self._ajouter_poste, False),
                        ("✏️ Modifier", self._modifier_poste, False), ("🗑️ Supprimer", self._supprimer_poste, False),
                        ("📄 Planning (PDF)", self._pdf_planning, False), ("📄 Signaleurs (PDF)", self._pdf_signaleurs, False)):
            w = _bouton(t, p)
            w.clicked.connect(f)
            b.addWidget(w)
        b.addStretch()
        lc.addLayout(b)
        self.principal.addWidget(cadre)
        cadre, lc = _cadre("Bénévoles")
        self.table = _table(["Nom", "Prénom", "Téléphone", "Âge", "Permis", "Secouriste", "Postes", "Statut", "Source"], 300)
        self.table.doubleClicked.connect(lambda _i: self._modifier())
        lc.addWidget(self.table)
        b = QHBoxLayout()
        for t, f, p in (("➕ Bénévole", self._ajouter, False), ("👥 Adhérents du club…", self._club, False),
                        ("📥 Importer…", self._importer, False), ("✏️ Modifier", self._modifier, False),
                        ("🗑️ Supprimer", self._supprimer, False)):
            w = _bouton(t, p)
            w.clicked.connect(f)
            b.addWidget(w)
        b.addStretch()
        lc.addLayout(b)
        b = QHBoxLayout()
        aff = _bouton("⬆️ Affecter au poste sélectionné", True)
        aff.clicked.connect(self._affecter)
        ret = _bouton("Retirer du poste")
        ret.clicked.connect(self._retirer)
        conv = _bouton("📄 Convocations (PDF)")
        conv.clicked.connect(self._pdf_convocations)
        mails = _bouton("📧 Copier les e-mails")
        mails.clicked.connect(self._emails)
        for w in (aff, ret, conv, mails):
            b.addWidget(w)
        b.addStretch()
        lc.addLayout(b)
        self.alertes = QLabel("")
        self.alertes.setWordWrap(True)
        self.alertes.setTextFormat(Qt.TextFormat.RichText)
        lc.addWidget(self.alertes)
        self.principal.addWidget(cadre)
        self.principal.addStretch()
        self._postes, self._bvs, self._ctl = [], [], None
        self._finir()

    def rafraichir(self):
        ev = self.evenement_id
        self._postes = dl.postes(ev) if ev else []
        self._bvs = dl.benevoles(ev) if ev else []
        self._ctl = dl.controle(ev) if ev else None
        coul = {}
        lignes = []
        for r, p in enumerate(self._postes):
            n, besoin = len(p["benevoles"]), int(p["besoin"] or 0)
            coul[(r, 5)] = VERT if n >= besoin else (ORANGE if n else ROUGE)
            lignes.append((p["nom"], p["libelle_type"], P._jour(p["jour"]), f"{p['heure_debut'] or ''} – {p['heure_fin'] or ''}",
                           (p["lieu"] or "") + (f" (km {_km(p['km'])})" if p.get("km") else ""), f"{n} / {besoin}",
                           ", ".join(f"{b.get('prenom') or ''} {b['nom']}".strip() for b in p["benevoles"])))
        _remplir(self.table_postes, lignes, coul)
        jour = (dor.evenement(ev) or {}).get("date_debut") if ev else None
        par_b = self._ctl["par_benevole"] if self._ctl else {}
        noms_postes = {p["id"]: p["nom"] for p in self._postes}
        lignes, coul = [], {}
        for r, b in enumerate(self._bvs):
            a = L.age(b["date_naissance"], jour) if jour else None
            if b["statut"] == "desiste":
                coul[r] = GRIS
            lignes.append((b["nom"], b["prenom"] or "", b["telephone"] or "", "" if a is None else a, "oui" if b["permis"] else "",
                           "oui" if b["secouriste"] else "", ", ".join(noms_postes[i] for i in par_b.get(b["id"], [])),
                           dl.LIBELLE_STATUT_BENEVOLE.get(b["statut"], ""), b["source"] or ""))
        _remplir(self.table, lignes, coul)
        c = self.cartes
        if not self._ctl:
            for x in c.values():
                x.valeur.setText("—")
            self.alertes.setText("")
            return
        ctl = self._ctl
        c["benevoles"].valeur.setText(str(len([b for b in self._bvs if b["statut"] != "desiste"])))
        c["benevoles"].detail.setText(f"{len(ctl['sans_poste'])} sans poste")
        c["pourvus"].valeur.setText(f"{ctl['pourvus']} / {ctl['besoin']}")
        c["manques"].valeur.setText(str(len(ctl["manques"])))
        c["manques"].detail.setText(", ".join(f"{m['poste']} ({m['manque']})" for m in ctl["manques"][:4]))
        c["alertes"].valeur.setText(str(len(ctl["conflits"]) + len(ctl["alertes"])))
        import html as h
        self.alertes.setText("<br>".join([f"⚠️ {h.escape(x)}" for x in ctl["conflits"] + ctl["alertes"]]) or
                             "Sélectionne un poste en haut et un ou plusieurs bénévoles ici, puis « Affecter ».")

    # -- postes
    def _spec_poste(self):
        rav = [(None, "—")] + [(r["id"], f"{r['nom']} (km {_km(r['km'])})") for r in dl.ravitaillements(self.evenement_id, False)]
        resp = [(None, "—")] + [(b["id"], f"{b.get('prenom') or ''} {b['nom']}".strip()) for b in self._bvs]
        return [("texte", "nom", "Poste", None), ("choix", "type", "Type", {"choix": L.TYPES_POSTE}),
                ("date", "jour", "Jour", None), ("heure", "heure_debut", "Début", None), ("heure", "heure_fin", "Fin", None),
                ("texte", "lieu", "Lieu", None), ("reel", "km", "Kilomètre", {"suffixe": " km"}),
                ("entier", "besoin", "Bénévoles nécessaires", {"defaut": 1}),
                ("choix", "responsable_id", "Responsable du poste", {"choix": resp}),
                ("choix", "ravitaillement_id", "Ravitaillement", {"choix": rav}), ("long", "consignes", "Consignes", None)]

    def _ajouter_poste(self):
        if self.evenement_id:
            ev = dor.evenement(self.evenement_id)
            d = DialogueChamps(self, "Nouveau poste", self._spec_poste(), {"jour": ev["date_debut"], "besoin": 1},
                               lambda c: dl.enregistrer_poste(self.evenement_id, c))
            if d.exec():
                self.rafraichir()

    def _modifier_poste(self):
        p = _ligne_choisie(self.table_postes, self._postes)
        if p:
            d = DialogueChamps(self, "Poste", self._spec_poste(), p, lambda c: dl.enregistrer_poste(self.evenement_id, c, p["id"]))
            if d.exec():
                self.rafraichir()

    def _supprimer_poste(self):
        p = _ligne_choisie(self.table_postes, self._postes)
        if p and QMessageBox.question(self, "Poste", f"Supprimer le poste « {p['nom']} » et ses affectations ?") == \
                QMessageBox.StandardButton.Yes:
            dl.supprimer_poste(p["id"])
            self.rafraichir()

    def _postes_types(self):
        if self.evenement_id:
            n = dl.creer_postes_suggeres(self.evenement_id)
            QMessageBox.information(self, "Postes", f"{n} poste(s) créé(s) d'après les épreuves, les ravitaillements et "
                                    "le contexte (onglet Démarches). Ajuste les horaires et les besoins.")
            self.rafraichir()

    # -- bénévoles
    def _spec(self):
        return [("texte", "nom", "Nom", None), ("texte", "prenom", "Prénom", None), ("texte", "telephone", "Téléphone", None),
                ("texte", "email", "E-mail", None), ("date", "date_naissance", "Date de naissance", None),
                ("case", "permis", "Permis de conduire", {"texte": "oui"}), ("case", "secouriste", "Secouriste (PSC1, PSE)", {"texte": "oui"}),
                ("texte", "taille_tshirt", "Taille t-shirt", None), ("texte", "disponibilites", "Disponibilités", None),
                ("texte", "competences", "Poste souhaité, compétences", None),
                ("choix", "statut", "Statut", {"choix": dl.STATUTS_BENEVOLE}), ("long", "notes", "Notes", None)]

    def _ajouter(self):
        if self.evenement_id:
            d = DialogueChamps(self, "Nouveau bénévole", self._spec(), {"statut": "confirme"},
                               lambda c: dl.enregistrer_benevole(self.evenement_id, {**c, "source": "Saisie"}))
            if d.exec():
                self.rafraichir()

    def _modifier(self):
        b = _ligne_choisie(self.table, self._bvs)
        if b:
            d = DialogueChamps(self, "Bénévole", self._spec(), b, lambda c: dl.enregistrer_benevole(self.evenement_id, c, b["id"]))
            if d.exec():
                self.rafraichir()

    def _supprimer(self):
        b = _ligne_choisie(self.table, self._bvs)
        if b and QMessageBox.question(self, "Bénévole", f"Retirer {b['nom']} des bénévoles de la course ?") == \
                QMessageBox.StandardButton.Yes:
            dl.supprimer_benevole(b["id"])
            self.rafraichir()

    def _club(self):
        if not self.evenement_id:
            return
        d = DialoguePersonnes(self, {b["personne_id"] for b in self._bvs if b["personne_id"]})
        if d.exec():
            n = dl.ajouter_personnes(self.evenement_id, d.choisis())
            QMessageBox.information(self, "Bénévoles", f"{n} adhérent(s) ajouté(s).")
            self.rafraichir()

    def _importer(self):
        if not self.evenement_id:
            return
        d = DialogueImportBenevoles(self)
        if d.exec():
            try:
                r = dl.importer_benevoles(self.evenement_id, *d.donnees())
            except (dl.ErreurLogistique, ValueError) as e:
                QMessageBox.warning(self, "Import", str(e))
                return
            QMessageBox.information(self, "Import", f"{r['ajoutes']} bénévole(s) ajouté(s), {r['deja']} déjà présent(s), "
                                    f"{r['ignores']} ligne(s) sans nom.")
            self.rafraichir()

    def _affecter(self):
        p = _ligne_choisie(self.table_postes, self._postes)
        bs = _lignes_choisies(self.table, self._bvs)
        if not p or not bs:
            QMessageBox.information(self, "Affecter", "Sélectionne un poste (en haut) et un ou plusieurs bénévoles.")
            return
        for b in bs:
            dl.affecter(p["id"], b["id"])
        self.rafraichir()

    def _retirer(self):
        p = _ligne_choisie(self.table_postes, self._postes)
        for b in _lignes_choisies(self.table, self._bvs):
            if p:
                dl.desaffecter(p["id"], b["id"])
        self.rafraichir()

    def _emails(self):
        m = [b["email"] for b in self._bvs if b.get("email") and b["statut"] != "desiste"]
        QGuiApplication.clipboard().setText("; ".join(m))
        QMessageBox.information(self, "E-mails", f"{len(m)} adresse(s) copiée(s) : colle-les dans le champ « Cci » "
                                "de ton message.")

    def _pdf_planning(self):
        if self.evenement_id:
            _ouvrir_pdf(self, "Planning des benevoles.pdf", P.html_planning_postes(dor.evenement(self.evenement_id), self._postes), True)

    def _pdf_signaleurs(self):
        if self.evenement_id:
            club = dclub.club_principal() or {}
            _ouvrir_pdf(self, "Liste des signaleurs.pdf", P.html_signaleurs(dor.evenement(self.evenement_id),
                                                                            dl.signaleurs(self.evenement_id),
                                                                            club.get("nom") or ""), True)

    def _pdf_convocations(self):
        if self.evenement_id:
            ev = dor.evenement(self.evenement_id)
            _ouvrir_pdf(self, "Convocations des benevoles.pdf",
                        P.html_convocations(ev, [b for b in self._bvs if b["statut"] != "desiste"], self._postes,
                                            ev.get("contact_email") or ""))


# ======================================================================
# 🍌 Ravitaillements
# ======================================================================

class RavitosOrga(_EcranOrga):

    def __init__(self, athlete_id_initial=None):
        super().__init__("🍌  Ravitaillements", "Position, type, épreuves qui y passent, horaires d'ouverture et "
                         "barrières horaires. Les quantités sont calculées d'après le quota de chaque épreuve (ou "
                         "les inscrits s'ils sont plus nombreux), avec plus d'eau l'été : des repères à ajuster après la première édition.",
                         athlete_id_initial)
        cadre, lc = _cadre("Ravitaillements")
        self.table = _table(["Ravitaillement", "Km", "Type", "Épreuves", "Coureurs attendus", "Ouverture", "Barrière",
                             "Bénévoles"], 220)
        self.table.itemSelectionChanged.connect(self._detail)
        self.table.doubleClicked.connect(lambda _i: self._modifier())
        lc.addWidget(self.table)
        b = QHBoxLayout()
        for t, f, p in (("➕ Ravitaillement", self._ajouter, True), ("✏️ Modifier", self._modifier, False),
                        ("🗑️ Supprimer", self._supprimer, False), ("📄 Plan et liste de courses (PDF)", self._pdf, False),
                        ("📤 Liste de courses (CSV)", self._csv, False)):
            w = _bouton(t, p)
            w.clicked.connect(f)
            b.addWidget(w)
        b.addStretch()
        lc.addLayout(b)
        self.principal.addWidget(cadre)
        l2 = QHBoxLayout()
        cadre, lc = _cadre("Quantités du ravitaillement choisi")
        self.table_q = _table(["Produit", "Quantité", "Unité"], 280)
        lc.addWidget(self.table_q)
        l2.addWidget(cadre, 1)
        cadre, lc = _cadre("Liste de courses (tous les ravitaillements)")
        self.table_total = _table(["Produit", "Quantité", "Unité"], 280)
        lc.addWidget(self.table_total)
        self.note = QLabel("")
        self.note.setWordWrap(True)
        self.note.setObjectName("texteSecondaire")
        lc.addWidget(self.note)
        l2.addWidget(cadre, 1)
        self.principal.addLayout(l2)
        self.principal.addStretch()
        self._rav = []
        self._finir()

    def rafraichir(self):
        ev = self.evenement_id
        self._rav = dl.ravitaillements(ev) if ev else []
        _remplir(self.table, [(r["nom"], _km(r["km"]), r["libelle_type"], ", ".join(r["epreuves"]), r["coureurs"],
                               r["ouverture"] or "", r["barriere_horaire"] or "", r["benevoles"]) for r in self._rav])
        tot = L.liste_de_courses(self._rav)
        _remplir(self.table_total, [(p, f"{q:g}", u) for p, (q, u) in sorted(tot.items())])
        ctx = dl.contexte(ev) if ev else {}
        self.note.setText("" if not ev else ("Gobelets fournis." if ctx.get("gobelets_fournis") else
                                             "Gobelet personnel obligatoire (à écrire dans le règlement) : aucun gobelet "
                                             "jetable compté. Change-le dans l'onglet Démarches, « Ta course »."))
        self._detail()

    def _detail(self):
        r = _ligne_choisie(self.table, self._rav)
        _remplir(self.table_q, [(p, f"{q:g}", u) for p, q, u in (r["quantites"] if r else [])])

    def _spec(self):
        eps = [(e["id"], e["nom"]) for e in dor.epreuves(self.evenement_id)]
        return [("texte", "nom", "Nom", {"aide": "Col du Cayron"}), ("reel", "km", "Kilomètre", {"suffixe": " km"}),
                ("choix", "type", "Type", {"choix": L.TYPES_RAVITO, "defaut": "complet"}),
                ("multi", "epreuve_ids", "Épreuves qui y passent (aucune cochée = toutes)", {"choix": eps}),
                ("heure", "ouverture", "Ouverture", None), ("heure", "barriere_horaire", "Barrière horaire", None),
                ("texte", "lieu", "Lieu", None), ("texte", "acces", "Accès (véhicule, piste)", None), ("long", "notes", "Notes", None)]

    def _ajouter(self):
        if self.evenement_id:
            d = DialogueChamps(self, "Nouveau ravitaillement", self._spec(), {"type": "complet"},
                               lambda c: dl.enregistrer_ravitaillement(self.evenement_id, c))
            if d.exec():
                self.rafraichir()

    def _modifier(self):
        r = _ligne_choisie(self.table, self._rav)
        if r:
            v = {**r, "epreuve_ids": r["epreuve_ids"] if r.get("epreuves_json") and r["epreuves_json"] != "[]" else []}
            d = DialogueChamps(self, "Ravitaillement", self._spec(), v,
                               lambda c: dl.enregistrer_ravitaillement(self.evenement_id, c, r["id"]))
            if d.exec():
                self.rafraichir()

    def _supprimer(self):
        r = _ligne_choisie(self.table, self._rav)
        if r and QMessageBox.question(self, "Ravitaillement", f"Supprimer « {r['nom']} » ?") == QMessageBox.StandardButton.Yes:
            dl.supprimer_ravitaillement(r["id"])
            self.rafraichir()

    def _pdf(self):
        if self.evenement_id:
            _ouvrir_pdf(self, "Ravitaillements.pdf", P.html_ravitaillements(dor.evenement(self.evenement_id), self._rav,
                                                                            L.liste_de_courses(self._rav)), True)

    def _csv(self):
        chemin, _ = QFileDialog.getSaveFileName(self, "Liste de courses", "Liste de courses.csv", "CSV (*.csv)")
        if chemin:
            t = "Produit;Quantité;Unité\n" + "".join(f"{p};{str(q).replace('.', ',')};{u}\n"
                                                    for p, (q, u) in sorted(L.liste_de_courses(self._rav).items()))
            Path(chemin).write_text("﻿" + t, encoding="utf-8")


# ======================================================================
# 📦 Matériel
# ======================================================================

class MaterielOrga(_EcranOrga):

    def __init__(self, athlete_id_initial=None):
        super().__init__("📦  Matériel", "Inventaire du matériel de la course : quantité nécessaire et disponible, "
                         "qui le prête ou le loue, où il va, son état d'avancement jusqu'au retour.", athlete_id_initial)
        ligne = QHBoxLayout()
        self.cartes = {k: self._carte(t) for k, t in (("articles", "Articles"), ("manquants", "Il en manque"),
                                                     ("a_rendre", "Prêts à rendre"), ("cout", "Coût"))}
        for c in self.cartes.values():
            ligne.addWidget(c, 1)
        self.principal.addLayout(ligne)
        cadre, lc = _cadre("Inventaire")
        h = QHBoxLayout()
        self.filtre = QComboBox()
        self.filtre.addItem("Tout le matériel", None)
        self.filtre.addItem("Il en manque", "manque")
        for k in L.CATEGORIES_MATERIEL:
            self.filtre.addItem(k, k)
        self.filtre.currentIndexChanged.connect(lambda _i: self._remplir())
        h.addWidget(self.filtre)
        h.addStretch()
        lc.addLayout(h)
        self.table = _table(["Article", "Catégorie", "Besoin", "Dispo", "Manque", "Prêté / loué par", "Où", "Statut", "Coût"], 420)
        self.table.doubleClicked.connect(lambda _i: self._modifier())
        lc.addWidget(self.table)
        b = QHBoxLayout()
        for t, f, p in (("✨ Ajouter la liste type", self._type, True), ("➕ Article", self._ajouter, False),
                        ("✏️ Modifier", self._modifier, False), ("🗑️ Supprimer", self._supprimer, False)):
            w = _bouton(t, p)
            w.clicked.connect(f)
            b.addWidget(w)
        self.statut = QComboBox()
        for k, t in L.STATUTS_MATERIEL:
            self.statut.addItem(t, k)
        app = _bouton("Changer le statut")
        app.clicked.connect(self._statut)
        pdf = _bouton("📄 Check-list (PDF)")
        pdf.clicked.connect(self._pdf)
        for w in (self.statut, app, pdf):
            b.addWidget(w)
        b.addStretch()
        lc.addLayout(b)
        self.principal.addWidget(cadre)
        self.principal.addStretch()
        self._ms, self._vues = [], []
        self._finir()

    def rafraichir(self):
        ev = self.evenement_id
        self._ms = dl.materiel(ev) if ev else []
        b = dl.bilan_materiel(ev) if ev else None
        for k, c in self.cartes.items():
            c.valeur.setText("—" if not b else (_euros(b[k]) if k == "cout" else str(b[k])))
        if b:
            self.cartes["manquants"].detail.setText(f"{b['a_trouver']} à trouver ou demandé(s)")
        self._remplir()

    def _remplir(self):
        f = self.filtre.currentData()
        self._vues = [m for m in self._ms if not f or (f == "manque" and m["manque"]) or m["categorie"] == f]
        coul = {}
        for r, m in enumerate(self._vues):
            if m["manque"]:
                coul[(r, 4)] = ROUGE
            coul[(r, 7)] = VERT if m["statut"] in ("en_place", "rendu", "charge") else (ORANGE if m["statut"] == "a_trouver" else None)
        rav = {r["id"]: r["nom"] for r in (dl.ravitaillements(self.evenement_id, False) if self.evenement_id else [])}
        _remplir(self.table, [(m["article"], m["categorie"] or "", f"{m['quantite']} {m['unite'] or ''}".strip(), m["disponible"],
                               m["manque"] or "", m["fournisseur"] or "", m["lieu"] or rav.get(m["ravitaillement_id"], ""),
                               L.LIBELLE_STATUT_MATERIEL.get(m["statut"], ""), _euros(m["cout"]) if m["cout"] else "")
                              for m in self._vues], coul)

    def _spec(self):
        rav = [(None, "—")] + [(r["id"], r["nom"]) for r in dl.ravitaillements(self.evenement_id, False)]
        return [("texte", "article", "Article", None),
                ("choix", "categorie", "Catégorie", {"choix": [(c, c) for c in L.CATEGORIES_MATERIEL]}),
                ("entier", "quantite", "Quantité nécessaire", {"defaut": 1}), ("entier", "disponible", "Disponible", None),
                ("texte", "unite", "Unité", None), ("texte", "fournisseur", "Prêté / loué par", None),
                ("euros", "cout", "Coût", None), ("texte", "lieu", "Où il va", None),
                ("choix", "ravitaillement_id", "Ravitaillement", {"choix": rav}),
                ("choix", "statut", "Statut", {"choix": L.STATUTS_MATERIEL}), ("long", "notes", "Notes", None)]

    def _ajouter(self):
        if self.evenement_id:
            d = DialogueChamps(self, "Nouvel article", self._spec(), {"categorie": "Divers", "quantite": 1},
                               lambda c: dl.enregistrer_materiel(self.evenement_id, c))
            if d.exec():
                self.rafraichir()

    def _modifier(self):
        m = _ligne_choisie(self.table, self._vues)
        if m:
            d = DialogueChamps(self, "Matériel", self._spec(), m, lambda c: dl.enregistrer_materiel(self.evenement_id, c, m["id"]))
            if d.exec():
                self.rafraichir()

    def _supprimer(self):
        ms = _lignes_choisies(self.table, self._vues)
        if ms and QMessageBox.question(self, "Matériel", f"Supprimer {len(ms)} article(s) ?") == QMessageBox.StandardButton.Yes:
            for m in ms:
                dl.supprimer_materiel(m["id"])
            self.rafraichir()

    def _type(self):
        if self.evenement_id:
            n = dl.ajouter_materiel_suggere(self.evenement_id)
            QMessageBox.information(self, "Matériel", f"{n} article(s) ajouté(s), quantités calculées d'après les "
                                    "épreuves, les ravitaillements, les carrefours et les bénévoles.")
            self.rafraichir()

    def _statut(self):
        ms = _lignes_choisies(self.table, self._vues)
        if ms:
            dl.changer_statut_materiel([m["id"] for m in ms], self.statut.currentData())
            self.rafraichir()

    def _pdf(self):
        if self.evenement_id:
            _ouvrir_pdf(self, "Check-list du materiel.pdf", P.html_materiel(dor.evenement(self.evenement_id), self._ms))


# ======================================================================
# 🤝 Partenaires et budget
# ======================================================================

class PartenairesOrga(_EcranOrga):

    def __init__(self, athlete_id_initial=None):
        super().__init__("🤝  Partenaires et budget", "Mécénat (don, reçu fiscal), parrainage (contre facture), "
                         "subventions et partenaires en nature ; budget prévisionnel et réalisé. Les inscriptions "
                         "encaissées et les accords des partenaires entrent tout seuls dans le budget.", athlete_id_initial)
        ligne = QHBoxLayout()
        self.cartes = {k: self._carte(t) for k, t in (("partenaires", "Partenaires"), ("relancer", "À relancer"),
                                                     ("solde", "Solde prévu"), ("seuil", "Seuil de rentabilité"))}
        for c in self.cartes.values():
            ligne.addWidget(c, 1)
        self.principal.addLayout(ligne)
        cadre, lc = _cadre("Partenaires")
        self.table = _table(["Partenaire", "Type", "Montant", "En nature", "Contreparties", "Statut", "Relance", "Reçu"], 260)
        self.table.itemSelectionChanged.connect(self._detail)
        self.table.doubleClicked.connect(lambda _i: self._modifier())
        lc.addWidget(self.table)
        self.detail = QLabel("")
        self.detail.setWordWrap(True)
        self.detail.setObjectName("texteSecondaire")
        lc.addWidget(self.detail)
        b = QHBoxLayout()
        for t, f, p in (("➕ Partenaire", self._ajouter, True), ("✏️ Modifier", self._modifier, False),
                        ("🗑️ Supprimer", self._supprimer, False), ("🧾 Reçu de don (PDF)", self._recu, False),
                        ("✉️ Courrier de partenariat", lambda: self._courrier("sponsor"), False),
                        ("✉️ Remerciements", lambda: self._courrier("remerciement"), False)):
            w = _bouton(t, p)
            w.clicked.connect(f)
            b.addWidget(w)
        b.addStretch()
        lc.addLayout(b)
        self.principal.addWidget(cadre)
        cadre, lc = _cadre("Budget")
        self.table_budget = _table(["Sens", "Catégorie", "Libellé", "Prévu", "Réalisé"], 320)
        self.table_budget.doubleClicked.connect(lambda _i: self._modifier_ligne())
        lc.addWidget(self.table_budget)
        b = QHBoxLayout()
        for t, f, p in (("➕ Recette", lambda: self._ajouter_ligne("recette"), False),
                        ("➕ Dépense", lambda: self._ajouter_ligne("depense"), False),
                        ("✏️ Modifier", self._modifier_ligne, False), ("🗑️ Supprimer", self._supprimer_ligne, False),
                        ("📄 Budget (PDF)", self._pdf_budget, False)):
            w = _bouton(t, p)
            w.clicked.connect(f)
            b.addWidget(w)
        b.addStretch()
        lc.addLayout(b)
        self.bilan = QLabel("")
        self.bilan.setWordWrap(True)
        self.bilan.setTextFormat(Qt.TextFormat.RichText)
        lc.addWidget(self.bilan)
        self.principal.addWidget(cadre)
        self.principal.addStretch()
        self._ps, self._lignes, self._b = [], [], None
        self._finir()

    def rafraichir(self):
        ev = self.evenement_id
        self._ps = dl.partenaires(ev) if ev else []
        coul = {}
        for r, p in enumerate(self._ps):
            coul[(r, 5)] = {"verse": VERT, "accord": VERT, "refus": GRIS, "relance": ORANGE}.get(p["statut"])
            if p["a_relancer"]:
                coul[(r, 6)] = ROUGE
        _remplir(self.table, [(p["nom"], L.LIBELLE_PARTENAIRE.get(p["type"], ""), _euros(p["montant"]) if p["montant"] else "",
                               _euros(p["valeur_nature"]) if p["valeur_nature"] else "", (p["contreparties"] or "")[:40],
                               L.LIBELLE_STATUT_PARTENAIRE.get(p["statut"], ""), P._jour(p["date_relance"]),
                               p["recu_numero"] or ("à faire" if p["recu_possible"] else "")) for p in self._ps], coul)
        self._b = dl.bilan(ev) if ev else None
        b = self._b
        self._lignes = []
        if b:
            self._lignes = b["recettes"] + b["depenses"]
        coul = {}
        for r, l in enumerate(self._lignes):
            if l.get("auto"):
                coul[r] = GRIS
        _remplir(self.table_budget, [("Recette" if l["sens"] == "recette" else "Dépense", l.get("categorie") or "",
                                      l["libelle"] + (" (par coureur)" if l.get("par_coureur") else ""),
                                      _euros(l.get("prevu_total", l.get("prevu"))) + (f" ({_euros(l['prevu'])} × coureurs)"
                                                                                      if l.get("par_coureur") else ""),
                                      _euros(l["realise"]) if l.get("realise") is not None else "") for l in self._lignes], coul)
        c = self.cartes
        if not b:
            for x in c.values():
                x.valeur.setText("—")
            self.bilan.setText("")
            return
        acc = [p for p in self._ps if p["statut"] in ("accord", "verse")]
        c["partenaires"].valeur.setText(f"{len(acc)} / {len(self._ps)}")
        c["partenaires"].detail.setText(_euros(sum(float(p["montant"] or 0) + float(p["valeur_nature"] or 0) for p in acc)) + " accordés")
        c["relancer"].valeur.setText(str(sum(1 for p in self._ps if p["a_relancer"])))
        c["solde"].valeur.setText(_euros(b["solde_prevu"]))
        c["solde"].valeur.setStyleSheet(f"font-size: 24px; font-weight: 700; color: {VERT if b['solde_prevu'] >= 0 else ROUGE};")
        c["solde"].detail.setText(f"réalisé {_euros(b['solde_realise'])}")
        c["seuil"].valeur.setText("—" if b["seuil"] is None else str(b["seuil"]))
        c["seuil"].detail.setText(f"coureurs au tarif moyen de {_euros(b['tarif_moyen'])} · {b['attendus']} attendus, "
                                  f"{b['inscrits']} inscrits")
        self.bilan.setText(f"Recettes prévues <b>{_euros(b['recettes_prevues'])}</b>, dépenses prévues "
                           f"<b>{_euros(b['depenses_prevues'])}</b> (fixes {_euros(b['fixe'])}, "
                           f"{_euros(b['variable_par_coureur'])} par coureur, pour {b['attendus']} coureurs attendus). Les lignes grises viennent des inscriptions "
                           "et des partenaires : elles se mettent à jour toutes seules.")
        self._detail()

    def _detail(self):
        p = _ligne_choisie(self.table, self._ps)
        if not p:
            self.detail.setText("Mécénat : un don sans contrepartie importante (reçu fiscal). Parrainage : une "
                                "prestation de visibilité, facturée.")
            return
        t = []
        if p["type"] in ("mecenat", "nature") and (p["montant"] or p["valeur_nature"]):
            av = L.avantage_fiscal(p["montant"] or p["valeur_nature"], bool(p["particulier"]))
            t.append(f"Réduction d'impôt pour le donateur : {av['taux']} %, soit {_euros(av['reduction'])} "
                     f"(coût réel {_euros(av['cout_reel'])}) ; plafond {av['plafond']}.")
            w = L.controle_contreparties(p["montant"] or p["valeur_nature"], _valeur(p["contreparties"]))
            if w:
                t.append("⚠️ " + w)
        elif p["type"] == "parrainage":
            t.append("Parrainage : facture à émettre (TVA si le club y est assujetti), pas de reçu fiscal.")
        if p["a_relancer"]:
            t.append("⏰ Relance prévue aujourd'hui ou dépassée.")
        self.detail.setText(" ".join(t))

    def _spec(self):
        return [("texte", "nom", "Partenaire", None), ("choix", "type", "Type", {"choix": L.TYPES_PARTENAIRE}),
                ("case", "particulier", "Donateur particulier", {"texte": "oui (sinon entreprise)"}),
                ("texte", "contact", "Contact", None), ("texte", "email", "E-mail", None), ("texte", "telephone", "Téléphone", None),
                ("long", "adresse", "Adresse (pour le reçu)", {"hauteur": 50}), ("texte", "siren", "SIREN", None),
                ("euros", "montant", "Montant", None), ("euros", "valeur_nature", "Valeur en nature", None),
                ("texte", "description_nature", "Don en nature (description)", None),
                ("long", "contreparties", "Contreparties (logo, banderole, dossards…)", {"hauteur": 50}),
                ("choix", "statut", "Statut", {"choix": L.STATUTS_PARTENAIRE}), ("date", "date_contact", "Contacté le", None),
                ("date", "date_relance", "Relancer le", None), ("date", "date_versement", "Versé le", None),
                ("texte", "mode_versement", "Mode de versement", {"aide": "virement, chèque…"}), ("long", "notes", "Notes", None)]

    def _ajouter(self):
        if self.evenement_id:
            d = DialogueChamps(self, "Nouveau partenaire", self._spec(), {"type": "parrainage", "statut": "a_contacter"},
                               lambda c: dl.enregistrer_partenaire(self.evenement_id, c), 560)
            if d.exec():
                self.rafraichir()

    def _modifier(self):
        p = _ligne_choisie(self.table, self._ps)
        if p:
            d = DialogueChamps(self, "Partenaire", self._spec(), p,
                               lambda c: dl.enregistrer_partenaire(self.evenement_id, c, p["id"]), 560)
            if d.exec():
                self.rafraichir()

    def _supprimer(self):
        p = _ligne_choisie(self.table, self._ps)
        if p and QMessageBox.question(self, "Partenaire", f"Supprimer « {p['nom']} » ?") == QMessageBox.StandardButton.Yes:
            dl.supprimer_partenaire(p["id"])
            self.rafraichir()

    def _recu(self):
        p = _ligne_choisie(self.table, self._ps)
        if not p:
            return
        try:
            p = dl.emettre_recu(p["id"])
        except dl.ErreurLogistique as e:
            QMessageBox.warning(self, "Reçu", str(e))
            return
        _ouvrir_pdf(self, f"Recu {p['recu_numero']}.pdf",
                    P.html_recu_don(dclub.club_principal(), p, dor.evenement(self.evenement_id)))
        self.rafraichir()

    def _courrier(self, code):
        if not self.evenement_id:
            return
        p = _ligne_choisie(self.table, self._ps)
        objet, texte = L.courrier(code, dor.evenement(self.evenement_id), dor.epreuves(self.evenement_id),
                                  dclub.club_principal(), {"nom": p["nom"] if p else None}, dl.contexte(self.evenement_id))
        DialogueTexte(self, L.LIBELLE_COURRIER[code], texte, f"Courrier {p['nom'] if p else 'partenaire'}.pdf").exec()

    def _spec_ligne(self, sens):
        cats = L.CATEGORIES_RECETTE if sens == "recette" else L.CATEGORIES_DEPENSE
        s = [("choix", "categorie", "Catégorie", {"choix": [(c, c) for c in cats]}), ("texte", "libelle", "Libellé", None),
             ("euros", "prevu", "Prévu", None), ("euros", "realise", "Réalisé", None)]
        if sens == "depense":
            s.append(("case", "par_coureur", "Montant par coureur", {"texte": "multiplié par le nombre d'inscrits"}))
        return s + [("long", "notes", "Notes", None)]

    def _ajouter_ligne(self, sens):
        if self.evenement_id:
            d = DialogueChamps(self, "Recette" if sens == "recette" else "Dépense", self._spec_ligne(sens), {},
                               lambda c: dl.enregistrer_ligne_budget(self.evenement_id, {**c, "sens": sens,
                                                                                          "realise": c["realise"] or None}))
            if d.exec():
                self.rafraichir()

    def _modifier_ligne(self):
        l = _ligne_choisie(self.table_budget, self._lignes)
        if not l:
            return
        if l.get("auto"):
            QMessageBox.information(self, "Budget", "Cette ligne vient des inscriptions ou d'un partenaire : modifie-la à "
                                    "sa source.")
            return
        d = DialogueChamps(self, "Ligne du budget", self._spec_ligne(l["sens"]), l,
                           lambda c: dl.enregistrer_ligne_budget(self.evenement_id, {**c, "realise": c["realise"] or None}, l["id"]))
        if d.exec():
            self.rafraichir()

    def _supprimer_ligne(self):
        l = _ligne_choisie(self.table_budget, self._lignes)
        if l and not l.get("auto") and QMessageBox.question(self, "Budget", f"Supprimer « {l['libelle']} » ?") == \
                QMessageBox.StandardButton.Yes:
            dl.supprimer_ligne_budget(l["id"])
            self.rafraichir()

    def _pdf_budget(self):
        if self._b:
            _ouvrir_pdf(self, "Budget de la course.pdf", P.html_budget(dor.evenement(self.evenement_id), self._b))


def _valeur(texte):
    """Montant écrit dans les contreparties (« banderole 150 € ») : la somme des nombres suivis de €."""
    import re
    return sum(float(x.replace(",", ".")) for x in re.findall(r"(\d+(?:[.,]\d+)?)\s*€", texte or ""))
