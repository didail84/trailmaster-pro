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


# (numéro, description lisible, fonction) — dans l'ordre, sans trou
MIGRATIONS = [
    (1, "Identifiant universel (UUID) pour chaque donnée", _m001_identifiants_universels),
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
