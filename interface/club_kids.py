"""
Kids, l'école d'athlé (chantier D) — onglet « 🧒 Kids » de la fenêtre Club : les enfants (baby à minimes),
leur carnet de progression en quatre niveaux (compétences à cocher), leurs badges, leur équipement, l'accord
parental et le droit à l'image, le carnet en PDF pour les parents. Aucun classement entre enfants.
Aucune requête SQL ici : noyau/donnees/kids.py.
"""

import html
from datetime import date

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QDesktopServices
from PySide6.QtCore import QUrl
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFileDialog, QFormLayout, QHBoxLayout, QInputDialog, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QMessageBox, QTableWidgetItem, QVBoxLayout,
)

from noyau.donnees import kids as dki, club as dclub
from noyau.club import kids as KI
from interface.club import _EcranClub, _bouton, _cadre, _table


class KidsClub(_EcranClub):

    def __init__(self, athlete_id_initial=None):
        super().__init__("🧒  Kids : école d'athlé et de trail", "Le carnet de progression de chaque enfant en quatre "
                         "niveaux (découverte, explorateur, montagnard, jeune traileur), ses badges et son équipement. "
                         "Chaque enfant progresse à son rythme : pas de classement entre eux. Les parents voient le "
                         "carnet de leur enfant (téléphone, ou carnet PDF).", athlete_id_initial)
        h = QHBoxLayout()
        self.f_groupe = QComboBox()
        self.f_groupe.currentIndexChanged.connect(lambda _i: self._remplir())
        h.addWidget(QLabel("Groupe :"))
        h.addWidget(self.f_groupe)
        h.addStretch()
        self.principal.addLayout(h)
        cadre, lc = _cadre("Enfants")
        self.table = _table(["Nom", "Prénom", "Catégorie", "Niveau conseillé", "Progression", "Badges", "Accord parental"], 260)
        self.table.itemSelectionChanged.connect(self._carnet)
        lc.addWidget(self.table)
        self.resume = QLabel("")
        self.resume.setObjectName("texteSecondaire")
        self.resume.setWordWrap(True)
        lc.addWidget(self.resume)
        self.principal.addWidget(cadre)
        cadre, lc = _cadre("Carnet de progression")
        self.titre = QLabel("Choisis un enfant.")
        self.titre.setTextFormat(Qt.TextFormat.RichText)
        self.titre.setWordWrap(True)
        lc.addWidget(self.titre)
        self.liste = QListWidget()
        self.liste.setMinimumHeight(420)
        self.liste.setStyleSheet("QListWidget::indicator { width: 15px; height: 15px; border: 1px solid #8a948e; "
                                 "border-radius: 3px; } QListWidget::indicator:checked { background: #2E7D32; "
                                 "border-color: #2E7D32; }")
        self.liste.itemChanged.connect(self._coche)
        lc.addWidget(self.liste)
        b = QHBoxLayout()
        aj = _bouton("➕ Compétence propre au club")
        aj.clicked.connect(self._ajouter_competence)
        pdf = _bouton("📄 Carnet pour les parents (PDF)", True)
        pdf.clicked.connect(self._pdf)
        b.addWidget(aj)
        b.addWidget(pdf)
        b.addStretch()
        lc.addLayout(b)
        self.badges = QLabel("")
        self.badges.setWordWrap(True)
        self.badges.setTextFormat(Qt.TextFormat.RichText)
        lc.addWidget(self.badges)
        self.principal.addWidget(cadre)
        cadre, lc = _cadre("Équipement")
        f = QFormLayout()
        self.eq = {k: QLineEdit() for k in ("taille_vetement", "taille_tshirt", "pointure", "sac")}
        for k, lib in (("taille_vetement", "Taille des vêtements"), ("taille_tshirt", "Taille t-shirt"),
                       ("pointure", "Pointure"), ("sac", "Sac, ceinture")):
            f.addRow(lib, self.eq[k])
        self.cases = {k: QCheckBox(lib) for k, lib in (("gourde", "Gourde ou flasque"), ("veste", "Coupe-vent"),
                                                       ("frontale", "Lampe frontale"))}
        h = QHBoxLayout()
        for c in self.cases.values():
            h.addWidget(c)
        f.addRow("A son", h)
        self.eq_notes = QLineEdit()
        f.addRow("Notes", self.eq_notes)
        lc.addLayout(f)
        enr = _bouton("💾 Enregistrer l'équipement")
        enr.clicked.connect(self._enregistrer_eq)
        lc.addWidget(enr)
        self.principal.addWidget(cadre)
        self.principal.addStretch()
        self._enfants, self._courant, self._remplissage = [], None, False
        self._finaliser()

    def actualiser(self):
        actuel = self.f_groupe.currentData()
        self.f_groupe.blockSignals(True)
        self.f_groupe.clear()
        self.f_groupe.addItem("Tous les groupes", None)
        for g in self.groupes_visibles():
            self.f_groupe.addItem(g["nom"], g["id"])
        self.f_groupe.setCurrentIndex(max(0, self.f_groupe.findData(actuel)))
        self.f_groupe.blockSignals(False)
        self._remplir()

    def _remplir(self):
        self._enfants = dki.enfants(self.club_id, self.saison, self.section_id, self.f_groupe.currentData())
        t = self.table
        t.setRowCount(len(self._enfants))
        for r, e in enumerate(self._enfants):
            n = e["niveau_conseille"]
            p = e["progression"].get(n) if n else None
            vals = (e["nom"], e["prenom"] or "", e["categorie"]["libelle"] if e["categorie"] else "?",
                    f"{KI.ICONE_NIVEAU.get(n, '')} {KI.LIBELLE_NIVEAU.get(n, '')}", f"{p['faites']} / {p['total']}" if p else "",
                    str(e["nb_badges"]), "oui" if e["accord_parental"] else "à demander")
            for j, v in enumerate(vals):
                it = QTableWidgetItem(v)
                if j == 6 and not e["accord_parental"]:
                    it.setForeground(QColor("#E65100"))
                t.setItem(r, j, it)
        t.resizeColumnsToContents()
        b = dki.bilan_club(self.club_id, self.saison)
        self.resume.setText(f"{b['enfants']} enfant(s) · " + " · ".join(f"{KI.LIBELLE_NIVEAU[n]} {v}" for n, v in b["par_niveau"].items())
                            + f" · {b['badges_saison']} badge(s) gagné(s) cette saison"
                            + (f" · {b['sans_accord']} accord(s) parental(aux) à demander" if b["sans_accord"] else ""))
        self._carnet()

    def _enfant(self):
        r = self.table.currentRow()
        return self._enfants[r] if 0 <= r < len(self._enfants) else None

    def _carnet(self):
        e = self._enfant()
        self._remplissage = True
        self.liste.clear()
        self._courant = None
        if not e:
            self.titre.setText("Choisis un enfant.")
            self.badges.setText("")
            self._remplissage = False
            return
        c = dki.carnet(e["personne_id"], self.club_id, self.saison)
        self._courant = c
        p = c["personne"]
        self.titre.setText(f"<b>{html.escape(p['prenom'] or '')} {html.escape(p['nom'])}</b> · "
                           f"{html.escape(c['categorie']['libelle']) if c['categorie'] else ''} · niveau conseillé : "
                           f"{KI.LIBELLE_NIVEAU.get(c['niveau_conseille'], '—')} · {c['presences']} entraînement(s)"
                           + (f"<br>Repères FFA : {html.escape(' ; '.join(c['reperes']))}" if c["reperes"] else "")
                           + ("" if c["accord_parental"] or e["accord_parental"] else
                              "<br><span style='color:#E65100'>Accord parental pas encore enregistré.</span>"))
        for n in c["niveaux"]:
            t = QListWidgetItem(f"{n['icone']} {n['libelle']} — {n['faites']} / {n['total']}")
            t.setFlags(Qt.ItemFlag.NoItemFlags)
            f = t.font()
            f.setBold(True)
            t.setFont(f)
            self.liste.addItem(t)
            for x in n["competences"]:
                it = QListWidgetItem(f"    {x['libelle']}  ·  {x['libelle_domaine']}"
                                     + (f"  (le {x['date'][8:10]}/{x['date'][5:7]})" if x["validee"] else ""))
                it.setData(Qt.ItemDataRole.UserRole, x["id"])
                it.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable)
                it.setCheckState(Qt.CheckState.Checked if x["validee"] else Qt.CheckState.Unchecked)
                self.liste.addItem(it)
        self.badges.setText("<b>Badges</b> : " + (" · ".join(html.escape(b["libelle"]) for b in c["badges"]) or "pas encore"))
        eq = c["equipement"]
        for k, w in self.eq.items():
            w.setText(eq.get(k) or "")
        for k, w in self.cases.items():
            w.setChecked(bool(eq.get(k)))
        self.eq_notes.setText(eq.get("notes") or "")
        self._remplissage = False

    def _coche(self, it):
        if self._remplissage or not self._courant:
            return
        cid = it.data(Qt.ItemDataRole.UserRole)
        pid = self._courant["personne"]["id"]
        if it.checkState() == Qt.CheckState.Checked:
            nouveaux = dki.valider(pid, cid, (dclub.club_principal() or {}).get("nom"))
            if nouveaux:
                QMessageBox.information(self, "Bravo !", "Nouveau badge : " + ", ".join(nouveaux))
        else:
            dki.retirer_validation(pid, cid)
        r = self.table.currentRow()
        self._remplir()
        self.table.selectRow(r)

    def _ajouter_competence(self):
        niveaux = [l for _c, l, _i in KI.NIVEAUX]
        n, ok = QInputDialog.getItem(self, "Compétence", "Niveau :", niveaux, 0, False)
        if not ok:
            return
        doms = [l for _c, l in KI.DOMAINES]
        d, ok = QInputDialog.getItem(self, "Compétence", "Domaine :", doms, 0, False)
        if not ok:
            return
        t, ok = QInputDialog.getText(self, "Compétence", "La compétence (ce que l'enfant sait faire) :")
        if ok and t.strip():
            dki.ajouter_competence(self.club_id, KI.NIVEAUX[niveaux.index(n)][0], KI.DOMAINES[doms.index(d)][0], t)
            self._carnet()

    def _enregistrer_eq(self):
        if self._courant:
            v = {k: w.text().strip() or None for k, w in self.eq.items()}
            v.update({k: w.isChecked() for k, w in self.cases.items()})
            v["notes"] = self.eq_notes.text().strip() or None
            dki.enregistrer_equipement(self._courant["personne"]["id"], v)
            QMessageBox.information(self, "Équipement", "Équipement enregistré.")

    def _pdf(self):
        if not self._courant:
            return
        p = self._courant["personne"]
        chemin, _ = QFileDialog.getSaveFileName(self, "Carnet", f"Carnet {p['prenom'] or ''} {p['nom']}.pdf", "PDF (*.pdf)")
        if chemin:
            from interface import orga_pdf as P
            P.rendre(chemin, "Carnet", html_carnet(dclub.club_principal(), self._courant))
            QDesktopServices.openUrl(QUrl.fromLocalFile(chemin))


def html_carnet(club, c):
    e = lambda v: html.escape("" if v is None else str(v))
    p = c["personne"]
    blocs = ""
    for n in c["niveaux"]:
        lignes = "".join(f"<tr><td style='padding:3px 6px'>{'☑' if x['validee'] else '☐'}</td><td style='padding:3px 6px'>{e(x['libelle'])}"
                         f"</td><td style='padding:3px 6px;color:#666'>{e(x['libelle_domaine'])}</td><td style='padding:3px 6px;color:#666'>"
                         f"{e(x['date'][8:10] + '/' + x['date'][5:7] + '/' + x['date'][:4]) if x['date'] else ''}</td></tr>"
                         for x in n["competences"])
        blocs += (f"<p style='font-size:13pt;font-weight:bold;margin:14px 0 4px 0'>{e(n['icone'])} {e(n['libelle'])} · "
                  f"{n['faites']} / {n['total']}</p><table width='100%' cellspacing='0'>{lignes}</table>")
    return (f"<div style='font-family:Helvetica,Arial,sans-serif;color:#111;font-size:10.5pt'>"
            f"<p style='font-size:17pt;font-weight:bold;margin:0'>Carnet de progression · {e(p['prenom'])} {e(p['nom'])}</p>"
            f"<p style='color:#555'>{e((club or {}).get('nom'))} · {e(c['categorie']['libelle']) if c['categorie'] else ''} · "
            f"{c['presences']} entraînement(s) · imprimé le {date.today():%d/%m/%Y}</p>"
            + (f"<p><b>Badges</b> : {e(' · '.join(b['libelle'] for b in c['badges']))}</p>" if c["badges"] else "")
            + blocs + (f"<p style='color:#555'>Repères FFA en compétition : {e(' ; '.join(c['reperes']))}</p>" if c["reperes"] else "")
            + "<p style='color:#555'>Chaque enfant progresse à son rythme : ce carnet ne le compare à personne.</p></div>")
