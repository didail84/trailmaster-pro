"""
Rythme de vie hebdomadaire de l'athlète (lever, trajets, horaires de
travail) — un facteur de fatigue "hors entraînement" que les données de
sortie ou de sommeil ne capturent pas forcément (lever très tôt, longue
journée, trajets), mais qui pèse quand même sur la récupération réelle.

Renseigné une fois dans Réglages (rythme partagé, pas par athlète — comme
la configuration du tableau de bord), ce rythme est ensuite :
  - intégré comme une composante légère du score de forme du jour
    (interface/coach.py) les jours de semaine où la journée est longue ;
  - transmis en texte à l'IA (Gemini/Groq) dans ses prompts d'analyse,
    pour qu'elle en tienne compte dans ses commentaires ;
  - rappelé dans le diagnostic local de la replanification automatique.

100% local, aucune dépendance réseau, aucune nouvelle table : stocké
comme les autres réglages dans parametres_app.
"""

import json
from datetime import datetime

from data.database import obtenir_parametre, definir_parametre, connexion


CLE_PARAMETRE = "rythme_vie_semaine"

# Amplitude "lever -> retour à la maison" à partir de laquelle une
# journée de semaine est considérée comme longue. Seuil simple et
# approximatif (pas une donnée scientifique), utilisé uniquement pour
# déclencher un léger facteur de vigilance supplémentaire. Réglable
# depuis Réglages (Alertes et objectifs) ; 12h par défaut.
SEUIL_JOURNEE_LONGUE_MIN_DEFAUT = 12 * 60
CLE_PARAMETRE_SEUIL_JOURNEE_LONGUE = "seuil_journee_longue_min"


def obtenir_seuil_journee_longue_min():
    valeur = obtenir_parametre(CLE_PARAMETRE_SEUIL_JOURNEE_LONGUE)
    try:
        return int(valeur) if valeur else SEUIL_JOURNEE_LONGUE_MIN_DEFAUT
    except (TypeError, ValueError):
        return SEUIL_JOURNEE_LONGUE_MIN_DEFAUT


def definir_seuil_journee_longue_min(minutes):
    definir_parametre(CLE_PARAMETRE_SEUIL_JOURNEE_LONGUE, minutes)

CHAMPS = ["lever", "depart_domicile", "duree_trajet_min", "depart_travail", "arrivee_domicile"]


def obtenir_rythme_vie():
    """Retourne le dict enregistré (heures au format 'HH:MM', sauf
    duree_trajet_min en minutes) ou None si rien n'a encore été
    renseigné dans Réglages."""

    brut = obtenir_parametre(CLE_PARAMETRE)
    if not brut:
        return None
    try:
        rythme = json.loads(brut)
    except (TypeError, ValueError):
        return None
    return rythme if any(rythme.get(c) for c in CHAMPS) else None


def definir_rythme_vie(rythme):
    definir_parametre(CLE_PARAMETRE, json.dumps(rythme))


def _minutes(heure_texte):
    if not heure_texte:
        return None
    try:
        h, m = str(heure_texte).split(":")
        return int(h) * 60 + int(m)
    except (ValueError, AttributeError):
        return None


def amplitude_journee_minutes(rythme):
    """Minutes entre le lever et le retour à la maison le soir. None si
    l'un des deux horaires n'est pas renseigné."""

    debut = _minutes(rythme.get("lever"))
    fin = _minutes(rythme.get("arrivee_domicile"))
    if debut is None or fin is None:
        return None
    if fin < debut:
        fin += 24 * 60  # cas extrême d'un retour après minuit
    return fin - debut


def jour_est_ouvre(date_reference):
    return date_reference.weekday() < 5  # lundi=0 ... vendredi=4


# ------------------------------------------------------------------
# PÉRIODES EXCEPTIONNELLES — déplacement pro, astreinte... déclarables
# ponctuellement (table rythme_vie_exceptions) sans reconfigurer tout
# le rythme hebdomadaire habituel ci-dessus. Contrairement au rythme
# habituel, une période exceptionnelle s'applique aussi le week-end :
# une astreinte ou un déplacement fatigue un samedi comme un mardi.
# ------------------------------------------------------------------

def obtenir_exceptions_rythme_vie():
    conn = connexion()
    cur = conn.cursor()
    cur.execute(
        "SELECT id, date_debut, date_fin, motif, niveau FROM rythme_vie_exceptions "
        "ORDER BY date_debut DESC"
    )
    lignes = cur.fetchall()
    conn.close()
    return lignes


def ajouter_exception_rythme_vie(date_debut, date_fin, motif, niveau="Journée longue"):
    conn = connexion()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO rythme_vie_exceptions (date_debut, date_fin, motif, niveau) VALUES (?, ?, ?, ?)",
        (date_debut, date_fin, motif, niveau),
    )
    conn.commit()
    conn.close()


def supprimer_exception_rythme_vie(exception_id):
    conn = connexion()
    cur = conn.cursor()
    cur.execute("DELETE FROM rythme_vie_exceptions WHERE id=?", (exception_id,))
    conn.commit()
    conn.close()


def _exception_active(date_reference):
    """Retourne la ligne d'exception (motif, niveau) couvrant
    date_reference, ou None."""

    for _id, date_debut, date_fin, motif, niveau in obtenir_exceptions_rythme_vie():
        try:
            debut = datetime.strptime(date_debut[:10], "%Y-%m-%d").date()
            fin = datetime.strptime(date_fin[:10], "%Y-%m-%d").date()
        except (ValueError, TypeError):
            continue
        if debut <= date_reference <= fin:
            return {"motif": motif, "niveau": niveau}
    return None


def contexte_fatigue_vie(date_reference=None):
    """Décrit l'impact du rythme de vie sur le jour donné (aujourd'hui
    par défaut) :
      - configure : un rythme a été renseigné dans Réglages
      - jour_ouvre : le jour donné est un jour de semaine
      - amplitude_min / amplitude_texte : durée lever -> retour maison
      - journee_longue : amplitude >= SEUIL_JOURNEE_LONGUE_MIN
      - actif : jour_ouvre ET journee_longue ET configure — c'est ce
        drapeau qui déclenche le léger malus dans le score de forme et
        la mention dans le diagnostic de replanification.
      - texte : phrase descriptive, réutilisée telle quelle dans les
        prompts envoyés à l'IA."""

    date_reference = date_reference or datetime.now().date()
    rythme = obtenir_rythme_vie()

    resultat = {
        "configure": rythme is not None,
        "jour_ouvre": jour_est_ouvre(date_reference),
        "amplitude_min": None,
        "amplitude_texte": None,
        "journee_longue": False,
        "actif": False,
        "texte": None,
        "exception": None,
    }

    exception = _exception_active(date_reference)
    if exception:
        # Une période exceptionnelle s'applique tous les jours (y
        # compris le week-end) et prend le pas sur le rythme habituel :
        # pas besoin d'un rythme hebdomadaire configuré pour déclencher
        # le malus de fatigue le temps de cette période.
        resultat["exception"] = exception
        resultat["actif"] = True
        resultat["texte"] = (
            f"Période exceptionnelle en cours ({exception['motif'] or 'sans motif précisé'}) : "
            f"fatigue supplémentaire ({exception['niveau']}) à prendre en compte dans le "
            "diagnostic et les conseils, y compris le week-end."
        )
        return resultat

    if not rythme:
        return resultat

    amplitude = amplitude_journee_minutes(rythme)
    resultat["amplitude_min"] = amplitude
    if amplitude is not None:
        h, m = divmod(amplitude, 60)
        resultat["amplitude_texte"] = f"{h}h{m:02d}" if m else f"{h}h"
        resultat["journee_longue"] = amplitude >= obtenir_seuil_journee_longue_min()

    resultat["actif"] = resultat["jour_ouvre"] and resultat["journee_longue"]

    morceaux = []
    if rythme.get("lever"):
        morceaux.append(f"lever à {rythme['lever']}")
    if rythme.get("depart_domicile"):
        depart = f"départ de la maison à {rythme['depart_domicile']}"
        if rythme.get("duree_trajet_min"):
            depart += f" ({rythme['duree_trajet_min']} min de trajet)"
        morceaux.append(depart)
    if rythme.get("depart_travail") or rythme.get("arrivee_domicile"):
        retour = "retour"
        if rythme.get("depart_travail"):
            retour += f" — départ du travail vers {rythme['depart_travail']}"
        if rythme.get("arrivee_domicile"):
            retour += f", arrivée à la maison vers {rythme['arrivee_domicile']}"
        morceaux.append(retour)

    if morceaux:
        texte = "Rythme de vie en semaine : " + ", ".join(morceaux) + "."
        if resultat["amplitude_texte"]:
            texte += f" Amplitude de la journée (lever → retour) : environ {resultat['amplitude_texte']}."
        texte += (
            " Ce rythme (jours ouvrés uniquement) représente une source de fatigue en dehors "
            "de l'entraînement à prendre en compte dans le diagnostic et les conseils."
        )
        resultat["texte"] = texte

    return resultat
