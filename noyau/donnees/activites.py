"""
Accès aux sorties (table `activites`).

Les requêtes sont reprises telles qu'elles étaient dans les écrans
(étape 1.4a) : mêmes colonnes, mêmes filtres, même ordre de tri, mêmes
lignes renvoyées (tuples). Toute écriture faite sans transaction
partagée annonce DONNEES_MODIFIEES (cache du coach, calculs en cours).
"""

from noyau.donnees import base
from noyau.outils.evenements import emettre, DONNEES_MODIFIEES

TYPES_COURSE = ("Trail", "Course")


def _annoncer(cur):
    if cur is None:
        emettre(DONNEES_MODIFIEES)


# ------------------------------------------------------------------
# Une sortie
# ------------------------------------------------------------------

def valeurs(activite_id, *colonnes, athlete_id=None, cur=None):
    """Colonnes choisies d'une sortie (tuple) ou None.
    Avec athlete_id, la sortie doit aussi appartenir à cet athlète."""
    return base.valeurs("activites", activite_id, colonnes, cur=cur, filtre_athlete=athlete_id)


def id_par_empreinte(empreinte, cur=None):
    ligne = base.lire_un("SELECT id FROM activites WHERE empreinte = ?", (empreinte,), cur)
    return ligne[0] if ligne else None


def inserer(champs, cur=None):
    """Crée une sortie à partir d'un dict {colonne: valeur} ; renvoie son id."""
    nouvel_id = base.inserer("activites", champs, cur)
    _annoncer(cur)
    return nouvel_id


def modifier(activite_id, athlete_id, colonnes_valeurs, cur=None):
    """colonnes_valeurs : liste [(colonne, valeur), ...] — UPDATE de la
    sortie `activite_id` de l'athlète `athlete_id`."""
    noms = base.verifier_colonnes([nom for nom, _ in colonnes_valeurs])
    affectations = ", ".join(f"{nom}=?" for nom in noms)
    parametres = [valeur for _, valeur in colonnes_valeurs] + [activite_id, athlete_id]
    base.ecrire(f"UPDATE activites SET {affectations} WHERE id=? AND athlete_id=?", parametres, cur)
    _annoncer(cur)


# ------------------------------------------------------------------
# Listes de sorties d'un athlète
# ------------------------------------------------------------------

def ids_chronologiques(athlete_id):
    lignes = base.lire_tous("SELECT id FROM activites WHERE athlete_id=? ORDER BY date, id", (athlete_id,))
    return [r[0] for r in lignes]


def recentes(athlete_id, limite):
    """(id, date, nom, type, distance, denivele, duree, fc_moyenne), plus récente d'abord."""
    return base.lire_tous(
        "SELECT id, date, nom, type, distance, denivele, duree, frequence_cardiaque_moyenne "
        "FROM activites WHERE athlete_id=? ORDER BY date DESC LIMIT ?",
        (athlete_id, limite),
    )


def pour_liaison(athlete_id, limite):
    """(id, date, type, distance, duree) des dernières sorties — liste
    proposée pour rattacher une blessure, un résultat ou une séance."""
    return base.lire_tous(
        "SELECT id, date, type, distance, duree FROM activites "
        "WHERE athlete_id=? ORDER BY date DESC LIMIT ?",
        (athlete_id, limite),
    )


def pour_choix_photo(athlete_id):
    """(id, date, nom, type), plus récente d'abord."""
    return base.lire_tous(
        "SELECT id, date, nom, type FROM activites WHERE athlete_id=? ORDER BY date DESC",
        (athlete_id,),
    )


def par_jour_entre(athlete_id, debut_iso, fin_iso):
    """(id, date, nom, type, distance, denivele, duree, fc_moyenne) dont le
    jour est entre debut_iso et fin_iso inclus, dans l'ordre chronologique."""
    return base.lire_tous(
        "SELECT id, date, nom, type, distance, denivele, duree, frequence_cardiaque_moyenne "
        "FROM activites WHERE athlete_id=? AND substr(date,1,10) BETWEEN ? AND ? "
        "ORDER BY date",
        (athlete_id, debut_iso, fin_iso),
    )


def colonnes_de_l_athlete(athlete_id, colonnes, debut=None, fin=None, type_=None):
    """Colonnes choisies de toutes les sorties de l'athlète, filtrées par
    période (debut et fin, bornes incluses) ou par type."""
    sql = f"SELECT {', '.join(base.verifier_colonnes(list(colonnes)))} FROM activites WHERE athlete_id=?"
    parametres = [athlete_id]
    if debut is not None and fin is not None:
        sql += " AND date >= ? AND date <= ?"
        parametres += [debut, fin]
    elif type_ is not None:
        sql += " AND type=?"
        parametres.append(type_)
    return base.lire_tous(sql, tuple(parametres))


def pour_record_vo2max(athlete_id):
    """(date, distance, duree, vo2max) des courses et trails d'au moins 3 km."""
    return base.lire_tous(
        "SELECT date, distance, duree, vo2max FROM activites WHERE athlete_id=? "
        "AND type IN ('Trail','Course') AND distance >= 3 AND duree > 0",
        (athlete_id,),
    )


def pour_page_telephone(athlete_id):
    return base.lire_tous(
        "SELECT date, nom, type, distance, denivele, duree, frequence_cardiaque_moyenne, allure_moyenne, vo2max "
        "FROM activites WHERE athlete_id=? ORDER BY date",
        (athlete_id,),
    )


def detaillees_depuis(athlete_id, depuis_iso):
    """Sorties depuis une date avec effet d'entraînement et temps par zone."""
    return base.lire_tous(
        "SELECT id, date, nom, type, distance, denivele, duree, frequence_cardiaque_moyenne, "
        "te_aerobie, te_anaerobie, charge_garmin, "
        "temps_zone_1, temps_zone_2, temps_zone_3, temps_zone_4, temps_zone_5 "
        "FROM activites WHERE athlete_id=? AND date>=? ORDER BY date",
        (athlete_id, depuis_iso),
    )


def maxima_depuis(athlete_id, depuis_iso):
    """(plus longue distance, plus gros D+) des Trail/Course/Randonnée depuis une date."""
    return base.lire_un(
        "SELECT MAX(distance), MAX(denivele) FROM activites "
        "WHERE athlete_id=? AND date >= ? AND type IN ('Trail','Course','Randonnée')",
        (athlete_id, depuis_iso),
    )


def somme_distance_depuis(athlete_id, depuis_iso, types=None):
    """Kilomètres cumulés depuis une date, éventuellement pour certains types."""
    if types:
        marqueurs = ",".join("?" * len(types))
        ligne = base.lire_un(
            f"SELECT SUM(distance) FROM activites WHERE athlete_id=? AND date >= ? "
            f"AND type IN ({marqueurs})",
            (athlete_id, depuis_iso, *types),
        )
    else:
        ligne = base.lire_un(
            "SELECT SUM(distance) FROM activites WHERE athlete_id=? AND date >= ?",
            (athlete_id, depuis_iso),
        )
    return ligne[0]


# ------------------------------------------------------------------
# Sorties avec leur trace (jointure avec parcours_gpx)
# ------------------------------------------------------------------

def avec_trace_entre(athlete_id, debut_iso, fin_iso_exclue):
    """(id, date, distance, type, trace_json) des sorties ayant une trace."""
    return base.lire_tous(
        "SELECT a.id, a.date, a.distance, a.type, p.trace_json FROM activites a "
        "JOIN parcours_gpx p ON p.activite_id=a.id WHERE a.athlete_id=? AND a.date>=? AND a.date<? "
        "AND p.trace_json IS NOT NULL ORDER BY a.date",
        (athlete_id, debut_iso, fin_iso_exclue),
    )


def avec_trace_recentes(athlete_id, depuis_iso, limite):
    """(date, nom, distance, trace_json), plus récente d'abord."""
    return base.lire_tous(
        "SELECT a.date, a.nom, a.distance, p.trace_json FROM activites a "
        "JOIN parcours_gpx p ON p.activite_id = a.id "
        "WHERE a.athlete_id=? AND a.date>=? AND p.trace_json IS NOT NULL "
        "ORDER BY a.date DESC LIMIT ?",
        (athlete_id, depuis_iso, limite),
    )
