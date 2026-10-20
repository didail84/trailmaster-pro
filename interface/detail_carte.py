"""
Clic sur une carte du tableau de bord : ouvre une fenêtre qui explique
en mots simples ce que représente la carte, montre un graphique de son
évolution, et propose un bouton pour ouvrir la page complète
correspondante.

Tout est calculé à partir des mêmes fonctions que le tableau de bord
(interface/coach.py) : aucun nouveau calcul à maintenir, les chiffres
de la fenêtre sont donc toujours cohérents avec ceux de la carte.
"""

from datetime import date

from PySide6.QtCore import Qt, QObject, QEvent
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame,
    QComboBox, QScrollArea, QWidget,
)

from interface.courbe_multiligne import CourbeMultiLignes
from interface.courbe_widget import CourbeBarres
from interface.theme import PALETTE, POLICE_TEXTE, obtenir_couleur_accent, eclaircir
from interface.coach import (
    calculer_acwr, calculer_score_forme_jour, calculer_serie_forme,
    obtenir_charges_journalieres, obtenir_charges_periode,
    obtenir_mesure_periode, obtenir_date_premiere_activite, generer_alertes,
    obtenir_seuils_alertes, serie_rythme_vie_actif, serie_resultats_courses,
)

# Pages de destination : (libellé du bouton, nom de la méthode du
# TableauBord qui ouvre la page, index d'onglet éventuel).
PAGE_ANALYSES = ("Ouvrir « Analyses && Forme »", "ouvrir_analyses_et_forme", None)
PAGE_HISTORIQUE = ("Ouvrir l'historique des activités", "ouvrir_historique_activites", None)
PAGE_COMPTE = ("Ouvrir la fiche athlète", "ouvrir_athletes", None)

# Périodes proposées dans la fenêtre : (libellé, nombre de jours)
PERIODES_DETAIL = [
    ("30 jours", 30), ("3 mois", 90), ("6 mois", 180),
    ("1 an", 365), ("2 ans", 730), ("Tout l'historique", None),
]

NIVEAUX_ALERTE = {
    "critique": ("🛑", "#EF5350"), "attention": ("⚠️", "#F9A825"),
    "info": ("ℹ️", "#42A5F5"), "ok": ("✅", "#66BB6A"),
}

# Texte explicatif de chaque carte (mots simples, pour comprendre à
# quoi correspond le chiffre sans connaître le jargon).
EXPLICATIONS = {
    "charge_semaine": (
        "CHARGE SEMAINE",
        "La charge mesure l'effort total de tes séances : plus tu cours longtemps, "
        "vite et avec du dénivelé, plus elle monte. Le chiffre de la carte est la somme "
        "des 7 derniers jours. Le graphique montre la charge jour après jour : les "
        "grosses barres sont tes séances dures, les jours vides sont des jours de repos.",
    ),
    "entrainements_semaine": (
        "ENTRAÎNEMENTS",
        "Nombre de jours où tu as fait au moins une séance sur les 7 derniers jours. "
        "Le graphique montre ce nombre semaine par semaine pour voir si ta régularité "
        "progresse ou baisse.",
    ),
    "forme": (
        "FORME",
        "La forme compare ta condition physique construite sur le long terme (« fitness », "
        "lente à monter) à ta fatigue récente (rapide à monter et à descendre). "
        "Forme = fitness − fatigue : positive, tu es frais ; fortement négative, tu es "
        "chargé et il faut récupérer. Le graphique montre les trois courbes.",
    ),
    "acwr": (
        "ACWR",
        "Ratio entre ta charge des 7 derniers jours et ta charge moyenne des 28 derniers. "
        "Autour de 1, tu t'entraînes comme d'habitude. Quand il monte trop haut, tu "
        "augmentes brutalement la charge et le risque de blessure grimpe. Les lignes "
        "du graphique sont tes seuils d'alerte (réglables dans les réglages).",
    ),
    "indice_forme": (
        "INDICE DE FORME",
        "Score sur 100 qui combine ta charge, ton sommeil, tes blessures éventuelles et "
        "tes signaux de récupération quand ils sont disponibles. Plus il est haut, mieux "
        "tu es prêt à t'entraîner dur. Le détail de chaque ingrédient est ci-dessous ; "
        "le graphique montre la forme physique (fitness − fatigue) sur la période.",
    ),
    "distance_cumulee": (
        "DISTANCE CUMULÉE",
        "Total des kilomètres sur la période choisie sur la carte. Le graphique découpe "
        "la période en barres (jours, semaines ou mois selon la durée) pour voir où "
        "se concentrent tes kilomètres.",
    ),
    "denivele_cumule": (
        "DÉNIVELÉ D+ CUMULÉ",
        "Total de mètres de montée sur la période choisie sur la carte. Le graphique "
        "montre comment ce dénivelé se répartit dans le temps.",
    ),
    "duree_cumulee": (
        "TEMPS CUMULÉ",
        "Total d'heures d'entraînement sur la période choisie sur la carte. Le graphique "
        "montre comment ce temps se répartit dans le temps.",
    ),
    "graphique_charge": (
        "ÉVOLUTION DE LA CHARGE",
        "La charge d'entraînement dans le temps. Les barres sont agrégées automatiquement "
        "(jour, semaine, mois) pour rester lisibles. Tu peux changer la période ci-dessous.",
    ),
    "graphique_sur_mesure": (
        "GRAPHIQUE POLYVALENT",
        "Une mesure au choix (distance, dénivelé, durée, séances, charge) dans le temps. "
        "Change la mesure et la période ci-dessous.",
    ),
    "mini_forme_fatigue": (
        "FITNESS / FATIGUE / FORME",
        "Fitness (bleu) : ta condition construite sur ~6 semaines. Fatigue (rouge) : "
        "l'effort de la dernière semaine. Forme (vert) : fitness − fatigue. "
        "Quand le vert est positif, tu es frais ; très négatif, tu es chargé.",
    ),
    "tableau_croise": (
        "TABLEAU CROISÉ",
        "Ta forme (vert), tes jours de rythme de vie actif (violet) et tes jours de course "
        "(orange) superposés, pour voir comment ils se recoupent.",
    ),
}

# Mesures disponibles pour les cartes cumulées
MESURE_PAR_CARTE = {
    "distance_cumulee": "distance",
    "denivele_cumule": "denivele",
    "duree_cumulee": "duree",
}


def _nb_jours(libelle_periode, athlete_id):
    nb = dict(PERIODES_DETAIL).get(libelle_periode)
    if nb is None:
        premiere = obtenir_date_premiere_activite(athlete_id)
        nb = (date.today() - premiere).days + 1 if premiere else 90
    return max(nb, 7)


def _serie_acwr(athlete_id, nb_jours):
    """ACWR jour par jour : charge moyenne des 7 derniers jours divisée
    par celle des 28 derniers (même définition que la carte)."""
    charges = obtenir_charges_journalieres(athlete_id, nb_jours=nb_jours + 28)
    valeurs = [c for _, c in charges]
    points = []
    for i in range(28, len(charges)):
        chronique = sum(valeurs[i - 27:i + 1]) / 28
        aigue = sum(valeurs[i - 6:i + 1]) / 7
        if chronique > 0:
            points.append((charges[i][0], round(min(aigue / chronique, 3.0), 2)))
    return points


def _jours_actifs_par_semaine(athlete_id, nb_jours):
    charges = obtenir_charges_journalieres(athlete_id, nb_jours=nb_jours)
    semaines = []
    for debut in range(len(charges) - 7, -1, -7):
        bloc = charges[debut:debut + 7]
        semaines.append((bloc[0][0].strftime("%d/%m"), sum(1 for _, c in bloc if c > 0)))
    semaines.reverse()
    return semaines


class DialogueDetailCarte(QDialog):
    """Fenêtre de détail d'une carte du tableau de bord."""

    def __init__(self, cle, athlete_id, ouvrir_page=None, parent=None):
        super().__init__(parent)
        self.cle = cle
        self.athlete_id = athlete_id
        self._ouvrir_page = ouvrir_page

        titre, explication = EXPLICATIONS.get(cle, (cle, ""))
        self.setWindowTitle(f"TrailMaster Pro — {titre.title()}")
        self.resize(860, 640)
        self._appliquer_style()

        racine = QVBoxLayout(self)
        racine.setContentsMargins(20, 18, 20, 16)
        racine.setSpacing(10)

        en_tete = QHBoxLayout()
        label_titre = QLabel(titre)
        label_titre.setObjectName("titreDetail")
        en_tete.addWidget(label_titre)
        en_tete.addStretch()
        self.combo_periode = QComboBox()
        for libelle, _ in PERIODES_DETAIL:
            self.combo_periode.addItem(libelle)
        self.combo_periode.setCurrentText(self._periode_par_defaut())
        self.combo_periode.currentIndexChanged.connect(self._rafraichir)
        en_tete.addWidget(self.combo_periode)
        racine.addLayout(en_tete)

        self.label_valeur = QLabel("")
        self.label_valeur.setObjectName("valeurDetail")
        racine.addWidget(self.label_valeur)

        self.label_explication = QLabel(explication)
        self.label_explication.setObjectName("texteDetail")
        self.label_explication.setWordWrap(True)
        racine.addWidget(self.label_explication)

        self.zone_graphique = QVBoxLayout()
        racine.addLayout(self.zone_graphique, 1)

        self.label_complement = QLabel("")
        self.label_complement.setObjectName("texteDetail")
        self.label_complement.setWordWrap(True)
        racine.addWidget(self.label_complement)

        pied = QHBoxLayout()
        pied.addStretch()
        page = self._page_cible()
        if page is not None and ouvrir_page is not None:
            bouton_page = QPushButton(page[0])
            bouton_page.setObjectName("boutonPage")
            bouton_page.setCursor(Qt.CursorShape.PointingHandCursor)
            bouton_page.clicked.connect(self._cliquer_page)
            pied.addWidget(bouton_page)
        bouton_fermer = QPushButton("Fermer")
        bouton_fermer.clicked.connect(self.close)
        pied.addWidget(bouton_fermer)
        racine.addLayout(pied)

        self._rafraichir()

    # ------------------------------------------------------------
    def _periode_par_defaut(self):
        if self.cle in ("charge_semaine", "mini_forme_fatigue", "tableau_croise", "indice_forme"):
            return "3 mois"
        if self.cle == "entrainements_semaine":
            return "6 mois"
        if self.cle in MESURE_PAR_CARTE:
            return "1 an"
        return "3 mois"

    def _page_cible(self):
        if self.cle == "entrainements_semaine" or self.cle in MESURE_PAR_CARTE:
            return PAGE_HISTORIQUE
        if self.cle == "fiche_coureur":
            return PAGE_COMPTE
        return PAGE_ANALYSES

    def _cliquer_page(self):
        page = self._page_cible()
        if self._ouvrir_page is not None and page is not None:
            self._ouvrir_page(page[1], page[2])
        self.close()

    def _appliquer_style(self):
        accent = obtenir_couleur_accent()
        self.setStyleSheet(f"""
            QDialog {{ background-color: {PALETTE['fond']}; }}
            QLabel {{ color: {PALETTE['texte']}; font-family: '{POLICE_TEXTE}', sans-serif; }}
            #titreDetail {{ font-size: 18px; font-weight: 700; }}
            #valeurDetail {{ font-size: 26px; font-weight: 700; color: {accent}; }}
            #texteDetail {{ color: {PALETTE['texte_secondaire']}; font-size: 13px; }}
            QPushButton {{
                background-color: {PALETTE['carte']}; color: {PALETTE['texte']};
                border: 1px solid #2A3138; border-radius: 8px; padding: 8px 16px;
            }}
            QPushButton:hover {{ border-color: {accent}; }}
            #boutonPage {{ background-color: {accent}; color: #0B0F12; font-weight: 600; border: none; }}
            #boutonPage:hover {{ background-color: {eclaircir(accent)}; }}
            QComboBox {{
                background-color: {PALETTE['carte']}; color: {PALETTE['texte']};
                border: 1px solid #2A3138; border-radius: 6px; padding: 4px 10px;
            }}
            QScrollArea {{ border: none; background: transparent; }}
        """)

    def _vider_graphiques(self):
        while self.zone_graphique.count():
            item = self.zone_graphique.takeAt(0)
            w = item.widget()
            if w is not None:
                w.hide()
                w.setParent(None)
                w.deleteLater()

    def _ajouter_barres(self, points, seuil=None, titre=None, libelle=None):
        if titre:
            etiquette = QLabel(titre)
            etiquette.setObjectName("texteDetail")
            self.zone_graphique.addWidget(etiquette)
        courbe = CourbeBarres()
        courbe.setMinimumHeight(240)
        courbe.definir_donnees(points, seuil=seuil, libelle=libelle)
        self.zone_graphique.addWidget(courbe, 1)

    def _ajouter_lignes(self, series, titre=None, echelle_ajustee=False):
        if titre:
            etiquette = QLabel(titre)
            etiquette.setObjectName("texteDetail")
            self.zone_graphique.addWidget(etiquette)
        courbe = CourbeMultiLignes()
        courbe.setMinimumHeight(240)
        if echelle_ajustee:
            courbe.echelle_ajustee = True
        courbe.definir_series(series)
        self.zone_graphique.addWidget(courbe, 1)

    # ------------------------------------------------------------
    def _rafraichir(self):
        self._vider_graphiques()
        aid = self.athlete_id
        cle = self.cle
        nb = _nb_jours(self.combo_periode.currentText(), aid)
        valeur, complement = "", ""

        if aid is None:
            self.label_valeur.setText("--")
            self.label_complement.setText("Sélectionne un athlète pour voir le détail.")
            return

        if cle in ("charge_semaine", "graphique_charge"):
            charges = obtenir_charges_journalieres(aid, nb_jours=35)
            total = round(sum(c for _, c in charges[-7:]), 1)
            valeur = f"{total} sur 7 jours" if cle == "charge_semaine" else ""
            points, gran = obtenir_charges_periode(aid, nb)
            acwr = calculer_acwr(aid)
            seuil = acwr["charge_chronique"] * 1.5 if (acwr["charge_chronique"] and nb <= 35) else None
            self._ajouter_barres(points, seuil=seuil, libelle="Charge",
                                titre=f"Charge d'entraînement — {self.combo_periode.currentText()}")
            complement = (
                f"Charge moyenne par jour : {acwr['charge_aigue']} (7 j) · "
                f"{acwr['charge_chronique']} (28 j)."
            )

        elif cle == "entrainements_semaine":
            charges = obtenir_charges_journalieres(aid, nb_jours=7)
            actifs = sum(1 for _, c in charges if c > 0)
            valeur = f"{actifs} jour(s) actif(s) cette semaine"
            semaines = _jours_actifs_par_semaine(aid, max(nb, 28))
            self._ajouter_barres(semaines, titre="Jours actifs par semaine", libelle="Jours actifs")
            if semaines:
                moyenne = sum(v for _, v in semaines) / len(semaines)
                complement = f"Moyenne sur la période : {moyenne:.1f} jour(s) actif(s) par semaine."

        elif cle in ("forme", "mini_forme_fatigue", "indice_forme"):
            serie = calculer_serie_forme(aid, nb_jours=nb)
            if cle == "indice_forme":
                forme_jour = calculer_score_forme_jour(aid)
                valeur = f"{forme_jour['score']}/100"
                complement = forme_jour["interpretation"]
                morceaux = []
                if forme_jour.get("sommeil_moyen") is not None:
                    morceaux.append(f"sommeil moyen {forme_jour['sommeil_moyen']} h")
                morceaux.append("blessure active" if forme_jour.get("blessure_active") else "aucune blessure active")
                if forme_jour.get("recuperation_importee"):
                    morceaux.append("signaux de récupération pris en compte")
                complement += "\nIngrédients : " + " · ".join(morceaux) + "."
            elif cle == "forme":
                acwr = calculer_acwr(aid)
                valeur = acwr["interpretation"]
                if serie:
                    dernier = serie[-1]
                    complement = (
                        f"Aujourd'hui : fitness {dernier['fitness']} · "
                        f"fatigue {dernier['fatigue']} · forme {dernier['forme']}."
                    )
            else:
                if serie:
                    valeur = f"Forme actuelle : {serie[-1]['forme']}"
            self._ajouter_lignes([
                {"nom": "Fitness", "couleur": "#42A5F5",
                 "valeurs": [(j["date"].strftime("%d/%m"), j["fitness"]) for j in serie]},
                {"nom": "Fatigue", "couleur": "#EF5350",
                 "valeurs": [(j["date"].strftime("%d/%m"), j["fatigue"]) for j in serie]},
                {"nom": "Forme", "couleur": "#66BB6A",
                 "valeurs": [(j["date"].strftime("%d/%m"), j["forme"]) for j in serie]},
            ], titre=f"Fitness / Fatigue / Forme — {self.combo_periode.currentText()}")

        elif cle == "acwr":
            info = calculer_acwr(aid)
            valeur = f"{info['acwr']}" if info["acwr"] is not None else "--"
            complement = info["interpretation"]
            points = _serie_acwr(aid, nb)
            seuils = obtenir_seuils_alertes()
            etiquettes = [d.strftime("%d/%m") for d, _ in points]
            series = [{"nom": "ACWR", "couleur": "#42A5F5",
                       "valeurs": [(e, v) for e, (_, v) in zip(etiquettes, points)]}]
            for nom, cle_seuil, couleur in (
                ("Seuil bas", "acwr_bas", "#66BB6A"),
                ("Seuil d'attention", "acwr_attention", "#F9A825"),
                ("Seuil de risque", "acwr_risque", "#EF5350"),
            ):
                if cle_seuil in seuils:
                    series.append({"nom": f"{nom} ({seuils[cle_seuil]})", "couleur": couleur,
                                   "valeurs": [(e, seuils[cle_seuil]) for e in etiquettes]})
            self._ajouter_lignes(series, titre=f"ACWR — {self.combo_periode.currentText()}", echelle_ajustee=True)

        elif cle in MESURE_PAR_CARTE or cle == "graphique_sur_mesure":
            mesures = [MESURE_PAR_CARTE[cle]] if cle in MESURE_PAR_CARTE else [
                "distance", "denivele", "duree", "nb_seances", "charge"]
            from interface.coach import MESURES_CUMULABLES
            for m in mesures:
                points, gran, total = obtenir_mesure_periode(aid, m, nb)
                libelle = MESURES_CUMULABLES[m]["libelle"]
                if cle in MESURE_PAR_CARTE:
                    valeur = f"{total} — {libelle}"
                    complement = f"Total sur : {self.combo_periode.currentText().lower()}."
                self._ajouter_barres(points, titre=f"{libelle} — total {total}")
                if cle == "graphique_sur_mesure":
                    break  # une seule mesure à la fois pour rester lisible
            if cle == "graphique_sur_mesure":
                self._ajouter_selecteur_mesure()

        elif cle == "tableau_croise":
            serie = calculer_serie_forme(aid, nb_jours=nb)
            rythme = serie_rythme_vie_actif(nb_jours=nb)
            courses = serie_resultats_courses(aid, nb_jours=nb)
            vmax = max((j["forme"] for j in serie), default=5) or 5
            echelle = max(abs(vmax), 5)
            self._ajouter_lignes([
                {"nom": "Forme", "couleur": "#66BB6A",
                 "valeurs": [(j["date"].strftime("%d/%m"), j["forme"]) for j in serie]},
                {"nom": "Rythme de vie actif", "couleur": "#AB47BC",
                 "valeurs": [(j.strftime("%d/%m"), echelle if a else 0) for j, a in rythme]},
                {"nom": "Jour de course", "couleur": "#FFA726",
                 "valeurs": [(j.strftime("%d/%m"), echelle if a else 0) for j, a in courses]},
            ], titre=f"Forme, rythme de vie et courses — {self.combo_periode.currentText()}")
            nb_courses = sum(1 for _, a in courses if a)
            complement = f"{nb_courses} jour(s) de course sur la période."

        self.label_valeur.setText(valeur)
        self.label_complement.setText(complement)

    def _ajouter_selecteur_mesure(self):
        """Graphique polyvalent : petit sélecteur de mesure sous le graphique."""
        from interface.coach import MESURES_CUMULABLES
        ligne = QHBoxLayout()
        ligne.addWidget(QLabel("Mesure :"))
        combo = QComboBox()
        for k, info in MESURES_CUMULABLES.items():
            combo.addItem(info["libelle"], k)
        combo.setCurrentIndex(getattr(self, "_mesure_idx", 0))
        combo.currentIndexChanged.connect(self._changer_mesure)
        ligne.addWidget(combo)
        ligne.addStretch()
        conteneur = QWidget()
        conteneur.setLayout(ligne)
        self.zone_graphique.insertWidget(0, conteneur)
        self._combo_mesure = combo

    def _changer_mesure(self, idx):
        self._mesure_idx = idx
        # Recalcule le graphique avec la mesure choisie.
        from interface.coach import MESURES_CUMULABLES
        mesure = self._combo_mesure.currentData()
        nb = _nb_jours(self.combo_periode.currentText(), self.athlete_id)
        points, _, total = obtenir_mesure_periode(self.athlete_id, mesure, nb)
        # Garde le sélecteur (item 0), remplace le reste.
        while self.zone_graphique.count() > 1:
            item = self.zone_graphique.takeAt(1)
            w = item.widget()
            if w is not None:
                w.hide()
                w.setParent(None)
                w.deleteLater()
        self._ajouter_barres(points, titre=f"{MESURES_CUMULABLES[mesure]['libelle']} — total {total}",
                             libelle=MESURES_CUMULABLES[mesure]['libelle'])


class DialogueAlertes(QDialog):
    """Détail des alertes proactives : toutes les alertes avec leur
    niveau, et un bouton vers la page d'analyses."""

    def __init__(self, athlete_id, ouvrir_page=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("TrailMaster Pro — Alertes proactives")
        self.resize(720, 520)
        self._ouvrir_page = ouvrir_page
        self.setStyleSheet(f"""
            QDialog {{ background-color: {PALETTE['fond']}; }}
            QLabel {{ color: {PALETTE['texte']}; font-family: '{POLICE_TEXTE}', sans-serif; }}
            QPushButton {{ background-color: {PALETTE['carte']}; color: {PALETTE['texte']};
                border: 1px solid #2A3138; border-radius: 8px; padding: 8px 16px; }}
            QScrollArea {{ border: none; background: transparent; }}
            #contenuAlertes {{ background-color: {PALETTE['fond']}; }}
        """)
        racine = QVBoxLayout(self)
        titre = QLabel("⚡ Alertes proactives")
        titre.setStyleSheet("font-size: 18px; font-weight: 700;")
        racine.addWidget(titre)
        intro = QLabel(
            "Ces alertes sont calculées à partir de ta charge, de ta forme et de ton "
            "sommeil. Les plus urgentes sont affichées sur le tableau de bord ; "
            "voici la liste complète."
        )
        intro.setWordWrap(True)
        intro.setStyleSheet(f"color: {PALETTE['texte_secondaire']};")
        racine.addWidget(intro)

        defilement = QScrollArea()
        defilement.setWidgetResizable(True)
        contenu = QWidget()
        contenu.setObjectName("contenuAlertes")
        liste = QVBoxLayout(contenu)
        alertes = generer_alertes(athlete_id) if athlete_id is not None else []
        if not alertes:
            alertes = [{"niveau": "ok", "message": "Rien à signaler."}]
        for a in alertes:
            icone, couleur = NIVEAUX_ALERTE.get(a["niveau"], ("•", PALETTE["texte"]))
            ligne = QLabel(f"{icone}  {a['message']}")
            ligne.setWordWrap(True)
            ligne.setStyleSheet(f"color: {couleur}; padding: 6px 0;")
            liste.addWidget(ligne)
        liste.addStretch()
        defilement.setWidget(contenu)
        racine.addWidget(defilement, 1)

        pied = QHBoxLayout()
        pied.addStretch()
        if ouvrir_page is not None:
            bouton = QPushButton(PAGE_ANALYSES[0])
            bouton.clicked.connect(lambda: (ouvrir_page(PAGE_ANALYSES[1], None), self.close()))
            pied.addWidget(bouton)
        fermer = QPushButton("Fermer")
        fermer.clicked.connect(self.close)
        pied.addWidget(fermer)
        racine.addLayout(pied)


class FiltreClicCarte(QObject):
    """Filtre d'événements : un clic gauche sur la carte (hors listes
    déroulantes, qui gardent leur comportement) appelle `rappel`."""

    def __init__(self, carte, rappel):
        super().__init__(carte)
        self._rappel = rappel
        self._appui = False
        carte.installEventFilter(self)
        carte.setCursor(Qt.CursorShape.PointingHandCursor)
        carte.setToolTip("Cliquer pour voir le détail")
        for combo in carte.findChildren(QComboBox):
            combo.setCursor(Qt.CursorShape.ArrowCursor)

    def eventFilter(self, objet, evenement):
        t = evenement.type()
        if t == QEvent.Type.MouseButtonPress and evenement.button() == Qt.MouseButton.LeftButton:
            self._appui = True
        elif t == QEvent.Type.MouseButtonRelease and evenement.button() == Qt.MouseButton.LeftButton:
            if self._appui:
                self._appui = False
                self._rappel()
        return False
