"""
Profils des licenciés, séances partagées et entraîneurs (Trail Hub Center,
étape 4.3) — trois onglets de la fenêtre « 🏟️ Club » :
  - 🏅 Licenciés : la fiche de chaque adhérent (catégorie, groupes,
    présences, bilan de saison, records, index ITRA / UTMB / Betrail,
    résultats), import du classement d'une course extérieure ;
  - 📚 Séances : la bibliothèque de séances du club (texte de l'entraîneur
    ou fractionné de la bibliothèque), programmée pour un groupe et envoyée
    dans la planification des coureurs ;
  - 🧑‍🏫 Entraîneurs : groupes et séances encadrés, diplômes et échéances.
Aucune requête SQL ici : tout passe par noyau/donnees/profils.py.
"""

import html
from datetime import date, timedelta
from pathlib import Path

from PySide6.QtCore import Qt, QDate
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QComboBox, QDialog, QDoubleSpinBox, QFileDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QMessageBox, QPlainTextEdit, QSpinBox, QTableWidgetItem, QVBoxLayout, QWidget,
)

from noyau.donnees import profils as dpro, club as dclub, personnes as dper, agenda_club as dag
from noyau.club import profils as P, categories as cat, agenda as ag
from interface.club import _EcranClub, _bouton, _cadre, _table, VERT, ORANGE, ROUGE, GRIS
from interface.club_agenda import _champ_date, _combo_groupe, _combo_entraineur, _boutons_dialogue, _date_courte, _horaire
from interface.ecran_liste import obtenir_style_ecran

ORGANISMES_INDEX = ("ITRA", "UTMB Index", "Betrail", "Autre")


def _jour(iso):
    return date.fromisoformat(str(iso)[:10]).strftime("%d/%m/%Y") if iso else ""


def _texte_classement(r):
    m = []
    if r.get("classement_general"):
        m.append(f"{r['classement_general']}e" + (f"/{r['nb_classes']}" if r.get("nb_classes") else ""))
    if r.get("classement_sexe"):
        m.append(f"{r['classement_sexe']}e sexe")
    if r.get("classement_categorie"):
        m.append(f"{r['classement_categorie']}e {r.get('categorie') or 'cat.'}")
    return " · ".join(m)


# ======================================================================
# Dialogues
# ======================================================================

class DialogueResultat(QDialog):

    def __init__(self, parent, personne_id, resultat=None):
        super().__init__(parent)
        self.personne_id, r = personne_id, resultat or {}
        self.resultat_id = r.get("id")
        self.setWindowTitle("Résultat")
        self.setStyleSheet(obtenir_style_ecran())
        self.resize(520, 520)
        lay = QVBoxLayout(self)
        f = QFormLayout()
        self.course, self.epreuve, self.commune = (QLineEdit(r.get("course") or ""), QLineEdit(r.get("epreuve") or ""),
                                                   QLineEdit(r.get("commune") or ""))
        self.jour = _champ_date(r.get("date"))
        self.distance = QDoubleSpinBox()
        self.distance.setRange(0, 400)
        self.distance.setDecimals(2)
        self.distance.setSuffix(" km")
        self.distance.setValue(r.get("distance_km") or 0)
        self.dplus = QSpinBox()
        self.dplus.setRange(0, 30000)
        self.dplus.setSuffix(" m D+")
        self.dplus.setValue(r.get("denivele_m") or 0)
        self.temps = QLineEdit(P.texte_temps(r["temps_s"]) if r.get("temps_s") else "")
        self.temps.setPlaceholderText("1:52:10, 38'40, 2h05")
        self.statut = QComboBox()
        for c, l in P.STATUTS_RESULTAT:
            self.statut.addItem(l, c)
        self.statut.setCurrentIndex(max(0, self.statut.findData(r.get("statut") or "classe")))
        self.rangs = {}
        for k in ("classement_general", "nb_classes", "classement_sexe", "classement_categorie"):
            s = QSpinBox()
            s.setRange(0, 100000)
            s.setSpecialValueText("—")
            s.setValue(r.get(k) or 0)
            self.rangs[k] = s
        self.categorie = QLineEdit(r.get("categorie") or "")
        self.notes = QLineEdit(r.get("notes") or "")
        for lib, w in (("Course", self.course), ("Épreuve", self.epreuve), ("Date", self.jour), ("Commune", self.commune),
                       ("Distance", self.distance), ("Dénivelé", self.dplus), ("Temps", self.temps), ("Statut", self.statut),
                       ("Classement", self.rangs["classement_general"]), ("sur (classés)", self.rangs["nb_classes"]),
                       ("Classement sexe", self.rangs["classement_sexe"]),
                       ("Classement catégorie", self.rangs["classement_categorie"]), ("Catégorie", self.categorie),
                       ("Notes", self.notes)):
            f.addRow(lib, w)
        lay.addLayout(f)
        _boutons_dialogue(self, lay)

    def accept(self):
        t = self.temps.text().strip()
        ts = P.lire_temps(t) if t else None
        if t and ts is None:
            QMessageBox.warning(self, "Résultat", f"Temps illisible : {t} (écris par exemple 1:52:10).")
            return
        v = {"course": self.course.text(), "epreuve": self.epreuve.text().strip() or None,
             "date": self.jour.date().toString("yyyy-MM-dd"), "commune": self.commune.text().strip() or None,
             "distance_km": self.distance.value() or None, "denivele_m": self.dplus.value() or None, "temps_s": ts,
             "statut": self.statut.currentData(), "categorie": self.categorie.text().strip() or None,
             "notes": self.notes.text().strip() or None, "source": "Saisie",
             **{k: s.value() or None for k, s in self.rangs.items()}}
        try:
            dpro.enregistrer_resultat(self.personne_id, v, self.resultat_id)
        except dpro.ErreurProfil as e:
            QMessageBox.warning(self, "Résultat", str(e))
            return
        super().accept()


class DialogueImportClassement(QDialog):
    """Le classement d'une course extérieure : fichier ou tableau collé ; les adhérents sont retrouvés par leur nom."""

    def __init__(self, parent, club_id, saison):
        super().__init__(parent)
        self.club_id, self.saison = club_id, saison
        self.setWindowTitle("Importer le classement d'une course")
        self.setStyleSheet(obtenir_style_ecran())
        self.resize(820, 700)
        lay = QVBoxLayout(self)
        f = QFormLayout()
        self.course, self.epreuve, self.commune = QLineEdit(), QLineEdit(), QLineEdit()
        self.course.setPlaceholderText("ex. Trail des Collines de Mazan")
        self.epreuve.setPlaceholderText("ex. 25 km")
        self.jour = _champ_date()
        self.distance = QDoubleSpinBox()
        self.distance.setRange(0, 400)
        self.distance.setDecimals(2)
        self.distance.setSuffix(" km")
        self.dplus = QSpinBox()
        self.dplus.setRange(0, 30000)
        self.dplus.setSuffix(" m D+")
        for lib, w in (("Course", self.course), ("Épreuve", self.epreuve), ("Date", self.jour), ("Commune", self.commune),
                       ("Distance", self.distance), ("Dénivelé", self.dplus)):
            f.addRow(lib, w)
        lay.addLayout(f)
        self.texte = QPlainTextEdit()
        self.texte.setPlaceholderText("Colle ici le classement copié depuis le site des résultats (avec la ligne des titres : "
                                      "Clt, Nom, Prénom, Temps, Cat…), ou choisis un fichier.")
        lay.addWidget(self.texte, 1)
        b = QHBoxLayout()
        fichier = _bouton("📂 Choisir un fichier")
        fichier.clicked.connect(self._fichier)
        apercu = _bouton("👀 Qui est du club ?")
        apercu.clicked.connect(self._apercu)
        b.addWidget(fichier)
        b.addWidget(apercu)
        b.addStretch()
        lay.addLayout(b)
        self.label = QLabel("")
        self.label.setWordWrap(True)
        self.label.setTextFormat(Qt.TextFormat.RichText)
        lay.addWidget(self.label)
        self._contenu, self._nom = None, ""
        _boutons_dialogue(self, lay, "Importer")

    def _fichier(self):
        chemin, _ = QFileDialog.getOpenFileName(self, "Classement", "", "Tableaux (*.csv *.txt *.xlsx)")
        if chemin:
            self._contenu, self._nom = Path(chemin).read_bytes(), chemin
            self.texte.setPlainText(f"(fichier {Path(chemin).name})")
            self._apercu()

    def lignes(self):
        if self._contenu is not None:
            return P.lire_classement(self._contenu, self._nom)
        return P.lire_classement(self.texte.toPlainText())

    def _apercu(self):
        try:
            lignes, n = self.lignes()
        except ValueError as e:
            self.label.setText(html.escape(str(e)))
            return
        adh = [a for a in dclub.adhesions(self.club_id, self.saison) if a["statut"] != "annulee"]
        paires = P.associer(lignes, adh)
        self.label.setText(f"<b>{len(lignes)} ligne(s), {n} classé(s).</b> Adhérents retrouvés : {len(paires)}"
                           + ("<ul>" + "".join(f"<li>{html.escape(a['prenom'])} {html.escape(a['nom'])} — "
                                               f"{l['rang'] or P.LIBELLE_STATUT_RESULTAT[l['statut']]}"
                                               f"{('e en ' + P.texte_temps(l['temps_s'])) if l['temps_s'] else ''}</li>"
                                               for l, a in paires[:20]) + "</ul>" if paires else
                              "<br>Aucun adhérent retrouvé (nom et prénom identiques à la fiche du club)."))

    def accept(self):
        if not self.course.text().strip():
            QMessageBox.warning(self, "Classement", "Donne le nom de la course.")
            return
        lignes, n = self.lignes()
        course = {"course": self.course.text().strip(), "epreuve": self.epreuve.text().strip() or None,
                  "date": self.jour.date().toString("yyyy-MM-dd"), "commune": self.commune.text().strip() or None,
                  "distance_km": self.distance.value() or None, "denivele_m": self.dplus.value() or None}
        self.resultat = dpro.importer_classement(self.club_id, self.saison, course, lignes, n)
        super().accept()


# ======================================================================
# Onglet Licenciés
# ======================================================================

class LicenciesClub(_EcranClub):

    def __init__(self, athlete_id_initial=None):
        super().__init__("🏅  Licenciés", "La fiche de chaque adhérent : catégorie, groupes, présences, bilan de la saison, "
                         "records, index ITRA, UTMB et Betrail, résultats. Les résultats d'une course chronométrée par le "
                         "club arrivent tout seuls ; ceux d'une autre course se saisissent ou s'importent.",
                         athlete_id_initial)
        haut = QHBoxLayout()
        gauche = QVBoxLayout()
        self.recherche = QLineEdit()
        self.recherche.setPlaceholderText("Rechercher un adhérent")
        self.recherche.textChanged.connect(lambda _t: self._remplir_liste())
        self.liste = QListWidget()
        self.liste.setMinimumWidth(270)
        self.liste.setMinimumHeight(560)
        self.liste.currentRowChanged.connect(lambda _r: self._afficher())
        gauche.addWidget(self.recherche)
        gauche.addWidget(self.liste)
        imp = _bouton("📥 Importer un classement")
        imp.clicked.connect(self._importer)
        gauche.addWidget(imp)
        haut.addLayout(gauche)
        droite = QVBoxLayout()
        cadre, lc = _cadre("Profil")
        self.fiche = QLabel("Choisis un adhérent.")
        self.fiche.setWordWrap(True)
        self.fiche.setTextFormat(Qt.TextFormat.RichText)
        lc.addWidget(self.fiche)
        droite.addWidget(cadre)
        cadre, lc = _cadre("Résultats")
        self.table = _table(["Date", "Course", "Épreuve", "Distance", "Temps", "Classement", "Source"], 230)
        self.table.cellDoubleClicked.connect(lambda _r, _c: self._modifier())
        lc.addWidget(self.table)
        b = QHBoxLayout()
        for texte, fn, p in (("➕ Résultat", self._ajouter, True), ("✏️ Modifier", self._modifier, False),
                             ("🗑 Supprimer", self._supprimer, False), ("📈 Index", self._index, False)):
            w = _bouton(texte, p)
            w.clicked.connect(fn)
            b.addWidget(w)
        b.addStretch()
        lc.addLayout(b)
        droite.addWidget(cadre)
        haut.addLayout(droite, 1)
        self.principal.addLayout(haut)
        cadre, lc = _cadre("Derniers résultats du club (90 jours)")
        self.table_club = _table(["Date", "Licencié", "Course", "Temps", "Classement"], 200)
        lc.addWidget(self.table_club)
        self.principal.addWidget(cadre)
        self.principal.addStretch()
        self._adh, self._vues, self._res = [], [], []
        self._finaliser()

    def actualiser(self):
        self._adh = [a for a in dclub.adhesions(self.club_id, self.saison) if a["statut"] != "annulee"]
        self._remplir_liste()
        rs = dpro.resultats_du_club(self.club_id, date.today() - timedelta(days=90))
        t = self.table_club
        t.setRowCount(len(rs))
        for i, r in enumerate(rs):
            for j, v in enumerate((_jour(r["date"]), f"{r['prenom']} {r['nom']}", r["course"] + (f" · {r['epreuve']}"
                                                                                                   if r["epreuve"] else ""),
                                   P.texte_temps(r["temps_s"]) or P.LIBELLE_STATUT_RESULTAT.get(r["statut"], ""),
                                   _texte_classement(r))):
                t.setItem(i, j, QTableWidgetItem(v))
        t.resizeColumnsToContents()

    def _remplir_liste(self):
        from noyau.club import imports as imp
        q = imp._cle(self.recherche.text())
        actuel = self._courant()
        self._vues = [a for a in self._adh if not q or q in imp._cle(f"{a['nom']} {a['prenom']} {a['prenom']} {a['nom']}")]
        self.liste.blockSignals(True)
        self.liste.clear()
        for a in self._vues:
            c = a["categorie"]
            self.liste.addItem(f"{a['nom']} {a['prenom']}" + (f"  ·  {c['code']}" if c else ""))
        ids = [a["personne_id"] for a in self._vues]
        self.liste.setCurrentRow(ids.index(actuel) if actuel in ids else (0 if ids else -1))
        self.liste.blockSignals(False)
        self._afficher()

    def _courant(self):
        i = self.liste.currentRow()
        return self._vues[i]["personne_id"] if 0 <= i < len(self._vues) else None

    def choisir(self, personne_id):
        ids = [a["personne_id"] for a in self._vues]
        if personne_id in ids:
            self.liste.setCurrentRow(ids.index(personne_id))

    def _afficher(self):
        pid = self._courant()
        if not pid:
            self.fiche.setText("Aucun adhérent pour cette saison." if not self._adh else "Choisis un adhérent.")
            self.table.setRowCount(0)
            return
        p = dpro.profil(pid, self.club_id, self.saison)
        e = html.escape
        f, a = p["fiche"], p["adhesion"] or {}
        c = p["categorie"]
        l = [f"<b style='font-size:16px'>{e(f['prenom'])} {e(f['nom'])}</b>"
             + (f" · {e(c['libelle'])} ({c['code']})" if c else "")
             + (f" · {e(cat.LIBELLE_LICENCE.get(a.get('type_licence'), ''))}" if a.get("type_licence") else "")
             + (f" n° {e(a['numero_licence'])}" if a.get("numero_licence") else "")]
        if p["groupes"]:
            l.append("Groupes : " + e(", ".join(p["groupes"])))
        pr = p["presences"]
        if pr:
            l.append(f"Présences {p['saison']} : {pr['presents'] + pr['retards']} sur {pr['seances']} séance(s)"
                     + (f", <b>{pr['taux']} %</b>" if pr["taux"] is not None else "")
                     + (f" · <span style='color:{ROUGE}'>{pr['absences_de_suite']} absences de suite</span>"
                        if pr["absences_de_suite"] >= ag.ABSENCES_DECROCHAGE else ""))
        bs, bt = p["bilan_saison"], p["bilan_total"]
        l.append(f"Saison : {bs['courses']} course(s), {bs['km']:g} km, {bs['dplus']} m D+, {bs['podiums']} podium(s)"
                 + (f", {bs['abandons']} abandon(s)" if bs["abandons"] else "")
                 + f" · Depuis le début : {bt['courses']} course(s), {bt['podiums']} podium(s)")
        rec = p["records"]
        if rec["route"]:
            l.append("Records route : " + " · ".join(f"<b>{e(x['distance'])}</b> {x['temps']} ({x['allure']}, "
                                                     f"{_jour(x['date'])})" for x in rec["route"]))
        if rec["trail"]:
            l.append("Trail (meilleure vitesse en km-effort) : " + " · ".join(
                f"<b>{e(x['discipline'])}</b> {x['vitesse_ke']:g} km-effort/h sur {e(x['course'])}" for x in rec["trail"]))
        if rec["plus_longue"]:
            x = rec["plus_longue"]
            l.append(f"Plus longue course : {e(x['course'])}, {x['distance_km']:g} km"
                     + (f" et {x['denivele_m']} m D+" if x.get("denivele_m") else ""))
        dern = {}
        for i in p["index"]:
            dern.setdefault(i["organisme"], i)
        if dern:
            l.append("Index : " + " · ".join(f"<b>{e(k)}</b> {v['valeur']:g} ({_jour(v['date_releve'])})"
                                             for k, v in dern.items()))
        if p["diplomes"]:
            l.append("Diplômes : " + " · ".join(
                e(d["intitule"]) + (f" <span style='color:{ROUGE if d['etat'] == 'expiré' else ORANGE}'>({d['etat']})</span>"
                                    if d["etat"] in ("expiré", "bientôt") else "") for d in p["diplomes"]))
        if p["athlete_id"]:
            l.append("<span style='color:#9E9E9E'>A un profil coureur dans Trail Hub : ses résultats y sont recopiés.</span>")
        self.fiche.setText("<br>".join(l))
        self._res = p["resultats"]
        t = self.table
        t.setRowCount(len(self._res))
        for i, r in enumerate(self._res):
            vals = (_jour(r["date"]), r["course"], r["epreuve"] or "",
                    (f"{r['distance_km']:g} km" if r["distance_km"] else "") + (f" {r['denivele_m']} D+" if r["denivele_m"]
                                                                                 else ""),
                    P.texte_temps(r["temps_s"]) if r["temps_s"] else P.LIBELLE_STATUT_RESULTAT.get(r["statut"], ""),
                    _texte_classement(r), r["source"] or "")
            for j, v in enumerate(vals):
                it = QTableWidgetItem(v)
                if j == 4 and r["statut"] != "classe":
                    it.setForeground(QColor(GRIS))
                t.setItem(i, j, it)
        t.resizeColumnsToContents()

    def _resultat(self):
        i = self.table.currentRow()
        return self._res[i] if 0 <= i < len(self._res) else None

    def _ajouter(self):
        pid = self._courant()
        if pid and DialogueResultat(self, pid).exec():
            self.actualiser()

    def _modifier(self):
        r = self._resultat()
        if r and DialogueResultat(self, self._courant(), r).exec():
            self.actualiser()

    def _supprimer(self):
        r = self._resultat()
        if r and QMessageBox.question(self, "Supprimer", f"Supprimer le résultat « {r['course']} » du "
                                      f"{_jour(r['date'])} ?") == QMessageBox.StandardButton.Yes:
            dpro.supprimer_resultat(r["id"])
            self.actualiser()

    def _index(self):
        pid = self._courant()
        if not pid:
            return
        d = QDialog(self)
        d.setWindowTitle("Index de performance")
        d.setStyleSheet(obtenir_style_ecran())
        lay = QVBoxLayout(d)
        f = QFormLayout()
        org = QComboBox()
        org.setEditable(True)
        org.addItems(ORGANISMES_INDEX)
        val = QDoubleSpinBox()
        val.setRange(0, 1500)
        val.setDecimals(1)
        jour = _champ_date()
        categorie = QComboBox()
        categorie.setEditable(True)
        categorie.addItems(["Général", "XS", "S", "M", "L", "XL", "XXL", "20K", "50K", "100K", "100M"])
        f.addRow("Organisme", org)
        f.addRow("Valeur", val)
        f.addRow("Catégorie", categorie)
        f.addRow("Relevé le", jour)
        lay.addLayout(f)
        aide = QLabel("Relève l'index sur le site de l'organisme (itra.run, utmb.world, betrail.run) : il évolue après "
                      "chaque course.")
        aide.setWordWrap(True)
        aide.setObjectName("texteSecondaire")
        lay.addWidget(aide)
        _boutons_dialogue(d, lay)
        if d.exec():
            try:
                dper.ajouter_index(pid, org.currentText(), val.value(), jour.date().toString("yyyy-MM-dd"),
                                   categorie.currentText())
            except dper.ErreurPersonne as e:
                QMessageBox.warning(self, "Index", str(e))
            self.actualiser()

    def _importer(self):
        d = DialogueImportClassement(self, self.club_id, self.saison)
        if d.exec():
            r = d.resultat
            QMessageBox.information(self, "Classement", f"{r['associes']} adhérent(s) retrouvé(s) : {r['ajoutes']} résultat(s) "
                                    f"ajouté(s), {r['mis_a_jour']} mis à jour."
                                    + (f"\n\nDu club d'après la colonne Club mais pas retrouvés (nom différent ?) : "
                                       + ", ".join(r["non_trouves"][:15]) if r["non_trouves"] else ""))
            self.actualiser()


# ======================================================================
# Onglet Séances partagées
# ======================================================================

class DialogueModele(QDialog):

    def __init__(self, parent, club_id, modele=None):
        super().__init__(parent)
        self.club_id, m = club_id, modele or {}
        self.modele_id = m.get("id")
        self.setWindowTitle("Séance du club")
        self.setStyleSheet(obtenir_style_ecran())
        self.resize(620, 620)
        lay = QVBoxLayout(self)
        f = QFormLayout()
        self.titre = QLineEdit(m.get("titre") or "")
        self.titre.setPlaceholderText("ex. 30/30 du mardi, Côtes de Bédoin, Sortie longue en endurance")
        self.type = QComboBox()
        for c, l in ag.TYPES:
            self.type.addItem(l, c)
        self.type.setCurrentIndex(max(0, self.type.findData(m.get("type") or "entrainement")))
        self.objectif, self.public = QLineEdit(m.get("objectif") or ""), QLineEdit(m.get("public") or "")
        self.objectif.setPlaceholderText("ex. VMA, seuil, foncier, côtes")
        self.public.setPlaceholderText("ex. adultes trail, minimes-cadets")
        self.duree = QSpinBox()
        self.duree.setRange(0, 600)
        self.duree.setSuffix(" min")
        self.duree.setSpecialValueText("—")
        self.duree.setValue(m.get("duree_min") or 0)
        self.fractionne = QComboBox()
        self.fractionne.addItem("— pas de fractionné de la bibliothèque —", None)
        from noyau.entrainement import fractionne as fr
        for s in fr.BIBLIOTHEQUE:
            self.fractionne.addItem(f"{s['nom']} ({fr.resume(s)})", s["code"])
        self.fractionne.setCurrentIndex(max(0, self.fractionne.findData(m.get("fractionne_code"))))
        self.auteur = _combo_entraineur(m.get("auteur_id"))
        self.contenu = QPlainTextEdit(m.get("contenu") or "")
        self.contenu.setPlaceholderText("Échauffement, corps de séance, retour au calme, consignes…")
        for lib, w in (("Titre", self.titre), ("Type", self.type), ("Objectif", self.objectif), ("Pour qui", self.public),
                       ("Durée", self.duree), ("Fractionné", self.fractionne), ("Entraîneur", self.auteur),
                       ("Contenu", self.contenu)):
            f.addRow(lib, w)
        lay.addLayout(f)
        self.apercu = QLabel("")
        self.apercu.setWordWrap(True)
        self.apercu.setObjectName("texteSecondaire")
        lay.addWidget(self.apercu)
        self.fractionne.currentIndexChanged.connect(lambda _i: self._apercu())
        self._apercu()
        _boutons_dialogue(self, lay)

    def champs(self):
        return {"titre": self.titre.text(), "type": self.type.currentData(), "objectif": self.objectif.text().strip() or None,
                "public": self.public.text().strip() or None, "duree_min": self.duree.value() or None,
                "fractionne_code": self.fractionne.currentData(), "auteur_id": self.auteur.currentData(),
                "contenu": self.contenu.toPlainText().strip() or None}

    def _apercu(self):
        self.apercu.setText(("Exemple pour une VMA de 15 km/h : " + dpro.texte_modele(self.champs(), 15).split("\n")[-1])
                            if self.fractionne.currentData() else "")

    def accept(self):
        try:
            dpro.enregistrer_modele(self.club_id, self.champs(), self.modele_id)
        except dpro.ErreurProfil as e:
            QMessageBox.warning(self, "Séance", str(e))
            return
        super().accept()


class SeancesPartageesClub(_EcranClub):

    def __init__(self, athlete_id_initial=None):
        super().__init__("📚  Séances du club", "La bibliothèque des séances écrites par les entraîneurs. Programme une séance "
                         "pour un groupe : elle arrive dans l'agenda, et dans la planification des coureurs qui ont un "
                         "profil dans Trail Hub (avec les allures de leur VMA pour un fractionné).", athlete_id_initial)
        b = QHBoxLayout()
        for texte, fn, p in (("➕ Nouvelle séance", self._nouvelle, True), ("✏️ Modifier", self._modifier, False),
                             ("📅 Programmer pour un groupe", self._programmer, True),
                             ("🗑 Supprimer", self._supprimer, False)):
            w = _bouton(texte, p)
            w.clicked.connect(fn)
            b.addWidget(w)
        b.addStretch()
        self.principal.addLayout(b)
        self.table = _table(["Séance", "Type", "Objectif", "Pour qui", "Durée", "Fractionné", "Entraîneur", "Programmée"], 260)
        self.table.cellDoubleClicked.connect(lambda _r, _c: self._modifier())
        self.table.itemSelectionChanged.connect(self._apercu)
        self.principal.addWidget(self.table)
        cadre, lc = _cadre("Contenu")
        self.label = QLabel("")
        self.label.setWordWrap(True)
        lc.addWidget(self.label)
        self.principal.addWidget(cadre)
        cadre, lc = _cadre("Séances programmées à venir")
        self.table_prog = _table(["Date", "Horaire", "Séance", "Groupe", "Entraîneur"], 180)
        lc.addWidget(self.table_prog)
        b2 = QHBoxLayout()
        env = _bouton("📲 Envoyer aux coureurs du groupe")
        env.clicked.connect(self._envoyer)
        b2.addWidget(env)
        b2.addStretch()
        lc.addLayout(b2)
        self.principal.addWidget(cadre)
        self.principal.addStretch()
        self._modeles, self._prog = [], []
        self._finaliser()

    def actualiser(self):
        self._modeles = dpro.modeles(self.club_id)
        from noyau.entrainement import fractionne as fr
        t = self.table
        t.setRowCount(len(self._modeles))
        for i, m in enumerate(self._modeles):
            s = fr.modele(m["fractionne_code"]) if m["fractionne_code"] else None
            for j, v in enumerate((m["titre"], ag.LIBELLE_TYPE.get(m["type"], ""), m["objectif"] or "", m["public"] or "",
                                   f"{m['duree_min']} min" if m["duree_min"] else "", s["nom"] if s else "",
                                   m["auteur"] or "", f"{m['fois']} fois" if m["fois"] else "")):
                t.setItem(i, j, QTableWidgetItem(v))
        t.resizeColumnsToContents()
        auj = date.today()
        self._prog = [s for s in dag.seances(self.club_id, auj, auj + timedelta(days=60), avec_annulees=False)
                      if s["contenu"]]
        t = self.table_prog
        t.setRowCount(len(self._prog))
        for i, s in enumerate(self._prog):
            for j, v in enumerate((_date_courte(s["date"]), _horaire(s), s["titre"], s["groupe"] or "Tout le club",
                                   s["entraineur"] or "")):
                t.setItem(i, j, QTableWidgetItem(v))
        t.resizeColumnsToContents()
        self._apercu()

    def _courant(self):
        i = self.table.currentRow()
        return self._modeles[i] if 0 <= i < len(self._modeles) else None

    def _apercu(self):
        m = self._courant()
        self.label.setText(dpro.texte_modele(m, 15) + ("\n\n(cibles calculées ici pour une VMA de 15 km/h ; chaque coureur "
                                                       "reçoit les siennes)" if m and m["fractionne_code"] else "")
                           if m else "Choisis une séance.")

    def _nouvelle(self):
        if DialogueModele(self, self.club_id).exec():
            self.actualiser()

    def _modifier(self):
        m = self._courant()
        if m and DialogueModele(self, self.club_id, m).exec():
            self.actualiser()

    def _supprimer(self):
        m = self._courant()
        if m and QMessageBox.question(self, "Supprimer", f"Supprimer « {m['titre']} » de la bibliothèque ? Les séances déjà "
                                      "programmées restent dans l'agenda.") == QMessageBox.StandardButton.Yes:
            dpro.supprimer_modele(m["id"])
            self.actualiser()

    def _programmer(self):
        m = self._courant()
        if not m:
            QMessageBox.information(self, "Programmer", "Choisis d'abord une séance de la bibliothèque.")
            return
        d = QDialog(self)
        d.setWindowTitle(f"Programmer « {m['titre']} »")
        d.setStyleSheet(obtenir_style_ecran())
        lay = QVBoxLayout(d)
        f = QFormLayout()
        groupe = _combo_groupe(self.club_id)
        jour = _champ_date((date.today() + timedelta(days=1)).isoformat())
        existante = QComboBox()

        def remplir():
            existante.clear()
            existante.addItem("une nouvelle séance dans l'agenda", None)
            j = jour.date().toString("yyyy-MM-dd")
            for s in dag.seances(self.club_id, j, j, avec_annulees=False):
                if groupe.currentData() is None or s["groupe_id"] == groupe.currentData():
                    existante.addItem(f"la séance prévue : {_horaire(s)} {s['titre']} ({s['groupe'] or 'tout le club'})",
                                      s["id"])
            existante.setCurrentIndex(1 if existante.count() > 1 else 0)
        groupe.currentIndexChanged.connect(lambda _i: remplir())
        jour.dateChanged.connect(lambda _d: remplir())
        remplir()
        debut, fin, lieu = QLineEdit(), QLineEdit(), QLineEdit()
        debut.setPlaceholderText("18:30")
        fin.setPlaceholderText("20:00")
        envoyer = QComboBox()
        envoyer.addItem("et l'envoyer dans la planification des coureurs du groupe", True)
        envoyer.addItem("sans l'envoyer aux coureurs", False)
        for lib, w in (("Groupe", groupe), ("Date", jour), ("Dans", existante), ("Début", debut), ("Fin", fin),
                       ("Lieu", lieu), ("", envoyer)):
            f.addRow(lib, w)
        lay.addLayout(f)
        _boutons_dialogue(d, lay, "Programmer")
        if not d.exec():
            return
        try:
            sid = dpro.planifier(m["id"], self.club_id, jour.date().toString("yyyy-MM-dd"), groupe.currentData(),
                                 ag.verifier_heure(debut.text()), ag.verifier_heure(fin.text()), lieu.text().strip() or None,
                                 seance_id=existante.currentData())
            n = dpro.envoyer_aux_coureurs(sid) if envoyer.currentData() else 0
        except (dpro.ErreurProfil, ag.ErreurAgenda) as e:
            QMessageBox.warning(self, "Programmer", str(e))
            return
        QMessageBox.information(self, "Programmer", "Séance dans l'agenda du club"
                                + (f", envoyée à {n} coureur(s) qui ont un profil dans Trail Hub." if envoyer.currentData()
                                   else "."))
        self.actualiser()

    def _envoyer(self):
        i = self.table_prog.currentRow()
        if 0 <= i < len(self._prog):
            n = dpro.envoyer_aux_coureurs(self._prog[i]["id"])
            QMessageBox.information(self, "Envoyer", f"Séance envoyée à {n} coureur(s) (ceux qui l'avaient déjà ne la "
                                    "reçoivent pas deux fois).")


# ======================================================================
# Onglet Entraîneurs
# ======================================================================

class EntraineursClub(_EcranClub):

    def __init__(self, athlete_id_initial=None):
        super().__init__("🧑‍🏫  Entraîneurs", "Les entraîneurs du club, leurs groupes, les séances encadrées ces 60 derniers "
                         "jours et à venir, leurs diplômes et les dates de recyclage.", athlete_id_initial)
        b = QHBoxLayout()
        for texte, fn, p in (("➕ Désigner un entraîneur", self._designer, True), ("🎓 Ajouter un diplôme", self._diplome, False),
                             ("🗑 Retirer le diplôme", self._retirer_diplome, False)):
            w = _bouton(texte, p)
            w.clicked.connect(fn)
            b.addWidget(w)
        b.addStretch()
        self.principal.addLayout(b)
        self.alertes = QLabel("")
        self.alertes.setWordWrap(True)
        self.alertes.setTextFormat(Qt.TextFormat.RichText)
        self.principal.addWidget(self.alertes)
        self.table = _table(["Entraîneur", "Groupes", "Séances encadrées (60 j)", "Prochaines séances", "Diplômes", "Téléphone"],
                            260)
        self.table.itemSelectionChanged.connect(self._diplomes)
        self.principal.addWidget(self.table)
        cadre, lc = _cadre("Diplômes de l'entraîneur")
        self.table_d = _table(["Diplôme", "Organisme", "Obtenu le", "Valable jusqu'au", "État"], 160)
        lc.addWidget(self.table_d)
        self.principal.addWidget(cadre)
        self.principal.addStretch()
        self._ent, self._dip = [], []
        self._finaliser()

    def actualiser(self):
        self._ent = dpro.entraineurs(self.club_id)
        t = self.table
        t.setRowCount(len(self._ent))
        for i, e in enumerate(self._ent):
            prochaines = ", ".join(f"{_date_courte(s['date'])} {s['titre']}" for s in e["prochaines"][:3])
            vals = (f"{e['prenom']} {e['nom']}", ", ".join(e["groupes"]), str(e["seances_encadrees"]), prochaines,
                    ", ".join(d["intitule"] for d in e["diplomes"]), e["telephone"] or "")
            for j, v in enumerate(vals):
                it = QTableWidgetItem(v)
                if j == 4 and e["alertes"]:
                    it.setForeground(QColor(ORANGE))
                    it.setToolTip("\n".join(e["alertes"]))
                t.setItem(i, j, it)
        t.resizeColumnsToContents()
        al = [f"{e['prenom']} {e['nom']} — {a}" for e in self._ent for a in e["alertes"]]
        self.alertes.setText(("<b style='color:%s'>Diplômes à renouveler :</b> " % ORANGE) + html.escape(" · ".join(al))
                             if al else ("" if self._ent else "Pas encore d'entraîneur : désigne-les, ou choisis-les dans "
                                         "les groupes et les séances."))
        self._diplomes()

    def _courant(self):
        i = self.table.currentRow()
        return self._ent[i] if 0 <= i < len(self._ent) else None

    def _diplomes(self):
        e = self._courant()
        self._dip = e["diplomes"] if e else []
        t = self.table_d
        t.setRowCount(len(self._dip))
        for i, d in enumerate(self._dip):
            for j, v in enumerate((d["intitule"], d["organisme"] or "", _jour(d["date_obtention"]), _jour(d["date_validite"]),
                                   d["etat"])):
                it = QTableWidgetItem(v)
                if j == 4:
                    it.setForeground(QColor({"expiré": ROUGE, "bientôt": ORANGE, "valide": VERT}.get(d["etat"], GRIS)))
                t.setItem(i, j, it)
        t.resizeColumnsToContents()

    def _designer(self):
        d = QDialog(self)
        d.setWindowTitle("Désigner un entraîneur")
        d.setStyleSheet(obtenir_style_ecran())
        lay = QVBoxLayout(d)
        combo = QComboBox()
        deja = {e["personne_id"] for e in self._ent}
        for p in dper.lister():
            if p["id"] not in deja:
                combo.addItem(f"{p['nom']} {p['prenom']}", p["id"])
        lay.addWidget(QLabel("Personne (fiche Personne existante) :"))
        lay.addWidget(combo)
        _boutons_dialogue(d, lay, "Désigner")
        if d.exec() and combo.currentData():
            pid = combo.currentData()
            dper.definir_roles(pid, list(dper.roles(pid)) + ["entraineur"])
            self.actualiser()

    def _diplome(self):
        e = self._courant()
        if not e:
            QMessageBox.information(self, "Diplôme", "Choisis d'abord l'entraîneur.")
            return
        d = QDialog(self)
        d.setWindowTitle(f"Diplôme — {e['prenom']} {e['nom']}")
        d.setStyleSheet(obtenir_style_ecran())
        lay = QVBoxLayout(d)
        f = QFormLayout()
        intitule = QComboBox()
        intitule.setEditable(True)
        intitule.addItems(["Entraîneur Running", "Entraîneur Trail", "Coach Athlé Santé", "Animateur Athlé Découverte",
                           "Entraîneur Fédéral 1er degré", "Officiel FFA", "PSC1 (premiers secours)", "BPJEPS", "DEJEPS"])
        organisme = QLineEdit("FFA")
        obtention = _champ_date()
        validite = _champ_date((date.today() + timedelta(days=4 * 365)).isoformat())
        for lib, w in (("Diplôme", intitule), ("Organisme", organisme), ("Obtenu le", obtention),
                       ("Valable jusqu'au", validite)):
            f.addRow(lib, w)
        lay.addLayout(f)
        _boutons_dialogue(d, lay)
        if d.exec():
            try:
                dpro.enregistrer_diplome(e["personne_id"], {"intitule": intitule.currentText(), "organisme": organisme.text(),
                                                            "date_obtention": obtention.date().toString("yyyy-MM-dd"),
                                                            "date_validite": validite.date().toString("yyyy-MM-dd")})
            except dpro.ErreurProfil as x:
                QMessageBox.warning(self, "Diplôme", str(x))
            self.actualiser()

    def _retirer_diplome(self):
        i = self.table_d.currentRow()
        if 0 <= i < len(self._dip):
            dpro.supprimer_diplome(self._dip[i]["id"])
            self.actualiser()
