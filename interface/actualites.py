"""
Fenêtre « 📰 Actualités du trail » (chantier F) :
  - Fil d'actualités : les articles des flux France et monde (titre, date,
    court extrait, lien vers le site), filtres, favoris, lus ;
  - Coureurs connus : français et étrangers, palmarès vérifié avec ses
    sources, coureurs suivis et les articles qui les citent ;
  - Flux : ceux livrés et les tiens, pause, relecture.
Aucune requête SQL ici : noyau/donnees/actualites.py. Le réseau ne passe
jamais par l'écran : les flux sont lus dans des fils de travail.
"""

import html
from datetime import datetime

from PySide6.QtCore import QObject, QRunnable, QThreadPool, QUrl, Signal, Qt
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QCheckBox, QComboBox, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QSplitter, QTextBrowser

from noyau.actualites import regles as R
from noyau.donnees import actualites as dac
from interface.conteneur_onglets import ConteneurOnglets
from interface.forme_evolution import _EcranAthlete
from interface.calendrier_competitions import _bouton, _cadre, _table, _style_cases
from interface.organisation_logistique import DialogueChamps, _remplir, _ligne_choisie

GRIS, ORANGE, VERT = "#8A949E", "#E65100", "#2E7D32"


def _e(v):
    return html.escape(str(v if v is not None else ""))


def _quand(d):
    if not d:
        return ""
    try:
        x = datetime.fromisoformat(str(d)[:19])
    except ValueError:
        return str(d)[:10]
    jours = (datetime.now() - x).days
    return "aujourd'hui" if jours <= 0 else "hier" if jours == 1 else x.strftime("%d/%m/%Y")


def _lecteur():
    """Zone de lecture : liens lisibles sur le thème sombre comme sur le clair, ouverts dans le navigateur."""
    t = QTextBrowser()
    t.setOpenExternalLinks(True)
    t.document().setDefaultStyleSheet("a { color: #4FA3E0; text-decoration: none; } h3 { font-size: 15px; }")
    return t


def _jour(d):
    try:
        return datetime.fromisoformat(str(d)[:10]).strftime("%d/%m/%Y")
    except ValueError:
        return str(d or "")


class _Signaux(QObject):
    fini = Signal(int, object, object)


class _Lecture(QRunnable):
    def __init__(self, source_id, url):
        super().__init__()
        self.source_id, self.url = source_id, url
        self.signaux = _Signaux()

    def run(self):
        try:
            self.signaux.fini.emit(self.source_id, dac.telecharger(self.url), None)
        except Exception as e:                   # réseau, robots.txt : le message est gardé sur le flux
            self.signaux.fini.emit(self.source_id, None, f"lecture impossible : {e}")


class _EcranActu(_EcranAthlete):

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

    def _fenetre(self):
        w = self.window()
        return w if isinstance(w, ActualitesFenetre) else None

    def showEvent(self, ev):
        super().showEvent(ev)
        if getattr(self, "_vu", False):
            self.actualiser()
        self._vu = True


def _html_article(a):
    if not a:
        return "<p style='color:#8A949E'>Choisis un article.</p>"
    cites = (f"<p>🏃 {_e(', '.join(a['coureurs']))}</p>" if a.get("coureurs") else "")
    return (f"<h3 style='margin:0 0 4px 0'>{_e(a['titre'])}</h3>"
            f"<p style='color:#8A949E;margin:0 0 8px 0'>{_e(a['source'] or 'Flux supprimé')} · {_e(_quand(a['date']))}</p>"
            f"<p>{_e(a['extrait']) or '<i>Pas d’extrait.</i>'}</p>{cites}"
            f"<p><a href='{_e(a['lien'])}'>Lire l'article sur le site ↗</a></p>")


# ======================================================================
# Fil d'actualités
# ======================================================================

class FilActualites(_EcranActu):

    def __init__(self, athlete_id_initial=None):
        super().__init__("📰  Fil d'actualités", "Les dernières nouvelles du trail en France et dans le monde, lues dans "
                         "les flux publiés par les sites. Seuls le titre, la date et un court extrait sont gardés : "
                         "l'article complet s'ouvre sur le site.", athlete_id_initial)
        self._arts = []
        h = QHBoxLayout()
        self.zone, self.source, self.coureur = QComboBox(), QComboBox(), QComboBox()
        self.zone.addItem("France et monde", None)
        for c, l in R.ZONES:
            self.zone.addItem(l, c)
        self.recherche = QLineEdit()
        self.recherche.setPlaceholderText("Chercher (course, coureur…)")
        self.trail = QCheckBox("Trail seulement")
        self.trail.setChecked(True)
        self.non_lus = QCheckBox("Non lus")
        self.favoris = QCheckBox("Favoris")
        for w in (self.zone, self.source, self.coureur, self.recherche, self.trail, self.non_lus, self.favoris):
            h.addWidget(w)
        h.addStretch()
        self.principal.addLayout(h)
        h2 = QHBoxLayout()
        self.etat = QLabel("")
        self.etat.setObjectName("texteSecondaire")
        h2.addWidget(self.etat, 1)
        self.b_relire = _bouton("🔄 Relire les flux", True)
        self.b_relire.clicked.connect(lambda: self._fenetre() and self._fenetre().lancer_lectures(toutes=True))
        self.b_lu = _bouton("Tout marquer lu")
        self.b_lu.clicked.connect(self._tout_lu)
        h2.addWidget(self.b_relire)
        h2.addWidget(self.b_lu)
        self.principal.addLayout(h2)
        cadre, lc = _cadre("Articles")
        sp = QSplitter(Qt.Orientation.Horizontal)
        self.table = _table(["Date", "Source", "Titre", "Coureurs"], 460)
        self.table.itemSelectionChanged.connect(self._detail)
        self.table.doubleClicked.connect(lambda _i: self._ouvrir())
        sp.addWidget(self.table)
        self.lecteur = _lecteur()
        self.lecteur.setOpenExternalLinks(True)
        self.lecteur.setMinimumWidth(320)
        sp.addWidget(self.lecteur)
        sp.setSizes([760, 420])
        lc.addWidget(sp, 1)
        b = QHBoxLayout()
        self.b_ouvrir = _bouton("Ouvrir l'article ↗", True)
        self.b_ouvrir.clicked.connect(self._ouvrir)
        self.b_fav = _bouton("☆ Favori")
        self.b_fav.clicked.connect(self._favori)
        self.b_masquer = _bouton("Masquer")
        self.b_masquer.clicked.connect(self._masquer)
        for w in (self.b_ouvrir, self.b_fav, self.b_masquer):
            b.addWidget(w)
        b.addStretch()
        lc.addLayout(b)
        self.principal.addWidget(cadre, 1)
        self._listes()
        for w in (self.zone, self.source, self.coureur):
            w.currentIndexChanged.connect(lambda _i: self.rafraichir())
        for w in (self.trail, self.non_lus, self.favoris):
            w.toggled.connect(lambda _b: self.rafraichir())
        self.recherche.textChanged.connect(lambda _t: self.rafraichir())
        self._finir()

    def _listes(self):
        for combo, items, tout in ((self.source, [(s["nom"], s["id"]) for s in dac.sources()], "Tous les flux"),
                                   (self.coureur, [("★ Coureurs suivis", "suivis")]
                                    + [(c["nom_complet"], c["id"]) for c in dac.coureurs()], "Tous les coureurs")):
            garde = combo.currentData()
            combo.blockSignals(True)
            combo.clear()
            combo.addItem(tout, None)
            for l, v in items:
                combo.addItem(l, v)
            i = combo.findData(garde)
            combo.setCurrentIndex(max(0, i))
            combo.blockSignals(False)

    def rafraichir(self):
        c = self.coureur.currentData()
        self._arts = dac.articles(zone=self.zone.currentData(), source_id=self.source.currentData(),
                                  coureur_id=c if isinstance(c, int) else None, suivis=c == "suivis",
                                  recherche=self.recherche.text().strip() or None, non_lus=self.non_lus.isChecked(),
                                  favoris=self.favoris.isChecked(), trail_seulement=self.trail.isChecked())
        coul = {}
        for r, a in enumerate(self._arts):
            if a["lu"]:
                coul[(r, 2)] = GRIS
        _remplir(self.table, [(_quand(a["date"]), a["source"] or "", ("★ " if a["favori"] else "") + a["titre"],
                               ", ".join(a["coureurs"])) for a in self._arts], coul)
        if self.table.columnWidth(2) > 520:
            self.table.setColumnWidth(2, 520)
        t = dac.tableau(0)
        self.etat.setText(f"{len(self._arts)} article(s) affiché(s) · {t['non_lus']} non lu(s) · {t['sources']} flux actifs"
                          + (" · aucun article : clique sur « Relire les flux » (connexion Internet nécessaire)."
                             if not t["derniers"] and not self._arts else ""))
        self._detail()

    def _choisi(self):
        return _ligne_choisie(self.table, self._arts)

    def _detail(self):
        a = self._choisi()
        self.lecteur.setHtml(_html_article(a))
        for b in (self.b_ouvrir, self.b_fav, self.b_masquer):
            b.setEnabled(a is not None)
        if a:
            self.b_fav.setText("★ Retirer des favoris" if a["favori"] else "☆ Favori")
            if not a["lu"]:
                dac.marquer_lu(a["id"])
                a["lu"] = 1

    def _ouvrir(self):
        a = self._choisi()
        if a:
            QDesktopServices.openUrl(QUrl(a["lien"]))

    def _favori(self):
        a = self._choisi()
        if a:
            dac.definir_favori(a["id"], not a["favori"])
            self.rafraichir()

    def _masquer(self):
        a = self._choisi()
        if a:
            dac.masquer(a["id"])
            self.rafraichir()

    def _tout_lu(self):
        dac.tout_marquer_lu()
        self.rafraichir()


# ======================================================================
# Coureurs connus
# ======================================================================

def _html_coureur(c, arts):
    if not c:
        return "<p style='color:#8A949E'>Choisis un coureur.</p>"
    palm = "".join(f"<li>{_e(p)}</li>" for p in c["palmares"]) or "<li><i>Pas de palmarès saisi.</i></li>"
    src = " · ".join(f"<a href='{_e(s)}'>{_e(s.split('/')[2])}</a>" for s in c["sources"] if s.count("/") >= 2)
    a = "".join(f"<li><a href='{_e(x['lien'])}'>{_e(x['titre'])}</a> <span style='color:#8A949E'>"
                f"({_e(x['source'] or '')}, {_e(_quand(x['date']))})</span></li>" for x in arts[:15])
    return (f"<h3 style='margin:0'>{_e(c['nom_complet'])} {'★' if c['suivi'] else ''}</h3>"
            f"<p style='color:#8A949E;margin:2px 0 8px 0'>{_e(c['pays_nom'])}"
            f"{' · palmarès vérifié le ' + _jour(c['verifie_le']) if c.get('verifie_le') and not c['modifie'] else ''}"
            f"{' · fiche corrigée par toi' if c['modifie'] else ''}</p>"
            f"<p><b>Palmarès</b></p><ul>{palm}</ul>"
            + (f"<p style='color:#8A949E'>Sources : {src}</p>" if src else "")
            + (f"<p>{_e(c['mes_notes'])}</p>" if c.get("mes_notes") else "")
            + f"<p><b>Dans l'actualité</b></p>" + (f"<ul>{a}</ul>" if a else "<p style='color:#8A949E'>Aucun article reçu "
                                                    "ne le cite pour l'instant.</p>"))


class CoureursConnus(_EcranActu):

    def __init__(self, athlete_id_initial=None):
        super().__init__("🏃  Coureurs connus", "Les grands noms du trail, français et étrangers, avec un palmarès vérifié "
                         "sur les sources indiquées (sans photo). Suis ceux qui t'intéressent : leurs articles "
                         "apparaissent dans le fil (« Coureurs suivis »).", athlete_id_initial)
        self._cs = []
        h = QHBoxLayout()
        self.pays = QComboBox()
        for l, v in (("Tous", None), ("Français", "FRA"), ("Étrangers", "etranger")):
            self.pays.addItem(l, v)
        self.suivis = QCheckBox("Suivis seulement")
        h.addWidget(self.pays)
        h.addWidget(self.suivis)
        h.addStretch()
        self.principal.addLayout(h)
        cadre, lc = _cadre("Coureurs")
        sp = QSplitter(Qt.Orientation.Horizontal)
        self.table = _table(["", "Coureur", "Pays", "Articles"], 460)
        self.table.itemSelectionChanged.connect(self._detail)
        self.table.doubleClicked.connect(lambda _i: self._modifier())
        sp.addWidget(self.table)
        self.fiche = _lecteur()
        self.fiche.setOpenExternalLinks(True)
        self.fiche.setMinimumWidth(380)
        sp.addWidget(self.fiche)
        sp.setSizes([520, 660])
        lc.addWidget(sp, 1)
        b = QHBoxLayout()
        self.b_suivre = _bouton("★ Suivre", True)
        self.b_suivre.clicked.connect(self._suivre)
        bn, bm, bs = _bouton("➕ Ajouter un coureur"), _bouton("Modifier"), _bouton("Supprimer")
        bn.clicked.connect(lambda: self._modifier(nouveau=True))
        bm.clicked.connect(self._modifier)
        bs.clicked.connect(self._supprimer)
        for w in (self.b_suivre, bn, bm, bs):
            b.addWidget(w)
        b.addStretch()
        lc.addLayout(b)
        self.principal.addWidget(cadre, 1)
        self.pays.currentIndexChanged.connect(lambda _i: self.rafraichir())
        self.suivis.toggled.connect(lambda _b: self.rafraichir())
        self._finir()

    def rafraichir(self):
        self._cs = dac.coureurs(pays=self.pays.currentData(), suivis=self.suivis.isChecked())
        _remplir(self.table, [("★" if c["suivi"] else "", c["nom_complet"], c["pays_nom"], c["nb_articles"] or "")
                              for c in self._cs])
        self._detail()

    def _choisi(self):
        return _ligne_choisie(self.table, self._cs)

    def _detail(self):
        c = self._choisi()
        self.fiche.setHtml(_html_coureur(c, dac.articles(coureur_id=c["id"]) if c else []))
        self.b_suivre.setEnabled(c is not None)
        if c:
            self.b_suivre.setText("Ne plus suivre" if c["suivi"] else "★ Suivre")

    def _suivre(self):
        c = self._choisi()
        if c:
            r = self.table.currentRow()
            dac.suivre(c["id"], not c["suivi"])
            self.rafraichir()
            self.table.selectRow(r)

    def _modifier(self, nouveau=False):
        c = None if nouveau else self._choisi()
        if not nouveau and not c:
            return
        spec = [("texte", "prenom", "Prénom", None), ("texte", "nom", "Nom", None),
                ("texte", "pays", "Pays (code à 3 lettres)", {"aide": "FRA, ESP, USA…"}),
                ("choix", "sexe", "Sexe", {"choix": [(None, "—"), ("F", "Femme"), ("H", "Homme")]}),
                ("long", "palmares", "Palmarès (une ligne par résultat)", {"hauteur": 110}),
                ("long", "sources", "Sources (une adresse par ligne)", {"hauteur": 60}),
                ("long", "alias", "Autres graphies du nom (une par ligne)", {"hauteur": 50}),
                ("long", "mes_notes", "Mes notes", None)]
        v = dict(c) if c else {}
        for k in ("palmares", "sources", "alias"):
            v[k] = "\n".join(v.get(k) or [])
        d = DialogueChamps(self, "Coureur", spec, v, lambda ch: dac.enregistrer_coureur(ch, c["id"] if c else None),
                           largeur=620)
        if d.exec():
            self.rafraichir()

    def _supprimer(self):
        c = self._choisi()
        if c and QMessageBox.question(self, "Coureur", f"Supprimer la fiche de {c['nom_complet']} ? "
                                      "(une fiche livrée avec Trail Hub ne reviendra pas)") == QMessageBox.StandardButton.Yes:
            dac.supprimer_coureur(c["id"])
            self.rafraichir()


# ======================================================================
# Flux
# ======================================================================

class SourcesActualites(_EcranActu):

    def __init__(self, athlete_id_initial=None):
        super().__init__("📡  Flux d'actualités", "Les flux RSS lus toutes les 6 heures quand la fenêtre est ouverte. "
                         "Le fichier robots.txt de chaque site est respecté : un site qui refuse la lecture automatique "
                         "met son flux en pause. Ajoute l'adresse du flux d'un site que tu aimes (souvent …/feed/).",
                         athlete_id_initial)
        self._ss = []
        cadre, lc = _cadre("Flux")
        self.table = _table(["Flux", "Zone", "Langue", "Adresse", "Dernière lecture", "Articles", "État"], 360)
        self.table.doubleClicked.connect(lambda _i: self._modifier())
        lc.addWidget(self.table)
        b = QHBoxLayout()
        bn, bm, bp, br, bs = (_bouton("➕ Ajouter un flux", True), _bouton("Modifier"), _bouton("Pause / reprendre"),
                              _bouton("Relire ce flux"), _bouton("Supprimer"))
        bn.clicked.connect(lambda: self._modifier(nouveau=True))
        bm.clicked.connect(self._modifier)
        bp.clicked.connect(self._pause)
        br.clicked.connect(self._relire)
        bs.clicked.connect(self._supprimer)
        for w in (bn, bm, bp, br, bs):
            b.addWidget(w)
        b.addStretch()
        lc.addLayout(b)
        self.principal.addWidget(cadre)
        self.principal.addStretch()
        self._finir()

    def rafraichir(self):
        self._ss = dac.sources()
        f = self._fenetre()
        en_cours = f._en_cours if f else set()
        coul = {}
        for r, s in enumerate(self._ss):
            if s["erreur"]:
                coul[(r, 6)] = ORANGE
        _remplir(self.table, [(s["nom"], R.LIBELLE_ZONE.get(s["zone"], s["zone"]), (s["langue"] or "").upper(), s["url"],
                               (s["derniere_maj"] or "").replace("T", " ")[:16], s["nb_articles"] or 0,
                               "lecture…" if s["id"] in en_cours else ("⚠️ " + s["erreur"]) if s["erreur"]
                               else "en pause" if not s["actif"] else "ok") for s in self._ss], coul)
        if self.table.columnWidth(3) > 320:
            self.table.setColumnWidth(3, 320)

    def _choisi(self):
        return _ligne_choisie(self.table, self._ss)

    def _modifier(self, nouveau=False):
        s = None if nouveau else self._choisi()
        if not nouveau and not s:
            return
        spec = [("texte", "nom", "Nom", None), ("texte", "url", "Adresse du flux", {"aide": "https://…/feed/"}),
                ("texte", "site", "Site", None),
                ("choix", "zone", "Zone", {"choix": list(R.ZONES)}),
                ("choix", "langue", "Langue", {"choix": [("fr", "Français"), ("en", "Anglais"), ("es", "Espagnol"),
                                                         ("it", "Italien")]})]
        d = DialogueChamps(self, "Flux", spec, dict(s) if s else {"zone": "france", "langue": "fr"},
                           lambda ch: dac.enregistrer_source({**ch, "actif": s["actif"] if s else True},
                                                             s["id"] if s else None))
        if d.exec():
            self.rafraichir()
            f = self._fenetre()
            if f and d.resultat:
                f.lancer_lectures(ids=[d.resultat])

    def _pause(self):
        s = self._choisi()
        if s:
            dac.activer_source(s["id"], not s["actif"])
            self.rafraichir()

    def _relire(self):
        s, f = self._choisi(), self._fenetre()
        if s and f:
            f.lancer_lectures(ids=[s["id"]])

    def _supprimer(self):
        s = self._choisi()
        if s and QMessageBox.question(self, "Flux", f"Supprimer le flux « {s['nom']} » et ses articles (tes favoris "
                                      "sont gardés) ?") == QMessageBox.StandardButton.Yes:
            dac.supprimer_source(s["id"])
            self.rafraichir()


class ActualitesFenetre(ConteneurOnglets):

    def __init__(self, athlete_id_initial=None, lecture_auto=True):
        self._en_cours = set()
        super().__init__(titre="Actualités du trail", onglets=[("📰 Fil d'actualités", FilActualites),
                                                                ("🏃 Coureurs connus", CoureursConnus),
                                                                ("📡 Flux", SourcesActualites)],
                         athlete_id_initial=athlete_id_initial)
        self.fil, self.coureurs, self.flux = self.ecrans
        if lecture_auto:
            self.lancer_lectures()

    def lancer_lectures(self, toutes=False, ids=None):
        """Relit en tâche de fond les flux à relire (ou tous, ou ceux donnés)."""
        if ids:
            liste = [s for s in (dac.source(i) for i in ids) if s]
        elif toutes:
            liste = [s for s in dac.sources() if s["actif"]]
        else:
            liste = dac.a_relire()
        n = 0
        for s in liste:
            if s["id"] in self._en_cours:
                continue
            self._en_cours.add(s["id"])
            t = _Lecture(s["id"], s["url"])
            t.signaux.fini.connect(self._lu)
            QThreadPool.globalInstance().start(t)
            n += 1
        if n:
            self.fil.etat.setText(f"Lecture de {n} flux…")
            self.flux.rafraichir()
        return n

    def _lu(self, source_id, contenu, erreur):
        from shiboken6 import isValid
        if not isValid(self):
            return
        self._en_cours.discard(source_id)
        dac.appliquer_flux(source_id, contenu, erreur)
        if not self._en_cours:
            self.fil._listes()
            self.fil.rafraichir()
            self.coureurs.rafraichir()
        self.flux.rafraichir()
