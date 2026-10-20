import sqlite3
import sys
import shutil
from pathlib import Path

# ----------------------------
# Base de données
# ----------------------------


def _dossier_configuration_locale():
    """Dossier local à CET ordinateur (jamais synchronisé) — sert à la
    fois d'emplacement par défaut pour la base (comme avant) et à
    stocker le petit pointeur texte utilisé par la synchronisation
    gratuite entre ordinateurs (voir plus bas) : ce pointeur doit rester
    propre à chaque machine, jamais lui-même dans un dossier partagé."""

    if sys.platform == "darwin":
        dossier = Path.home() / "Library" / "Application Support" / "TrailMaster Pro"
    elif sys.platform == "win32":
        import os
        dossier = Path(os.environ.get("APPDATA", Path.home())) / "TrailMaster Pro"
    else:
        dossier = Path.home() / ".local" / "share" / "TrailMaster Pro"

    dossier.mkdir(parents=True, exist_ok=True)
    return dossier


CHEMIN_POINTEUR_SYNC = _dossier_configuration_locale() / "emplacement_synchronise.txt"


def _emplacement_synchronise_configure():
    """Dossier synchronisé choisi par l'utilisateur (Réglages > Synchro-
    nisation), ex. un dossier iCloud Drive/Google Drive/OneDrive déjà
    installé sur cet ordinateur — ou None si la synchronisation n'est
    pas activée (comportement par défaut, base 100% locale)."""

    if CHEMIN_POINTEUR_SYNC.exists():
        chemin_texte = CHEMIN_POINTEUR_SYNC.read_text(encoding="utf-8").strip()
        if chemin_texte:
            return Path(chemin_texte)
    return None


def dossier_portable():
    """Version portable (clé USB, Windows) : si un dossier « Donnees » se
    trouve à côté de TrailMaster Pro.exe, la base et les photos y sont
    rangées — elles voyagent avec la clé au lieu de rester sur le PC."""

    if getattr(sys, "frozen", False) and sys.platform == "win32":
        dossier = Path(sys.executable).resolve().parent / "Donnees"
        if dossier.is_dir():
            return dossier
    return None


def _obtenir_chemin_bdd():
    """En exécution normale (python3 main.py), la base reste à côté du
    code, comme avant. Une fois empaquetée en vraie application
    (PyInstaller), le dossier du programme peut être en lecture seule
    et est de toute façon reconstruit à chaque nouvelle version : la
    base doit alors vivre dans un dossier utilisateur permanent.

    Dans les deux cas, si une synchronisation a été activée (pointeur
    présent), c'est ce dossier synchronisé qui prime sur tout le reste
    — c'est ce qui permet à deux installations (Mac et Windows, par
    exemple) de partager la même base via un dossier iCloud Drive/
    Google Drive/OneDrive déjà synchronisé entre les deux machines."""

    portable = dossier_portable()
    if portable is not None:
        return portable / "trailmaster.db"

    emplacement_sync = _emplacement_synchronise_configure()
    if emplacement_sync is not None:
        emplacement_sync.mkdir(parents=True, exist_ok=True)
        return emplacement_sync / "trailmaster.db"

    if not getattr(sys, "frozen", False):
        base_locale = Path(__file__).parent / "trailmaster.db"
        if base_locale.exists():
            return base_locale
        # Dossier du logiciel sans base (nouvelle version dézippée ailleurs,
        # copie propre pour partager le code...) : on reprend la base du
        # dossier utilisateur permanent (celle de l'application installée)
        # plutôt que d'en créer une vide à côté du code et de donner
        # l'impression que toutes les sorties ont disparu.
        return _dossier_configuration_locale() / "trailmaster.db"

    dossier = _dossier_configuration_locale()
    chemin = dossier / "trailmaster.db"

    # Migration ponctuelle : si une base existait déjà à côté du script
    # (utilisation précédente via Lancer_TrailMaster.command) et qu'aucune
    # base n'existe encore dans le nouvel emplacement, on la copie une
    # fois pour ne pas perdre les données déjà enregistrées.
    ancienne_base = Path(__file__).parent / "trailmaster.db"
    if not chemin.exists() and ancienne_base.exists():
        shutil.copy2(ancienne_base, chemin)

    return chemin


CHEMIN_BDD = _obtenir_chemin_bdd()


# --------------------------------------------------
# SYNCHRONISATION GRATUITE ENTRE ORDINATEURS
# --------------------------------------------------
# Principe : TrailMaster Pro n'héberge rien lui-même (pas de serveur, pas
# de compte à créer, donc gratuit par construction) — il se contente de
# stocker sa base dans un dossier que l'utilisateur synchronise lui-même
# avec le service gratuit de son choix (iCloud Drive, Google Drive,
# OneDrive, Dropbox...), déjà installé et connecté sur chaque ordinateur.
# Chaque appli pointe alors vers le même fichier via ce dossier partagé.
#
# Limite à connaître (documentée aussi côté interface) : comme pour tout
# fichier partagé via ce type d'outil, il ne faut utiliser qu'UN SEUL
# ordinateur à la fois, en le fermant complètement avant de basculer sur
# l'autre — une écriture simultanée depuis les deux machines risquerait
# de corrompre la base ou de faire perdre des données.

def emplacement_synchronise_actuel():
    """Retourne le chemin du dossier synchronisé actuellement configuré
    (texte), ou None si la base est purement locale à cet ordinateur."""

    emplacement = _emplacement_synchronise_configure()
    return str(emplacement) if emplacement else None


def activer_synchronisation(nouveau_dossier):
    """Configure nouveau_dossier comme emplacement partagé de la base.

    Si une base existe déjà dans ce dossier (cas du 2e ordinateur qui
    rejoint une synchronisation déjà en place sur le 1er), elle est
    conservée telle quelle — la base locale de CET ordinateur n'est
    surtout PAS copiée par-dessus, pour ne pas écraser les données déjà
    synchronisées. Sinon (1er ordinateur à activer la synchronisation),
    la base locale actuelle est copiée dans le nouveau dossier.

    Retourne un message à afficher à l'utilisateur. Un redémarrage
    complet de l'application est nécessaire pour que le changement
    prenne effet (CHEMIN_BDD n'est calculé qu'une fois, au démarrage)."""

    nouveau_dossier = Path(nouveau_dossier)
    nouveau_dossier.mkdir(parents=True, exist_ok=True)
    nouvelle_bdd = nouveau_dossier / "trailmaster.db"

    if nouvelle_bdd.exists():
        message = (
            "Une base de données existait déjà dans ce dossier (probablement déjà "
            "synchronisée depuis un autre ordinateur) — elle sera utilisée telle quelle. "
            "Ta base actuelle sur CET ordinateur n'a pas été copiée par-dessus."
        )
    else:
        shutil.copy2(CHEMIN_BDD, nouvelle_bdd)
        dossier_photos_source = CHEMIN_BDD.parent / "photos"
        if dossier_photos_source.exists():
            shutil.copytree(dossier_photos_source, nouveau_dossier / "photos", dirs_exist_ok=True)
        message = "Ta base de données actuelle a été copiée dans le dossier synchronisé."

    CHEMIN_POINTEUR_SYNC.write_text(str(nouveau_dossier), encoding="utf-8")
    return message


def desactiver_synchronisation():
    """Retire le pointeur de synchronisation : au prochain démarrage,
    l'appli revient à une base purement locale à cet ordinateur (celle
    qui était utilisée avant l'activation de la synchronisation, ou une
    nouvelle base vide si celle-ci n'existe plus)."""

    if CHEMIN_POINTEUR_SYNC.exists():
        CHEMIN_POINTEUR_SYNC.unlink()


def connexion():
    """Retourne une connexion SQLite avec les clés étrangères activées."""
    conn = sqlite3.connect(CHEMIN_BDD)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn
  
def creer_base_de_donnees():
    """Crée la base si elle n'existe pas."""

    conn = connexion()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS athletes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,

            nom TEXT NOT NULL,
            prenom TEXT NOT NULL,

            age INTEGER,
            sexe TEXT,

            taille INTEGER,
            poids REAL,

            fc_repos INTEGER,
            fc_max INTEGER,
            fc_seuil INTEGER,

            vma REAL,
            vo2max REAL,

            niveau TEXT,

            date_creation TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
# --------------------------------------------------
    # ACTIVITES (importées depuis Strava/Garmin)
    # --------------------------------------------------
    # NB : c'est la table réellement utilisée par l'import (nom français).
    # L'ancienne table "activities" (anglaise, jamais utilisée par le code,
    # 0 ligne) a été retirée du schéma lors du nettoyage.

    cur.execute("""
        CREATE TABLE IF NOT EXISTS activites (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            athlete_id INTEGER,
            date TEXT NOT NULL,
            nom TEXT,
            type TEXT,
            distance REAL DEFAULT 0,
            denivele INTEGER DEFAULT 0,
            duree INTEGER DEFAULT 0,
            vitesse_moyenne REAL,
            allure_moyenne REAL,
            frequence_cardiaque_moyenne INTEGER,
            frequence_cardiaque_max INTEGER,
            calories REAL,
            source TEXT,
            fichier_source TEXT,
            identifiant_externe TEXT,
            empreinte TEXT UNIQUE,
            notes TEXT,
            date_import TEXT DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY (athlete_id)
                REFERENCES athletes(id)
        )
    """)

    # --------------------------------------------------
    # IMPORTATIONS (historique des imports CSV)
    # --------------------------------------------------

    cur.execute("""
        CREATE TABLE IF NOT EXISTS importations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fichier TEXT,
            source TEXT,
            date_import TEXT DEFAULT CURRENT_TIMESTAMP,
            total INTEGER DEFAULT 0,
            nouvelles INTEGER DEFAULT 0,
            doublons INTEGER DEFAULT 0,
            erreurs INTEGER DEFAULT 0
        )
    """)

    # --------------------------------------------------
    # ENTRAINEMENTS
    # --------------------------------------------------

    cur.execute("""
        CREATE TABLE IF NOT EXISTS entrainements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            athlete_id INTEGER,
            date TEXT NOT NULL,
            type TEXT NOT NULL,
            distance REAL DEFAULT 0,
            denivele INTEGER DEFAULT 0,
            duree INTEGER DEFAULT 0,
            intensite TEXT,
            calories REAL DEFAULT 0,
            source TEXT,
            notes TEXT,

            FOREIGN KEY (athlete_id)
                REFERENCES athletes(id)
        )
    """)

    # --------------------------------------------------
    # PLANNING
    # --------------------------------------------------

    cur.execute("""
        CREATE TABLE IF NOT EXISTS planning (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            athlete_id INTEGER,
            date TEXT NOT NULL,
            type_seance TEXT NOT NULL,
            duree INTEGER DEFAULT 0,
            distance REAL DEFAULT 0,
            denivele INTEGER DEFAULT 0,
            objectif TEXT,
            notes TEXT,

            FOREIGN KEY (athlete_id)
                REFERENCES athletes(id)
        )
    """)

    # --------------------------------------------------
    # SOMMEIL
    # --------------------------------------------------

    cur.execute("""
        CREATE TABLE IF NOT EXISTS sommeil (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            athlete_id INTEGER,
            date TEXT NOT NULL,
            heure_coucher TEXT,
            heure_lever TEXT,
            duree_heures REAL,
            qualite INTEGER,
            reveils_nombre INTEGER DEFAULT 0,
            notes TEXT,

            FOREIGN KEY (athlete_id)
                REFERENCES athletes(id)
        )
    """)

    # --------------------------------------------------
    # BLESSURES
    # --------------------------------------------------

    cur.execute("""
        CREATE TABLE IF NOT EXISTS blessures (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            athlete_id INTEGER,
            date_debut TEXT NOT NULL,
            date_fin TEXT,
            zone_corporelle TEXT,
            type_blessure TEXT,
            gravite TEXT,
            cause TEXT,
            statut TEXT DEFAULT 'En cours',
            notes TEXT,

            FOREIGN KEY (athlete_id)
                REFERENCES athletes(id)
        )
    """)

    # --------------------------------------------------
    # SOINS (massage, kinésithérapeute, ostéopathe...)
    # --------------------------------------------------

    cur.execute("""
        CREATE TABLE IF NOT EXISTS soins (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            athlete_id INTEGER,
            date TEXT NOT NULL,
            type_soin TEXT,
            motif TEXT DEFAULT 'Entretien',
            praticien TEXT,
            blessure_id INTEGER,
            notes TEXT,

            FOREIGN KEY (athlete_id)
                REFERENCES athletes(id),
            FOREIGN KEY (blessure_id)
                REFERENCES blessures(id)
        )
    """)

    # --------------------------------------------------
    # SUIVI CORPOREL (poids + fatigue jambes / générale)
    # --------------------------------------------------

    cur.execute("""
        CREATE TABLE IF NOT EXISTS suivi_corporel (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            athlete_id INTEGER,
            date TEXT NOT NULL,
            poids_kg REAL,
            etat_jambes TEXT,
            fatigue_jambes INTEGER,
            fatigue_generale INTEGER,
            notes TEXT,

            FOREIGN KEY (athlete_id)
                REFERENCES athletes(id)
        )
    """)

    # --------------------------------------------------
    # MATERIEL
    # --------------------------------------------------

    cur.execute("""
        CREATE TABLE IF NOT EXISTS materiel (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            athlete_id INTEGER,
            nom TEXT NOT NULL,
            type TEXT,
            date_achat TEXT,
            km_actuels REAL DEFAULT 0,
            km_max_recommande REAL,
            statut TEXT DEFAULT 'Actif',
            notes TEXT,

            FOREIGN KEY (athlete_id)
                REFERENCES athletes(id)
        )
    """)

    # --------------------------------------------------
    # RESULTATS DE COURSES
    # --------------------------------------------------

    cur.execute("""
        CREATE TABLE IF NOT EXISTS resultats_courses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            athlete_id INTEGER,
            nom_course TEXT NOT NULL,
            date TEXT NOT NULL,
            distance REAL,
            denivele INTEGER,
            temps TEXT,
            classement_general INTEGER,
            classement_categorie INTEGER,
            objectif_atteint TEXT,
            notes TEXT,

            FOREIGN KEY (athlete_id)
                REFERENCES athletes(id)
        )
    """)

    # --------------------------------------------------
    # ZONES D'ENTRAINEMENT
    # --------------------------------------------------

    cur.execute("""
        CREATE TABLE IF NOT EXISTS zones_entrainement (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            athlete_id INTEGER,
            zone_numero INTEGER NOT NULL,
            nom_zone TEXT,
            fc_min INTEGER,
            fc_max INTEGER,
            allure_min TEXT,
            allure_max TEXT,
            description TEXT,

            FOREIGN KEY (athlete_id)
                REFERENCES athletes(id)
        )
    """)

    # --------------------------------------------------
    # NUTRITION
    # --------------------------------------------------

    cur.execute("""
        CREATE TABLE IF NOT EXISTS nutrition (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            athlete_id INTEGER,
            date TEXT NOT NULL,
            type_repas TEXT,
            aliments TEXT,
            calories REAL,
            glucides_g REAL,
            proteines_g REAL,
            lipides_g REAL,
            hydratation_l REAL,
            notes TEXT,

            FOREIGN KEY (athlete_id)
                REFERENCES athletes(id)
        )
    """)

    # --------------------------------------------------
    # OBJECTIFS
    # --------------------------------------------------

    cur.execute("""
        CREATE TABLE IF NOT EXISTS objectifs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            athlete_id INTEGER,
            titre TEXT NOT NULL,
            description TEXT,
            date_cible TEXT,
            type_objectif TEXT,
            statut TEXT DEFAULT 'À venir',
            priorite TEXT DEFAULT 'Moyenne',

            FOREIGN KEY (athlete_id)
                REFERENCES athletes(id)
        )
    """)

    # --------------------------------------------------
    # COURSES A VENIR (calendrier de trails suggérés)
    # --------------------------------------------------

    cur.execute("""
        CREATE TABLE IF NOT EXISTS courses_calendrier (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            athlete_id INTEGER,
            nom TEXT NOT NULL,
            date TEXT,
            lieu TEXT,
            region TEXT,
            distance_km REAL,
            denivele_m INTEGER,
            type_terrain TEXT,
            lien TEXT,
            source TEXT,
            notes TEXT,

            FOREIGN KEY (athlete_id)
                REFERENCES athletes(id)
        )
    """)

    # --------------------------------------------------
    # PARCOURS GPX
    # --------------------------------------------------

    cur.execute("""
        CREATE TABLE IF NOT EXISTS parcours_gpx (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            athlete_id INTEGER,
            nom TEXT NOT NULL,
            fichier_source TEXT,
            date_ajout TEXT DEFAULT CURRENT_TIMESTAMP,
            distance_km REAL,
            denivele_positif INTEGER,
            denivele_negatif INTEGER,
            altitude_min INTEGER,
            altitude_max INTEGER,
            trace_json TEXT,
            activite_id INTEGER,

            FOREIGN KEY (athlete_id)
                REFERENCES athletes(id),
            FOREIGN KEY (activite_id)
                REFERENCES activites(id)
        )
    """)

    # --------------------------------------------------
    # PHOTOS DES SORTIES (fichiers réduits dans photos/sorties/)
    # --------------------------------------------------

    cur.execute("""
        CREATE TABLE IF NOT EXISTS photos_sorties (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            athlete_id INTEGER,
            activite_id INTEGER,
            fichier TEXT NOT NULL,
            legende TEXT,
            date_prise TEXT,
            latitude REAL,
            longitude REAL,
            largeur INTEGER,
            hauteur INTEGER,
            empreinte TEXT,
            source TEXT,
            date_ajout TEXT DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY (athlete_id) REFERENCES athletes(id),
            FOREIGN KEY (activite_id) REFERENCES activites(id)
        )
    """)
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_photos_activite ON photos_sorties(activite_id)"
    )

    # --------------------------------------------------
    # v98 — ressenti après sortie, météo des sorties, objectifs annuels
    # --------------------------------------------------

    cur.execute("""
        CREATE TABLE IF NOT EXISTS ressentis_sorties (
            activite_id INTEGER PRIMARY KEY,
            athlete_id INTEGER,
            effort INTEGER,          -- 1 facile, 2 correct, 3 dur
            jambes INTEGER,          -- 1 légères, 2 normales, 3 lourdes
            humeur INTEGER,          -- 1 bof, 2 bien, 3 super
            date_saisie TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (activite_id) REFERENCES activites(id) ON DELETE CASCADE
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS meteo_sorties (
            activite_id INTEGER PRIMARY KEY,
            athlete_id INTEGER,
            temperature REAL,        -- °C au moment de la sortie
            humidite REAL,           -- %
            vent_kmh REAL,
            precipitation_mm REAL,
            source TEXT,
            date_maj TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (activite_id) REFERENCES activites(id) ON DELETE CASCADE
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS objectifs_annuels (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            athlete_id INTEGER NOT NULL,
            annee INTEGER NOT NULL,
            metrique TEXT NOT NULL,  -- distance_km | denivele_m | duree_h | sorties
            cible REAL NOT NULL,
            UNIQUE (athlete_id, annee, metrique)
        )
    """)

    # Migration : ajoute la photo de profil si elle n'existe pas déjà
    # (les bases créées avant cette mise à jour n'ont pas cette colonne).
    cur.execute("PRAGMA table_info(athletes)")
    colonnes_athletes = [c[1] for c in cur.fetchall()]
    if "photo_path" not in colonnes_athletes:
        cur.execute("ALTER TABLE athletes ADD COLUMN photo_path TEXT")

    # --------------------------------------------------
    # SÉANCES STRUCTURÉES
    # --------------------------------------------------

    cur.execute("""
        CREATE TABLE IF NOT EXISTS seances_structurees (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            athlete_id INTEGER,
            nom TEXT NOT NULL,
            type_seance TEXT,
            date_prevue TEXT,
            statut TEXT DEFAULT 'Prévue',
            etapes_json TEXT,
            activite_id INTEGER,
            score_conformite INTEGER,
            notes TEXT,

            FOREIGN KEY (athlete_id)
                REFERENCES athletes(id),
            FOREIGN KEY (activite_id)
                REFERENCES activites(id)
        )
    """)

    # --------------------------------------------------
    # PLANS D'ENTRAÎNEMENT
    # --------------------------------------------------

    cur.execute("""
        CREATE TABLE IF NOT EXISTS plans_entrainement (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            athlete_id INTEGER,
            nom TEXT NOT NULL,
            distance_cible TEXT,
            niveau TEXT,
            nb_semaines INTEGER,
            jours_par_semaine INTEGER,
            allure_objectif TEXT,
            date_debut TEXT,
            date_course TEXT,
            date_creation TEXT DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY (athlete_id)
                REFERENCES athletes(id)
        )
    """)

    # Migration : seances_structurees existait avant les plans, on lui
    # ajoute la colonne de liaison si elle n'existe pas déjà (les bases
    # déjà créées avant cette mise à jour n'ont pas cette colonne).
    cur.execute("PRAGMA table_info(seances_structurees)")
    colonnes_seances = [c[1] for c in cur.fetchall()]
    if "plan_id" not in colonnes_seances:
        cur.execute(
            "ALTER TABLE seances_structurees ADD COLUMN plan_id INTEGER "
            "REFERENCES plans_entrainement(id)"
        )

    # --------------------------------------------------
    # SEGMENTS PRÉCIS
    # --------------------------------------------------

    cur.execute("""
        CREATE TABLE IF NOT EXISTS segments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            athlete_id INTEGER,
            nom TEXT NOT NULL,
            distance_km REAL,
            denivele_positif INTEGER,
            points_reference_json TEXT,
            parcours_origine_id INTEGER,
            date_creation TEXT DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY (athlete_id)
                REFERENCES athletes(id),
            FOREIGN KEY (parcours_origine_id)
                REFERENCES parcours_gpx(id)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS segments_efforts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            segment_id INTEGER,
            parcours_id INTEGER,
            activite_id INTEGER,
            date TEXT,
            duree_s REAL,

            FOREIGN KEY (segment_id)
                REFERENCES segments(id),
            FOREIGN KEY (parcours_id)
                REFERENCES parcours_gpx(id),
            FOREIGN KEY (activite_id)
                REFERENCES activites(id)
        )
    """)

    # --------------------------------------------------
    # PARAMÈTRES DE L'APPLICATION (clé/valeur)
    # --------------------------------------------------

    cur.execute("""
        CREATE TABLE IF NOT EXISTS parametres_app (
            cle TEXT PRIMARY KEY,
            valeur TEXT
        )
    """)

    # Migration : lien optionnel vers l'activité GPS correspondante
    # (les bases créées avant cette mise à jour n'ont pas cette colonne).
    cur.execute("PRAGMA table_info(resultats_courses)")
    colonnes_resultats = [c[1] for c in cur.fetchall()]
    if "activite_id" not in colonnes_resultats:
        cur.execute(
            "ALTER TABLE resultats_courses ADD COLUMN activite_id INTEGER REFERENCES activites(id)"
        )

    # Migration : colonnes supplémentaires pour l'historique des activités
    # personnalisable (dénivelé négatif, allure/vitesse max, cadence,
    # VO2max estimé) — pas toutes remplies par les imports existants,
    # mais disponibles dès qu'une source de données les fournit.
    cur.execute("PRAGMA table_info(activites)")
    colonnes_activites = [c[1] for c in cur.fetchall()]
    colonnes_activites_a_ajouter = [
        ("denivele_negatif", "INTEGER"),
        ("vitesse_max", "REAL"),
        ("allure_max", "REAL"),
        ("cadence_moyenne", "INTEGER"),
        ("vo2max", "REAL"),
        # v91 — détail avancé d'une sortie (Garmin / Strava) servant à
        # analyser la fatigue : effet d'entraînement, charge Garmin, temps
        # par zone de FC (secondes), puissance, dynamique de course, etc.
        ("te_aerobie", "REAL"),
        ("te_anaerobie", "REAL"),
        ("charge_garmin", "REAL"),
        ("temps_zone_1", "INTEGER"),
        ("temps_zone_2", "INTEGER"),
        ("temps_zone_3", "INTEGER"),
        ("temps_zone_4", "INTEGER"),
        ("temps_zone_5", "INTEGER"),
        ("puissance_moyenne", "INTEGER"),
        ("puissance_max", "INTEGER"),
        ("oscillation_verticale", "REAL"),   # cm
        ("temps_contact_sol", "INTEGER"),    # ms
        ("longueur_foulee", "REAL"),         # m
        ("temperature_moyenne", "REAL"),     # °C
        ("effort_percu", "REAL"),            # RPE saisi dans Strava
        ("suffer_score", "INTEGER"),         # « effort relatif » Strava
    ]
    for nom_colonne, type_colonne in colonnes_activites_a_ajouter:
        if nom_colonne not in colonnes_activites:
            cur.execute(f"ALTER TABLE activites ADD COLUMN {nom_colonne} {type_colonne}")

    # Migration : lien optionnel objectif -> résultat de course (permet de
    # marquer un objectif "Atteint" automatiquement une fois la course faite,
    # au lieu de rester une case cochée à la main et jamais recroisée).
    cur.execute("PRAGMA table_info(objectifs)")
    colonnes_objectifs = [c[1] for c in cur.fetchall()]
    if "resultat_id" not in colonnes_objectifs:
        cur.execute(
            "ALTER TABLE objectifs ADD COLUMN resultat_id INTEGER REFERENCES resultats_courses(id)"
        )

    # Migration : liens optionnels blessure -> sortie / séance de
    # renforcement déclenchante (carnet de douleur unifié : une douleur
    # élevée notée en musculation peut être reliée à une fiche blessure).
    cur.execute("PRAGMA table_info(blessures)")
    colonnes_blessures = [c[1] for c in cur.fetchall()]
    if "activite_id" not in colonnes_blessures:
        cur.execute(
            "ALTER TABLE blessures ADD COLUMN activite_id INTEGER REFERENCES activites(id)"
        )
    if "musculation_suivi_id" not in colonnes_blessures:
        cur.execute(
            "ALTER TABLE blessures ADD COLUMN musculation_suivi_id "
            "INTEGER REFERENCES musculation_suivi(id)"
        )

    # Migration : lien optionnel séance planifiée -> parcours déjà créé/
    # importé (permet de préparer le tracé prévu avant de partir courir).
    cur.execute("PRAGMA table_info(seances_structurees)")
    colonnes_seances = [c[1] for c in cur.fetchall()]
    if "parcours_id" not in colonnes_seances:
        cur.execute(
            "ALTER TABLE seances_structurees ADD COLUMN parcours_id "
            "INTEGER REFERENCES parcours_gpx(id)"
        )

    # Migration : explication (texte local, toujours renseigné) attachée
    # à une séance quand la replanification automatique l'a modifiée —
    # visible directement dans l'écran "Séances structurées" pour
    # comprendre pourquoi telle séance a été allégée/déplacée.
    if "commentaire_replanification" not in colonnes_seances:
        cur.execute(
            "ALTER TABLE seances_structurees ADD COLUMN commentaire_replanification TEXT"
        )

    # --------------------------------------------------
    # REPLANIFICATION AUTOMATIQUE DU PLAN
    # --------------------------------------------------
    # Historique des passages de la replanification automatique sur un
    # plan (séances ratées, ACWR, dérive de FC...) : un "resume" texte
    # local est toujours généré (100% hors-ligne), et un "resume_ia"
    # optionnel peut être ajouté si l'utilisateur a demandé un
    # commentaire du coach IA (Gemini/Groq) pour ce passage précis.

    cur.execute("""
        CREATE TABLE IF NOT EXISTS replanifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            plan_id INTEGER,
            athlete_id INTEGER,
            date_generation TEXT DEFAULT CURRENT_TIMESTAMP,
            niveau_ajustement TEXT,
            resume TEXT,
            resume_ia TEXT,
            nb_seances_modifiees INTEGER,

            FOREIGN KEY (plan_id) REFERENCES plans_entrainement(id),
            FOREIGN KEY (athlete_id) REFERENCES athletes(id)
        )
    """)

    # --------------------------------------------------
    # ANALYSES IA (compte rendu par sortie, Gemini)
    # --------------------------------------------------
    # Une ligne par analyse générée (conservée même si régénérée, pour
    # garder un historique) — évite de rappeler l'API (gratuite mais à
    # quota) pour ré-afficher un compte rendu déjà obtenu.

    cur.execute("""
        CREATE TABLE IF NOT EXISTS analyses_ia (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            athlete_id INTEGER,
            activite_id INTEGER,
            date_generation TEXT DEFAULT CURRENT_TIMESTAMP,
            contenu TEXT,

            FOREIGN KEY (athlete_id) REFERENCES athletes(id),
            FOREIGN KEY (activite_id) REFERENCES activites(id)
        )
    """)

    # Migration : bilans périodiques (semaine/mois/année), en plus des
    # comptes rendus par sortie — mêmes lignes, distinguées par "type"
    # ("sortie" garde activite_id renseigné ; "semaine"/"mois"/"annee"
    # laissent activite_id à NULL et renseignent periode_cle à la place,
    # ex. "2026-S38", "2026-09", "2026").
    cur.execute("PRAGMA table_info(analyses_ia)")
    colonnes_analyses_ia = [c[1] for c in cur.fetchall()]
    if "type" not in colonnes_analyses_ia:
        cur.execute("ALTER TABLE analyses_ia ADD COLUMN type TEXT DEFAULT 'sortie'")
    if "periode_cle" not in colonnes_analyses_ia:
        cur.execute("ALTER TABLE analyses_ia ADD COLUMN periode_cle TEXT")

    # --------------------------------------------------
    # RENFORCEMENT MUSCULAIRE & MOBILITÉ
    # --------------------------------------------------

    cur.execute("""
        CREATE TABLE IF NOT EXISTS musculation_exercices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            athlete_id INTEGER,
            groupe_seance TEXT,
            exercice TEXT NOT NULL,
            charge_depart_kg REAL,
            bloc1 TEXT, bloc2 TEXT, bloc3 TEXT, bloc4 TEXT, bloc5 TEXT, bloc6 TEXT,

            FOREIGN KEY (athlete_id) REFERENCES athletes(id)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS musculation_suivi (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            athlete_id INTEGER,
            date TEXT,
            exercice TEXT,
            charge_kg REAL,
            series INTEGER,
            reps_prevues TEXT,
            rpe INTEGER,
            douleur INTEGER,
            charge_proposee REAL,
            decision TEXT,

            FOREIGN KEY (athlete_id) REFERENCES athletes(id)
        )
    """)

    # Migration : ajoute les colonnes "cardio machine" au suivi musculation
    # (les bases créées avant cette mise à jour n'ont pas ces colonnes).
    cur.execute("PRAGMA table_info(musculation_suivi)")
    colonnes_suivi = [c[1] for c in cur.fetchall()]
    colonnes_cardio_a_ajouter = [
        ("type_seance", "TEXT DEFAULT 'Renforcement'"),
        ("appareil", "TEXT"),
        ("duree_min", "REAL"),
        ("type_intensite", "TEXT"),
        ("valeur_intensite", "TEXT"),
        ("distance_km", "REAL"),
        ("fc_moyenne", "INTEGER"),
        ("calories", "INTEGER"),
        ("groupe_musculaire", "TEXT"),
    ]
    for nom_colonne, type_colonne in colonnes_cardio_a_ajouter:
        if nom_colonne not in colonnes_suivi:
            cur.execute(f"ALTER TABLE musculation_suivi ADD COLUMN {nom_colonne} {type_colonne}")

    cur.execute("""
        CREATE TABLE IF NOT EXISTS mobilite_exercices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            athlete_id INTEGER,
            categorie TEXT,
            exercice TEXT,
            moment_ou_objectif TEXT,
            zone TEXT,
            bloc1 TEXT, bloc2 TEXT, bloc3 TEXT, bloc4 TEXT, bloc5 TEXT, bloc6 TEXT,
            progression TEXT,

            FOREIGN KEY (athlete_id) REFERENCES athletes(id)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS planning_mobilite (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            athlete_id INTEGER,
            jour TEXT,
            duree TEXT,
            bloc TEXT,
            contenu TEXT,
            intensite TEXT,
            moment TEXT,

            FOREIGN KEY (athlete_id) REFERENCES athletes(id)
        )
    """)

    # --------------------------------------------------
    # ANALYSE TACTIQUE D'UNE COURSE À VENIR (objectif type "Course")
    # --------------------------------------------------
    # Une ligne par analyse générée (conservée même si régénérée, pour
    # garder un historique) : caractéristiques de la course saisies (ou
    # récupérées au mieux depuis une page web), diagnostic local
    # (stade d'entraînement, ACWR, forme, "à fond" ou "en réserve") et
    # commentaire IA (tactique de course, gestion de l'effort).

    cur.execute("""
        CREATE TABLE IF NOT EXISTS analyses_course (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            objectif_id INTEGER,
            athlete_id INTEGER,
            date_generation TEXT DEFAULT CURRENT_TIMESTAMP,
            distance_km REAL,
            denivele_positif INTEGER,
            denivele_negatif INTEGER,
            type_terrain TEXT,
            url_course TEXT,
            notes_course TEXT,
            recommandation TEXT,
            diagnostic_local TEXT,
            contenu_ia TEXT,

            FOREIGN KEY (objectif_id) REFERENCES objectifs(id),
            FOREIGN KEY (athlete_id) REFERENCES athletes(id)
        )
    """)

    # --------------------------------------------------
    # INDEX DE PERFORMANCE
    # --------------------------------------------------
    # Toutes les colonnes ci-dessous sont filtrées ("WHERE athlete_id=…",
    # "WHERE activite_id=…", etc.) dans de très nombreux écrans, mais
    # n'avaient jamais d'index : SQLite devait donc relire la table
    # entière à chaque ouverture de fenêtre. C'est particulièrement
    # coûteux pour "parcours_gpx", dont la colonne trace_json peut peser
    # plusieurs centaines de Ko par ligne — d'où la lenteur ressentie à
    # l'ouverture du détail d'une sortie. CREATE INDEX IF NOT EXISTS est
    # sans risque à rejouer à chaque démarrage (aucun effet si l'index
    # existe déjà).
    cur.execute("CREATE INDEX IF NOT EXISTS idx_activites_athlete_id ON activites(athlete_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_activites_empreinte ON activites(empreinte)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_parcours_gpx_athlete_id ON parcours_gpx(athlete_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_parcours_gpx_activite_id ON parcours_gpx(activite_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_segments_athlete_id ON segments(athlete_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_segments_efforts_segment_id ON segments_efforts(segment_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_segments_efforts_activite_id ON segments_efforts(activite_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_musculation_suivi_athlete_id ON musculation_suivi(athlete_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_musculation_exercices_athlete_id ON musculation_exercices(athlete_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_mobilite_exercices_athlete_id ON mobilite_exercices(athlete_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_sommeil_athlete_id ON sommeil(athlete_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_objectifs_athlete_id ON objectifs(athlete_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_blessures_athlete_id ON blessures(athlete_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_seances_structurees_plan_id ON seances_structurees(plan_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_seances_structurees_athlete_id ON seances_structurees(athlete_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_plans_entrainement_athlete_id ON plans_entrainement(athlete_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_analyses_ia_athlete_id ON analyses_ia(athlete_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_analyses_ia_activite_id ON analyses_ia(activite_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_replanifications_plan_id ON replanifications(plan_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_analyses_course_objectif_id ON analyses_course(objectif_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_replanifications_athlete_id ON replanifications(athlete_id)")

    # Index composites (athlete_id, date) — les écrans de liste filtrent
    # quasi toujours par athlète PUIS trient par date (ORDER BY date
    # DESC) : un index composite sert les deux à la fois, plus efficace
    # qu'un index sur athlete_id seul quand le volume de données grandit.
    cur.execute("CREATE INDEX IF NOT EXISTS idx_activites_athlete_date ON activites(athlete_id, date)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_resultats_courses_athlete_id ON resultats_courses(athlete_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_resultats_courses_athlete_date ON resultats_courses(athlete_id, date)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_seances_structurees_athlete_date ON seances_structurees(athlete_id, date_prevue)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_objectifs_athlete_date ON objectifs(athlete_id, date_cible)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_parcours_gpx_athlete_date ON parcours_gpx(athlete_id, date_ajout)")

    # --------------------------------------------------
    # SIGNAUX DE RÉCUPÉRATION (HRV / stress, importés depuis un .FIT
    # quand la montre les enregistre — donnée journalière, indépendante
    # d'une activité précise, d'où une table à part plutôt que des
    # colonnes sur "activites")
    # --------------------------------------------------

    cur.execute("""
        CREATE TABLE IF NOT EXISTS signaux_recuperation (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            athlete_id INTEGER,
            date TEXT NOT NULL,
            hrv_ms REAL,
            stress_moyen INTEGER,
            source_fichier TEXT,
            date_import TEXT DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY (athlete_id) REFERENCES athletes(id)
        )
    """)
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_signaux_recuperation_athlete_id "
        "ON signaux_recuperation(athlete_id)"
    )

    # --------------------------------------------------
    # RÉCUPÉRATION QUOTIDIENNE (v91) — une ligne par jour avec les mesures
    # de santé de la montre (FC de repos, HRV de nuit, sommeil détaillé,
    # Body Battery, stress). Alimentée par l'import « santé Garmin » ;
    # jours sans port de la montre = pas de ligne (trous normaux).
    # --------------------------------------------------

    cur.execute("""
        CREATE TABLE IF NOT EXISTS recuperation_quotidienne (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            athlete_id INTEGER NOT NULL,
            date TEXT NOT NULL,
            fc_repos INTEGER,
            fc_min INTEGER,
            hrv_nuit_ms REAL,
            hrv_statut TEXT,
            sommeil_score INTEGER,
            sommeil_duree_h REAL,
            sommeil_profond_min INTEGER,
            sommeil_leger_min INTEGER,
            sommeil_paradoxal_min INTEGER,
            sommeil_eveil_min INTEGER,
            body_battery_max INTEGER,
            body_battery_min INTEGER,
            stress_moyen INTEGER,
            spo2_moyenne REAL,
            source TEXT DEFAULT 'Garmin',
            date_import TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (athlete_id, date),
            FOREIGN KEY (athlete_id) REFERENCES athletes(id)
        )
    """)

    # Données quotidiennes en plus venues de Garmin Connect (synchro auto) :
    # activité du jour, disponibilité d'entraînement de la montre, etc.
    cur.execute("""
        CREATE TABLE IF NOT EXISTS garmin_quotidien (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            athlete_id INTEGER NOT NULL,
            date TEXT NOT NULL,
            pas INTEGER,
            calories_totales INTEGER,
            minutes_intenses INTEGER,
            respiration_moyenne REAL,
            readiness_score INTEGER,
            readiness_niveau TEXT,
            statut_entrainement TEXT,
            vo2max REAL,
            poids_kg REAL,
            date_import TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (athlete_id, date),
            FOREIGN KEY (athlete_id) REFERENCES athletes(id)
        )
    """)

    # --------------------------------------------------
    # RYTHME DE VIE — PÉRIODES EXCEPTIONNELLES (déplacement pro,
    # astreinte...) déclarables ponctuellement sans reconfigurer tout
    # le profil hebdomadaire habituel (interface/rythme_vie.py)
    # --------------------------------------------------

    cur.execute("""
        CREATE TABLE IF NOT EXISTS rythme_vie_exceptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date_debut TEXT NOT NULL,
            date_fin TEXT NOT NULL,
            motif TEXT,
            niveau TEXT DEFAULT 'Journée longue'
        )
    """)

    # --------------------------------------------------
    # COMPARAISON COURSES DE RÉPÈRE — écart cible/réalisé conservé pour
    # ajuster les prédictions Riegel au fil du temps (interface/
    # comparaison_courses.py)
    # --------------------------------------------------

    cur.execute("""
        CREATE TABLE IF NOT EXISTS comparaisons_courses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            athlete_id INTEGER,
            seance_id INTEGER,
            activite_id INTEGER,
            date_generation TEXT DEFAULT CURRENT_TIMESTAMP,
            allure_cible REAL,
            allure_reelle REAL,
            ecart_allure_pct REAL,
            fc_cible INTEGER,
            fc_reelle INTEGER,

            FOREIGN KEY (athlete_id) REFERENCES athletes(id),
            FOREIGN KEY (seance_id) REFERENCES seances_structurees(id),
            FOREIGN KEY (activite_id) REFERENCES activites(id)
        )
    """)

    # --------------------------------------------------
    # RAPPORTS DE FIN DE BLOC (programme Ultra)
    # --------------------------------------------------

    cur.execute("""
        CREATE TABLE IF NOT EXISTS rapports_bloc (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            plan_id INTEGER,
            athlete_id INTEGER,
            nom_bloc TEXT,
            date_generation TEXT DEFAULT CURRENT_TIMESTAMP,
            contenu TEXT,

            FOREIGN KEY (plan_id) REFERENCES plans_entrainement(id),
            FOREIGN KEY (athlete_id) REFERENCES athletes(id)
        )
    """)

    conn.commit()
    conn.close()

def ajouter_athlete(
        nom,
        prenom,
        age,
        sexe,
        taille,
        poids,
        fc_repos,
        fc_max,
        fc_seuil,
        vma,
        vo2max,
        niveau):

    conn = connexion()
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO athletes(
            nom,
            prenom,
            age,
            sexe,
            taille,
            poids,
            fc_repos,
            fc_max,
            fc_seuil,
            vma,
            vo2max,
            niveau
        )
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
    """, (
        nom,
        prenom,
        age,
        sexe,
        taille,
        poids,
        fc_repos,
        fc_max,
        fc_seuil,
        vma,
        vo2max,
        niveau
    ))

    nouvel_id = cur.lastrowid

    conn.commit()
    conn.close()

    return nouvel_id


def definir_photo_athlete(athlete_id, chemin_photo):
    conn = connexion()
    cur = conn.cursor()
    cur.execute("UPDATE athletes SET photo_path=? WHERE id=?", (chemin_photo, athlete_id))
    conn.commit()
    conn.close()


def supprimer_activite(activite_id):
    """Supprime définitivement une activité (sortie) ainsi que tout ce
    qui lui est directement rattaché : trace GPS, efforts sur segments,
    comptes rendus IA. Les enregistrements qui existent indépendamment
    de la sortie (une séance planifiée, un résultat de course, une
    fiche blessure) ne sont eux jamais supprimés — seul le lien vers
    l'activité effacée est retiré, pour ne pas perdre ces données."""

    conn = connexion()
    cur = conn.cursor()

    cur.execute("DELETE FROM parcours_gpx WHERE activite_id=?", (activite_id,))
    cur.execute("DELETE FROM segments_efforts WHERE activite_id=?", (activite_id,))
    cur.execute("DELETE FROM analyses_ia WHERE activite_id=?", (activite_id,))

    cur.execute(
        "UPDATE seances_structurees "
        "SET statut='Prévue', activite_id=NULL, score_conformite=NULL "
        "WHERE activite_id=?",
        (activite_id,),
    )
    cur.execute(
        "UPDATE resultats_courses SET activite_id=NULL WHERE activite_id=?",
        (activite_id,),
    )
    cur.execute(
        "UPDATE blessures SET activite_id=NULL WHERE activite_id=?",
        (activite_id,),
    )

    # Les photos restent dans la galerie, simplement sans sortie rattachée
    cur.execute(
        "UPDATE photos_sorties SET activite_id=NULL WHERE activite_id=?",
        (activite_id,),
    )
    cur.execute("DELETE FROM ressentis_sorties WHERE activite_id=?", (activite_id,))
    cur.execute("DELETE FROM meteo_sorties WHERE activite_id=?", (activite_id,))

    cur.execute("DELETE FROM activites WHERE id=?", (activite_id,))

    conn.commit()
    conn.close()

    # Import différé (jamais au niveau module) pour éviter un import
    # circulaire : interface/coach.py importe déjà data.database.
    try:
        from interface.coach import invalider_cache_coach
        invalider_cache_coach()
    except ImportError:
        pass


def creer_activite_manuelle(athlete_id, date_iso, nom, type_, distance_km=None,
                             denivele_m=None, duree_min=None, notes=None):
    """Ajoute une sortie saisie à la main (ex. pour transformer un jour de
    repos en sortie quand on a oublié de l'enregistrer autrement) — même
    table que les sorties importées, avec source='Manuel' pour les
    distinguer dans l'historique."""

    conn = connexion()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO activites (athlete_id, date, nom, type, distance, denivele, duree, source, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?, 'Manuel', ?)
        """,
        (
            athlete_id, date_iso, nom or type_, type_,
            distance_km or 0, denivele_m or 0,
            int((duree_min or 0) * 60), notes,
        ),
    )
    conn.commit()
    nouvel_id = cur.lastrowid
    conn.close()

    try:
        from interface.coach import invalider_cache_coach
        invalider_cache_coach()
    except ImportError:
        pass

    return nouvel_id


def obtenir_activites_par_jour(athlete_id, date_debut_iso, date_fin_iso):
    """Renvoie {jour_iso: [ (id, nom, type, distance, denivele, duree), ... ]}
    pour toutes les sorties de l'athlète entre les deux dates (incluses) —
    base commune pour les vues « sorties + jours de repos » (historique et
    calendrier)."""

    conn = connexion()
    cur = conn.cursor()
    cur.execute(
        "SELECT id, date, nom, type, distance, denivele, duree FROM activites "
        "WHERE athlete_id=? AND date >= ? AND date <= ? ORDER BY date",
        (athlete_id, date_debut_iso, f"{date_fin_iso}T23:59:59"),
    )
    lignes = cur.fetchall()
    conn.close()

    resultat = {}
    for id_, date_, nom, type_, distance, denivele, duree in lignes:
        jour = str(date_)[:10]
        resultat.setdefault(jour, []).append((id_, nom, type_, distance, denivele, duree))
    return resultat


def fusionner_activites(id_survivant, id_a_fusionner):
    """Fusionne deux activités détectées comme doublons (voir
    interface/doublons.py) : `id_a_fusionner` disparaît, et tout ce qui
    pointait vers elle est reporté sur `id_survivant` plutôt que perdu
    — utilisé typiquement quand une sortie suivie en direct depuis le
    téléphone (GPS moins précis) est ensuite resynchronisée depuis une
    montre Garmin ou Strava (GPS plus précis) : `id_survivant` doit
    alors être la version la plus fiable des deux.

    - la trace GPS du survivant est gardée telle quelle ; celle de
      l'activité fusionnée n'est reprise que si le survivant n'en a
      aucune (mieux vaut une trace téléphone qu'aucune trace) ;
    - une séance planifiée, un résultat de course ou une fiche
      blessure liés à l'activité fusionnée sont rattachés au survivant
      (seulement s'il n'a pas déjà son propre lien, pour ne rien
      écraser) ;
    - les efforts sur segments et l'analyse IA de l'activité fusionnée,
      propres à cet enregistrement précis, sont supprimés plutôt que
      dupliqués."""

    if id_survivant == id_a_fusionner:
        return

    conn = connexion()
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) FROM parcours_gpx WHERE activite_id=?", (id_survivant,))
    survivant_a_une_trace = cur.fetchone()[0] > 0
    if survivant_a_une_trace:
        cur.execute("DELETE FROM parcours_gpx WHERE activite_id=?", (id_a_fusionner,))
    else:
        cur.execute(
            "UPDATE parcours_gpx SET activite_id=? WHERE activite_id=?",
            (id_survivant, id_a_fusionner),
        )

    cur.execute("DELETE FROM segments_efforts WHERE activite_id=?", (id_a_fusionner,))
    cur.execute("DELETE FROM analyses_ia WHERE activite_id=?", (id_a_fusionner,))
    # Les photos suivent la sortie conservée
    cur.execute(
        "UPDATE photos_sorties SET activite_id=? WHERE activite_id=?",
        (id_survivant, id_a_fusionner),
    )

    for table in ("seances_structurees", "resultats_courses", "blessures"):
        cur.execute(f"SELECT COUNT(*) FROM {table} WHERE activite_id=?", (id_survivant,))
        deja_lie = cur.fetchone()[0] > 0
        if not deja_lie:
            cur.execute(
                f"UPDATE {table} SET activite_id=? WHERE activite_id=?",
                (id_survivant, id_a_fusionner),
            )
        else:
            cur.execute(
                f"UPDATE {table} SET activite_id=NULL WHERE activite_id=?",
                (id_a_fusionner,),
            )

    cur.execute("DELETE FROM activites WHERE id=?", (id_a_fusionner,))

    conn.commit()
    conn.close()

    try:
        from interface.coach import invalider_cache_coach
        invalider_cache_coach()
    except ImportError:
        pass


# --------------------------------------------------
# LECTURE
# --------------------------------------------------

def obtenir_athlete_par_id(athlete_id):
    conn = connexion()
    cur = conn.cursor()
    cur.execute("SELECT * FROM athletes WHERE id=?", (athlete_id,))
    ligne = cur.fetchone()
    conn.close()
    return ligne


def obtenir_athletes():

    conn = connexion()
    cur = conn.cursor()

    cur.execute("""
        SELECT *
        FROM athletes
        ORDER BY nom, prenom
    """)

    athletes = cur.fetchall()

    conn.close()

    return athletes


# --------------------------------------------------
# SUPPRESSION
# --------------------------------------------------

def supprimer_athlete(id_athlete):

    conn = connexion()
    cur = conn.cursor()

    cur.execute(
        "DELETE FROM athletes WHERE id=?",
        (id_athlete,)
    )
   
    
    conn.commit()
    conn.close()


# --------------------------------------------------
# PARAMÈTRES GÉNÉRAUX (clé/valeur)
# --------------------------------------------------

def obtenir_parametre(cle, defaut=None):
    conn = connexion()
    cur = conn.cursor()
    cur.execute("SELECT valeur FROM parametres_app WHERE cle=?", (cle,))
    ligne = cur.fetchone()
    conn.close()
    return ligne[0] if ligne else defaut


def definir_parametre(cle, valeur):
    conn = connexion()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO parametres_app (cle, valeur) VALUES (?, ?) "
        "ON CONFLICT(cle) DO UPDATE SET valeur=excluded.valeur",
        (cle, str(valeur)),
    )
    conn.commit()
    conn.close()


def affichage_simplifie_actif():
    """Renvoie True si le mode « Affichage simplifié » est activé dans les
    réglages (masque les fonctions avancées peu utilisées : Programme Ultra,
    Replanification automatique, Tactique de course, Serveur local,
    Découplage cardiaque — sans jamais rien supprimer, juste les cacher)."""
    return obtenir_parametre("affichage_simplifie", "0") == "1"


# --------------------------------------------------
# SIGNAUX DE RÉCUPÉRATION (HRV / stress importés depuis un .FIT)
# --------------------------------------------------

def enregistrer_signal_recuperation(athlete_id, date_texte, hrv_ms, stress_moyen, source_fichier):
    conn = connexion()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO signaux_recuperation (athlete_id, date, hrv_ms, stress_moyen, source_fichier) "
        "VALUES (?, ?, ?, ?, ?)",
        (athlete_id, date_texte, hrv_ms, stress_moyen, source_fichier),
    )
    conn.commit()
    conn.close()


def obtenir_signaux_recuperation_recents(athlete_id, nb_entrees=10):
    conn = connexion()
    cur = conn.cursor()
    cur.execute(
        "SELECT date, hrv_ms, stress_moyen, source_fichier FROM signaux_recuperation "
        "WHERE athlete_id=? ORDER BY date DESC LIMIT ?",
        (athlete_id, nb_entrees),
    )
    lignes = cur.fetchall()
    conn.close()
    return lignes


# --------------------------------------------------
# INITIALISATION
# --------------------------------------------------

def completer_vitesses_calculables():
    """Vitesse et allure moyennes = distance / durée : quand elles sont
    vides (import Strava d'avant la v90, par exemple) mais que distance
    et durée sont connues, on les calcule. Ne touche jamais une valeur
    déjà présente ; sans effet une fois tout rempli."""
    try:
        conn = connexion()
        cur = conn.cursor()
        cur.execute(
            "UPDATE activites SET "
            "vitesse_moyenne = ROUND(distance / (duree / 3600.0), 2), "
            "allure_moyenne = ROUND((duree / 60.0) / distance, 2) "
            "WHERE vitesse_moyenne IS NULL AND allure_moyenne IS NULL "
            "AND distance > 0 AND duree > 0"
        )
        conn.commit()
        conn.close()
    except Exception:
        pass  # amélioration facultative : ne jamais empêcher le démarrage


creer_base_de_donnees()
completer_vitesses_calculables()


if __name__ == "__main__":

    print("Base :", CHEMIN_BDD)

    athletes = obtenir_athletes()

    print(f"{len(athletes)} athlète(s) enregistré(s)")