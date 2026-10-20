"""
Import direct depuis une montre Garmin branchée en USB — lit les
fichiers .FIT du dossier GARMIN/Activity/ d'une montre montée comme
une simple clé USB, sans compte Garmin Connect ni connexion internet.

Deux cas de figure, traités dans le même écran :
- une sortie présente sur la montre mais absente de TrailMaster →
  importée comme une nouvelle activité (avec sa trace GPS) ;
- une sortie déjà enregistrée dans TrailMaster (par exemple via un
  import CSV/JSON plus pauvre, sans FC ni trace GPS) mais dont la
  version originale est encore sur la montre → seuls les champs
  manquants sont complétés, sans jamais écraser une valeur déjà
  présente (y compris une correction faite à la main dans le Détail
  de la sortie).

La correspondance entre un fichier .FIT et une activité déjà en base
utilise la même tolérance (écart de quelques minutes, distance
proche) que interface/doublons.py — pas un nouveau critère inventé.

Note sur les horaires : les fichiers .FIT stockent l'heure de départ
en UTC ; elle est convertie vers l'heure locale de cet ordinateur pour
la comparer aux dates déjà enregistrées (qui sont, elles, en heure
locale) — cohérent tant que TrailMaster est utilisé dans le même
fuseau horaire que celui où la sortie a été faite.
"""

import json
from datetime import timezone
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QComboBox,
    QPushButton,
    QLineEdit,
    QFileDialog,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QCheckBox,
    QFrame,
    QScrollArea,
    QMessageBox,
)

from data.database import connexion, creer_base_de_donnees, obtenir_athletes
from interface.ecran_liste import obtenir_style_ecran, configurer_table_redimensionnable
from interface.fit_utils import parser_fit, parser_resume_session_fit
from interface.doublons import FENETRE_TEMPS_MINUTES
from interface.date_utils import parser_date_flexible


# ------------------------------------------------------------------
# RECHERCHE DES FICHIERS .FIT SUR LA MONTRE
# ------------------------------------------------------------------

SOUS_DOSSIERS_ACTIVITE_CANDIDATS = ["GARMIN/Activity", "Garmin/Activity", "GARMIN/ACTIVITY", "Activity"]


def _lister_fit(dossier):
    return sorted(
        p for p in dossier.iterdir() if p.is_file() and p.suffix.lower() == ".fit"
    )


def trouver_fichiers_fit(dossier_racine):
    """Cherche les .FIT d'activités dans le dossier choisi — soit
    directement le dossier "Activity" de la montre, soit sa racine (on
    essaie alors les emplacements standard Garmin en priorité, pour
    éviter de remonter aussi les fichiers de suivi quotidien qui
    vivent ailleurs sur la montre ; un scan récursif reste le dernier
    recours si aucun des deux ne correspond)."""

    dossier_racine = Path(dossier_racine)
    if not dossier_racine.is_dir():
        return []

    if dossier_racine.name.lower() == "activity":
        return _lister_fit(dossier_racine)

    for sous_dossier in SOUS_DOSSIERS_ACTIVITE_CANDIDATS:
        candidat = dossier_racine / sous_dossier
        if candidat.is_dir():
            return _lister_fit(candidat)

    return sorted(
        p for p in dossier_racine.rglob("*") if p.is_file() and p.suffix.lower() == ".fit"
    )


def _fit_datetime_vers_local(dt_utc):
    if dt_utc is None:
        return None
    if dt_utc.tzinfo is None:
        dt_utc = dt_utc.replace(tzinfo=timezone.utc)
    return dt_utc.astimezone().replace(tzinfo=None)


# ------------------------------------------------------------------
# CORRESPONDANCE AVEC UNE ACTIVITÉ DÉJÀ EN BASE
# ------------------------------------------------------------------

# (colonne dans `activites`, clé dans le résumé FIT, libellé affiché)
CHAMPS_COMPLETABLES = [
    ("denivele", "denivele_positif", "D+"),
    ("denivele_negatif", "denivele_negatif", "D-"),
    ("frequence_cardiaque_moyenne", "fc_moyenne", "FC moyenne"),
    ("frequence_cardiaque_max", "fc_max", "FC max"),
    ("cadence_moyenne", "cadence_moyenne", "Cadence moyenne"),
    ("calories", "calories", "Calories"),
    ("vitesse_max", "vitesse_max_kmh", "Vitesse max"),
]


def _trouver_activite_correspondante(athlete_id, date_locale, distance_km):
    if date_locale is None:
        return None

    conn = connexion()
    cur = conn.cursor()
    cur.execute(
        "SELECT id, date, distance, denivele, denivele_negatif, duree, "
        "frequence_cardiaque_moyenne, frequence_cardiaque_max, cadence_moyenne, calories, "
        "vitesse_max FROM activites WHERE athlete_id=?",
        (athlete_id,),
    )
    lignes = cur.fetchall()

    for (id_, date_texte, distance, denivele, denivele_neg, duree, fc_moy, fc_max,
         cadence, calories, vitesse_max) in lignes:
        date_obj = parser_date_flexible(date_texte)
        if date_obj is None:
            continue
        ecart_minutes = abs((date_obj - date_locale).total_seconds()) / 60
        if ecart_minutes > FENETRE_TEMPS_MINUTES:
            continue
        distance = distance or 0
        if distance_km is not None and abs(distance - distance_km) > max(0.3, distance_km * 0.1):
            continue

        cur.execute("SELECT COUNT(*) FROM parcours_gpx WHERE activite_id=?", (id_,))
        a_une_trace = cur.fetchone()[0] > 0
        conn.close()
        return {
            "id": id_, "denivele": denivele, "denivele_negatif": denivele_neg, "duree": duree,
            "frequence_cardiaque_moyenne": fc_moy, "frequence_cardiaque_max": fc_max,
            "cadence_moyenne": cadence, "calories": calories, "vitesse_max": vitesse_max,
            "a_une_trace": a_une_trace,
        }

    conn.close()
    return None


def _champs_manquants(activite_db, resume_fit):
    manquants = []
    for champ_db, champ_fit, libelle in CHAMPS_COMPLETABLES:
        valeur_db = activite_db.get(champ_db)
        valeur_fit = resume_fit.get(champ_fit)
        if (valeur_db is None or valeur_db == 0) and valeur_fit not in (None, 0):
            manquants.append((champ_db, champ_fit, libelle))
    if not activite_db.get("a_une_trace"):
        manquants.append(("trace", None, "Trace GPS"))
    return manquants


# ------------------------------------------------------------------
# ANALYSE D'UN DOSSIER (lecture seule — rien n'est écrit en base ici)
# ------------------------------------------------------------------

def analyser_dossier(dossier_racine, athlete_id):
    """Retourne une liste de dicts, un par fichier .FIT trouvé :
    {chemin, statut, resume, date_locale, activite_id?, champs_manquants?, raison?}
    statut ∈ {'nouveau', 'a_completer', 'complet', 'ignore'}."""

    resultats = []
    for chemin in trouver_fichiers_fit(dossier_racine):
        resume = parser_resume_session_fit(chemin)
        date_locale = _fit_datetime_vers_local(resume.get("date_debut")) if resume else None

        if not resume or date_locale is None:
            resultats.append({
                "chemin": chemin, "statut": "ignore", "resume": resume or {},
                "raison": "Pas de données de session exploitables (probablement un fichier "
                          "de suivi quotidien de la montre, pas un enregistrement d'activité).",
            })
            continue

        correspondance = _trouver_activite_correspondante(
            athlete_id, date_locale, resume.get("distance_km")
        )

        if correspondance is None:
            resultats.append({
                "chemin": chemin, "statut": "nouveau", "resume": resume, "date_locale": date_locale,
            })
            continue

        champs_manquants = _champs_manquants(correspondance, resume)
        if not champs_manquants:
            resultats.append({
                "chemin": chemin, "statut": "complet", "resume": resume,
                "date_locale": date_locale, "activite_id": correspondance["id"],
            })
        else:
            resultats.append({
                "chemin": chemin, "statut": "a_completer", "resume": resume,
                "date_locale": date_locale, "activite_id": correspondance["id"],
                "champs_manquants": champs_manquants,
            })

    return resultats


def _invalider_cache():
    try:
        from interface.coach import invalider_cache_coach
        invalider_cache_coach()
    except ImportError:
        pass


# ------------------------------------------------------------------
# ÉCRITURE EN BASE
# ------------------------------------------------------------------

def importer_nouveau(chemin, athlete_id, resume, date_locale):
    """Crée une nouvelle activité (+ trace GPS si disponible) à partir
    d'un .FIT trouvé sur la montre et absent de TrailMaster. Retourne
    l'id de l'activité créée."""

    trace_info = parser_fit(chemin)
    distance_km = resume.get("distance_km") or trace_info.get("distance_km") or 0
    denivele_positif = resume.get("denivele_positif")
    if denivele_positif is None:
        denivele_positif = trace_info.get("denivele_positif") or 0
    denivele_negatif = resume.get("denivele_negatif")
    if denivele_negatif is None:
        denivele_negatif = trace_info.get("denivele_negatif") or 0
    duree_s = resume.get("duree_s") or 0
    allure_moyenne = round((duree_s / 60) / distance_km, 2) if distance_km else None
    type_sortie = resume.get("type") or "Autre"
    nom = f"{type_sortie} du {date_locale.strftime('%d/%m/%Y')}"

    conn = connexion()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO activites (
            athlete_id, date, nom, type, distance, denivele, denivele_negatif, duree,
            vitesse_moyenne, allure_moyenne, vitesse_max,
            frequence_cardiaque_moyenne, frequence_cardiaque_max,
            calories, cadence_moyenne, source, fichier_source
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            athlete_id, date_locale.strftime("%Y-%m-%d %H:%M:%S"), nom, type_sortie,
            distance_km, denivele_positif, denivele_negatif, duree_s,
            resume.get("vitesse_moyenne_kmh"), allure_moyenne, resume.get("vitesse_max_kmh"),
            resume.get("fc_moyenne"), resume.get("fc_max"),
            resume.get("calories"), resume.get("cadence_moyenne"),
            "Montre Garmin (USB)", chemin.name,
        ),
    )
    activite_id = cur.lastrowid

    if trace_info.get("points"):
        cur.execute(
            """
            INSERT INTO parcours_gpx (
                athlete_id, nom, distance_km, denivele_positif, denivele_negatif,
                trace_json, activite_id
            ) VALUES (?,?,?,?,?,?,?)
            """,
            (athlete_id, nom, distance_km, denivele_positif, denivele_negatif,
             json.dumps(trace_info["points"]), activite_id),
        )

    conn.commit()
    conn.close()
    _invalider_cache()
    return activite_id


def completer_activite(activite_id, chemin, champs_manquants):
    """Remplit uniquement les champs listés dans `champs_manquants`
    (voir _champs_manquants) — ne touche jamais un champ déjà rempli."""

    resume = parser_resume_session_fit(chemin)

    conn = connexion()
    cur = conn.cursor()

    assignations, valeurs = [], []
    for champ_db, champ_fit, _ in champs_manquants:
        if champ_db == "trace":
            continue
        valeur = resume.get(champ_fit)
        if valeur is None:
            continue
        assignations.append(f"{champ_db}=?")
        valeurs.append(valeur)

    if assignations:
        valeurs.append(activite_id)
        cur.execute(f"UPDATE activites SET {', '.join(assignations)} WHERE id=?", valeurs)

    if any(champ_db == "trace" for champ_db, _, _ in champs_manquants):
        trace_info = parser_fit(chemin)
        if trace_info.get("points"):
            cur.execute("SELECT athlete_id, nom, distance FROM activites WHERE id=?", (activite_id,))
            ligne = cur.fetchone()
            if ligne:
                athlete_id, nom, distance = ligne
                cur.execute(
                    """
                    INSERT INTO parcours_gpx (
                        athlete_id, nom, distance_km, denivele_positif, denivele_negatif,
                        trace_json, activite_id
                    ) VALUES (?,?,?,?,?,?,?)
                    """,
                    (athlete_id, nom, distance, trace_info.get("denivele_positif"),
                     trace_info.get("denivele_negatif"), json.dumps(trace_info["points"]), activite_id),
                )

    conn.commit()
    conn.close()
    _invalider_cache()


# ------------------------------------------------------------------
# ÉCRAN
# ------------------------------------------------------------------

LIBELLE_STATUT = {
    "nouveau": "🆕 Nouvelle activité",
    "a_completer": "🧩 À compléter",
    "complet": "✅ Déjà complet",
    "ignore": "⏭️ Ignoré",
}


class ImporterMontreUSB(QMainWindow):

    def __init__(self, athlete_id_initial=None):
        super().__init__()

        creer_base_de_donnees()

        self.setWindowTitle("TrailMaster Pro – Montre Garmin (USB)")
        self.resize(1250, 800)
        self.setMinimumSize(1000, 650)

        self.dossier_courant = None
        self.resultats_courants = []
        self.cases = []

        conteneur_scroll = QScrollArea()
        conteneur_scroll.setWidgetResizable(True)
        conteneur_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        conteneur_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        conteneur_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.setCentralWidget(conteneur_scroll)

        central = QWidget()
        conteneur_scroll.setWidget(central)

        principal = QVBoxLayout(central)
        principal.setContentsMargins(25, 20, 25, 20)
        principal.setSpacing(15)

        titre = QLabel("⌚ Montre Garmin (USB)")
        titre.setObjectName("titrePage")
        sous_titre = QLabel(
            "Branche ta montre en USB (elle apparaît comme une clé USB classique), choisis son "
            "dossier, et importe directement les sorties qui manquent — ou complète celles déjà "
            "enregistrées auxquelles il manque des informations (FC, D+, cadence, trace GPS...) "
            "tant qu'elles sont encore dans la mémoire de la montre. 100% local, aucune connexion "
            "internet ni compte Garmin nécessaire."
        )
        sous_titre.setObjectName("sousTitrePage")
        principal.addWidget(titre)
        principal.addWidget(sous_titre)

        barre = QHBoxLayout()
        label_athlete = QLabel("Athlète :")
        label_athlete.setObjectName("labelChamp")
        self.combo_athlete = QComboBox()
        for a in obtenir_athletes():
            self.combo_athlete.addItem(f"{a[2]} {a[1]}", a[0])
        if athlete_id_initial is not None:
            for i in range(self.combo_athlete.count()):
                if self.combo_athlete.itemData(i) == athlete_id_initial:
                    self.combo_athlete.setCurrentIndex(i)
                    break

        bouton_dossier = QPushButton("📂 Choisir le dossier de la montre")
        bouton_dossier.setObjectName("boutonSecondaire")
        bouton_dossier.clicked.connect(self.choisir_dossier)

        bouton_analyser = QPushButton("🔍 Analyser")
        bouton_analyser.setObjectName("boutonPrincipal")
        bouton_analyser.clicked.connect(self.analyser)

        barre.addWidget(label_athlete)
        barre.addWidget(self.combo_athlete)
        barre.addWidget(bouton_dossier)
        barre.addWidget(bouton_analyser)
        barre.addStretch()
        principal.addLayout(barre)

        self.champ_dossier = QLineEdit("")
        self.champ_dossier.setReadOnly(True)
        self.champ_dossier.setPlaceholderText("Aucun dossier choisi")
        principal.addWidget(self.champ_dossier)

        self.label_resultat = QLabel("—")
        self.label_resultat.setObjectName("texteSecondaire")
        self.label_resultat.setWordWrap(True)
        principal.addWidget(self.label_resultat)

        self.table = QTableWidget()
        colonnes = ["Traiter ?", "Fichier", "Date", "Type", "Distance (km)", "Statut", "Détail"]
        self.table.setColumnCount(len(colonnes))
        self.table.setHorizontalHeaderLabels(colonnes)
        configurer_table_redimensionnable(self.table)
        self.table.horizontalHeader().setSectionResizeMode(6, QHeaderView.ResizeMode.Stretch)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        principal.addWidget(self.table, 1)

        self.bouton_traiter = QPushButton("▶️ Traiter la sélection (importer / compléter)")
        self.bouton_traiter.setObjectName("boutonPrincipal")
        self.bouton_traiter.clicked.connect(self.traiter_selection)
        principal.addWidget(self.bouton_traiter)

        self.setStyleSheet(obtenir_style_ecran())

    def choisir_dossier(self):
        dossier = QFileDialog.getExistingDirectory(
            self, "Choisir le dossier de la montre (ou son dossier GARMIN/Activity)"
        )
        if dossier:
            self.dossier_courant = dossier
            self.champ_dossier.setText(dossier)

    def analyser(self):
        if not self.dossier_courant:
            QMessageBox.warning(self, "Dossier requis", "Choisis d'abord le dossier de la montre.")
            return

        athlete_id = self.combo_athlete.currentData()
        if athlete_id is None:
            QMessageBox.warning(self, "Athlète requis", "Sélectionne un athlète.")
            return

        self.resultats_courants = analyser_dossier(self.dossier_courant, athlete_id)
        self.table.setRowCount(0)
        self.cases = []

        if not self.resultats_courants:
            self.label_resultat.setText(
                "Aucun fichier .FIT trouvé dans ce dossier — vérifie que c'est bien le bon "
                "dossier de la montre (ou son sous-dossier GARMIN/Activity)."
            )
            return

        self.table.setRowCount(len(self.resultats_courants))
        for ligne, resultat in enumerate(self.resultats_courants):
            statut = resultat["statut"]
            case = QCheckBox()
            case.setChecked(statut in ("nouveau", "a_completer"))
            case.setEnabled(statut in ("nouveau", "a_completer"))
            self.table.setCellWidget(ligne, 0, case)
            self.cases.append(case)

            resume = resultat.get("resume", {})
            date_locale = resultat.get("date_locale")

            self.table.setItem(ligne, 1, QTableWidgetItem(resultat["chemin"].name))
            self.table.setItem(ligne, 2, QTableWidgetItem(date_locale.strftime("%d/%m/%Y %H:%M") if date_locale else "—"))
            self.table.setItem(ligne, 3, QTableWidgetItem(resume.get("type") or "—"))
            distance = resume.get("distance_km")
            self.table.setItem(ligne, 4, QTableWidgetItem(f"{distance:.2f}" if distance else "—"))
            self.table.setItem(ligne, 5, QTableWidgetItem(LIBELLE_STATUT.get(statut, statut)))

            if statut == "nouveau":
                detail = "Sera ajoutée comme nouvelle activité, avec sa trace GPS."
            elif statut == "a_completer":
                libelles = ", ".join(c[2] for c in resultat["champs_manquants"])
                detail = f"Complétera l'activité déjà enregistrée : {libelles}."
            elif statut == "complet":
                detail = "Déjà enregistrée et déjà complète — rien à faire."
            else:
                detail = resultat.get("raison", "")
            self.table.setItem(ligne, 6, QTableWidgetItem(detail))

        self.table.resizeColumnsToContents()
        nb_nouveau = sum(1 for r in self.resultats_courants if r["statut"] == "nouveau")
        nb_completer = sum(1 for r in self.resultats_courants if r["statut"] == "a_completer")
        self.label_resultat.setText(
            f"{len(self.resultats_courants)} fichier(s) .FIT trouvé(s) — {nb_nouveau} nouvelle(s) "
            f"activité(s), {nb_completer} à compléter."
        )

    def traiter_selection(self):
        a_traiter = [
            resultat for case, resultat in zip(self.cases, self.resultats_courants)
            if case.isChecked() and resultat["statut"] in ("nouveau", "a_completer")
        ]
        if not a_traiter:
            QMessageBox.information(self, "Rien à traiter", "Aucune ligne cochée.")
            return

        athlete_id = self.combo_athlete.currentData()
        nb_importees, nb_completees, nb_erreurs = 0, 0, 0

        for resultat in a_traiter:
            try:
                if resultat["statut"] == "nouveau":
                    importer_nouveau(
                        resultat["chemin"], athlete_id, resultat["resume"], resultat["date_locale"]
                    )
                    nb_importees += 1
                else:
                    completer_activite(
                        resultat["activite_id"], resultat["chemin"], resultat["champs_manquants"]
                    )
                    nb_completees += 1
            except Exception:
                nb_erreurs += 1

        message = f"{nb_importees} nouvelle(s) activité(s) importée(s), {nb_completees} complétée(s)."
        if nb_erreurs:
            message += f" {nb_erreurs} fichier(s) n'ont pas pu être traités."
        QMessageBox.information(self, "Terminé", message)

        self.analyser()
