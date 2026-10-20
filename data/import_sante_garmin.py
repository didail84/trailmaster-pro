"""
Import des données de SANTÉ quotidienne d'un export Garmin Connect
("Exporter vos données") : FC de repos, HRV de nuit, sommeil (durée,
phases, score), Body Battery, stress, SpO₂.

Ces données alimentent la table `recuperation_quotidienne` (une ligne par
jour où la montre a été portée — les jours sans port n'ont simplement pas
de ligne) et sont aussi recopiées, quand c'est utile, dans les tables
existantes `sommeil` et `signaux_recuperation` pour que l'indice de forme
du tableau de bord en profite.

Le dossier d'export de Garmin varie selon la montre, le firmware et la
date de l'export : les noms de fichiers et de champs ne sont donc PAS
supposés figés. Le lecteur est volontairement tolérant :
  - il accepte un DOSSIER (parcouru récursivement) ou un fichier .ZIP
    (lu sans extraction) ;
  - il retient tous les .json dont le nom évoque le sommeil, le résumé
    quotidien (UDSFile), la santé / la HRV ;
  - pour chaque mesure, il cherche plusieurs noms de champ possibles,
    à n'importe quelle profondeur ;
  - chaque valeur est contrôlée (plage plausible) avant d'être gardée ;
  - le compte rendu dit précisément ce qui a été trouvé ou non.
Rien n'est écrasé : une valeur déjà en base n'est jamais remplacée.
"""

import json
import os
import re
import zipfile
from datetime import datetime

from data.database import connexion

# Fichiers retenus (comparaison sur le nom en minuscules).
MOTIFS_FICHIERS = ("sleepdata", "udsfile", "healthstatus", "hrv", "wellness", "dailysummary")

# mesure -> (noms de champ possibles, plage plausible, type)
CHAMPS = {
    "fc_repos": (("restingHeartRate", "restingHeartRateValue", "restingHR"), (30, 110), int),
    "fc_min": (("minHeartRate",), (25, 120), int),
    "hrv_nuit_ms": (("avgOvernightHrv", "lastNightAvg", "overnightHrv"), (8, 300), float),
    "stress_moyen": (("averageStressLevel", "avgStressLevel", "overallStressLevel"), (0, 100), int),
    "sommeil_score": (("overallScore", "sleepScore", "overallSleepScore"), (0, 100), int),
    "spo2_moyenne": (("averageSPO2", "averageSpO2", "avgSpO2", "spo2Avg"), (70, 100), float),
    "body_battery_max": (("bodyBatteryHighestValue", "highestBodyBattery", "bodyBatteryMax",
                          "bodyBatteryHighest"), (0, 100), int),
    "body_battery_min": (("bodyBatteryLowestValue", "lowestBodyBattery", "bodyBatteryMin",
                          "bodyBatteryLowest"), (0, 100), int),
}
STATUTS_HRV = ("hrvStatus", "hrvStatusType")
SECONDES = {
    "sommeil_profond_min": ("deepSleepSeconds",),
    "sommeil_leger_min": ("lightSleepSeconds",),
    "sommeil_paradoxal_min": ("remSleepSeconds",),
    "sommeil_eveil_min": ("awakeSleepSeconds",),
}
TOUTES_MESURES = (
    list(CHAMPS) + list(SECONDES) + ["hrv_statut", "sommeil_duree_h"]
)


# ------------------------------------------------------------------
# OUTILS DE RECHERCHE TOLÉRANTE
# ------------------------------------------------------------------

def _chercher(objet, noms, profondeur=0):
    """Premier champ portant l'un des `noms` (insensible à la casse),
    à n'importe quelle profondeur raisonnable. Si la valeur est un
    dict du type {"value": 82}, on prend sa clé "value"."""
    if profondeur > 5:
        return None
    cles = {n.lower() for n in noms}
    if isinstance(objet, dict):
        for k, v in objet.items():
            if k.lower() in cles:
                if isinstance(v, dict):
                    v = v.get("value", v.get("qualifierKey"))
                if v is not None and not isinstance(v, (dict, list)):
                    return v
        for v in objet.values():
            if isinstance(v, (dict, list)):
                r = _chercher(v, noms, profondeur + 1)
                if r is not None:
                    return r
    elif isinstance(objet, list):
        for v in objet[:50]:
            r = _chercher(v, noms, profondeur + 1)
            if r is not None:
                return r
    return None


def _nombre(valeur, plage, type_):
    try:
        x = float(valeur)
    except (TypeError, ValueError):
        return None
    if not (plage[0] <= x <= plage[1]):
        return None
    return int(round(x)) if type_ is int else round(x, 1)


def _date(valeur):
    """'2026-09-20', '2026-09-20T05:10:00.0', timestamp ms -> 'YYYY-MM-DD'."""
    if valeur is None:
        return None
    if isinstance(valeur, (int, float)):
        try:
            ts = valeur / 1000 if valeur > 1e11 else valeur
            d = datetime.utcfromtimestamp(ts)
        except (OverflowError, OSError, ValueError):
            return None
        return d.strftime("%Y-%m-%d") if 2000 <= d.year <= 2100 else None
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})", str(valeur).strip())
    if m and 2000 <= int(m.group(1)) <= 2100:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    return None


def _date_enregistrement(rec):
    for cle in ("calendarDate", "summaryDate", "date", "startDate", "sleepDate"):
        for k, v in rec.items():
            if k.lower() == cle.lower():
                d = _date(v)
                if d:
                    return d
    # En dernier recours : fin de nuit (horodatage), date du réveil.
    for cle in ("sleepEndTimestampGMT", "sleepEndTimestampLocal", "sleepStartTimestampLocal"):
        if cle in rec:
            d = _date(rec[cle])
            if d:
                return d
    return None


def _body_battery(rec):
    """Valeurs max/min depuis une liste de statistiques éventuelle."""
    haut = bas = None
    liste = _chercher_liste(rec, "bodyBatteryStatList")
    for e in liste or []:
        if not isinstance(e, dict):
            continue
        t = str(e.get("bodyBatteryStatType", "")).upper()
        v = e.get("statsValue")
        if t == "HIGHEST":
            haut = v
        elif t == "LOWEST":
            bas = v
    return haut, bas


def _chercher_liste(objet, nom, profondeur=0):
    if profondeur > 4 or not isinstance(objet, dict):
        return None
    for k, v in objet.items():
        if k.lower() == nom.lower() and isinstance(v, list):
            return v
    for v in objet.values():
        if isinstance(v, dict):
            r = _chercher_liste(v, nom, profondeur + 1)
            if r is not None:
                return r
    return None


def _extraire_jour(rec):
    """Mesures d'un enregistrement quotidien -> dict (valeurs plausibles seules)."""
    sortie = {}
    for mesure, (noms, plage, type_) in CHAMPS.items():
        v = _nombre(_chercher(rec, noms), plage, type_)
        if v is not None:
            sortie[mesure] = v

    haut, bas = _body_battery(rec)
    if "body_battery_max" not in sortie:
        v = _nombre(haut, (0, 100), int)
        if v is not None:
            sortie["body_battery_max"] = v
    if "body_battery_min" not in sortie:
        v = _nombre(bas, (0, 100), int)
        if v is not None:
            sortie["body_battery_min"] = v

    total_s = 0
    for mesure, noms in SECONDES.items():
        s = _nombre(_chercher(rec, noms), (0, 86400), float)
        if s is not None:
            sortie[mesure] = int(round(s / 60))
            if mesure != "sommeil_eveil_min":
                total_s += s
    if total_s > 0:
        h = round(total_s / 3600, 2)
        if 1 <= h <= 16:
            sortie["sommeil_duree_h"] = h
    else:
        s = _nombre(_chercher(rec, ("sleepTimeSeconds",)), (3600, 57600), float)
        if s is not None:
            sortie["sommeil_duree_h"] = round(s / 3600, 2)

    statut = _chercher(rec, STATUTS_HRV)
    if isinstance(statut, str) and statut.strip():
        sortie["hrv_statut"] = statut.strip()[:30]
    return sortie


def _enregistrements(donnees):
    """Liste des dicts "un jour" d'un JSON (liste, ou dict contenant une liste)."""
    if isinstance(donnees, list):
        recs = []
        for e in donnees:
            if isinstance(e, dict):
                recs.append(e)
        # liste d'un seul dict-enveloppe (ex. [{"xxxExport": [...]}])
        if len(recs) == 1:
            for v in recs[0].values():
                if isinstance(v, list) and v and isinstance(v[0], dict):
                    return [r for r in v if isinstance(r, dict)]
        return recs
    if isinstance(donnees, dict):
        for v in donnees.values():
            if isinstance(v, list) and v and isinstance(v[0], dict):
                return [r for r in v if isinstance(r, dict)]
        return [donnees]
    return []


# ------------------------------------------------------------------
# LECTURE D'UN DOSSIER / ZIP
# ------------------------------------------------------------------

def _fichiers_json(source):
    """Génère (nom, contenu_bytes) des .json retenus."""
    if os.path.isdir(source):
        for racine, _, fichiers in os.walk(source):
            for f in fichiers:
                bas = f.lower()
                if bas.endswith(".json") and any(m in bas for m in MOTIFS_FICHIERS):
                    chemin = os.path.join(racine, f)
                    try:
                        with open(chemin, "rb") as fh:
                            yield f, fh.read()
                    except OSError:
                        continue
    elif zipfile.is_zipfile(source):
        with zipfile.ZipFile(source) as z:
            for info in z.infolist():
                bas = info.filename.lower()
                if bas.endswith(".json") and any(m in os.path.basename(bas) for m in MOTIFS_FICHIERS):
                    try:
                        yield os.path.basename(info.filename), z.read(info)
                    except (OSError, zipfile.BadZipFile):
                        continue
                elif bas.endswith(".zip"):
                    # export Garmin = zip contenant d'autres zips
                    try:
                        import io
                        with zipfile.ZipFile(io.BytesIO(z.read(info))) as z2:
                            for i2 in z2.infolist():
                                b2 = i2.filename.lower()
                                if b2.endswith(".json") and any(m in os.path.basename(b2) for m in MOTIFS_FICHIERS):
                                    yield os.path.basename(i2.filename), z2.read(i2)
                    except (OSError, zipfile.BadZipFile):
                        continue


def lire_sante(source):
    """-> (jours, fichiers_lus). jours = {date: {mesure: valeur}} fusionnés
    entre tous les fichiers (première valeur valide gardée)."""
    jours = {}
    fichiers_lus = 0
    for nom, brut in _fichiers_json(source):
        try:
            donnees = json.loads(brut.decode("utf-8-sig", errors="replace"))
        except ValueError:
            continue
        fichiers_lus += 1
        for rec in _enregistrements(donnees):
            d = _date_enregistrement(rec)
            if d is None:
                continue
            mesures = _extraire_jour(rec)
            if not mesures:
                continue
            cible = jours.setdefault(d, {})
            for k, v in mesures.items():
                cible.setdefault(k, v)
    return jours, fichiers_lus


# ------------------------------------------------------------------
# ÉCRITURE EN BASE
# ------------------------------------------------------------------

def enregistrer_sante(athlete_id, jours):
    """Insère / complète recuperation_quotidienne, et recopie sommeil et
    HRV/stress dans les tables que l'indice de forme lit déjà.
    Retourne un dict de compte rendu."""
    conn = connexion()
    cur = conn.cursor()
    ajoutes = completes = 0
    sommeil_copies = signaux_copies = 0
    try:
        for date, m in sorted(jours.items()):
            cur.execute(
                "SELECT id FROM recuperation_quotidienne WHERE athlete_id=? AND date=?",
                (athlete_id, date),
            )
            ligne = cur.fetchone()
            if ligne is None:
                colonnes = ["athlete_id", "date"] + [k for k in m if k in TOUTES_MESURES]
                valeurs = [athlete_id, date] + [m[k] for k in m if k in TOUTES_MESURES]
                cur.execute(
                    f"INSERT INTO recuperation_quotidienne ({', '.join(colonnes)}) "
                    f"VALUES ({', '.join('?' * len(colonnes))})",
                    valeurs,
                )
                ajoutes += 1
            else:
                id_ = ligne[0]
                maj = 0
                for k, v in m.items():
                    if k not in TOUTES_MESURES:
                        continue
                    cur.execute(
                        f"UPDATE recuperation_quotidienne SET {k}=? WHERE id=? AND {k} IS NULL",
                        (v, id_),
                    )
                    maj += cur.rowcount
                completes += 1 if maj else 0

            # --- recopie dans `sommeil` (durée + qualité 1-5) si la nuit n'existe pas
            if m.get("sommeil_duree_h"):
                cur.execute(
                    "SELECT 1 FROM sommeil WHERE athlete_id=? AND date=?", (athlete_id, date)
                )
                if cur.fetchone() is None:
                    qualite = None
                    if m.get("sommeil_score") is not None:
                        qualite = max(1, min(5, round(m["sommeil_score"] / 20)))
                    cur.execute(
                        "INSERT INTO sommeil (athlete_id, date, duree_heures, qualite, notes) "
                        "VALUES (?, ?, ?, ?, ?)",
                        (athlete_id, date, m["sommeil_duree_h"], qualite, "Import santé Garmin"),
                    )
                    sommeil_copies += 1

            # --- recopie HRV / stress dans `signaux_recuperation`
            if m.get("hrv_nuit_ms") is not None or m.get("stress_moyen") is not None:
                cur.execute(
                    "SELECT 1 FROM signaux_recuperation "
                    "WHERE athlete_id=? AND date=? AND source_fichier='Garmin santé'",
                    (athlete_id, date),
                )
                if cur.fetchone() is None:
                    cur.execute(
                        "INSERT INTO signaux_recuperation "
                        "(athlete_id, date, hrv_ms, stress_moyen, source_fichier) "
                        "VALUES (?, ?, ?, ?, 'Garmin santé')",
                        (athlete_id, date, m.get("hrv_nuit_ms"), m.get("stress_moyen")),
                    )
                    signaux_copies += 1
        conn.commit()
    finally:
        conn.close()
    return {
        "jours": len(jours), "ajoutes": ajoutes, "completes": completes,
        "sommeil_copies": sommeil_copies, "signaux_copies": signaux_copies,
    }


def importer_sante(athlete_id, source):
    """Tout-en-un. Retourne le compte rendu avec, en plus, le détail des
    mesures trouvées (nombre de jours par mesure) pour que l'écran puisse
    dire clairement ce que contient (ou non) l'export."""
    jours, fichiers_lus = lire_sante(source)
    bilan = enregistrer_sante(athlete_id, jours)
    bilan["fichiers"] = fichiers_lus
    trouvees = {}
    for m in jours.values():
        for k in m:
            trouvees[k] = trouvees.get(k, 0) + 1
    bilan["mesures"] = trouvees
    if jours:
        bilan["premier"], bilan["dernier"] = min(jours), max(jours)
    return bilan


LIBELLES_MESURES = {
    "fc_repos": "FC de repos", "fc_min": "FC minimale",
    "hrv_nuit_ms": "HRV de nuit", "hrv_statut": "statut HRV",
    "stress_moyen": "stress", "sommeil_score": "score de sommeil",
    "sommeil_duree_h": "durée de sommeil", "sommeil_profond_min": "sommeil profond",
    "sommeil_leger_min": "sommeil léger", "sommeil_paradoxal_min": "sommeil paradoxal",
    "sommeil_eveil_min": "éveils", "spo2_moyenne": "SpO₂",
    "body_battery_max": "Body Battery max", "body_battery_min": "Body Battery min",
}
