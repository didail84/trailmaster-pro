"""
Écrans santé & charge de la v98 :
  - SommeilRecuperation : dette de sommeil (S2), HRV avec bande normale
    (S3), FC de repos avec alerte (S4), acclimatation à la chaleur (S10)
  - ChargeEquilibre : monotonie et contrainte (S5), hausse de charge par
    semaine (S6), répartition facile / dur 80-20 (E4)
  - PoidsLisse : poids lissé et objectif (S7)

Tous les chiffres viennent de data/metriques.py.
"""

from datetime import date

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QPushButton, QProgressDialog, QInputDialog, QApplication, QMessageBox,
)

import data.metriques as met
from interface.forme_evolution import _EcranAthlete
from interface.apercu_widgets import virgule
from interface.courbe_widget import CourbeBarres
from interface.outils_ui import notifier

VERT, ORANGE, ROUGE, BLEU, GRIS = "#66BB6A", "#FFA726", "#EF5350", "#42A5F5", "#9AA7AE"


def _fmt_jour(j):
    return j.strftime("%d/%m")


def _couleur_niveau(niveau):
    return {"ok": VERT, "bonne": VERT, "equilibree": VERT, "acclimate": VERT,
            "attention": ORANGE, "moyenne": ORANGE, "en_cours": ORANGE, "haute": ORANGE,
            "forte": ROUGE, "alerte": ROUGE, "elevee": ROUGE, "basse": ORANGE, "baisse": BLEU,
            "faible": GRIS}.get(niveau, GRIS)


def _pastille(texte, niveau):
    return f'<span style="color:{_couleur_niveau(niveau)}">● {texte}</span>'


def _vide(carte, valeur="—", detail=""):
    carte.valeur.setText(valeur)
    carte.valeur.setStyleSheet("font-size: 24px; font-weight: 700;")
    carte.detail.setText(detail)


# ----------------------------------------------------------------------
# Sommeil, HRV, FC repos, chaleur
# ----------------------------------------------------------------------

class SommeilRecuperation(_EcranAthlete):

    def __init__(self, athlete_id_initial=None):
        super().__init__(
            "😴  Sommeil, HRV et cœur au repos",
            "Ce que ton corps dit de sa récupération. Les courbes ne relient que les jours réellement "
            "mesurés (montre portée) : aucune valeur n'est inventée.",
            athlete_id_initial,
        )
        ligne = QHBoxLayout()
        ligne.setSpacing(15)
        self.cartes = {}
        for cle, titre in (("dette", "Dette de sommeil (14 j)"), ("hrv", "HRV de nuit (7 j)"),
                           ("fc", "FC de repos (3 derniers jours)"), ("chaleur", "Acclimatation à la chaleur")):
            self.cartes[cle] = self._carte(titre)
            ligne.addWidget(self.cartes[cle], 1)
        self.principal.addLayout(ligne)

        self.c_sommeil = self._cadre_courbe(
            "Sommeil et dette", "Heures dormies par nuit, et dette cumulée par rapport à ton objectif "
            "(les nuits longues effacent les courtes).", 240)
        self.c_sommeil.courbe.echelle_ajustee = True
        self.principal.addWidget(self.c_sommeil)

        self.c_hrv = self._cadre_courbe(
            "HRV de nuit et bande normale",
            "La zone verte est ta variabilité habituelle (moyenne sur 28 jours ± 1 écart-type). "
            "Sous la bande plusieurs jours de suite : récupération incomplète.", 260)
        self.c_hrv.courbe.echelle_ajustee = True
        self.principal.addWidget(self.c_hrv)

        self.c_fc = self._cadre_courbe(
            "FC de repos", "Une FC de repos qui monte de 3 à 5 bpm au-dessus de ta base signale souvent "
            "fatigue, maladie qui arrive ou manque de sommeil.", 240)
        self.c_fc.courbe.echelle_ajustee = True
        self.principal.addWidget(self.c_fc)

        self.note_chaleur = QLabel("")
        self.note_chaleur.setObjectName("texteSecondaire")
        self.note_chaleur.setWordWrap(True)
        self.note_chaleur.setTextFormat(Qt.TextFormat.RichText)
        self.bouton_meteo = QPushButton("🌡️ Compléter la météo de mes sorties (internet)")
        self.bouton_meteo.setObjectName("boutonPrincipal")
        self.bouton_meteo.clicked.connect(self._completer_meteo)
        self.principal.addWidget(self.note_chaleur)
        self.principal.addWidget(self.bouton_meteo, 0, Qt.AlignmentFlag.AlignLeft)
        self.principal.addStretch()
        self._finaliser()

    def _completer_meteo(self):
        a = self.athlete_id
        if a is None:
            return
        dlg = QProgressDialog("Récupération de la météo des sorties…", "Annuler", 0, 40, self)
        dlg.setWindowModality(Qt.WindowModality.WindowModal)
        dlg.setMinimumDuration(0)

        def prog(n, total):
            dlg.setMaximum(max(total, 1))
            dlg.setValue(n)
            QApplication.processEvents()

        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            ok, ko, err = met.completer_meteo(a, nb_jours=60, progression=prog)
        finally:
            QApplication.restoreOverrideCursor()
            dlg.close()
        if ok:
            notifier(f"Météo ajoutée pour {ok} sortie(s)", parent=self)
        elif ko:
            QMessageBox.information(self, "Météo", f"Impossible de récupérer la météo ({err}). "
                                    "Vérifie ta connexion internet et réessaie.")
        else:
            notifier("Toutes les sorties récentes ont déjà leur météo", "info", parent=self)
        self.actualiser()

    def actualiser(self):
        a = self.athlete_id
        for c in self.cartes.values():
            _vide(c)
        for cadre in (self.c_sommeil, self.c_hrv, self.c_fc):
            cadre.courbe.definir_series([])
            cadre.courbe.bande = None
            cadre.courbe.reperes = []
        self.note_chaleur.setText("")
        if a is None:
            return

        # --- sommeil
        d = met.dette_sommeil(a, 14)
        if d["dette_h"] is None:
            self.cartes["dette"].detail.setText("Aucune nuit enregistrée sur 14 jours.")
        else:
            self.cartes["dette"].valeur.setText(f"{virgule(d['dette_h'], 1)} h")
            txt = {"ok": "Dette faible", "attention": "Dette à rattraper", "forte": "Forte dette"}[d["niveau"]]
            extra = f" · {d['nb_estimes']} nuit(s) estimée(s) d'après ton rythme" if d["nb_estimes"] else ""
            self.cartes["dette"].detail.setText(
                _pastille(txt, d["niveau"]) + f"<br>moyenne {virgule(d['moyenne_h'], 1)} h / objectif "
                f"{virgule(d['objectif'], 1)} h{extra}")
            self.c_sommeil.courbe.reperes = [(d["objectif"], f"objectif {virgule(d['objectif'], 1)} h", GRIS)]
            self.c_sommeil.courbe.definir_series([
                {"nom": "Sommeil (h)", "couleur": BLEU, "valeurs": [(_fmt_jour(j), h) for j, h in d["serie"]]},
                {"nom": "Dette cumulée (h)", "couleur": ORANGE, "valeurs": [(_fmt_jour(j), v) for j, v in d["courbe"]]},
            ])

        # --- HRV
        h = met.hrv_avec_bande(a, 90)
        if not h["points"]:
            self.cartes["hrv"].detail.setText("Pas de HRV : importe ta santé Garmin (Import & Synchro).")
        else:
            texte = {"equilibree": "Dans ta bande normale", "basse": "Sous ta bande normale",
                     "haute": "Au-dessus de ta bande", None: "Base en construction"}[h["statut"]]
            self.cartes["hrv"].valeur.setText(f"{round(h['moyenne_7j'])} ms")
            self.cartes["hrv"].detail.setText(_pastille(texte, h["statut"] or "faible"))
            self.c_hrv.courbe.bande = [(p[2], p[3]) if p[2] is not None else None for p in h["points"]]
            self.c_hrv.courbe.bande_nom = "Bande normale"
            self.c_hrv.courbe.definir_series([
                {"nom": "HRV (ms)", "couleur": "#AB47BC", "valeurs": [(_fmt_jour(p[0]), p[1]) for p in h["points"]]}])

        # --- FC repos
        f = met.fc_repos_et_alerte(a, 90)
        if not f["points"]:
            self.cartes["fc"].detail.setText("Pas de FC de repos : importe ta santé Garmin.")
        else:
            if f["ecart"] is not None:
                signe = "+" if f["ecart"] > 0 else "−"
                self.cartes["fc"].valeur.setText(f"{signe}{virgule(abs(f['ecart']), 1)} bpm")
                txt = {"ok": "Normale", "attention": "Un peu haute", "alerte": "Haute : repos conseillé"}[f["niveau"]]
                self.cartes["fc"].detail.setText(_pastille(txt, f["niveau"]) +
                                                 f"<br>base {round(f['base'])} bpm · dernière {round(f['derniere'])}")
                self.c_fc.courbe.reperes = [(f["base"], f"base {round(f['base'])} bpm", GRIS),
                                            (f["base"] + 5, "alerte +5", ROUGE)]
            else:
                self.cartes["fc"].valeur.setText(f"{round(f['derniere'])} bpm")
                self.cartes["fc"].detail.setText("Base en construction (5 jours de mesure minimum).")
            self.c_fc.courbe.definir_series([
                {"nom": "FC repos (bpm)", "couleur": ROUGE, "valeurs": [(_fmt_jour(j), v) for j, v in f["points"]]}])

        # --- chaleur
        c = met.acclimatation_chaleur(a, 14)
        if c["niveau"] is None:
            self.cartes["chaleur"].detail.setText("Pas de température de sortie : utilise le bouton ci-dessous.")
            self.note_chaleur.setText("Pour mesurer ton acclimatation, il faut la température de tes sorties. "
                                      "Le bouton récupère la météo du lieu et de l'heure de chaque sortie (internet).")
        else:
            txt = {"acclimate": "Acclimaté", "en_cours": "En cours", "faible": "Peu exposé"}[c["niveau"]]
            self.cartes["chaleur"].valeur.setText(f"{c['score']} %")
            self.cartes["chaleur"].detail.setText(_pastille(txt, c["niveau"]) +
                                                  f"<br>{c['nb_chaudes']} sortie(s) ≥ {round(c['seuil'])} °C en 14 j")
            self.note_chaleur.setText(
                "L'acclimatation demande environ 6 sorties de plus de 30 minutes par chaleur (≥ 22 °C) sur deux "
                "semaines. Avant une course chaude, vise ce niveau. " +
                (f"{c['nb_avec_temperature']} sortie(s) sur {c['nb_sorties']} ont une température connue." if
                 c["nb_avec_temperature"] < c["nb_sorties"] else ""))


# ----------------------------------------------------------------------
# Charge & équilibre
# ----------------------------------------------------------------------

class ChargeEquilibre(_EcranAthlete):

    def __init__(self, athlete_id_initial=None):
        super().__init__(
            "⚖️  Charge, variété et équilibre",
            "Trois regards sur ta façon de charger : la variété des jours (monotonie), la montée d'une "
            "semaine à l'autre, et la part de temps passée facile ou dur.",
            athlete_id_initial,
        )
        ligne = QHBoxLayout()
        ligne.setSpacing(15)
        self.cartes = {}
        for cle, titre in (("mono", "Monotonie (dernière semaine complète)"),
                           ("hausse", "Hausse de charge"), ("facile", "Temps facile (12 sem.)")):
            self.cartes[cle] = self._carte(titre)
            ligne.addWidget(self.cartes[cle], 1)
        self.principal.addLayout(ligne)

        self.c_hausse = self._cadre_courbe("Charge par semaine", None, 240)
        self.c_hausse.courbe.hide()
        self.barres = CourbeBarres()
        self.barres.setMinimumHeight(230)
        self.c_hausse.layout().addWidget(self.barres)
        self.note_hausse = QLabel("")
        self.note_hausse.setObjectName("texteSecondaire")
        self.note_hausse.setWordWrap(True)
        self.note_hausse.setTextFormat(Qt.TextFormat.RichText)
        self.c_hausse.layout().addWidget(self.note_hausse)
        self.principal.addWidget(self.c_hausse)

        self.c_mono = self._cadre_courbe(
            "Monotonie et contrainte",
            "Monotonie = charge moyenne ÷ écart-type sur la semaine. Au-dessus de 2 : tous tes jours se "
            "ressemblent (pas assez de jours faciles) ; c'est le terrain des blessures. "
            "Contrainte = charge × monotonie.", 240)
        self.c_mono.courbe.reperes = [(1.5, "1,5", ORANGE), (2.0, "2,0 : trop uniforme", ROUGE)]
        self.principal.addWidget(self.c_mono)

        self.c_8020 = self._cadre_courbe(
            "Facile ou dur : la règle des 80/20",
            "Part du temps passée sous 80 % de ta FC max, semaine par semaine. Les coureurs qui progressent "
            "bien passent environ 80 % du temps facile.", 240)
        self.c_8020.courbe.reperes = [(80, "objectif 80 %", VERT)]
        self.note_8020 = QLabel("")
        self.note_8020.setObjectName("texteSecondaire")
        self.note_8020.setWordWrap(True)
        self.c_8020.layout().addWidget(self.note_8020)
        self.principal.addWidget(self.c_8020)
        self.principal.addStretch()
        self._finaliser()

    def actualiser(self):
        a = self.athlete_id
        for c in self.cartes.values():
            _vide(c)
        self.barres.definir_donnees([])
        self.c_mono.courbe.definir_series([])
        self.c_8020.courbe.definir_series([])
        self.note_hausse.setText("")
        self.note_8020.setText("")
        if a is None:
            return

        mc = met.monotonie_contrainte(a, 12)
        completes = [m for m in mc if m["monotonie"] is not None and not m["partielle"]]
        if completes:
            m = completes[-1]
            self.cartes["mono"].valeur.setText(virgule(m["monotonie"], 2))
            txt = {"bonne": "Bonne variété", "moyenne": "À surveiller", "elevee": "Trop uniforme"}[m["niveau"]]
            extra = " · contrainte élevée" if m["contrainte_haute"] else ""
            self.cartes["mono"].detail.setText(_pastille(txt, m["niveau"]) + f"<br>semaine du {_fmt_jour(m['lundi'])}{extra}")
        self.c_mono.courbe.definir_series([
            {"nom": "Monotonie", "couleur": ORANGE,
             "valeurs": [(_fmt_jour(m["lundi"]), m["monotonie"]) for m in mc if m["monotonie"] is not None]},
        ] if any(m["monotonie"] is not None for m in mc) else [])

        hc = met.hausse_charge_hebdo(a, 12)
        self.barres.definir_donnees([(_fmt_jour(s["lundi"]), s["charge"]) for s in hc], libelle="Charge")
        derniere_complete = next((s for s in reversed(hc) if s["variation_pct"] is not None), None)
        if derniere_complete:
            v = derniere_complete["variation_pct"]
            self.cartes["hausse"].valeur.setText(f"{'+' if v > 0 else '−' if v < 0 else ''}{abs(v)} %")
            txt = {"ok": "Progression raisonnable", "attention": "Hausse marquée", "forte": "Hausse trop rapide",
                   "baisse": "Semaine plus légère"}[
                derniere_complete["niveau"]]
            self.cartes["hausse"].detail.setText(
                _pastille(txt, derniere_complete["niveau"]) + f"<br>semaine du {_fmt_jour(derniere_complete['lundi'])} "
                "vs la précédente")
        partielle = hc[-1] if hc and hc[-1]["partielle"] else None
        if partielle:
            self.note_hausse.setText(f"Semaine en cours (pas terminée) : charge {round(partielle['charge'])} "
                                     f"pour l'instant. Repère classique : ne pas augmenter de plus de 10 % d'une "
                                     "semaine à l'autre.")
        else:
            self.note_hausse.setText("Repère classique : ne pas augmenter la charge de plus de 10 % d'une semaine à l'autre.")

        r = met.repartition_facile_dur(a, 12)
        if r["pct_facile"] is not None:
            self.cartes["facile"].valeur.setText(f"{r['pct_facile']} %")
            niveau = "ok" if r["pct_facile"] >= 75 else "attention" if r["pct_facile"] >= 65 else "forte"
            self.cartes["facile"].detail.setText(_pastille("objectif ≈ 80 %", niveau) +
                                                 f"<br>seuil facile : sous {r['seuil_bpm']} bpm")
        vals = [(_fmt_jour(s["lundi"]), s["pct_facile"]) for s in r["semaines"] if s["pct_facile"] is not None]
        self.c_8020.courbe.echelle_ajustee = False
        self.c_8020.courbe.definir_series([{"nom": "% de temps facile", "couleur": VERT, "valeurs": vals}] if vals else [])
        self.note_8020.setText(r["conseil"])


# ----------------------------------------------------------------------
# Poids lissé
# ----------------------------------------------------------------------

class PoidsLisse(_EcranAthlete):

    def __init__(self, athlete_id_initial=None):
        super().__init__(
            "⚖️  Poids lissé et objectif",
            "Le poids varie de 1 à 2 kg d'un jour à l'autre (eau, repas) : seule la courbe lissée "
            "(moyenne sur environ une semaine) montre la vraie tendance.",
            athlete_id_initial,
        )
        self.bouton_obj = QPushButton("🎯 Fixer mon objectif de poids…")
        self.bouton_obj.clicked.connect(self._fixer_objectif)
        self.barre.addWidget(self.bouton_obj)

        ligne = QHBoxLayout()
        ligne.setSpacing(15)
        self.cartes = {}
        for cle, titre in (("actuel", "Poids lissé"), ("tendance", "Tendance (4 sem.)"), ("objectif", "Objectif")):
            self.cartes[cle] = self._carte(titre)
            ligne.addWidget(self.cartes[cle], 1)
        self.principal.addLayout(ligne)
        self.cadre = self._cadre_courbe("Poids brut et poids lissé", "Les points bruts sont les pesées ; "
                                        "la ligne lissée est celle à suivre.", 320)
        self.cadre.courbe.echelle_ajustee = True
        self.principal.addWidget(self.cadre)
        self.principal.addStretch()
        self._finaliser()

    def _fixer_objectif(self):
        a = self.athlete_id
        if a is None:
            return
        actuel = met.objectif_poids(a) or 0.0
        valeur, ok = QInputDialog.getDouble(self, "Objectif de poids", "Poids visé (kg) — 0 pour effacer :",
                                            actuel, 0, 250, 1)
        if ok:
            met.definir_objectif_poids(a, valeur if valeur > 0 else None)
            notifier("Objectif enregistré")
            self.actualiser()

    def actualiser(self):
        a = self.athlete_id
        for c in self.cartes.values():
            _vide(c)
        self.cadre.courbe.definir_series([])
        self.cadre.courbe.reperes = []
        if a is None:
            return
        p = met.poids_lisse(a, 365)
        if not p["lisse"]:
            self.cartes["actuel"].detail.setText("Aucune pesée enregistrée (onglet Poids & fatigue).")
            return
        self.cartes["actuel"].valeur.setText(f"{virgule(p['actuel'], 1)} kg")
        self.cartes["actuel"].detail.setText(f"dernière pesée {virgule(p['brut'][-1][1], 1)} kg le {_fmt_jour(p['brut'][-1][0])}")
        t = p["tendance_kg_sem"]
        if t is not None:
            self.cartes["tendance"].valeur.setText(f"{'+' if t > 0 else '−' if t < 0 else ''}{virgule(abs(t), 2)} kg/sem")
            self.cartes["tendance"].detail.setText("stable" if abs(t) < 0.1 else "en hausse" if t > 0 else "en baisse")
        if p["objectif"]:
            reste = p["actuel"] - p["objectif"]
            self.cartes["objectif"].valeur.setText(f"{virgule(p['objectif'], 1)} kg")
            eta = f"<br>≈ {p['semaines_restantes']} semaine(s) à ce rythme" if p["semaines_restantes"] else ""
            self.cartes["objectif"].detail.setText(
                f"{'encore ' + virgule(abs(reste), 1) + ' kg' if abs(reste) >= 0.1 else 'atteint !'}{eta}")
            self.cadre.courbe.reperes = [(p["objectif"], f"objectif {virgule(p['objectif'], 1)} kg", VERT)]
        self.cadre.courbe.definir_series([
            {"nom": "Pesée (kg)", "couleur": "#5C6770", "valeurs": [(j.strftime("%d/%m/%y"), v) for j, v in p["brut"]]},
            {"nom": "Lissé (kg)", "couleur": BLEU, "valeurs": [(j.strftime("%d/%m/%y"), v) for j, v in p["lisse"]]},
        ])
