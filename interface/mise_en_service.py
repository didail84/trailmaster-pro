"""
Fenêtre « ✅ Mise en service et données » (étape 8) :
  - Recette : contrôles automatiques de cet ordinateur, essais à faire pour
    de vrai étape par étape (à cocher avec une note), répétition générale
    (course fictive), rapport PDF ;
  - Données personnelles : registre des traitements (PDF), durées de
    conservation et nettoyage, demandes des personnes (copie, effacement),
    violations de données ;
  - Licences : celle de Trail Hub et celles des composants embarqués.
Aucune requête SQL ici : noyau/recette.py et noyau/rgpd.py.
"""

import html
from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QComboBox, QFileDialog, QHBoxLayout, QInputDialog, QLabel, QLineEdit, QMessageBox, QSpinBox, QTextBrowser,
)

from noyau import recette as RE, rgpd as RG
from noyau.donnees import personnes as dper
from interface.conteneur_onglets import ConteneurOnglets
from interface.forme_evolution import _EcranAthlete
from interface.calendrier_competitions import _bouton, _cadre, _table, _style_cases
from interface.organisation_logistique import DialogueChamps, _remplir, _ligne_choisie, _ouvrir_pdf
from interface import orga_pdf as P

VERT, ORANGE, ROUGE, GRIS = "#2E7D32", "#E65100", "#C62828", "#8A949E"
COULEUR_ETAT = {"ok": VERT, "attention": ORANGE, "echec": ROUGE, "info": GRIS, "fait": VERT, "probleme": ROUGE,
                "a_faire": None, "sans_objet": GRIS}
SYMBOLE = {"ok": "✅", "attention": "⚠️", "echec": "❌", "info": "ℹ️"}


def _e(v):
    return html.escape(str(v if v is not None else ""))


class _Ecran(_EcranAthlete):

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
# Recette
# ======================================================================

class RecetteEcran(_Ecran):

    def __init__(self, athlete_id_initial=None):
        super().__init__("✅  Mise en service", "Ce que le logiciel vérifie tout seul sur cet ordinateur, puis les essais à "
                         "faire pour de vrai avec le club, étape par étape. Une étape n'est vraiment terminée que quand "
                         "ses essais sont faits.", athlete_id_initial)
        self._ctrl, self._rec = [], []
        h = QHBoxLayout()
        self.c_total, self.c_pb, self.c_rep = self._carte("Essais réussis"), self._carte("Problèmes trouvés"), \
            self._carte("Répétition générale")
        for c in (self.c_total, self.c_pb, self.c_rep):
            h.addWidget(c)
        self.principal.addLayout(h)
        cadre, lc = _cadre("Contrôles de cet ordinateur")
        self.t_ctrl = _table(["", "Contrôle", "Résultat"], 260)
        lc.addWidget(self.t_ctrl)
        b = QHBoxLayout()
        br = _bouton("🔄 Relancer")
        br.clicked.connect(lambda: self.rafraichir(False))
        bn = _bouton("🌐 Vérifier le réseau (serveur, Relais)")
        bn.clicked.connect(lambda: self.rafraichir(True))
        b.addWidget(br)
        b.addWidget(bn)
        b.addStretch()
        lc.addLayout(b)
        self.principal.addWidget(cadre)
        cadre, lc = _cadre("Essais pour de vrai")
        self.t_rec = _table(["Étape", "Essai", "État", "Note", "Le"], 420)
        self.t_rec.doubleClicked.connect(lambda _i: self._noter())
        lc.addWidget(self.t_rec)
        b = QHBoxLayout()
        bno = _bouton("✏️ Noter l'essai choisi", True)
        bno.clicked.connect(self._noter)
        bpdf = _bouton("📄 Rapport de mise en service")
        bpdf.clicked.connect(self._pdf)
        self.b_rep = _bouton("🎭 Créer la répétition générale")
        self.b_rep.clicked.connect(self._repetition)
        for w in (bno, bpdf, self.b_rep):
            b.addWidget(w)
        b.addStretch()
        lc.addLayout(b)
        aide = QLabel("Répétition générale : une course fictive (40 coureurs inventés, 2 épreuves, dossards, points de "
                      "contrôle, postes) pour s'entraîner au chrono, au PC course et aux téléphones avec les bénévoles. "
                      "Elle apparaît dans l'Organisation ; supprime-la ici après l'entraînement.")
        aide.setObjectName("texteSecondaire")
        aide.setWordWrap(True)
        lc.addWidget(aide)
        self.principal.addWidget(cadre)
        self._finir()

    def rafraichir(self, reseau=False):
        self._ctrl = RE.controles(reseau=reseau)
        _remplir(self.t_ctrl, [(SYMBOLE.get(c["etat"], ""), c["libelle"], c["detail"]) for c in self._ctrl],
                 {(r, 2): COULEUR_ETAT.get(c["etat"]) for r, c in enumerate(self._ctrl) if c["etat"] in ("attention", "echec")})
        if self.t_ctrl.columnWidth(2) > 760:
            self.t_ctrl.setColumnWidth(2, 760)
        self.t_ctrl.setWordWrap(True)
        self.t_ctrl.resizeRowsToContents()
        self._rec = RE.recette()
        _remplir(self.t_rec, [(r["etape"], r["libelle"], RE.LIBELLE_ETAT[r["etat"]], r["note"] or "",
                               (r["maj"] or "")[:10]) for r in self._rec],
                 {(k, 2): COULEUR_ETAT.get(r["etat"]) for k, r in enumerate(self._rec) if COULEUR_ETAT.get(r["etat"])})
        if self.t_rec.columnWidth(1) > 520:
            self.t_rec.setColumnWidth(1, 520)
        _av, t = RE.avancement()
        self.c_total.valeur.setText(f"{t['faits']}/{t['total']}")
        self.c_total.detail.setText("essais faits et réussis")
        self.c_pb.valeur.setText(str(t["problemes"]))
        self.c_pb.detail.setText("note ce qui ne va pas : je le corrigerai" if t["problemes"] else "aucun pour l'instant")
        rep = RE.repetition()
        self.c_rep.valeur.setText("en place" if rep else "—")
        self.c_rep.detail.setText("dans l'Organisation : « Répétition générale »" if rep else "pas créée")
        self.b_rep.setText("🗑 Supprimer la répétition générale" if rep else "🎭 Créer la répétition générale")

    def _noter(self):
        r = _ligne_choisie(self.t_rec, self._rec)
        if not r:
            return
        spec = [("choix", "etat", "État", {"choix": list(RE.ETATS)}), ("long", "note", "Note (ce qui marche, ce qui coince)",
                                                                          {"hauteur": 90}),
                ("texte", "par", "Essayé par", None)]
        d = DialogueChamps(self, r["libelle"], spec, r, lambda ch: RE.noter(r["code"], ch["etat"], ch["note"], ch["par"]))
        if d.exec():
            self.rafraichir()

    def _repetition(self):
        if RE.repetition():
            if QMessageBox.question(self, "Répétition générale", "Supprimer la course fictive et tout ce qui a été saisi "
                                    "dessus (passages, incidents, photos) ?") == QMessageBox.StandardButton.Yes:
                RE.supprimer_repetition()
        else:
            RE.creer_repetition()
            QMessageBox.information(self, "Répétition générale", "Course fictive créée pour demain, avec 40 coureurs, "
                                    "2 épreuves, 2 points de contrôle et 3 postes. Ouvre Organisation : elle s'appelle "
                                    "« Répétition générale (course fictive) ». Donne aux bénévoles un compte sur le serveur "
                                    "pour cet événement (Serveur et comptes) pour essayer les téléphones.")
        self.rafraichir()

    def _pdf(self):
        r = RE.rapport()
        lignes_c = [(SYMBOLE.get(c["etat"], ""), P._e(c["libelle"]), P._e(c["detail"])) for c in r["controles"]]
        lignes_r = [(P._e(x["etape"]), P._e(x["libelle"]), f"<b>{P._e(RE.LIBELLE_ETAT[x['etat']])}</b>",
                     P._e(x["note"] or ""), P._e((x["maj"] or "")[:10])) for x in r["recette"]]
        t = r["total"]
        html_ = (P._entete("Mise en service de Trail Hub Center", {"nom": "Rapport", "date_debut": r["date"]},
                           f"{t['faits']} essai(s) réussi(s) sur {t['total']}, {t['problemes']} problème(s)")
                 + "<p><b>Contrôles de l'ordinateur</b></p>" + P._tableau(["", "Contrôle", "Résultat"], lignes_c, [5, 30, 65])
                 + "<p><b>Essais pour de vrai</b></p>" + P._tableau(["Étape", "Essai", "État", "Note", "Le"], lignes_r,
                                                                     [15, 38, 13, 26, 8]) + P._pied())
        _ouvrir_pdf(self, "Mise en service.pdf", html_, True)


# ======================================================================
# Données personnelles
# ======================================================================

class DonneesEcran(_Ecran):

    def __init__(self, athlete_id_initial=None):
        super().__init__("🔐  Données personnelles", "Le club est responsable des données de ses adhérents, coureurs, "
                         "bénévoles et enfants (RGPD). Ici : le registre des traitements, les durées de conservation et le "
                         "nettoyage, les demandes des personnes, les violations de données. Une aide, pas un avis "
                         "juridique : les guides de la CNIL font référence.", athlete_id_initial)
        self._reg, self._dem, self._inc = [], [], []
        cadre, lc = _cadre("Registre des traitements (d'après les modules allumés)")
        self.t_reg = _table(["Traitement", "Pour quoi faire", "Personnes", "Données", "Base légale", "Qui y a accès",
                             "Combien de temps"], 230)
        lc.addWidget(self.t_reg)
        b = QHBoxLayout()
        bp = _bouton("📄 Registre en PDF", True)
        bp.clicked.connect(self._pdf_registre)
        b.addWidget(bp)
        b.addStretch()
        lc.addLayout(b)
        self.principal.addWidget(cadre)
        cadre, lc = _cadre("Durées de conservation et nettoyage")
        self.t_dur = _table(["Données", "Garder (mois)", "Au-delà aujourd'hui"], 190)
        self.t_dur.doubleClicked.connect(lambda _i: self._duree())
        lc.addWidget(self.t_dur)
        b = QHBoxLayout()
        bd, bn, ba = _bouton("Changer la durée"), _bouton("🧹 Nettoyer ce qui dépasse…", True), _bouton("Anciens adhérents…")
        bd.clicked.connect(self._duree)
        bn.clicked.connect(self._nettoyer)
        ba.clicked.connect(self._anciens)
        for w in (bn, bd, ba):
            b.addWidget(w)
        b.addStretch()
        lc.addLayout(b)
        self.principal.addWidget(cadre)
        cadre, lc = _cadre("Demandes des personnes (réponse sous un mois)")
        self.t_dem = _table(["Reçue le", "Personne", "Demande", "Échéance", "Traitée le", "Réponse"], 170)
        lc.addWidget(self.t_dem)
        b = QHBoxLayout()
        bn2, bx, bef, bt = (_bouton("➕ Nouvelle demande"), _bouton("📤 Copie de ses données (JSON)…"),
                            _bouton("Effacer la personne…"), _bouton("Marquer traitée"))
        bn2.clicked.connect(self._nouvelle_demande)
        bx.clicked.connect(self._exporter)
        bef.clicked.connect(self._effacer)
        bt.clicked.connect(self._traiter)
        for w in (bn2, bx, bef, bt):
            b.addWidget(w)
        b.addStretch()
        lc.addLayout(b)
        self.principal.addWidget(cadre)
        cadre, lc = _cadre("Violations de données (fuite, perte, vol)")
        conduite = QLabel("<br>".join(f"{k}. {_e(x)}" for k, x in enumerate(RG.CONDUITE_VIOLATION, 1)))
        conduite.setWordWrap(True)
        conduite.setTextFormat(Qt.TextFormat.RichText)
        lc.addWidget(conduite)
        self.t_inc = _table(["Constatée le", "Ce qui s'est passé", "Personnes", "CNIL avant le", "CNIL prévenue", "Close"], 150)
        self.t_inc.doubleClicked.connect(lambda _i: self._incident(modifier=True))
        lc.addWidget(self.t_inc)
        b = QHBoxLayout()
        bi = _bouton("➕ Noter une violation")
        bi.clicked.connect(self._incident)
        b.addWidget(bi)
        b.addStretch()
        lc.addLayout(b)
        self.principal.addWidget(cadre)
        self._finir()

    def rafraichir(self):
        self._reg = RG.registre()
        _remplir(self.t_reg, [(t["traitement"], t["finalite"], t["personnes"], t["donnees"], t["base_legale"],
                               t["destinataires"], t["duree"]) for t in self._reg])
        for c in range(1, 7):
            if self.t_reg.columnWidth(c) > 230:
                self.t_reg.setColumnWidth(c, 230)
        self.t_reg.setWordWrap(True)
        self.t_reg.resizeRowsToContents()
        d, n = RG.durees(), RG.a_nettoyer()
        self._cles = list(RG.DUREES_DEFAUT)
        _remplir(self.t_dur, [(RG.LIBELLE_DUREE[k], d[k], n.get(k, "—")) for k in self._cles],
                 {(r, 2): ORANGE for r, k in enumerate(self._cles) if n.get(k)})
        self._dem = RG.demandes()
        _remplir(self.t_dem, [(x["recue_le"], x["nom"], RG.LIBELLE_DEMANDE[x["type"]], x["echeance"], x["traitee_le"] or "",
                               x["reponse"] or "") for x in self._dem],
                 {(r, 3): ROUGE for r, x in enumerate(self._dem) if x["en_retard"]})
        self._inc = RG.incidents()
        _remplir(self.t_inc, [(x["constate_le"].replace("T", " "), x["description"], x["personnes"] or "",
                               x["limite_cnil"].replace("T", " "), x["cnil_le"] or "", "oui" if x["clos"] else "")
                              for x in self._inc])

    def _pdf_registre(self):
        from data.database import obtenir_parametre
        lignes = [(f"<b>{P._e(t['traitement'])}</b>", P._e(t["finalite"]), P._e(t["personnes"]), P._e(t["donnees"]),
                   P._e(t["base_legale"]), P._e(t["destinataires"]), P._e(t["duree"])) for t in self._reg]
        html_ = (P._entete("Registre des traitements", {"nom": obtenir_parametre("nom_structure") or "Association",
                                                         "date_debut": __import__("datetime").date.today().isoformat()},
                           "tenu avec Trail Hub Center")
                 + "<p>Responsable de traitement : l'association (président). Mesures de sécurité communes : base sur "
                   "l'ordinateur du club ou le NAS, serveur en HTTPS, comptes nominatifs avec rôles, mots de passe protégés, "
                   "journal des accès, sauvegardes.</p>"
                 + P._tableau(["Traitement", "Finalité", "Personnes", "Données", "Base légale", "Destinataires", "Durée"],
                              lignes, [12, 16, 11, 19, 14, 14, 14]) + P._pied())
        _ouvrir_pdf(self, "Registre des traitements.pdf", html_, True)

    def _duree(self):
        r = self.t_dur.currentRow()
        if r < 0:
            return
        k = self._cles[r]
        m, ok = QInputDialog.getInt(self, "Durée", f"{RG.LIBELLE_DUREE[k]} : garder combien de mois ?", RG.durees()[k], 1, 240)
        if ok:
            RG.regler_duree(k, m)
            self.rafraichir()

    def _nettoyer(self):
        n = RG.a_nettoyer()
        cles = [k for k in ("positions_gps", "photos", "inscrits") if n.get(k)]
        if not cles:
            QMessageBox.information(self, "Nettoyage", "Rien ne dépasse les durées choisies.")
            return
        txt = "\n".join(f"• {RG.LIBELLE_DUREE[k]} : {n[k]}" for k in cles)
        if QMessageBox.question(self, "Nettoyage", f"Supprimer ou rendre anonyme ce qui dépasse :\n{txt}\n\nLes résultats "
                                "et classements restent. Fais une sauvegarde avant si tu as un doute.") == \
                QMessageBox.StandardButton.Yes:
            f = RG.nettoyer(cles)
            QMessageBox.information(self, "Nettoyage", "Fait : " + ", ".join(f"{RG.LIBELLE_DUREE[k]} {v}" for k, v in f.items()))
            self.rafraichir()

    def _anciens(self):
        l = RG.anciens_adherents()
        if not l:
            QMessageBox.information(self, "Anciens adhérents", "Personne à revoir.")
            return
        QMessageBox.information(self, "Anciens adhérents", f"{len(l)} fiche(s) sans adhésion depuis longtemps (à revoir une "
                                "par une : effacer, ou garder si la personne revient) :\n\n"
                                + "\n".join(f"• {x['nom']} {x['prenom'] or ''} (dernière saison {x['derniere_saison']})"
                                            for x in l[:40]))

    def _personne(self, titre):
        q, ok = QInputDialog.getText(self, titre, "Nom de la personne :")
        if not ok or not q.strip():
            return None
        l = dper.lister(recherche=q)
        if not l:
            QMessageBox.information(self, titre, "Personne trouvée sous ce nom.")
            return None
        if len(l) == 1:
            return l[0]
        noms = [f"{p['nom']} {p['prenom'] or ''} · {p.get('date_naissance') or ''}" for p in l]
        c, ok = QInputDialog.getItem(self, titre, "Laquelle ?", noms, 0, False)
        return l[noms.index(c)] if ok else None

    def _nouvelle_demande(self):
        p = self._personne("Nouvelle demande")
        if not p:
            return
        t, ok = QInputDialog.getItem(self, "Demande", "Que demande-t-elle ?", [l for _c, l in RG.TYPES_DEMANDE], 0, False)
        if ok:
            RG.enregistrer_demande(next(c for c, l in RG.TYPES_DEMANDE if l == t), f"{p['nom']} {p['prenom'] or ''}", p["id"])
            self.rafraichir()

    def _exporter(self):
        d = _ligne_choisie(self.t_dem, self._dem)
        p = {"id": d["personne_id"], "nom": d["nom"]} if d and d.get("personne_id") else self._personne("Copie des données")
        if not p:
            return
        chemin, _ = QFileDialog.getSaveFileName(self, "Copie des données", f"donnees_{p['nom'].split()[0]}.json", "JSON (*.json)")
        if chemin:
            Path(chemin).write_text(RG.export_json(p["id"]), encoding="utf-8")
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(chemin).parent)))

    def _effacer(self):
        d = _ligne_choisie(self.t_dem, self._dem)
        p = {"id": d["personne_id"], "nom": d["nom"]} if d and d.get("personne_id") else self._personne("Effacement")
        if not p:
            return
        if QMessageBox.question(self, "Effacement", f"Effacer {p['nom']} : fiche, adhésions, consentements, carnet, "
                                "présences et résultats ; ses inscriptions deviennent « Anonyme ». C'est définitif "
                                "(sauf restauration d'une sauvegarde).") != QMessageBox.StandardButton.Yes:
            return
        try:
            RG.effacer_personne(p["id"])
        except ValueError as e:
            QMessageBox.warning(self, "Effacement", str(e))
            return
        if d:
            RG.traiter_demande(d["id"], "données effacées")
        self.rafraichir()

    def _traiter(self):
        d = _ligne_choisie(self.t_dem, self._dem)
        if d:
            t, ok = QInputDialog.getText(self, "Demande traitée", "Réponse donnée :")
            if ok:
                RG.traiter_demande(d["id"], t)
                self.rafraichir()

    def _incident(self, modifier=False):
        x = _ligne_choisie(self.t_inc, self._inc) if modifier else None
        spec = [("long", "description", "Ce qui s'est passé", {"hauteur": 70}), ("texte", "donnees", "Données touchées", None),
                ("entier", "personnes", "Nombre de personnes", {"max": 100000}), ("long", "mesures", "Mesures prises", None),
                ("date", "cnil_le", "CNIL prévenue le", None), ("date", "informees_le", "Personnes prévenues le", None),
                ("case", "clos", "", {"texte": "Dossier clos"})]
        d = DialogueChamps(self, "Violation de données", spec, x or {},
                           lambda ch: RG.enregistrer_incident({**ch, "clos": 1 if ch.get("clos") else 0},
                                                              x["id"] if x else None))
        if d.exec():
            self.rafraichir()


# ======================================================================
# Licences
# ======================================================================

class LicencesEcran(_Ecran):

    def __init__(self, athlete_id_initial=None):
        super().__init__("📜  Licences", "Trail Hub Center est un logiciel libre (licence MIT). Il embarque des composants "
                         "d'autres auteurs, chacun sous sa propre licence.", athlete_id_initial)
        from interface.theme import dossier_racine_ressources
        r = dossier_racine_ressources()
        t = QTextBrowser()
        t.setOpenExternalLinks(True)
        t.setMinimumHeight(560)
        textes = []
        for nom in ("THIRD_PARTY_NOTICES.md", "LICENSE"):
            try:
                textes.append((r / nom).read_text(encoding="utf-8"))
            except OSError:
                pass
        t.setMarkdown("\n\n---\n\n".join(textes) or "Fichiers de licence introuvables dans cette installation.")
        self.principal.addWidget(t)
        self._finir()

    def rafraichir(self):
        pass


class MiseEnServiceFenetre(ConteneurOnglets):

    def __init__(self, athlete_id_initial=None):
        super().__init__(titre="Mise en service et données", onglets=[("✅ Mise en service", RecetteEcran),
                                                                       ("🔐 Données personnelles", DonneesEcran),
                                                                       ("📜 Licences", LicencesEcran)],
                         athlete_id_initial=athlete_id_initial)
        self.recette, self.donnees, self.licences = self.ecrans
