"""
Chrono et classements (Trail Hub Center, étape 4.5) — deux onglets de la
fenêtre « 🏁 Organisation » :
  - ⏱️ Chrono : départ réel de chaque épreuve (« top départ »), saisie des
    arrivées au clavier (dossard puis Entrée = l'heure exacte), import d'un
    fichier de chronométrage, contrôle (doublons, dossards inconnus, coureurs
    encore en course) ;
  - 🏆 Classements : scratch, femmes, hommes, par catégorie ; abandons,
    disqualifications, non-partants ; corrections ; export CSV et PDF ;
    publication des résultats sur les profils des licenciés (une seule fois).
Aucune requête SQL ici : tout passe par noyau/donnees/chrono.py.
"""

import html
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QColor, QDesktopServices, QGuiApplication
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QDialog, QFileDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QMessageBox,
    QTableWidgetItem, QVBoxLayout,
)

from noyau.donnees import chrono as dch, organisation as dor
from noyau.organisation import chrono as C
from noyau.club import categories as cat
from noyau.club.profils import texte_temps, lire_temps
from interface.organisation import _EcranOrga, _boutons, VERT, ORANGE, ROUGE, GRIS
from interface.calendrier_competitions import _bouton, _cadre, _table
from interface.ecran_liste import obtenir_style_ecran


def _heure(iso):
    """« 10:42:17.4 » (au dixième)."""
    if not iso:
        return ""
    h = datetime.fromisoformat(iso)
    return h.strftime("%H:%M:%S") + f".{h.microsecond // 100000}"


class ChronoOrga(_EcranOrga):

    def __init__(self, athlete_id_initial=None):
        super().__init__("⏱️  Chrono", "Le jour de la course : donne le départ de chaque épreuve, puis tape le dossard de "
                         "chaque coureur qui arrive et Entrée : l'heure exacte est enregistrée. Un double « top » est "
                         "ignoré ; un dossard inconnu est signalé.", athlete_id_initial)
        cadre, lc = _cadre("Départs")
        self.table_ep = _table(["Épreuve", "Départ prévu", "Départ réel", "Partants", "Arrivés", "Encore en course",
                                "Hors course"], 150)
        lc.addWidget(self.table_ep)
        b = QHBoxLayout()
        for texte, fn, p in (("🔫 Top départ maintenant", self._top_depart, True), ("⌚ Départ à une heure précise",
                                                                                   self._depart_heure, False),
                             ("↩️ Annuler le départ", self._annuler_depart, False)):
            w = _bouton(texte, p)
            w.clicked.connect(fn)
            b.addWidget(w)
        b.addStretch()
        lc.addLayout(b)
        self.principal.addWidget(cadre)
        cadre, lc = _cadre("Arrivées")
        l1 = QHBoxLayout()
        self.horloge = QLabel("")
        self.horloge.setStyleSheet("font-size: 34px; font-weight: 700; font-family: monospace;")
        self.saisie = QLineEdit()
        self.saisie.setPlaceholderText("Dossard puis Entrée")
        self.saisie.setStyleSheet("font-size: 26px; padding: 8px;")
        self.saisie.setMaximumWidth(260)
        self.saisie.returnPressed.connect(self._top_arrivee)
        self.heure_manuelle = QLineEdit()
        self.heure_manuelle.setPlaceholderText("heure à la main (10:42:17), sinon maintenant")
        self.heure_manuelle.setMaximumWidth(300)
        l1.addWidget(self.horloge)
        l1.addSpacing(20)
        l1.addWidget(self.saisie)
        l1.addWidget(self.heure_manuelle)
        l1.addStretch()
        lc.addLayout(l1)
        self.retour = QLabel("")
        self.retour.setWordWrap(True)
        self.retour.setTextFormat(Qt.TextFormat.RichText)
        self.retour.setStyleSheet("font-size: 16px;")
        lc.addWidget(self.retour)
        self.table = _table(["Heure", "Dossard", "Coureur", "Épreuve", "Temps", "Remarque"], 360)
        lc.addWidget(self.table)
        b2 = QHBoxLayout()
        for texte, fn in (("✏️ Corriger le dossard", self._corriger), ("🗑 Annuler le passage", self._annuler_passage),
                          ("📥 Importer un fichier de chrono", self._importer)):
            w = _bouton(texte)
            w.clicked.connect(fn)
            b2.addWidget(w)
        b2.addStretch()
        lc.addLayout(b2)
        self.controle = QLabel("")
        self.controle.setWordWrap(True)
        self.controle.setTextFormat(Qt.TextFormat.RichText)
        lc.addWidget(self.controle)
        self.principal.addWidget(cadre)
        self.principal.addStretch()
        self._eps, self._pass = [], []
        self._minuterie = QTimer(self)
        self._minuterie.timeout.connect(self._tic)
        self._minuterie.start(200)
        self._tic()
        self._finir()

    def _tic(self):
        self.horloge.setText(datetime.now().strftime("%H:%M:%S"))

    def rafraichir(self):
        if not self.evenement_id:
            self.table_ep.setRowCount(0)
            self.table.setRowCount(0)
            return
        et = dch.etat(self.evenement_id)
        self._eps = et["epreuves"]
        t = self.table_ep
        t.setRowCount(len(self._eps))
        for i, e in enumerate(self._eps):
            for j, v in enumerate((e["epreuve"], e["heure_prevue"] or "", _heure(e["depart"]) if e["depart"] else "—",
                                   str(e["partants"]), str(e["arrives"]), str(e["en_course"]), str(e["hors_course"]))):
                it = QTableWidgetItem(v)
                if j == 2 and not e["depart"]:
                    it.setForeground(QColor(ORANGE))
                t.setItem(i, j, it)
        t.resizeColumnsToContents()
        ins = {i["dossard"]: i for i in dor.inscriptions(self.evenement_id) if i.get("dossard")}
        eps = {e["id"]: e for e in dor.epreuves(self.evenement_id)}
        self._pass = list(reversed(dch.passages(self.evenement_id)))
        doublons = {p["id"] for p in et["doublons"]}
        t = self.table
        t.setRowCount(len(self._pass))
        for r, p in enumerate(self._pass):
            i = ins.get(p["dossard"])
            e = eps.get(i["epreuve_id"]) if i else None
            temps = ""
            if e and e.get("depart_reel"):
                s = C.secondes_entre(e["depart_reel"], p["heure"])
                temps = texte_temps(s, True) if s > 0 else "avant le départ !"
            rem = ("dossard inconnu" if p["dossard"] and not i else "sans dossard" if not p["dossard"] else
                   "doublon (déjà arrivé)" if p["id"] in doublons else "départ pas encore donné" if e and not e.get("depart_reel")
                   else "")
            for j, v in enumerate((_heure(p["heure"]), str(p["dossard"] or "?"),
                                   f"{i['prenom'] or ''} {i['nom']}" if i else "", e["nom"] if e else "", temps, rem)):
                it = QTableWidgetItem(v)
                if j == 5 and rem:
                    it.setForeground(QColor(ROUGE if "inconnu" in rem or "avant" in rem else ORANGE))
                t.setItem(r, j, it)
        t.resizeColumnsToContents()
        n_inc, n_db = len(et["inconnus"]), len(et["doublons"])
        en_course = sum(e["en_course"] for e in self._eps)
        self.controle.setText(f"{len(self._pass)} passage(s) · encore en course : <b>{en_course}</b>"
                              + (f" · <span style='color:{ROUGE}'>{n_inc} dossard(s) inconnu(s)</span>" if n_inc else "")
                              + (f" · <span style='color:{ORANGE}'>{n_db} doublon(s)</span>" if n_db else ""))

    def _epreuve(self):
        i = self.table_ep.currentRow()
        if 0 <= i < len(self._eps):
            return self._eps[i]
        if len(self._eps) == 1:
            return self._eps[0]
        QMessageBox.information(self, "Départ", "Choisis l'épreuve dans le tableau des départs.")
        return None

    def _top_depart(self):
        e = self._epreuve()
        if e and (not e["depart"] or QMessageBox.question(self, "Départ", f"Le départ de « {e['epreuve']} » est déjà donné. "
                                                          "Le remplacer ?") == QMessageBox.StandardButton.Yes):
            h = dch.donner_depart(e["epreuve_id"])
            self.retour.setText(f"<b style='color:{VERT}'>Départ {html.escape(e['epreuve'])} : {_heure(h)}</b>")
            self.rafraichir()
            self.saisie.setFocus()

    def _depart_heure(self):
        e = self._epreuve()
        if not e:
            return
        d = QDialog(self)
        d.setWindowTitle("Heure de départ")
        d.setStyleSheet(obtenir_style_ecran())
        lay = QVBoxLayout(d)
        champ = QLineEdit(e["heure_prevue"] + ":00" if e["heure_prevue"] else "")
        champ.setPlaceholderText("08:30:00")
        lay.addWidget(QLabel(f"Départ réel de « {e['epreuve']} » :"))
        lay.addWidget(champ)
        _boutons(d, lay, "Enregistrer")
        if d.exec():
            ev = dor.evenement(self.evenement_id)
            ep = next(x for x in dor.epreuves(self.evenement_id) if x["id"] == e["epreuve_id"])
            h = C.lire_heure(champ.text(), ep.get("date") or ev["date_debut"])
            if not h:
                QMessageBox.warning(self, "Départ", "Heure illisible (écris par exemple 08:30:00).")
                return
            dch.donner_depart(e["epreuve_id"], h)
            self.rafraichir()

    def _annuler_depart(self):
        e = self._epreuve()
        if e and e["depart"] and QMessageBox.question(self, "Départ", f"Annuler le départ de « {e['epreuve']} » ? Les "
                                                      "passages sont gardés.") == QMessageBox.StandardButton.Yes:
            dch.annuler_depart(e["epreuve_id"])
            self.rafraichir()

    def _top_arrivee(self):
        if not self.evenement_id:
            return
        texte = self.saisie.text().strip()
        self.saisie.clear()
        if not texte.isdigit():
            self.retour.setText(f"<span style='color:{ROUGE}'>Tape un numéro de dossard.</span>")
            return
        h = None
        if self.heure_manuelle.text().strip():
            ev = dor.evenement(self.evenement_id)
            h = C.lire_heure(self.heure_manuelle.text(), ev["date_debut"])
            if not h:
                self.retour.setText(f"<span style='color:{ROUGE}'>Heure à la main illisible.</span>")
                return
            self.heure_manuelle.clear()
        r = dch.ajouter_passage(self.evenement_id, int(texte), h)
        i = r["inscrit"]
        txt = f"<b>{texte}</b> · {_heure(r['heure'])}"
        if i:
            txt += f" · {html.escape((i['prenom'] or '') + ' ' + i['nom'])} ({html.escape(i['epreuve'])})"
        if r["avertissement"]:
            txt += f" · <span style='color:{ORANGE}'>{html.escape(r['avertissement'])}</span>"
        self.retour.setText(txt)
        self.rafraichir()

    def _passage(self):
        i = self.table.currentRow()
        return self._pass[i] if 0 <= i < len(self._pass) else None

    def _corriger(self):
        p = self._passage()
        if not p:
            return
        d = QDialog(self)
        d.setWindowTitle("Corriger le passage")
        d.setStyleSheet(obtenir_style_ecran())
        lay = QVBoxLayout(d)
        f = QFormLayout()
        dos = QLineEdit(str(p["dossard"] or ""))
        heure = QLineEdit(_heure(p["heure"]))
        f.addRow("Dossard", dos)
        f.addRow("Heure", heure)
        lay.addLayout(f)
        _boutons(d, lay)
        if d.exec():
            ev = dor.evenement(self.evenement_id)
            h = C.lire_heure(heure.text(), p["heure"][:10] or ev["date_debut"])
            if heure.text().strip() and not h:
                QMessageBox.warning(self, "Passage", "Heure illisible.")
                return
            dch.corriger_passage(p["id"], dos.text().strip() if dos.text().strip().isdigit() or not dos.text().strip()
                                 else None, h)
            self.rafraichir()

    def _annuler_passage(self):
        p = self._passage()
        if p:
            dch.annuler_passage(p["id"])
            self.rafraichir()

    def _importer(self):
        if not self.evenement_id:
            return
        chemin, _ = QFileDialog.getOpenFileName(self, "Fichier de chrono", "", "Tableaux (*.csv *.txt *.xlsx)")
        if not chemin:
            return
        d = QDialog(self)
        d.setWindowTitle("Le fichier contient")
        d.setStyleSheet(obtenir_style_ecran())
        lay = QVBoxLayout(d)
        mode = QComboBox()
        mode.addItem("des heures de passage (10:42:17)", "heure")
        mode.addItem("des temps de course (2:12:10)", "temps")
        lay.addWidget(QLabel("Une ligne par coureur : le dossard, puis"))
        lay.addWidget(mode)
        _boutons(d, lay, "Importer")
        if not d.exec():
            return
        self.importer_fichier(chemin, mode.currentData())

    def importer_fichier(self, chemin, mode="heure", confirmer=True):
        ev = dor.evenement(self.evenement_id)
        lus, erreurs = C.lire_fichier(Path(chemin).read_bytes(), chemin, ev["date_debut"], mode)
        r = dch.importer_fichier(self.evenement_id, lus)
        if confirmer:
            QMessageBox.information(self, "Import", f"{r['passages']} passage(s) et {r['temps']} temps importé(s)."
                                    + (f"\nDossards inconnus : {', '.join(map(str, r['inconnus'][:20]))}" if r["inconnus"]
                                       else "") + ("\n\nÀ revoir :\n" + "\n".join(erreurs[:10]) if erreurs else ""))
        self.rafraichir()
        return r


class ClassementsOrga(_EcranOrga):
    COLONNES = ["Clt", "Dossard", "Nom", "Prénom", "Cat.", "Clt cat.", "Clt sexe", "Club", "Temps", "Écart", "Vitesse",
                "Allure"]

    def __init__(self, athlete_id_initial=None):
        super().__init__("🏆  Classements", "Scratch, femmes, hommes et par catégorie, calculés depuis le départ réel de "
                         "chaque épreuve. Publie-les sur les profils : chaque licencié retrouve sa course, une seule fois.",
                         athlete_id_initial)
        f = QHBoxLayout()
        self.epreuve = QComboBox()
        self.vue = QComboBox()
        for c, l in (("scratch", "Scratch"), ("F", "Femmes"), ("H", "Hommes"), ("categorie", "Par catégorie")):
            self.vue.addItem(l, c)
        self.categorie = QComboBox()
        for w in (QLabel("Épreuve :"), self.epreuve, QLabel("Classement :"), self.vue, self.categorie):
            f.addWidget(w)
        f.addStretch()
        self.principal.addLayout(f)
        b = QHBoxLayout()
        for texte, fn, p in (("🚩 Statut (abandon, DSQ, non partant)", self._statut, False),
                             ("✏️ Corriger le temps", self._corriger, False), ("📤 Export CSV", self._csv, False),
                             ("📄 Classement PDF", self._pdf, False), ("📋 Copier les podiums", self._podiums, False),
                             ("🏅 Publier sur les profils", self._publier, True)):
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
        self.principal.addWidget(self.table)
        self.principal.addStretch()
        self._lignes, self._vues = [], []
        self.epreuve.currentIndexChanged.connect(lambda _i: self._calculer())
        self.vue.currentIndexChanged.connect(lambda _i: self._remplir())
        self.categorie.currentIndexChanged.connect(lambda _i: self._remplir())
        self._finir()

    def rafraichir(self):
        actuel = self.epreuve.currentData()
        self.epreuve.blockSignals(True)
        self.epreuve.clear()
        for e in (dor.epreuves(self.evenement_id) if self.evenement_id else []):
            self.epreuve.addItem(e["nom"], e["id"])
        if actuel is None and self.evenement_id:            # par défaut : l'épreuve qui a le plus d'arrivées
            et = dch.etat(self.evenement_id)["epreuves"]
            if et:
                actuel = max(et, key=lambda x: (x["arrives"], x["partants"]))["epreuve_id"]
        self.epreuve.setCurrentIndex(max(0, self.epreuve.findData(actuel)))
        self.epreuve.blockSignals(False)
        self._calculer()

    def _calculer(self):
        e = self.epreuve.currentData()
        self._lignes = dch.classement(self.evenement_id, e) if self.evenement_id and e else []
        cats = sorted({l["categorie"] for l in self._lignes if l["statut"] == "classe"},
                      key=lambda c: (cat.ORDRE.get(c[:-1], 99), c[-1:]))
        actuel = self.categorie.currentData()
        self.categorie.blockSignals(True)
        self.categorie.clear()
        for c in cats:
            self.categorie.addItem(f"{cat.LIBELLE.get(c[:-1], c)} {'femmes' if c.endswith('F') else 'hommes'} ({c})", c)
        self.categorie.setCurrentIndex(max(0, self.categorie.findData(actuel)))
        self.categorie.blockSignals(False)
        self._remplir()

    def _remplir(self):
        v = self.vue.currentData()
        self.categorie.setVisible(v == "categorie")
        self._vues = (C.filtrer(self._lignes, "sexe", v) if v in ("F", "H") else
                      C.filtrer(self._lignes, "categorie", self.categorie.currentData()) if v == "categorie" else self._lignes)
        t = self.table
        t.setRowCount(len(self._vues))
        for r, l in enumerate(self._vues):
            rang = l["rang_sexe"] if v in ("F", "H") else l["rang_categorie"] if v == "categorie" else l["rang"]
            vals = (str(rang or ""), str(l.get("dossard") or ""), l["nom"], l.get("prenom") or "", l["categorie"],
                    str(l.get("rang_categorie") or ""), str(l.get("rang_sexe") or ""), l.get("club") or "", l["temps"],
                    l.get("ecart") or "", f"{l['vitesse']:.2f}".replace(".", ",") if l.get("vitesse") else "",
                    l.get("allure") or "")
            for j, val in enumerate(vals):
                it = QTableWidgetItem(val)
                if l["statut"] != "classe":
                    it.setForeground(QColor(GRIS))
                elif rang and rang <= 3 and j in (0, 2, 3):
                    it.setForeground(QColor(("#F9A825", "#B0BEC5", "#BF8970")[rang - 1]))
                t.setItem(r, j, it)
        t.resizeColumnsToContents()
        n = sum(1 for l in self._lignes if l["statut"] == "classe")
        hors = {s: sum(1 for l in self._lignes if l["statut"] == s) for s in ("abandon", "disqualifie", "non_partant")}
        self.compte.setText(f"{n} classé(s)" + "".join(f" · {v} {C.ABREGE[k]}" for k, v in hors.items() if v))

    def _selection(self):
        lignes = sorted({x.row() for x in self.table.selectedIndexes()})
        return [self._vues[l] for l in lignes if l < len(self._vues)]

    def _statut(self):
        s = self._selection()
        if not s:
            QMessageBox.information(self, "Statut", "Choisis le ou les coureurs dans le classement. (Un coureur pas encore "
                                    "arrivé se règle depuis l'onglet Inscriptions : il n'apparaît ici qu'arrivé ou avec un "
                                    "statut.)")
            return
        d = QDialog(self)
        d.setWindowTitle("Statut de course")
        d.setStyleSheet(obtenir_style_ecran())
        lay = QVBoxLayout(d)
        combo = QComboBox()
        for c, l in C.STATUTS_COURSE:
            combo.addItem(l + (" (remettre au classement)" if c == "classe" else ""), c)
        lay.addWidget(QLabel(f"{len(s)} coureur(s) :"))
        lay.addWidget(combo)
        _boutons(d, lay, "Appliquer")
        if d.exec():
            dch.definir_statut([l["id"] for l in s], combo.currentData())
            self._calculer()

    def _corriger(self):
        s = self._selection()
        if not s:
            return
        l = s[0]
        d = QDialog(self)
        d.setWindowTitle(f"Temps de {l.get('prenom') or ''} {l['nom']}")
        d.setStyleSheet(obtenir_style_ecran())
        lay = QVBoxLayout(d)
        champ = QLineEdit(l["temps"] if l["statut"] == "classe" else "")
        champ.setPlaceholderText("2:12:10 (vide = temps calculé depuis le passage)")
        lay.addWidget(QLabel("Temps de course retenu (pénalité, erreur de pointage…) :"))
        lay.addWidget(champ)
        _boutons(d, lay)
        if d.exec():
            t = champ.text().strip()
            ts = lire_temps(t) if t else None
            if t and ts is None:
                QMessageBox.warning(self, "Temps", "Temps illisible.")
                return
            dch.corriger_temps(l["id"], ts)
            self._calculer()

    def _nom_epreuve(self):
        return self.epreuve.currentText()

    def _csv(self):
        chemin, _ = QFileDialog.getSaveFileName(self, "Classement", f"Classement {self._nom_epreuve()}.csv", "CSV (*.csv)")
        if chemin:
            Path(chemin).write_text(dch.export_csv(self._lignes, self._nom_epreuve()), encoding="utf-8")
            QMessageBox.information(self, "Export", "Classement exporté (Excel, Numbers, LibreOffice, ou à envoyer à la "
                                    "ligue avec les résultats).")

    def _pdf(self):
        if not self._lignes:
            return
        chemin, _ = QFileDialog.getSaveFileName(self, "Classement PDF", f"Classement {self._nom_epreuve()}.pdf", "PDF (*.pdf)")
        if chemin:
            from interface.club_pdf import rendre_classement
            rendre_classement(chemin, dor.evenement(self.evenement_id), self._nom_epreuve(), self._lignes)
            QDesktopServices.openUrl(QUrl.fromLocalFile(chemin))

    def texte_podiums(self):
        p = C.podiums(self._lignes)
        fmt = lambda ls: ", ".join(f"{k}. {l.get('prenom') or ''} {l['nom']} ({l['temps']})" for k, l in enumerate(ls, 1))
        ev = dor.evenement(self.evenement_id) or {}
        l = [f"{ev.get('nom', '')} — {self._nom_epreuve()}", f"Scratch : {fmt(p['scratch'])}"]
        if p["F"]:
            l.append(f"Femmes : {fmt(p['F'])}")
        if p["H"]:
            l.append(f"Hommes : {fmt(p['H'])}")
        for c, ls in p["categories"].items():
            l.append(f"{c} : {fmt(ls)}")
        return "\n".join(l)

    def _podiums(self):
        QGuiApplication.clipboard().setText(self.texte_podiums())
        QMessageBox.information(self, "Podiums", "Podiums copiés : colle-les dans ton message, sur le site ou au micro.")

    def _publier(self):
        if not self.evenement_id:
            return
        r = dch.publier_sur_profils(self.evenement_id)
        QMessageBox.information(self, "Profils", f"{r['publies']} résultat(s) ajouté(s) aux profils, {r['mis_a_jour']} mis à "
                                f"jour (déjà publiés). {r['sans_profil']} participant(s) sans fiche dans Trail Hub.\n\nLes "
                                "licenciés qui ont un profil coureur retrouvent aussi la course dans leurs résultats.")
