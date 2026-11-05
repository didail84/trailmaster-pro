"""
Migrations numérotées de la base de Trail Hub Center (étape 2.1).

Jusqu'à la v108, la base évoluait par petits ajouts de colonnes au cas
par cas dans creer_base_de_donnees(). Ce schéma de départ reste la
« version 0 ». Chaque évolution suivante est une migration numérotée,
appliquée une seule fois, dans l'ordre, et notée dans la table
`schema_version`. Une base de club, une base de coureur ou une
sauvegarde ancienne savent ainsi toujours où elles en sont.

Sécurité :
  - une copie complète de la base est faite dans le dossier
    « sauvegardes » à côté d'elle, AVANT toute migration d'une base qui
    contient déjà des données ;
  - chaque migration se fait en une seule transaction : en cas d'erreur
    rien n'est modifié, la base reste dans sa version précédente ;
  - une base plus récente que le logiciel (ouverte avec une ancienne
    version) n'est jamais touchée.

Pour ajouter une migration : écrire une fonction _mNNN_nom(cur) et
l'ajouter à la fin de MIGRATIONS, avec le numéro suivant. Ne jamais
modifier ni renuméroter une migration déjà publiée.
"""

import sqlite3
from datetime import datetime
from pathlib import Path

# data.database n'est PAS importé ici : il appelle lui-même ce module à la
# fin de creer_base_de_donnees() ; l'importer en tête créerait une boucle.


class ErreurMigration(Exception):
    """Message lisible par l'utilisateur ; la base est restée intacte."""


# ------------------------------------------------------------------
# Migration 1 — identifiant universel (UUID) de chaque donnée
# ------------------------------------------------------------------

# Tables dont les lignes pourront circuler entre ordinateurs, club,
# serveur et passeport coureur : chacune reçoit une colonne `uuid`.
TABLES_AVEC_UUID = (
    "athletes", "activites", "parcours_gpx", "photos_sorties",
    "seances_structurees", "plans_entrainement", "roadbooks",
    "courses_calendrier", "resultats_courses", "objectifs",
    "blessures", "soins", "materiel", "segments", "segments_efforts",
    "suivi_corporel", "sommeil", "nutrition", "musculation_suivi", "zones_entrainement",
)

# UUID version 4 (format 8-4-4-4-12, ex. 3f2a9c1e-5b7d-4e8a-9c21-7d4e5f6a8b90)
# calculé par SQLite lui-même : les déclencheurs le donnent à toute ligne
# créée, quel que soit l'écran ou l'import qui la crée.
EXPRESSION_UUID = (
    "lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || "
    "substr(lower(hex(randomblob(2))), 2) || '-' || "
    "substr('89ab', 1 + (abs(random()) % 4), 1) || substr(lower(hex(randomblob(2))), 2) || '-' || "
    "lower(hex(randomblob(6)))"
)


def _colonnes(cur, table):
    return [r[1] for r in cur.execute(f"PRAGMA table_info({table})")]


def _tables(cur):
    return {r[0] for r in cur.execute("SELECT name FROM sqlite_master WHERE type='table'")}


def _m001_identifiants_universels(cur):
    existantes = _tables(cur)
    for table in TABLES_AVEC_UUID:
        if table not in existantes:
            continue
        if "uuid" not in _colonnes(cur, table):
            cur.execute(f"ALTER TABLE {table} ADD COLUMN uuid TEXT")
        cur.execute(f"UPDATE {table} SET uuid = {EXPRESSION_UUID} WHERE uuid IS NULL")
        cur.execute(f"CREATE UNIQUE INDEX IF NOT EXISTS idx_{table}_uuid ON {table}(uuid)")
        cur.execute(
            f"CREATE TRIGGER IF NOT EXISTS uuid_{table} AFTER INSERT ON {table} "
            f"FOR EACH ROW WHEN NEW.uuid IS NULL BEGIN "
            f"UPDATE {table} SET uuid = {EXPRESSION_UUID} WHERE rowid = NEW.rowid; END"
        )


def _ajouter_uuid(cur, table):
    """Même traitement que la migration 1, pour une table créée plus tard."""
    if "uuid" not in _colonnes(cur, table):
        cur.execute(f"ALTER TABLE {table} ADD COLUMN uuid TEXT")
    cur.execute(f"UPDATE {table} SET uuid = {EXPRESSION_UUID} WHERE uuid IS NULL")
    cur.execute(f"CREATE UNIQUE INDEX IF NOT EXISTS idx_{table}_uuid ON {table}(uuid)")
    cur.execute(
        f"CREATE TRIGGER IF NOT EXISTS uuid_{table} AFTER INSERT ON {table} "
        f"FOR EACH ROW WHEN NEW.uuid IS NULL BEGIN "
        f"UPDATE {table} SET uuid = {EXPRESSION_UUID} WHERE rowid = NEW.rowid; END"
    )


# ------------------------------------------------------------------
# Migration 2 — fiche Personne unique et rôles (étape 2.2)
# ------------------------------------------------------------------

# Rôles possibles d'une personne (bloc 1 du Master Plan) : (code, libellé)
ROLES = (
    ("coureur", "Coureur"),
    ("licencie", "Licencié"),
    ("enfant", "Enfant"),
    ("parent", "Parent"),
    ("entraineur", "Entraîneur"),
    ("benevole", "Bénévole"),
    ("organisateur", "Organisateur"),
)


def _m002_personnes_et_roles(cur):
    """Une fiche par personne (identité), lue par tous les modules ;
    le profil sportif de la table `athletes` devient le rôle « coureur »
    de cette personne. Chaque athlète existant reçoit sa fiche."""
    cur.execute("""
        CREATE TABLE IF NOT EXISTS personnes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nom TEXT NOT NULL,
            prenom TEXT NOT NULL DEFAULT '',
            date_naissance TEXT,
            sexe TEXT,
            email TEXT,
            telephone TEXT,
            adresse TEXT,
            code_postal TEXT,
            ville TEXT,
            photo_path TEXT,
            notes TEXT,
            date_creation TEXT DEFAULT CURRENT_TIMESTAMP
        )""")
    _ajouter_uuid(cur, "personnes")
    codes = ", ".join(f"'{c}'" for c, _ in ROLES)
    cur.execute(f"""
        CREATE TABLE IF NOT EXISTS personnes_roles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            personne_id INTEGER NOT NULL REFERENCES personnes(id) ON DELETE CASCADE,
            role TEXT NOT NULL CHECK (role IN ({codes})),
            depuis TEXT,
            notes TEXT,
            UNIQUE (personne_id, role)
        )""")
    cur.execute("""
        CREATE TABLE IF NOT EXISTS personnes_liens (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            parent_id INTEGER NOT NULL REFERENCES personnes(id) ON DELETE CASCADE,
            enfant_id INTEGER NOT NULL REFERENCES personnes(id) ON DELETE CASCADE,
            lien TEXT NOT NULL DEFAULT 'parent',
            UNIQUE (parent_id, enfant_id),
            CHECK (parent_id <> enfant_id)
        )""")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_personnes_roles_role ON personnes_roles(role)")

    cols = _colonnes(cur, "athletes")
    if "personne_id" not in cols:
        cur.execute("ALTER TABLE athletes ADD COLUMN personne_id INTEGER REFERENCES personnes(id)")
    cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_athletes_personne ON athletes(personne_id)")
    photo = "NEW.photo_path" if "photo_path" in cols else "NULL"

    # Les athlètes déjà présents reçoivent chacun leur fiche et le rôle coureur
    for (athlete_id,) in cur.execute("SELECT id FROM athletes WHERE personne_id IS NULL ORDER BY id").fetchall():
        cur.execute(
            "INSERT INTO personnes (nom, prenom, sexe, photo_path, date_creation) "
            f"SELECT nom, COALESCE(prenom, ''), sexe, {'photo_path' if 'photo_path' in cols else 'NULL'}, "
            "COALESCE(date_creation, CURRENT_TIMESTAMP) FROM athletes WHERE id=?", (athlete_id,))
        personne_id = cur.lastrowid
        cur.execute("UPDATE athletes SET personne_id=? WHERE id=?", (personne_id, athlete_id))
        cur.execute("INSERT OR IGNORE INTO personnes_roles (personne_id, role, depuis) "
                    "SELECT ?, 'coureur', substr(COALESCE(date_creation, CURRENT_TIMESTAMP), 1, 10) FROM athletes WHERE id=?",
                    (personne_id, athlete_id))

    # Tout athlète créé ensuite (écran Athlètes, import, restauration…)
    # reçoit automatiquement sa fiche, sans changer le code qui le crée.
    cur.execute(f"""
        CREATE TRIGGER IF NOT EXISTS personne_nouvel_athlete AFTER INSERT ON athletes
        FOR EACH ROW WHEN NEW.personne_id IS NULL BEGIN
            INSERT INTO personnes (nom, prenom, sexe, photo_path)
                VALUES (NEW.nom, COALESCE(NEW.prenom, ''), NEW.sexe, {photo});
            UPDATE athletes SET personne_id = last_insert_rowid() WHERE rowid = NEW.rowid;
            INSERT OR IGNORE INTO personnes_roles (personne_id, role, depuis)
                SELECT personne_id, 'coureur', date('now') FROM athletes WHERE rowid = NEW.rowid;
        END""")
    cur.execute("""
        CREATE TRIGGER IF NOT EXISTS personne_athlete_lie AFTER INSERT ON athletes
        FOR EACH ROW WHEN NEW.personne_id IS NOT NULL BEGIN
            INSERT OR IGNORE INTO personnes_roles (personne_id, role, depuis)
                VALUES (NEW.personne_id, 'coureur', date('now'));
        END""")
    # Le nom, le sexe et la photo modifiés dans l'écran Athlètes suivent sur la fiche
    suivies = "nom, prenom, sexe" + (", photo_path" if "photo_path" in cols else "")
    maj_photo = ", photo_path = NEW.photo_path" if "photo_path" in cols else ""
    cur.execute(f"""
        CREATE TRIGGER IF NOT EXISTS personne_suit_athlete AFTER UPDATE OF {suivies} ON athletes
        FOR EACH ROW WHEN NEW.personne_id IS NOT NULL BEGIN
            UPDATE personnes SET nom = NEW.nom, prenom = COALESCE(NEW.prenom, ''), sexe = NEW.sexe{maj_photo}
            WHERE id = NEW.personne_id;
        END""")
    # Un athlète supprimé perd son rôle coureur ; une fiche sans plus aucun
    # rôle ni lien est supprimée aussi (aucune fiche orpheline).
    cur.execute("""
        CREATE TRIGGER IF NOT EXISTS personne_athlete_supprime AFTER DELETE ON athletes
        FOR EACH ROW WHEN OLD.personne_id IS NOT NULL BEGIN
            DELETE FROM personnes_roles WHERE personne_id = OLD.personne_id AND role = 'coureur';
            DELETE FROM personnes WHERE id = OLD.personne_id
                AND NOT EXISTS (SELECT 1 FROM personnes_roles WHERE personne_id = OLD.personne_id)
                AND NOT EXISTS (SELECT 1 FROM personnes_liens WHERE parent_id = OLD.personne_id OR enfant_id = OLD.personne_id);
        END""")


# ------------------------------------------------------------------
# Migration 3 — index de performance (étape 2.4, passeport coureur)
# ------------------------------------------------------------------

def _m003_index_performance(cur):
    """Index ITRA, UTMB, Betrail… d'une personne, avec leur date : ils
    voyagent dans le passeport coureur et seront tenus à jour par le Club."""
    cur.execute("""
        CREATE TABLE IF NOT EXISTS index_performance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            personne_id INTEGER NOT NULL REFERENCES personnes(id) ON DELETE CASCADE,
            organisme TEXT NOT NULL,
            categorie TEXT NOT NULL DEFAULT 'Général',
            valeur REAL NOT NULL,
            date_releve TEXT NOT NULL,
            source TEXT,
            UNIQUE (personne_id, organisme, categorie, date_releve)
        )""")
    _ajouter_uuid(cur, "index_performance")


def _m004_nutrition_course(cur):
    """Produits de course (tes gels, barres, boissons, fait maison), essais de
    tolérance et recettes « fait maison » (étape 3.3, bloc 12)."""
    cur.execute("""
        CREATE TABLE IF NOT EXISTS produits_nutrition (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            athlete_id INTEGER NOT NULL REFERENCES athletes(id) ON DELETE CASCADE,
            nom TEXT NOT NULL,
            marque TEXT,
            categorie TEXT NOT NULL DEFAULT 'Autre',
            type_nutriscore TEXT NOT NULL DEFAULT 'aliment',
            portion REAL,
            unite_portion TEXT NOT NULL DEFAULT 'g',
            energie_kcal REAL, glucides_g REAL, sucres_g REAL, fibres_g REAL, proteines_g REAL,
            lipides_g REAL, ags_g REAL, sel_g REAL,
            fruits_legumes_pct REAL DEFAULT 0,
            edulcorants INTEGER DEFAULT 0,
            cafeine_mg REAL DEFAULT 0,
            glucose_fructose TEXT,
            prix_portion REAL,
            code_barre TEXT,
            nutriscore_officiel TEXT,
            source TEXT,
            recette_id INTEGER,
            favori INTEGER DEFAULT 0,
            notes TEXT,
            date_ajout TEXT
        )""")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_produits_nutrition_athlete ON produits_nutrition(athlete_id)")
    cur.execute("""
        CREATE TABLE IF NOT EXISTS tolerances_nutrition (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            athlete_id INTEGER NOT NULL REFERENCES athletes(id) ON DELETE CASCADE,
            produit_id INTEGER NOT NULL REFERENCES produits_nutrition(id) ON DELETE CASCADE,
            date TEXT NOT NULL,
            contexte TEXT NOT NULL DEFAULT 'Entraînement',
            activite_id INTEGER,
            quantite REAL,
            duree_min REAL,
            glucides_g_h REAL,
            temperature_c REAL,
            ressenti TEXT NOT NULL,
            symptomes TEXT,
            notes TEXT
        )""")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_tolerances_produit ON tolerances_nutrition(produit_id)")
    cur.execute("""
        CREATE TABLE IF NOT EXISTS recettes_nutrition (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            athlete_id INTEGER NOT NULL REFERENCES athletes(id) ON DELETE CASCADE,
            nom TEXT NOT NULL,
            categorie TEXT NOT NULL DEFAULT 'Barre',
            nb_portions REAL NOT NULL DEFAULT 1,
            ingredients_json TEXT NOT NULL,
            preparation TEXT,
            conservation TEXT,
            notes TEXT,
            produit_id INTEGER,
            date_modification TEXT
        )""")
    for t in ("produits_nutrition", "tolerances_nutrition", "recettes_nutrition"):
        _ajouter_uuid(cur, t)


# (numéro, description lisible, fonction) — dans l'ordre, sans trou
MIGRATIONS = [
    (1, "Identifiant universel (UUID) pour chaque donnée", _m001_identifiants_universels),
    (2, "Fiche Personne unique et rôles", _m002_personnes_et_roles),
    (3, "Index de performance (ITRA, UTMB, Betrail)", _m003_index_performance),
    (4, "Nutrition de course : produits, tolérances, recettes fait maison", _m004_nutrition_course),
]
VERSION_LOGICIEL = MIGRATIONS[-1][0]


# ------------------------------------------------------------------
# Moteur
# ------------------------------------------------------------------

def _preparer_table_version(conn):
    conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_version ("
        " version INTEGER PRIMARY KEY,"
        " description TEXT,"
        " date_application TEXT)"
    )


def version_de_la_base(conn):
    _preparer_table_version(conn)
    ligne = conn.execute("SELECT MAX(version) FROM schema_version").fetchone()
    return ligne[0] or 0


def _contient_des_donnees(conn):
    for table in ("athletes", "activites"):
        try:
            if conn.execute(f"SELECT 1 FROM {table} LIMIT 1").fetchone():
                return True
        except sqlite3.Error:
            pass
    return False


def sauvegarder_avant_migration(chemin_bdd, version_depart):
    """Copie complète et cohérente de la base (API de sauvegarde SQLite)
    dans <dossier de la base>/sauvegardes ; renvoie le chemin de la copie."""
    chemin_bdd = Path(chemin_bdd)
    dossier = chemin_bdd.parent / "sauvegardes"
    dossier.mkdir(parents=True, exist_ok=True)
    horodatage = datetime.now().strftime("%Y%m%d_%H%M%S")
    copie = dossier / f"{chemin_bdd.stem}_avant_migration_v{version_depart}_{horodatage}.db"
    source = sqlite3.connect(chemin_bdd)
    destination = sqlite3.connect(copie)
    try:
        source.backup(destination)
    finally:
        destination.close()
        source.close()
    return copie


def appliquer_migrations(chemin_bdd=None):
    """Met la base à jour ; renvoie {"avant", "apres", "appliquees",
    "sauvegarde"}. Sans effet (et quasi instantané) si elle l'est déjà."""
    if chemin_bdd is None:
        import data.database as _base
        chemin_bdd = _base.CHEMIN_BDD
    chemin_bdd = Path(chemin_bdd)
    conn = sqlite3.connect(chemin_bdd)
    conn.isolation_level = None  # transactions gérées à la main (BEGIN / COMMIT)
    try:
        avant = version_de_la_base(conn)
        bilan = {"avant": avant, "apres": avant, "appliquees": [], "sauvegarde": None}
        if avant >= VERSION_LOGICIEL:
            return bilan  # à jour, ou plus récente que ce logiciel : on n'y touche pas
        if _contient_des_donnees(conn):
            bilan["sauvegarde"] = str(sauvegarder_avant_migration(chemin_bdd, avant))
        for numero, description, fonction in MIGRATIONS:
            if numero <= avant:
                continue
            cur = conn.cursor()
            try:
                cur.execute("BEGIN")
                fonction(cur)
                cur.execute("INSERT INTO schema_version (version, description, date_application) VALUES (?,?,?)",
                            (numero, description, datetime.now().isoformat(timespec="seconds")))
                cur.execute("COMMIT")
            except Exception as erreur:
                cur.execute("ROLLBACK")
                raise ErreurMigration(
                    f"La mise à jour n° {numero} de la base (« {description} ») a échoué : {erreur}. "
                    f"La base n'a pas été modifiée"
                    + (f" ; une copie de sécurité a été faite : {bilan['sauvegarde']}" if bilan["sauvegarde"] else "")
                    + "."
                ) from erreur
            bilan["appliquees"].append(numero)
            bilan["apres"] = numero
        return bilan
    finally:
        conn.close()
