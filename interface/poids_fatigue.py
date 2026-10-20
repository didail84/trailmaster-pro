"""
Suivi du poids et de la fatigue (jambes + générale) au fil des jours —
une ligne par relevé (souvent le matin au réveil), avec en option l'état
des jambes et une note libre (ex. « courbatures après le trail du
dimanche »). Un bouton ouvre les courbes d'évolution du poids et de la
fatigue pour repérer une tendance (perte de poids, fatigue qui
s'installe après une grosse semaine...).

Tous les champs hors date sont facultatifs : on peut saisir seulement le
poids un jour, seulement la fatigue un autre.
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFrame, QLabel, QPushButton, QMessageBox, QFileDialog,
)

from data.database import connexion
from interface.ecran_liste import EcranListe, Champ, obtenir_style_ecran
from interface.courbe_multiligne import CourbeMultiLignes
from data.suivi_corporel_initial import importer_historique_initial


ETATS_JAMBES = ["Normales", "Lourdes", "Fatiguées", "Courbatures", "Douloureuses"]


def _formater_date_courte(date_texte):
    jour = str(date_texte)[:10]
    try:
        annee, mois, j = jour.split("-")
        return f"{j}/{mois}"
    except ValueError:
        return jour


def _calculer_variation_poids(id_ligne, valeurs):
    conn = connexion()
    cur = conn.cursor()
    cur.execute(
        "SELECT athlete_id, date, poids_kg FROM suivi_corporel WHERE id=?", (id_ligne,)
    )
    ligne = cur.fetchone()
    if not ligne or ligne[2] is None:
        conn.close()
        return "—"

    athlete_id, date_, poids = ligne
    cur.execute(
        "SELECT poids_kg FROM suivi_corporel "
        "WHERE athlete_id=? AND poids_kg IS NOT NULL AND date < ? "
        "ORDER BY date DESC LIMIT 1",
        (athlete_id, date_),
    )
    precedent = cur.fetchone()
    conn.close()

    if not precedent:
        return "— (premier relevé)"
    ecart = round(poids - precedent[0], 1)
    if ecart == 0:
        return "= stable"
    signe = "+" if ecart > 0 else "−"
    return f"{signe}{abs(ecart)} kg"


def donnees_courbes(athlete_id):
    """Séries des deux courbes (poids ; fatigue générale + jambes) et
    quelques repères, partagées par la fenêtre de courbes et l'écran."""
    conn = connexion()
    cur = conn.cursor()
    cur.execute(
        "SELECT date, poids_kg, fatigue_jambes, fatigue_generale FROM suivi_corporel "
        "WHERE athlete_id=? ORDER BY date ASC",
        (athlete_id,),
    )
    lignes = cur.fetchall()
    conn.close()

    valeurs_poids = [(_formater_date_courte(d), p) for d, p, _, _ in lignes if p is not None]

    dates_fatigue = [(d, fj, fg) for d, _, fj, fg in lignes if fj is not None or fg is not None]
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
        series_fatigue.append({"nom": "Fatigue générale", "couleur": "#FFA726", "valeurs": valeurs_fg})
        if a_des_jambes:
            series_fatigue.append({"nom": "Fatigue jambes", "couleur": "#B388FF", "valeurs": valeurs_fj})

    serie_poids = [{"nom": "Poids (kg)", "couleur": "#42A5F5", "valeurs": valeurs_poids}] if valeurs_poids else []
    return serie_poids, series_fatigue, valeurs_poids


class DialogueCourbesPoidsFatigue(QDialog):

    def __init__(self, athlete_id, parent=None):
        super().__init__(parent)
        self.setWindowTitle("TrailMaster Pro – Courbes poids & fatigue")
        self.resize(900, 700)
        self.setStyleSheet(obtenir_style_ecran())
        layout = QVBoxLayout(self)
        serie_poids, series_fatigue, valeurs_poids = donnees_courbes(athlete_id)

        titre_poids = QLabel("⚖️ Poids (kg)")
        titre_poids.setObjectName("titreCarte")
        layout.addWidget(titre_poids)
        self.courbe_poids = CourbeMultiLignes()
        self.courbe_poids.definir_series(serie_poids)
        layout.addWidget(self.courbe_poids)

        if len(valeurs_poids) >= 2:
            ecart = round(valeurs_poids[-1][1] - valeurs_poids[0][1], 1)
            signe = "+" if ecart > 0 else "−" if ecart < 0 else ""
            resume = QLabel(
                f"Du premier au dernier relevé : {valeurs_poids[0][1]} kg → "
                f"{valeurs_poids[-1][1]} kg ({signe}{abs(ecart)} kg)"
            )
            resume.setObjectName("texteSecondaire")
            layout.addWidget(resume)

        titre_fatigue = QLabel("😮‍💨 Fatigue (0 à 10)")
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


def _ouvrir_courbes(ecran):
    athlete_id = ecran.athlete_selectionne_id()
    if athlete_id is None:
        QMessageBox.information(
            ecran, "Athlète requis", "Sélectionne d'abord un athlète pour voir ses courbes."
        )
        return
    DialogueCourbesPoidsFatigue(athlete_id, ecran).exec()


def _importer_excel(ecran):
    """Importe un classeur Excel (.xlsx) ou CSV de suivi poids/jambes/RPE
    dans la liste — voir data/import_suivi_excel.py pour le format."""
    from data.import_suivi_excel import importer_fichier

    athlete_id = ecran.athlete_selectionne_id()
    if athlete_id is None:
        QMessageBox.information(
            ecran, "Athlète requis", "Sélectionne d'abord un athlète pour importer son suivi."
        )
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


class PoidsFatigue(EcranListe):

    def __init__(self, athlete_id_initial=None):
        # Import unique de l'historique relevé à la main (voir le module).
        importer_historique_initial()

        champs = [
            Champ("date", "Date", "date", obligatoire=True),
            Champ("poids_kg", "Poids (kg)", "decimal"),
            Champ("etat_jambes", "État des jambes", "choix", choix=ETATS_JAMBES),
            Champ("fatigue_jambes", "Fatigue jambes (0-10)", "entier"),
            Champ("fatigue_generale", "Fatigue générale (0-10)", "entier"),
            Champ("notes", "Notes", "texte_long"),
        ]
        super().__init__(
            titre="Poids & fatigue",
            sous_titre=(
                "Poids, état des jambes et fatigue au réveil ou après une sortie — "
                "tous les champs sont facultatifs, une ligne par relevé"
            ),
            icone="⚖️",
            table_sql="suivi_corporel",
            champs=champs,
            athlete_id_initial=athlete_id_initial,
            tri="date DESC",
            colonnes_calculees=[
                {"label": "Variation poids", "fonction": _calculer_variation_poids},
            ],
            bouton_extra=[("📈 Voir les courbes", _ouvrir_courbes), ("📥 Importer un Excel", _importer_excel)],
        )
        self._construire_apercu()
        self.charger_donnees()

    # ------------------------------------------------------------
    # Mise en page « tout d'un coup d'œil » : cartes, courbes, relevés
    # ------------------------------------------------------------
    def _construire_apercu(self):
        self._cartes = {}
        ligne = QHBoxLayout()
        ligne.setSpacing(15)
        for cle, titre in (("poids", "Dernier poids"), ("variation", "Variation sur 30 jours"),
                           ("fatigue", "Fatigue générale"), ("jambes", "Jambes")):
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
            lay.addWidget(t)
            lay.addWidget(v)
            lay.addWidget(d)
            self._cartes[cle] = (v, d)
            ligne.addWidget(cadre, 1)
        self.zone_haut.addLayout(ligne)

        cadre_poids = QFrame()
        cadre_poids.setObjectName("carteForm")
        lp = QVBoxLayout(cadre_poids)
        tp = QLabel("Poids (kg)")
        tp.setObjectName("titreCarte")
        self.courbe_poids_page = CourbeMultiLignes()
        self.courbe_poids_page.setMinimumHeight(230)
        self.courbe_poids_page.echelle_ajustee = True
        lp.addWidget(tp)
        lp.addWidget(self.courbe_poids_page)
        self.zone_haut.addWidget(cadre_poids)

        cadre_fat = QFrame()
        cadre_fat.setObjectName("carteForm")
        lf = QVBoxLayout(cadre_fat)
        tf = QLabel("Fatigue (0 à 10)")
        tf.setObjectName("titreCarte")
        nf = QLabel("Un jour sans valeur reprend la dernière valeur connue ; "
                    "survole la courbe pour lire les relevés.")
        nf.setObjectName("texteSecondaire")
        nf.setWordWrap(True)
        self.courbe_fatigue_page = CourbeMultiLignes()
        self.courbe_fatigue_page.setMinimumHeight(230)
        lf.addWidget(tf)
        lf.addWidget(nf)
        lf.addWidget(self.courbe_fatigue_page)
        self.zone_haut.addWidget(cadre_fat)

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
        for c in range(t.columnCount()):
            en_tete = t.horizontalHeaderItem(c)
            if en_tete and en_tete.text() != en_tete.text().upper():
                en_tete.setText(en_tete.text().upper())
        for r in range(t.rowCount()):
            for c in range(t.columnCount()):
                item = t.item(r, c)
                if item is None:
                    continue
                texte = item.text()
                if c == 0 and len(texte) >= 10 and texte[4:5] == "-":
                    item.setText(f"{texte[8:10]}/{texte[5:7]}/{texte[:4]}")
                elif c == 1 and texte not in ("", "0", "0.0"):
                    item.setText(texte.replace(".", ",") + " kg")
                elif texte in ("", "0", "0.0") and c in (1, 3, 4):
                    item.setText("—")
                elif texte == "" and c == 2:
                    item.setText("—")
        t.resizeColumnsToContents()
        # Tous les relevés visibles d'un coup (la page défile), jusqu'à 25 lignes
        lignes_visibles = min(max(t.rowCount(), 3), 25)
        t.setMinimumHeight(t.horizontalHeader().height() + lignes_visibles * 32 + 8)

    def _rafraichir_apercu(self):
        athlete_id = self.athlete_selectionne_id()
        for v, d in self._cartes.values():
            v.setText("—")
            d.setText("")
        if athlete_id is None:
            self.courbe_poids_page.definir_series([])
            self.courbe_fatigue_page.definir_series([])
            return
        serie_poids, series_fatigue, _ = donnees_courbes(athlete_id)
        self.courbe_poids_page.definir_series(serie_poids)
        self.courbe_fatigue_page.definir_series(series_fatigue)

        conn = connexion()
        cur = conn.cursor()
        cur.execute("SELECT date, poids_kg, etat_jambes, fatigue_generale FROM suivi_corporel "
                    "WHERE athlete_id=? ORDER BY date DESC, id DESC", (athlete_id,))
        lignes = cur.fetchall()
        conn.close()

        def fr(d):
            return f"{str(d)[8:10]}/{str(d)[5:7]}/{str(d)[:4]}"

        avec_poids = [(d, p) for d, p, _, _ in lignes if p]
        if avec_poids:
            d0, p0 = avec_poids[0]
            self._cartes["poids"][0].setText(f"{p0:.1f}".replace(".", ",") + " kg")
            self._cartes["poids"][1].setText(f"relevé du {fr(d0)}")
            from datetime import datetime, timedelta
            try:
                limite = (datetime.strptime(str(d0)[:10], "%Y-%m-%d") - timedelta(days=30)).strftime("%Y-%m-%d")
                anciens = [(d, p) for d, p in avec_poids if str(d)[:10] <= limite]
                if anciens:
                    ref_d, ref_p = anciens[0]
                    ecart = round(p0 - ref_p, 1)
                    signe = "+" if ecart > 0 else "−" if ecart < 0 else ""
                    self._cartes["variation"][0].setText(f"{signe}{abs(ecart):.1f}".replace(".", ",") + " kg")
                    self._cartes["variation"][1].setText(f"depuis le {fr(ref_d)}")
                else:
                    self._cartes["variation"][1].setText("pas de relevé vieux de 30 jours")
            except ValueError:
                pass
        fatigues = [f for _, _, _, f in lignes if f is not None][:5]
        if fatigues:
            moyenne = sum(fatigues) / len(fatigues)
            self._cartes["fatigue"][0].setText(f"{moyenne:.1f}".replace(".", ",") + " / 10")
            self._cartes["fatigue"][1].setText(f"moyenne des {len(fatigues)} derniers relevés")
        jambes = [(d, e) for d, _, e, _ in lignes if e]
        if jambes:
            self._cartes["jambes"][0].setText(jambes[0][1])
            self._cartes["jambes"][1].setText(f"relevé du {fr(jambes[0][0])}")
