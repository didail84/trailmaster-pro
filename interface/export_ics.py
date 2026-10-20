"""
Export calendrier (.ics) des séances planifiées — permet de consulter
les prochaines séances depuis n'importe quel calendrier (téléphone,
Google/Apple Calendar...) sans construire d'application mobile dédiée.

100% local : aucun appel réseau, juste la génération d'un fichier texte
au format iCalendar (RFC 5545) standard, importable partout.
"""

import json
import uuid
from datetime import datetime, timedelta

from data.database import connexion, obtenir_parametre, definir_parametre
from interface.conformite import duree_totale_prevue_min


CLE_PARAMETRE_HEURE_DEBUT = "export_ics_heure_debut"
CLE_PARAMETRE_DUREE_DEFAUT = "export_ics_duree_defaut_min"
HEURE_DEBUT_PAR_DEFAUT = "07:00"
DUREE_DEFAUT_PAR_DEFAUT_MIN = 45


def obtenir_heure_debut_defaut():
    valeur = obtenir_parametre(CLE_PARAMETRE_HEURE_DEBUT)
    if valeur and ":" in valeur:
        try:
            h, m = valeur.split(":")
            return int(h), int(m)
        except ValueError:
            pass
    h, m = HEURE_DEBUT_PAR_DEFAUT.split(":")
    return int(h), int(m)


def definir_heure_debut_defaut(heure_texte):
    definir_parametre(CLE_PARAMETRE_HEURE_DEBUT, heure_texte)


def obtenir_duree_defaut_min():
    valeur = obtenir_parametre(CLE_PARAMETRE_DUREE_DEFAUT)
    try:
        return int(valeur) if valeur else DUREE_DEFAUT_PAR_DEFAUT_MIN
    except (TypeError, ValueError):
        return DUREE_DEFAUT_PAR_DEFAUT_MIN


def definir_duree_defaut_min(minutes):
    definir_parametre(CLE_PARAMETRE_DUREE_DEFAUT, minutes)


def _echapper_ics(texte):
    """Échappe les caractères spéciaux du format iCalendar (virgules,
    points-virgules, retours à la ligne)."""
    if not texte:
        return ""
    return (
        str(texte)
        .replace("\\", "\\\\")
        .replace(",", "\\,")
        .replace(";", "\\;")
        .replace("\n", "\\n")
    )


def generer_ics(athlete_id, plan_id=None, seulement_a_venir=True):
    """Retourne le contenu texte d'un fichier .ics pour les séances
    structurées de l'athlète (toutes, ou d'un seul plan si plan_id est
    précisé). Chaque séance devient un évènement d'une durée estimée
    (à partir de ses étapes prévues, 45 min par défaut si inconnue),
    démarrant à 7h00 le jour prévu (horaire neutre, éditable une fois
    importé dans le calendrier de destination)."""

    conn = connexion()
    cur = conn.cursor()

    requete = (
        "SELECT id, nom, type_seance, date_prevue, statut, etapes_json, notes "
        "FROM seances_structurees WHERE athlete_id=?"
    )
    params = [athlete_id]
    if plan_id is not None:
        requete += " AND plan_id=?"
        params.append(plan_id)
    if seulement_a_venir:
        requete += " AND statut='Prévue'"
    requete += " ORDER BY date_prevue ASC"

    cur.execute(requete, params)
    lignes = cur.fetchall()
    conn.close()

    maintenant = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")

    corps = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//TrailMaster Pro//Export séances//FR",
        "CALSCALE:GREGORIAN",
    ]

    for id_, nom, type_seance, date_prevue, statut, etapes_json, notes in lignes:
        if not date_prevue:
            continue
        try:
            jour = datetime.strptime(date_prevue[:10], "%Y-%m-%d")
        except ValueError:
            continue

        heure_h, heure_m = obtenir_heure_debut_defaut()
        debut = jour.replace(hour=heure_h, minute=heure_m, second=0)

        duree_min = obtenir_duree_defaut_min()
        if etapes_json:
            try:
                etapes = json.loads(etapes_json)
                duree_calculee = duree_totale_prevue_min(etapes)
                if duree_calculee:
                    duree_min = duree_calculee
            except (ValueError, TypeError):
                pass

        fin = debut + timedelta(minutes=max(duree_min, 15))

        description = type_seance or ""
        if notes:
            description += f" — {notes}"

        corps.extend([
            "BEGIN:VEVENT",
            f"UID:trailmaster-seance-{id_}-{uuid.uuid4().hex[:8]}@trailmaster.local",
            f"DTSTAMP:{maintenant}",
            f"DTSTART:{debut.strftime('%Y%m%dT%H%M%S')}",
            f"DTEND:{fin.strftime('%Y%m%dT%H%M%S')}",
            f"SUMMARY:{_echapper_ics(nom)}",
            f"DESCRIPTION:{_echapper_ics(description)}",
            "END:VEVENT",
        ])

    corps.append("END:VCALENDAR")

    # RFC 5545 impose des retours à la ligne CRLF.
    return "\r\n".join(corps) + "\r\n"
