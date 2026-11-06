"""
Jour de course (Trail Hub Center, étape 6) — onglet « 🧭 Jour de course » de la fenêtre Organisation :
tableau de commandement du PC course (coureurs en course, à chercher, hors délai, arrivés, abandons),
points de contrôle et pointages, incidents et leur suivi, bénévoles présents à leur poste, carte
schématique, Trail Live (page publique des proches, positions importées d'un traceur).
Aucune requête SQL ici : noyau/donnees/commandement.py.
"""

from pathlib import Path

from PySide6.QtCore import Qt, QByteArray, QTimer
from PySide6.QtGui import QGuiApplication
from PySide6.QtSvgWidgets import QSvgWidget
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFileDialog, QHBoxLayout, QInputDialog, QLabel, QLineEdit, QMessageBox,
)

from noyau.donnees import commandement as dk, organisation as dor
from noyau.organisation import commandement as K
from interface.organisation import _EcranOrga, VERT, ORANGE, ROUGE, GRIS
from interface.calendrier_competitions import _bouton, _cadre, _table
from interface.organisation_logistique import DialogueChamps, _remplir, _ligne_choisie, _lignes_choisies, _km

FILTRES = (("surveiller", "À surveiller (à chercher, hors délai)"), ("en_course", "En course"), ("tous", "Tous"),
           ("arrives", "Arrivés"), ("hors", "Abandons, non partis"))
COULEUR_ETAT = {"à chercher": ORANGE, "hors délai": ROUGE, "arrivé": VERT, "abandon": GRIS, "disqualifié": GRIS,
                "non partant": GRIS, "pas parti": GRIS}


class CommandementOrga(_EcranOrga):

    def __init__(self, athlete_id_initial=None):
        super().__init__("🧭  Jour de course", "Le tableau du PC course : où en est chaque coureur, qui n'a pas été vu au "
                         "point suivant, les incidents et les bénévoles à leur poste. Les heures attendues sont des "
                         "estimations (allure de chaque coureur depuis le départ). Les bénévoles pointent et signalent "
                         "depuis leur téléphone (Outils > Serveur).", athlete_id_initial)
        ligne = QHBoxLayout()
        self.cartes = {k: self._carte(t) for k, t in (("en_course", "En course"), ("a_chercher", "À chercher"),
                                                     ("arrives", "Arrivés"), ("abandons", "Abandons"),
                                                     ("incidents", "Incidents ouverts"), ("benevoles", "Bénévoles à leur poste"))}
        for c in self.cartes.values():
            ligne.addWidget(c, 1)
        self.principal.addLayout(ligne)
        h = QHBoxLayout()
        self.auto = QCheckBox("Actualiser toutes les 30 secondes")
        self.auto.setChecked(True)
        maj = _bouton("🔄 Actualiser")
        maj.clicked.connect(self.rafraichir)
        self.heure = QLabel("")
        self.heure.setObjectName("texteSecondaire")
        h.addWidget(self.auto)
        h.addWidget(maj)
        h.addWidget(self.heure)
        h.addStretch()
        self.principal.addLayout(h)
        # carte
        cadre, lc = _cadre("Parcours")
        self.carte = QSvgWidget()
        self.carte.setMinimumHeight(260)
        lc.addWidget(self.carte)
        self.principal.addWidget(cadre)
        # incidents
        cadre, lc = _cadre("Incidents")
        self.table_inc = _table(["N°", "Heure", "Gravité", "Type", "Où", "Coureur", "Ce qui se passe", "Statut", "Suivi par"], 220)
        self.table_inc.doubleClicked.connect(lambda _i: self._voir_incident())
        lc.addWidget(self.table_inc)
        b = QHBoxLayout()
        for t, f, p in (("🚑 Nouvel incident", self._nouvel_incident, True), ("🙋 Je m'en occupe", self._prendre, False),
                        ("📝 Ajouter un suivi", self._suivi, False), ("✅ Clore", self._clore, False),
                        ("↩️ Rouvrir", self._rouvrir, False), ("🔎 Détail", self._voir_incident, False)):
            w = _bouton(t, p)
            w.clicked.connect(f)
            b.addWidget(w)
        b.addStretch()
        lc.addLayout(b)
        self.principal.addWidget(cadre)
        # coureurs
        cadre, lc = _cadre("Coureurs")
        h = QHBoxLayout()
        self.filtre = QComboBox()
        for k, t in FILTRES:
            self.filtre.addItem(t, k)
        self.filtre.setCurrentIndex(2)
        self.filtre.currentIndexChanged.connect(lambda _i: self._remplir_coureurs())
        self.recherche = QLineEdit()
        self.recherche.setPlaceholderText("Dossard ou nom")
        self.recherche.textChanged.connect(lambda _t: self._remplir_coureurs())
        h.addWidget(self.filtre)
        h.addWidget(self.recherche, 1)
        lc.addLayout(h)
        self.table = _table(["Dos.", "Coureur", "Épreuve", "État", "Dernier point", "À", "Prochain", "Attendu vers", "Alerte",
                             "Arrivée estimée"], 320)
        lc.addWidget(self.table)
        b = QHBoxLayout()
        self.saisie = QLineEdit()
        self.saisie.setPlaceholderText("Dossard")
        self.saisie.setMaximumWidth(110)
        self.saisie.returnPressed.connect(self._pointer)
        self.point_saisie = QComboBox()
        poi = _bouton("📍 Pointer", True)
        poi.clicked.connect(self._pointer)
        abd = _bouton("Abandon du coureur choisi")
        abd.clicked.connect(self._abandon)
        for w in (QLabel("Pointer à la main :"), self.saisie, self.point_saisie, poi, abd):
            b.addWidget(w)
        b.addStretch()
        lc.addLayout(b)
        self.retour = QLabel("")
        lc.addWidget(self.retour)
        self.principal.addWidget(cadre)
        # points de contrôle et postes
        l2 = QHBoxLayout()
        cadre, lc = _cadre("Points de contrôle")
        self.table_pts = _table(["Point", "Type", "Km", "Barrière", "Épreuves", "Passés"], 200)
        self.table_pts.doubleClicked.connect(lambda _i: self._modifier_point())
        lc.addWidget(self.table_pts)
        b = QHBoxLayout()
        for t, f, p in (("✨ Depuis les ravitaillements", self._points_ravitos, False), ("➕ Point", self._ajouter_point, False),
                        ("✏️", self._modifier_point, False), ("🗑️", self._supprimer_point, False)):
            w = _bouton(t, p)
            w.clicked.connect(f)
            b.addWidget(w)
        b.addStretch()
        lc.addLayout(b)
        l2.addWidget(cadre, 1)
        cadre, lc = _cadre("Bénévoles à leur poste")
        self.table_postes = _table(["Poste", "Présents", "Pas encore là"], 200)
        lc.addWidget(self.table_postes)
        l2.addWidget(cadre, 1)
        self.principal.addLayout(l2)
        # Trail Live
        cadre, lc = _cadre("Trail Live : page publique et positions")
        h = QHBoxLayout()
        self.noms = QCheckBox("Montrer les noms des coureurs")
        self.noms.setChecked(True)
        self.tel_pc = QLineEdit()
        self.tel_pc.setPlaceholderText("Téléphone du PC course (montré aux bénévoles sans réseau)")
        ouvrir = _bouton("🌍 Ouvrir la page publique", True)
        ouvrir.clicked.connect(self._live)
        fermer = _bouton("Fermer la page publique")
        fermer.clicked.connect(self._fermer_live)
        pos = _bouton("📥 Importer des positions (CSV, GPX)")
        pos.clicked.connect(self._positions)
        for w in (self.noms, self.tel_pc, ouvrir, fermer, pos):
            h.addWidget(w)
        lc.addLayout(h)
        self.info_live = QLabel("")
        self.info_live.setWordWrap(True)
        self.info_live.setTextFormat(Qt.TextFormat.RichText)
        self.info_live.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        lc.addWidget(self.info_live)
        self.principal.addWidget(cadre)
        self.principal.addStretch()
        self._lignes, self._vues, self._inc, self._pts = [], [], [], []
        self._minuteur = QTimer(self)
        self._minuteur.setInterval(30000)
        self._minuteur.timeout.connect(lambda: self.auto.isChecked() and self.isVisible() and self.rafraichir())
        self._minuteur.start()
        self._finir()

    # ------------------------------------------------------------------ rafraîchir
    def rafraichir(self):
        from datetime import datetime
        ev = self.evenement_id
        self.heure.setText(f"à jour à {datetime.now():%H:%M:%S}")
        if not ev:
            for c in self.cartes.values():
                c.valeur.setText("—")
            return
        t = dk.tableau(ev)
        self._lignes = dk.situation(ev)
        self._inc = dk.incidents(ev)
        self._pts = t["points"]
        b = t["bilan"]
        c = self.cartes
        c["en_course"].valeur.setText(str(b["en_course"]))
        c["en_course"].detail.setText(f"{b['hors_delai']} hors délai" if b["hors_delai"] else "")
        c["a_chercher"].valeur.setText(str(b["a_chercher"]))
        c["a_chercher"].valeur.setStyleSheet(f"font-size: 24px; font-weight: 700; color: {ORANGE if b['a_chercher'] else VERT};")
        c["a_chercher"].detail.setText("pas vus au point suivant")
        c["arrives"].valeur.setText(str(b["arrives"]))
        c["abandons"].valeur.setText(str(b["abandons"]))
        c["abandons"].detail.setText(f"{b['non_partis']} non parti(s)")
        c["incidents"].valeur.setText(str(len(t["incidents_ouverts"])))
        c["incidents"].valeur.setStyleSheet(f"font-size: 24px; font-weight: 700; color: {ROUGE if t['urgents'] else VERT};")
        c["incidents"].detail.setText(f"dont {t['urgents']} urgent(s)" if t["urgents"] else "")
        c["benevoles"].valeur.setText(f"{t['benevoles_presents']} / {t['benevoles_attendus']}")
        # incidents
        coul = {}
        for r, i in enumerate(self._inc):
            coul[r] = GRIS if i["statut"] == "clos" else (ROUGE if i["gravite"] == "urgent" else None)
        _remplir(self.table_inc, [(i["numero"], i["horodatage"][11:16], i["libelle_gravite"], i["libelle_type"],
                                   i["point"] or (f"km {_km(i['km'])}" if i["km"] is not None else ""),
                                   f"{i['dossard'] or ''} {i['coureur']}".strip(), (i["description"] or "")[:70],
                                   K.LIBELLE_STATUT_INCIDENT.get(i["statut"], ""), i["pris_par"] or "") for i in self._inc], coul)
        self._remplir_coureurs()
        # points
        passes = {}
        from noyau.donnees import chrono as dch
        for p in dch.passages(ev):
            passes.setdefault(p["point"], set()).add(p["dossard"])
        noms_ep = {e["id"]: e["nom"] for e in dor.epreuves(ev)}
        _remplir(self.table_pts, [(p["nom"], p["libelle_type"], _km(p["km"]), p["barriere_horaire"] or "",
                                   ", ".join(noms_ep.get(x, "") for x in p["epreuve_ids"]) or "toutes",
                                   len(passes.get(p["cle"], ()))) for p in self._pts])
        actuel = self.point_saisie.currentData()
        self.point_saisie.clear()
        for p in self._pts:
            self.point_saisie.addItem(p["nom"], p["id"])
        self.point_saisie.addItem("Arrivée", "arrivee")
        self.point_saisie.setCurrentIndex(max(0, self.point_saisie.findData(actuel)))
        postes = [p for p in t["postes"] if p["affectes"]]
        coul = {(r, 1): (VERT if p["presents"] >= p["affectes"] else ORANGE) for r, p in enumerate(postes)}
        _remplir(self.table_postes, [(p["poste"], f"{p['presents']} / {p['affectes']}", ", ".join(p["absents"]))
                                     for p in postes], coul)
        # carte
        pos = dk.dernieres_positions(ev)
        eps = dor.epreuves(ev)
        cour = [{"dossard": l["dossard"], "km": l["km"], "etat": l["etat"], **({k: pos[l["dossard"]][k] for k in ("lat", "lon")}
                                                                               if l["dossard"] in pos else {})} for l in self._lignes]
        svg = K.svg_carte(self._pts, cour, [i for i in self._inc if i["statut"] != "clos"], 1000, 280,
                          max([e.get("distance_km") or 0 for e in eps] + [1]), self._sombre())
        self.carte.load(QByteArray(svg.encode("utf-8")))
        self._infos_live()

    @staticmethod
    def _sombre():
        try:
            from interface.theme import PALETTE
            c = PALETTE.get("fond", "#000000").lstrip("#")
            return sum(int(c[i:i + 2], 16) for i in (0, 2, 4)) < 3 * 128
        except Exception:
            return True

    def _remplir_coureurs(self):
        f = self.filtre.currentData()
        q = self.recherche.text().strip().lower()
        garde = {"surveiller": lambda l: l["etat"] in ("à chercher", "hors délai"),
                 "en_course": lambda l: l["etat"] in ("en course", "à chercher", "hors délai"),
                 "arrives": lambda l: l["etat"] == "arrivé", "hors": lambda l: l["etat"] in ("abandon", "disqualifié",
                                                                                            "non partant", "pas parti"),
                 "tous": lambda l: True}[f or "tous"]
        self._vues = [l for l in self._lignes if garde(l) and (not q or q in f"{l['dossard']} {l['nom']}".lower())]
        coul = {(r, 3): COULEUR_ETAT.get(l["etat"]) for r, l in enumerate(self._vues)}
        coul.update({(r, 8): ROUGE for r, l in enumerate(self._vues) if l["alerte"]})
        _remplir(self.table, [(l["dossard"], l["nom"], l["epreuve"], l["etat"], l["dernier"],
                               (l["dernier_heure"] or "")[11:16], l["prochain"], (l["attendu"] or "")[11:16], l["alerte"] or "",
                               K.texte_temps(l["temps"]) if l["temps"] else (l["projection"] or "")[11:16])
                              for l in self._vues], coul)

    # ------------------------------------------------------------------ pointage et abandon
    def _pointer(self):
        if not self.evenement_id or not self.saisie.text().strip().isdigit():
            return
        try:
            r = dk.pointer(self.evenement_id, self.point_saisie.currentData(), int(self.saisie.text()), source="PC course")
        except dk.ErreurCommandement as e:
            self.retour.setText(str(e))
            return
        i = r["inscrit"]
        self.retour.setText(f"✅ {self.saisie.text()} {((i['prenom'] or '') + ' ' + i['nom']) if i else ''} à "
                            f"{self.point_saisie.currentText()} ({r['heure'][11:19]})" + (f" · ⚠️ {r['avertissement']}"
                                                                                           if r["avertissement"] else ""))
        self.saisie.clear()
        self.rafraichir()

    def _abandon(self):
        l = _ligne_choisie(self.table, self._vues)
        if l and QMessageBox.question(self, "Abandon", f"Abandon du dossard {l['dossard']} ({l['nom']}) ?") == \
                QMessageBox.StandardButton.Yes:
            dk.marquer_abandon(self.evenement_id, l["dossard"])
            self.rafraichir()

    # ------------------------------------------------------------------ incidents
    def _spec_incident(self):
        return [("choix", "gravite", "Gravité", {"choix": K.GRAVITES, "defaut": "moyen"}),
                ("choix", "type", "Type", {"choix": K.TYPES_INCIDENT}), ("texte", "dossard", "Dossard", None),
                ("choix", "point_id", "Où", {"choix": [(None, "— sur le parcours —")] + [(p["id"], p["nom"]) for p in self._pts]}),
                ("reel", "km", "Kilomètre", {"suffixe": " km"}), ("long", "description", "Ce qui se passe", None),
                ("texte", "signale_par", "Signalé par", None)]

    def _nouvel_incident(self):
        if self.evenement_id:
            d = DialogueChamps(self, "Nouvel incident", self._spec_incident(), {"gravite": "moyen", "type": "blessure"},
                               lambda c: dk.signaler(self.evenement_id, {**c, "km": c["km"] or None}, c.get("signale_par") or "PC course"))
            if d.exec():
                self.rafraichir()

    def _choisi(self):
        return _ligne_choisie(self.table_inc, self._inc)

    def _prendre(self):
        i = self._choisi()
        if i:
            dk.prendre_en_charge(i["id"], "PC course")
            self.rafraichir()

    def _suivi(self):
        i = self._choisi()
        if i:
            t, ok = QInputDialog.getText(self, f"Incident n°{i['numero']}", "Ce qui a été fait :")
            if ok and t.strip():
                dk.ajouter_suivi(i["id"], t, "PC course")
                self.rafraichir()

    def _clore(self):
        i = self._choisi()
        if i:
            t, ok = QInputDialog.getText(self, f"Clore l'incident n°{i['numero']}", "Comment il s'est terminé :")
            if ok:
                dk.clore(i["id"], "PC course", t or None)
                if i["type"] == "abandon" and i["dossard"] and QMessageBox.question(
                        self, "Abandon", f"Noter l'abandon du dossard {i['dossard']} dans le classement ?") == QMessageBox.StandardButton.Yes:
                    dk.marquer_abandon(self.evenement_id, i["dossard"])
                self.rafraichir()

    def _rouvrir(self):
        i = self._choisi()
        if i and i["statut"] == "clos":
            dk.rouvrir(i["id"], "PC course")
            self.rafraichir()

    def _voir_incident(self):
        i = self._choisi()
        if not i:
            return
        suivi = "\n".join(f"{s['heure'][11:16]} {s['par']} : {s['texte']}" for s in i["suivi"]) or "—"
        QMessageBox.information(self, f"Incident n°{i['numero']}",
                                f"{i['libelle_gravite']} · {i['libelle_type']} · {i['horodatage'][11:16]}\n"
                                f"Où : {i['point'] or ('km ' + _km(i['km']) if i['km'] is not None else '?')}\n"
                                f"Coureur : {i['dossard'] or '—'} {i['coureur']}\nSignalé par : {i['signale_par'] or '?'}\n\n"
                                f"{i['description'] or ''}\n\nSuivi :\n{suivi}")

    # ------------------------------------------------------------------ points de contrôle
    def _spec_point(self):
        eps = [(e["id"], e["nom"]) for e in dor.epreuves(self.evenement_id)]
        return [("texte", "nom", "Nom", None), ("choix", "type", "Type", {"choix": K.TYPES_POINT}),
                ("reel", "km", "Kilomètre", {"suffixe": " km"}), ("heure", "barriere_horaire", "Barrière horaire", None),
                ("multi", "epreuve_ids", "Épreuves (aucune cochée = toutes)", {"choix": eps}),
                ("reel", "lat", "Latitude (facultatif)", {"decimales": 6, "max": 90}),
                ("reel", "lon", "Longitude (facultatif)", {"decimales": 6, "max": 180}), ("long", "notes", "Notes", None)]

    def _ajouter_point(self):
        if self.evenement_id:
            d = DialogueChamps(self, "Point de contrôle", self._spec_point(), {"type": "pointage"},
                               lambda c: dk.enregistrer_point(self.evenement_id, c))
            if d.exec():
                self.rafraichir()

    def _modifier_point(self):
        p = _ligne_choisie(self.table_pts, self._pts)
        if p:
            d = DialogueChamps(self, "Point de contrôle", self._spec_point(), p,
                               lambda c: dk.enregistrer_point(self.evenement_id, c, p["id"]))
            if d.exec():
                self.rafraichir()

    def _supprimer_point(self):
        p = _ligne_choisie(self.table_pts, self._pts)
        if p and QMessageBox.question(self, "Point", f"Supprimer « {p['nom']} » ? Les pointages restent enregistrés.") == \
                QMessageBox.StandardButton.Yes:
            dk.supprimer_point(p["id"])
            self.rafraichir()

    def _points_ravitos(self):
        if self.evenement_id:
            n = dk.creer_points_depuis_ravitaillements(self.evenement_id)
            QMessageBox.information(self, "Points de contrôle", f"{n} point(s) créé(s) depuis les ravitaillements.")
            self.rafraichir()

    # ------------------------------------------------------------------ Trail Live
    def _infos_live(self):
        r = dk.reglages_live(self.evenement_id) if self.evenement_id else None
        if not r:
            self.info_live.setText("")
            return
        if r["pc_telephone"] and not self.tel_pc.text():
            self.tel_pc.setText(r["pc_telephone"])
        if not r["jeton"]:
            self.info_live.setText("Page publique fermée.")
            return
        from noyau.serveur import serveur as S, demarrage as DM
        base = None
        if S.actif():
            base = S.infos()["adresses"][0]
        elif DM.etat.get("mode") == "serveur":
            base = DM.configuration()["url"]
        url = f"{base}/live/{r['jeton']}" if base else f"(adresse du serveur)/live/{r['jeton']}"
        self.info_live.setText(f"Page publique ouverte : <code>{url}</code> · noms {'affichés' if r['noms'] else 'cachés'}. "
                               "Les positions GPS ne sont montrées que pour les coureurs qui ont donné leur accord "
                               "(consentement « géolocalisation »).")

    def _live(self):
        if self.evenement_id:
            dk.activer_live(self.evenement_id, self.noms.isChecked(), self.tel_pc.text().strip() or None)
            self._infos_live()
            QGuiApplication.clipboard().setText(self.info_live.text().split("<code>")[-1].split("</code>")[0])

    def _fermer_live(self):
        if self.evenement_id:
            dk.desactiver_live(self.evenement_id)
            self._infos_live()

    def _positions(self):
        if not self.evenement_id:
            return
        chemin, _ = QFileDialog.getOpenFileName(self, "Positions", "", "Positions (*.csv *.txt *.gpx)")
        if not chemin:
            return
        dossard = None
        if chemin.lower().endswith(".gpx"):
            dossard, ok = QInputDialog.getInt(self, "Positions", "Dossard du coureur de ce GPX :", 1, 1, 100000)
            if not ok:
                return
        self.importer_positions(chemin, dossard)

    def importer_positions(self, chemin, dossard=None):
        try:
            r = dk.importer_positions(self.evenement_id, Path(chemin).read_bytes(), Path(chemin).name, dossard)
        except dk.ErreurCommandement as e:
            QMessageBox.warning(self, "Positions", str(e))
            return None
        self.retour.setText(f"{r['ajoutees']} position(s) ajoutée(s) sur {r['lues']} lue(s).")
        self.rafraichir()
        return r
