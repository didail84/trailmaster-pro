"""
Récupération & tendances — écran d'analyse de la fatigue et de la forme
à partir des données de la montre (FC de repos, HRV de nuit, sommeil,
Body Battery, stress) et de calculs sur les sorties (efficience, dérive
cardiaque, répartition de l'intensité, effet d'entraînement).

La montre n'étant pas portée tous les jours, les mesures quotidiennes ont
des trous : aucune valeur n'est inventée ; les courbes relient seulement
les jours mesurés et l'écran indique toujours combien de jours ont des
données.
"""

import json
from datetime import date, datetime, timedelta
from statistics import mean, median

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QComboBox, QScrollArea, QTableWidget, QTableWidgetItem,
)

from data.database import connexion, obtenir_athletes
from interface.courbe_multiligne import CourbeMultiLignes
from interface.ecran_liste import obtenir_style_ecran, configurer_table_redimensionnable
from interface.vma import _carte_kpi, _table, _remplir, duree_texte

PERIODES = [("30 jours", 30), ("3 mois", 90), ("6 mois", 180), ("1 an", 365)]
TYPES_COURSE = ("Trail", "Course")

# Seuils de lecture (volontairement prudents : ce sont des repères
# généralement admis en sport, pas un diagnostic médical).
ECART_FC_REPOS_ATTENTION = 3    # bpm au-dessus de ta base habituelle
ECART_FC_REPOS_ALERTE = 5
RATIO_HRV_BAS = 0.85            # HRV < 85 % de ta base habituelle
RATIO_HRV_TRES_BAS = 0.75
MIN_JOURS_BASE = 5              # jours de mesure minimum pour avoir une « base »


# ==================================================================
# DONNÉES QUOTIDIENNES
# ==================================================================

COLONNES_JOUR = (
    "date", "fc_repos", "fc_min", "hrv_nuit_ms", "hrv_statut", "sommeil_score",
    "sommeil_duree_h", "sommeil_profond_min", "sommeil_leger_min",
    "sommeil_paradoxal_min", "sommeil_eveil_min", "body_battery_max",
    "body_battery_min", "stress_moyen", "spo2_moyenne",
)


def charger_recuperation(athlete_id, nb_jours=90, fin=None):
    """Lignes de recuperation_quotidienne (dicts) du plus ancien au plus récent."""
    fin = fin or date.today()
    debut = fin - timedelta(days=nb_jours)
    conn = connexion()
    cur = conn.cursor()
    try:
        cur.execute(
            f"SELECT {', '.join(COLONNES_JOUR)} FROM recuperation_quotidienne "
            "WHERE athlete_id=? AND date>=? AND date<=? ORDER BY date",
            (athlete_id, debut.isoformat(), fin.isoformat()),
        )
        lignes = [dict(zip(COLONNES_JOUR, l)) for l in cur.fetchall()]
    except Exception:
        lignes = []  # table absente (très vieille base) : pas de donnée
    conn.close()
    return lignes


def base_habituelle(lignes, cle, jours=30, avant=None):
    """Médiane de `cle` sur les `jours` jours précédant `avant` (date ISO,
    exclue) ; None s'il y a moins de MIN_JOURS_BASE mesures."""
    if avant is None:
        avant = date.today().isoformat()
    debut = (date.fromisoformat(avant) - timedelta(days=jours)).isoformat()
    valeurs = [l[cle] for l in lignes if l.get(cle) is not None and debut <= l["date"] < avant]
    return median(valeurs) if len(valeurs) >= MIN_JOURS_BASE else None


def derniere_mesure(lignes, cle):
    for l in reversed(lignes):
        if l.get(cle) is not None:
            return l["date"], l[cle]
    return None, None


def lecture_du_jour(athlete_id):
    """Phrases d'interprétation [(niveau, texte)] et couverture.
    niveau : 'ok' | 'info' | 'attention' | 'alerte'."""
    lignes = charger_recuperation(athlete_id, nb_jours=120)
    messages = []
    if not lignes:
        return [("info", "Aucune donnée de santé importée pour l'instant. Utilise « 🩺 Importer la "
                         "santé Garmin » (Import & synchro) avec ton export Garmin Connect.")], 0

    aujourdhui = date.today()
    d_max = max(l["date"] for l in lignes)
    retard = (aujourdhui - date.fromisoformat(d_max)).days
    if retard > 3:
        messages.append(("info", f"Dernière mesure de la montre : {d_max} (il y a {retard} jours) — "
                                 "les lectures ci-dessous datent de cette période."))

    # FC de repos
    d, fc = derniere_mesure(lignes, "fc_repos")
    if fc is not None:
        base = base_habituelle(lignes, "fc_repos", avant=d)
        if base is None:
            messages.append(("info", f"FC de repos : {fc} bpm ({d}). Pas encore assez de mesures "
                                     "pour connaître ta valeur habituelle."))
        else:
            ecart = fc - base
            if ecart >= ECART_FC_REPOS_ALERTE:
                messages.append(("alerte", f"FC de repos élevée : {fc} bpm, soit +{ecart:.0f} par rapport à ta "
                                           f"valeur habituelle ({base:.0f}). Fatigue accumulée, manque de "
                                           "sommeil, chaleur ou début de maladie possibles : séance légère ou repos."))
            elif ecart >= ECART_FC_REPOS_ATTENTION:
                messages.append(("attention", f"FC de repos un peu haute : {fc} bpm (+{ecart:.0f} vs {base:.0f} "
                                              "d'habitude). À surveiller."))
            else:
                messages.append(("ok", f"FC de repos normale : {fc} bpm (habituel {base:.0f})."))

    # HRV
    d, hrv = derniere_mesure(lignes, "hrv_nuit_ms")
    if hrv is not None:
        base = base_habituelle(lignes, "hrv_nuit_ms", avant=d)
        if base:
            ratio = hrv / base
            if ratio < RATIO_HRV_TRES_BAS:
                messages.append(("alerte", f"HRV de nuit très basse : {hrv:.0f} ms ({ratio*100:.0f} % de ta base "
                                           f"{base:.0f}). Récupération insuffisante."))
            elif ratio < RATIO_HRV_BAS:
                messages.append(("attention", f"HRV de nuit en baisse : {hrv:.0f} ms ({ratio*100:.0f} % de ta base "
                                              f"{base:.0f})."))
            else:
                messages.append(("ok", f"HRV de nuit correcte : {hrv:.0f} ms (base {base:.0f})."))
        else:
            messages.append(("info", f"HRV de nuit : {hrv:.0f} ms ({d}). Pas encore de base de comparaison."))

    # Sommeil : moyenne des 3 dernières nuits mesurées
    nuits = [l["sommeil_duree_h"] for l in lignes if l.get("sommeil_duree_h")][-3:]
    if nuits:
        try:
            from interface.coach import obtenir_objectif_sommeil_heures
            objectif = obtenir_objectif_sommeil_heures()
        except Exception:
            objectif = 7.5
        moy = mean(nuits)
        if moy < objectif - 1:
            messages.append(("attention", f"Sommeil court : {moy:.1f} h en moyenne sur les {len(nuits)} dernières "
                                          f"nuits mesurées (objectif {objectif:g} h)."))
        else:
            messages.append(("ok", f"Sommeil suffisant : {moy:.1f} h en moyenne sur les {len(nuits)} dernières nuits mesurées."))

    # Body Battery
    d, bb = derniere_mesure(lignes, "body_battery_max")
    if bb is not None:
        if bb < 50:
            messages.append(("attention", f"Body Battery maximal faible ({bb}/100 le {d}) : tu t'es mal rechargé."))
        else:
            messages.append(("ok", f"Body Battery maximal : {bb}/100 ({d})."))

    couverture = sum(1 for l in lignes if l["date"] >= (aujourdhui - timedelta(days=90)).isoformat())
    return messages, couverture


# ==================================================================
# CALCULS SUR LES SORTIES
# ==================================================================

def _lundi(iso_jour):
    d = date.fromisoformat(iso_jour[:10])
    return d - timedelta(days=d.weekday())


def _sorties(athlete_id, nb_jours):
    debut = (date.today() - timedelta(days=nb_jours)).isoformat()
    conn = connexion()
    cur = conn.cursor()
    cur.execute(
        "SELECT id, date, nom, type, distance, denivele, duree, frequence_cardiaque_moyenne, "
        "te_aerobie, te_anaerobie, charge_garmin, "
        "temps_zone_1, temps_zone_2, temps_zone_3, temps_zone_4, temps_zone_5 "
        "FROM activites WHERE athlete_id=? AND date>=? ORDER BY date",
        (athlete_id, debut),
    )
    cles = ("id", "date", "nom", "type", "distance", "denivele", "duree", "fc_moy",
            "te_aerobie", "te_anaerobie", "charge_garmin",
            "z1", "z2", "z3", "z4", "z5")
    res = [dict(zip(cles, l)) for l in cur.fetchall()]
    conn.close()
    return res


def efficience(sortie):
    """Mètres parcourus (à plat équivalent) par minute et par battement :
    plus c'est haut, plus tu vas vite pour le même effort cardiaque.
    None si la sortie n'a pas de FC, trop courte ou allure aberrante."""
    km, duree, fc = sortie.get("distance"), sortie.get("duree"), sortie.get("fc_moy")
    if not km or km < 3 or not duree or not fc or fc < 90:
        return None
    denivele = min(sortie.get("denivele") or 0, 60 * km)
    km_eq = km + denivele / 125
    allure = duree / 60 / km_eq
    if not 3.5 <= allure <= 10:
        return None
    return round(km_eq * 1000 / (duree / 60) / fc, 3)


def serie_efficience(athlete_id, nb_jours=180):
    """[(lundi_iso, efficience_moyenne_semaine, nb_sorties)] — courses/trails avec FC."""
    par_semaine = {}
    for s in _sorties(athlete_id, nb_jours):
        if s["type"] not in TYPES_COURSE:
            continue
        e = efficience(s)
        if e is not None:
            par_semaine.setdefault(_lundi(s["date"]), []).append(e)
    return [(l.isoformat(), round(mean(v), 3), len(v)) for l, v in sorted(par_semaine.items())]


def evolution_efficience(serie):
    """% de variation entre les 4 dernières semaines mesurées et les 4 précédentes."""
    if len(serie) < 4:
        return None
    vals = [v for _, v, _ in serie]
    recent = mean(vals[-4:])
    avant = mean(vals[-8:-4]) if len(vals) >= 8 else mean(vals[:-4])
    if not avant:
        return None
    return round((recent - avant) / avant * 100, 1)


def _repartition_sortie(s, fc_max):
    """(facile, moyen, dur) en secondes. Zones Garmin si présentes, sinon
    estimation d'après la FC moyenne rapportée à la FC max du profil."""
    z = [s.get(f"z{i}") for i in range(1, 6)]
    if sum(v or 0 for v in z) > 0:
        return (z[0] or 0) + (z[1] or 0), z[2] or 0, (z[3] or 0) + (z[4] or 0)
    if s.get("fc_moy") and fc_max and s.get("duree"):
        pct = s["fc_moy"] / fc_max
        d = s["duree"]
        if pct < 0.75:
            return d, 0, 0
        if pct < 0.85:
            return 0, d, 0
        return 0, 0, d
    return None


def repartition_intensite(athlete_id, nb_semaines=12):
    """[(lundi_iso, % facile, % moyen, % dur)] par semaine, tous types confondus
    (sorties avec FC ou zones). Retourne aussi la part de sorties estimées."""
    fc_max = None
    conn = connexion()
    cur = conn.cursor()
    cur.execute("SELECT fc_max FROM athletes WHERE id=?", (athlete_id,))
    r = cur.fetchone()
    conn.close()
    if r and r[0]:
        fc_max = r[0]

    semaines, nb_garmin, nb_estime = {}, 0, 0
    for s in _sorties(athlete_id, nb_semaines * 7):
        rep = _repartition_sortie(s, fc_max)
        if rep is None:
            continue
        if sum(s.get(f"z{i}") or 0 for i in range(1, 6)) > 0:
            nb_garmin += 1
        else:
            nb_estime += 1
        cumul = semaines.setdefault(_lundi(s["date"]), [0, 0, 0])
        for i in range(3):
            cumul[i] += rep[i]
    sortie = []
    for lundi, (f, m, d) in sorted(semaines.items()):
        total = f + m + d
        if total > 0:
            sortie.append((lundi.isoformat(), round(f / total * 100), round(m / total * 100), round(d / total * 100)))
    return sortie, nb_garmin, nb_estime


def derives_cardiaques(athlete_id, nb_jours=365, limite=40):
    """Dérive cardiaque (découplage) des sorties dont la trace contient la FC.
    [(date, nom, km, decouplage_pct, interpretation)] du plus récent au plus ancien."""
    from interface.dynamique_course import calculer_decouplage_cardiaque
    debut = (date.today() - timedelta(days=nb_jours)).isoformat()
    conn = connexion()
    cur = conn.cursor()
    cur.execute(
        "SELECT a.date, a.nom, a.distance, p.trace_json FROM activites a "
        "JOIN parcours_gpx p ON p.activite_id = a.id "
        "WHERE a.athlete_id=? AND a.date>=? AND p.trace_json IS NOT NULL "
        "ORDER BY a.date DESC LIMIT ?",
        (athlete_id, debut, limite),
    )
    lignes = cur.fetchall()
    conn.close()
    sortie = []
    for d, nom, km, trace in lignes:
        try:
            points = json.loads(trace)
        except (ValueError, TypeError):
            continue
        r = calculer_decouplage_cardiaque(points)
        if r:
            sortie.append((d[:10], nom, km, r["decouplage_pct"], r["interpretation"]))
    return sortie


def sorties_avec_effet(athlete_id, nb_jours=90, limite=25):
    """Sorties ayant au moins un indicateur Garmin (effet d'entraînement / charge)."""
    return [s for s in reversed(_sorties(athlete_id, nb_jours))
            if s["te_aerobie"] is not None or s["te_anaerobie"] is not None
            or s["charge_garmin"] is not None][:limite]


# ==================================================================
# ÉCRAN
# ==================================================================

COULEURS = {"ok": "#66BB6A", "info": "#42A5F5", "attention": "#F9A825", "alerte": "#EF5350"}
ICONES = {"ok": "✅", "info": "ℹ️", "attention": "⚠️", "alerte": "🛑"}


def _serie(nom, couleur, lignes, cle):
    return {
        "nom": nom, "couleur": couleur,
        "valeurs": [(l["date"][8:10] + "/" + l["date"][5:7], l[cle]) for l in lignes if l.get(cle) is not None],
    }


class RecuperationTendances(QMainWindow):

    def __init__(self, athlete_id_initial=None):
        super().__init__()
        self.setWindowTitle("TrailMaster Pro – Récupération & tendances")
        self.resize(1300, 900)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.setCentralWidget(scroll)
        central = QWidget()
        scroll.setWidget(central)
        self.principal = QVBoxLayout(central)
        self.principal.setContentsMargins(25, 20, 25, 20)
        self.principal.setSpacing(15)

        titre = QLabel("🩺  Récupération & tendances")
        titre.setObjectName("titrePage")
        sous = QLabel(
            "Fatigue et forme d'après ta montre (FC de repos, HRV, sommeil, Body Battery) et tes sorties "
            "(efficience, dérive cardiaque, intensité). Les jours où la montre n'est pas portée n'ont pas "
            "de mesure : les courbes ne relient que les jours mesurés."
        )
        sous.setObjectName("sousTitrePage")
        sous.setWordWrap(True)
        self.principal.addWidget(titre)
        self.principal.addWidget(sous)

        barre = QHBoxLayout()
        lab = QLabel("Athlète :")
        lab.setObjectName("labelChamp")
        self.combo_athlete = QComboBox()
        self.combo_athlete.addItem("Sélectionner...", None)
        for a in obtenir_athletes():
            self.combo_athlete.addItem(f"{a[2]} {a[1]}", a[0])
        lab2 = QLabel("Période :")
        lab2.setObjectName("labelChamp")
        self.combo_periode = QComboBox()
        for libelle, _ in PERIODES:
            self.combo_periode.addItem(libelle)
        self.combo_periode.setCurrentText("3 mois")
        barre.addWidget(lab)
        barre.addWidget(self.combo_athlete)
        barre.addSpacing(20)
        barre.addWidget(lab2)
        barre.addWidget(self.combo_periode)
        barre.addStretch()
        self.principal.addLayout(barre)

        # Lecture du jour
        self.cadre_lecture = QFrame()
        self.cadre_lecture.setObjectName("carteForm")
        self.lay_lecture = QVBoxLayout(self.cadre_lecture)
        t = QLabel("🧭 Lecture du jour")
        t.setObjectName("titreCarte")
        self.lay_lecture.addWidget(t)
        self.zone_lecture = QVBoxLayout()
        self.lay_lecture.addLayout(self.zone_lecture)
        self.principal.addWidget(self.cadre_lecture)

        self.zone_kpi = QHBoxLayout()
        self.zone_kpi.setSpacing(15)
        self.principal.addLayout(self.zone_kpi)

        # Courbes de récupération (A)
        grille = QHBoxLayout()
        grille.setSpacing(15)
        self.courbes = {}
        colonne_g, colonne_d = QVBoxLayout(), QVBoxLayout()
        for col, (cle, titre_c) in (
            (colonne_g, ("fc", "❤️ FC de repos (bpm)")),
            (colonne_d, ("hrv", "💓 HRV de nuit (ms)")),
            (colonne_g, ("sommeil", "😴 Sommeil (heures)")),
            (colonne_d, ("bb", "🔋 Body Battery")),
        ):
            cadre = QFrame()
            cadre.setObjectName("carteForm")
            lay = QVBoxLayout(cadre)
            tt = QLabel(titre_c)
            tt.setObjectName("titreCarte")
            courbe = CourbeMultiLignes()
            courbe.setMinimumHeight(190)
            courbe.echelle_ajustee = True
            lay.addWidget(tt)
            lay.addWidget(courbe)
            col.addWidget(cadre)
            self.courbes[cle] = courbe
        grille.addLayout(colonne_g, 1)
        grille.addLayout(colonne_d, 1)
        self.principal.addLayout(grille)

        # Efficience + intensité (C)
        zone2 = QHBoxLayout()
        zone2.setSpacing(15)
        c_eff = QFrame()
        c_eff.setObjectName("carteForm")
        l_eff = QVBoxLayout(c_eff)
        t_eff = QLabel("⚡ Efficience (vitesse à plat ÷ FC)")
        t_eff.setObjectName("titreCarte")
        self.note_eff = QLabel("")
        self.note_eff.setObjectName("texteSecondaire")
        self.note_eff.setWordWrap(True)
        self.courbe_eff = CourbeMultiLignes()
        self.courbe_eff.setMinimumHeight(200)
        self.courbe_eff.echelle_ajustee = True
        l_eff.addWidget(t_eff)
        l_eff.addWidget(self.note_eff)
        l_eff.addWidget(self.courbe_eff)
        c_int = QFrame()
        c_int.setObjectName("carteForm")
        l_int = QVBoxLayout(c_int)
        t_int = QLabel("🎚️ Répartition de l'intensité (par semaine)")
        t_int.setObjectName("titreCarte")
        self.note_int = QLabel("")
        self.note_int.setObjectName("texteSecondaire")
        self.note_int.setWordWrap(True)
        self.courbe_int = CourbeMultiLignes()
        self.courbe_int.setMinimumHeight(200)
        l_int.addWidget(t_int)
        l_int.addWidget(self.note_int)
        l_int.addWidget(self.courbe_int)
        zone2.addWidget(c_eff, 1)
        zone2.addWidget(c_int, 1)
        self.principal.addLayout(zone2)

        # Dérive cardiaque
        c_der = QFrame()
        c_der.setObjectName("carteForm")
        l_der = QVBoxLayout(c_der)
        t_der = QLabel("📉 Dérive cardiaque des sorties (FC qui monte à allure constante)")
        t_der.setObjectName("titreCarte")
        n_der = QLabel(
            "Compare la 2ᵉ moitié de la sortie à la 1ʳᵉ. Sous 5 % : endurance solide. Au-delà de 10 % : "
            "fatigue, chaleur ou base aérobie à renforcer. Disponible seulement pour les sorties dont la "
            "trace contient la FC (synchro Strava, import montre)."
        )
        n_der.setObjectName("texteSecondaire")
        n_der.setWordWrap(True)
        self.table_derive = _table(["Date", "Sortie", "km", "Dérive", "Lecture"], 180)
        self._largeurs(self.table_derive, [100, 280, 70, 90])
        l_der.addWidget(t_der)
        l_der.addWidget(n_der)
        l_der.addWidget(self.table_derive)
        self.principal.addWidget(c_der)

        # Effet d'entraînement (B)
        c_te = QFrame()
        c_te.setObjectName("carteForm")
        l_te = QVBoxLayout(c_te)
        t_te = QLabel("🏋️ Effet d'entraînement et charge Garmin (90 derniers jours)")
        t_te.setObjectName("titreCarte")
        n_te = QLabel(
            "Effet aérobie / anaérobie : 0 à 5 (3 = amélioration, 4 = forte, 5 = surcharge). La charge Garmin "
            "mesure l'effort de la séance pour la montre ; elle sert de repère à comparer à la charge "
            "calculée par TrailMaster."
        )
        n_te.setObjectName("texteSecondaire")
        n_te.setWordWrap(True)
        self.table_te = _table(["Date", "Sortie", "Effet aérobie", "Effet anaérobie", "Charge Garmin",
                                "Zones 1-2", "Zone 3", "Zones 4-5"], 180)
        self._largeurs(self.table_te, [100, 280, 110, 120, 120, 100, 100])
        l_te.addWidget(t_te)
        l_te.addWidget(n_te)
        l_te.addWidget(self.table_te)
        self.principal.addWidget(c_te)

        self.setStyleSheet(obtenir_style_ecran())

        if athlete_id_initial is not None:
            for i in range(self.combo_athlete.count()):
                if self.combo_athlete.itemData(i) == athlete_id_initial:
                    self.combo_athlete.setCurrentIndex(i)
                    break
        self.combo_athlete.currentIndexChanged.connect(self.actualiser)
        self.combo_periode.currentIndexChanged.connect(self.actualiser)
        self.actualiser()

    # ------------------------------------------------------------
    @staticmethod
    def _largeurs(table, largeurs):
        """Largeurs de départ lisibles ; la dernière colonne prend le reste."""
        for i, w in enumerate(largeurs):
            table.setColumnWidth(i, w)
        table.horizontalHeader().setStretchLastSection(True)

    @staticmethod
    def _vider(layout):
        while layout.count():
            w = layout.takeAt(0).widget()
            if w:
                w.hide()
                w.setParent(None)
                w.deleteLater()

    def actualiser(self):
        self._vider(self.zone_lecture)
        self._vider(self.zone_kpi)
        athlete_id = self.combo_athlete.currentData()
        nb_jours = dict(PERIODES)[self.combo_periode.currentText()]

        if athlete_id is None:
            self.zone_lecture.addWidget(QLabel("Sélectionne un athlète."))
            for c in list(self.courbes.values()) + [self.courbe_eff, self.courbe_int]:
                c.definir_series([])
            for t in (self.table_derive, self.table_te):
                t.setRowCount(0)
            return

        # --- Lecture du jour
        messages, couverture = lecture_du_jour(athlete_id)
        for niveau, texte in messages:
            l = QLabel(f"{ICONES[niveau]}  {texte}")
            l.setWordWrap(True)
            l.setStyleSheet(f"color: {COULEURS[niveau]}; padding: 2px 0;")
            self.zone_lecture.addWidget(l)

        # --- Courbes quotidiennes
        lignes = charger_recuperation(athlete_id, nb_jours)
        jours_mesures = len(lignes)

        def moy(cle, n=7):
            v = [l[cle] for l in lignes if l.get(cle) is not None][-n:]
            return mean(v) if v else None

        d, fc = derniere_mesure(lignes, "fc_repos")
        base_fc = base_habituelle(lignes, "fc_repos", avant=d) if d else None
        d2, hrv = derniere_mesure(lignes, "hrv_nuit_ms")
        sommeil = moy("sommeil_duree_h", 7)
        score = moy("sommeil_score", 7)
        d3, bb = derniere_mesure(lignes, "body_battery_max")

        self.zone_kpi.addWidget(_carte_kpi(
            "FC de repos", f"{fc} bpm" if fc is not None else "—",
            (f"Habituel {base_fc:.0f} bpm ({fc - base_fc:+.0f})" if base_fc is not None and fc is not None
             else "Pas encore de base")))
        statut = next((l["hrv_statut"] for l in reversed(lignes) if l.get("hrv_statut")), "")
        self.zone_kpi.addWidget(_carte_kpi(
            "HRV de nuit", f"{hrv:.0f} ms" if hrv is not None else "—", statut.capitalize() if statut else ""))
        self.zone_kpi.addWidget(_carte_kpi(
            "Sommeil (moy. 7 nuits mesurées)", f"{sommeil:.1f} h" if sommeil else "—",
            f"Score moyen {score:.0f}/100" if score else ""))
        self.zone_kpi.addWidget(_carte_kpi(
            "Body Battery max", f"{bb}/100" if bb is not None else "—", d3 or ""))
        self.zone_kpi.addWidget(_carte_kpi(
            "Jours avec mesures", f"{jours_mesures} / {nb_jours}",
            "La montre n'est pas portée tous les jours : c'est normal."))

        ref_fc = []
        if base_fc is not None and lignes:
            ref_fc = [{"nom": f"Habituel ({base_fc:.0f})", "couleur": "#7F878D",
                       "valeurs": [(l["date"][8:10] + "/" + l["date"][5:7], round(base_fc)) for l in lignes
                                   if l.get("fc_repos") is not None]}]
        self.courbes["fc"].definir_series(
            ([_serie("FC de repos (bpm)", "#EF5350", lignes, "fc_repos")] if any(l.get("fc_repos") for l in lignes) else []) + ref_fc)
        base_hrv = base_habituelle(lignes, "hrv_nuit_ms", avant=d2) if d2 else None
        ref_hrv = []
        if base_hrv is not None:
            ref_hrv = [{"nom": f"Habituel ({base_hrv:.0f})", "couleur": "#7F878D",
                        "valeurs": [(l["date"][8:10] + "/" + l["date"][5:7], round(base_hrv)) for l in lignes
                                    if l.get("hrv_nuit_ms") is not None]}]
        self.courbes["hrv"].definir_series(
            ([_serie("HRV de nuit (ms)", "#AB47BC", lignes, "hrv_nuit_ms")] if any(l.get("hrv_nuit_ms") for l in lignes) else []) + ref_hrv)
        self.courbes["sommeil"].definir_series(
            [_serie("Durée de sommeil (h)", "#42A5F5", lignes, "sommeil_duree_h")]
            if any(l.get("sommeil_duree_h") for l in lignes) else [])
        self.courbes["bb"].definir_series(
            [s for s in (_serie("Maximum", "#66BB6A", lignes, "body_battery_max"),
                         _serie("Minimum", "#FFA726", lignes, "body_battery_min")) if s["valeurs"]])

        # --- Efficience
        serie_e = serie_efficience(athlete_id, max(nb_jours, 180))
        self.courbe_eff.definir_series(
            [{"nom": "Efficience", "couleur": "#26C6DA",
              "valeurs": [(j[8:10] + "/" + j[5:7], v) for j, v, _ in serie_e]}] if serie_e else [])
        evo = evolution_efficience(serie_e)
        if evo is None:
            self.note_eff.setText("Pas assez de semaines avec courses/trails et FC pour juger l'évolution.")
        else:
            lecture = ("en progression : tu vas plus vite pour le même effort cardiaque." if evo > 1.5
                       else "en baisse : fatigue, chaleur ou forme en retrait ?" if evo < -1.5
                       else "stable.")
            self.note_eff.setText(
                f"4 dernières semaines vs 4 précédentes : {evo:+.1f} % — {lecture} "
                "(mètres à plat équivalent par minute et par battement ; D+ converti à 125 m ≈ 1 km.)")

        # --- Intensité
        rep, nb_g, nb_e = repartition_intensite(athlete_id, 12)
        self.courbe_int.definir_series([
            {"nom": "Facile (zones 1-2) %", "couleur": "#66BB6A",
             "valeurs": [(j[8:10] + "/" + j[5:7], f) for j, f, _, _ in rep]},
            {"nom": "Moyen (zone 3) %", "couleur": "#F9A825",
             "valeurs": [(j[8:10] + "/" + j[5:7], m) for j, _, m, _ in rep]},
            {"nom": "Dur (zones 4-5) %", "couleur": "#EF5350",
             "valeurs": [(j[8:10] + "/" + j[5:7], d_) for j, _, _, d_ in rep]},
        ] if rep else [])
        if rep:
            facile4 = mean(f for _, f, _, _ in rep[-4:])
            self.note_int.setText(
                f"Part de temps facile sur les 4 dernières semaines : {facile4:.0f} % (repère courant : ≈ 80 %). "
                f"Source : zones Garmin pour {nb_g} sortie(s), estimation d'après la FC moyenne pour {nb_e}."
            )
        else:
            self.note_int.setText("Aucune sortie avec FC ou zones sur les 12 dernières semaines.")

        # --- Dérive cardiaque
        der = derives_cardiaques(athlete_id)
        _remplir(self.table_derive, [(d, n, f"{k:.1f}" if k else "", f"{p:+.1f} %", i) for d, n, k, p, i in der])

        # --- Effet d'entraînement
        te = sorties_avec_effet(athlete_id, 90)
        lignes_te = []
        for s in te:
            z = [s.get(f"z{i}") or 0 for i in range(1, 6)]
            tot = sum(z)
            if tot:
                zs = (duree_texte(z[0] + z[1]), duree_texte(z[2]), duree_texte(z[3] + z[4]))
            else:
                zs = ("", "", "")
            lignes_te.append((
                s["date"][:10], s["nom"],
                "" if s["te_aerobie"] is None else f"{s['te_aerobie']:.1f}",
                "" if s["te_anaerobie"] is None else f"{s['te_anaerobie']:.1f}",
                "" if s["charge_garmin"] is None else f"{s['charge_garmin']:.0f}",
                *zs,
            ))
        _remplir(self.table_te, lignes_te)
