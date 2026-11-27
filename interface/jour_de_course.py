"""
Fenêtre « ⏳ Jour de course » : la prochaine course sur un seul écran —
compte à rebours, durée visée, sac à préparer (cases gardées), plan de
ravitaillement heure par heure, météo connue et playlist de la course.

Calculs : noyau/course/jour_de_course.py.
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QMessageBox

from noyau.course import jour_de_course as J
from interface.conteneur_onglets import ConteneurOnglets
from interface.forme_evolution import _EcranAthlete
from interface.calendrier_competitions import _bouton, _cadre, _table, _style_cases
from interface.organisation_logistique import _remplir
from interface.theme import obtenir_couleur_accent


def _h(heures):
    if not heures:
        return "—"
    m = int(round(heures * 60))
    return f"{m // 60} h {m % 60:02d}"


class JourDeCourseEcran(_EcranAthlete):

    def __init__(self, athlete_id_initial=None):
        super().__init__("⏳  Jour de course",
                         "Tout pour ta prochaine course : compte à rebours, sac à préparer, ravitaillement heure par "
                         "heure, météo et playlist. Ajoute la course dans « Courses à venir » ou crée son roadbook.",
                         athlete_id_initial)
        h = QHBoxLayout()
        self.c_rebours = self._carte("Compte à rebours")
        self.c_rebours.valeur.setStyleSheet(f"font-size: 40px; font-weight: 800; color: {obtenir_couleur_accent()};")
        self.c_course = self._carte("Course")
        self.c_duree = self._carte("Durée visée")
        for c in (self.c_rebours, self.c_course, self.c_duree):
            h.addWidget(c, 1)
        self.principal.addLayout(h)

        h = QHBoxLayout()
        cadre, lc = _cadre("Sac à préparer")
        self.sac = QListWidget()
        self.sac.setMinimumHeight(300)
        from interface.theme import PALETTE
        acc = obtenir_couleur_accent()
        self.sac.setStyleSheet(f"QListWidget::indicator {{ width: 16px; height: 16px; border: 1px solid {PALETTE['texte_discret']}; "
                               f"border-radius: 4px; background: {PALETTE['carte_haute']}; }}"
                               f"QListWidget::indicator:checked {{ background: {acc}; border-color: {acc}; }}"
                               "QListWidget::item { padding: 4px 2px; }")
        self.sac.itemChanged.connect(self._coche)
        lc.addWidget(self.sac)
        self.sac_info = QLabel("")
        self.sac_info.setObjectName("texteSecondaire")
        lc.addWidget(self.sac_info)
        h.addWidget(cadre, 1)
        cadre, lc = _cadre("Ravitaillement heure par heure")
        self.t_plan = _table(["Heure", "Glucides", "Eau", "Sodium"], 260)
        lc.addWidget(self.t_plan)
        self.plan_info = QLabel("")
        self.plan_info.setWordWrap(True)
        self.plan_info.setObjectName("texteSecondaire")
        lc.addWidget(self.plan_info)
        h.addWidget(cadre, 1)
        self.principal.addLayout(h)

        cadre, lc = _cadre("Le jour J")
        self.meteo = QLabel("")
        self.meteo.setWordWrap(True)
        lc.addWidget(self.meteo)
        b = QHBoxLayout()
        self.b_playlist = _bouton("🎵 Playlist de la course", True)
        self.b_playlist.clicked.connect(self._playlist)
        b.addWidget(self.b_playlist)
        b.addStretch()
        lc.addLayout(b)
        self.principal.addWidget(cadre)
        self._donnees = None
        self._finaliser()
        _style_cases(self)

    def actualiser(self, *_):
        a = self.athlete_id
        self._donnees = J.preparer(a) if a is not None else None
        d = self._donnees
        self.sac.blockSignals(True)
        self.sac.clear()
        if not d:
            self.c_rebours.valeur.setText("—")
            self.c_rebours.detail.setText("Aucune course à venir.")
            self.c_course.valeur.setText("—")
            self.c_course.detail.setText("Ajoute-la dans Courses à venir.")
            self.c_duree.valeur.setText("—")
            self.c_duree.detail.setText("")
            self.t_plan.setRowCount(0)
            self.meteo.setText("")
            self.b_playlist.setEnabled(False)
            self.sac.blockSignals(False)
            return
        c = d["course"]
        self.c_rebours.valeur.setText(d["rebours"]["texte"])
        self.c_rebours.detail.setText(str(c["date"])[:10])
        self.c_course.valeur.setText(c["nom"])
        self.c_course.detail.setText(" · ".join(x for x in (
            f"{c['distance_km']:g} km".replace(".", ",") if c.get("distance_km") else "",
            f"{int(c['denivele_m'])} m D+" if c.get("denivele_m") else "", c.get("lieu") or "",
            "roadbook prêt" if d.get("roadbook") else "") if x))
        self.c_duree.valeur.setText(_h(d["duree_h"]))
        self.c_duree.detail.setText(d["origine_duree"] or "")
        sections = {}
        for e in d["sac"]:
            sections.setdefault(e.get("section", "Divers"), []).append(e)
        for sec, items in sections.items():
            titre = QListWidgetItem(sec)
            titre.setFlags(Qt.ItemFlag.NoItemFlags)
            f = titre.font()
            f.setBold(True)
            titre.setFont(f)
            self.sac.addItem(titre)
            for e in items:
                it = QListWidgetItem(e["texte"])
                it.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable)
                it.setCheckState(Qt.CheckState.Checked if e.get("coche") else Qt.CheckState.Unchecked)
                it.setData(Qt.ItemDataRole.UserRole, (e.get("section"), e["texte"]))
                self.sac.addItem(it)
        self.sac.blockSignals(False)
        self._compter()
        p = d.get("plan")
        if p:
            _remplir(self.t_plan, [(f"{x['heure']}ᵉ h", f"{x['glucides_g']} g", f"{x['eau_ml']} ml", f"{x['sodium_mg']} mg")
                                   for x in p["heures"]])
            self.plan_info.setText(" · ".join(p.get("notes") or []) or
                                   f"Environ {p.get('nb_gels', 0)} gels et {p.get('nb_barres', 0)} barres (estimation).")
        else:
            self.t_plan.setRowCount(0)
            self.plan_info.setText("Indique la distance de la course pour calculer le ravitaillement.")
        m = d.get("meteo")
        self.meteo.setText(f"Météo au départ ({m['parcours']}, AllTrails) : {m['texte']}" if m else
                           "Météo : ouvre l'écran Météo la veille, ou cherche un parcours proche du départ dans "
                           "Connecteurs Claude pour recevoir la prévision.")
        self.b_playlist.setEnabled(True)
        self.b_playlist.setText(f"🎵 Playlist de la course ({_h(d['duree_h'])})")

    def _compter(self):
        n = coches = 0
        for i in range(self.sac.count()):
            it = self.sac.item(i)
            if it.flags() & Qt.ItemFlag.ItemIsUserCheckable:
                n += 1
                coches += it.checkState() == Qt.CheckState.Checked
        self.sac_info.setText(f"{coches} sur {n} prêts." + (" Le sac est bouclé !" if n and coches == n else ""))

    def _coche(self, _item):
        d = self._donnees
        if not d:
            return
        etat = {}
        for i in range(self.sac.count()):
            it = self.sac.item(i)
            cle = it.data(Qt.ItemDataRole.UserRole)
            if cle:
                etat[tuple(cle)] = it.checkState() == Qt.CheckState.Checked
        for e in d["sac"]:
            e["coche"] = etat.get((e.get("section"), e["texte"]), e.get("coche", False))
        J.enregistrer_sac(d["course"], d["sac"])
        self._compter()

    def _playlist(self):
        d = self._donnees
        if not d:
            return
        from noyau.donnees import connecteurs as D
        from noyau.connecteurs import pont as P
        D.demander_playlist(self.athlete_id, d["course"]["nom"], d["playlist_min"],
                            style="funk et disco des années 80 et 90, entraînant pour une course de trail")
        envoye = P.ecrire_demandes() if P.dossier() else None
        QMessageBox.information(self, "Playlist", "Demande déposée pour Claude : la playlist arrivera au prochain passage."
                                if envoye is not None else
                                "Demande enregistrée. Choisis le dossier partagé (Connecteurs Claude > Pont) pour qu'elle parte.")


class JourDeCourseFenetre(ConteneurOnglets):

    def __init__(self, athlete_id_initial=None):
        super().__init__(titre="Jour de course", onglets=[("⏳ Jour J", JourDeCourseEcran)],
                         athlete_id_initial=athlete_id_initial)
        self.ecran = self.ecrans[0]
