"""
Calendrier des courses (module « calendrier ») : compétitions de stade,
hors stade, cross, trail, montagne, ultra-trail, marche nordique, pour
Provence-Alpes-Côte d'Azur, Occitanie et Auvergne-Rhône-Alpes.

Fenêtre « 🗓️ Calendrier des courses », deux onglets :
  - Courses : filtres (période, région, département, famille, niveau),
    fiche de la course, envoi vers « Courses à venir » ou vers l'agenda du
    club, export .ics ;
  - Sources : flux .ics relus tout seuls (toutes les 12 heures, à
    l'ouverture), tableau collé depuis une page de calendrier, fichier
    importé, liens pour ouvrir les calendriers en ligne (FFA, Betrail…).
Aucune requête SQL ici : tout passe par noyau/donnees/calendrier.py.
"""

import html
from datetime import date, timedelta
from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Qt, QUrl, Signal, QDate
from PySide6.QtGui import QColor, QDesktopServices, QGuiApplication
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QDateEdit, QDialog, QDialogButtonBox, QDoubleSpinBox, QFileDialog,
    QFormLayout, QFrame, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPlainTextEdit, QPushButton, QSpinBox,
    QTableWidget, QTableWidgetItem, QVBoxLayout,
)

from noyau.donnees import calendrier as dcal
from noyau.calendrier import regles as R
from interface.conteneur_onglets import ConteneurOnglets
from interface.ecran_liste import configurer_table_redimensionnable, obtenir_style_ecran
from interface.forme_evolution import _EcranAthlete

JOURS = ("lun.", "mar.", "mer.", "jeu.", "ven.", "sam.", "dim.")
COULEUR_FAMILLE = {"Stade": "#42A5F5", "Hors stade": "#FFA726", "Trail": "#66BB6A", "Montagne": "#AB47BC",
                   "Marche nordique": "#26C6DA", "Autre": "#9E9E9E"}


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


def _style_cases(w):
    from interface.theme import PALETTE, obtenir_couleur_accent
    a = obtenir_couleur_accent()
    w.setStyleSheet(w.styleSheet() + (
        " QCheckBox { background: transparent; spacing: 8px; }"
        f" QCheckBox::indicator {{ width: 16px; height: 16px; border: 1px solid {PALETTE['texte_discret']};"
        f" border-radius: 4px; background: {PALETTE['carte_haute']}; }}"
        f" QCheckBox::indicator:checked {{ background: {a}; border-color: {a}; }}"))


def date_courte(iso, fin=None):
    j = date.fromisoformat(str(iso)[:10])
    t = f"{JOURS[j.weekday()]} {j.strftime('%d/%m/%Y')}"
    if fin:
        f = date.fromisoformat(str(fin)[:10])
        t += f" → {JOURS[f.weekday()]} {f.strftime('%d/%m')}"
    return t


def texte_epreuves(c):
    return " · ".join(f"{e['distance_km']:g} km" + (f" {e['denivele_m']} D+" if e.get("denivele_m") else "")
                      for e in c.get("epreuves", []) if e.get("distance_km"))


# ======================================================================
# Lecture des flux en tâche de fond
# ======================================================================

class _Signaux(QObject):
    fini = Signal(int, object, object)          # source_id, contenu, erreur


class _LectureFlux(QRunnable):
    def __init__(self, source_id, url):
        super().__init__()
        self.source_id, self.url = source_id, url
        self.signaux = _Signaux()

    def run(self):
        try:
            self.signaux.fini.emit(self.source_id, dcal.telecharger(self.url), None)
        except Exception as e:                   # réseau ou serveur : le message est gardé sur la source
            self.signaux.fini.emit(self.source_id, None, f"lecture impossible : {e}")


# ======================================================================
# Fiche d'une course
# ======================================================================

class DialogueCourse(QDialog):

    def __init__(self, parent, course=None):
        super().__init__(parent)
        c = course or {}
        self.course_id = c.get("id")
        self.setWindowTitle("Course" if course else "Ajouter une course")
        self.setStyleSheet(obtenir_style_ecran())
        self.resize(640, 640)
        lay = QVBoxLayout(self)
        f = QFormLayout()
        self.nom = QLineEdit(c.get("nom") or "")
        self.debut = QDateEdit(QDate.fromString(c["date_debut"], "yyyy-MM-dd") if c.get("date_debut") else QDate.currentDate())
        self.fin = QDateEdit(QDate.fromString(c["date_fin"], "yyyy-MM-dd") if c.get("date_fin") else self.debut.date())
        for d in (self.debut, self.fin):
            d.setCalendarPopup(True)
            d.setDisplayFormat("dd/MM/yyyy")
        self.commune, self.cp = QLineEdit(c.get("commune") or ""), QLineEdit(c.get("code_postal") or "")
        self.dep = QComboBox()
        self.dep.addItem("—", None)
        for code, nom in sorted(R.NOMS_DEPARTEMENTS.items()):
            self.dep.addItem(f"{code} · {nom}", code)
        self.dep.setCurrentIndex(max(0, self.dep.findData(c.get("departement"))))
        self.discipline = QComboBox()
        for code, lib in R.DISCIPLINES:
            self.discipline.addItem(lib, code)
        self.discipline.setCurrentIndex(max(0, self.discipline.findData(c.get("discipline") or "trail_court")))
        self.niveau = QComboBox()
        self.niveau.addItem("—", None)
        for code, lib in R.NIVEAUX:
            self.niveau.addItem(lib, code)
        self.niveau.setCurrentIndex(max(0, self.niveau.findData(c.get("niveau"))))
        self.statut = QComboBox()
        for code, lib in R.STATUTS:
            self.statut.addItem(lib, code)
        self.statut.setCurrentIndex(max(0, self.statut.findData(c.get("statut") or "prevue")))
        self.organisateur, self.site = QLineEdit(c.get("organisateur") or ""), QLineEdit(c.get("site") or "")
        self.inscription = QLineEdit(c.get("inscription_url") or "")
        self.epreuves = QLineEdit(", ".join(f"{e['distance_km']:g} km" + (f" {e['denivele_m']} D+" if e.get("denivele_m")
                                                                              else "")
                                            for e in c.get("epreuves", []) if e.get("distance_km")))
        self.epreuves.setPlaceholderText("ex. 12 km 450 D+, 25 km 1200 D+, 42 km 2300 D+")
        self.notes = QLineEdit(c.get("notes") or "")
        self.mes_notes = QPlainTextEdit(c.get("mes_notes") or "")
        self.mes_notes.setMaximumHeight(80)
        self.mes_notes.setPlaceholderText("Tes notes : objectif, logement, covoiturage…")
        for lib, w in (("Nom", self.nom), ("Début", self.debut), ("Fin", self.fin), ("Commune", self.commune),
                       ("Code postal", self.cp), ("Département", self.dep), ("Discipline", self.discipline),
                       ("Niveau", self.niveau), ("État", self.statut), ("Organisateur", self.organisateur),
                       ("Site", self.site), ("Inscriptions", self.inscription), ("Épreuves", self.epreuves),
                       ("Remarque", self.notes), ("Mes notes", self.mes_notes)):
            f.addRow(lib, w)
        lay.addLayout(f)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        bb.button(QDialogButtonBox.StandardButton.Save).setText("Enregistrer")
        bb.button(QDialogButtonBox.StandardButton.Cancel).setText("Annuler")
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def champs(self):
        d0, d1 = self.debut.date().toString("yyyy-MM-dd"), self.fin.date().toString("yyyy-MM-dd")
        cp = self.cp.text().strip() or None
        return {"nom": self.nom.text(), "date_debut": d0, "date_fin": d1 if d1 > d0 else None,
                "commune": self.commune.text().strip() or None, "code_postal": cp,
                "departement": self.dep.currentData() or (cp[:2] if cp else None), "discipline": self.discipline.currentData(),
                "niveau": self.niveau.currentData(), "statut": self.statut.currentData(),
                "organisateur": self.organisateur.text().strip() or None, "site": self.site.text().strip() or None,
                "inscription_url": self.inscription.text().strip() or None, "notes": self.notes.text().strip() or None,
                "mes_notes": self.mes_notes.toPlainText().strip() or None,
                "epreuves": [{"nom": f"{d:g} km", "distance_km": d, "denivele_m": dp}
                             for d, dp in R.lire_distances(self.epreuves.text())]}

    def accept(self):
        try:
            dcal.enregistrer_course(self.champs(), self.course_id)
        except dcal.ErreurCalendrier as e:
            QMessageBox.warning(self, "Course", str(e))
            return
        super().accept()


# ======================================================================
# Onglet Courses
# ======================================================================

PERIODES = (("3mois", "Les 3 prochains mois"), ("6mois", "Les 6 prochains mois"), ("saison", "Jusqu'au 31 août"),
            ("an", "Les 12 prochains mois"), ("tout", "Tout le calendrier à venir"), ("passees", "Courses passées"))


class CoursesCalendrierCompetitions(_EcranAthlete):
    COLONNES = ["Date", "Course", "Lieu", "Dép.", "Discipline", "Épreuves", "Niveau", "Source"]

    def __init__(self, athlete_id_initial=None):
        super().__init__("🗓️  Calendrier des courses", "Stade, hors stade, cross, trail, montagne, ultra-trail et marche "
                         "nordique en Provence-Alpes-Côte d'Azur, Occitanie et Auvergne-Rhône-Alpes. Choisis une course "
                         "pour l'ajouter à tes courses à venir ou à l'agenda du club.", athlete_id_initial)
        f = QHBoxLayout()
        self.periode = QComboBox()
        for code, lib in PERIODES:
            self.periode.addItem(lib, code)
        self.periode.setCurrentIndex(2)
        self.region = QComboBox()
        self.region.addItem("Les trois régions", None)
        for r in R.REGIONS:
            self.region.addItem(r, r)
        self.departement = QComboBox()
        self.famille = QComboBox()
        self.famille.addItem("Toutes les disciplines", None)
        for fam in R.FAMILLES:
            self.famille.addItem(fam, fam)
        self.niveau = QComboBox()
        self.niveau.addItem("Tous les niveaux", None)
        for code, lib in R.NIVEAUX:
            self.niveau.addItem(lib, code)
        for w in (self.periode, self.region, self.departement, self.famille, self.niveau):
            f.addWidget(w, 1)
        self.principal.addLayout(f)
        f2 = QHBoxLayout()
        self.recherche = QLineEdit()
        self.recherche.setPlaceholderText("Rechercher (nom, commune, organisateur, tes notes)")
        self.favoris = QCheckBox("Mes favorites")
        self.annulees = QCheckBox("Montrer les annulées")
        f2.addWidget(self.recherche, 3)
        f2.addWidget(self.favoris)
        f2.addWidget(self.annulees)
        self.principal.addLayout(f2)
        b = QHBoxLayout()
        for texte, fn, p in (("➕ Ajouter", self._ajouter, True), ("✏️ Fiche", self._modifier, False),
                             ("⭐ Favorite", self._favori, False), ("🏁 Dans mes courses à venir", self._mes_courses, True),
                             ("🏟️ À l'agenda du club", self._club, False), ("🌐 Site ou recherche", self._site, False),
                             ("🙈 Masquer", self._masquer, False), ("📆 Exporter (.ics)", self._ics, False)):
            w = _bouton(texte, p)
            w.clicked.connect(fn)
            b.addWidget(w)
        b.addStretch()
        self.principal.addLayout(b)
        self.compte = QLabel("")
        self.compte.setObjectName("texteSecondaire")
        self.principal.addWidget(self.compte)
        self.table = _table(self.COLONNES, 460)
        self.table.cellDoubleClicked.connect(lambda _r, _c: self._modifier())
        self.table.itemSelectionChanged.connect(self._detail)
        self.principal.addWidget(self.table)
        cadre, lc = _cadre("La course")
        self.detail = QLabel("Choisis une course.")
        self.detail.setWordWrap(True)
        self.detail.setTextFormat(Qt.TextFormat.RichText)
        self.detail.setOpenExternalLinks(True)
        lc.addWidget(self.detail)
        self.principal.addWidget(cadre)
        self.principal.addStretch()
        self._toutes, self._vues = [], []
        self._remplir_departements()
        self.region.currentIndexChanged.connect(lambda _i: (self._remplir_departements(), self._remplir()))
        for w in (self.periode, self.departement, self.famille, self.niveau):
            w.currentIndexChanged.connect(lambda _i: self._remplir())
        self.recherche.textChanged.connect(lambda _t: self._remplir())
        self.favoris.toggled.connect(lambda _b: self._remplir())
        self.annulees.toggled.connect(lambda _b: self._remplir())
        self._finaliser()
        _style_cases(self)

    def _remplir_departements(self):
        r = self.region.currentData()
        self.departement.blockSignals(True)
        self.departement.clear()
        self.departement.addItem("Tous les départements", None)
        for d in (R.REGIONS[r] if r else sorted(R.REGION_DU_DEPARTEMENT)):
            self.departement.addItem(f"{d} · {R.NOMS_DEPARTEMENTS[d]}", d)
        self.departement.blockSignals(False)

    def _bornes(self):
        auj = date.today()
        code = self.periode.currentData()
        if code == "passees":
            return auj - timedelta(days=730), auj - timedelta(days=1)
        if code == "saison":
            fin = date(auj.year + (1 if auj.month >= 9 else 0), 8, 31)
            return auj, fin
        jours = {"3mois": 92, "6mois": 183, "an": 365}.get(code)
        return auj, (auj + timedelta(days=jours)) if jours else None

    def actualiser(self, *_):
        self._toutes = []
        self._remplir()

    def _remplir(self):
        d0, d1 = self._bornes()
        if not self._toutes or getattr(self, "_periode_lue", None) != self.periode.currentData():
            self._periode_lue = self.periode.currentData()
            self._toutes = dcal.courses(d0, d1)
        r, dep = self.region.currentData(), self.departement.currentData()
        deps = (dep,) if dep else (R.REGIONS[r] if r else None)
        self._vues = R.filtrer(self._toutes, d0, d1, deps, (self.famille.currentData(),) if self.famille.currentData() else None,
                               None, (self.niveau.currentData(),) if self.niveau.currentData() else None,
                               self.recherche.text(), self.favoris.isChecked(), self.annulees.isChecked())
        if self.periode.currentData() == "passees":
            self._vues = list(reversed(self._vues))
        t = self.table
        t.setRowCount(len(self._vues))
        for i, c in enumerate(self._vues):
            vals = [date_courte(c["date_debut"], c.get("date_fin")), ("⭐ " if c["favori"] else "") + c["nom"],
                    c.get("commune") or "", c.get("departement") or "", R.LIBELLE_DISCIPLINE.get(c["discipline"], ""),
                    texte_epreuves(c), R.LIBELLE_NIVEAU.get(c.get("niveau"), ""), c.get("source") or ""]
            for j, v in enumerate(vals):
                it = QTableWidgetItem(v)
                if j == 4:
                    it.setForeground(QColor(COULEUR_FAMILLE.get(c["famille"], "#9E9E9E")))
                if c.get("statut") == "annulee":
                    f = it.font()
                    f.setStrikeOut(True)
                    it.setFont(f)
                t.setItem(i, j, it)
        t.resizeColumnsToContents()
        for j in range(t.columnCount()):
            if t.columnWidth(j) > 340:
                t.setColumnWidth(j, 340)
        par = {}
        for c in self._vues:
            par[c["famille"]] = par.get(c["famille"], 0) + 1
        self.compte.setText(f"{len(self._vues)} course(s)" + (" · " + ", ".join(f"{k} {v}" for k, v in par.items())
                                                              if par else "")
                            + ("" if self._toutes else " — le calendrier est vide : ajoute des sources dans l'onglet Sources."))
        self._detail()

    def _courante(self):
        i = self.table.currentRow()
        return self._vues[i] if 0 <= i < len(self._vues) and self.table.selectedItems() else None

    def _detail(self):
        c = self._courante()
        if not c:
            self.detail.setText("Choisis une course.")
            return
        e = html.escape
        l = [f"<b style='font-size:15px'>{e(c['nom'])}</b> · {e(date_courte(c['date_debut'], c.get('date_fin')))}"
             + (" · <span style='color:#EF5350'>ANNULÉE</span>" if c.get("statut") == "annulee" else
                " · reportée" if c.get("statut") == "reportee" else "")]
        lieu = " ".join(x for x in (c.get("code_postal"), c.get("commune")) if x)
        l.append(" · ".join(x for x in (e(lieu), e(R.NOMS_DEPARTEMENTS.get(c.get("departement"), "")), e(c.get("region") or ""))
                            if x))
        l.append(e(R.LIBELLE_DISCIPLINE.get(c["discipline"], "")) + (f" · {e(R.LIBELLE_NIVEAU[c['niveau']])}"
                                                                    if c.get("niveau") else ""))
        if c["epreuves"]:
            l.append("Épreuves : " + " · ".join(
                e(f"{x['distance_km']:g} km" + (f" / {x['denivele_m']} m D+ ({x['km_effort']:g} km-effort)"
                                                if x.get("denivele_m") else "")
                  + (f" à {x['heure_depart']}" if x.get("heure_depart") else "") + (f", {x['prix']:g} €" if x.get("prix")
                                                                                    else ""))
                for x in c["epreuves"] if x.get("distance_km")))
        if c.get("organisateur"):
            l.append(f"Organisateur : {e(c['organisateur'])}")
        liens = [f"<a style='color:#4FC3F7' href='{e(c['site'])}'>site</a>"] if c.get("site") else []
        if c.get("inscription_url"):
            liens.append(f"<a style='color:#4FC3F7' href='{e(c['inscription_url'])}'>inscriptions</a>")
        liens.append(f"<a style='color:#4FC3F7' href='{e(R.recherche_web(c))}'>chercher sur le web</a>")
        l.append(" · ".join(liens))
        if c.get("notes"):
            l.append(f"<i>{e(c['notes'][:300])}</i>")
        if c.get("mes_notes"):
            l.append(f"📝 {e(c['mes_notes'])}")
        l.append(f"<span style='color:#9E9E9E'>Source : {e(c.get('source') or '—')}"
                 + (" · corrigée par toi" if c.get("modifie") else "") + "</span>")
        self.detail.setText("<br>".join(l))

    def _ajouter(self):
        if DialogueCourse(self).exec():
            self._toutes = []
            self._remplir()

    def _modifier(self):
        c = self._courante()
        if c and DialogueCourse(self, c).exec():
            self._toutes = []
            self._remplir()

    def _favori(self):
        c = self._courante()
        if c:
            dcal.definir_favori(c["id"], not c["favori"])
            self._toutes = []
            self._remplir()

    def _masquer(self):
        c = self._courante()
        if c and QMessageBox.question(self, "Masquer", f"Ne plus montrer « {c['nom']} » ? (Elle ne reviendra pas avec les "
                                      "mises à jour des sources.)") == QMessageBox.StandardButton.Yes:
            dcal.masquer(c["id"])
            self._toutes = []
            self._remplir()

    def _site(self):
        c = self._courante()
        if c:
            QDesktopServices.openUrl(QUrl(c.get("inscription_url") or c.get("site") or R.recherche_web(c)))

    def _mes_courses(self):
        c = self._courante()
        a = self.combo_athlete.currentData()
        if not c:
            return
        if not a:
            QMessageBox.information(self, "Courses à venir", "Choisis d'abord l'athlète en haut de l'écran.")
            return
        ep = None
        if len(c["epreuves"]) > 1:
            d = QDialog(self)
            d.setWindowTitle("Quelle épreuve ?")
            d.setStyleSheet(obtenir_style_ecran())
            lay = QVBoxLayout(d)
            combo = QComboBox()
            for x in c["epreuves"]:
                combo.addItem(f"{x['distance_km']:g} km" + (f" / {x['denivele_m']} m D+" if x.get("denivele_m") else ""),
                              x["id"])
            lay.addWidget(QLabel(f"{c['nom']} : quelle épreuve cours-tu ?"))
            lay.addWidget(combo)
            bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
            bb.accepted.connect(d.accept)
            bb.rejected.connect(d.reject)
            lay.addWidget(bb)
            if not d.exec():
                return
            ep = combo.currentData()
        dcal.envoyer_vers_mes_courses(c["id"], a, ep)
        QMessageBox.information(self, "Courses à venir", f"« {c['nom']} » est dans tes courses à venir : prépare-la "
                                "(roadbook, matériel obligatoire, nutrition) depuis l'écran Courses à venir.")

    def _club(self):
        c = self._courante()
        if not c:
            return
        from noyau import modules as mods
        if not mods.est_actif("club"):
            QMessageBox.information(self, "Club", "Allume d'abord le module « Gestion du club » dans Réglages > Modules.")
            return
        from noyau.donnees import club as dclub
        dcal.proposer_au_club(c["id"], dclub.club_id_ou_creer())
        QMessageBox.information(self, "Club", f"« {c['nom']} » est dans l'agenda du club (compétition, tout le club). Tu "
                                "peux la rattacher à un groupe dans l'onglet Agenda du Club.")

    def _ics(self):
        chemin, _ = QFileDialog.getSaveFileName(self, "Exporter", "Calendrier des courses.ics", "Agenda (*.ics)")
        if chemin:
            Path(chemin).write_text(dcal.export_ics(self._vues), encoding="utf-8", newline="")
            QMessageBox.information(self, "Export", f"{len(self._vues)} course(s) exportée(s) : ouvre le fichier sur ton "
                                    "téléphone ou dans Google Agenda.")


# ======================================================================
# Onglet Sources
# ======================================================================

class SourcesCalendrier(_EcranAthlete):

    def __init__(self, athlete_id_initial=None):
        super().__init__("🔄  Sources du calendrier", "D'où viennent les courses. Les flux .ics sont relus tout seuls à "
                         "l'ouverture (toutes les 12 heures). Les sites de calendriers qui n'ont pas de flux s'ouvrent "
                         "dans ton navigateur : copie le tableau des courses et colle-le ici.", athlete_id_initial)
        for i in range(self.barre.count()):
            w = self.barre.itemAt(i).widget()
            if w is not None:
                w.hide()
        # --- flux .ics
        cadre, lc = _cadre("Sources (les flux .ics sont les agendas publiés par des organisateurs, comités, ligues, clubs)")
        self.table = _table(["Source", "Type", "Adresse", "Dernière lecture", "Courses", "État"], 200)
        lc.addWidget(self.table)
        b = QHBoxLayout()
        for texte, fn, p in (("➕ Ajouter un flux .ics", self._ajouter_flux, True), ("🔄 Relire maintenant", self._relire, False),
                             ("⏸ Activer / mettre en pause", self._pause, False), ("🗑 Supprimer", self._supprimer, False)):
            w = _bouton(texte, p)
            w.clicked.connect(fn)
            b.addWidget(w)
        b.addStretch()
        lc.addLayout(b)
        self.etat = QLabel("")
        self.etat.setWordWrap(True)
        self.etat.setObjectName("texteSecondaire")
        lc.addWidget(self.etat)
        aide = QLabel("Où trouver un flux : dans Google Agenda, « Paramètres de l'agenda > Adresse publique au format "
                      "iCal » ; sur un site, un lien « S'abonner », « iCal », « .ics » ou « webcal:// ».")
        aide.setWordWrap(True)
        aide.setObjectName("texteSecondaire")
        lc.addWidget(aide)
        self.principal.addWidget(cadre)
        # --- calendriers en ligne + collage
        cadre, lc = _cadre("Calendriers en ligne : ouvrir, copier le tableau, coller ici")
        l1 = QHBoxLayout()
        self.famille = QComboBox()
        for fam in R.FAMILLES[:-1]:
            self.famille.addItem(fam, fam)
        self.famille.setCurrentIndex(2)
        self.region = QComboBox()
        for r in R.REGIONS:
            self.region.addItem(r, r)
        l1.addWidget(QLabel("Discipline :"))
        l1.addWidget(self.famille)
        l1.addWidget(QLabel("Région :"))
        l1.addWidget(self.region)
        l1.addStretch()
        lc.addLayout(l1)
        self.liens = QHBoxLayout()
        lc.addLayout(self.liens)
        self.famille.currentIndexChanged.connect(lambda _i: self._remplir_liens())
        self.region.currentIndexChanged.connect(lambda _i: self._remplir_liens())
        self.collage = QPlainTextEdit()
        self.collage.setPlaceholderText("Colle ici le tableau copié depuis la page du calendrier (sélectionne les lignes "
                                        "des courses, Ctrl+C, puis Ctrl+V ici). Une ligne par course, avec au moins une "
                                        "date et un nom ; le lieu, le type et le niveau sont reconnus s'ils y sont.")
        self.collage.setMinimumHeight(180)
        lc.addWidget(self.collage)
        l2 = QHBoxLayout()
        self.nom_collage = QComboBox()
        self.nom_collage.setEditable(True)
        self.nom_collage.addItems(["Calendrier FFA", "Betrail", "Sas Départ", "GoTrail", "Sport-Nature", "Trace de Trail",
                                   "Autre calendrier"])
        coller = _bouton("📋 Coller depuis le presse-papiers")
        coller.clicked.connect(lambda: self.collage.setPlainText(QGuiApplication.clipboard().text()))
        apercu = _bouton("👀 Aperçu")
        apercu.clicked.connect(self._apercu)
        ajouter = _bouton("✅ Ajouter au calendrier", True)
        ajouter.clicked.connect(self._ajouter_collage)
        fichier = _bouton("📂 Importer un fichier (.ics, .csv)")
        fichier.clicked.connect(self._importer_fichier)
        l2.addWidget(QLabel("Provenance :"))
        l2.addWidget(self.nom_collage)
        for w in (coller, apercu, ajouter, fichier):
            l2.addWidget(w)
        l2.addStretch()
        lc.addLayout(l2)
        self.label_apercu = QLabel("")
        self.label_apercu.setWordWrap(True)
        self.label_apercu.setTextFormat(Qt.TextFormat.RichText)
        lc.addWidget(self.label_apercu)
        self.principal.addWidget(cadre)
        self.principal.addStretch()
        self._sources = []
        self._en_cours = set()
        self._remplir_liens()
        self._finaliser()
        _style_cases(self)

    def _fenetre(self):
        w = self.parent()
        while w is not None and not isinstance(w, CalendrierFenetre):
            w = w.parent()
        return w

    def _remplir_liens(self):
        while self.liens.count():
            w = self.liens.takeAt(0).widget()
            if w:
                w.deleteLater()
        for nom, url in R.liens_calendriers(self.famille.currentData(), self.region.currentData()):
            b = _bouton(f"🌐 {nom}")
            b.setToolTip(url)
            b.clicked.connect(lambda _c=False, u=url, n=nom: self._ouvrir(u, n))
            self.liens.addWidget(b)
        self.liens.addStretch()

    def _ouvrir(self, url, nom):
        QDesktopServices.openUrl(QUrl(url))
        i = self.nom_collage.findText(nom)
        if i >= 0:
            self.nom_collage.setCurrentIndex(i)

    def actualiser(self, *_):
        self._sources = dcal.sources()
        t = self.table
        t.setRowCount(len(self._sources))
        for i, s in enumerate(self._sources):
            etat = ("lecture…" if s["id"] in self._en_cours else ("⚠️ " + s["erreur"]) if s["erreur"] else
                    ("en pause" if not s["actif"] else "ok"))
            vals = [s["nom"], dcal.LIBELLE_SOURCE.get(s["type"], s["type"]), s["url"] or "",
                    (s["derniere_maj"] or "").replace("T", " ")[:16], str(s["nb_courses"] or 0), etat]
            for j, v in enumerate(vals):
                it = QTableWidgetItem(v)
                if j == 5 and s["erreur"]:
                    it.setForeground(QColor("#EF6C00"))
                t.setItem(i, j, it)
        t.resizeColumnsToContents()
        if t.columnWidth(2) > 380:
            t.setColumnWidth(2, 380)

    # --- flux
    def lancer_relectures(self, toutes=False):
        """Relit en tâche de fond les flux à relire (ou tous). Renvoie le nombre de lectures lancées."""
        liste = [s for s in dcal.sources() if s["type"] == "ics" and s["actif"] and s["url"]] if toutes else dcal.a_relire()
        for s in liste:
            if s["id"] in self._en_cours:
                continue
            self._en_cours.add(s["id"])
            tache = _LectureFlux(s["id"], s["url"])
            tache.signaux.fini.connect(self._flux_lu)
            QThreadPool.globalInstance().start(tache)
        if liste:
            self.etat.setText(f"Lecture de {len(liste)} flux…")
            self.actualiser()
        return len(liste)

    def _flux_lu(self, source_id, contenu, erreur):
        from shiboken6 import isValid
        if not isValid(self):
            return
        self._en_cours.discard(source_id)
        r = dcal.appliquer_flux(source_id, contenu, erreur)
        s = dcal.source(source_id)
        self.etat.setText(f"{s['nom'] if s else 'Flux'} : " + (f"⚠️ {erreur}" if erreur else
                          f"{r['ajoutees']} nouvelle(s) course(s), {r['mises_a_jour']} mise(s) à jour."))
        self.actualiser()
        f = self._fenetre()
        if f:
            f.courses._toutes = []
            f.courses._remplir()

    def _ajouter_flux(self):
        d = QDialog(self)
        d.setWindowTitle("Ajouter un flux .ics")
        d.setStyleSheet(obtenir_style_ecran())
        f = QFormLayout(d)
        nom, url = QLineEdit(), QLineEdit()
        nom.setPlaceholderText("ex. Comité du Vaucluse, Trails de Provence")
        url.setPlaceholderText("https://…/calendrier.ics ou webcal://…")
        f.addRow("Nom", nom)
        f.addRow("Adresse du flux", url)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(d.accept)
        bb.rejected.connect(d.reject)
        f.addRow(bb)
        if not d.exec():
            return
        try:
            dcal.enregistrer_source({"nom": nom.text(), "type": "ics", "url": url.text()})
        except dcal.ErreurCalendrier as e:
            QMessageBox.warning(self, "Flux", str(e))
            return
        self.lancer_relectures()
        self.actualiser()

    def _courante(self):
        i = self.table.currentRow()
        return self._sources[i] if 0 <= i < len(self._sources) else None

    def _relire(self):
        s = self._courante()
        if s and s["type"] == "ics":
            self._en_cours.discard(s["id"])
            self._en_cours.add(s["id"])
            tache = _LectureFlux(s["id"], s["url"])
            tache.signaux.fini.connect(self._flux_lu)
            QThreadPool.globalInstance().start(tache)
            self.actualiser()
        elif not s:
            self.lancer_relectures(toutes=True)

    def _pause(self):
        s = self._courante()
        if s:
            dcal.enregistrer_source({**s, "actif": not s["actif"]}, s["id"])
            self.actualiser()

    def _supprimer(self):
        s = self._courante()
        if not s:
            return
        rep = QMessageBox.question(self, "Supprimer", f"Supprimer la source « {s['nom']} » ? Oui : ses courses partent aussi "
                                   "(sauf tes favorites et celles que tu as corrigées ou notées). Non : les courses restent.",
                                   QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No |
                                   QMessageBox.StandardButton.Cancel)
        if rep == QMessageBox.StandardButton.Cancel:
            return
        dcal.supprimer_source(s["id"], rep == QMessageBox.StandardButton.Yes)
        self.actualiser()

    # --- collage et fichiers
    def _lire(self):
        t = self.collage.toPlainText()
        if "BEGIN:VCALENDAR" in t[:2000]:
            return R.lire_ics(t)
        return R.lire_tableau(t)

    def _apercu(self):
        courses, erreurs = self._lire()
        if not courses:
            self.label_apercu.setText("Aucune course reconnue : il faut au moins une date et un nom par ligne."
                                      + (f"<br>{html.escape('; '.join(erreurs[:5]))}" if erreurs else ""))
            return
        lignes = "".join(f"<li>{html.escape(date_courte(c['date_debut']))} — <b>{html.escape(c['nom'])}</b>"
                         f"{(' · ' + html.escape(c['commune'])) if c.get('commune') else ''}"
                         f"{(' (' + c['departement'] + ')') if c.get('departement') else ''} · "
                         f"{html.escape(R.LIBELLE_DISCIPLINE.get(c['discipline'], ''))}"
                         f"{(' · ' + html.escape(texte_epreuves(c))) if c.get('epreuves') else ''}</li>"
                         for c in courses[:12])
        self.label_apercu.setText(f"<b>{len(courses)} course(s) reconnue(s)</b>" + (f", {len(erreurs)} ligne(s) écartée(s)"
                                                                                 if erreurs else "")
                                  + f"<ul>{lignes}</ul>" + ("…" if len(courses) > 12 else ""))

    def _ajouter_collage(self):
        t = self.collage.toPlainText().strip()
        if not t:
            return
        r = dcal.importer_texte(t, self.nom_collage.currentText().strip() or "Collage")
        self._apres_import(r)
        self.collage.clear()

    def _importer_fichier(self):
        chemin, _ = QFileDialog.getOpenFileName(self, "Importer", "", "Calendriers (*.ics *.csv *.txt)")
        if chemin:
            r = dcal.importer_texte(Path(chemin).read_bytes(), Path(chemin).stem, "fichier")
            self._apres_import(r)

    def _apres_import(self, r):
        txt = f"{r['ajoutees']} course(s) ajoutée(s), {r['mises_a_jour']} mise(s) à jour (déjà connues)."
        if r.get("ignorees"):
            txt += f" {r['ignorees']} gardée(s) telle(s) que tu les as corrigées."
        if r["erreurs"]:
            txt += "\n\nÀ revoir :\n" + "\n".join(r["erreurs"][:10])
        QMessageBox.information(self, "Calendrier", txt)
        self.label_apercu.setText("")
        self.actualiser()
        f = self._fenetre()
        if f:
            f.courses._toutes = []
            f.courses._remplir()


class CalendrierFenetre(ConteneurOnglets):

    def __init__(self, athlete_id_initial=None):
        super().__init__(titre="Calendrier des courses",
                         onglets=[("🗓️ Courses", CoursesCalendrierCompetitions), ("🔄 Sources", SourcesCalendrier)],
                         athlete_id_initial=athlete_id_initial)
        self.courses, self.sources = self.ecrans
        self.sources.lancer_relectures()             # mise à jour automatique des flux à l'ouverture
