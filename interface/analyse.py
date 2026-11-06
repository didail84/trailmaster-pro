"""
Fenêtre « 📊 Analyse » (chantier E) :
  - Prévu ou réel : tes courses avec roadbook et résultat, l'écart, le
    scénario atteint, et un facteur de correction à appliquer (ou non) aux
    temps appris de la Stratégie ;
  - Bilans du club : une ligne par saison (effectif, fidélité, présences,
    résultats), pour l'association et la section choisies ;
  - Bilans des événements : chaque organisation et la comparaison des
    éditions d'une même course.
Aucune requête SQL ici : noyau/donnees/analyse.py.
"""

import html

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QMessageBox

from noyau.analyse import bilans as B
from noyau.donnees import analyse as dan, club as dclub
from interface.conteneur_onglets import ConteneurOnglets
from interface.forme_evolution import _EcranAthlete
from interface.calendrier_competitions import _bouton, _cadre, _table, _style_cases
from interface.organisation_logistique import _remplir, _ouvrir_pdf
from interface import orga_pdf as P

VERT, ORANGE, ROUGE = "#2E7D32", "#E65100", "#C62828"


def _pct(v, signe=False):
    if v is None:
        return ""
    return (f"{v:+g}" if signe else f"{v:g}").replace(".", ",") + " %"


def _ecart(s):
    if s is None:
        return ""
    t = B.texte_duree(abs(s))
    return ("+" if s > 0 else "−") + t


def _e(v):
    return html.escape(str(v if v is not None else ""))


class _EcranAnalyse(_EcranAthlete):

    AVEC_ATHLETE = False

    def __init__(self, titre, sous_titre, athlete_id_initial=None):
        super().__init__(titre, sous_titre, athlete_id_initial)
        if not self.AVEC_ATHLETE:
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
# Prévu ou réel
# ======================================================================

class PrevuReel(_EcranAnalyse):

    AVEC_ATHLETE = True

    def __init__(self, athlete_id_initial=None):
        super().__init__("🎯  Prévu ou réel", "Tes courses qui ont un roadbook (Stratégie) et un résultat le même jour : "
                         "le temps prévu, le temps réel, l'écart et le scénario atteint. L'écart médian peut corriger "
                         "les prochaines estimations « temps appris ».", athlete_id_initial)
        self._lignes, self._syn = [], {}
        h = QHBoxLayout()
        self.c_courses, self.c_mediane, self.c_fourchette, self.c_facteur = (
            self._carte("Courses comparées"), self._carte("Écart médian"), self._carte("Dans la fourchette"),
            self._carte("Correction appliquée"))
        for c in (self.c_courses, self.c_mediane, self.c_fourchette, self.c_facteur):
            h.addWidget(c)
        self.principal.addLayout(h)
        cadre, lc = _cadre("Course par course")
        self.texte = QLabel("")
        self.texte.setWordWrap(True)
        lc.addWidget(self.texte)
        self.table = _table(["Date", "Course", "Méthode", "Prévu", "Réel", "Écart", "Écart %", "Scénario"], 360)
        lc.addWidget(self.table)
        b = QHBoxLayout()
        self.b_appliquer = _bouton("Appliquer le facteur conseillé", True)
        self.b_appliquer.clicked.connect(self._appliquer)
        self.b_enlever = _bouton("Enlever la correction")
        self.b_enlever.clicked.connect(self._enlever)
        b.addWidget(self.b_appliquer)
        b.addWidget(self.b_enlever)
        b.addStretch()
        lc.addLayout(b)
        aide = QLabel("Pour qu'une course apparaisse : un roadbook enregistré à sa date (Stratégie > Roadbook) et son "
                      "résultat saisi (Mes courses). Le facteur ne s'applique qu'à la méthode « temps appris » et reste "
                      "entre 0,85 et 1,2.")
        aide.setObjectName("texteSecondaire")
        aide.setWordWrap(True)
        lc.addWidget(aide)
        self.principal.addWidget(cadre)
        self.principal.addStretch()
        self._finir()

    def rafraichir(self):
        a = self.combo_athlete.currentData()
        if a is None:
            self._lignes, self._syn = [], {"courses": 0, "texte": "Choisis un athlète.", "facteur": None, "applique": None}
        else:
            self._lignes, self._syn = dan.prevu_reel(a)
        s = self._syn
        self.c_courses.valeur.setText(str(s["courses"]))
        med = s.get("mediane")
        self.c_mediane.valeur.setText(_pct(round((med - 1) * 100, 1), True) if med else "—")
        self.c_mediane.detail.setText("plus lent que prévu" if med and med > 1 else "plus rapide que prévu" if med else "")
        self.c_fourchette.valeur.setText(f"{s.get('dans_la_fourchette', 0)}/{s['courses']}" if s["courses"] else "—")
        self.c_fourchette.detail.setText("entre ambitieux et prudent")
        self.c_facteur.valeur.setText(f"× {s['applique']:g}".replace(".", ",") if s.get("applique") else "aucune")
        self.c_facteur.detail.setText(f"conseillé : × {s['facteur']:g}".replace(".", ",") if s.get("facteur") else "")
        self.texte.setText(s["texte"])
        coul = {}
        for r, l in enumerate(self._lignes):
            coul[(r, 5)] = coul[(r, 6)] = ROUGE if l["ecart_pct"] > 5 else VERT if l["ecart_pct"] < -2 else None
            if l["scenario"].startswith("plus"):
                coul[(r, 7)] = ORANGE
        _remplir(self.table, [(P._jour(l["date"]), l["course"], {"temps": "temps visé", "appris": "temps appris", "vo2max": "VO₂max",
                                                       "allure": "allure sur le plat"}.get(l["methode"], l["methode"]),
                               B.texte_duree(l["prevu_s"]), B.texte_duree(l["reel_s"]), _ecart(l["ecart_s"]),
                               _pct(l["ecart_pct"], True), l["scenario"]) for l in self._lignes], coul)
        self.b_appliquer.setEnabled(bool(s.get("facteur")))
        self.b_enlever.setEnabled(bool(s.get("applique")))

    def _appliquer(self):
        a, f = self.combo_athlete.currentData(), self._syn.get("facteur")
        if a is None or not f:
            return
        dan.appliquer_correction(a, f)
        QMessageBox.information(self, "Correction", f"Les prochains temps « appris » de la Stratégie seront multipliés "
                                f"par {f:g}.".replace(".", ",", 1))
        self.rafraichir()

    def _enlever(self):
        a = self.combo_athlete.currentData()
        if a is not None:
            dan.appliquer_correction(a, None)
            self.rafraichir()


# ======================================================================
# Bilans du club
# ======================================================================

class BilansClub(_EcranAnalyse):

    def __init__(self, athlete_id_initial=None):
        super().__init__("🏟️  Bilans du club", "Saison après saison : effectif, nouveaux et fidélité, femmes et hommes, "
                         "jeunes, cotisations, séances et présences, résultats en course. Vraiment parlant après une "
                         "saison complète de données.", athlete_id_initial)
        self._lignes = []
        h = QHBoxLayout()
        self.combo_club, self.combo_section = QComboBox(), QComboBox()
        h.addWidget(QLabel("Association :"))
        h.addWidget(self.combo_club)
        h.addWidget(QLabel("Section :"))
        h.addWidget(self.combo_section)
        h.addStretch()
        self.b_pdf = _bouton("📄 PDF")
        self.b_pdf.clicked.connect(self._pdf)
        h.addWidget(self.b_pdf)
        self.principal.addLayout(h)
        h2 = QHBoxLayout()
        self.c_eff, self.c_fid, self.c_pres, self.c_res = (self._carte("Adhérents"), self._carte("Fidélisation"),
                                                          self._carte("Présence moyenne par séance"),
                                                          self._carte("Résultats en course"))
        for c in (self.c_eff, self.c_fid, self.c_pres, self.c_res):
            h2.addWidget(c)
        self.principal.addLayout(h2)
        cadre, lc = _cadre("Saison par saison")
        self.table = _table(["Saison", "Adhérents", "Nouveaux", "Renouvelés", "Fidélisation", "Partis", "Femmes", "Hommes",
                             "Jeunes", "Cotisations", "Reste dû", "Séances", "Présence moy.", "Résultats", "Courses",
                             "Podiums", "Km en course"], 300)
        lc.addWidget(self.table)
        self.principal.addWidget(cadre)
        self.principal.addStretch()
        self._charger_clubs()
        self.combo_club.currentIndexChanged.connect(self._club_change)
        self.combo_section.currentIndexChanged.connect(lambda _i: self.rafraichir())
        self._finir()

    def _charger_clubs(self):
        self.combo_club.blockSignals(True)
        self.combo_club.clear()
        for c in dclub.clubs():
            self.combo_club.addItem(c["nom"], c["id"])
        cid = dclub.club_courant_id()
        i = self.combo_club.findData(cid)
        if i >= 0:
            self.combo_club.setCurrentIndex(i)
        self.combo_club.blockSignals(False)
        self._sections()

    def _sections(self):
        self.combo_section.blockSignals(True)
        self.combo_section.clear()
        self.combo_section.addItem("Toute l'association", None)
        if self.combo_club.currentData():
            for s in dclub.sections(self.combo_club.currentData()):
                self.combo_section.addItem(s["nom"], s["id"])
        self.combo_section.blockSignals(False)

    def _club_change(self, *_):
        self._sections()
        self.rafraichir()

    def rafraichir(self):
        cid = self.combo_club.currentData()
        self._lignes, evo = dan.bilans_club(cid, self.combo_section.currentData()) if cid else ([], {})
        dern = self._lignes[-1] if self._lignes else None

        def carte(c, cle, fmt=str):
            if not dern:
                c.valeur.setText("—")
                c.detail.setText("Pas encore de données." if not cid else "")
                return
            c.valeur.setText(fmt(dern[cle]) if dern[cle] is not None else "—")
            e = evo.get(cle, [])
            d = e[-1][2] if e else None
            c.detail.setText(f"{dern['saison']}" + (f" · {d:+g} par rapport à la saison d'avant".replace(".", ",")
                                                     if d not in (None, 0) else ""))
        carte(self.c_eff, "adherents")
        carte(self.c_pres, "presence_moyenne", lambda v: f"{v:g}".replace(".", ","))
        carte(self.c_res, "resultats")
        if dern:
            self.c_fid.valeur.setText(_pct(dern["fidelisation"]) or "—")
            self.c_fid.detail.setText(f"{dern['renouveles']} renouvelés, {dern['partis']} partis")
        else:
            self.c_fid.valeur.setText("—")
            self.c_fid.detail.setText("")
        e = lambda v: f"{v:,.0f} €".replace(",", " ")
        _remplir(self.table, [(l["saison"], l["adherents"], l["nouveaux"], l["renouveles"], _pct(l["fidelisation"]),
                               l["partis"], l["femmes"], l["hommes"], l["jeunes"], e(l["cotisations"]), e(l["reste_a_payer"]),
                               l["seances"], "" if l["presence_moyenne"] is None else f"{l['presence_moyenne']:g}".replace(".", ","),
                               l["resultats"], l["courses"], l["podiums"], l["km_course"]) for l in reversed(self._lignes)])

    def _pdf(self):
        if not self._lignes:
            return
        nom = self.combo_club.currentText() + (f" · {self.combo_section.currentText()}" if self.combo_section.currentData() else "")
        _ouvrir_pdf(self, "Bilans du club.pdf", html_bilans_club(nom, self._lignes), True)


# ======================================================================
# Bilans des événements
# ======================================================================

class BilansEvenements(_EcranAnalyse):

    def __init__(self, athlete_id_initial=None):
        super().__init__("🏁  Bilans des événements", "Chaque course organisée : inscrits, partants, finishers, "
                         "abandons, incidents, bénévoles et solde du budget ; puis les éditions d'une même course "
                         "côte à côte (même nom, l'année en moins).", athlete_id_initial)
        self._lignes, self._comp = [], {}
        h = QHBoxLayout()
        h.addStretch()
        self.b_pdf = _bouton("📄 PDF")
        self.b_pdf.clicked.connect(self._pdf)
        h.addWidget(self.b_pdf)
        self.principal.addLayout(h)
        cadre, lc = _cadre("Événements")
        self.table = _table(["Date", "Événement", "Inscrits", "Partants", "Arrivés", "Abandons", "Finishers", "Incidents",
                             "Dont urgents", "Bénévoles", "Recettes", "Dépenses", "Solde"], 280)
        lc.addWidget(self.table)
        self.principal.addWidget(cadre)
        cadre2, lc2 = _cadre("Éditions comparées")
        self.combo_edition = QComboBox()
        self.combo_edition.currentIndexChanged.connect(lambda _i: self._editions())
        lc2.addWidget(self.combo_edition)
        self.table_ed = _table(["Édition", "Inscrits", "Évolution", "Finishers", "Abandons", "Incidents", "Solde",
                                "Recette par coureur"], 200)
        lc2.addWidget(self.table_ed)
        self.vide_ed = QLabel("Les éditions apparaissent ici dès qu'une course a été organisée deux années de suite "
                              "(« Trail des Dentelles 2026 » et « Trail des Dentelles 2027 »).")
        self.vide_ed.setObjectName("texteSecondaire")
        self.vide_ed.setWordWrap(True)
        lc2.addWidget(self.vide_ed)
        self.principal.addWidget(cadre2)
        self.principal.addStretch()
        self._finir()

    def rafraichir(self):
        self._lignes, self._comp = dan.bilans_evenements()
        e = lambda v: f"{v:,.0f} €".replace(",", " ")
        coul = {}
        for r, l in enumerate(self._lignes):
            if l["solde"] < 0:
                coul[(r, 12)] = ROUGE
            if l["graves"]:
                coul[(r, 8)] = ROUGE
        _remplir(self.table, [(P._jour(l["date"]), l["nom"], l["inscrits"], l["partants"], l["arrives"], l["abandons"],
                               _pct(l["taux_finishers"]), l["incidents"], l["graves"], l["benevoles"], e(l["recettes"]),
                               e(l["depenses"]), e(l["solde"])) for l in self._lignes], coul)
        self.combo_edition.blockSignals(True)
        self.combo_edition.clear()
        for k, v in self._comp.items():
            self.combo_edition.addItem(f"{v[-1]['nom']} ({len(v)} éditions)", k)
        self.combo_edition.blockSignals(False)
        self._editions()

    def _editions(self):
        v = self._comp.get(self.combo_edition.currentData(), [])
        self.vide_ed.setVisible(not v)
        self.combo_edition.setVisible(bool(v))
        e = lambda x: f"{x:,.0f} €".replace(",", " ") if x is not None else ""
        lignes, prec = [], None
        for l in v:
            evo = "" if not prec or not prec["inscrits"] else _pct(round(100 * (l["inscrits"] - prec["inscrits"]) / prec["inscrits"]), True)
            lignes.append((f"{str(l['date'])[:4]} · {l['nom']}", l["inscrits"], evo, _pct(l["taux_finishers"]), l["abandons"],
                           l["incidents"], e(l["solde"]), e(l["recette_par_coureur"])))
            prec = l
        _remplir(self.table_ed, lignes)

    def _pdf(self):
        if self._lignes:
            _ouvrir_pdf(self, "Bilans des evenements.pdf", html_bilans_evenements(self._lignes, self._comp), True)


# ---------------------------------------------------------------- PDF

def _doc(titre, sous):
    return (f"<div style='font-family:Helvetica,Arial,sans-serif;color:#111;font-size:9pt'>"
            f"<p style='font-size:16pt;font-weight:bold;margin:0'>{_e(titre)}</p>"
            f"<p style='color:#555;margin:2px 0 10px 0'>{_e(sous)}</p>")


def html_bilans_club(nom, lignes):
    e = lambda v: f"{v:,.0f} €".replace(",", " ")
    t = P._tableau(["Saison", "Adhérents", "Nouveaux", "Fidélisation", "Femmes", "Hommes", "Jeunes", "Cotisations",
                    "Séances", "Présence moy.", "Résultats", "Podiums", "Km en course"],
                   [(_e(l["saison"]), l["adherents"], l["nouveaux"], _pct(l["fidelisation"]), l["femmes"], l["hommes"],
                     l["jeunes"], e(l["cotisations"]), l["seances"],
                     "" if l["presence_moyenne"] is None else f"{l['presence_moyenne']:g}".replace(".", ","),
                     l["resultats"], l["podiums"], l["km_course"]) for l in lignes])
    return _doc("Bilans du club", nom) + t + P._pied()


def html_bilans_evenements(lignes, comp):
    e = lambda v: f"{v:,.0f} €".replace(",", " ") if v is not None else ""
    t = P._tableau(["Date", "Événement", "Inscrits", "Partants", "Arrivés", "Abandons", "Finishers", "Incidents",
                    "Bénévoles", "Solde"],
                   [(P._jour(l["date"]), _e(l["nom"]), l["inscrits"], l["partants"], l["arrives"], l["abandons"],
                     _pct(l["taux_finishers"]), l["incidents"], _e(l["benevoles"]), e(l["solde"])) for l in lignes])
    ed = ""
    for _k, v in comp.items():
        ed += (f"<p style='font-weight:bold;margin:14px 0 4px 0'>{_e(v[-1]['nom'])} : {len(v)} éditions</p>"
               + P._tableau(["Édition", "Inscrits", "Finishers", "Abandons", "Incidents", "Solde"],
                            [(str(l["date"])[:4], l["inscrits"], _pct(l["taux_finishers"]), l["abandons"], l["incidents"],
                              e(l["solde"])) for l in v]))
    return _doc("Bilans des événements", f"{len(lignes)} événement(s)") + t + ed + P._pied()


class AnalyseFenetre(ConteneurOnglets):

    def __init__(self, athlete_id_initial=None):
        super().__init__(titre="Analyse", onglets=[("🎯 Prévu ou réel", PrevuReel), ("🏟️ Bilans du club", BilansClub),
                                                   ("🏁 Bilans des événements", BilansEvenements)],
                         athlete_id_initial=athlete_id_initial)
        self.prevu, self.club, self.evenements = self.ecrans
