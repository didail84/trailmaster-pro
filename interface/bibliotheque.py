"""
Fenêtre « 📚 Bibliothèque trail » : les livres et documents de référence
sur l'entraînement trail, la physiologie, la charge, la récupération, la
nutrition, le renforcement, les blessures, le mental, les récits et
l'organisation de courses — chacun rattaché aux écrans du logiciel qu'il
éclaire.
  - Livres : filtres (thème, module, langue, à lire / lu), recherche, fiche
    et lien pour trouver le livre ;
  - Par écran du logiciel : pour chaque écran du menu, les livres qui vont
    avec.
Les règles et la liste sont dans noyau/bibliotheque ; l'écran ne fait
qu'afficher. Les statuts « à lire » et « lu » sont gardés dans les réglages.
"""

import html

from PySide6.QtCore import QUrl, Qt
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QCheckBox, QComboBox, QHBoxLayout, QLabel, QLineEdit, QSplitter, QTextBrowser

from noyau import modules as M
from noyau.bibliotheque import regles as R
from interface.conteneur_onglets import ConteneurOnglets
from interface.forme_evolution import _EcranAthlete
from interface.calendrier_competitions import _bouton, _cadre, _table, _style_cases
from interface.organisation_logistique import _remplir, _ligne_choisie

GRIS, VERT, ORANGE = "#8A949E", "#2E7D32", "#E65100"


def _e(v):
    return html.escape(str(v if v is not None else ""))


def _lecteur():
    t = QTextBrowser()
    t.setOpenExternalLinks(True)
    t.document().setDefaultStyleSheet("a { color: #4FA3E0; text-decoration: none; } h3 { font-size: 15px; }")
    return t


def html_livre(l, statut=None):
    """Fiche d'un livre, en HTML simple (aussi utilisée par les tests)."""
    if not l:
        return "<p style='color:#8A949E'>Choisis un livre dans la liste.</p>"
    titre = R.titre_affiche(l)
    orig = (f"<p style='color:#8A949E;margin:0'>Titre d'origine : <i>{_e(l['titre'])}</i></p>"
            if l.get("titre_fr") and l["titre_fr"] != l["titre"] else "")
    ref = R.reference_courte(l)
    noms_modules = [M.PAR_CODE[c].nom for c in l.get("modules", []) if c in M.PAR_CODE]
    lignes = [
        f"<h3 style='margin:0 0 4px 0'>{_e(titre)}</h3>", orig,
        f"<p style='margin:4px 0'>{_e(R.auteurs(l))}</p>",
        f"<p style='color:#8A949E;margin:0 0 8px 0'>{_e(l.get('type', 'Livre'))}"
        + (f" · {_e(ref)}" if ref else "") + f" · {_e(R.NOM_LANGUE.get(l.get('langue'), l.get('langue')))}"
        + "</p>",
        f"<p>{_e(l.get('pourquoi'))}</p>",
        f"<p><b>Thème :</b> {_e(R.nom_theme(l['theme']))} · <b>Niveau :</b> {_e(l.get('niveau'))}</p>",
        f"<p><b>Dans le logiciel :</b> {_e(', '.join(l.get('ecrans', [])))}"
        + (f" <span style='color:#8A949E'>(modules {_e(', '.join(noms_modules))})</span>" if noms_modules else "") + "</p>",
    ]
    if l.get("note"):
        lignes.append(f"<p style='color:#8A949E'>{_e(l['note'])}</p>")
    if statut:
        lignes.append(f"<p><b>{_e(R.LIBELLE_STATUT[statut])}</b></p>")
    texte_lien = "Ouvrir le document ↗" if l.get("lien") else "Trouver ce livre (Open Library) ↗"
    lignes.append(f"<p><a href='{_e(R.lien(l))}'>{texte_lien}</a></p>")
    return "".join(lignes)


class _EcranBiblio(_EcranAthlete):
    """Pas de choix de coureur : la bibliothèque est la même pour tous."""

    def __init__(self, titre, sous_titre, athlete_id_initial=None):
        super().__init__(titre, sous_titre, athlete_id_initial)
        for i in range(self.barre.count()):
            w = self.barre.itemAt(i).widget()
            if w is not None:
                w.hide()

    def _finir(self):
        self._finaliser()
        _style_cases(self)

    def actualiser(self, *_):
        self.rafraichir()

    def showEvent(self, ev):
        super().showEvent(ev)
        if getattr(self, "_vu", False):
            self.actualiser()
        self._vu = True


# ======================================================================
# Livres
# ======================================================================

class LivresReference(_EcranBiblio):

    def __init__(self, athlete_id_initial=None):
        super().__init__("📚  Livres de référence",
                         "Les livres et documents qui font référence pour le trail et pour ce que fait le logiciel : "
                         "entraînement, VMA et fractionné, charge et fréquence cardiaque, récupération et sommeil, "
                         "nutrition et poids, renforcement, blessures, mental, récits, organisation de courses. "
                         "Titres, auteurs et éditeurs vérifiés ; une case vide veut dire « non vérifiée ».",
                         athlete_id_initial)
        self._vues, self._statuts = [], {}
        h = QHBoxLayout()
        self.theme, self.module, self.langue, self.statut = QComboBox(), QComboBox(), QComboBox(), QComboBox()
        self.theme.addItem("Tous les thèmes", None)
        for c, n in R.themes():
            self.theme.addItem(n, c)
        self.module.addItem("Tous les modules", None)
        codes = {c for l in R.lire_reference()["livres"] for c in l.get("modules", [])}
        for m in M.MODULES:
            if m.code in codes:
                self.module.addItem(m.nom, m.code)
        self.langue.addItem("Toutes les langues", None)
        for c, n in R.LANGUES:
            self.langue.addItem(f"Écrit en {n.lower()}", c)
        self.statut.addItem("Tous", None)
        for c, n in R.STATUTS:
            self.statut.addItem(n, c)
        self.statut.addItem("Ni à lire ni lu", "aucun")
        self.recherche = QLineEdit()
        self.recherche.setPlaceholderText("Chercher (titre, auteur, VMA, sommeil…)")
        self.en_francais = QCheckBox("Lisible en français")
        for w in (self.theme, self.module, self.langue, self.statut, self.recherche, self.en_francais):
            h.addWidget(w)
        h.addStretch()
        self.principal.addLayout(h)
        self.etat = QLabel("")
        self.etat.setObjectName("texteSecondaire")
        self.principal.addWidget(self.etat)

        cadre, lc = _cadre("Bibliothèque")
        sp = QSplitter(Qt.Orientation.Horizontal)
        self.table = _table(["Titre", "Auteur(s)", "Année", "Thème", "Niveau", "Langue", "Statut"], 460)
        self.table.itemSelectionChanged.connect(self._detail)
        self.table.doubleClicked.connect(lambda _i: self._ouvrir())
        sp.addWidget(self.table)
        self.lecteur = _lecteur()
        self.lecteur.setMinimumWidth(340)
        sp.addWidget(self.lecteur)
        sp.setSizes([760, 440])
        lc.addWidget(sp, 1)
        b = QHBoxLayout()
        self.b_ouvrir = _bouton("Trouver le livre ↗", True)
        self.b_ouvrir.clicked.connect(self._ouvrir)
        self.b_a_lire = _bouton("★ À lire")
        self.b_a_lire.clicked.connect(lambda: self._basculer("a_lire"))
        self.b_lu = _bouton("✓ Lu")
        self.b_lu.clicked.connect(lambda: self._basculer("lu"))
        for w in (self.b_ouvrir, self.b_a_lire, self.b_lu):
            b.addWidget(w)
        b.addStretch()
        lc.addLayout(b)
        self.principal.addWidget(cadre, 1)

        for w in (self.theme, self.module, self.langue, self.statut):
            w.currentIndexChanged.connect(lambda _i: self.rafraichir())
        self.en_francais.toggled.connect(lambda _b: self.rafraichir())
        self.recherche.textChanged.connect(lambda _t: self.rafraichir())
        self._finir()

    def rafraichir(self):
        avant = self._choisi() if self._vues else None
        garde = avant["id"] if avant else None
        self._statuts = R.lire_statuts()
        self._vues = R.livres(theme=self.theme.currentData(), module=self.module.currentData(),
                              langue=self.langue.currentData(), en_francais=self.en_francais.isChecked(),
                              recherche=self.recherche.text().strip() or None, statut=self.statut.currentData(),
                              statuts=self._statuts)
        coul = {}
        for r, l in enumerate(self._vues):
            s = self._statuts.get(l["id"])
            if s == "lu":
                coul[(r, 6)] = VERT
            elif s == "a_lire":
                coul[(r, 6)] = ORANGE
        _remplir(self.table, [(R.titre_affiche(l), R.auteurs(l), str(l.get("annee") or ""), R.nom_theme(l["theme"]),
                               l.get("niveau", ""), R.NOM_LANGUE.get(l.get("langue"), "")
                               + (" · trad. fr." if l.get("langue") != "fr" and l.get("titre_fr") else ""),
                               R.LIBELLE_STATUT.get(self._statuts.get(l["id"]), ""))
                              for l in self._vues], coul)
        for c, maxi in ((0, 360), (1, 220)):
            if self.table.columnWidth(c) > maxi:
                self.table.setColumnWidth(c, maxi)
        t = R.resume(self._statuts)
        self.etat.setText(f"{len(self._vues)} sur {t['livres']} affiché(s) · {t['en_francais']} lisibles en français · "
                          f"{t['a_lire']} à lire · {t['lus']} lu(s)")
        if garde:
            for r, l in enumerate(self._vues):
                if l["id"] == garde:
                    self.table.selectRow(r)
                    break
        self._detail()

    def _choisi(self):
        return _ligne_choisie(self.table, self._vues)

    def _detail(self):
        l = self._choisi()
        self.lecteur.setHtml(html_livre(l, self._statuts.get(l["id"]) if l else None))
        for b in (self.b_ouvrir, self.b_a_lire, self.b_lu):
            b.setEnabled(l is not None)
        if l:
            s = self._statuts.get(l["id"])
            self.b_ouvrir.setText("Ouvrir le document ↗" if l.get("lien") else "Trouver le livre ↗")
            self.b_a_lire.setText("Retirer de « À lire »" if s == "a_lire" else "★ À lire")
            self.b_lu.setText("Retirer de « Lu »" if s == "lu" else "✓ Lu")

    def _ouvrir(self):
        l = self._choisi()
        if l:
            QDesktopServices.openUrl(QUrl(R.lien(l)))

    def _basculer(self, statut):
        l = self._choisi()
        if l:
            R.definir_statut(l["id"], None if self._statuts.get(l["id"]) == statut else statut)
            self.rafraichir()


# ======================================================================
# Par écran du logiciel
# ======================================================================

class LivresParEcran(_EcranBiblio):

    def __init__(self, athlete_id_initial=None):
        super().__init__("🧭  Par écran du logiciel",
                         "Choisis un écran du menu : les livres qui expliquent ce qu'il calcule ou qui aident à s'en servir.",
                         athlete_id_initial)
        h = QHBoxLayout()
        self.ecran = QComboBox()
        ecrans = []
        for l in R.lire_reference()["livres"]:
            for e in l.get("ecrans", []):
                if e not in ecrans:
                    ecrans.append(e)
        for e in sorted(ecrans, key=R._sans_accents):
            self.ecran.addItem(f"{e} ({len(R.livres_pour_ecran(e))})", e)
        h.addWidget(QLabel("Écran :"))
        h.addWidget(self.ecran)
        h.addStretch()
        self.principal.addLayout(h)
        cadre, lc = _cadre("Livres pour cet écran")
        self.lecteur = _lecteur()
        self.lecteur.setMinimumHeight(460)
        lc.addWidget(self.lecteur, 1)
        self.principal.addWidget(cadre, 1)
        self.ecran.currentIndexChanged.connect(lambda _i: self.rafraichir())
        self._finir()

    def rafraichir(self):
        e = self.ecran.currentData()
        statuts = R.lire_statuts()
        ls = R.livres_pour_ecran(e) if e else []
        if not ls:
            self.lecteur.setHtml("<p style='color:#8A949E'>Aucun livre pour cet écran.</p>")
            return
        self.lecteur.setHtml("<hr>".join(html_livre(l, statuts.get(l["id"])) for l in ls))


class BibliothequeFenetre(ConteneurOnglets):

    def __init__(self, athlete_id_initial=None):
        super().__init__(titre="Bibliothèque trail", onglets=[("📚 Livres", LivresReference),
                                                               ("🧭 Par écran du logiciel", LivresParEcran)],
                         athlete_id_initial=athlete_id_initial)
        self.livres, self.par_ecran = self.ecrans
