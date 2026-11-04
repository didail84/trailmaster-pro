"""Étape 2.1 — migrations numérotées et identifiants universels.

Une base « v108 » (schéma de départ, sans table de version) est
fabriquée telle que la v108 la créait, puis convertie : rien ne doit
être perdu, une copie de sécurité doit exister, et une erreur ne doit
jamais laisser une base à moitié convertie."""
import re
import sqlite3

import pytest

import data.database as db
from data import migrations as mig

FORMAT_UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")


@pytest.fixture
def base_v108(tmp_path, monkeypatch):
    """Base au schéma v108 avec des données, AVANT toute migration."""
    chemin = tmp_path / "trailmaster.db"
    monkeypatch.setattr(db, "CHEMIN_BDD", chemin)
    monkeypatch.setattr(mig, "appliquer_migrations", lambda *a, **k: None)  # création seule, comme la v108
    db.creer_base_de_donnees()
    monkeypatch.undo()
    monkeypatch.setattr(db, "CHEMIN_BDD", chemin)
    c = sqlite3.connect(chemin)
    c.execute("INSERT INTO athletes (id, nom, prenom, vma) VALUES (1, 'Beltran', 'Didier', 12.5)")
    for i in range(300):
        cur = c.execute("INSERT INTO activites (athlete_id, date, nom, type, distance, duree) VALUES (1,?,?,?,?,?)",
                        (f"2026-0{1 + i % 9}-{1 + i % 28:02d} 07:00:00", f"Sortie {i}", "Trail", 5 + i % 20, 1800 + i))
        if i % 10 == 0:
            c.execute("INSERT INTO parcours_gpx (athlete_id, nom, trace_json, activite_id) VALUES (1, ?, '[]', ?)",
                      (f"Trace {i}", cur.lastrowid))
    c.execute("INSERT INTO suivi_corporel (athlete_id, date, poids_kg) VALUES (1, '2026-10-01', 88)")
    c.commit()
    c.close()
    return chemin


def contenu(chemin, table, sans=("uuid", "personne_id")):
    c = sqlite3.connect(chemin)
    try:
        cols = [r[1] for r in c.execute(f"PRAGMA table_info({table})") if r[1] not in sans]
        return cols, c.execute(f"SELECT {', '.join(cols)} FROM {table} ORDER BY id").fetchall()
    finally:
        c.close()


def test_la_base_v108_est_en_version_0(base_v108):
    c = sqlite3.connect(base_v108)
    assert mig.version_de_la_base(c) == 0
    assert "uuid" not in [r[1] for r in c.execute("PRAGMA table_info(activites)")]
    c.close()


def test_conversion_sans_perte(base_v108):
    avant = {t: contenu(base_v108, t) for t in ("athletes", "activites", "parcours_gpx", "suivi_corporel")}
    bilan = mig.appliquer_migrations(base_v108)
    assert bilan["avant"] == 0 and bilan["apres"] == mig.VERSION_LOGICIEL and bilan["appliquees"] == [1, 2]
    for table, (cols, lignes) in avant.items():
        assert contenu(base_v108, table) == (cols, lignes), table  # toutes les valeurs sont intactes
    c = sqlite3.connect(base_v108)
    uuids = [r[0] for r in c.execute("SELECT uuid FROM activites")]
    assert len(uuids) == 300 and len(set(uuids)) == 300
    assert all(FORMAT_UUID.match(u) for u in uuids)
    assert c.execute("SELECT version, description FROM schema_version").fetchall() == [
        (1, "Identifiant universel (UUID) pour chaque donnée"), (2, "Fiche Personne unique et rôles")]
    c.close()


def test_copie_de_securite_identique_a_la_base_d_origine(base_v108):
    avant = contenu(base_v108, "activites")
    bilan = mig.appliquer_migrations(base_v108)
    copie = bilan["sauvegarde"]
    assert copie and "sauvegardes" in copie and "avant_migration_v0" in copie
    assert contenu(copie, "activites") == avant
    c = sqlite3.connect(copie)
    assert "uuid" not in [r[1] for r in c.execute("PRAGMA table_info(activites)")]  # vraiment l'état d'avant
    c.close()


def test_deuxieme_passage_sans_effet(base_v108):
    mig.appliquer_migrations(base_v108)
    c = sqlite3.connect(base_v108)
    avant = c.execute("SELECT id, uuid FROM activites ORDER BY id").fetchall()
    c.close()
    bilan = mig.appliquer_migrations(base_v108)
    assert bilan["appliquees"] == [] and bilan["sauvegarde"] is None
    c = sqlite3.connect(base_v108)
    assert c.execute("SELECT id, uuid FROM activites ORDER BY id").fetchall() == avant  # les UUID ne changent jamais
    c.close()


def test_les_nouvelles_lignes_recoivent_un_uuid(base_v108):
    mig.appliquer_migrations(base_v108)
    from noyau.donnees import activites as dact, athletes as dath  # noqa: F401
    nouvel = dact.inserer({"athlete_id": 1, "date": "2026-11-04 08:00:00", "nom": "Après migration"})
    c = sqlite3.connect(base_v108)
    nom, u = c.execute("SELECT nom, uuid FROM activites WHERE id=?", (nouvel,)).fetchone()
    assert nom == "Après migration" and FORMAT_UUID.match(u)  # l'id renvoyé reste le bon
    # un uuid fourni (passeport, autre ordinateur) est conservé tel quel
    c.execute("INSERT INTO athletes (nom, prenom, uuid) VALUES ('A', 'B', '11111111-2222-4333-8444-555555555555')")
    assert c.execute("SELECT uuid FROM athletes WHERE nom='A'").fetchone()[0] == "11111111-2222-4333-8444-555555555555"
    with pytest.raises(sqlite3.IntegrityError):  # deux lignes ne peuvent pas partager un uuid
        c.execute("INSERT INTO athletes (nom, prenom, uuid) VALUES ('C', 'D', '11111111-2222-4333-8444-555555555555')")
    c.close()


def test_une_erreur_ne_laisse_rien_a_moitie(base_v108, monkeypatch):
    def migration_cassee(cur):
        cur.execute("ALTER TABLE activites ADD COLUMN uuid TEXT")
        cur.execute("UPDATE activites SET uuid = 'x'")
        raise RuntimeError("coupure de courant simulée")

    monkeypatch.setattr(mig, "MIGRATIONS", [(1, "Essai", migration_cassee)])
    monkeypatch.setattr(mig, "VERSION_LOGICIEL", 1)
    avant = contenu(base_v108, "activites")
    with pytest.raises(mig.ErreurMigration) as erreur:
        mig.appliquer_migrations(base_v108)
    assert "n'a pas été modifiée" in str(erreur.value) and "copie de sécurité" in str(erreur.value)
    c = sqlite3.connect(base_v108)
    assert "uuid" not in [r[1] for r in c.execute("PRAGMA table_info(activites)")]  # ALTER annulé
    assert mig.version_de_la_base(c) == 0
    c.close()
    assert contenu(base_v108, "activites") == avant


def test_une_base_plus_recente_n_est_pas_touchee(base_v108):
    c = sqlite3.connect(base_v108)
    mig._preparer_table_version(c)
    c.execute("INSERT INTO schema_version VALUES (99, 'future', '2030-01-01')")
    c.commit()
    c.close()
    bilan = mig.appliquer_migrations(base_v108)
    assert bilan["appliquees"] == [] and bilan["apres"] == 99
    c = sqlite3.connect(base_v108)
    assert "uuid" not in [r[1] for r in c.execute("PRAGMA table_info(activites)")]
    c.close()


def test_base_neuve_sans_copie_inutile(tmp_path, monkeypatch):
    chemin = tmp_path / "neuve.db"
    monkeypatch.setattr(db, "CHEMIN_BDD", chemin)
    db.creer_base_de_donnees()  # création + migrations
    c = sqlite3.connect(chemin)
    assert mig.version_de_la_base(c) == mig.VERSION_LOGICIEL
    assert "uuid" in [r[1] for r in c.execute("PRAGMA table_info(athletes)")]
    c.close()
    assert not (tmp_path / "sauvegardes").exists()  # base vide : rien à sauvegarder


def test_toutes_les_tables_prevues_ont_un_uuid(tmp_path, monkeypatch):
    chemin = tmp_path / "neuve.db"
    monkeypatch.setattr(db, "CHEMIN_BDD", chemin)
    db.creer_base_de_donnees()
    c = sqlite3.connect(chemin)
    tables = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    for table in mig.TABLES_AVEC_UUID:
        assert table in tables, f"table {table} absente du schéma"
        assert "uuid" in [r[1] for r in c.execute(f"PRAGMA table_info({table})")], table
        assert c.execute("SELECT 1 FROM sqlite_master WHERE type='trigger' AND name=?", (f"uuid_{table}",)).fetchone()
    c.close()


def test_import_des_migrations_en_premier():
    """Importer data.migrations avant data.database ne doit pas créer de boucle."""
    import subprocess
    import sys
    from pathlib import Path
    r = subprocess.run([sys.executable, "-c", "import data.migrations, data.database; print('ok')"],
                       cwd=Path(__file__).resolve().parent.parent, capture_output=True, text=True, timeout=60)
    assert r.stdout.strip() == "ok", r.stderr[-1500:]


def test_migrations_numerotees_sans_trou():
    numeros = [n for n, _, _ in mig.MIGRATIONS]
    assert numeros == list(range(1, len(numeros) + 1))
    assert mig.VERSION_LOGICIEL == numeros[-1]
