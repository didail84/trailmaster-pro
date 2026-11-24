"""
Accès aux données des connecteurs Claude : records, charge, agenda, parcours, sécurité, playlists, matériel suivi
par Strava, et demandes envoyées à Claude (séance vers la montre, événement d'agenda, playlist, parcours, sécurité).
"""

import json
import uuid
from datetime import date, datetime, timedelta

from noyau.donnees import base
from noyau.connecteurs import regles as R

ErreurConnecteurs = R.ErreurConnecteurs


def _maintenant():
    return datetime.now().isoformat(timespec="seconds")


# ------------------------------------------------------------------ lecture

def records(athlete_id):
    res = []
    for sport, type_, v, u, d, ext in base.lire_tous(
            "SELECT sport, type, valeur, unite, date, activite_externe FROM connecteurs_records WHERE athlete_id=? "
            "ORDER BY sport, valeur", (athlete_id,)):
        res.append({"sport": sport, "type": type_, "libelle": R.RECORDS_LIBELLES.get(type_, type_), "valeur": v,
                    "unite": u, "date": d, "activite_externe": ext, "texte": texte_record(v, u)})
    ordre = list(R.RECORDS_LIBELLES)
    res.sort(key=lambda r: (r["sport"], ordre.index(r["type"]) if r["type"] in ordre else 99))
    return res


def texte_record(valeur, unite):
    if valeur is None:
        return ""
    if (unite or "").startswith("second"):
        s = int(round(valeur))
        h, m, sec = s // 3600, (s % 3600) // 60, s % 60
        return f"{h} h {m:02d} min {sec:02d} s" if h else f"{m} min {sec:02d} s"
    if (unite or "").startswith("meter") or unite == "m":
        return f"{valeur / 1000:.2f} km".replace(".", ",") if valeur >= 1000 else f"{int(valeur)} m"
    if unite == "watts":
        return f"{int(valeur)} W"
    return f"{valeur} {unite or ''}".strip()


def derniere_charge(athlete_id):
    l = base.lire_un("SELECT date, aigue, chronique, acwr, source FROM connecteurs_charge WHERE athlete_id=? "
                     "ORDER BY date DESC, id DESC LIMIT 1", (athlete_id,))
    if not l:
        return None
    c = dict(zip(("date", "aigue", "chronique", "acwr", "source"), l))
    c["zone"], c["libelle"], c["conseil"] = R.zone_acwr(c["acwr"])
    return c


def historique_charge(athlete_id, jours=60):
    debut = (date.today() - timedelta(days=jours)).isoformat()
    return [dict(zip(("date", "acwr"), l)) for l in base.lire_tous(
        "SELECT date, acwr FROM connecteurs_charge WHERE athlete_id=? AND date>=? ORDER BY date", (athlete_id, debut))]


def materiel_strava(athlete_id):
    res = []
    for i, nom, type_, km, kmax, statut, notes in base.lire_tous(
            "SELECT id, nom, type, km_actuels, km_max_recommande, statut, notes FROM materiel WHERE athlete_id=? "
            "AND notes LIKE '%strava:%' ORDER BY statut, type, nom", (athlete_id,)):
        u = R.usure_chaussure((km or 0) * 1000, kmax or R.USURE_CHAUSSURE_KM) if type_ == "Chaussures" else None
        res.append({"id": i, "nom": nom, "type": type_, "km": km or 0, "statut": statut, "usure": u})
    return res


def agenda(athlete_id, debut=None, jours=14):
    d0 = debut or date.today().isoformat()
    d1 = (date.fromisoformat(d0[:10]) + timedelta(days=jours)).isoformat()
    return [dict(zip(("titre", "debut", "fin", "lieu", "journee"), l)) for l in base.lire_tous(
        "SELECT titre, debut, fin, lieu, journee FROM connecteurs_agenda WHERE athlete_id=? AND debut>=? AND debut<? "
        "ORDER BY debut", (athlete_id, d0, d1))]


def fatigue_par_jour(athlete_id, debut=None, jours=14):
    """[{jour, heures, bonus, chargee}] : temps pris par l'agenda chaque jour et bonus de fatigue (0 à 2)."""
    evts = agenda(athlete_id, debut, jours)
    heures = R.charge_agenda_par_jour(evts)
    d0 = date.fromisoformat((debut or date.today().isoformat())[:10])
    res = []
    for i in range(jours):
        j = (d0 + timedelta(days=i)).isoformat()
        h = heures.get(j, 0)
        b = R.fatigue_agenda(h)
        res.append({"jour": j, "heures": h, "bonus": b, "chargee": b > 0,
                    "creneaux": R.creneaux_libres(evts, j)})
    return res


def parcours(athlete_id, favoris=False):
    sql = ("SELECT id, source, externe_id, nom, lieu, distance_m, denivele_m, difficulte, type_parcours, note, lien, "
           "lat, lon, meteo, recu_le, favori FROM connecteurs_parcours WHERE athlete_id=?")
    if favoris:
        sql += " AND favori=1"
    cols = ("id", "source", "externe_id", "nom", "lieu", "distance_m", "denivele_m", "difficulte", "type_parcours",
            "note", "lien", "lat", "lon", "meteo", "recu_le", "favori")
    return [dict(zip(cols, l)) for l in base.lire_tous(sql + " ORDER BY favori DESC, recu_le DESC, nom", (athlete_id,))]


def basculer_favori(parcours_id):
    base.ecrire("UPDATE connecteurs_parcours SET favori=1-ifnull(favori,0) WHERE id=?", (parcours_id,))


def securite(athlete_id, limite=30):
    cols = ("trajet", "date", "niveau", "resume", "details", "lien")
    return [dict(zip(cols, l)) for l in base.lire_tous(
        "SELECT trajet, date, niveau, resume, details, lien FROM connecteurs_securite WHERE athlete_id=? "
        "ORDER BY date DESC, id DESC LIMIT ?", (athlete_id, limite))]


def playlists(athlete_id):
    cols = ("nom", "lien", "duree_min", "seance", "cree_le")
    return [dict(zip(cols, l)) for l in base.lire_tous(
        "SELECT nom, lien, duree_min, seance, cree_le FROM connecteurs_playlists WHERE athlete_id=? "
        "ORDER BY cree_le DESC, id DESC", (athlete_id,))]


def activites_recues(athlete_id, limite=30):
    cols = ("id", "date", "nom", "type", "distance", "denivele", "duree", "source")
    return [dict(zip(cols, l)) for l in base.lire_tous(
        "SELECT id, date, nom, type, distance, denivele, duree, source FROM activites WHERE athlete_id=? "
        "AND source LIKE '%(connecteur)' ORDER BY date DESC LIMIT ?", (athlete_id, limite))]


def seances_prevues(athlete_id):
    """Séances structurées prévues (aujourd'hui et après) qu'on peut envoyer à la montre."""
    cols = ("id", "nom", "type_seance", "date_prevue", "statut", "etapes_json")
    res = []
    for l in base.lire_tous(
            "SELECT id, nom, type_seance, date_prevue, statut, etapes_json FROM seances_structurees "
            "WHERE athlete_id=? AND ifnull(date_prevue,'')>=? ORDER BY date_prevue LIMIT 60",
            (athlete_id, date.today().isoformat())):
        s = dict(zip(cols, l))
        try:
            s["etapes"] = json.loads(s.pop("etapes_json") or "[]")
        except ValueError:
            s["etapes"] = []
        s["duree_min"] = R.duree_seance_min(s["etapes"])
        res.append(s)
    return res


def bilan_semaine():
    from data.database import obtenir_parametre
    t = obtenir_parametre("connecteurs_bilan_semaine")
    return {"texte": t, "date": obtenir_parametre("connecteurs_bilan_semaine_date")} if t else None


# ------------------------------------------------------------------ demandes

COL_DEMANDE = ("id", "cle", "athlete_id", "type", "titre", "parametres_json", "statut", "cree_le", "traite_le",
               "message", "lien")


def _demande(l):
    d = dict(zip(COL_DEMANDE, l))
    try:
        d["parametres"] = json.loads(d.pop("parametres_json") or "{}")
    except ValueError:
        d["parametres"] = {}
    d["type_libelle"] = R.TYPES_DEMANDE.get(d["type"], d["type"])
    d["statut_libelle"] = R.STATUTS_DEMANDE.get(d["statut"], d["statut"])
    return d


def creer_demande(athlete_id, type_, titre, parametres):
    if type_ not in R.TYPES_DEMANDE:
        raise ErreurConnecteurs(f"Type de demande inconnu : {type_}")
    cle = uuid.uuid4().hex[:16]
    base.ecrire("INSERT INTO connecteurs_demandes (cle, athlete_id, type, titre, parametres_json, statut, cree_le) "
                "VALUES (?,?,?,?,?,'a_faire',?)",
                (cle, athlete_id, type_, (titre or R.TYPES_DEMANDE[type_])[:200],
                 json.dumps(parametres or {}, ensure_ascii=False), _maintenant()))
    return cle


def demandes(statuts=None, limite=200):
    sql = f"SELECT {', '.join(COL_DEMANDE)} FROM connecteurs_demandes"
    params = []
    if statuts:
        sql += f" WHERE statut IN ({','.join('?' * len(statuts))})"
        params = list(statuts)
    return [_demande(l) for l in base.lire_tous(sql + " ORDER BY cree_le DESC, id DESC LIMIT ?", (*params, limite))]


def demandes_en_attente():
    return list(reversed(demandes(("a_faire", "envoyee"))))


def marquer_envoyees(cles):
    for c in cles:
        base.ecrire("UPDATE connecteurs_demandes SET statut='envoyee' WHERE cle=? AND statut='a_faire'", (c,))


def annuler_demande(cle):
    base.ecrire("UPDATE connecteurs_demandes SET statut='annulee', traite_le=? WHERE cle=? "
                "AND statut IN ('a_faire','envoyee')", (_maintenant(), cle))


def supprimer_demande(cle):
    base.ecrire("DELETE FROM connecteurs_demandes WHERE cle=?", (cle,))


# --- demandes toutes faites

def demander_seance_montre(athlete_id, seance):
    """`seance` : dict de seances_prevues (nom, date_prevue, etapes). Vérifie que la séance se convertit."""
    workout = R.seance_vers_running_workout(seance["nom"], seance.get("etapes"), seance.get("type_seance"))
    return creer_demande(athlete_id, "seance_montre", f"⌚ {seance['nom']} — {seance.get('date_prevue') or 'sans date'}",
                         {"workout": workout, "scheduledDate": (seance.get("date_prevue") or "")[:10] or None,
                          "seance_id": seance.get("id")})


def demander_agenda(athlete_id, titre, debut, fin, lieu=None, description=None):
    d, f = R.date_locale(debut), R.date_locale(fin)
    if not d or not f or f <= d:
        raise ErreurConnecteurs("Indique une heure de début et une heure de fin valables.")
    return creer_demande(athlete_id, "agenda", f"📅 {titre} — {d[:16]}",
                         {"summary": titre, "startTime": d.replace(" ", "T"), "endTime": f.replace(" ", "T"),
                          "location": lieu, "description": description})


def demander_playlist(athlete_id, nom_seance, duree_min, style=None, rythme=None):
    prompt = R.prompt_playlist(nom_seance, duree_min, style or "funk et disco des années 80 et 90", rythme)
    return creer_demande(athlete_id, "playlist", f"🎵 {nom_seance} ({duree_min} min)",
                         {"prompt": prompt, "language": "fr-FR", "seance": nom_seance, "duree_min": duree_min})


def demander_parcours(athlete_id, lieu, lat, lon, distance_km=None, denivele_m=None, rayon_km=20):
    filtres = {"activity": ["trail-running"]}
    if distance_km:
        filtres["length"] = {"min": max(1000, distance_km * 1000 * 0.75), "max": distance_km * 1000 * 1.25}
    if denivele_m:
        filtres["elevation_gain"] = {"min": max(0, denivele_m * 0.7), "max": denivele_m * 1.3}
    return creer_demande(athlete_id, "parcours", f"🗺️ Parcours autour de {lieu}",
                         {"lieu": lieu, "latitude": lat, "longitude": lon, "max_radius_meters": int(rayon_km * 1000),
                          "filters": filtres, "locale": "fr-FR", "meteo": True})


def demander_securite(athlete_id, depart, arrivee, jour=None):
    return creer_demande(athlete_id, "securite", f"🛡️ {depart} → {arrivee}",
                         {"from": depart, "to": arrivee, "date": jour or date.today().isoformat(),
                          "feux": True, "hiver": True})
