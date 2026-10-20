"""
Analyse de dates dans différents formats, y compris le format français
avec abréviations de mois (ex. "9 sept. 2022, 03:58:44"), tel
qu'exporté par certaines versions localisées de Garmin Connect.

Utilisé à la fois par l'import CSV (normalisation à l'enregistrement)
et par le moteur de coaching (lecture défensive des dates déjà en
base, dont certaines n'ont pas été normalisées correctement par le
passé).
"""

import re
from datetime import datetime

MOIS_FR = {
    "janv": 1, "jan": 1,
    "févr": 2, "fevr": 2, "fév": 2, "fev": 2,
    "mars": 3,
    "avr": 4,
    "mai": 5,
    "juin": 6,
    "juil": 7,
    "août": 8, "aout": 8,
    "sept": 9, "sep": 9,
    "oct": 10,
    "nov": 11,
    "déc": 12, "dec": 12,
}

MOIS_EN = {
    "jan": 1, "january": 1,
    "feb": 2, "february": 2,
    "mar": 3, "march": 3,
    "apr": 4, "april": 4,
    "may": 5,
    "jun": 6, "june": 6,
    "jul": 7, "july": 7,
    "aug": 8, "august": 8,
    "sep": 9, "sept": 9, "september": 9,
    "oct": 10, "october": 10,
    "nov": 11, "november": 11,
    "dec": 12, "december": 12,
}

FORMATS_NUMERIQUES = [
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%Y-%m-%d",
    "%d/%m/%Y %H:%M:%S",
    "%d/%m/%Y %H:%M",
    "%d/%m/%Y",
    "%m/%d/%Y %H:%M:%S",
    "%m/%d/%Y %H:%M",
    "%m/%d/%Y",
]

# Reconnaît par ex. "9 sept. 2022, 03:58:44" ou "9 sept. 2022 03:58"
_RE_DATE_FR = re.compile(
    r"^(\d{1,2})\s+([a-zA-Zéûôàè\.]+)\s+(\d{4})(?:,)?(?:\s+(\d{1,2}):(\d{2})(?::(\d{2}))?)?$"
)

# Reconnaît le format anglais réel exporté par Strava, ex.
# "Sep 10, 2026, 7:30:00 AM" ou "Sep 10 2026 07:30:00" (sans AM/PM)
_RE_DATE_EN = re.compile(
    r"^([a-zA-Z]+)\s+(\d{1,2}),?\s+(\d{4})(?:,)?"
    r"(?:\s+(\d{1,2}):(\d{2})(?::(\d{2}))?\s*([AaPp][Mm])?)?$"
)


def parser_date_flexible(valeur):
    """Retourne un datetime.datetime, ou None si le format n'est pas reconnu."""

    if not valeur:
        return None

    texte = str(valeur).strip()

    for format_date in FORMATS_NUMERIQUES:
        try:
            return datetime.strptime(texte, format_date)
        except ValueError:
            continue

    correspondance = _RE_DATE_FR.match(texte)
    if correspondance:
        jour, mois_texte, annee, heure, minute, seconde = correspondance.groups()
        cle_mois = mois_texte.lower().rstrip(".")
        mois = MOIS_FR.get(cle_mois)
        if mois:
            try:
                return datetime(
                    int(annee), mois, int(jour),
                    int(heure or 0), int(minute or 0), int(seconde or 0),
                )
            except ValueError:
                return None

    correspondance = _RE_DATE_EN.match(texte)
    if correspondance:
        mois_texte, jour, annee, heure, minute, seconde, ampm = correspondance.groups()
        mois = MOIS_EN.get(mois_texte.lower().rstrip("."))
        if mois:
            heure_int = int(heure or 0)
            if ampm:
                ampm = ampm.lower()
                if ampm == "pm" and heure_int != 12:
                    heure_int += 12
                elif ampm == "am" and heure_int == 12:
                    heure_int = 0
            try:
                return datetime(
                    int(annee), mois, int(jour),
                    heure_int, int(minute or 0), int(seconde or 0),
                )
            except ValueError:
                return None

    return None


def normaliser_vers_iso(valeur):
    """Convertit une date reconnue (quel que soit son format d'origine)
    vers le format ISO utilisé pour le stockage en base."""

    date = parser_date_flexible(valeur)
    if date is None:
        return str(valeur).strip() if valeur else ""
    return date.strftime("%Y-%m-%d %H:%M:%S")
