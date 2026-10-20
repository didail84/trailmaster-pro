"""
Moteur de coaching de TrailMaster Pro.

Calcule la charge d'entraînement (TRIMP quand les données de FC sont
disponibles, avec repli automatique sur la durée puis la distance
sinon), l'ACWR (ratio charge aiguë / charge chronique — l'indicateur
standard de risque de blessure en sciences du sport) et génère des
alertes/conseils à partir de règles fixes.

Aucune dépendance externe, aucun appel réseau : tout est calculé à
partir des données déjà en base (activités, sommeil, blessures).
"""

import math
from datetime import datetime, timedelta

from data.database import connexion, obtenir_parametre, definir_parametre
from interface.date_utils import parser_date_flexible
from interface.rythme_vie import contexte_fatigue_vie

# --------------------------------------------------
# Cache court (forme du jour / ACWR) — ces deux calculs sont les plus
# lourds et les plus souvent redemandés (tableau de bord rouvert
# plusieurs fois de suite pendant une session) ; ils ne changent en
# réalité qu'après l'ajout/suppression d'une activité, donc les
# recalculer à l'identique à chaque clic est du temps perdu. Cache en
# mémoire (perdu à la fermeture du logiciel, sans effet de bord),
# avec une durée de vie courte (auto-expiration) plutôt qu'une
# invalidation manuelle partout où une activité peut être ajoutée —
# plus simple et sans risque d'oubli, au prix d'un décalage de
# quelques dizaines de secondes au pire après un import.
_DUREE_CACHE_SECONDES = 90
_cache_forme_jour = {}
_cache_acwr = {}


def invalider_cache_coach(athlete_id=None):
    """Vide le cache forme/ACWR — appelé après une suppression
    d'activité pour un rafraîchissement immédiat ; sinon le cache
    s'auto-expire de toute façon au bout de _DUREE_CACHE_SECONDES."""

    if athlete_id is None:
        _cache_forme_jour.clear()
        _cache_acwr.clear()
    else:
        for cle in [c for c in _cache_forme_jour if c[0] == athlete_id]:
            del _cache_forme_jour[cle]
        _cache_acwr.pop(athlete_id, None)


# --------------------------------------------------
# Réglages utilisateur (Réglages > Alertes et objectifs) — objectif de
# sommeil et sensibilité des alertes de charge. Stockés comme les
# autres réglages (parametres_app), relus à chaque calcul plutôt que
# mis en cache, pour qu'un changement soit pris en compte tout de
# suite (contrairement à la couleur d'accent, ça ne coûte rien de
# recalculer à chaque fois ici).

CLE_PARAMETRE_OBJECTIF_SOMMEIL = "objectif_sommeil_heures"
OBJECTIF_SOMMEIL_PAR_DEFAUT = 8.0


def obtenir_objectif_sommeil_heures():
    valeur = obtenir_parametre(CLE_PARAMETRE_OBJECTIF_SOMMEIL)
    try:
        return float(valeur) if valeur else OBJECTIF_SOMMEIL_PAR_DEFAUT
    except (TypeError, ValueError):
        return OBJECTIF_SOMMEIL_PAR_DEFAUT


def definir_objectif_sommeil_heures(heures):
    definir_parametre(CLE_PARAMETRE_OBJECTIF_SOMMEIL, heures)


CLE_PARAMETRE_SENSIBILITE_ALERTES = "sensibilite_alertes"

# Les 3 paliers déplacent ensemble les seuils ACWR et "séances
# manquées" qui déclenchent les alertes — plutôt que d'exposer les
# chiffres bruts un par un (risque de réglage incohérent), un choix à
# 3 niveaux qui garde des paliers validés.
SEUILS_SENSIBILITE_ALERTES = {
    "Prudent": {
        "acwr_bas": 0.8, "acwr_attention": 1.2, "acwr_risque": 1.4,
        "manquees_7j": 1, "manquees_14j": 2,
    },
    "Standard": {
        "acwr_bas": 0.8, "acwr_attention": 1.3, "acwr_risque": 1.5,
        "manquees_7j": 2, "manquees_14j": 3,
    },
    "Tolérant": {
        "acwr_bas": 0.7, "acwr_attention": 1.4, "acwr_risque": 1.6,
        "manquees_7j": 3, "manquees_14j": 4,
    },
}


def obtenir_sensibilite_alertes():
    valeur = obtenir_parametre(CLE_PARAMETRE_SENSIBILITE_ALERTES)
    return valeur if valeur in SEUILS_SENSIBILITE_ALERTES else "Standard"


def definir_sensibilite_alertes(niveau):
    if niveau not in SEUILS_SENSIBILITE_ALERTES:
        niveau = "Standard"
    definir_parametre(CLE_PARAMETRE_SENSIBILITE_ALERTES, niveau)


def obtenir_seuils_alertes():
    return SEUILS_SENSIBILITE_ALERTES[obtenir_sensibilite_alertes()]


# Poids relatif de pénibilité par type d'activité, utilisé uniquement
# en repli quand les données de fréquence cardiaque sont indisponibles.
FACTEUR_TYPE = {
    "Trail": 1.0,
    "Course": 0.95,
    "Vélo": 0.6,
    "VTT": 0.75,
    "Randonnée": 0.5,
    "Route": 0.9,
    "Cardio machine": 0.55,
    "Autre": 0.8,
}


def _facteur_type(type_activite):
    return FACTEUR_TYPE.get((type_activite or "").strip(), FACTEUR_TYPE["Autre"])


# Pénibilité d'une séance de renforcement à partir du RPE (échelle 6-10
# utilisée dans l'écran de suivi musculation) : sert au calcul de charge
# façon "session RPE" (méthode de Foster), en repli d'une mesure FC/TRIMP
# qui n'a pas de sens pour du travail en séries/répétitions.
def _facteur_musculation(rpe):
    if rpe is None:
        return 0.5
    rpe = max(6, min(10, rpe))
    return 0.35 + (rpe - 6) * 0.15


def calculer_charge_musculation(seance, athlete):
    """
    seance : dict avec type_seance ('Renforcement' ou 'Cardio machine'),
    et selon le type : duree_min/distance_km/fc_moyenne (Cardio machine)
    ou series/rpe/douleur (Renforcement).

    Retourne (valeur_charge, methode), même logique que
    calculer_charge_activite : "trimp"/"duree"/"distance" pour le cardio
    machine (calcul identique à une sortie), "musculation_rpe" pour le
    renforcement (méthode session-RPE : durée × pénibilité perçue).
    """

    if seance.get("type_seance") == "Cardio machine":
        activite = {
            "type": "Cardio machine",
            "distance": seance.get("distance_km") or 0,
            "duree": (seance.get("duree_min") or 0) * 60,
            "frequence_cardiaque_moyenne": seance.get("fc_moyenne") or 0,
        }
        return calculer_charge_activite(activite, athlete)

    duree_min = seance.get("duree_min") or 0
    if duree_min <= 0:
        series = seance.get("series") or 0
        duree_min = max(series * 4, 15) if series else 20

    charge = round(duree_min * _facteur_musculation(seance.get("rpe")), 1)
    return charge, "musculation_rpe"


def _obtenir_athlete(athlete_id):
    conn = connexion()
    cur = conn.cursor()
    cur.execute(
        "SELECT id, nom, prenom, fc_repos, fc_max, fc_seuil, sexe "
        "FROM athletes WHERE id=?",
        (athlete_id,),
    )
    ligne = cur.fetchone()
    conn.close()
    if not ligne:
        return None
    return {
        "id": ligne[0], "nom": ligne[1], "prenom": ligne[2],
        "fc_repos": ligne[3], "fc_max": ligne[4], "fc_seuil": ligne[5],
        "sexe": ligne[6],
    }


def calculer_charge_activite(activite, athlete):
    """
    activite : dict avec au moins date/type/distance/duree (en secondes)/
    frequence_cardiaque_moyenne.

    Retourne (valeur_charge, methode) :
      - "trimp"    : formule de Banister, la plus fiable (nécessite FC
                     moyenne de la séance + FC repos/max de l'athlète)
      - "duree"    : estimation à partir de la durée réelle × pénibilité du type
      - "distance" : dernier repli, à partir de la distance seule
                     (utile tant que la durée n'est pas correctement
                     importée depuis le fichier source)
      - "aucune"   : pas assez de données pour estimer une charge
    """

    duree_min = (activite.get("duree") or 0) / 60
    fc_moy = activite.get("frequence_cardiaque_moyenne") or 0
    distance = activite.get("distance") or 0

    fc_repos = athlete.get("fc_repos") if athlete else None
    fc_max = athlete.get("fc_max") if athlete else None

    if duree_min > 0 and fc_moy > 0 and fc_repos and fc_max and fc_max > fc_repos:
        ratio = (fc_moy - fc_repos) / (fc_max - fc_repos)
        ratio = max(0.0, min(1.0, ratio))
        if (athlete.get("sexe") or "").lower().startswith("f"):
            trimp = duree_min * ratio * 0.86 * math.exp(1.67 * ratio)
        else:
            trimp = duree_min * ratio * 0.64 * math.exp(1.92 * ratio)
        return round(trimp, 1), "trimp"

    if duree_min > 0:
        return round(duree_min * _facteur_type(activite.get("type")), 1), "duree"

    if distance > 0:
        return round(distance * _facteur_type(activite.get("type")) * 10, 1), "distance"

    return 0.0, "aucune"


def charge_activite_pour_athlete(activite, athlete_id):
    """Wrapper pratique pour un affichage ponctuel (ex. colonne "Charge"
    de l'historique) : évite à l'appelant d'avoir à récupérer lui-même
    le profil complet de l'athlète (fc_repos/fc_max/sexe)."""
    athlete = _obtenir_athlete(athlete_id)
    return calculer_charge_activite(activite, athlete)


def obtenir_charges_journalieres(athlete_id, nb_jours=35):
    """Retourne une liste de (date_jour, charge_totale_du_jour) pour les
    nb_jours derniers jours (aujourd'hui inclus), du plus ancien au
    plus récent — y compris les jours sans activité (charge à 0)."""

    athlete = _obtenir_athlete(athlete_id)

    conn = connexion()
    cur = conn.cursor()
    cur.execute(
        "SELECT date, type, distance, duree, frequence_cardiaque_moyenne "
        "FROM activites WHERE athlete_id=?",
        (athlete_id,),
    )
    lignes = cur.fetchall()
    conn.close()

    aujourdhui = datetime.now().date()
    date_min = aujourdhui - timedelta(days=nb_jours - 1)

    charges_par_jour = {}
    for date_texte, type_, distance, duree, fc_moy in lignes:
        date = parser_date_flexible(date_texte)
        if date is None:
            continue
        jour = date.date()
        if jour < date_min or jour > aujourdhui:
            continue

        activite = {
            "type": type_, "distance": distance,
            "duree": duree, "frequence_cardiaque_moyenne": fc_moy,
        }
        charge, _ = calculer_charge_activite(activite, athlete)
        charges_par_jour[jour] = charges_par_jour.get(jour, 0) + charge

    conn = connexion()
    cur = conn.cursor()
    cur.execute(
        "SELECT date, type_seance, duree_min, distance_km, fc_moyenne, series, rpe "
        "FROM musculation_suivi WHERE athlete_id=?",
        (athlete_id,),
    )
    lignes_muscu = cur.fetchall()
    conn.close()

    for date_texte, type_seance, duree_min, distance_km, fc_moy, series, rpe in lignes_muscu:
        date = parser_date_flexible(date_texte)
        if date is None:
            continue
        jour = date.date()
        if jour < date_min or jour > aujourdhui:
            continue

        seance = {
            "type_seance": type_seance, "duree_min": duree_min,
            "distance_km": distance_km, "fc_moyenne": fc_moy,
            "series": series, "rpe": rpe,
        }
        charge, _ = calculer_charge_musculation(seance, athlete)
        charges_par_jour[jour] = charges_par_jour.get(jour, 0) + charge

    resultat = []
    for i in range(nb_jours):
        jour = date_min + timedelta(days=i)
        resultat.append((jour, round(charges_par_jour.get(jour, 0.0), 1)))

    return resultat


def obtenir_date_premiere_activite(athlete_id):
    """Date (objet date) de la toute première activité enregistrée
    pour cet athlète, ou None si aucune activité n'a de date valide."""

    conn = connexion()
    cur = conn.cursor()
    cur.execute("SELECT date FROM activites WHERE athlete_id=?", (athlete_id,))
    lignes = cur.fetchall()
    conn.close()

    dates = [parser_date_flexible(d) for (d,) in lignes]
    dates = [d for d in dates if d is not None]
    return min(dates).date() if dates else None


# Périodes proposées à l'affichage : (libellé, nombre de jours ou None
# pour "tout l'historique", calculé dynamiquement selon la 1ère sortie).
PERIODES_DISPONIBLES = [
    ("7 jours", 7),
    ("1 mois", 30),
    ("6 mois", 182),
    ("1 an", 365),
    ("2 ans", 730),
    ("5 ans", 1825),
    ("10 ans", 3650),
    ("Tout l'historique", None),
]


def _granularite_auto(nb_jours):
    """Choisit le regroupement le mieux adapté pour rester lisible :
    au-delà d'une trentaine de barres, on agrège plutôt que d'afficher
    un point par jour (un graphique sur 10 ans en jours ferait 3650
    barres, illisible et lent à dessiner)."""

    if nb_jours <= 35:
        return "jour"
    if nb_jours <= 180:
        return "semaine"
    if nb_jours <= 730:
        return "mois"
    return "trimestre"


def _agreger_points(points_journaliers, granularite, arrondi=1):
    """Regroupe une liste de (jour: date, valeur) par jour/semaine/mois/
    trimestre selon la granularité demandée — logique partagée par le
    graphique de charge et le graphique polyvalent du tableau de bord
    (n'importe quelle mesure cumulable : distance, dénivelé, durée,
    nombre de séances...)."""

    if granularite == "jour":
        return [(jour.strftime("%d/%m"), round(valeur, arrondi)) for jour, valeur in points_journaliers]

    groupes = {}
    ordre = []

    for jour, valeur in points_journaliers:
        if granularite == "semaine":
            annee_iso, semaine_iso, _ = jour.isocalendar()
            cle = (annee_iso, semaine_iso)
            label = f"S{semaine_iso:02d}/{str(annee_iso)[2:]}"
        elif granularite == "mois":
            cle = (jour.year, jour.month)
            label = jour.strftime("%m/%Y")
        else:  # trimestre
            trimestre = (jour.month - 1) // 3 + 1
            cle = (jour.year, trimestre)
            label = f"T{trimestre} {jour.year}"

        if cle not in groupes:
            groupes[cle] = [label, 0.0]
            ordre.append(cle)
        groupes[cle][1] += valeur

    return [(groupes[cle][0], round(groupes[cle][1], arrondi)) for cle in ordre]


def obtenir_charges_periode(athlete_id, nb_jours):
    """Retourne (points, granularite) où points est une liste de
    (libellé, charge) prête à être tracée, agrégée selon la durée
    demandée pour rester lisible sur les longues périodes."""

    charges = obtenir_charges_journalieres(athlete_id, nb_jours=nb_jours)
    granularite = _granularite_auto(nb_jours)
    return _agreger_points(charges, granularite), granularite


# ------------------------------------------------------------------
# GRAPHIQUE POLYVALENT DU TABLEAU DE BORD — n'importe quelle mesure
# cumulable (distance, dénivelé, durée, nombre de séances), sur
# n'importe quelle période — même principe d'agrégation que la charge.
# ------------------------------------------------------------------

MESURES_CUMULABLES = {
    "distance": {"libelle": "Distance (km)", "champ": "distance", "arrondi": 1},
    "denivele": {"libelle": "Dénivelé D+ (m)", "champ": "denivele", "arrondi": 0},
    "duree": {"libelle": "Durée (h)", "champ": "duree", "arrondi": 1},
    "nb_seances": {"libelle": "Nombre de séances", "champ": None, "arrondi": 0},
    "charge": {"libelle": "Charge d'entraînement", "champ": None, "arrondi": 1},
}


def _journalier_par_mesure(athlete_id, mesure, nb_jours):
    """Liste de (date, valeur) — même forme que
    obtenir_charges_journalieres, pour une mesure quelconque parmi
    MESURES_CUMULABLES, jour par jour sur nb_jours jours (aujourd'hui
    inclus), jours sans activité à 0."""

    if mesure == "charge":
        return obtenir_charges_journalieres(athlete_id, nb_jours=nb_jours)

    conn = connexion()
    cur = conn.cursor()
    cur.execute(
        "SELECT date, distance, denivele, duree FROM activites WHERE athlete_id=?",
        (athlete_id,),
    )
    lignes = cur.fetchall()
    conn.close()

    aujourdhui = datetime.now().date()
    date_min = aujourdhui - timedelta(days=nb_jours - 1)

    valeurs_par_jour = {}
    for date_texte, distance, denivele, duree in lignes:
        date_obj = parser_date_flexible(date_texte)
        if date_obj is None:
            continue
        jour = date_obj.date()
        if jour < date_min or jour > aujourdhui:
            continue

        if mesure == "distance":
            apport = distance or 0
        elif mesure == "denivele":
            apport = denivele or 0
        elif mesure == "duree":
            apport = (duree or 0) / 3600  # secondes -> heures
        elif mesure == "nb_seances":
            apport = 1
        else:
            apport = 0

        valeurs_par_jour[jour] = valeurs_par_jour.get(jour, 0) + apport

    resultat = []
    for i in range(nb_jours):
        jour = date_min + timedelta(days=i)
        resultat.append((jour, round(valeurs_par_jour.get(jour, 0.0), 3)))
    return resultat


def obtenir_mesure_periode(athlete_id, mesure, nb_jours):
    """Équivalent de obtenir_charges_periode, généralisé à n'importe
    quelle mesure de MESURES_CUMULABLES. Retourne (points, granularite,
    total_periode)."""

    info = MESURES_CUMULABLES.get(mesure, MESURES_CUMULABLES["distance"])
    journalier = _journalier_par_mesure(athlete_id, mesure, nb_jours)
    granularite = _granularite_auto(nb_jours)
    points = _agreger_points(journalier, granularite, arrondi=info["arrondi"])
    total = round(sum(v for _, v in journalier), info["arrondi"])
    return points, granularite, total


def _calculer_acwr_sans_cache(athlete_id):
    """Retourne charge_chronique (moyenne/jour sur 28j), charge_aigue
    (moyenne/jour sur 7j), acwr (ratio) et une interprétation courte."""

    charges = obtenir_charges_journalieres(athlete_id, nb_jours=28)

    charge_chronique = sum(c for _, c in charges) / 28
    charge_aigue = sum(c for _, c in charges[-7:]) / 7

    if charge_chronique <= 0:
        acwr = None
    else:
        acwr = round(charge_aigue / charge_chronique, 2)

    seuils = obtenir_seuils_alertes()

    if acwr is None:
        interpretation = "Pas assez de données récentes pour calculer l'ACWR."
    elif acwr < seuils["acwr_bas"]:
        interpretation = "Charge en retrait — tu peux relancer progressivement."
    elif acwr <= seuils["acwr_attention"]:
        interpretation = "Charge bien équilibrée, poursuis sur ce rythme."
    elif acwr <= seuils["acwr_risque"]:
        interpretation = "Charge en hausse — reste vigilant sur les prochains jours."
    else:
        interpretation = "Charge en forte hausse — risque de blessure élevé."

    return {
        "charge_chronique": round(charge_chronique, 1),
        "charge_aigue": round(charge_aigue, 1),
        "acwr": acwr,
        "interpretation": interpretation,
    }


def _sommeil_moyen_recent(athlete_id, nb_entrees=5):
    conn = connexion()
    cur = conn.cursor()
    cur.execute(
        "SELECT duree_heures FROM sommeil WHERE athlete_id=? "
        "ORDER BY date DESC LIMIT ?",
        (athlete_id, nb_entrees),
    )
    valeurs = [d for (d,) in cur.fetchall() if d is not None]
    conn.close()
    if not valeurs:
        return None
    return sum(valeurs) / len(valeurs)


def _recuperation_recente(athlete_id, nb_jours=5):
    """Combine les signaux de récupération (HRV, stress — importés depuis
    un .FIT ou depuis l'export santé Garmin —, FC de repos et Body
    Battery de recuperation_quotidienne) sur les derniers jours en un
    score 0-100, ou None si rien n'a jamais été importé pour cet athlète.
    Repli documenté : sans aucune de ces données, le score de forme
    continue de fonctionner exactement comme avant leur ajout."""

    from data.database import obtenir_signaux_recuperation_recents

    lignes = obtenir_signaux_recuperation_recents(athlete_id, nb_entrees=nb_jours)

    stress_valeurs = [s for (_, _, s, _) in lignes if s is not None]
    hrv_valeurs = [h for (_, h, _, _) in lignes if h is not None]

    composantes = []
    if stress_valeurs:
        stress_moyen = sum(stress_valeurs) / len(stress_valeurs)
        composantes.append(max(0, min(100, 100 - stress_moyen)))  # stress bas = bon score
    if len(hrv_valeurs) >= 2:
        # Tendance simple : dernière valeur vs moyenne des précédentes —
        # une HRV en baisse marquée est un signe de fatigue non
        # récupérée (littérature sport science), pas d'échelle absolue
        # universelle (dépend trop de l'individu/capteur).
        derniere = hrv_valeurs[0]
        reference = sum(hrv_valeurs[1:]) / len(hrv_valeurs[1:])
        if reference > 0:
            variation_pct = (derniere - reference) / reference * 100
            composantes.append(max(0, min(100, 60 + variation_pct * 2)))

    # FC de repos et Body Battery (export santé Garmin) : seulement si la
    # mesure est récente (7 jours) — la montre n'est pas portée tous les jours.
    try:
        from datetime import date as _d, timedelta as _td
        from statistics import median as _med
        conn = connexion()
        cur = conn.cursor()
        limite = (_d.today() - _td(days=7)).isoformat()
        cur.execute(
            "SELECT date, fc_repos, body_battery_max FROM recuperation_quotidienne "
            "WHERE athlete_id=? AND date>=? ORDER BY date DESC",
            (athlete_id, limite),
        )
        recentes = cur.fetchall()
        fc_recente = next(((d, v) for d, v, _ in recentes if v is not None), None)
        bb_recent = next((b for _, _, b in recentes if b is not None), None)
        if fc_recente:
            debut_base = (_d.fromisoformat(fc_recente[0]) - _td(days=30)).isoformat()
            cur.execute(
                "SELECT fc_repos FROM recuperation_quotidienne WHERE athlete_id=? "
                "AND fc_repos IS NOT NULL AND date>=? AND date<?",
                (athlete_id, debut_base, fc_recente[0]),
            )
            base = [v for (v,) in cur.fetchall()]
            if len(base) >= 5:
                ecart = fc_recente[1] - _med(base)  # bpm au-dessus de l'habitude
                composantes.append(max(0, min(100, 65 - ecart * 8)))
        if bb_recent is not None:
            composantes.append(max(0, min(100, bb_recent)))
        conn.close()
    except Exception:
        pass  # table absente (ancienne base) : ignoré

    if not composantes:
        return None

    return round(sum(composantes) / len(composantes))


def _blessures_actives(athlete_id):
    conn = connexion()
    cur = conn.cursor()
    cur.execute(
        "SELECT zone_corporelle, type_blessure FROM blessures "
        "WHERE athlete_id=? AND statut != 'Guérie'",
        (athlete_id,),
    )
    lignes = cur.fetchall()
    conn.close()
    return lignes


def _jours_forte_charge_recents(athlete_id, nb_jours=5):
    """Compte les jours récents dont la charge dépasse nettement la
    moyenne chronique (repli utilisé en l'absence de RPE/FC fiables
    pour détecter un enchaînement de séances trop exigeantes)."""

    acwr_info = calculer_acwr(athlete_id)
    charge_chronique = acwr_info["charge_chronique"]
    if charge_chronique <= 0:
        return 0

    charges = obtenir_charges_journalieres(athlete_id, nb_jours=nb_jours)
    seuil = charge_chronique * 1.5
    return sum(1 for _, c in charges if c > seuil)


def _seances_renforcement_jambes_recentes(athlete_id):
    """Séances de renforcement 'Jambes' à ressenti élevé (RPE≥8 ou
    douleur≥3) aujourd'hui ou hier — sert à repérer un cumul de fatigue
    avec une sortie intense sur la même période."""

    conn = connexion()
    cur = conn.cursor()
    cur.execute(
        "SELECT date, rpe, douleur FROM musculation_suivi "
        "WHERE athlete_id=? AND type_seance='Renforcement' AND groupe_musculaire='Jambes'",
        (athlete_id,),
    )
    lignes = cur.fetchall()
    conn.close()

    aujourdhui = datetime.now().date()
    resultat = []
    for date_texte, rpe, douleur in lignes:
        date = parser_date_flexible(date_texte)
        if date is None:
            continue
        jour = date.date()
        if jour not in (aujourdhui, aujourdhui - timedelta(days=1)):
            continue
        if (rpe is not None and rpe >= 8) or (douleur is not None and douleur >= 3):
            resultat.append(jour)
    return resultat


def _charge_sorties_jour(athlete_id, jour, athlete):
    """Charge des seules sorties (table activites, hors musculation)
    pour un jour donné — utilisé pour croiser avec les séances jambes."""

    conn = connexion()
    cur = conn.cursor()
    cur.execute(
        "SELECT date, type, distance, duree, frequence_cardiaque_moyenne "
        "FROM activites WHERE athlete_id=?",
        (athlete_id,),
    )
    lignes = cur.fetchall()
    conn.close()

    total = 0.0
    for date_texte, type_, distance, duree, fc_moy in lignes:
        date = parser_date_flexible(date_texte)
        if date is None or date.date() != jour:
            continue
        activite = {
            "type": type_, "distance": distance,
            "duree": duree, "frequence_cardiaque_moyenne": fc_moy,
        }
        charge, _ = calculer_charge_activite(activite, athlete)
        total += charge
    return total


# ==================================================================
# POURCENTAGE DE RISQUE PAR CRITÈRE — alimente les pastilles colorées
# vert/jaune/orange/rouge/noir (voir interface/theme.py —
# couleur_pour_pourcentage) sur le tableau de bord et les alertes.
# Chaque critère est ramené à une échelle 0-100 (au-delà de 100 en cas
# de dépassement franc d'un seuil) : 0 = situation idéale, 100 = seuil
# critique atteint.
# ==================================================================

def _pourcentage_lineaire(valeur, bas, haut):
    """0% à `bas`, 100% à `haut` (peut dépasser 100% si valeur > haut,
    jamais négatif si valeur < bas)."""
    if haut == bas:
        return 0.0
    return max(0.0, (valeur - bas) / (haut - bas) * 100)


def pourcentage_risque_acwr(acwr_info):
    """0% au seuil bas, 50% au seuil attention, 100% au seuil risque —
    au-delà, continue de monter linéairement (peut dépasser 100%)."""

    acwr = acwr_info.get("acwr") if acwr_info else None
    if acwr is None:
        return None
    seuils = obtenir_seuils_alertes()
    if acwr <= seuils["acwr_attention"]:
        return round(_pourcentage_lineaire(acwr, seuils["acwr_bas"], seuils["acwr_attention"]) * 0.5, 1)
    return round(50 + _pourcentage_lineaire(acwr, seuils["acwr_attention"], seuils["acwr_risque"]) * 0.5, 1)


def pourcentage_risque_forme_jour(score):
    """Le score de forme du jour est déjà 0-100 (100 = excellent) —
    le risque est simplement son complément."""

    if score is None:
        return None
    return round(max(0, 100 - score), 1)


def pourcentage_risque_sommeil(sommeil_moyen, objectif=None):
    if sommeil_moyen is None:
        return None
    objectif = objectif if objectif is not None else obtenir_objectif_sommeil_heures()
    if not objectif or objectif <= 0:
        return None
    ratio_atteint = sommeil_moyen / objectif * 100
    return round(max(0, 100 - ratio_atteint), 1)


def pourcentage_risque_charge(jours_forte_charge, max_jours=5):
    """100% quand tous les jours de la fenêtre récente sont à forte
    charge (voir _jours_forte_charge_recents)."""

    return round(max(0, min(150, jours_forte_charge / max_jours * 100)), 1)


def obtenir_indicateurs_couleur(athlete_id):
    """Vue d'ensemble des critères surveillés (ACWR, indice de forme du
    jour, sommeil récent, jours à forte charge), chacun avec sa valeur,
    son pourcentage de risque 0-100+ et la couleur correspondante —
    alimente les pastilles colorées du tableau de bord et de la
    consultation réseau local."""

    from interface.theme import couleur_pour_pourcentage

    acwr_info = calculer_acwr(athlete_id)
    forme_jour = calculer_score_forme_jour(athlete_id)
    sommeil_moyen = _sommeil_moyen_recent(athlete_id)
    jours_forte_charge = _jours_forte_charge_recents(athlete_id)

    indicateurs = {}

    pourcentage = pourcentage_risque_acwr(acwr_info)
    couleur, label = couleur_pour_pourcentage(pourcentage)
    indicateurs["acwr"] = {
        "titre": "ACWR", "valeur": acwr_info["acwr"],
        "pourcentage": pourcentage, "couleur": couleur, "label_couleur": label,
    }

    pourcentage = pourcentage_risque_forme_jour(forme_jour["score"])
    couleur, label = couleur_pour_pourcentage(pourcentage)
    indicateurs["forme_jour"] = {
        "titre": "Indice de forme", "valeur": forme_jour["score"],
        "pourcentage": pourcentage, "couleur": couleur, "label_couleur": label,
    }

    pourcentage = pourcentage_risque_sommeil(sommeil_moyen)
    couleur, label = couleur_pour_pourcentage(pourcentage)
    indicateurs["sommeil"] = {
        "titre": "Sommeil récent",
        "valeur": round(sommeil_moyen, 1) if sommeil_moyen is not None else None,
        "pourcentage": pourcentage, "couleur": couleur, "label_couleur": label,
    }

    pourcentage = pourcentage_risque_charge(jours_forte_charge)
    couleur, label = couleur_pour_pourcentage(pourcentage)
    indicateurs["charge"] = {
        "titre": "Jours à forte charge (5j)", "valeur": jours_forte_charge,
        "pourcentage": pourcentage, "couleur": couleur, "label_couleur": label,
    }

    return indicateurs


def generer_alertes(athlete_id):
    """Retourne une liste de dicts {niveau, message}.
    niveau ∈ {'critique', 'attention', 'info', 'ok'}."""

    alertes = []

    acwr_info = calculer_acwr(athlete_id)
    acwr = acwr_info["acwr"]
    seuils = obtenir_seuils_alertes()

    pourcentage_acwr = pourcentage_risque_acwr(acwr_info)

    if acwr is None:
        alertes.append({
            "niveau": "info",
            "message": "Pas encore assez d'activités récentes pour évaluer la charge d'entraînement.",
            "pourcentage": None,
        })
    elif acwr > seuils["acwr_risque"]:
        alertes.append({
            "niveau": "critique",
            "message": (
                f"ACWR à {acwr} : charge en forte hausse, risque de blessure élevé. "
                "Privilégie une séance légère ou un repos complet dans les prochains jours."
            ),
            "pourcentage": pourcentage_acwr,
        })
    elif acwr > seuils["acwr_attention"]:
        alertes.append({
            "niveau": "attention",
            "message": f"ACWR à {acwr} : charge en hausse, reste vigilant sur les prochains jours.",
            "pourcentage": pourcentage_acwr,
        })
    elif acwr < seuils["acwr_bas"]:
        alertes.append({
            "niveau": "info",
            "message": f"ACWR à {acwr} : charge en retrait, tu peux relancer progressivement.",
            "pourcentage": pourcentage_acwr,
        })
    else:
        alertes.append({
            "niveau": "ok",
            "message": f"ACWR à {acwr} : charge bien équilibrée, poursuis sur ce rythme.",
            "pourcentage": pourcentage_acwr,
        })

    for zone, type_blessure in _blessures_actives(athlete_id):
        alertes.append({
            "niveau": "critique",
            "message": (
                f"Blessure non guérie ({type_blessure or 'type non précisé'} — "
                f"{zone or 'zone non précisée'}) : évite les séances à forte intensité "
                "tant qu'elle n'est pas résolue."
            ),
        })

    sommeil_moyen = _sommeil_moyen_recent(athlete_id)
    if sommeil_moyen is not None and sommeil_moyen < 6:
        alertes.append({
            "niveau": "attention",
            "message": (
                f"Sommeil moyen de {sommeil_moyen:.1f} h sur les dernières nuits renseignées : "
                "priorise la récupération avant d'ajouter du volume d'entraînement."
            ),
            "pourcentage": pourcentage_risque_sommeil(sommeil_moyen),
        })

    charge_chronique = acwr_info["charge_chronique"]
    if charge_chronique > 0:
        athlete = _obtenir_athlete(athlete_id)
        for jour_jambes in _seances_renforcement_jambes_recentes(athlete_id):
            jour_lendemain = jour_jambes + timedelta(days=1)
            charge_meme_jour = _charge_sorties_jour(athlete_id, jour_jambes, athlete)
            charge_lendemain = _charge_sorties_jour(athlete_id, jour_lendemain, athlete)

            if charge_meme_jour > charge_chronique or charge_lendemain > charge_chronique:
                label_jour = "aujourd'hui" if jour_jambes == datetime.now().date() else "hier"
                alertes.append({
                    "niveau": "attention",
                    "message": (
                        f"Grosse séance jambes {label_jour} (RPE élevé ou douleur notable) combinée "
                        "à une sortie de charge supérieure à ta moyenne sur la même période : "
                        "laisse le temps aux jambes de récupérer, envisage une sortie plus légère "
                        "ou un jour de repos."
                    ),
                })
                break  # une seule alerte de ce type suffit

    jours_forte_charge = _jours_forte_charge_recents(athlete_id)
    if jours_forte_charge >= 3:
        alertes.append({
            "niveau": "attention",
            "message": (
                f"{jours_forte_charge} jours à forte charge sur les 5 derniers jours : "
                "intercale une sortie facile pour éviter l'accumulation de fatigue."
            ),
        })

    if not alertes:
        alertes.append({
            "niveau": "info",
            "message": "Pas encore assez de données pour générer des conseils.",
        })

    return alertes


# ==================================================================
# COURBE FITNESS / FATIGUE / FORME (équivalent CTL/ATL/TSB)
# ==================================================================
# Même principe que la Performance Management Chart popularisée par
# TrainingPeaks : Fitness (CTL) = moyenne mobile exponentielle de la
# charge sur 42 jours, Fatigue (ATL) = idem sur 7 jours, Forme (TSB) =
# Fitness - Fatigue. Une Forme positive indique un athlète reposé et
# prêt à performer ; très négative, un athlète fatigué qui a besoin
# de récupération.
#
# Limite à connaître : au tout début de la fenêtre calculée, Fitness et
# Fatigue démarrent à 0 et remontent progressivement — les toutes
# premières semaines de la courbe sont donc sous-estimées tant que la
# moyenne mobile n'a pas eu le temps de se stabiliser (about 6 semaines).

CONSTANTE_FITNESS_JOURS = 42
CONSTANTE_FATIGUE_JOURS = 7


def calculer_serie_forme(athlete_id, nb_jours=180):
    """Retourne une liste de dicts {date, fitness, fatigue, forme} du
    plus ancien au plus récent, sur nb_jours jours."""

    charges = obtenir_charges_journalieres(athlete_id, nb_jours=nb_jours)

    fitness = 0.0
    fatigue = 0.0
    serie = []

    for jour, charge in charges:
        fitness += (charge - fitness) / CONSTANTE_FITNESS_JOURS
        fatigue += (charge - fatigue) / CONSTANTE_FATIGUE_JOURS
        forme = fitness - fatigue

        serie.append({
            "date": jour,
            "fitness": round(fitness, 1),
            "fatigue": round(fatigue, 1),
            "forme": round(forme, 1),
        })

    return serie


# ==================================================================
# SCORE DE FORME DU JOUR
# ==================================================================
# Combine quatre signaux déjà calculés par ailleurs (aucun nouveau
# capteur requis) : la Forme (TSB), le sommeil récent, la présence
# d'une blessure active, et le rythme de vie du jour (lever, trajets,
# horaires de travail — renseigné une fois dans Réglages). Pondération :
# 45 % charge/forme, 25 % sommeil, 20 % absence de blessure, 10 % rythme
# de vie — plafonné à 45 en cas de blessure active en cours, quel que
# soit le reste, par prudence.

def _calculer_score_forme_jour_sans_cache(athlete_id, date_reference=None):
    serie = calculer_serie_forme(athlete_id, nb_jours=180)
    forme_jour = serie[-1]["forme"] if serie else 0.0

    # Forme 0 -> 50/100 ; chaque point de Forme au-dessus/en-dessous de
    # zéro déplace le score de 2 points, plafonné à [0, 100].
    score_charge = max(0, min(100, 50 + forme_jour * 2))

    sommeil_moyen = _sommeil_moyen_recent(athlete_id)
    if sommeil_moyen is None:
        score_sommeil = 70  # neutre, faute de donnée
    else:
        objectif_sommeil = obtenir_objectif_sommeil_heures()
        score_sommeil = max(0, min(100, (sommeil_moyen / objectif_sommeil) * 100))

    # Si des signaux HRV/stress ont été importés depuis un .FIT
    # (interface/fit_utils.py), on les mélange au score sommeil plutôt
    # que d'ajouter une composante séparée : ce sont deux facettes de la
    # même récupération, et ça évite de retoucher les poids 45/25/20/10
    # déjà réglés. Sans donnée importée (cas le plus courant), aucun
    # changement de comportement par rapport à avant.
    score_recuperation = _recuperation_recente(athlete_id)
    if score_recuperation is not None:
        score_sommeil = round(score_sommeil * 0.7 + score_recuperation * 0.3)

    blessures = _blessures_actives(athlete_id)
    score_blessure = 30 if blessures else 100

    fatigue_vie = contexte_fatigue_vie(date_reference)
    score_vie = 55 if fatigue_vie["actif"] else 100

    score = round(
        score_charge * 0.45 + score_sommeil * 0.25
        + score_blessure * 0.20 + score_vie * 0.10
    )
    if blessures:
        score = min(score, 45)
    score = max(0, min(100, score))

    if score >= 75:
        interpretation = "Bonne forme, tu peux pousser l'entraînement."
    elif score >= 50:
        interpretation = "Forme correcte, séance normale possible."
    elif score >= 30:
        interpretation = "Forme fragile, privilégie une séance légère."
    else:
        interpretation = "Fatigue ou risque élevé, repos conseillé."

    if fatigue_vie["actif"]:
        interpretation += (
            " Journée de semaine chargée (rythme de vie) : fatigue "
            "supplémentaire prise en compte."
        )

    return {
        "score": score,
        "forme": forme_jour,
        "sommeil_moyen": round(sommeil_moyen, 1) if sommeil_moyen is not None else None,
        "blessure_active": bool(blessures),
        "fatigue_vie": fatigue_vie,
        "recuperation_importee": score_recuperation is not None,
        "interpretation": interpretation,
    }


# ==================================================================
# CORRÉLATIONS TRANSVERSALES — rythme de vie ↔ forme, blessures sur la
# courbe de forme, répartition multisport (voir le document de
# positionnement marché : ces fonctions alimentent le tableau de bord
# croisé et les graphiques de l'écran Analyses & Forme).
# ==================================================================

def obtenir_blessures_periode(athlete_id, date_min, date_max):
    """Blessures dont la période (date_debut -> date_fin, ou aujourd'hui
    si toujours en cours) chevauche [date_min, date_max] — utilisé pour
    annoter la courbe de forme long terme."""

    conn = connexion()
    cur = conn.cursor()
    cur.execute(
        "SELECT date_debut, date_fin, zone_corporelle, type_blessure, statut "
        "FROM blessures WHERE athlete_id=?",
        (athlete_id,),
    )
    lignes = cur.fetchall()
    conn.close()

    resultat = []
    for date_debut_texte, date_fin_texte, zone, type_b, statut in lignes:
        debut = parser_date_flexible(date_debut_texte)
        if debut is None:
            continue
        debut = debut.date()
        fin = parser_date_flexible(date_fin_texte).date() if date_fin_texte else datetime.now().date()
        if fin < date_min or debut > date_max:
            continue
        resultat.append({
            "date_debut": debut, "date_fin": fin,
            "zone": zone or "zone non précisée", "type": type_b or "",
            "statut": statut,
        })
    return sorted(resultat, key=lambda b: b["date_debut"])


def serie_rythme_vie_actif(nb_jours=180):
    """Liste de (date, 100 ou 0) — 100 les jours de semaine où le
    rythme de vie déclare une journée longue (voir interface/
    rythme_vie.py), 0 sinon — même échelle que le score de forme pour
    être superposable sur un même graphique."""

    aujourdhui = datetime.now().date()
    resultat = []
    for i in range(nb_jours):
        jour = aujourdhui - timedelta(days=nb_jours - 1 - i)
        contexte = contexte_fatigue_vie(jour)
        resultat.append((jour, 100 if contexte["actif"] else 0))
    return resultat


def serie_resultats_courses(athlete_id, nb_jours=90):
    """Liste de (date, 100 ou 0) marquant les jours de résultat de
    course enregistré — même principe que serie_rythme_vie_actif, pour
    superposer les courses sur le tableau de bord croisé."""

    conn = connexion()
    cur = conn.cursor()
    cur.execute("SELECT date FROM resultats_courses WHERE athlete_id=?", (athlete_id,))
    dates_courses = set()
    for (date_texte,) in cur.fetchall():
        d = parser_date_flexible(date_texte)
        if d is not None:
            dates_courses.add(d.date())
    conn.close()

    aujourdhui = datetime.now().date()
    return [
        (aujourdhui - timedelta(days=nb_jours - 1 - i),
         100 if (aujourdhui - timedelta(days=nb_jours - 1 - i)) in dates_courses else 0)
        for i in range(nb_jours)
    ]


def repartition_par_sport(athlete_id, nb_jours=90):
    """Retourne {type_activite: {distance_km, duree_h, charge, nb_seances}}
    sur les nb_jours derniers jours — pour ne pas sous-estimer la charge
    globale quand l'athlète pratique plusieurs sports en complément du
    trail (vélo, natation...)."""

    athlete = _obtenir_athlete(athlete_id)
    conn = connexion()
    cur = conn.cursor()
    cur.execute(
        "SELECT date, type, distance, duree, frequence_cardiaque_moyenne "
        "FROM activites WHERE athlete_id=?",
        (athlete_id,),
    )
    lignes = cur.fetchall()
    conn.close()

    date_min = datetime.now().date() - timedelta(days=nb_jours - 1)
    repartition = {}
    for date_texte, type_, distance, duree, fc_moy in lignes:
        date_obj = parser_date_flexible(date_texte)
        if date_obj is None or date_obj.date() < date_min:
            continue
        type_ = type_ or "Autre"
        activite = {
            "type": type_, "distance": distance,
            "duree": duree, "frequence_cardiaque_moyenne": fc_moy,
        }
        charge, _ = calculer_charge_activite(activite, athlete)

        entree = repartition.setdefault(type_, {"distance_km": 0.0, "duree_h": 0.0, "charge": 0.0, "nb_seances": 0})
        entree["distance_km"] += distance or 0
        entree["duree_h"] += (duree or 0) / 3600
        entree["charge"] += charge
        entree["nb_seances"] += 1

    for entree in repartition.values():
        entree["distance_km"] = round(entree["distance_km"], 1)
        entree["duree_h"] = round(entree["duree_h"], 1)
        entree["charge"] = round(entree["charge"], 1)

    return dict(sorted(repartition.items(), key=lambda kv: -kv[1]["charge"]))


# --------------------------------------------------
# Points d'entrée publics, mis en cache (voir le bloc de cache en
# haut du fichier) — mêmes noms et mêmes signatures qu'avant, tout le
# reste du logiciel continue de les appeler normalement.

def calculer_acwr(athlete_id):
    import time

    maintenant = time.monotonic()
    entree = _cache_acwr.get(athlete_id)
    if entree is not None and (maintenant - entree[0]) < _DUREE_CACHE_SECONDES:
        return entree[1]

    resultat = _calculer_acwr_sans_cache(athlete_id)
    _cache_acwr[athlete_id] = (maintenant, resultat)
    return resultat


def calculer_score_forme_jour(athlete_id, date_reference=None):
    import time

    maintenant = time.monotonic()
    cle = (athlete_id, date_reference)
    entree = _cache_forme_jour.get(cle)
    if entree is not None and (maintenant - entree[0]) < _DUREE_CACHE_SECONDES:
        return entree[1]

    resultat = _calculer_score_forme_jour_sans_cache(athlete_id, date_reference)
    _cache_forme_jour[cle] = (maintenant, resultat)
    return resultat
