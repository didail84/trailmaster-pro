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


def _m005_materiel_obligatoire(cur):
    """Matériel obligatoire d'une course comparé à ton équipement (étape 3.4, bloc 13) :
    caractéristiques de ton matériel et liste du règlement de chaque course."""
    nouvelles = {"equipement": "TEXT", "poids_g": "REAL", "quantite": "INTEGER DEFAULT 1",
                 "caracteristiques": "TEXT", "controle_le": "TEXT"}
    deja = _colonnes(cur, "materiel")
    for col, typ in nouvelles.items():
        if col not in deja:
            cur.execute(f"ALTER TABLE materiel ADD COLUMN {col} {typ}")
    deja = _colonnes(cur, "courses_calendrier")
    for col in ("reglement_verifie_le", "reglement_source"):
        if col not in deja:
            cur.execute(f"ALTER TABLE courses_calendrier ADD COLUMN {col} TEXT")
    cur.execute("""
        CREATE TABLE IF NOT EXISTS materiel_obligatoire (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            athlete_id INTEGER NOT NULL REFERENCES athletes(id) ON DELETE CASCADE,
            course_id INTEGER NOT NULL REFERENCES courses_calendrier(id) ON DELETE CASCADE,
            ordre INTEGER DEFAULT 0,
            libelle TEXT NOT NULL,
            equipement TEXT,
            niveau TEXT NOT NULL DEFAULT 'obligatoire',
            quantite INTEGER DEFAULT 1,
            valeur_min REAL,
            precision TEXT,
            dans_le_sac INTEGER DEFAULT 0
        )""")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_materiel_obligatoire_course ON materiel_obligatoire(course_id)")
    _ajouter_uuid(cur, "materiel_obligatoire")


def _m006_fractionne(cur):
    """Fractionné court ou long, à plat ou en côte (étape 3.5, bloc 14) : tes séances perso et les
    fractionnés faits pendant une sortie, avec le temps de chaque répétition."""
    cur.execute("""
        CREATE TABLE IF NOT EXISTS fractionnes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            athlete_id INTEGER NOT NULL REFERENCES athletes(id) ON DELETE CASCADE,
            nom TEXT NOT NULL,
            format TEXT NOT NULL,
            terrain TEXT NOT NULL,
            structure_json TEXT NOT NULL,
            notes TEXT,
            date_creation TEXT
        )""")
    cur.execute("""
        CREATE TABLE IF NOT EXISTS fractionnes_realises (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            athlete_id INTEGER NOT NULL REFERENCES athletes(id) ON DELETE CASCADE,
            activite_id INTEGER REFERENCES activites(id) ON DELETE SET NULL,
            date TEXT NOT NULL,
            modele TEXT,
            nom TEXT NOT NULL,
            format TEXT NOT NULL,
            terrain TEXT NOT NULL,
            vma_ref REAL,
            structure_json TEXT NOT NULL,
            repetitions_json TEXT NOT NULL,
            rpe INTEGER,
            source TEXT,
            notes TEXT,
            date_saisie TEXT
        )""")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_fractionnes_realises_athlete ON fractionnes_realises(athlete_id, date)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_fractionnes_realises_activite ON fractionnes_realises(activite_id)")
    for t in ("fractionnes", "fractionnes_realises"):
        _ajouter_uuid(cur, t)


def _m007_club(cur):
    """Espace Club (étape 4.1) : le club, ses groupes, les adhésions de chaque saison (licence FFA,
    santé, autorisation parentale, cotisation) et les tarifs. Un adhérent est une fiche Personne
    avec le rôle « licencié » : pas de second fichier de membres."""
    cur.execute("""
        CREATE TABLE IF NOT EXISTS clubs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nom TEXT NOT NULL,
            sigle TEXT,
            numero_ffa TEXT,
            ligue TEXT,
            comite TEXT,
            adresse TEXT,
            code_postal TEXT,
            ville TEXT,
            email TEXT,
            telephone TEXT,
            site TEXT,
            president TEXT,
            logo_path TEXT,
            notes TEXT,
            date_creation TEXT DEFAULT CURRENT_TIMESTAMP
        )""")
    cur.execute("""
        CREATE TABLE IF NOT EXISTS groupes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            club_id INTEGER NOT NULL REFERENCES clubs(id) ON DELETE CASCADE,
            nom TEXT NOT NULL,
            description TEXT,
            couleur TEXT,
            entraineur_id INTEGER REFERENCES personnes(id) ON DELETE SET NULL,
            actif INTEGER DEFAULT 1,
            UNIQUE (club_id, nom)
        )""")
    cur.execute("""
        CREATE TABLE IF NOT EXISTS groupes_membres (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            groupe_id INTEGER NOT NULL REFERENCES groupes(id) ON DELETE CASCADE,
            personne_id INTEGER NOT NULL REFERENCES personnes(id) ON DELETE CASCADE,
            UNIQUE (groupe_id, personne_id)
        )""")
    cur.execute("""
        CREATE TABLE IF NOT EXISTS adhesions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            club_id INTEGER NOT NULL REFERENCES clubs(id) ON DELETE CASCADE,
            personne_id INTEGER NOT NULL REFERENCES personnes(id) ON DELETE CASCADE,
            saison TEXT NOT NULL,
            type_licence TEXT,
            numero_licence TEXT,
            date_licence TEXT,
            statut TEXT NOT NULL DEFAULT 'en_cours',
            sante_type TEXT,
            sante_date TEXT,
            autorisation_parentale INTEGER DEFAULT 0,
            droit_image INTEGER,
            tarif TEXT,
            cotisation REAL,
            montant_paye REAL DEFAULT 0,
            paiement_mode TEXT,
            paiement_date TEXT,
            recu_numero TEXT,
            source TEXT,
            notes TEXT,
            date_creation TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (club_id, personne_id, saison)
        )""")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_adhesions_saison ON adhesions(club_id, saison)")
    cur.execute("""
        CREATE TABLE IF NOT EXISTS tarifs_cotisation (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            club_id INTEGER NOT NULL REFERENCES clubs(id) ON DELETE CASCADE,
            saison TEXT NOT NULL,
            libelle TEXT NOT NULL,
            type_licence TEXT,
            montant REAL NOT NULL,
            UNIQUE (club_id, saison, libelle)
        )""")
    deja = _colonnes(cur, "personnes")
    for col in ("contact_urgence_nom", "contact_urgence_tel"):
        if col not in deja:
            cur.execute(f"ALTER TABLE personnes ADD COLUMN {col} TEXT")
    for t in ("clubs", "groupes", "adhesions", "tarifs_cotisation"):
        _ajouter_uuid(cur, t)


def _m008_agenda_club(cur):
    """Agenda du club et appel des présences (étape 4.2) : séries hebdomadaires (un groupe, un jour,
    un horaire, hors vacances scolaires et jours fériés au choix), séances (issues d'une série ou
    ponctuelles, annulables) et présences de chaque personne à chaque séance."""
    cur.execute("""
        CREATE TABLE IF NOT EXISTS series_club (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            club_id INTEGER NOT NULL REFERENCES clubs(id) ON DELETE CASCADE,
            groupe_id INTEGER REFERENCES groupes(id) ON DELETE CASCADE,
            titre TEXT NOT NULL,
            type TEXT NOT NULL DEFAULT 'entrainement',
            jour_semaine INTEGER NOT NULL,
            heure_debut TEXT,
            heure_fin TEXT,
            lieu TEXT,
            entraineur_id INTEGER REFERENCES personnes(id) ON DELETE SET NULL,
            date_debut TEXT NOT NULL,
            date_fin TEXT NOT NULL,
            sauf_vacances INTEGER DEFAULT 0,
            sauf_feries INTEGER DEFAULT 1,
            notes TEXT
        )""")
    cur.execute("""
        CREATE TABLE IF NOT EXISTS seances_club (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            club_id INTEGER NOT NULL REFERENCES clubs(id) ON DELETE CASCADE,
            serie_id INTEGER REFERENCES series_club(id) ON DELETE SET NULL,
            groupe_id INTEGER REFERENCES groupes(id) ON DELETE SET NULL,
            titre TEXT NOT NULL,
            type TEXT NOT NULL DEFAULT 'entrainement',
            date TEXT NOT NULL,
            heure_debut TEXT,
            heure_fin TEXT,
            lieu TEXT,
            entraineur_id INTEGER REFERENCES personnes(id) ON DELETE SET NULL,
            contenu TEXT,
            annulee INTEGER DEFAULT 0,
            motif_annulation TEXT,
            appel_fait INTEGER DEFAULT 0,
            notes TEXT
        )""")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_seances_club_date ON seances_club(club_id, date)")
    cur.execute("""
        CREATE TABLE IF NOT EXISTS presences_club (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            seance_id INTEGER NOT NULL REFERENCES seances_club(id) ON DELETE CASCADE,
            personne_id INTEGER NOT NULL REFERENCES personnes(id) ON DELETE CASCADE,
            statut TEXT NOT NULL,
            note TEXT,
            UNIQUE (seance_id, personne_id)
        )""")
    if "zone_vacances" not in _colonnes(cur, "clubs"):
        cur.execute("ALTER TABLE clubs ADD COLUMN zone_vacances TEXT DEFAULT 'B'")
    for t in ("series_club", "seances_club", "presences_club"):
        _ajouter_uuid(cur, t)


def _m009_annuaire(cur):
    """Annuaire trail : clubs, écoles et sections trail, organisateurs, magasins et marques. Les fiches de
    référence (livrées avec le logiciel) et les tiennes sont dans la même table ; tes notes, favoris et
    corrections ne sont jamais écrasés par une mise à jour de la référence. Le matériel gagne sa marque et
    son magasin."""
    cur.execute("""
        CREATE TABLE IF NOT EXISTS annuaire (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cle_reference TEXT UNIQUE,
            type TEXT NOT NULL,
            nom TEXT NOT NULL,
            sigle TEXT,
            enseigne TEXT,
            categorie TEXT,
            commune TEXT,
            code_postal TEXT,
            departement TEXT,
            adresse TEXT,
            site TEXT,
            affiliation TEXT,
            pays TEXT,
            categories TEXT,
            groupe TEXT,
            source TEXT,
            notes TEXT,
            mes_notes TEXT,
            favori INTEGER DEFAULT 0,
            masque INTEGER DEFAULT 0,
            modifie INTEGER DEFAULT 0,
            verifie_le TEXT,
            date_creation TEXT DEFAULT CURRENT_TIMESTAMP
        )""")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_annuaire_type ON annuaire(type, departement)")
    deja = _colonnes(cur, "materiel")
    for col in ("marque", "magasin"):
        if col not in deja:
            cur.execute(f"ALTER TABLE materiel ADD COLUMN {col} TEXT")
    _ajouter_uuid(cur, "annuaire")


def _m010_calendrier_organisation(cur):
    """Calendrier des courses (sources .ics, collage, import) et organisation d'un événement (étape 4.4) :
    épreuves, tarifs, inscriptions contrôlées selon la réglementation FFA, dossards."""
    cur.execute("""
        CREATE TABLE IF NOT EXISTS calendrier_sources (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nom TEXT NOT NULL,
            type TEXT NOT NULL,
            url TEXT,
            actif INTEGER DEFAULT 1,
            derniere_maj TEXT,
            nb_courses INTEGER DEFAULT 0,
            erreur TEXT,
            notes TEXT
        )""")
    cur.execute("""
        CREATE TABLE IF NOT EXISTS calendrier_courses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cle TEXT,
            nom TEXT NOT NULL,
            date_debut TEXT NOT NULL,
            date_fin TEXT,
            commune TEXT,
            code_postal TEXT,
            departement TEXT,
            discipline TEXT,
            niveau TEXT,
            organisateur TEXT,
            site TEXT,
            inscription_url TEXT,
            statut TEXT DEFAULT 'prevue',
            source_id INTEGER REFERENCES calendrier_sources(id) ON DELETE SET NULL,
            source TEXT,
            ref_externe TEXT,
            evenement_id INTEGER,
            notes TEXT,
            mes_notes TEXT,
            favori INTEGER DEFAULT 0,
            masque INTEGER DEFAULT 0,
            modifie INTEGER DEFAULT 0,
            vu_le TEXT
        )""")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_calendrier_date ON calendrier_courses(date_debut, departement)")
    cur.execute("""
        CREATE TABLE IF NOT EXISTS calendrier_epreuves (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            course_id INTEGER NOT NULL REFERENCES calendrier_courses(id) ON DELETE CASCADE,
            nom TEXT,
            distance_km REAL,
            denivele_m INTEGER,
            discipline TEXT,
            heure_depart TEXT,
            prix REAL
        )""")
    cur.execute("""
        CREATE TABLE IF NOT EXISTS evenements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            club_id INTEGER REFERENCES clubs(id) ON DELETE SET NULL,
            nom TEXT NOT NULL,
            date_debut TEXT NOT NULL,
            date_fin TEXT,
            commune TEXT,
            code_postal TEXT,
            lieu TEXT,
            site TEXT,
            contact_email TEXT,
            description TEXT,
            statut TEXT NOT NULL DEFAULT 'brouillon',
            declaration_ffa TEXT,
            ouverture_inscriptions TEXT,
            cloture_inscriptions TEXT,
            date_tarif_tardif TEXT,
            pps_validite_mois INTEGER DEFAULT 3,
            autorisation_parentale INTEGER DEFAULT 1,
            notes TEXT,
            date_creation TEXT DEFAULT CURRENT_TIMESTAMP
        )""")
    cur.execute("""
        CREATE TABLE IF NOT EXISTS epreuves (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            evenement_id INTEGER NOT NULL REFERENCES evenements(id) ON DELETE CASCADE,
            nom TEXT NOT NULL,
            discipline TEXT NOT NULL DEFAULT 'trail',
            distance_km REAL,
            denivele_m INTEGER DEFAULT 0,
            date TEXT,
            heure_depart TEXT,
            quota INTEGER,
            tarif REAL DEFAULT 0,
            tarif_licencie REAL,
            tarif_tardif REAL,
            dossard_debut INTEGER,
            dossard_fin INTEGER,
            categorie_min TEXT,
            competitive INTEGER DEFAULT 1,
            notes TEXT
        )""")
    cur.execute("""
        CREATE TABLE IF NOT EXISTS inscriptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            epreuve_id INTEGER NOT NULL REFERENCES epreuves(id) ON DELETE CASCADE,
            personne_id INTEGER REFERENCES personnes(id) ON DELETE SET NULL,
            nom TEXT NOT NULL,
            prenom TEXT,
            sexe TEXT,
            date_naissance TEXT,
            nationalite TEXT,
            email TEXT,
            telephone TEXT,
            club TEXT,
            justificatif TEXT,
            numero_licence TEXT,
            type_licence TEXT,
            federation TEXT,
            pps_date TEXT,
            certificat_date TEXT,
            questionnaire_mineur INTEGER DEFAULT 0,
            autorisation_parentale INTEGER DEFAULT 0,
            justificatif_valide INTEGER DEFAULT 0,
            contact_urgence_nom TEXT,
            contact_urgence_tel TEXT,
            taille_tshirt TEXT,
            statut TEXT NOT NULL DEFAULT 'en_attente',
            dossard INTEGER,
            montant REAL,
            montant_paye REAL DEFAULT 0,
            paiement_mode TEXT,
            date_inscription TEXT,
            source TEXT,
            ref_externe TEXT,
            dossard_retire INTEGER DEFAULT 0,
            notes TEXT
        )""")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_inscriptions_epreuve ON inscriptions(epreuve_id, statut)")
    for t in ("calendrier_sources", "calendrier_courses", "evenements", "epreuves", "inscriptions"):
        _ajouter_uuid(cur, t)


# (numéro, description lisible, fonction) — dans l'ordre, sans trou
MIGRATIONS = [
    (1, "Identifiant universel (UUID) pour chaque donnée", _m001_identifiants_universels),
    (2, "Fiche Personne unique et rôles", _m002_personnes_et_roles),
    (3, "Index de performance (ITRA, UTMB, Betrail)", _m003_index_performance),
    (4, "Nutrition de course : produits, tolérances, recettes fait maison", _m004_nutrition_course),
    (5, "Matériel obligatoire des courses et caractéristiques de ton équipement", _m005_materiel_obligatoire),
    (6, "Fractionné : séances perso et répétitions faites pendant les sorties", _m006_fractionne),
    (7, "Espace Club : club, groupes, adhésions et licences par saison, tarifs", _m007_club),
    (8, "Agenda du club : séries hebdomadaires, séances, appel des présences", _m008_agenda_club),
    (9, "Annuaire trail : clubs, écoles, magasins et marques ; marque et magasin du matériel", _m009_annuaire),
    (10, "Calendrier des courses et organisation : événements, épreuves, inscriptions, dossards",
     _m010_calendrier_organisation),
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
