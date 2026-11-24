"""
Règles des connecteurs Claude, sans base de données ni réseau.

Paquet (Claude -> logiciel), fichier « trailhub-connecteurs-AAAA-MM-JJ[-HHMM].json » :

    {"format": "trailhub-connecteurs", "version": 1, "cree_le": "2026-11-24T05:50:00",
     "activites":   [{"source": "strava", "id_externe", "date" (heure locale), "nom", "sport",
                      "distance_m", "duree_s", "duree_totale_s", "denivele_m", "vitesse_moy_ms",
                      "vitesse_max_ms", "fc_moy", "fc_max", "calories", "cadence", "effort_relatif",
                      "materiel_id", "lieu"}],
     "sante":       [{"date", "sommeil_duree_h", "sommeil_score", "hrv_nuit_ms", "fc_repos",
                      "stress_moyen", "body_battery_max", "body_battery_min", "pas"}],
     "records":     [{"sport", "type", "valeur", "unite", "date", "activite_externe"}],
     "materiel":    [{"id", "type" (Shoe/Bike), "nom", "marque", "modele", "distance_m", "retire"}],
     "charge":      {"date", "aigue", "chronique", "acwr", "source"},
     "agenda":      [{"cle", "titre", "debut", "fin", "lieu", "journee"}],
     "courses_mail":[{"nom", "date", "lieu", "distance_km", "denivele_m", "lien", "sujet"}],
     "parcours":    [{"source", "id", "nom", "lieu", "distance_m", "denivele_m", "difficulte",
                      "type_parcours", "note", "lien", "lat", "lon", "meteo"}],
     "securite":    [{"trajet", "date", "niveau", "resume", "details", "lien"}],
     "playlists":   [{"nom", "lien", "duree_min", "seance"}],
     "analyses":    [{"id_externe", "source", "texte"}],          # analyses écrites par Claude
     "demandes_traitees": [{"cle", "statut" (fait/erreur), "message", "lien"}]}

Toutes les sections sont facultatives. Les heures sont locales (Europe/Paris).

Demandes (logiciel -> Claude), fichier « trailhub-demandes.json » :

    {"format": "trailhub-demandes", "version": 1, "cree_le", "demandes": [
        {"cle", "type", "titre", "cree_le", "parametres": {...}}]}

Types de demandes : seance_montre, agenda, playlist, parcours, securite.
"""

import hashlib
import json
import re
from datetime import date, datetime, timedelta

FORMAT_PAQUET = "trailhub-connecteurs"
FORMAT_DEMANDES = "trailhub-demandes"
VERSION = 1
MOTIF_PAQUET = re.compile(r"^trailhub-connecteurs-.*\.json$", re.I)
FICHIER_DEMANDES = "trailhub-demandes.json"

SECTIONS = ("activites", "sante", "records", "materiel", "agenda", "courses_mail", "parcours", "securite",
            "playlists", "analyses", "demandes_traitees")

SOURCES_ACTIVITE = {"strava": "Strava (connecteur)", "garmin": "Garmin (connecteur)"}

TYPES_DEMANDE = {
    "seance_montre": "Séance vers la montre",
    "agenda": "Événement dans Google Agenda",
    "playlist": "Playlist Spotify",
    "parcours": "Recherche de parcours (AllTrails)",
    "securite": "Contrôle de sécurité d'un trajet (TrailSync)",
}
STATUTS_DEMANDE = {"a_faire": "À faire", "envoyee": "Envoyée à Claude", "fait": "Fait", "erreur": "Erreur",
                   "annulee": "Annulée"}

# Strava (sport_type) et Garmin (activityType) -> types du logiciel
TYPES_SPORT = {
    "trailrun": "Trail", "trail_running": "Trail", "run": "Course", "running": "Course", "virtualrun": "Course",
    "track_running": "Course", "treadmill_running": "Course", "street_running": "Course",
    "mountainbikeride": "VTT", "gravelride": "VTT", "mountain_biking": "VTT", "gravel_cycling": "VTT",
    "ride": "Vélo", "virtualride": "Vélo", "ebikeride": "Vélo", "cycling": "Vélo", "road_biking": "Vélo",
    "indoor_cycling": "Vélo", "virtual_ride": "Vélo",
    "hike": "Randonnée", "walk": "Randonnée", "hiking": "Randonnée", "walking": "Randonnée",
}

RECORDS_LIBELLES = {
    "Fastest400": "400 m", "FastestHalfMile": "800 m (½ mile)", "Fastest1k": "1 km", "Fastest1500": "1 500 m",
    "FastestMile": "1 mile", "Fastest2k": "2 km", "Fastest3k": "3 km", "Fastest2Mile": "2 miles",
    "Fastest5k": "5 km", "Fastest5Mile": "5 miles", "Fastest10k": "10 km", "Fastest15k": "15 km",
    "Fastest10Mile": "10 miles", "Fastest20k": "20 km", "FastestHalfMarathon": "Semi-marathon",
    "Fastest30k": "30 km", "FastestMarathon": "Marathon", "Fastest50k": "50 km", "Fastest100k": "100 km",
    "BiggestClimb": "Plus grande montée", "MostElevationGain": "Plus gros dénivelé", "LongestActivity": "Plus longue sortie",
}

USURE_CHAUSSURE_KM = 700          # repère courant : une chaussure de trail se change entre 600 et 800 km
ACWR_BAS, ACWR_HAUT, ACWR_DANGER = 0.8, 1.3, 1.5
JOURNEE_CHARGEE_H = 9             # heures d'agenda dans la journée au-delà desquelles on parle de journée chargée


class ErreurConnecteurs(Exception):
    pass


# ------------------------------------------------------------------ outils

def _nb(v):
    if v is None or v == "" or isinstance(v, bool):
        return None
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if x == x else None          # NaN -> None


def _texte(v, maxi=500):
    if v is None:
        return None
    t = str(v).strip()
    return t[:maxi] if t else None


def date_locale(v):
    """'2026-11-23T18:31:54', '2026-11-23 18:31', '2026-11-23' -> 'AAAA-MM-JJ HH:MM:SS' (ou None)."""
    if not v:
        return None
    t = str(v).strip().replace("Z", "")[:19]
    try:
        return datetime.fromisoformat(t).strftime("%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None


def jour(v):
    d = date_locale(v)
    return d[:10] if d else None


def lien_sur(v):
    """Seuls les liens https sont gardés (ils viennent de services extérieurs)."""
    t = _texte(v, 1000)
    return t if t and t.lower().startswith("https://") else None


def empreinte(contenu):
    if isinstance(contenu, (dict, list)):
        contenu = json.dumps(contenu, sort_keys=True, ensure_ascii=False)
    if isinstance(contenu, str):
        contenu = contenu.encode("utf-8")
    return hashlib.sha256(contenu).hexdigest()


def type_sport(code):
    if not code:
        return "Autre"
    c = str(code).strip().lower().replace(" ", "_")
    return TYPES_SPORT.get(c) or TYPES_SPORT.get(c.replace("_", "")) or "Autre"


# ------------------------------------------------------------------ paquet

def lire_paquet(texte_ou_dict):
    """Vérifie et normalise un paquet. Lève ErreurConnecteurs avec un message lisible."""
    if isinstance(texte_ou_dict, (str, bytes)):
        try:
            p = json.loads(texte_ou_dict)
        except ValueError:
            raise ErreurConnecteurs("Ce fichier n'est pas un paquet de connecteurs lisible (JSON abîmé).")
    else:
        p = texte_ou_dict
    if not isinstance(p, dict) or p.get("format") != FORMAT_PAQUET:
        raise ErreurConnecteurs("Ce fichier n'est pas un paquet « Connecteurs Claude » de Trail Hub Center.")
    try:
        version = int(p.get("version", 0))
    except (TypeError, ValueError):
        version = 0
    if version < 1:
        raise ErreurConnecteurs("Version du paquet inconnue.")
    if version > VERSION:
        raise ErreurConnecteurs(f"Ce paquet (version {version}) vient d'une version plus récente : mets le logiciel "
                                "à jour.")
    out = {"format": FORMAT_PAQUET, "version": version, "cree_le": date_locale(p.get("cree_le")) or "",
           "charge": None}
    for s in SECTIONS:
        v = p.get(s) or []
        out[s] = [x for x in v if isinstance(x, dict)] if isinstance(v, list) else []
    out["activites"] = [a for a in (normaliser_activite(x) for x in out["activites"]) if a]
    out["sante"] = [s for s in (normaliser_sante(x) for x in out["sante"]) if s]
    if isinstance(p.get("charge"), dict):
        out["charge"] = normaliser_charge(p["charge"])
    if isinstance(p.get("bilan_semaine"), str):
        out["bilan_semaine"] = p["bilan_semaine"][:4000]
    return out


def normaliser_activite(a):
    src = str(a.get("source") or "strava").lower()
    if src not in SOURCES_ACTIVITE:
        return None
    ident, d = _texte(a.get("id_externe"), 60), date_locale(a.get("date"))
    if not ident or not d:
        return None
    dist_km = round((_nb(a.get("distance_m")) or 0) / 1000, 3)
    duree = int(_nb(a.get("duree_s")) or 0)
    v = _nb(a.get("vitesse_moy_ms"))
    if not v and dist_km and duree:
        v = dist_km * 1000 / duree
    vmax = _nb(a.get("vitesse_max_ms"))
    cad = _nb(a.get("cadence"))
    if cad and cad < 120 and type_sport(a.get("sport")) in ("Course", "Trail"):
        cad = cad * 2                       # Strava donne les pas d'une jambe : on compte les deux
    return {
        "source": src, "id_externe": ident, "date": d, "nom": _texte(a.get("nom"), 200) or "Sortie",
        "type": type_sport(a.get("sport")), "sport": _texte(a.get("sport"), 40),
        "distance": dist_km, "duree": duree, "duree_totale": int(_nb(a.get("duree_totale_s")) or 0) or None,
        "denivele": int(round(_nb(a.get("denivele_m")) or 0)),
        "vitesse_moyenne": round(v * 3.6, 2) if v else None,
        "allure_moyenne": round(1000 / v / 60, 3) if v else None,       # min/km
        "vitesse_max": round(vmax * 3.6, 2) if vmax else None,
        "allure_max": round(1000 / vmax / 60, 3) if vmax else None,
        "frequence_cardiaque_moyenne": int(_nb(a.get("fc_moy"))) if _nb(a.get("fc_moy")) else None,
        "frequence_cardiaque_max": int(_nb(a.get("fc_max"))) if _nb(a.get("fc_max")) else None,
        "calories": _nb(a.get("calories")), "cadence_moyenne": round(cad, 1) if cad else None,
        "effort_relatif": _nb(a.get("effort_relatif")), "materiel_id": _texte(a.get("materiel_id"), 40),
        "lieu": _texte(a.get("lieu"), 120),
    }


CHAMPS_SANTE = {"sommeil_duree_h": (0, 16), "sommeil_score": (0, 100), "hrv_nuit_ms": (5, 300),
                "fc_repos": (25, 120), "stress_moyen": (0, 100), "body_battery_max": (0, 100),
                "body_battery_min": (0, 100)}


def normaliser_sante(s):
    j = jour(s.get("date"))
    if not j:
        return None
    m = {}
    for k, (lo, hi) in CHAMPS_SANTE.items():
        v = _nb(s.get(k))
        if v is not None and lo <= v <= hi:
            m[k] = round(v, 2) if k == "sommeil_duree_h" else (round(v, 1) if k == "hrv_nuit_ms" else int(round(v)))
    pas = _nb(s.get("pas"))
    return {"date": j, "mesures": m, "pas": int(pas) if pas else None} if (m or pas) else None


def normaliser_charge(c):
    a, ch = _nb(c.get("aigue")), _nb(c.get("chronique"))
    r = _nb(c.get("acwr"))
    if r is None and a is not None and ch:
        r = round(a / ch, 2)
    if r is None:
        return None
    return {"date": jour(c.get("date")) or date.today().isoformat(), "aigue": a, "chronique": ch,
            "acwr": round(r, 2), "source": _texte(c.get("source"), 60) or "Running Workout"}


def zone_acwr(r):
    """(code, libellé, conseil) pour un rapport charge aiguë / chronique."""
    if r is None:
        return ("inconnu", "Pas de donnée", "")
    if r < ACWR_BAS:
        return ("bas", "Charge en baisse", "Tu peux remonter progressivement le volume.")
    if r <= ACWR_HAUT:
        return ("optimal", "Zone conseillée", "Charge bien dosée : continue ainsi.")
    if r <= ACWR_DANGER:
        return ("eleve", "Au-dessus de la zone conseillée",
                "La semaine est plus chargée que d'habitude : prévois une séance facile ou un jour de repos.")
    return ("danger", "Hausse brutale", "Risque de blessure accru : allège nettement les 3 prochains jours.")


# ------------------------------------------------------------------ matériel

def usure_chaussure(distance_m, km_max=USURE_CHAUSSURE_KM):
    km = (distance_m or 0) / 1000
    pct = round(100 * km / km_max) if km_max else 0
    if pct >= 100:
        etat = "À changer"
    elif pct >= 85:
        etat = "Bientôt à changer"
    else:
        etat = "Bon état"
    return {"km": round(km, 1), "pct": pct, "etat": etat, "reste_km": max(0, round(km_max - km))}


def nom_materiel(m):
    if m.get("nom"):
        return str(m["nom"]).strip()
    morceaux = [str(x).strip() for x in (m.get("marque"), m.get("modele")) if x]
    return " ".join(morceaux) or "Matériel Strava"


# ------------------------------------------------------------------ agenda et fatigue

def charge_agenda_par_jour(evenements):
    """{jour: heures occupées} (événements de la journée entière ignorés : congés, anniversaires…)."""
    par_jour = {}
    for e in evenements:
        if e.get("journee"):
            continue
        d, f = date_locale(e.get("debut")), date_locale(e.get("fin"))
        if not d or not f:
            continue
        dd, ff = datetime.fromisoformat(d), datetime.fromisoformat(f)
        if ff <= dd or (ff - dd) > timedelta(hours=16):
            continue
        par_jour[d[:10]] = par_jour.get(d[:10], 0) + (ff - dd).total_seconds() / 3600
    return {k: round(v, 1) for k, v in par_jour.items()}


def fatigue_agenda(heures):
    """Bonus de fatigue (0 à 2 sur 10) d'une journée selon les heures prises dans l'agenda."""
    if not heures:
        return 0
    if heures >= JOURNEE_CHARGEE_H + 2:
        return 2
    if heures >= JOURNEE_CHARGEE_H:
        return 1
    return 0


def creneaux_libres(evenements, jour_iso, debut_h=6, fin_h=21, duree_min=60):
    """Créneaux libres d'au moins `duree_min` dans la journée (pour proposer l'heure d'une séance)."""
    occupes = []
    for e in evenements:
        d, f = date_locale(e.get("debut")), date_locale(e.get("fin"))
        if e.get("journee") or not d or not f or d[:10] != jour_iso:
            continue
        occupes.append((datetime.fromisoformat(d), datetime.fromisoformat(f)))
    base = datetime.fromisoformat(jour_iso)
    t, fin = base + timedelta(hours=debut_h), base + timedelta(hours=fin_h)
    libres = []
    for d, f in sorted(occupes):
        if d - t >= timedelta(minutes=duree_min):
            libres.append((t.strftime("%H:%M"), min(d, fin).strftime("%H:%M")))
        t = max(t, f)
    if fin - t >= timedelta(minutes=duree_min):
        libres.append((t.strftime("%H:%M"), fin.strftime("%H:%M")))
    return libres


# ------------------------------------------------------------------ demandes

def prompt_playlist(nom_seance, duree_min, style="funk et disco des années 80 et 90", rythme=None):
    """Texte envoyé au connecteur Spotify (en français, commence par « Crée »)."""
    duree = max(10, int(duree_min or 45))
    morceaux = [f"Crée une playlist de {duree} minutes de {style}"]
    if rythme:
        morceaux.append(f"avec un tempo autour de {int(rythme)} BPM")
    morceaux.append(f"pour ma séance de course « {str(nom_seance or 'footing').strip()[:80]} »")
    return " ".join(morceaux) + "."


def _allure_ms(texte):
    try:
        m, s = str(texte).strip().split(":")
        sec = int(m) * 60 + int(s)
        return 1000 / sec if sec > 0 else None
    except (ValueError, TypeError):
        return None


_INTENSITE = {"Échauffement": "WARMUP", "Retour au calme": "COOLDOWN", "Effort": "ACTIVE", "Récupération": "RECOVERY"}


def _pas_running_workout(e):
    if e.get("mode") == "distance":
        dt, dv = "DISTANCE", round(float(e.get("valeur") or 0) * 1000)
    else:
        dt, dv = "TIME", round(float(e.get("valeur") or 0) * 60)
    pas = {"type": "WorkoutStep", "intensity": _INTENSITE.get(e.get("type"), "ACTIVE"),
           "durationType": dt, "durationValue": dv, "targetType": "OPEN"}
    v = _allure_ms(e.get("allure_cible"))
    if v:
        pas.update(targetType="PACE", targetValueLow=round(v * 0.97, 3), targetValueHigh=round(v * 1.03, 3))
    elif e.get("fc_cible"):
        fc = int(e["fc_cible"])
        pas.update(targetType="HEART_RATE", targetValueLow=fc - 5, targetValueHigh=fc + 5)
    if e.get("description") or e.get("consigne"):
        pas["description"] = str(e.get("description") or e.get("consigne"))[:120]
    return pas


def seance_vers_running_workout(nom, etapes, description=None):
    """Étapes d'une séance du logiciel -> « workout » du connecteur Running Workout (unités SI).
    Les paires effort / récupération identiques deviennent une répétition."""
    if not etapes:
        raise ErreurConnecteurs("La séance n'a aucune étape.")
    from noyau.entrainement.export_fit_seance import _regrouper
    pas = []
    for p in _regrouper(etapes):
        if p[0] == "etape":
            pas.append(_pas_running_workout(p[1]))
        else:
            n = p[2]
            recup, effort = pas.pop(), pas.pop()
            pas.append({"type": "WorkoutRepeatStep", "repeatValue": n, "steps": [effort, recup]})
    w = {"workoutName": str(nom or "Séance").strip()[:60], "sport": "RUNNING",
         "segments": [{"segmentOrder": 1, "steps": pas}]}
    if description:
        w["description"] = str(description)[:300]
    return w


def duree_seance_min(etapes):
    """Durée estimée (minutes) : les étapes en distance comptent 6 min/km sans allure cible."""
    total = 0.0
    for e in etapes or []:
        try:
            v = float(e.get("valeur") or 0)
        except (TypeError, ValueError):
            continue
        if e.get("mode") == "distance":
            a = _allure_ms(e.get("allure_cible"))
            total += (v * 1000 / a / 60) if a else v * 6
        else:
            total += v
    return int(round(total))


def fichier_demandes(demandes, maintenant=None):
    """Contenu du fichier « trailhub-demandes.json » (les demandes à faire)."""
    return {"format": FORMAT_DEMANDES, "version": VERSION,
            "cree_le": (maintenant or datetime.now()).isoformat(timespec="seconds"),
            "demandes": [{"cle": d["cle"], "type": d["type"], "titre": d.get("titre"), "cree_le": d.get("cree_le"),
                          "parametres": d.get("parametres") or {}} for d in demandes]}


def nom_fichier_paquet(quand=None):
    q = quand or datetime.now()
    return f"trailhub-connecteurs-{q.strftime('%Y-%m-%d-%H%M')}.json"


# ------------------------------------------------------------------ fiche pour l'IA

def resume_paquet(bilan):
    """Une phrase de compte rendu d'import."""
    if not bilan:
        return "Rien de nouveau."
    m = []
    if bilan.get("activites_nouvelles"):
        m.append(f"{bilan['activites_nouvelles']} sortie(s) ajoutée(s)")
    if bilan.get("activites_completees"):
        m.append(f"{bilan['activites_completees']} complétée(s)")
    if bilan.get("sante_jours"):
        m.append(f"{bilan['sante_jours']} jour(s) de récupération")
    for cle, lib in (("records", "record(s)"), ("materiel", "matériel(s) à jour"), ("courses", "course(s) repérée(s) dans tes mails"),
                     ("agenda", "événement(s) d'agenda"), ("parcours", "parcours"), ("securite", "contrôle(s) de sécurité"),
                     ("playlists", "playlist(s)"), ("analyses", "analyse(s) de Claude"), ("demandes", "demande(s) traitée(s)")):
        if bilan.get(cle):
            m.append(f"{bilan[cle]} {lib}")
    if bilan.get("charge"):
        m.append(f"charge {str(bilan['charge']).replace('.', ',')}")
    return (", ".join(m) + ".").capitalize() if m else "Rien de nouveau (tout était déjà dans la base)."
