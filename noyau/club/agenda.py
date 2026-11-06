"""
Règles de l'agenda du club (étape 4.2) : vacances scolaires et jours
fériés, dates d'une série hebdomadaire, bilan d'un appel, assiduité des
adhérents, export de l'agenda au format iCalendar (.ics, lu par les
téléphones). Aucune base ici : noyau/donnees/agenda_club.py lit et écrit.
"""

from datetime import date, datetime, timedelta, timezone
import re

TYPES = (("entrainement", "Entraînement"), ("sortie", "Sortie longue / trail"), ("competition", "Compétition"),
         ("stage", "Stage"), ("reunion", "Réunion"), ("autre", "Autre"))
LIBELLE_TYPE = dict(TYPES)
STATUTS_PRESENCE = (("present", "Présent"), ("retard", "En retard"), ("excuse", "Excusé"), ("absent", "Absent"))
LIBELLE_PRESENCE = dict(STATUTS_PRESENCE)
COMPTE_PRESENT = ("present", "retard")
JOURS = ("lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche")
ZONES = ("A", "B", "C")
ABSENCES_DECROCHAGE = 3          # absences non excusées de suite avant de prévenir l'entraîneur

# Vacances scolaires officielles (ministère de l'Éducation nationale) : (nom, premier jour sans cours,
# jour de reprise). Les vacances vont du samedi indiqué jusqu'à la veille de la reprise.
VACANCES = {
    "2025-2026": {
        "A": (("Toussaint", "2025-10-18", "2025-11-03"), ("Noël", "2025-12-20", "2026-01-05"),
              ("Hiver", "2026-02-07", "2026-02-23"), ("Printemps", "2026-04-04", "2026-04-20"),
              ("Été", "2026-07-04", "2026-09-01")),
        "B": (("Toussaint", "2025-10-18", "2025-11-03"), ("Noël", "2025-12-20", "2026-01-05"),
              ("Hiver", "2026-02-14", "2026-03-02"), ("Printemps", "2026-04-11", "2026-04-27"),
              ("Été", "2026-07-04", "2026-09-01")),
        "C": (("Toussaint", "2025-10-18", "2025-11-03"), ("Noël", "2025-12-20", "2026-01-05"),
              ("Hiver", "2026-02-21", "2026-03-09"), ("Printemps", "2026-04-18", "2026-05-04"),
              ("Été", "2026-07-04", "2026-09-01")),
    },
    "2026-2027": {
        "A": (("Toussaint", "2026-10-17", "2026-11-02"), ("Noël", "2026-12-19", "2027-01-04"),
              ("Hiver", "2027-02-13", "2027-03-01"), ("Printemps", "2027-04-10", "2027-04-26"),
              ("Été", "2027-07-03", "2027-09-01")),
        "B": (("Toussaint", "2026-10-17", "2026-11-02"), ("Noël", "2026-12-19", "2027-01-04"),
              ("Hiver", "2027-02-20", "2027-03-08"), ("Printemps", "2027-04-17", "2027-05-03"),
              ("Été", "2027-07-03", "2027-09-01")),
        "C": (("Toussaint", "2026-10-17", "2026-11-02"), ("Noël", "2026-12-19", "2027-01-04"),
              ("Hiver", "2027-02-06", "2027-02-22"), ("Printemps", "2027-04-03", "2027-04-19"),
              ("Été", "2027-07-03", "2027-09-01")),
    },
}
# la rentrée 2027 n'est pas encore publiée : fin de l'été 2027 estimée au 1er septembre
ESTIMATIONS = {("2026-2027", "Été")}
PONTS = (("Pont de l'Ascension", "2026-05-15"), ("Pont de l'Ascension", "2027-05-07"))
NOM_VACANCES = {"Toussaint": "vacances de la Toussaint", "Noël": "vacances de Noël", "Hiver": "vacances d'hiver",
                "Printemps": "vacances de printemps", "Été": "vacances d'été"}
ZONE_PAR_ACADEMIE = {
    "A": ("Besançon", "Bordeaux", "Clermont-Ferrand", "Dijon", "Grenoble", "Limoges", "Lyon", "Poitiers"),
    "B": ("Aix-Marseille", "Amiens", "Lille", "Nancy-Metz", "Nantes", "Nice", "Normandie", "Orléans-Tours", "Reims",
          "Rennes", "Strasbourg"),
    "C": ("Créteil", "Montpellier", "Paris", "Toulouse", "Versailles"),
}


class ErreurAgenda(Exception):
    """Message lisible ; rien n'a été modifié."""


def _jour(d):
    if isinstance(d, datetime):
        return d.date()
    if isinstance(d, date):
        return d
    return date.fromisoformat(str(d)[:10])


def paques(annee):
    """Dimanche de Pâques (algorithme de Meeus pour le calendrier grégorien)."""
    a, b, c = annee % 19, annee // 100, annee % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    mois = (h + l - 7 * m + 114) // 31
    jour = (h + l - 7 * m + 114) % 31 + 1
    return date(annee, mois, jour)


def jours_feries(annee):
    """{date: nom} des onze jours fériés de métropole."""
    p = paques(annee)
    return {date(annee, 1, 1): "Jour de l'an", p + timedelta(days=1): "Lundi de Pâques", date(annee, 5, 1): "Fête du Travail",
            date(annee, 5, 8): "Victoire 1945", p + timedelta(days=39): "Ascension",
            p + timedelta(days=50): "Lundi de Pentecôte", date(annee, 7, 14): "Fête nationale",
            date(annee, 8, 15): "Assomption", date(annee, 11, 1): "Toussaint", date(annee, 11, 11): "Armistice 1918",
            date(annee, 12, 25): "Noël"}


def ferie(jour):
    j = _jour(jour)
    return jours_feries(j.year).get(j)


def vacances_de(saison, zone="B"):
    """[(nom, premier jour, dernier jour, estimé ?)] ; [] si le calendrier de la saison n'est pas connu."""
    res = []
    for nom, debut, reprise in VACANCES.get(saison, {}).get(zone or "B", ()):
        res.append((nom, date.fromisoformat(debut), date.fromisoformat(reprise) - timedelta(days=1),
                    (saison, nom) in ESTIMATIONS))
    return res


def calendrier_connu(saison):
    return saison in VACANCES


def en_vacances(jour, zone="B"):
    """Nom des vacances scolaires (ou du pont) qui couvrent ce jour, sinon None."""
    j = _jour(jour)
    for s in VACANCES:
        for nom, debut, fin, _est in vacances_de(s, zone):
            if debut <= j <= fin:
                return NOM_VACANCES.get(nom, f"vacances de {nom}")
    for nom, d in PONTS:
        if j == date.fromisoformat(d):
            return nom.lower()
    return None


def verifier_heure(h):
    """« 18:30 » ; accepte 18h30, 18h, 18.30. None si vide. ErreurAgenda si illisible."""
    if h is None or not str(h).strip():
        return None
    m = re.fullmatch(r"\s*(\d{1,2})\s*(?:[:hH.]\s*(\d{2})?)?\s*", str(h))
    if not m or int(m.group(1)) > 23 or (m.group(2) and int(m.group(2)) > 59):
        raise ErreurAgenda(f"Heure illisible : {h} (écris par exemple 18:30).")
    return f"{int(m.group(1)):02d}:{m.group(2) or '00'}"


def dates_serie(jour_semaine, debut, fin, zone="B", sauf_vacances=False, sauf_feries=True):
    """Les dates d'une série hebdomadaire (jour_semaine : 0 = lundi). Renvoie (dates, écartées) avec
    écartées = [(date, raison)]."""
    d0, d1 = _jour(debut), _jour(fin)
    if d1 < d0:
        raise ErreurAgenda("La date de fin est avant la date de début.")
    if not 0 <= int(jour_semaine) <= 6:
        raise ErreurAgenda("Jour de la semaine inconnu.")
    if (d1 - d0).days > 400:
        raise ErreurAgenda("Une série dure au plus une saison (un peu plus d'un an).")
    j = d0 + timedelta(days=(int(jour_semaine) - d0.weekday()) % 7)
    dates, ecartees = [], []
    while j <= d1:
        f = ferie(j) if sauf_feries else None
        v = en_vacances(j, zone) if sauf_vacances else None
        if f:
            ecartees.append((j, f"férié : {f}"))
        elif v:
            ecartees.append((j, v))
        else:
            dates.append(j)
        j += timedelta(days=7)
    return dates, ecartees


# ------------------------------------------------------------------ présences

def bilan_appel(statuts, attendus=None):
    """statuts : {personne_id: statut} ; attendus : ids des membres attendus (le groupe).
    Renvoie {present, retard, excuse, absent, non_pointes, effectif, taux} ; taux = présents (retards
    compris) sur les personnes pointées, en %."""
    compte = {k: 0 for k, _l in STATUTS_PRESENCE}
    for s in statuts.values():
        if s in compte:
            compte[s] += 1
    pointes = sum(compte.values())
    non = len(set(attendus or ()) - set(statuts)) if attendus is not None else 0
    presents = compte["present"] + compte["retard"]
    return {**compte, "non_pointes": non, "effectif": presents,
            "taux": round(100 * presents / pointes) if pointes else None}


def assiduite(lignes):
    """lignes : [(personne_id, date, statut)] des séances où la personne était attendue ou pointée,
    triées par date. Renvoie {personne_id: {seances, presents, retards, excuses, absents, taux,
    absences_de_suite, derniere_presence}} ; taux = (présents + retards) / (séances - excusées)."""
    res = {}
    for pid, jour, statut in sorted(lignes, key=lambda x: (x[0], str(x[1]))):
        r = res.setdefault(pid, {"seances": 0, "presents": 0, "retards": 0, "excuses": 0, "absents": 0,
                                 "non_pointes": 0, "absences_de_suite": 0, "derniere_presence": None})
        r["seances"] += 1
        if statut in COMPTE_PRESENT:
            r["presents" if statut == "present" else "retards"] += 1
            r["absences_de_suite"] = 0
            r["derniere_presence"] = str(jour)[:10]
        elif statut == "excuse":
            r["excuses"] += 1
        elif statut == "absent":
            r["absents"] += 1
            r["absences_de_suite"] += 1
        else:
            r["non_pointes"] += 1
    for r in res.values():
        base = r["seances"] - r["excuses"] - r["non_pointes"]
        r["taux"] = round(100 * (r["presents"] + r["retards"]) / base) if base > 0 else None
    return res


def alertes_presences(assid, noms, seances_sans_appel=0):
    """Phrases pour l'entraîneur : décrochages (absences non excusées de suite) et appels oubliés."""
    res = []
    decroche = sorted((noms.get(pid, "?") for pid, r in assid.items() if r["absences_de_suite"] >= ABSENCES_DECROCHAGE))
    if decroche:
        res.append(f"{', '.join(decroche[:6])}{'…' if len(decroche) > 6 else ''} : {ABSENCES_DECROCHAGE} absences "
                   "ou plus de suite, sans excuse. Un petit message ?")
    if seances_sans_appel:
        res.append(f"{seances_sans_appel} séance{'s' if seances_sans_appel > 1 else ''} passée"
                   f"{'s' if seances_sans_appel > 1 else ''} sans appel.")
    return res


# ------------------------------------------------------------------ export iCalendar

def _ics_texte(t):
    return (str(t or "").replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n"))


def _plier(ligne):
    """Lignes de 75 octets au plus (norme RFC 5545)."""
    out, b = [], ligne.encode("utf-8")
    while len(b) > 75:
        coupe = 75
        while (b[coupe] & 0xC0) == 0x80:      # ne pas couper un caractère accentué
            coupe -= 1
        out.append(b[:coupe].decode("utf-8"))
        b = b" " + b[coupe:]
    out.append(b.decode("utf-8"))
    return "\r\n".join(out)


def ics(seances, nom_club="Club", maintenant=None):
    """Texte .ics des séances (dict : uuid ou id, titre, date, heure_debut, heure_fin, lieu, type, groupe,
    entraineur, contenu, annulee). Heures locales (fuseau de Paris)."""
    stamp = (maintenant or datetime.now(timezone.utc)).strftime("%Y%m%dT%H%M%SZ")
    l = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Trail Hub Center//Agenda du club//FR", "CALSCALE:GREGORIAN",
         f"X-WR-CALNAME:{_ics_texte(nom_club)}", "X-WR-TIMEZONE:Europe/Paris",
         "BEGIN:VTIMEZONE", "TZID:Europe/Paris",
         "BEGIN:DAYLIGHT", "TZOFFSETFROM:+0100", "TZOFFSETTO:+0200", "TZNAME:CEST", "DTSTART:19700329T020000",
         "RRULE:FREQ=YEARLY;BYMONTH=3;BYDAY=-1SU", "END:DAYLIGHT",
         "BEGIN:STANDARD", "TZOFFSETFROM:+0200", "TZOFFSETTO:+0100", "TZNAME:CET", "DTSTART:19701025T030000",
         "RRULE:FREQ=YEARLY;BYMONTH=10;BYDAY=-1SU", "END:STANDARD", "END:VTIMEZONE"]
    for s in seances:
        j = _jour(s["date"]).strftime("%Y%m%d")
        l.append("BEGIN:VEVENT")
        l.append(f"UID:{s.get('uuid') or s['id']}@trailhubcenter")
        l.append(f"DTSTAMP:{stamp}")
        if s.get("heure_debut"):
            hd = s["heure_debut"].replace(":", "")
            hf = (s.get("heure_fin") or "").replace(":", "")
            if not hf:
                h, m = int(hd[:2]), int(hd[2:])
                hf = f"{min(23, h + 1):02d}{m:02d}"
            l.append(f"DTSTART;TZID=Europe/Paris:{j}T{hd}00")
            l.append(f"DTEND;TZID=Europe/Paris:{j}T{hf}00")
        else:
            l.append(f"DTSTART;VALUE=DATE:{j}")
            l.append(f"DTEND;VALUE=DATE:{(_jour(s['date']) + timedelta(days=1)).strftime('%Y%m%d')}")
        titre = s["titre"] + (f" ({s['groupe']})" if s.get("groupe") and s["groupe"] not in s["titre"] else "")
        l.append("SUMMARY:" + _ics_texte(("ANNULÉ — " if s.get("annulee") else "") + titre))
        if s.get("lieu"):
            l.append("LOCATION:" + _ics_texte(s["lieu"]))
        desc = [LIBELLE_TYPE.get(s.get("type"), "")]
        if s.get("entraineur"):
            desc.append(f"Entraîneur : {s['entraineur']}")
        if s.get("contenu"):
            desc.append(s["contenu"])
        if s.get("annulee") and s.get("motif_annulation"):
            desc.append(f"Annulée : {s['motif_annulation']}")
        l.append("DESCRIPTION:" + _ics_texte("\n".join(x for x in desc if x)))
        if s.get("annulee"):
            l.append("STATUS:CANCELLED")
        l.append("END:VEVENT")
    l.append("END:VCALENDAR")
    return "\r\n".join(_plier(x) for x in l) + "\r\n"
