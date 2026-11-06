"""
Règles du calendrier des courses (sans base ni Qt) : disciplines de la FFA,
régions et départements, lecture d'un flux iCalendar (.ics), d'un tableau
collé depuis une page de calendrier (FFA, Betrail…) ou d'un fichier CSV,
reconnaissance des doublons et liens pour ouvrir les calendriers en ligne.

Le logiciel ne lit tout seul que les adresses que tu lui donnes (flux .ics
publiés par des organisateurs, comités ou ligues) : les sites de
calendriers qui interdisent la lecture automatique sont ouverts dans ton
navigateur, et tu colles le tableau.
"""

import csv
import io
import re
import unicodedata
from datetime import date, datetime, timedelta
from urllib.parse import quote_plus

DISCIPLINES = (("stade", "Stade (piste)"), ("cross", "Cross-country"), ("route", "Route (hors stade)"),
               ("trail_decouverte", "Trail découverte"), ("trail_court", "Trail court"), ("trail_long", "Trail long"),
               ("ultra_trail", "Ultra-trail"), ("montagne", "Course en montagne"), ("kv", "Kilomètre vertical"),
               ("marche_nordique", "Marche nordique"), ("course_nature", "Course nature"), ("relais", "Relais, ekiden"),
               ("autre", "Autre"))
LIBELLE_DISCIPLINE = dict(DISCIPLINES)
FAMILLE = {"stade": "Stade", "cross": "Hors stade", "route": "Hors stade", "trail_decouverte": "Trail",
           "trail_court": "Trail", "trail_long": "Trail", "ultra_trail": "Trail", "montagne": "Montagne", "kv": "Montagne",
           "marche_nordique": "Marche nordique", "course_nature": "Trail", "relais": "Hors stade", "autre": "Autre"}
FAMILLES = ("Stade", "Hors stade", "Trail", "Montagne", "Marche nordique", "Autre")
NIVEAUX = (("international", "International"), ("national", "National"), ("regional", "Régional"),
           ("departemental", "Départemental"), ("championnat_france", "Championnat de France"),
           ("championnat_regional", "Championnat régional"), ("label", "Course à label FFA"), ("loisir", "Loisir, non classant"))
LIBELLE_NIVEAU = dict(NIVEAUX)
STATUTS = (("prevue", "Prévue"), ("annulee", "Annulée"), ("reportee", "Reportée"))
REGIONS = {
    "Provence-Alpes-Côte d'Azur": ("04", "05", "06", "13", "83", "84"),
    "Occitanie": ("09", "11", "12", "30", "31", "32", "34", "46", "48", "65", "66", "81", "82"),
    "Auvergne-Rhône-Alpes": ("01", "03", "07", "15", "26", "38", "42", "43", "63", "69", "73", "74"),
}
REGION_DU_DEPARTEMENT = {d: r for r, ds in REGIONS.items() for d in ds}
NOMS_DEPARTEMENTS = {
    "01": "Ain", "03": "Allier", "04": "Alpes-de-Haute-Provence", "05": "Hautes-Alpes", "06": "Alpes-Maritimes",
    "07": "Ardèche", "09": "Ariège", "11": "Aude", "12": "Aveyron", "13": "Bouches-du-Rhône", "15": "Cantal",
    "26": "Drôme", "30": "Gard", "31": "Haute-Garonne", "32": "Gers", "34": "Hérault", "38": "Isère", "42": "Loire",
    "43": "Haute-Loire", "46": "Lot", "48": "Lozère", "63": "Puy-de-Dôme", "65": "Hautes-Pyrénées",
    "66": "Pyrénées-Orientales", "69": "Rhône", "73": "Savoie", "74": "Haute-Savoie", "81": "Tarn",
    "82": "Tarn-et-Garonne", "83": "Var", "84": "Vaucluse"}
MOIS = {"janvier": 1, "janv": 1, "fevrier": 2, "fevr": 2, "fev": 2, "mars": 3, "avril": 4, "avr": 4, "mai": 5, "juin": 6,
        "juillet": 7, "juil": 7, "aout": 8, "septembre": 9, "sept": 9, "sep": 9, "octobre": 10, "oct": 10,
        "novembre": 11, "nov": 11, "decembre": 12, "dec": 12}

# Liens pour ouvrir les calendriers en ligne dans le navigateur (le logiciel ne les lit pas lui-même)
CALENDRIERS_EN_LIGNE = (
    ("ffa", "Calendrier officiel FFA", "https://bases.athle.fr/asp.net/liste.aspx?frmbase=calendrier&frmmode=1"
     "&frmespace=0&frmsaison={saison}&frmtype1={type_ffa}"),
    ("betrail", "Betrail", "https://www.betrail.run/calendrier-trail/france/{region_slug}"),
    ("sasdepart", "Sas Départ", "https://sasdepart.fr/calendrier-trail/"),
    ("gotrail", "GoTrail", "https://gotrail.run/trail-running-calendar/france"),
    ("sportnature", "Sport-Nature", "https://www.sport-nature.net/agenda-trail/"),
    ("tracedetrail", "Trace de Trail", "https://tracedetrail.fr/fr/calendar"),
)
TYPE_FFA = {"Stade": "Stade", "Hors stade": "Hors+Stade", "Trail": "Hors+Stade", "Montagne": "Hors+Stade",
            "Marche nordique": "Hors+Stade", "Autre": ""}
SLUG_REGION = {"Provence-Alpes-Côte d'Azur": "provence-alpes-cote-d-azur", "Occitanie": "occitanie",
               "Auvergne-Rhône-Alpes": "auvergne-rhone-alpes"}


class ErreurCalendrier(Exception):
    """Message lisible ; rien n'a été modifié."""


def sans_accents(t):
    t = unicodedata.normalize("NFD", str(t or "").lower())
    return "".join(c for c in t if unicodedata.category(c) != "Mn")


def km_effort(distance_km, denivele_m):
    """Distance + 1 km par 100 m de dénivelé positif (réglementation FFA des manifestations running)."""
    if not distance_km:
        return None
    return round(float(distance_km) + (float(denivele_m or 0)) / 100, 1)


def classer(texte="", distance_km=None, denivele_m=None):
    """Discipline la plus probable d'après le nom ou la description, la distance et le dénivelé.
    Trail : découverte sous 30 km-effort, court de 30 à 59, long à partir de 60, ultra à partir de 80 km."""
    t = sans_accents(texte)
    if re.search(r"\b(kv|kilometre vertical|vertical race)\b", t):
        return "kv"
    if "marche nordique" in t:
        return "marche_nordique"
    if re.search(r"\bcross\b", t) and "crossfit" not in t:
        return "cross"
    if re.search(r"\b(piste|meeting|interclubs|pointe|salle|lancers?|sauts?|sprints?|stade)\b", t) \
            and not re.search(r"trail|route|semi|marathon", t):
        return "stade"
    if re.search(r"\b(ekiden|relais)\b", t):
        return "relais"
    if re.search(r"montagne|skyrace|sky race", t):
        return "montagne"
    ke = km_effort(distance_km, denivele_m)
    if re.search(r"\b(ultra|utra|100 ?miles|backyard)\b", t) or (distance_km and distance_km >= 80 and
                                                               ("trail" in t or (denivele_m or 0) > 800)):
        return "ultra_trail"
    if "trail" in t or "course nature" in t or ((denivele_m or 0) >= 300 and distance_km):
        if ke is None:
            return "trail_court" if "trail" in t else "course_nature"
        return "trail_decouverte" if ke < 30 else "trail_court" if ke < 60 else "trail_long" \
            if (distance_km or 0) < 80 else "ultra_trail"
    if re.search(r"\b(10 ?km|5 ?km|semi|marathon|corrida|foulees?|route|run|course pedestre|jogging|100 ?km)\b", t) \
            or distance_km:
        return "route"
    return "autre"


def niveau_depuis(texte):
    t = sans_accents(texte)
    for mots, code in ((("championnat de france", "championnats de france", "france de"), "championnat_france"),
                       (("championnat regional", "championnats regionaux", "regionaux"), "championnat_regional"),
                       (("international",), "international"), (("national",), "national"),
                       (("label",), "label"), (("regional",), "regional"), (("departemental",), "departemental")):
        if any(m in t for m in mots):
            return code
    return None


# ------------------------------------------------------------------ dates et lieux

def lire_date(texte, annee_defaut=None):
    """Une date en français : 15/11/2026, 15-11-26, 2026-11-15, « dim. 15 nov. 2026 », « 15 novembre »."""
    t = sans_accents(texte).strip()
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", t)
    if m:
        return date(int(m[1]), int(m[2]), int(m[3]))
    m = re.search(r"\b(\d{1,2})[/.\-](\d{1,2})[/.\-](\d{2,4})\b", t)
    if m:
        a = int(m[3])
        a = a + 2000 if a < 100 else a
        try:
            return date(a, int(m[2]), int(m[1]))
        except ValueError:
            return None
    m = re.search(r"\b(\d{1,2})(?:er)?\s+([a-z]{3,9})\.?\s*(\d{4})?", t)
    if m and m[2] in MOIS:
        a = int(m[3]) if m[3] else (annee_defaut or date.today().year)
        try:
            return date(a, MOIS[m[2]], int(m[1]))
        except ValueError:
            return None
    return None


def lire_dates(texte, annee_defaut=None):
    """(début, fin) : « du 13 au 15 novembre 2026 », « 13-15/11/2026 », « 13/11/2026 - 15/11/2026 »."""
    t = sans_accents(texte)
    m = re.search(r"\b(\d{1,2})\s*(?:au|-|et)\s*(\d{1,2})[/.](\d{1,2})[/.](\d{2,4})\b", t)
    if m:
        f = lire_date(f"{m[2]}/{m[3]}/{m[4]}")
        try:
            return (f.replace(day=int(m[1])) if f else None), f
        except ValueError:
            return f, f
    m = re.search(r"\b(?:du\s+)?(\d{1,2})(?:er)?\s+(?:au|-)\s+(\d{1,2})\s+([a-z]{3,9})\.?\s*(\d{4})?", t)
    if m and m[3] in MOIS:
        f = lire_date(f"{m[2]} {m[3]} {m[4] or ''}", annee_defaut)
        return (f.replace(day=int(m[1])) if f else None), f
    dates = re.findall(r"\d{1,2}[/.\-]\d{1,2}[/.\-]\d{2,4}|\d{4}-\d{2}-\d{2}", t)
    if len(dates) >= 2:
        return lire_date(dates[0]), lire_date(dates[1])
    d = lire_date(texte, annee_defaut)
    return d, None


def lire_lieu(texte):
    """(commune, code postal, département) depuis « Bédoin (84) », « 84410 Bédoin », « Bédoin - 84 »."""
    t = str(texte or "").strip()
    m = re.search(r"\b(\d{5})\b", t)
    if m:
        cp = m[1]
        commune = re.sub(r"\s+", " ", t.replace(cp, "")).strip(" -,()")
        return commune or None, cp, cp[:2]
    m = re.search(r"\(?\b(0[1-9]|[1-8]\d|9[0-5]|2[AB])\b\)?\s*$", t)
    if m:
        return t[:m.start()].strip(" -,(") or None, None, m[1]
    return t or None, None, None


DISTANCE = re.compile(r"(\d+(?:[.,]\d+)?)\s*(km|k)\b(?:\s*(?:/|et|,|-)?\s*(\d{2,5})\s*(?:m\s*)?d\+)?", re.I)


def lire_distances(texte):
    """[(distance_km, D+ ou None)] trouvées dans un texte : « 12 km / 600 D+, 25 km 1200m D+, 42k »."""
    res = []
    for m in DISTANCE.finditer(str(texte or "")):
        d = float(m[1].replace(",", "."))
        if 0.1 <= d <= 400:
            res.append((d, int(m[3]) if m[3] else None))
    return res


def nom_sans_distances(nom):
    """« Trail du Ventoux 23 km 1100 D+ » → « Trail du Ventoux » : seules les distances en fin de nom partent
    (« Les 10 km de Carpentras » reste tel quel) ; elles sont gardées dans les épreuves."""
    n = str(nom or "").strip()
    fin = re.compile(r"[\s/,+\-–]*(?:\d+(?:[.,]\d+)?\s*(?:km|k)\b(?:\s*(?:/|et|,|-)?\s*\d{2,5}\s*(?:m\s*)?d\+)?"
                     r"|et)\s*$", re.I)
    while True:
        m = fin.search(n)
        if not m or m.start() == 0:
            break
        n = n[:m.start()].rstrip(" /,+-–")
    if n != str(nom or "").strip():
        n = re.sub(r"(\s+\d+(?:[.,]\d+)?)+$", "", n)      # « Trail 12 et 25 km » : le 12 part aussi
    return n if len(n) >= 3 else str(nom or "").strip()


def cle(nom, jour, departement=None):
    """Clé de doublon : nom sans année ni numéro d'édition, date, département."""
    n = sans_accents(nom)
    n = re.sub(r"\b(19|20)\d{2}\b|\b\d+(e|eme|ème|ieme)\s+edition\b|\bedition\b|\b\d+e\b", " ", n)
    n = re.sub(r"[^a-z0-9]+", " ", n).strip()
    return f"{n}|{jour}|{departement or ''}"


def mots(nom):
    vides = {"de", "du", "des", "la", "le", "les", "l", "d", "et", "en", "a", "au", "aux", "trail", "course", "the"}
    return {m for m in re.sub(r"[^a-z0-9]+", " ", sans_accents(nom)).split() if m not in vides and not m.isdigit()}


def meme_course(a, b):
    """Deux fiches sont la même course si même date de début et noms proches (et même département si connu)."""
    if str(a.get("date_debut"))[:10] != str(b.get("date_debut"))[:10]:
        return False
    if a.get("departement") and b.get("departement") and a["departement"] != b["departement"]:
        return False
    ma, mb = mots(a.get("nom")), mots(b.get("nom"))
    if not ma or not mb:
        return sans_accents(a.get("nom")) == sans_accents(b.get("nom"))
    return len(ma & mb) / len(ma | mb) >= 0.5 or ma <= mb or mb <= ma


def normaliser(c):
    """Complète une fiche lue : dates ISO, département, discipline, clé. Lève ErreurCalendrier si inutilisable."""
    c = {k: (v.strip() if isinstance(v, str) else v) for k, v in c.items()}
    if not c.get("nom"):
        raise ErreurCalendrier("course sans nom")
    d = c.get("date_debut")
    if isinstance(d, str):
        d = lire_date(d)
    if not d:
        raise ErreurCalendrier(f"date illisible pour « {c['nom']} »")
    c["date_debut"] = d.isoformat()
    f = c.get("date_fin")
    if isinstance(f, str):
        f = lire_date(f)
    c["date_fin"] = f.isoformat() if f and f > d else None
    if c.get("code_postal") and not c.get("departement"):
        c["departement"] = c["code_postal"][:2]
    c["epreuves"] = c.get("epreuves") or []
    if not c.get("discipline"):
        e = max(c["epreuves"], key=lambda x: x.get("distance_km") or 0) if c["epreuves"] else {}
        c["discipline"] = classer(f"{c['nom']} {c.get('notes') or ''}", e.get("distance_km"), e.get("denivele_m"))
    for e in c["epreuves"]:
        e.setdefault("discipline", classer(f"{c['nom']} {e.get('nom') or ''}", e.get("distance_km"), e.get("denivele_m")))
    c["niveau"] = c.get("niveau") or niveau_depuis(f"{c['nom']} {c.get('notes') or ''}")
    c["cle"] = cle(c["nom"], c["date_debut"], c.get("departement"))
    return c


# ------------------------------------------------------------------ iCalendar

def _ics_valeur(v):
    morceaux, i = [], 0
    while i < len(v):                                   # séquences d'échappement de la norme RFC 5545
        if v[i] == "\\" and i + 1 < len(v):
            morceaux.append({"n": "\n", "N": "\n"}.get(v[i + 1], v[i + 1]))
            i += 2
        else:
            morceaux.append(v[i])
            i += 1
    return "".join(morceaux)


def _ics_date(v):
    m = re.match(r"(\d{4})(\d{2})(\d{2})(?:T(\d{2})(\d{2}))?", v)
    if not m:
        return None, None
    return date(int(m[1]), int(m[2]), int(m[3])), (f"{m[4]}:{m[5]}" if m[4] else None)


def lire_ics(texte):
    """Courses d'un flux iCalendar. Renvoie (courses, erreurs)."""
    if isinstance(texte, bytes):
        texte = texte.decode("utf-8", "replace")
    lignes = re.sub(r"\r?\n[ \t]", "", texte).splitlines()
    courses, erreurs, ev = [], [], None
    for l in lignes:
        if l.startswith("BEGIN:VEVENT"):
            ev = {}
        elif l.startswith("END:VEVENT") and ev is not None:
            try:
                courses.append(_depuis_evenement(ev))
            except ErreurCalendrier as e:
                erreurs.append(str(e))
            ev = None
        elif ev is not None and ":" in l:
            k, v = l.split(":", 1)
            ev[k.split(";")[0].upper()] = (k, _ics_valeur(v))
    return courses, erreurs


def _depuis_evenement(ev):
    nom = ev.get("SUMMARY", ("", ""))[1].strip()
    d0, heure = _ics_date(ev.get("DTSTART", ("", ""))[1])
    d1, _h = _ics_date(ev.get("DTEND", ("", ""))[1])
    if d1 and "VALUE=DATE" in ev.get("DTEND", ("", ""))[0]:
        d1 -= timedelta(days=1)                      # fin exclusive des journées entières
    lieu = ev.get("LOCATION", ("", ""))[1]
    desc = ev.get("DESCRIPTION", ("", ""))[1]
    commune, cp, dep = lire_lieu(lieu.split(",")[-1] if "," in lieu and not re.search(r"\d{5}", lieu) else lieu)
    epreuves = [{"nom": f"{d:g} km", "distance_km": d, "denivele_m": dp, "heure_depart": heure}
                for d, dp in lire_distances(f"{nom} {desc}")]
    statut = "annulee" if ev.get("STATUS", ("", ""))[1].upper() == "CANCELLED" or "annul" in sans_accents(nom) else "prevue"
    nom = re.sub(r"^(annule|annulé|annulée)\s*[—:-]\s*", "", nom, flags=re.I)
    return normaliser({"nom": nom_sans_distances(nom), "date_debut": d0,
                       "date_fin": d1, "commune": commune, "code_postal": cp, "departement": dep,
                       "site": ev.get("URL", ("", ""))[1] or None, "notes": desc[:500] or None,
                       "ref_externe": ev.get("UID", ("", ""))[1] or None, "statut": statut, "epreuves": epreuves})


# ------------------------------------------------------------------ tableau collé ou CSV

ENTETES = {"date": ("date", "dates", "jour", "le"), "nom": ("nom", "libelle", "epreuve", "course", "evenement",
                                                           "manifestation", "competition", "titre", "intitule"),
           "lieu": ("lieu", "ville", "commune", "localite", "localisation"), "departement": ("dept", "dep", "departement"),
           "discipline": ("type", "discipline", "categorie"), "niveau": ("niveau", "label"),
           "distance": ("distance", "distances", "km", "parcours", "formats"), "site": ("site", "lien", "url", "web"),
           "organisateur": ("organisateur", "club", "organisation")}


def _decouper(lignes):
    sep = "\t" if sum(l.count("\t") for l in lignes) >= len(lignes) else ";" if sum(l.count(";") for l in lignes) >= \
        len(lignes) else None
    if sep:
        return [next(csv.reader([l], delimiter=sep)) for l in lignes]
    return [re.split(r"\s{2,}|\s\|\s", l.strip()) for l in lignes]


def lire_tableau(texte, annee_defaut=None):
    """Courses d'un tableau copié depuis une page de calendrier (cellules séparées par des tabulations, des
    points-virgules ou plusieurs espaces), avec ou sans ligne d'en-tête. Renvoie (courses, erreurs)."""
    if isinstance(texte, bytes):
        for enc in ("utf-8-sig", "cp1252"):
            try:
                texte = texte.decode(enc)
                break
            except UnicodeDecodeError:
                continue
    lignes = [l for l in str(texte).splitlines() if l.strip()]
    if not lignes:
        return [], []
    cellules = _decouper(lignes)
    entete = [sans_accents(c).strip(" :") for c in cellules[0]]
    colonnes = {}
    for champ, noms in ENTETES.items():
        for i, c in enumerate(entete):
            if i not in colonnes.values() and (c in noms or any(c.startswith(n) for n in noms if len(n) > 3)):
                colonnes[champ] = i
                break
    avec_entete = "nom" in colonnes and "date" in colonnes
    courses, erreurs = [], []
    for n, ligne in enumerate(cellules[1:] if avec_entete else cellules, 2 if avec_entete else 1):
        ligne = [c.strip() for c in ligne]
        if sum(1 for c in ligne if c) < 2:              # titre, séparateur, ligne de texte : pas une course
            continue
        if avec_entete:
            v = {k: (ligne[i] if i < len(ligne) else "") for k, i in colonnes.items()}
        else:
            v = _deviner(ligne, annee_defaut)
            if v is None:
                continue
        try:
            courses.append(_depuis_ligne(v, annee_defaut))
        except ErreurCalendrier as e:
            erreurs.append(f"ligne {n} : {e}")
    return courses, erreurs


def _deviner(cellules, annee_defaut):
    """Sans en-tête : la cellule avec une date, celle avec un lieu (département ou code postal), le type,
    le niveau ; le nom est la plus longue des autres."""
    v, reste = {}, []
    for c in cellules:
        if not c:
            continue
        if "date" not in v and lire_date(c, annee_defaut) and len(c) <= 40:
            v["date"] = c
        elif "lieu" not in v and re.search(r"\(\s*(\d{2}|2[AB])\s*\)|\b\d{5}\b", c):
            v["lieu"] = c
        elif "discipline" not in v and re.fullmatch(r"(?i)\s*(stade|hors stade|cross|trail|route|montagne|"
                                                     r"marche nordique|running|nature)\s*", sans_accents(c)):
            v["discipline"] = c
        elif "niveau" not in v and niveau_depuis(c) and len(c) < 40:
            v["niveau"] = c
        elif "distance" not in v and lire_distances(c) and len(c) < 60:
            v["distance"] = c
        else:
            reste.append(c)
    if "date" not in v or not reste:
        return None
    v["nom"] = max(reste, key=len)
    return v


def _depuis_ligne(v, annee_defaut):
    d0, d1 = lire_dates(v.get("date", ""), annee_defaut)
    commune, cp, dep = lire_lieu(v.get("lieu"))
    if v.get("departement"):
        m = re.search(r"\b(\d{2}|2[AB])\b", v["departement"])
        dep = m[1] if m else dep
    texte_disc = sans_accents(v.get("discipline"))
    eps = [{"nom": f"{d:g} km", "distance_km": d, "denivele_m": dp}
           for d, dp in lire_distances(f"{v.get('distance', '')} {v.get('nom', '')}")]
    discipline = None
    if texte_disc:
        e = max(eps, key=lambda x: x["distance_km"]) if eps else {}
        discipline = classer(f"{texte_disc} {v.get('nom')}", e.get("distance_km"), e.get("denivele_m"))
        if texte_disc.strip() == "hors stade" and discipline in ("autre", "stade"):
            discipline = "route"
    return normaliser({"nom": nom_sans_distances(v.get("nom")), "date_debut": d0, "date_fin": d1, "commune": commune,
                       "code_postal": cp,
                       "departement": dep, "discipline": discipline, "niveau": niveau_depuis(v.get("niveau") or "")
                       or None, "site": v.get("site") or None, "organisateur": v.get("organisateur") or None,
                       "epreuves": eps})


# ------------------------------------------------------------------ filtres et liens

def filtrer(courses, debut=None, fin=None, departements=None, familles=None, disciplines=None, niveaux=None,
            recherche="", favoris=False, avec_annulees=True):
    q = sans_accents(recherche).split()
    res = []
    for c in courses:
        d = str(c["date_debut"])[:10]
        if debut and (c.get("date_fin") or d) < str(debut)[:10]:
            continue
        if fin and d > str(fin)[:10]:
            continue
        if departements and c.get("departement") not in departements:
            continue
        if familles and FAMILLE.get(c.get("discipline"), "Autre") not in familles:
            continue
        if disciplines and c.get("discipline") not in disciplines:
            continue
        if niveaux and c.get("niveau") not in niveaux:
            continue
        if favoris and not c.get("favori"):
            continue
        if not avec_annulees and c.get("statut") == "annulee":
            continue
        if q:
            t = sans_accents(" ".join(str(c.get(k) or "") for k in ("nom", "commune", "organisateur", "mes_notes")))
            if not all(m in t for m in q):
                continue
        res.append(c)
    return res


def liens_calendriers(famille="Trail", region="Provence-Alpes-Côte d'Azur", saison=None):
    """[(nom, adresse)] des calendriers en ligne à ouvrir dans le navigateur."""
    saison = saison or (date.today().year + (1 if date.today().month >= 9 else 0))
    res = []
    for code, nom, modele in CALENDRIERS_EN_LIGNE:
        if code == "betrail" and famille not in ("Trail", "Montagne"):
            continue
        res.append((nom, modele.format(saison=saison, type_ffa=TYPE_FFA.get(famille, ""),
                                       region_slug=SLUG_REGION.get(region, "provence-alpes-cote-d-azur"))))
    return res


def recherche_web(c):
    return "https://www.google.com/search?q=" + quote_plus(" ".join(x for x in (c.get("nom"), c.get("commune"),
                                                                                 str(c.get("date_debut"))[:4]) if x))


def vers_ics(courses, nom="Calendrier des courses"):
    from noyau.club.agenda import ics
    return ics([{"id": c.get("id") or i, "uuid": c.get("uuid"), "titre": c["nom"], "date": c["date_debut"],
                 "heure_debut": None, "lieu": " ".join(x for x in (c.get("code_postal"), c.get("commune")) if x),
                 "type": "competition", "contenu": ", ".join(f"{e['distance_km']:g} km" for e in c.get("epreuves", [])
                                                             if e.get("distance_km")) + (f"\n{c['site']}" if c.get("site") else ""),
                 "annulee": c.get("statut") == "annulee"} for i, c in enumerate(courses, 1)], nom)
