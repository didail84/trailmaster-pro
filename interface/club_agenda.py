"""
Agenda du club et appel des présences (Trail Hub Center, étape 4.2).

Deux onglets de la fenêtre « 🏟️ Club » :
  - 📅 Agenda : séances ponctuelles et séries chaque semaine (un groupe, un
    jour, un horaire), sans les jours fériés et, au choix, sans les vacances
    scolaires de la zone du club ; annuler, dupliquer, feuille d'appel PDF,
    export de l'agenda vers les téléphones (.ics) ;
  - ✅ Présences : l'appel d'une séance (présent, en retard, excusé,
    absent), l'assiduité de chacun et de chaque groupe, les décrochages.
Aucune requête SQL ici : tout passe par noyau/donnees/agenda_club.py.
"""

from datetime import date, timedelta
from pathlib import Path

from PySide6.QtCore import Qt, QDate, QUrl
from PySide6.QtGui import QColor, QDesktopServices
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QDateEdit, QDialog, QDialogButtonBox, QFileDialog, QFormLayout,
    QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPlainTextEdit, QTableWidgetItem, QVBoxLayout,
)

from noyau.donnees import agenda_club as dag, club as dclub, personnes as dper
from noyau.club import agenda as ag, categories as cat
from interface.club import _EcranClub, _bouton, _cadre, _table, _style_cases, VERT, ORANGE, ROUGE, GRIS
from interface.ecran_liste import obtenir_style_ecran

JOURS_COURTS = ("lun.", "mar.", "mer.", "jeu.", "ven.", "sam.", "dim.")
MOIS = ("janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre", "novembre",
        "décembre")


def _d(iso):
    return date.fromisoformat(str(iso)[:10])


def _date_courte(iso):
    j = _d(iso)
    return f"{JOURS_COURTS[j.weekday()]} {j.strftime('%d/%m')}"


def _date_longue(iso):
    j = _d(iso)
    return f"{ag.JOURS[j.weekday()]} {j.day} {MOIS[j.month - 1]} {j.year}"


def _horaire(s):
    if not s.get("heure_debut"):
        return "—"
    return s["heure_debut"].replace(":", "h") + (f" – {s['heure_fin'].replace(':', 'h')}" if s.get("heure_fin") else "")


def _champ_date(valeur=None):
    w = QDateEdit(QDate.fromString(str(valeur)[:10], "yyyy-MM-dd") if valeur else QDate.currentDate())
    w.setCalendarPopup(True)
    w.setDisplayFormat("dd/MM/yyyy")
    return w


def _combo_type(valeur=None):
    c = QComboBox()
    for code, lib in ag.TYPES:
        c.addItem(lib, code)
    c.setCurrentIndex(max(0, c.findData(valeur or "entrainement")))
    return c


def _combo_groupe(club_id, valeur=None, tous="Tout le club"):
    c = QComboBox()
    c.addItem(tous, None)
    for g in dclub.groupes(club_id):
        c.addItem(g["nom"], g["id"])
    c.setCurrentIndex(max(0, c.findData(valeur)))
    return c


def _combo_entraineur(valeur=None):
    c = QComboBox()
    c.addItem("—", None)
    gens = dper.lister()
    for p in sorted(gens, key=lambda p: ("entraineur" not in p["roles"], p["nom"].lower(), p["prenom"].lower())):
        c.addItem(f"{p['prenom']} {p['nom']}" + ("  · entraîneur" if "entraineur" in p["roles"] else ""), p["id"])
    c.setCurrentIndex(max(0, c.findData(valeur)))
    return c


def _boutons_dialogue(d, lay, texte_ok="Enregistrer"):
    bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
    bb.button(QDialogButtonBox.StandardButton.Save).setText(texte_ok)
    bb.button(QDialogButtonBox.StandardButton.Cancel).setText("Annuler")
    bb.accepted.connect(d.accept)
    bb.rejected.connect(d.reject)
    lay.addWidget(bb)
    return bb


# ======================================================================
# Dialogues : une séance, une série
# ======================================================================

class DialogueSeance(QDialog):

    def __init__(self, parent, club_id, seance=None, jour=None):
        super().__init__(parent)
        self.club_id, self.s = club_id, seance
        s = seance or {}
        self.setWindowTitle("Séance" if seance else "Nouvelle séance")
        self.setStyleSheet(obtenir_style_ecran())
        self.resize(560, 520)
        lay = QVBoxLayout(self)
        f = QFormLayout()
        self.titre = QLineEdit(s.get("titre") or "")
        self.titre.setPlaceholderText("ex. Fractionné piste, Sortie longue au Ventoux, Cross départemental")
        self.type = _combo_type(s.get("type"))
        self.groupe = _combo_groupe(club_id, s.get("groupe_id"))
        self.date = _champ_date(s.get("date") or jour)
        self.debut, self.fin = QLineEdit(s.get("heure_debut") or ""), QLineEdit(s.get("heure_fin") or "")
        self.debut.setPlaceholderText("18:30")
        self.fin.setPlaceholderText("20:00")
        h = QHBoxLayout()
        h.addWidget(self.debut)
        h.addWidget(QLabel("à"))
        h.addWidget(self.fin)
        self.lieu = QLineEdit(s.get("lieu") or "")
        self.entraineur = _combo_entraineur(s.get("entraineur_id"))
        self.contenu = QPlainTextEdit(s.get("contenu") or "")
        self.contenu.setPlaceholderText("Le contenu de la séance (échauffement, corps de séance, retour au calme)…")
        self.contenu.setMaximumHeight(110)
        self.notes = QLineEdit(s.get("notes") or "")
        for lib, w in (("Titre", self.titre), ("Type", self.type), ("Groupe", self.groupe), ("Date", self.date),
                       ("Horaire", h), ("Lieu", self.lieu), ("Entraîneur", self.entraineur), ("Contenu", self.contenu),
                       ("Notes", self.notes)):
            f.addRow(lib, w)
        lay.addLayout(f)
        self.avis = QLabel("")
        self.avis.setWordWrap(True)
        lay.addWidget(self.avis)
        self.date.dateChanged.connect(lambda _d: self._avis())
        self._avis()
        _boutons_dialogue(self, lay)

    def _avis(self):
        j = self.date.date().toPython()
        f, v = ag.ferie(j), ag.en_vacances(j, dag.zone_du_club(self.club_id))
        self.avis.setText("⚠️ " + " · ".join(x for x in (f and f"jour férié : {f}", v) if x) if f or v else "")

    def champs(self):
        return {"titre": self.titre.text(), "type": self.type.currentData(), "groupe_id": self.groupe.currentData(),
                "date": self.date.date().toString("yyyy-MM-dd"), "heure_debut": self.debut.text(),
                "heure_fin": self.fin.text(), "lieu": self.lieu.text().strip() or None,
                "entraineur_id": self.entraineur.currentData(), "contenu": self.contenu.toPlainText().strip() or None,
                "notes": self.notes.text().strip() or None}

    def accept(self):
        try:
            dag.enregistrer_seance(self.club_id, self.champs(), self.s["id"] if self.s else None)
        except dag.ErreurAgenda as e:
            QMessageBox.warning(self, "Séance", str(e))
            return
        super().accept()


class DialogueSerie(QDialog):

    def __init__(self, parent, club_id, saison, serie=None):
        super().__init__(parent)
        self.club_id, self.serie = club_id, serie
        s = serie or {}
        self.setWindowTitle("Série chaque semaine" if not serie else f"Série — {s['titre']}")
        self.setStyleSheet(obtenir_style_ecran())
        _style_cases(self)
        self.resize(620, 560)
        lay = QVBoxLayout(self)
        f = QFormLayout()
        self.titre = QLineEdit(s.get("titre") or "")
        self.titre.setPlaceholderText("ex. Entraînement piste, Sortie trail du samedi")
        self.type = _combo_type(s.get("type"))
        self.groupe = _combo_groupe(club_id, s.get("groupe_id"))
        self.jour = QComboBox()
        for i, j in enumerate(ag.JOURS):
            self.jour.addItem(j.capitalize(), i)
        self.jour.setCurrentIndex(s.get("jour_semaine", 1) if serie else 1)
        self.debut, self.fin = QLineEdit(s.get("heure_debut") or ""), QLineEdit(s.get("heure_fin") or "")
        self.debut.setPlaceholderText("18:30")
        self.fin.setPlaceholderText("20:00")
        h = QHBoxLayout()
        h.addWidget(self.debut)
        h.addWidget(QLabel("à"))
        h.addWidget(self.fin)
        d0, d1 = cat.bornes_saison(saison)
        debut_defaut = max(d0, date.today()) if not serie else None
        self.date_debut = _champ_date(s.get("date_debut") or debut_defaut.isoformat())
        self.date_fin = _champ_date(s.get("date_fin") or date(d1.year, 6, 30).isoformat())
        self.lieu = QLineEdit(s.get("lieu") or "")
        self.entraineur = _combo_entraineur(s.get("entraineur_id"))
        zone = dag.zone_du_club(club_id)
        self.sauf_vacances = QCheckBox(f"Pas pendant les vacances scolaires (zone {zone})")
        self.sauf_vacances.setChecked(bool(s.get("sauf_vacances", 0)))
        self.sauf_feries = QCheckBox("Pas les jours fériés")
        self.sauf_feries.setChecked(bool(s.get("sauf_feries", 1)))
        for lib, w in (("Titre", self.titre), ("Type", self.type), ("Groupe", self.groupe), ("Chaque", self.jour),
                       ("Horaire", h), ("Du", self.date_debut), ("Au", self.date_fin), ("Lieu", self.lieu),
                       ("Entraîneur", self.entraineur), ("", self.sauf_vacances), ("", self.sauf_feries)):
            f.addRow(lib, w)
        lay.addLayout(f)
        self.apercu = QLabel("")
        self.apercu.setWordWrap(True)
        self.apercu.setTextFormat(Qt.TextFormat.RichText)
        lay.addWidget(self.apercu)
        for w in (self.jour,):
            w.currentIndexChanged.connect(lambda _i: self._apercu())
        for w in (self.date_debut, self.date_fin):
            w.dateChanged.connect(lambda _d: self._apercu())
        for w in (self.sauf_vacances, self.sauf_feries):
            w.toggled.connect(lambda _b: self._apercu())
        self._apercu()
        _boutons_dialogue(self, lay, "Créer les séances" if not serie else "Enregistrer")

    def champs(self):
        return {"titre": self.titre.text(), "type": self.type.currentData(), "groupe_id": self.groupe.currentData(),
                "jour_semaine": self.jour.currentData(), "heure_debut": self.debut.text(), "heure_fin": self.fin.text(),
                "date_debut": self.date_debut.date().toString("yyyy-MM-dd"),
                "date_fin": self.date_fin.date().toString("yyyy-MM-dd"), "lieu": self.lieu.text().strip() or None,
                "entraineur_id": self.entraineur.currentData(), "sauf_vacances": self.sauf_vacances.isChecked(),
                "sauf_feries": self.sauf_feries.isChecked()}

    def _apercu(self):
        try:
            dates, ecartees = dag.apercu_serie(self.club_id, {**self.champs(), "titre": "x"})
        except dag.ErreurAgenda as e:
            self.apercu.setText(f"<span style='color:{ORANGE}'>{e}</span>")
            return
        txt = f"<b>{len(dates)} séance{'s' if len(dates) > 1 else ''}</b>"
        if dates:
            txt += f", du {_date_longue(dates[0])} au {_date_longue(dates[-1])}"
        if ecartees:
            par = {}
            for _j, r in ecartees:
                par[r] = par.get(r, 0) + 1
            txt += ". Sans : " + ", ".join(f"{r} ({n})" for r, n in par.items())
        if not ag.calendrier_connu(cat.saison_de(self.date_debut.date().toPython())) and self.sauf_vacances.isChecked():
            txt += (f"<br><span style='color:{ORANGE}'>Les vacances de cette saison ne sont pas encore dans Trail Hub : "
                    "seuls les jours fériés sont retirés.</span>")
        if self.serie:
            txt += ("<br><span style='color:#9E9E9E'>Les séances à venir sans appel sont recréées avec ces réglages ; "
                    "les séances passées ou déjà appelées restent.</span>")
        self.apercu.setText(txt + ".")

    def accept(self):
        try:
            r = dag.enregistrer_serie(self.club_id, self.champs(), self.serie["id"] if self.serie else None)
        except dag.ErreurAgenda as e:
            QMessageBox.warning(self, "Série", str(e))
            return
        self.resultat = r
        super().accept()


# ======================================================================
# Onglet Agenda
# ======================================================================

PERIODES = (("semaine", "Cette semaine"), ("4semaines", "Les 4 prochaines semaines"), ("mois", "Ce mois-ci"),
            ("mois_suivant", "Le mois prochain"), ("saison", "Toute la saison"), ("passees", "Passées, appel à faire"))


def bornes_periode(code, saison, aujourdhui=None):
    auj = aujourdhui or date.today()
    if code == "semaine":
        d = auj - timedelta(days=auj.weekday())
        return d, d + timedelta(days=6)
    if code == "4semaines":
        return auj, auj + timedelta(days=27)
    if code == "mois":
        d = auj.replace(day=1)
        return d, (d + timedelta(days=32)).replace(day=1) - timedelta(days=1)
    if code == "mois_suivant":
        d = (auj.replace(day=1) + timedelta(days=32)).replace(day=1)
        return d, (d + timedelta(days=32)).replace(day=1) - timedelta(days=1)
    if code == "passees":
        return auj - timedelta(days=60), auj - timedelta(days=1)
    return cat.bornes_saison(saison)


class AgendaClub(_EcranClub):
    COLONNES = ["Date", "Horaire", "Séance", "Type", "Groupe", "Lieu", "Entraîneur", "Présents", "État"]

    def __init__(self, athlete_id_initial=None):
        super().__init__("📅  Agenda du club", "Les séances de chaque groupe, une par une ou en série chaque semaine. "
                         "Les jours fériés et, au choix, les vacances scolaires sont retirés tout seuls.",
                         athlete_id_initial)
        f = QHBoxLayout()
        self.periode = QComboBox()
        for code, lib in PERIODES:
            self.periode.addItem(lib, code)
        self.periode.setCurrentIndex(1)
        self.f_groupe = QComboBox()
        self.avec_annulees = QCheckBox("Montrer les séances annulées")
        self.avec_annulees.setChecked(True)
        f.addWidget(QLabel("Période :"))
        f.addWidget(self.periode)
        f.addWidget(self.f_groupe)
        f.addWidget(self.avec_annulees)
        f.addStretch()
        self.principal.addLayout(f)
        b = QHBoxLayout()
        for texte, fn, p in (("➕ Séance", self._nouvelle, True), ("🔁 Série chaque semaine", self._serie, True),
                             ("✏️ Modifier", self._modifier, False), ("📋 Dupliquer", self._dupliquer, False),
                             ("⛔ Annuler / rétablir", self._annuler, False), ("🗑 Supprimer", self._supprimer, False),
                             ("✅ Faire l'appel", self._appel, False), ("📄 Feuille d'appel PDF", self._feuille, False),
                             ("📆 Exporter vers les téléphones", self._ics, False)):
            w = _bouton(texte, p)
            w.clicked.connect(fn)
            b.addWidget(w)
        b.addStretch()
        self.principal.addLayout(b)
        self.compte = QLabel("")
        self.compte.setObjectName("texteSecondaire")
        self.principal.addWidget(self.compte)
        self.table = _table(self.COLONNES, 420)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.cellDoubleClicked.connect(lambda _r, _c: self._modifier())
        self.principal.addWidget(self.table)
        cadre, lc = _cadre("Séries chaque semaine")
        self.table_series = _table(["Séance", "Groupe", "Jour", "Horaire", "Période", "Vacances", "Séances", "Entraîneur"],
                                   150)
        self.table_series.cellDoubleClicked.connect(lambda _r, _c: self._modifier_serie())
        lc.addWidget(self.table_series)
        b2 = QHBoxLayout()
        for texte, fn in (("✏️ Modifier la série", self._modifier_serie), ("🗑 Supprimer la série", self._supprimer_serie)):
            w = _bouton(texte)
            w.clicked.connect(fn)
            b2.addWidget(w)
        b2.addStretch()
        lc.addLayout(b2)
        self.principal.addWidget(cadre)
        cadre, lc = _cadre("Vacances scolaires")
        self.label_vacances = QLabel("")
        self.label_vacances.setWordWrap(True)
        self.label_vacances.setTextFormat(Qt.TextFormat.RichText)
        lc.addWidget(self.label_vacances)
        self.principal.addWidget(cadre)
        self.principal.addStretch()
        self._seances, self._series = [], []
        self.periode.currentIndexChanged.connect(lambda _i: self._remplir())
        self.f_groupe.currentIndexChanged.connect(lambda _i: self._remplir())
        self.avec_annulees.toggled.connect(lambda _b: self._remplir())
        self._finaliser()

    def actualiser(self):
        actuel = self.f_groupe.currentData()
        self.f_groupe.blockSignals(True)
        self.f_groupe.clear()
        self.f_groupe.addItem("Tous les groupes", None)
        for g in dclub.groupes(self.club_id):
            self.f_groupe.addItem(g["nom"], g["id"])
        self.f_groupe.setCurrentIndex(max(0, self.f_groupe.findData(actuel)))
        self.f_groupe.blockSignals(False)
        self._remplir()

    def _remplir(self):
        d0, d1 = bornes_periode(self.periode.currentData(), self.saison)
        g = self.f_groupe.currentData()
        if self.periode.currentData() == "passees":
            ss = [s for s in dag.sans_appel(self.club_id) if g is None or s["groupe_id"] == g]
        else:
            ss = dag.seances(self.club_id, d0, d1, g, self.avec_annulees.isChecked())
        self._seances = ss
        auj = date.today().isoformat()
        t = self.table
        t.setRowCount(len(ss))
        for i, s in enumerate(ss):
            if s["annulee"]:
                etat, coul = "annulée" + (f" ({s['motif_annulation']})" if s["motif_annulation"] else ""), GRIS
            elif s["appel_fait"]:
                etat, coul = f"appel fait · {s['taux']} %" if s["taux"] is not None else "appel fait", VERT
            elif s["date"] < auj:
                etat, coul = "appel à faire", ORANGE
            elif s["date"] == auj:
                etat, coul = "aujourd'hui", ORANGE
            else:
                etat, coul = "à venir", None
            vals = [_date_courte(s["date"]) + (f"  ({s['ferie']})" if s["ferie"] else ""), _horaire(s), s["titre"],
                    ag.LIBELLE_TYPE.get(s["type"], ""), s["groupe"] or "Tout le club", s["lieu"] or "",
                    s["entraineur"] or "", str(s["presents"]) if s["appel_fait"] else "", etat]
            for j, v in enumerate(vals):
                it = QTableWidgetItem(v)
                if j == 8 and coul:
                    it.setForeground(QColor(coul))
                if s["annulee"] and j == 2:
                    f = it.font()
                    f.setStrikeOut(True)
                    it.setFont(f)
                if j == 2 and s["contenu"]:
                    it.setToolTip(s["contenu"])
                t.setItem(i, j, it)
        t.resizeColumnsToContents()
        if t.columnWidth(2) > 320:
            t.setColumnWidth(2, 320)
        actives = [s for s in ss if not s["annulee"]]
        self.compte.setText(f"{len(actives)} séance(s)" + (f", {len(ss) - len(actives)} annulée(s)" if len(ss) > len(actives)
                                                           else "") + f" · du {d0.strftime('%d/%m/%Y')} au "
                            f"{d1.strftime('%d/%m/%Y')}" if self.periode.currentData() != "passees" else
                            f"{len(ss)} séance(s) passée(s) sans appel (60 derniers jours).")
        # séries
        self._series = [x for x in dag.series(self.club_id) if g is None or x["groupe_id"] == g]
        t = self.table_series
        t.setRowCount(len(self._series))
        for i, x in enumerate(self._series):
            vals = [x["titre"], x["groupe"] or "Tout le club", ag.JOURS[x["jour_semaine"]], _horaire(x),
                    f"{_d(x['date_debut']).strftime('%d/%m/%Y')} → {_d(x['date_fin']).strftime('%d/%m/%Y')}",
                    "sans les vacances" if x["sauf_vacances"] else "aussi en vacances", str(x["nb_seances"]),
                    x["entraineur"] or ""]
            for j, v in enumerate(vals):
                t.setItem(i, j, QTableWidgetItem(v))
        t.resizeColumnsToContents()
        # vacances
        zone = dag.zone_du_club(self.club_id)
        vac = ag.vacances_de(self.saison, zone)
        if vac:
            lignes = []
            for nom, a, b, est in vac:
                passe = b < date.today()
                lib = ag.NOM_VACANCES[nom]
                txt = f"{lib[0].upper() + lib[1:]} : du {a.strftime('%d/%m/%Y')} au {b.strftime('%d/%m/%Y')}"
                if est:
                    txt += " (fin estimée)"
                lignes.append(f"<span style='color:#9E9E9E'>{txt}</span>" if passe else txt)
            ponts = [f"{n} le {_d(j).strftime('%d/%m/%Y')}" for n, j in ag.PONTS if cat.saison_de(j) == self.saison]
            self.label_vacances.setText(f"<b>Zone {zone}</b> (à changer dans l'onglet « Le club ») · saison {self.saison}<br>"
                                        + "<br>".join(lignes) + (("<br>" + ", ".join(ponts)) if ponts else ""))
        else:
            self.label_vacances.setText(f"Les vacances scolaires {self.saison} ne sont pas encore dans Trail Hub : les "
                                        "séries ne retirent que les jours fériés.")

    def _selection(self):
        lignes = sorted({i.row() for i in self.table.selectedIndexes()})
        return [self._seances[l] for l in lignes if l < len(self._seances)]

    def _apres(self):
        f = self._fenetre()
        for e in (f.ecrans if f else [self]):
            if e is not self and hasattr(e, "actualiser"):
                try:
                    e.actualiser()
                except RuntimeError:
                    pass
        self._remplir()

    def _nouvelle(self):
        if DialogueSeance(self, self.club_id).exec():
            self._apres()

    def _modifier(self):
        sel = self._selection()
        if sel and DialogueSeance(self, self.club_id, sel[0]).exec():
            self._apres()

    def _serie(self):
        d = DialogueSerie(self, self.club_id, self.saison)
        if d.exec():
            r = d.resultat
            QMessageBox.information(self, "Série", f"{r['creees']} séance(s) ajoutée(s) à l'agenda"
                                    + (f", {len(r['ecartees'])} date(s) sautée(s) (fériés ou vacances)." if r["ecartees"]
                                       else "."))
            self._apres()

    def _serie_courante(self):
        i = self.table_series.currentRow()
        return self._series[i] if 0 <= i < len(self._series) else None

    def _modifier_serie(self):
        x = self._serie_courante()
        if x:
            d = DialogueSerie(self, self.club_id, self.saison, x)
            if d.exec():
                r = d.resultat
                QMessageBox.information(self, "Série", f"{r['creees']} séance(s) à venir recréée(s) ; "
                                        f"{r['gardees']} séance(s) passée(s) ou appelée(s) gardée(s).")
                self._apres()

    def _supprimer_serie(self):
        x = self._serie_courante()
        if x and QMessageBox.question(self, "Supprimer la série", f"Supprimer la série « {x['titre']} » ? Les séances à "
                                      "venir sans appel sont retirées de l'agenda ; les séances passées et les présences "
                                      "sont gardées.") == QMessageBox.StandardButton.Yes:
            n = dag.supprimer_serie(x["id"])
            QMessageBox.information(self, "Série", f"Série supprimée : {n} séance(s) à venir retirée(s).")
            self._apres()

    def _dupliquer(self):
        sel = self._selection()
        if not sel:
            return
        d = QDialog(self)
        d.setWindowTitle("Dupliquer")
        d.setStyleSheet(obtenir_style_ecran())
        lay = QVBoxLayout(d)
        f = QFormLayout()
        jour = _champ_date((_d(sel[0]["date"]) + timedelta(days=7)).isoformat())
        f.addRow(f"Copier « {sel[0]['titre']} » au", jour)
        lay.addLayout(f)
        _boutons_dialogue(d, lay, "Dupliquer")
        if d.exec():
            dag.dupliquer_seance(sel[0]["id"], jour.date().toString("yyyy-MM-dd"))
            self._apres()

    def _annuler(self):
        sel = self._selection()
        if not sel:
            return
        if all(s["annulee"] for s in sel):
            for s in sel:
                dag.retablir_seance(s["id"])
        else:
            d = QDialog(self)
            d.setWindowTitle("Annuler")
            d.setStyleSheet(obtenir_style_ecran())
            lay = QVBoxLayout(d)
            lay.addWidget(QLabel(f"Annuler {len(sel)} séance(s) ? Elles restent visibles, barrées, dans l'agenda."))
            motif = QLineEdit()
            motif.setPlaceholderText("Motif (ex. piste fermée, alerte orage, entraîneur absent)")
            lay.addWidget(motif)
            _boutons_dialogue(d, lay, "Annuler les séances")
            if not d.exec():
                return
            for s in sel:
                if not s["annulee"]:
                    dag.annuler_seance(s["id"], motif.text())
        self._apres()

    def _supprimer(self):
        sel = self._selection()
        if not sel:
            return
        avec = [s for s in sel if s["pointes"]]
        msg = f"Supprimer {len(sel)} séance(s) de l'agenda ?"
        if avec:
            msg += f" {len(avec)} ont déjà un appel : leurs présences seront perdues. (Pour garder une trace, annule-les.)"
        if QMessageBox.question(self, "Supprimer", msg) == QMessageBox.StandardButton.Yes:
            for s in sel:
                dag.supprimer_seance(s["id"])
            self._apres()

    def _appel(self):
        sel = self._selection()
        f = self._fenetre()
        if sel and f:
            f.presences.choisir_seance(sel[0]["id"])
            f.tabs.setCurrentIndex(f.ecrans.index(f.presences))

    def _feuille(self):
        sel = self._selection()
        if not sel:
            return
        s = sel[0]
        chemin, _ = QFileDialog.getSaveFileName(self, "Feuille d'appel",
                                                f"Appel {s['date']} {s['titre']}.pdf".replace("/", "-"), "PDF (*.pdf)")
        if not chemin:
            return
        from interface.club_pdf import rendre_feuille_appel
        rendre_feuille_appel(chemin, dclub.club_principal(), s, dag.appel(s["id"]))
        QDesktopServices.openUrl(QUrl.fromLocalFile(chemin))

    def _ics(self):
        d0, d1 = bornes_periode(self.periode.currentData(), self.saison)
        if self.periode.currentData() in ("semaine", "passees"):
            d0, d1 = date.today(), cat.bornes_saison(self.saison)[1]
        g = self.f_groupe.currentData()
        nom = (self.f_groupe.currentText() if g else "club").replace("/", "-")
        chemin, _ = QFileDialog.getSaveFileName(self, "Exporter l'agenda", f"Agenda {nom}.ics", "Agenda (*.ics)")
        if chemin:
            Path(chemin).write_text(dag.export_ics(self.club_id, d0, d1, g), encoding="utf-8", newline="")
            QMessageBox.information(self, "Agenda", "Agenda exporté. Envoie ce fichier aux adhérents : en l'ouvrant sur "
                                    "leur téléphone (iPhone, Android) ou dans Google Agenda, les séances s'ajoutent à "
                                    "leur calendrier. Les séances annulées y apparaissent comme annulées.")


# ======================================================================
# Onglet Présences
# ======================================================================

class PresencesClub(_EcranClub):

    def __init__(self, athlete_id_initial=None):
        super().__init__("✅  Présences", "L'appel de chaque séance, puis l'assiduité de chacun et de chaque groupe. "
                         "Un adhérent absent plusieurs fois de suite sans excuse est signalé.", athlete_id_initial)
        cadre, lc = _cadre("Appel")
        l1 = QHBoxLayout()
        self.combo_seance = QComboBox()
        self.combo_seance.setMinimumWidth(460)
        l1.addWidget(QLabel("Séance :"))
        l1.addWidget(self.combo_seance, 1)
        lc.addLayout(l1)
        self.label_seance = QLabel("")
        self.label_seance.setWordWrap(True)
        self.label_seance.setObjectName("texteSecondaire")
        lc.addWidget(self.label_seance)
        b = QHBoxLayout()
        for texte, fn, p in (("👍 Tout le monde présent", self._tous_presents, False),
                             ("➖ Les non pointés : absents", self._reste_absents, False),
                             ("➕ Ajouter une personne", self._ajouter, False),
                             ("💾 Enregistrer l'appel", self._enregistrer, True)):
            w = _bouton(texte, p)
            w.clicked.connect(fn)
            b.addWidget(w)
        b.addStretch()
        lc.addLayout(b)
        self.table = _table(["Nom", "Prénom", "Cat.", "Présence", "Remarque", "Urgence"], 360)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.table.verticalHeader().setDefaultSectionSize(42)
        lc.addWidget(self.table)
        self.label_bilan = QLabel("")
        self.label_bilan.setTextFormat(Qt.TextFormat.RichText)
        lc.addWidget(self.label_bilan)
        self.principal.addWidget(cadre)
        cadre, lc = _cadre("Assiduité")
        l2 = QHBoxLayout()
        self.periode = QComboBox()
        for code, lib in (("30", "30 derniers jours"), ("90", "3 derniers mois"), ("saison", "Toute la saison")):
            self.periode.addItem(lib, code)
        self.f_groupe = QComboBox()
        exp = _bouton("📤 Export tableur des présences")
        exp.clicked.connect(self._export)
        l2.addWidget(QLabel("Période :"))
        l2.addWidget(self.periode)
        l2.addWidget(self.f_groupe)
        l2.addWidget(exp)
        l2.addStretch()
        lc.addLayout(l2)
        self.label_alertes = QLabel("")
        self.label_alertes.setWordWrap(True)
        self.label_alertes.setTextFormat(Qt.TextFormat.RichText)
        lc.addWidget(self.label_alertes)
        self.table_groupes = _table(["Groupe", "Séances", "Appels faits", "Présents en moyenne", "Taux"], 120)
        lc.addWidget(self.table_groupes)
        self.table_assid = _table(["Nom", "Prénom", "Séances", "Présent", "Retard", "Excusé", "Absent", "Taux",
                                   "Absences de suite", "Dernière présence"], 300)
        lc.addWidget(self.table_assid)
        self.principal.addWidget(cadre)
        self.principal.addStretch()
        self._lignes, self._combos, self._notes, self._seances = [], [], [], []
        self._modifie = False
        self.combo_seance.currentIndexChanged.connect(lambda _i: self._charger_appel())
        self.periode.currentIndexChanged.connect(lambda _i: self._remplir_assiduite())
        self.f_groupe.currentIndexChanged.connect(lambda _i: self._remplir_assiduite())
        self._finaliser()

    # ---------------------------------------------------------------- séances proposées
    def actualiser(self):
        actuel = self.combo_seance.currentData()
        auj = date.today()
        self._seances = [s for s in dag.seances(self.club_id, auj - timedelta(days=60), auj + timedelta(days=7))
                         if not s["annulee"]]
        self.combo_seance.blockSignals(True)
        self.combo_seance.clear()
        for s in reversed(self._seances):
            marque = "✅" if s["appel_fait"] else ("⚠️" if s["date"] < auj.isoformat() else "•")
            self.combo_seance.addItem(f"{marque} {_date_courte(s['date'])} · {_horaire(s)} · {s['titre']}"
                                      f" ({s['groupe'] or 'tout le club'})", s["id"])
        if not self._seances:
            self.combo_seance.addItem("Aucune séance ces 60 derniers jours : crée-les dans l'onglet Agenda", None)
        # par défaut : la séance du jour, sinon la plus récente passée
        if actuel is not None and self.combo_seance.findData(actuel) >= 0:
            i = self.combo_seance.findData(actuel)
        else:
            passees = [s for s in self._seances if s["date"] <= auj.isoformat()]
            i = self.combo_seance.findData(passees[-1]["id"]) if passees else 0
        self.combo_seance.setCurrentIndex(max(0, i))
        self.combo_seance.blockSignals(False)
        g = self.f_groupe.currentData()
        self.f_groupe.blockSignals(True)
        self.f_groupe.clear()
        self.f_groupe.addItem("Tous les groupes", None)
        for x in dclub.groupes(self.club_id):
            self.f_groupe.addItem(x["nom"], x["id"])
        self.f_groupe.setCurrentIndex(max(0, self.f_groupe.findData(g)))
        self.f_groupe.blockSignals(False)
        self._charger_appel()
        self._remplir_assiduite()

    def choisir_seance(self, seance_id):
        if self.combo_seance.findData(seance_id) < 0:
            s = dag.seance(seance_id)
            if s:
                self.combo_seance.addItem(f"{_date_courte(s['date'])} · {_horaire(s)} · {s['titre']}", s["id"])
        self.combo_seance.setCurrentIndex(self.combo_seance.findData(seance_id))

    # ---------------------------------------------------------------- appel
    def _charger_appel(self):
        sid = self.combo_seance.currentData()
        self._lignes = dag.appel(sid) if sid else []
        s = dag.seance(sid) if sid else None
        if s:
            self.label_seance.setText(f"{_date_longue(s['date']).capitalize()} · {_horaire(s)} · "
                                      f"{s['groupe'] or 'tout le club'}" + (f" · {s['lieu']}" if s["lieu"] else "")
                                      + (f" · {s['entraineur']}" if s["entraineur"] else "")
                                      + (f"\n{s['contenu']}" if s["contenu"] else ""))
        else:
            self.label_seance.setText("")
        t = self.table
        t.setRowCount(len(self._lignes))
        self._combos, self._notes = [], []
        for i, l in enumerate(self._lignes):
            c = l["categorie"]
            for j, v in enumerate((l["nom"], l["prenom"] + ("" if l["attendu"] else "  (invité)"), c["code"] if c else "?")):
                t.setItem(i, j, QTableWidgetItem(v))
            combo = QComboBox()
            combo.addItem("— à pointer —", None)
            for code, lib in ag.STATUTS_PRESENCE:
                combo.addItem(lib, code)
            combo.setCurrentIndex(max(0, combo.findData(l["statut"])))
            combo.currentIndexChanged.connect(lambda _i: self._bilan())
            t.setCellWidget(i, 3, combo)
            note = QLineEdit(l["note"] or "")
            note.setPlaceholderText("ex. blessé, malade, départ anticipé")
            t.setCellWidget(i, 4, note)
            urg = QTableWidgetItem(l["contact_urgence_tel"] or ("à renseigner" if l["mineur"] else ""))
            if l["mineur"] and not l["contact_urgence_tel"]:
                urg.setForeground(QColor(ORANGE))
            t.setItem(i, 5, urg)
            self._combos.append(combo)
            self._notes.append(note)
        t.resizeColumnsToContents()
        t.setColumnWidth(3, max(t.columnWidth(3), 150))
        t.setColumnWidth(4, max(t.columnWidth(4), 260))
        self._bilan()

    def statuts(self):
        return {l["personne_id"]: (c.currentData(), n.text()) for l, c, n in zip(self._lignes, self._combos, self._notes)}

    def _bilan(self):
        st = {pid: s for pid, (s, _n) in self.statuts().items() if s}
        b = ag.bilan_appel(st, [l["personne_id"] for l in self._lignes if l["attendu"]])
        if not self._lignes:
            self.label_bilan.setText("Personne n'est attendu : ajoute des membres au groupe (onglet Groupes) ou une "
                                     "personne à cet appel.")
            return
        self.label_bilan.setText(
            f"<b style='color:{VERT}'>{b['present']} présent(s)</b> · {b['retard']} en retard · {b['excuse']} excusé(s) · "
            f"<span style='color:{ROUGE}'>{b['absent']} absent(s)</span>"
            + (f" · <span style='color:{ORANGE}'>{b['non_pointes']} à pointer</span>" if b["non_pointes"] else "")
            + (f" · taux {b['taux']} %" if b["taux"] is not None else ""))

    def _tous_presents(self):
        for c in self._combos:
            if c.currentData() is None:
                c.setCurrentIndex(c.findData("present"))

    def _reste_absents(self):
        for c in self._combos:
            if c.currentData() is None:
                c.setCurrentIndex(c.findData("absent"))

    def _ajouter(self):
        sid = self.combo_seance.currentData()
        if not sid:
            return
        deja = {l["personne_id"] for l in self._lignes}
        d = QDialog(self)
        d.setWindowTitle("Ajouter à l'appel")
        d.setStyleSheet(obtenir_style_ecran())
        lay = QVBoxLayout(d)
        combo = QComboBox()
        s = dag.seance(sid)
        for a in dclub.adhesions(self.club_id, cat.saison_de(s["date"])):
            if a["personne_id"] not in deja and a["statut"] != "annulee":
                combo.addItem(f"{a['nom']} {a['prenom']}" + (f" · {a['groupes']}" if a["groupes"] else ""), a["personne_id"])
        for p in dper.lister():
            if p["id"] not in deja and combo.findData(p["id"]) < 0:
                combo.addItem(f"{p['nom']} {p['prenom']} (pas adhérent cette saison)", p["id"])
        lay.addWidget(QLabel("Une personne venue en plus (autre groupe, essai, invité) :"))
        lay.addWidget(combo)
        _boutons_dialogue(d, lay, "Ajouter")
        if d.exec() and combo.currentData():
            st = self.statuts()
            st[combo.currentData()] = ("present", "")
            self._sauver(st, marquer=False)

    def _sauver(self, st, marquer=True):
        sid = self.combo_seance.currentData()
        try:
            dag.enregistrer_appel(sid, {pid: (s, n) if s else None for pid, (s, n) in st.items()}, marquer)
        except dag.ErreurAgenda as e:
            QMessageBox.warning(self, "Appel", str(e))
            return False
        self.actualiser()
        self.choisir_seance(sid)
        return True

    def _enregistrer(self):
        if not self.combo_seance.currentData():
            return
        st = self.statuts()
        reste = sum(1 for s, _n in st.values() if s is None)
        if reste and QMessageBox.question(
                self, "Appel", f"{reste} personne(s) ne sont pas pointées. Enregistrer quand même ? (Elles ne comptent "
                "ni présentes ni absentes.)") != QMessageBox.StandardButton.Yes:
            return
        if self._sauver(st):
            f = self._fenetre()
            if f:
                f.agenda._remplir()
            QMessageBox.information(self, "Appel", "Appel enregistré.")

    # ---------------------------------------------------------------- assiduité
    def _bornes(self):
        auj = date.today()
        code = self.periode.currentData()
        if code == "saison":
            d0, _d1 = cat.bornes_saison(self.saison)
            return d0, auj
        return auj - timedelta(days=int(code)), auj

    def _remplir_assiduite(self):
        d0, d1 = self._bornes()
        g = self.f_groupe.currentData()
        a = dag.assiduite(self.club_id, d0, d1, g)
        noms = {pid: f"{r.get('prenom', '')} {r.get('nom', '')}".strip() for pid, r in a.items()}
        sans = [s for s in dag.sans_appel(self.club_id) if g is None or s["groupe_id"] == g]
        al = ag.alertes_presences(a, noms, len(sans))
        self.label_alertes.setText("<ul>" + "".join(f"<li>{x}</li>" for x in al) + "</ul>" if al else
                                   f"<span style='color:{VERT}'>Rien à signaler sur la période.</span>")
        pg = [x for x in dag.par_groupe(self.club_id, d0, d1)
              if g is None or x["groupe"] == self.f_groupe.currentText()]
        t = self.table_groupes
        t.setRowCount(len(pg))
        for i, x in enumerate(pg):
            for j, v in enumerate((x["groupe"], str(x["seances"]), str(x["appelees"]),
                                   str(x["presents_moyens"]).replace(".", ",") if x["presents_moyens"] is not None else "—",
                                   f"{x['taux']} %" if x["taux"] is not None else "—")):
                t.setItem(i, j, QTableWidgetItem(v))
        t.resizeColumnsToContents()
        lignes = sorted(a.items(), key=lambda x: (x[1]["taux"] if x[1]["taux"] is not None else 101, x[1].get("nom", "")))
        t = self.table_assid
        t.setRowCount(len(lignes))
        for i, (pid, r) in enumerate(lignes):
            vals = [r.get("nom", ""), r.get("prenom", ""), str(r["seances"]), str(r["presents"]), str(r["retards"]),
                    str(r["excuses"]), str(r["absents"]), f"{r['taux']} %" if r["taux"] is not None else "—",
                    str(r["absences_de_suite"]) if r["absences_de_suite"] else "",
                    _d(r["derniere_presence"]).strftime("%d/%m/%Y") if r["derniere_presence"] else "—"]
            for j, v in enumerate(vals):
                it = QTableWidgetItem(v)
                if j == 7 and r["taux"] is not None:
                    it.setForeground(QColor(VERT if r["taux"] >= 75 else ORANGE if r["taux"] >= 50 else ROUGE))
                if j == 8 and r["absences_de_suite"] >= ag.ABSENCES_DECROCHAGE:
                    it.setForeground(QColor(ROUGE))
                t.setItem(i, j, it)
        t.resizeColumnsToContents()

    def _export(self):
        d0, d1 = self._bornes()
        chemin, _ = QFileDialog.getSaveFileName(self, "Exporter les présences", f"Presences {d0} {d1}.csv", "CSV (*.csv)")
        if chemin:
            Path(chemin).write_text(dag.export_presences_csv(self.club_id, d0, d1, self.f_groupe.currentData()),
                                    encoding="utf-8")
            QMessageBox.information(self, "Export", "Présences exportées : une ligne par personne, une colonne par séance "
                                    "(P, R, E, A). Le fichier s'ouvre dans Excel, Numbers ou LibreOffice.")
