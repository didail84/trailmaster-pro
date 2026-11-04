"""
Poids & récupération — un seul écran pour le poids, l'état des jambes et la
fatigue au fil des jours (fusion des anciens onglets « Poids & fatigue » et
« Poids lissé et objectif », v100).

Une ligne par relevé, avec son moment (matin, soir, après séance). Seules
les pesées du MATIN alimentent les cartes, la courbe lissée et les
moyennes : ce sont les seules comparables d'un jour à l'autre (eau,
glycogène, repas et transpiration font varier les autres).

En haut : dernier poids, moyenne sur 7 jours, perte depuis le poids de
départ, reste jusqu'à l'objectif, fatigue et jambes au réveil. Puis le
poids brut avec sa courbe lissée, la fatigue, et le tableau de tous les
relevés avec la séance de la veille (tirée des sorties déjà synchronisées
et des séances de salle — rien à ressaisir).

Tous les champs hors date sont facultatifs : une case laissée à 0 est
enregistrée comme « non renseignée ».
"""

from datetime import date, timedelta

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QGridLayout, QFrame, QLabel, QPushButton, QMessageBox, QFileDialog,
    QInputDialog,
)

import noyau.entrainement.metriques as met
from data.database import connexion
from noyau.imports.import_suivi_excel import MOMENTS
from noyau.sante.mensurations import MESURES, serie_mesure, resume_mesures

COLONNES_MESURES = list(MESURES)
from interface.ecran_liste import EcranListe, Champ, obtenir_style_ecran
from interface.courbe_multiligne import CourbeMultiLignes


ETATS_JAMBES = ["Normales", "Lourdes", "Fatiguées", "Courbatures", "Douloureuses"]
VERT, ORANGE, BLEU, GRIS = "#66BB6A", "#FFA726", "#42A5F5", "#5C6770"


def _fr(nombre, decimales=1):
    return f"{nombre:.{decimales}f}".replace(".", ",")


def _formater_date_courte(date_texte):
    jour = str(date_texte)[:10]
    try:
        annee, mois, j = jour.split("-")
        return f"{j}/{mois}"
    except ValueError:
        return jour


def _date_longue(d):
    return d.strftime("%d/%m/%Y") if isinstance(d, date) else f"{str(d)[8:10]}/{str(d)[5:7]}/{str(d)[:4]}"


def _lire_ligne(id_ligne):
    conn = connexion()
    cur = conn.cursor()
    cur.execute("SELECT athlete_id, date, COALESCE(moment, 'matin'), poids_kg FROM suivi_corporel WHERE id=?",
                (id_ligne,))
    ligne = cur.fetchone()
    conn.close()
    return ligne


def _calculer_variation_poids(id_ligne, valeurs):
    """Écart avec la pesée du matin précédente (relevés du matin seulement)."""
    ligne = _lire_ligne(id_ligne)
    if not ligne or not ligne[3]:
        return "—"
    athlete_id, date_, moment, poids = ligne
    if moment != "matin":
        return "— (hors matin)"
    conn = connexion()
    cur = conn.cursor()
    cur.execute(
        "SELECT poids_kg FROM suivi_corporel WHERE athlete_id=? AND poids_kg > 0 "
        "AND COALESCE(moment, 'matin')='matin' AND date < ? ORDER BY date DESC, id DESC LIMIT 1",
        (athlete_id, date_),
    )
    precedent = cur.fetchone()
    conn.close()
    if not precedent:
        return "— (premier relevé)"
    ecart = round(poids - precedent[0], 1)
    if ecart == 0:
        return "= stable"
    return f"{'+' if ecart > 0 else '−'}{_fr(abs(ecart))} kg"


def _seance_liee(id_ligne, valeurs):
    """Séance de la veille pour un relevé du matin, du jour sinon."""
    ligne = _lire_ligne(id_ligne)
    if not ligne:
        return "—"
    athlete_id, date_, moment, _ = ligne
    try:
        jour = date.fromisoformat(str(date_)[:10])
    except ValueError:
        return "—"
    if moment == "matin":
        texte = met.seances_du_jour(athlete_id, jour - timedelta(days=1))
        return texte or "Repos (veille)"
    return met.seances_du_jour(athlete_id, jour) or "—"


def donnees_courbes(athlete_id):
    """Séries des deux courbes — poids du matin (brut + lissé) ; fatigue
    générale + jambes au réveil — partagées par la fenêtre de courbes et
    l'écran. Retourne (séries poids, séries fatigue, valeurs poids brutes)."""
    p = met.poids_lisse(athlete_id, 3650)
    valeurs_poids = [(j.strftime("%d/%m"), v) for j, v in p["brut"]]
    serie_poids = []
    if valeurs_poids:
        serie_poids = [
            {"nom": "Pesée du matin (kg)", "couleur": GRIS, "valeurs": valeurs_poids},
            {"nom": "Lissé (kg)", "couleur": BLEU, "valeurs": [(j.strftime("%d/%m"), v) for j, v in p["lisse"]]},
        ]

    conn = connexion()
    cur = conn.cursor()
    cur.execute(
        "SELECT date, fatigue_jambes, fatigue_generale FROM suivi_corporel "
        "WHERE athlete_id=? AND COALESCE(moment, 'matin')='matin' "
        "AND (fatigue_jambes IS NOT NULL OR fatigue_generale IS NOT NULL) ORDER BY date, id",
        (athlete_id,),
    )
    dates_fatigue = cur.fetchall()
    conn.close()

    series_fatigue = []
    if dates_fatigue:
        a_des_jambes = sum(1 for _, fj, _ in dates_fatigue if fj is not None) >= 2
        # Une valeur manquante un jour donné reprend la dernière connue
        # (la courbe n'accepte pas de trou) — sans valeur antérieure, on
        # part de 0 plutôt que d'inventer un chiffre.
        dernier_fg, dernier_fj = 0, 0
        valeurs_fg, valeurs_fj = [], []
        for d, fj, fg in dates_fatigue:
            if fg is not None:
                dernier_fg = fg
            if fj is not None:
                dernier_fj = fj
            etiquette = _formater_date_courte(d)
            valeurs_fg.append((etiquette, dernier_fg))
            valeurs_fj.append((etiquette, dernier_fj))
        series_fatigue.append({"nom": "Fatigue générale", "couleur": ORANGE, "valeurs": valeurs_fg})
        if a_des_jambes:
            series_fatigue.append({"nom": "Fatigue jambes", "couleur": "#B388FF", "valeurs": valeurs_fj})
    return serie_poids, series_fatigue, valeurs_poids


def _repere_objectif(courbe, athlete_id, valeurs_poids):
    """Ligne d'objectif seulement si elle est proche des pesées : à 10 kg
    sous la courbe, elle l'écraserait au bas du cadre."""
    objectif = met.objectif_poids(athlete_id)
    courbe.reperes = []
    if objectif and valeurs_poids and objectif >= min(v for _, v in valeurs_poids) - 3:
        courbe.reperes = [(objectif, f"objectif {_fr(objectif)} kg", VERT)]


class DialogueCourbesPoidsFatigue(QDialog):

    def __init__(self, athlete_id, parent=None):
        super().__init__(parent)
        self.setWindowTitle("TrailMaster Pro – Courbes poids & récupération")
        self.resize(900, 700)
        self.setStyleSheet(obtenir_style_ecran())
        layout = QVBoxLayout(self)
        serie_poids, series_fatigue, valeurs_poids = donnees_courbes(athlete_id)

        titre_poids = QLabel("⚖️ Poids du matin (kg)")
        titre_poids.setObjectName("titreCarte")
        layout.addWidget(titre_poids)
        self.courbe_poids = CourbeMultiLignes()
        self.courbe_poids.echelle_ajustee = True
        _repere_objectif(self.courbe_poids, athlete_id, valeurs_poids)
        self.courbe_poids.definir_series(serie_poids)
        layout.addWidget(self.courbe_poids)

        if len(valeurs_poids) >= 2:
            ecart = round(valeurs_poids[-1][1] - valeurs_poids[0][1], 1)
            signe = "+" if ecart > 0 else "−" if ecart < 0 else ""
            resume = QLabel(
                f"Du premier au dernier relevé du matin : {_fr(valeurs_poids[0][1])} kg → "
                f"{_fr(valeurs_poids[-1][1])} kg ({signe}{_fr(abs(ecart))} kg)"
            )
            resume.setObjectName("texteSecondaire")
            layout.addWidget(resume)

        titre_fatigue = QLabel("😮‍💨 Fatigue au réveil (0 à 10)")
        titre_fatigue.setObjectName("titreCarte")
        layout.addWidget(titre_fatigue)
        self.courbe_fatigue = CourbeMultiLignes()
        self.courbe_fatigue.definir_series(series_fatigue)
        layout.addWidget(self.courbe_fatigue)

        note = QLabel(
            "Un jour sans valeur reprend la dernière valeur connue sur la courbe. "
            "Les points sont espacés régulièrement, pas selon l'écart réel en jours."
        )
        note.setObjectName("texteSecondaire")
        note.setWordWrap(True)
        layout.addWidget(note)

        bouton_fermer = QPushButton("Fermer")
        bouton_fermer.clicked.connect(self.accept)
        layout.addWidget(bouton_fermer)


def _athlete_requis(ecran, action):
    athlete_id = ecran.athlete_selectionne_id()
    if athlete_id is None:
        QMessageBox.information(ecran, "Athlète requis", f"Sélectionne d'abord un athlète pour {action}.")
    return athlete_id


def _ouvrir_courbes(ecran):
    athlete_id = _athlete_requis(ecran, "voir ses courbes")
    if athlete_id is not None:
        DialogueCourbesPoidsFatigue(athlete_id, ecran).exec()


def _fixer_objectif(ecran):
    athlete_id = _athlete_requis(ecran, "fixer son objectif")
    if athlete_id is None:
        return
    actuel = met.objectif_poids(athlete_id) or 0.0
    valeur, ok = QInputDialog.getDouble(ecran, "Objectif de poids", "Poids visé (kg) — 0 pour effacer :",
                                        actuel, 0, 250, 1)
    if ok:
        met.definir_objectif_poids(athlete_id, valeur if valeur > 0 else None)
        ecran.charger_donnees()


def _fixer_depart(ecran):
    athlete_id = _athlete_requis(ecran, "fixer son poids de départ")
    if athlete_id is None:
        return
    actuel = met.poids_depart(athlete_id) or 0.0
    valeur, ok = QInputDialog.getDouble(ecran, "Poids de départ",
                                        "Poids au début du suivi (kg) — 0 pour effacer :", actuel, 0, 250, 1)
    if ok:
        met.definir_poids_depart(athlete_id, valeur if valeur > 0 else None)
        ecran.charger_donnees()


def _importer_excel(ecran):
    """Importe un classeur Excel (.xlsx) ou CSV de suivi poids/jambes/RPE
    dans la liste — voir data/import_suivi_excel.py pour le format."""
    from noyau.imports.import_suivi_excel import importer_fichier

    athlete_id = _athlete_requis(ecran, "importer son suivi")
    if athlete_id is None:
        return

    chemin, _ = QFileDialog.getOpenFileName(
        ecran, "Choisir le fichier Excel du suivi", "",
        "Excel ou CSV (*.xlsx *.csv);;Tous les fichiers (*)",
    )
    if not chemin:
        return

    try:
        bilan = importer_fichier(athlete_id, chemin)
    except Exception as erreur:
        QMessageBox.warning(
            ecran, "Import impossible",
            f"Le fichier n'a pas pu être lu :\n{erreur}\n\n"
            "Il faut une première ligne de titres avec au moins une colonne « Date ».",
        )
        return

    lignes = [
        f"✅ {bilan['ajoutes']} relevé(s) ajouté(s)",
        f"➕ {bilan['completes']} relevé(s) existant(s) complété(s) (cases vides remplies)",
        f"＝ {bilan['inchanges']} déjà à jour",
    ]
    if bilan["sans_date"]:
        lignes.append(
            f"⚠️ {bilan['sans_date']} ligne(s) sans date précise ignorée(s) "
            "(aucune date n'est inventée — ajoute-les à la main avec une date si tu veux)"
        )
    if bilan["vides"]:
        lignes.append(f"○ {bilan['vides']} ligne(s) sans aucune valeur ignorée(s)")
    QMessageBox.information(ecran, "Import terminé", "\n".join(lignes))
    ecran.charger_donnees()


def nettoyer_cases_vides():
    """Le formulaire écrit 0 (ou un état vide) dans les cases non remplies :
    on les remet à « non renseigné » pour ne pas fausser moyennes et courbes."""
    conn = connexion()
    cur = conn.cursor()
    for colonne in ("poids_kg", "fatigue_jambes", "fatigue_generale", *COLONNES_MESURES):
        cur.execute(f"UPDATE suivi_corporel SET {colonne}=NULL WHERE {colonne}=0")
    cur.execute("UPDATE suivi_corporel SET etat_jambes=NULL WHERE etat_jambes=''")
    cur.execute("UPDATE suivi_corporel SET moment='matin' WHERE moment IS NULL OR moment=''")
    conn.commit()
    conn.close()


class PoidsFatigue(EcranListe):

    def __init__(self, athlete_id_initial=None):
        champs = [
            Champ("date", "Date", "date", obligatoire=True),
            Champ("moment", "Moment", "choix", choix=MOMENTS),
            Champ("poids_kg", "Poids (kg)", "decimal"),
            Champ("etat_jambes", "État des jambes", "choix", choix=[""] + ETATS_JAMBES),
            Champ("fatigue_jambes", "Fatigue jambes (0-10)", "entier"),
            Champ("fatigue_generale", "Fatigue générale (0-10)", "entier"),
            Champ("tour_taille_cm", "Tour de taille (cm)", "decimal"),
            Champ("tour_hanches_cm", "Tour de hanches (cm)", "decimal"),
            Champ("tour_poitrine_cm", "Tour de poitrine (cm)", "decimal"),
            Champ("tour_cuisse_cm", "Tour de cuisse (cm)", "decimal"),
            Champ("tour_bras_cm", "Tour de bras (cm)", "decimal"),
            Champ("masse_grasse_pct", "Masse grasse (%)", "decimal"),
            Champ("notes", "Notes", "texte_long"),
        ]
        self._colonnes = [c.nom for c in champs] + ["variation", "seance"]
        super().__init__(
            titre="Poids & récupération",
            sous_titre=(
                "Poids, jambes et fatigue — de préférence le matin au réveil. Les cartes, la courbe lissée "
                "et les moyennes n'utilisent que les relevés du matin. Tous les champs sont facultatifs."
            ),
            icone="⚖️",
            table_sql="suivi_corporel",
            champs=champs,
            athlete_id_initial=athlete_id_initial,
            tri="date DESC, CASE COALESCE(moment, 'matin') WHEN 'matin' THEN 0 WHEN 'après séance' THEN 1 ELSE 2 END DESC",
            colonnes_calculees=[
                {"label": "Variation poids", "fonction": _calculer_variation_poids},
                {"label": "Séance de la veille", "fonction": _seance_liee},
            ],
            bouton_extra=[
                ("📈 Voir les courbes", _ouvrir_courbes),
                ("📥 Importer un Excel / CSV", _importer_excel),
                ("🎯 Objectif de poids…", _fixer_objectif),
                ("🏁 Poids de départ…", _fixer_depart),
            ],
        )
        for nom in ("fatigue_jambes", "fatigue_generale"):
            self.widgets_champs[nom].setRange(0, 10)
            self.widgets_champs[nom].setSpecialValueText("—")
        for nom in COLONNES_MESURES:
            w = self.widgets_champs[nom]
            w.setRange(0, 100 if nom == "masse_grasse_pct" else 250)
            w.setDecimals(1)
            w.setSpecialValueText("—")
        self.widgets_champs["poids_kg"].setRange(0, 250)
        self.widgets_champs["poids_kg"].setDecimals(1)
        self.widgets_champs["poids_kg"].setSpecialValueText("—")
        self._construire_apercu()
        self.charger_donnees()

    def ajouter_ligne(self):
        super().ajouter_ligne()
        nettoyer_cases_vides()
        self.charger_donnees()

    # ------------------------------------------------------------
    # Mise en page « tout d'un coup d'œil » : cartes, courbes, relevés
    # ------------------------------------------------------------
    def _construire_apercu(self):
        self._cartes = {}
        grille = QGridLayout()
        grille.setSpacing(15)
        titres = (("poids", "Dernier poids du matin"), ("moy7", "Moyenne 7 jours"),
                  ("perte", "Perdu depuis le départ"), ("objectif", "Reste jusqu'à l'objectif"),
                  ("fatigue", "Fatigue au réveil"), ("jambes", "Jambes au réveil"),
                  ("taille", "Tour de taille"), ("mesures", "Autres mesures"))
        for n, (cle, titre) in enumerate(titres):
            cadre = QFrame()
            cadre.setObjectName("carteForm")
            lay = QVBoxLayout(cadre)
            t = QLabel(titre)
            t.setObjectName("texteSecondaire")
            v = QLabel("—")
            v.setStyleSheet("font-size: 24px; font-weight: 700;")
            d = QLabel("")
            d.setObjectName("texteSecondaire")
            d.setWordWrap(True)
            d.setTextFormat(Qt.TextFormat.RichText)
            lay.addWidget(t)
            lay.addWidget(v)
            lay.addWidget(d)
            self._cartes[cle] = (v, d)
            grille.addWidget(cadre, n // 4, n % 4)
        self.zone_haut.addLayout(grille)

        cadre_poids = QFrame()
        cadre_poids.setObjectName("carteForm")
        lp = QVBoxLayout(cadre_poids)
        tp = QLabel("Poids du matin — pesées et courbe lissée")
        tp.setObjectName("titreCarte")
        np_ = QLabel("Le poids varie de 1 à 2 kg d'un jour à l'autre (eau, repas, grosse sortie) : "
                     "la courbe lissée (moyenne sur environ une semaine) montre la vraie tendance.")
        np_.setObjectName("texteSecondaire")
        np_.setWordWrap(True)
        self.courbe_poids_page = CourbeMultiLignes()
        self.courbe_poids_page.setMinimumHeight(250)
        self.courbe_poids_page.echelle_ajustee = True
        lp.addWidget(tp)
        lp.addWidget(np_)
        lp.addWidget(self.courbe_poids_page)
        self.zone_haut.addWidget(cadre_poids)

        cadre_fat = QFrame()
        cadre_fat.setObjectName("carteForm")
        lf = QVBoxLayout(cadre_fat)
        tf = QLabel("Fatigue au réveil (0 à 10)")
        tf.setObjectName("titreCarte")
        nf = QLabel("Fatigue générale et fatigue des jambes du matin. Un jour sans valeur reprend la "
                    "dernière valeur connue ; survole la courbe pour lire les relevés.")
        nf.setObjectName("texteSecondaire")
        nf.setWordWrap(True)
        self.courbe_fatigue_page = CourbeMultiLignes()
        self.courbe_fatigue_page.setMinimumHeight(230)
        lf.addWidget(tf)
        lf.addWidget(nf)
        lf.addWidget(self.courbe_fatigue_page)
        self.zone_haut.addWidget(cadre_fat)

        cadre_mes = QFrame()
        cadre_mes.setObjectName("carteForm")
        lm = QVBoxLayout(cadre_mes)
        tm = QLabel("Mensurations")
        tm.setObjectName("titreCarte")
        nm = QLabel("Tour de taille et autres mesures saisis dans le formulaire sous le tableau "
                    "(cases facultatives). À mesurer dans les mêmes conditions : le matin, à jeun, "
                    "au niveau du nombril, sans serrer.")
        nm.setObjectName("texteSecondaire")
        nm.setWordWrap(True)
        self.courbe_mesures_page = CourbeMultiLignes()
        self.courbe_mesures_page.setMinimumHeight(220)
        self.courbe_mesures_page.echelle_ajustee = True
        lm.addWidget(tm)
        lm.addWidget(nm)
        lm.addWidget(self.courbe_mesures_page)
        self.cadre_mesures = cadre_mes
        self.zone_haut.addWidget(cadre_mes)

        from interface.analyse_ia_widget import CarteAnalyseIA
        from data import analyse_ecran as _ae
        self.carte_ia = CarteAnalyseIA("poids", "poids et jambes", lambda: self.combo_athlete.currentData(),
                                       lambda: _ae.dossier_poids(self.combo_athlete.currentData()))
        self.zone_haut.addWidget(self.carte_ia)

        # Titre du tableau, et formulaire d'ajout déplacé sous le tableau
        titre_table = QLabel("Tous les relevés")
        titre_table.setObjectName("titreCarte")
        i = self.principal.indexOf(self.table)
        self.principal.insertWidget(i, titre_table)
        self.principal.removeWidget(self.cadre_form)
        self.principal.addWidget(self.cadre_form)
        self.table.verticalHeader().setVisible(False)

    def charger_donnees(self):
        super().charger_donnees()
        if not hasattr(self, "_cartes"):
            return
        self._mettre_en_forme_table()
        self._rafraichir_apercu()

    def _mettre_en_forme_table(self):
        """Dates jj/mm/aaaa, poids avec unité, cases vides en « — »."""
        t = self.table
        col = {nom: i for i, nom in enumerate(self._colonnes)}
        for c in range(t.columnCount()):
            en_tete = t.horizontalHeaderItem(c)
            if en_tete and en_tete.text() != en_tete.text().upper():
                en_tete.setText(en_tete.text().upper())
        vides = ("", "0", "0.0", "None")
        mesures_col = {col[n] for n in COLONNES_MESURES}
        for r in range(t.rowCount()):
            for c in range(t.columnCount()):
                item = t.item(r, c)
                if item is None:
                    continue
                texte = item.text()
                if c == col["date"] and len(texte) >= 10 and texte[4:5] == "-":
                    item.setText(f"{texte[8:10]}/{texte[5:7]}/{texte[:4]}")
                elif c == col["poids_kg"] and texte not in vides:
                    item.setText(texte.replace(".", ",") + " kg")
                elif c in mesures_col and texte not in vides:
                    item.setText(texte.replace(".", ",") + (" %" if c == col["masse_grasse_pct"] else " cm"))
                elif c in (col["poids_kg"], col["fatigue_jambes"], col["fatigue_generale"],
                           col["etat_jambes"], *mesures_col) and texte in vides:
                    item.setText("—")
                elif c == col["moment"] and texte in vides:
                    item.setText("matin")
        t.resizeColumnsToContents()
        # Tous les relevés visibles d'un coup (la page défile), jusqu'à 25 lignes
        lignes_visibles = min(max(t.rowCount(), 3), 25)
        t.setMinimumHeight(t.horizontalHeader().height() + lignes_visibles * 32 + 8)

    def _rafraichir_mesures(self, athlete_id):
        """Cartes « Tour de taille » / « Autres mesures » et courbe des mensurations."""
        r = resume_mesures(athlete_id)
        c = self._cartes
        taille = r.get("tour_taille_cm")
        if taille:
            c["taille"][0].setText(f"{_fr(taille['derniere'])} cm")
            detail = f"relevé du {_date_longue(taille['date'])}"
            if taille["ecart"] is not None:
                e = taille["ecart"]
                couleur = VERT if e <= 0 else ORANGE
                signe = "+" if e > 0 else "−" if e < 0 else ""
                detail += (f'<br><span style="color:{couleur}">{signe}{_fr(abs(e))} cm</span> '
                           f"depuis le {_date_longue(taille['date_premiere'])}")
            c["taille"][1].setText(detail)
        else:
            c["taille"][1].setText("à saisir dans le formulaire (case « Tour de taille »)")
        autres = [m for k, m in r.items() if k != "tour_taille_cm"]
        if autres:
            c["mesures"][0].setText(f"{len(autres)} mesure(s)")
            c["mesures"][1].setText("<br>".join(
                f"{m['libelle']} : {_fr(m['derniere'])} {m['unite']}" for m in autres))
        else:
            c["mesures"][1].setText("hanches, poitrine, cuisse, bras, masse grasse")
        # Une seule courbe (la mesure principale) : mettre taille et cuisse sur
        # la même échelle écraserait la plus petite variation.
        series = []
        principale = next((k for k in ("tour_taille_cm", *r) if k in r and k != "masse_grasse_pct"), None)
        if principale:
            s = serie_mesure(athlete_id, principale)
            if len(s) >= 2:
                series.append({"nom": f"{MESURES[principale][0]} (cm)", "couleur": BLEU,
                               "valeurs": [(_formater_date_courte(d), v) for d, v in s]})
        self.courbe_mesures_page.definir_series(series)
        self.cadre_mesures.setVisible(bool(series))

    def _rafraichir_apercu(self):
        athlete_id = self.athlete_selectionne_id()
        for v, d in self._cartes.values():
            v.setText("—")
            v.setStyleSheet("font-size: 24px; font-weight: 700;")
            d.setText("")
        if athlete_id is None:
            self.courbe_poids_page.reperes = []
            self.courbe_poids_page.definir_series([])
            self.courbe_fatigue_page.definir_series([])
            self.courbe_mesures_page.definir_series([])
            return
        self._rafraichir_mesures(athlete_id)
        serie_poids, series_fatigue, valeurs_poids = donnees_courbes(athlete_id)
        _repere_objectif(self.courbe_poids_page, athlete_id, valeurs_poids)
        self.courbe_poids_page.definir_series(serie_poids)
        self.courbe_fatigue_page.definir_series(series_fatigue)

        r = met.resume_poids_recuperation(athlete_id)
        c = self._cartes
        if r["dernier_poids"] is not None:
            c["poids"][0].setText(f"{_fr(r['dernier_poids'])} kg")
            c["poids"][1].setText(f"relevé du {_date_longue(r['dernier_date'])}")
        else:
            c["poids"][1].setText("aucune pesée du matin")
        if r["moy7"] is not None:
            c["moy7"][0].setText(f"{_fr(r['moy7'])} kg")
            if r["ecart7"] is not None:
                e = r["ecart7"]
                couleur = VERT if e <= 0 else ORANGE
                signe = "+" if e > 0 else "−" if e < 0 else ""
                c["moy7"][1].setText(f'<span style="color:{couleur}">{signe}{_fr(abs(e))} kg</span> '
                                     f"vs les 7 jours précédents ({_fr(r['moy7_prec'])} kg)")
            else:
                c["moy7"][1].setText("pas encore de semaine précédente à comparer")
        if r["perte"] is not None:
            p = r["perte"]
            c["perte"][0].setText(f"{'−' if p >= 0 else '+'}{_fr(abs(p))} kg")
            c["perte"][1].setText(f"depuis {_fr(r['depart'])} kg")
        else:
            c["perte"][1].setText("bouton « Poids de départ… » pour le renseigner")
        if r["reste"] is not None:
            reste = r["reste"]
            c["objectif"][0].setText(f"{_fr(max(reste, 0))} kg" if reste > 0.05 else "atteint !")
            detail = f"objectif {_fr(r['objectif'])} kg"
            pl = met.poids_lisse(athlete_id, 365)
            if pl["semaines_restantes"] and reste > 0.05:
                detail += f"<br>≈ {pl['semaines_restantes']} semaine(s) au rythme actuel"
            if pl["tendance_kg_sem"] is not None:
                t = pl["tendance_kg_sem"]
                detail += f"<br>tendance {'+' if t > 0 else '−' if t < 0 else ''}{_fr(abs(t), 2)} kg/sem (4 sem.)"
            c["objectif"][1].setText(detail)
        else:
            c["objectif"][1].setText("bouton « Objectif de poids… » pour le fixer")
        if r["fatigue"] is not None:
            c["fatigue"][0].setText(f"{r['fatigue']} / 10")
            c["fatigue"][1].setText(f"relevé du {_date_longue(r['fatigue_date'])}")
        if r["jambes_date"] is not None:
            if r["jambes_note"] is not None:
                c["jambes"][0].setText(f"{r['jambes_note']} / 10")
                c["jambes"][1].setText(f"{r['jambes_etat'] + ' — ' if r['jambes_etat'] else ''}"
                                       f"relevé du {_date_longue(r['jambes_date'])}")
            else:
                c["jambes"][0].setText(r["jambes_etat"])
                c["jambes"][1].setText(f"relevé du {_date_longue(r['jambes_date'])}")
