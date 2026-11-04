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

from data.database import connexion, creer_base_de_donnees, obtenir_athletes  # noqa: F401
from noyau.traces.fit_utils import parser_fit, parser_resume_session_fit
from noyau.traces.doublons import FENETRE_TEMPS_MINUTES
from noyau.outils.date_utils import parser_date_flexible


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
    from noyau.outils.evenements import emettre, DONNEES_MODIFIEES
    emettre(DONNEES_MODIFIEES)


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
