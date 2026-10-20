"""
Analyse tactique d'une course à venir (objectif de type "Course") —
TrailMaster Pro.

Combine :
  - les caractéristiques de la course (distance, D+/D-, terrain — saisies
    à la main, ou récupérées au mieux depuis une page web si une URL est
    fournie : best-effort, beaucoup de sites d'inscription sont trop
    dynamiques pour qu'une simple lecture de page fonctionne, donc la
    saisie manuelle reste toujours le chemin fiable) ;
  - le stade d'entraînement de l'athlète au moment de la course : si un
    programme (plan classique ou Programme Ultra long terme) couvre
    cette date, on regarde s'il s'agit du bloc final (objectif) ou d'une
    course de préparation planifiée à ce moment-là, en plus de l'ACWR,
    du score de forme et des records actuels ;
  - ce que l'athlète indique lui-même (objectif principal / course de
    préparation / je ne sais pas), qui prime toujours sur la déduction
    automatique quand il est renseigné.

Comme le reste du moteur de coaching : le diagnostic "à fond" ou "en
réserve" est toujours calculé localement (100% déterministe, pas besoin
d'IA), l'IA (Gemini/Groq) n'ajoute que la tactique de course en langage
naturel — récupération de page web et appel IA sont les deux seules
parties de cette fonctionnalité qui nécessitent internet.
"""

import re
import socket
import urllib.request
import urllib.error
from datetime import datetime, timedelta

from data.database import connexion
from interface.date_utils import parser_date_flexible
from interface.coach import calculer_acwr, calculer_score_forme_jour
from interface.records import calculer_records, calculer_predictions
from interface.rythme_vie import contexte_fatigue_vie
from interface.ia_coach import _appeler_ia, ErreurAnalyseIA


# ------------------------------------------------------------------
# RÉCUPÉRATION (best-effort) DES INFOS D'UNE PAGE DE COURSE
# ------------------------------------------------------------------

def tenter_recuperer_page(url, timeout=8, max_caracteres=4000):
    """Essaie de récupérer le texte visible d'une page de course pour
    laisser l'IA en tirer des infos utiles (profil, ravitos, cut-offs...).
    Best-effort uniquement : beaucoup de sites d'inscription sont des
    applications JavaScript dont le contenu réel n'est pas dans le HTML
    brut — un échec ou un texte vide ne bloque jamais le reste de
    l'analyse, la saisie manuelle des caractéristiques reste toujours le
    chemin fiable. Retourne None si la récupération échoue."""

    if not url or not url.strip():
        return None
    url = url.strip()
    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    try:
        requete = urllib.request.Request(
            url, headers={"User-Agent": "Mozilla/5.0 (TrailMasterPro/1.0)"}
        )
        with urllib.request.urlopen(requete, timeout=timeout) as reponse:
            brut = reponse.read(500_000).decode("utf-8", errors="ignore")
    except (urllib.error.URLError, socket.timeout, ValueError, OSError):
        return None

    # Extraction de texte très simple (pas de vrai parseur HTML pour
    # rester sans dépendance) : retire scripts/styles puis toutes les
    # balises, normalise les espaces.
    texte = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", brut)
    texte = re.sub(r"(?s)<[^>]+>", " ", texte)
    texte = re.sub(r"&nbsp;", " ", texte)
    texte = re.sub(r"\s+", " ", texte).strip()

    if len(texte) < 200:
        # Presque rien d'extrait : probablement une page JS pure —
        # inutile de la transmettre, elle n'apporterait rien.
        return None

    return texte[:max_caracteres]


# ------------------------------------------------------------------
# DIAGNOSTIC LOCAL — stade d'entraînement, à fond ou en réserve
# ------------------------------------------------------------------

def _programme_actif_a_date(athlete_id, date_course):
    """Cherche un plan d'entraînement de l'athlète qui couvre cette
    date, et la séance planifiée (s'il y en a une) la plus proche de
    cette date dans ce plan — sert à détecter si la course correspond à
    l'objectif final d'un Programme Ultra, à une course de préparation
    qui y est déjà planifiée, ou à rien de connu."""

    conn = connexion()
    cur = conn.cursor()
    cur.execute(
        "SELECT id, nom, distance_cible, nb_semaines, date_debut, date_course "
        "FROM plans_entrainement WHERE athlete_id=? ORDER BY date_creation DESC",
        (athlete_id,),
    )
    plans = cur.fetchall()

    for plan_id, nom, distance_cible, nb_semaines, date_debut_txt, date_course_plan_txt in plans:
        date_debut = parser_date_flexible(date_debut_txt)
        if date_debut is None:
            continue
        date_fin = parser_date_flexible(date_course_plan_txt) if date_course_plan_txt else None
        if date_fin is None and nb_semaines:
            date_fin = date_debut + timedelta(weeks=nb_semaines)
        if date_fin is None:
            continue

        if not (date_debut.date() <= date_course <= date_fin.date() + timedelta(days=7)):
            continue

        cur.execute(
            "SELECT nom, type_seance, date_prevue FROM seances_structurees "
            "WHERE plan_id=? AND type_seance='Course de préparation'",
            (plan_id,),
        )
        courses_planifiees = cur.fetchall()
        conn.close()

        plus_proche = None
        plus_proche_ecart = None
        for nom_seance, type_seance, date_prevue_txt in courses_planifiees:
            date_prevue = parser_date_flexible(date_prevue_txt)
            if date_prevue is None:
                continue
            ecart = abs((date_prevue.date() - date_course).days)
            if plus_proche_ecart is None or ecart < plus_proche_ecart:
                plus_proche_ecart = ecart
                plus_proche = nom_seance

        return {
            "plan_nom": nom, "plan_distance_cible": distance_cible,
            "seance_correspondante": plus_proche if plus_proche_ecart is not None and plus_proche_ecart <= 5 else None,
        }

    conn.close()
    return None


def diagnostiquer_course(athlete_id, date_course, intention_utilisateur=None):
    """Retourne {statut_recommande, justification, acwr, forme,
    programme} — statut_recommande ∈ {"a_fond", "en_reserve",
    "a_determiner"}. intention_utilisateur, si fourni par l'athlète
    ("objectif" | "preparation"), prime toujours sur la déduction."""

    acwr = calculer_acwr(athlete_id)
    forme = calculer_score_forme_jour(athlete_id)
    programme = _programme_actif_a_date(athlete_id, date_course)

    if intention_utilisateur == "objectif":
        statut = "a_fond"
        justification = "Tu as indiqué que c'est ton objectif principal."
    elif intention_utilisateur == "preparation":
        statut = "en_reserve"
        justification = "Tu as indiqué que c'est une course de préparation/entraînement."
    elif programme and programme["seance_correspondante"]:
        seance = programme["seance_correspondante"]
        if "OBJECTIF" in seance.upper():
            statut = "a_fond"
            justification = (
                f"Cette date correspond à l'objectif final de ton programme « {programme['plan_nom']} »."
            )
        else:
            statut = "en_reserve"
            justification = (
                f"Cette date correspond à une course de préparation déjà planifiée dans "
                f"« {programme['plan_nom']} » ({seance}) — pas la course objectif elle-même."
            )
    else:
        statut = "a_determiner"
        justification = (
            "Rien ne permet de savoir automatiquement si c'est ta course objectif ou une "
            "préparation — précise-le pour une recommandation plus fiable."
        )

    # Prudence supplémentaire, quel que soit le statut ci-dessus : un
    # ACWR élevé ou une forme très fragile justifient de tempérer même
    # une course objectif plutôt que d'ignorer le signal.
    alerte_charge = None
    if acwr["acwr"] is not None and acwr["acwr"] > 1.5:
        alerte_charge = f"ACWR élevé ({acwr['acwr']}) à l'approche de cette course — risque de blessure accru."
    elif forme["score"] < 35:
        alerte_charge = f"Score de forme bas ({forme['score']}/100) à l'approche de cette course."

    return {
        "statut_recommande": statut,
        "justification": justification,
        "alerte_charge": alerte_charge,
        "acwr": acwr,
        "forme": forme,
        "programme": programme,
    }


# ------------------------------------------------------------------
# CIBLE DE TEMPS / ALLURE (réutilise records.py, distances classiques)
# ------------------------------------------------------------------

def _estimation_temps(athlete_id, distance_km):
    records = calculer_records(athlete_id)
    predictions = calculer_predictions(records)
    # Choix de la distance de référence la plus proche pour une base de
    # comparaison simple (l'IA affine ensuite avec le dénivelé donné).
    from interface.records import DISTANCES_REFERENCE
    plus_proche = min(DISTANCES_REFERENCE, key=lambda d: abs(d[1] - distance_km))
    label = plus_proche[0]
    return records.get(label) or predictions.get(label)


# ------------------------------------------------------------------
# PROMPT IA — tactique de course
# ------------------------------------------------------------------

def _construire_prompt(diagnostic, caracteristiques, extrait_page):
    statut_texte = {
        "a_fond": "à fond (course objectif)",
        "en_reserve": "en réserve, allure contrôlée (course de préparation/entraînement)",
        "a_determiner": "à déterminer — donne ton avis en expliquant le compromis",
    }[diagnostic["statut_recommande"]]

    morceaux = [
        "Tu es un coach de course à pied trail expérimenté, bienveillant mais direct. "
        "Un athlète a une course à venir et demande une tactique de course. Voici ce qu'il a "
        "renseigné sur la course, le diagnostic local (calculé, pas par toi) sur s'il doit la "
        "courir à fond ou en réserve, et son contexte d'entraînement récent (pas de nom ni de "
        "données personnelles). Réponds UNIQUEMENT en français, structuré en 4 parties avec "
        "ces titres exacts :\n\n"
        "### À fond ou en réserve ?\n"
        "### Stratégie pour finir dans de bonnes conditions\n"
        "### Gestion de l'effort et de l'allure\n"
        "### Points d'attention liés à ton entraînement récent\n\n"
        "Dans la 1ère partie, confirme ou nuance le statut recommandé ci-dessous (le "
        "diagnostic local fait déjà foi sauf raison sérieuse de le nuancer) en une ou deux "
        "phrases claires. Dans 'Stratégie', donne un plan concret par phase de course "
        "(démarrage, milieu, fin) adapté au dénivelé/terrain donnés, y compris ravitaillement "
        "et gestion de la chaleur/fatigue si pertinent. Dans 'Gestion de l'effort', propose une "
        "fourchette d'allure ou de FC par phase si les données le permettent. Dans 'Points "
        "d'attention', relie explicitement tes conseils à l'ACWR/la forme/le sommeil/le rythme "
        "de vie fournis — pas de généralités déconnectées des chiffres. Reste concis : 4 à 7 "
        "lignes par partie maximum.\n\n"
        f"Statut recommandé par le diagnostic local : {statut_texte}.\n"
        f"Justification locale : {diagnostic['justification']}\n"
    ]
    if diagnostic["alerte_charge"]:
        morceaux.append(f"Alerte de charge : {diagnostic['alerte_charge']}\n")

    morceaux.append(f"\nCaractéristiques de la course :\n{caracteristiques}\n")

    if extrait_page:
        morceaux.append(
            f"\nExtrait de la page de la course (peut contenir profil, ravitos, cut-offs — "
            f"utilise ce qui est pertinent, ignore le reste) :\n{extrait_page}\n"
        )

    return "".join(morceaux)


def analyser_tactique_course(
    athlete_id, date_course, distance_km, denivele_positif=None, denivele_negatif=None,
    type_terrain=None, notes_course=None, url_course=None, intention_utilisateur=None,
):
    """Retourne (diagnostic, contenu_ia). Lève ErreurAnalyseIA si
    l'appel IA échoue — le diagnostic local, lui, est toujours
    disponible même sans internet."""

    diagnostic = diagnostiquer_course(athlete_id, date_course, intention_utilisateur)

    fatigue_vie = contexte_fatigue_vie(date_course)
    estimation = _estimation_temps(athlete_id, distance_km) if distance_km else None

    morceaux_carac = [f"Distance : {distance_km} km" if distance_km else "Distance : non précisée"]
    if denivele_positif:
        morceaux_carac.append(f"D+ : {denivele_positif} m")
    if denivele_negatif:
        morceaux_carac.append(f"D- : {denivele_negatif} m")
    if type_terrain:
        morceaux_carac.append(f"Terrain : {type_terrain}")
    if notes_course:
        morceaux_carac.append(f"Notes de l'athlète : {notes_course}")
    if estimation:
        cle = "duree_texte"
        if cle in estimation:
            morceaux_carac.append(f"Temps de référence estimé sur une distance proche : {estimation[cle]}")
    if fatigue_vie["texte"]:
        morceaux_carac.append(fatigue_vie["texte"])
    morceaux_carac.append(
        f"ACWR actuel : {diagnostic['acwr']['acwr']} ({diagnostic['acwr']['interpretation']})"
    )
    morceaux_carac.append(
        f"Score de forme du jour : {diagnostic['forme']['score']}/100 ({diagnostic['forme']['interpretation']})"
    )

    caracteristiques = "\n".join(f"- {m}" for m in morceaux_carac)

    extrait_page = tenter_recuperer_page(url_course) if url_course else None

    prompt = _construire_prompt(diagnostic, caracteristiques, extrait_page)
    contenu_ia = _appeler_ia(prompt)

    return diagnostic, contenu_ia


# ------------------------------------------------------------------
# PERSISTANCE
# ------------------------------------------------------------------

def enregistrer_analyse_course(
    objectif_id, athlete_id, distance_km, denivele_positif, denivele_negatif,
    type_terrain, url_course, notes_course, diagnostic, contenu_ia,
):
    conn = connexion()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO analyses_course (
            objectif_id, athlete_id, date_generation, distance_km, denivele_positif,
            denivele_negatif, type_terrain, url_course, notes_course, recommandation,
            diagnostic_local, contenu_ia
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            objectif_id, athlete_id, datetime.now().isoformat(timespec="seconds"),
            distance_km, denivele_positif, denivele_negatif, type_terrain, url_course,
            notes_course, diagnostic["statut_recommande"], diagnostic["justification"], contenu_ia,
        ),
    )
    conn.commit()
    conn.close()


def derniere_analyse_course(objectif_id):
    conn = connexion()
    cur = conn.cursor()
    cur.execute(
        "SELECT distance_km, denivele_positif, denivele_negatif, type_terrain, url_course, "
        "notes_course, recommandation, diagnostic_local, contenu_ia, date_generation "
        "FROM analyses_course WHERE objectif_id=? ORDER BY date_generation DESC LIMIT 1",
        (objectif_id,),
    )
    ligne = cur.fetchone()
    conn.close()
    return ligne
