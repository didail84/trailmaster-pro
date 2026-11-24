"""
Import d'un paquet « Connecteurs Claude » dans la base, sans doublon.

  - sorties Strava / Garmin : une sortie déjà connue (même identifiant, ou même
    heure à quelques minutes près et même distance, quelle que soit sa source)
    est seulement complétée ; les nouvelles reçoivent ensuite leur analyse
    automatique (événement « données modifiées ») ;
  - récupération (sommeil, VFC, FC de repos, stress, Body Battery) : mêmes
    tables que la synchro Garmin, via import_sante_garmin.enregistrer_sante ;
  - records, charge, agenda, parcours, sécurité, playlists : tables
    connecteurs_* ; matériel : table `materiel` (repère « strava:ID ») ;
  - courses trouvées dans les mails : « Courses à venir » ;
  - analyses écrites par Claude : table analyses_ia, rattachées à la sortie ;
  - demandes traitées : statut mis à jour (séance envoyée, playlist créée…).

Un paquet déjà importé (même contenu) est ignoré.
"""

import json
from datetime import datetime

from noyau.donnees import base
from noyau.connecteurs import regles as R
from noyau.outils.evenements import emettre, DONNEES_MODIFIEES

PREFIXE_ANALYSE = "🤖 Analyse de Claude (connecteurs)\n\n"
FENETRE_MINUTES = 10


def _maintenant():
    return datetime.now().isoformat(timespec="seconds")


def deja_importe(empreinte):
    return base.lire_un("SELECT id FROM connecteurs_paquets WHERE empreinte=?", (empreinte,)) is not None


def _activite_connue(cur, athlete_id, a):
    cur.execute("SELECT id FROM activites WHERE athlete_id=? AND identifiant_externe=? "
                "AND (source LIKE 'Strava%' OR source LIKE 'Garmin%')", (athlete_id, a["id_externe"]))
    l = cur.fetchone()
    if l:
        return l[0]
    cible = datetime.fromisoformat(a["date"])
    cur.execute("SELECT id, date, distance FROM activites WHERE athlete_id=? AND date LIKE ?",
                (athlete_id, a["date"][:10] + "%"))
    for aid, d, dist in cur.fetchall():
        try:
            dd = datetime.fromisoformat(str(d)[:19].replace("T", " "))
        except ValueError:
            continue
        if abs((dd - cible).total_seconds()) / 60 > FENETRE_MINUTES:
            continue
        if dist is None or abs((dist or 0) - a["distance"]) <= max(0.3, a["distance"] * 0.1):
            return aid
    return None


def _importer_activites(cur, athlete_id, activites, bilan, ids_par_externe):
    from noyau.imports.completer_activites import completer_activite
    for a in activites:
        extra = {k: a[k] for k in ("vitesse_moyenne", "allure_moyenne", "frequence_cardiaque_moyenne",
                                   "frequence_cardiaque_max", "calories", "vitesse_max", "allure_max",
                                   "cadence_moyenne") if a.get(k) is not None}
        if a.get("effort_relatif"):
            extra["suffer_score"] = a["effort_relatif"]
        connu = _activite_connue(cur, athlete_id, a)
        if connu is not None:
            if completer_activite(cur, connu, {"distance": a["distance"], "denivele": a["denivele"],
                                              "duree": a["duree"], **extra}):
                bilan["activites_completees"] += 1
            ids_par_externe[a["id_externe"]] = connu
            continue
        notes = f"Reçue par les connecteurs Claude ({a['lieu']})" if a.get("lieu") else "Reçue par les connecteurs Claude"
        cur.execute(
            "INSERT INTO activites (athlete_id, date, nom, type, distance, denivele, duree, source, "
            "identifiant_externe, notes) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (athlete_id, a["date"], a["nom"], a["type"], a["distance"], a["denivele"], a["duree"],
             R.SOURCES_ACTIVITE[a["source"]], a["id_externe"], notes))
        nouvel = cur.lastrowid
        completer_activite(cur, nouvel, extra)
        ids_par_externe[a["id_externe"]] = nouvel
        bilan["activites_nouvelles"] += 1


def _importer_materiel(cur, athlete_id, materiel, bilan):
    for m in materiel:
        ident = R._texte(m.get("id"), 40)
        if not ident:
            continue
        repere = f"strava:{ident}"
        dist = R._nb(m.get("distance_m")) or 0
        km = round(dist / 1000, 1)
        type_ = "Chaussures" if str(m.get("type", "")).lower() == "shoe" else "Vélo"
        statut = "Retiré" if m.get("retire") else "Actif"
        cur.execute("SELECT id FROM materiel WHERE athlete_id=? AND notes LIKE ?", (athlete_id, f"%{repere}%"))
        l = cur.fetchone()
        if l:
            cur.execute("UPDATE materiel SET km_actuels=?, statut=? WHERE id=?", (km, statut, l[0]))
        else:
            cur.execute("INSERT INTO materiel (athlete_id, nom, type, km_actuels, km_max_recommande, statut, notes) "
                        "VALUES (?,?,?,?,?,?,?)",
                        (athlete_id, R.nom_materiel(m), type_, km,
                         R.USURE_CHAUSSURE_KM if type_ == "Chaussures" else None, statut,
                         f"Kilométrage suivi par Strava ({repere})"))
        bilan["materiel"] += 1


def _importer_records(cur, athlete_id, records, bilan):
    for r in records:
        sport, type_ = R._texte(r.get("sport"), 30), R._texte(r.get("type"), 40)
        v = R._nb(r.get("valeur"))
        if not sport or not type_ or v is None:
            continue
        cur.execute("SELECT valeur, date FROM connecteurs_records WHERE athlete_id=? AND sport=? AND type=?",
                    (athlete_id, sport, type_))
        l = cur.fetchone()
        nouveau = (v, R.jour(r.get("date")))
        if l and (l[0], l[1]) == nouveau:
            continue
        cur.execute("INSERT INTO connecteurs_records (athlete_id, sport, type, valeur, unite, date, activite_externe, "
                    "recu_le) VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(athlete_id, sport, type) DO UPDATE SET "
                    "valeur=excluded.valeur, unite=excluded.unite, date=excluded.date, "
                    "activite_externe=excluded.activite_externe, recu_le=excluded.recu_le",
                    (athlete_id, sport, type_, v, R._texte(r.get("unite"), 20), nouveau[1],
                     R._texte(r.get("activite_externe"), 40), _maintenant()))
        bilan["records"] += 1


def _importer_agenda(cur, athlete_id, agenda, bilan):
    for e in agenda:
        debut = R.date_locale(e.get("debut"))
        if not debut:
            continue
        cle = R._texte(e.get("cle"), 200) or f"{debut}|{R._texte(e.get('titre'), 80)}"
        cur.execute("INSERT INTO connecteurs_agenda (athlete_id, cle, titre, debut, fin, lieu, journee) "
                    "VALUES (?,?,?,?,?,?,?) ON CONFLICT(athlete_id, cle) DO UPDATE SET titre=excluded.titre, "
                    "debut=excluded.debut, fin=excluded.fin, lieu=excluded.lieu, journee=excluded.journee",
                    (athlete_id, cle, R._texte(e.get("titre"), 200), debut, R.date_locale(e.get("fin")),
                     R._texte(e.get("lieu"), 200), 1 if e.get("journee") else 0))
        bilan["agenda"] += 1


def _importer_courses(cur, athlete_id, courses, bilan):
    for c in courses:
        nom, d = R._texte(c.get("nom"), 200), R.jour(c.get("date"))
        if not nom:
            continue
        cur.execute("SELECT id FROM courses_calendrier WHERE athlete_id=? AND lower(nom)=lower(?) "
                    "AND ifnull(date,'')=ifnull(?, '')", (athlete_id, nom, d))
        if cur.fetchone():
            continue
        notes = "Trouvée dans tes mails par Claude"
        if c.get("sujet"):
            notes += f" (« {R._texte(c['sujet'], 150)} »)"
        cur.execute("INSERT INTO courses_calendrier (athlete_id, nom, date, lieu, distance_km, denivele_m, lien, "
                    "source, notes) VALUES (?,?,?,?,?,?,?,?,?)",
                    (athlete_id, nom, d, R._texte(c.get("lieu"), 120), R._nb(c.get("distance_km")),
                     int(R._nb(c.get("denivele_m"))) if R._nb(c.get("denivele_m")) else None,
                     R.lien_sur(c.get("lien")), "Gmail (connecteur)", notes))
        bilan["courses"] += 1


def _importer_parcours(cur, athlete_id, parcours, bilan):
    for p in parcours:
        ident = R._texte(p.get("id"), 60)
        if not ident:
            continue
        meteo = p.get("meteo")
        if isinstance(meteo, (dict, list)):
            meteo = json.dumps(meteo, ensure_ascii=False)
        cur.execute(
            "INSERT INTO connecteurs_parcours (athlete_id, source, externe_id, nom, lieu, distance_m, denivele_m, "
            "difficulte, type_parcours, note, lien, lat, lon, meteo, recu_le) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) "
            "ON CONFLICT(athlete_id, source, externe_id) DO UPDATE SET nom=excluded.nom, lieu=excluded.lieu, "
            "distance_m=excluded.distance_m, denivele_m=excluded.denivele_m, difficulte=excluded.difficulte, "
            "type_parcours=excluded.type_parcours, note=excluded.note, lien=excluded.lien, lat=excluded.lat, "
            "lon=excluded.lon, meteo=coalesce(excluded.meteo, connecteurs_parcours.meteo), recu_le=excluded.recu_le",
            (athlete_id, R._texte(p.get("source"), 30) or "AllTrails", ident, R._texte(p.get("nom"), 200),
             R._texte(p.get("lieu"), 200), R._nb(p.get("distance_m")), R._nb(p.get("denivele_m")),
             R._texte(p.get("difficulte"), 30), R._texte(p.get("type_parcours"), 30), R._nb(p.get("note")),
             R.lien_sur(p.get("lien")), R._nb(p.get("lat")), R._nb(p.get("lon")), R._texte(meteo, 2000),
             _maintenant()))
        bilan["parcours"] += 1


def _importer_securite(cur, athlete_id, securite, bilan):
    for s in securite:
        trajet, d = R._texte(s.get("trajet"), 200), R.jour(s.get("date")) or datetime.now().date().isoformat()
        if not trajet:
            continue
        cur.execute("INSERT INTO connecteurs_securite (athlete_id, trajet, date, niveau, resume, details, lien) "
                    "VALUES (?,?,?,?,?,?,?) ON CONFLICT(athlete_id, trajet, date) DO UPDATE SET niveau=excluded.niveau, "
                    "resume=excluded.resume, details=excluded.details, lien=excluded.lien",
                    (athlete_id, trajet, d, R._texte(s.get("niveau"), 30), R._texte(s.get("resume"), 1000),
                     R._texte(s.get("details"), 4000), R.lien_sur(s.get("lien"))))
        bilan["securite"] += 1


def _importer_playlists(cur, athlete_id, playlists, bilan):
    for p in playlists:
        nom = R._texte(p.get("nom"), 200)
        if not nom:
            continue
        cur.execute("INSERT OR IGNORE INTO connecteurs_playlists (athlete_id, nom, lien, duree_min, seance, cree_le) "
                    "VALUES (?,?,?,?,?,?)",
                    (athlete_id, nom, R.lien_sur(p.get("lien")),
                     int(R._nb(p.get("duree_min"))) if R._nb(p.get("duree_min")) else None,
                     R._texte(p.get("seance"), 200), _maintenant()))
        bilan["playlists"] += cur.rowcount


def _importer_analyses(cur, athlete_id, analyses, ids_par_externe, bilan):
    for a in analyses:
        ident, texte = R._texte(a.get("id_externe"), 60), R._texte(a.get("texte"), 6000)
        if not ident or not texte:
            continue
        aid = ids_par_externe.get(ident)
        if aid is None:
            cur.execute("SELECT id FROM activites WHERE athlete_id=? AND identifiant_externe=?", (athlete_id, ident))
            l = cur.fetchone()
            aid = l[0] if l else None
        if aid is None:
            continue
        contenu = PREFIXE_ANALYSE + texte
        cur.execute("SELECT 1 FROM analyses_ia WHERE activite_id=? AND contenu=?", (aid, contenu))
        if cur.fetchone():
            continue
        cur.execute("INSERT INTO analyses_ia (athlete_id, activite_id, date_generation, contenu) VALUES (?,?,?,?)",
                    (athlete_id, aid, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), contenu))
        bilan["analyses"] += 1


def _importer_demandes_traitees(cur, traitees, bilan):
    for d in traitees:
        cle = R._texte(d.get("cle"), 80)
        statut = d.get("statut") if d.get("statut") in ("fait", "erreur") else None
        if not cle or not statut:
            continue
        cur.execute("UPDATE connecteurs_demandes SET statut=?, traite_le=?, message=?, lien=? WHERE cle=? "
                    "AND statut IN ('a_faire', 'envoyee')",
                    (statut, _maintenant(), R._texte(d.get("message"), 1000), R.lien_sur(d.get("lien")), cle))
        bilan["demandes"] += cur.rowcount


def importer(paquet, athlete_id, fichier=None, forcer=False):
    """Importe un paquet (dict brut ou texte JSON) pour le coureur `athlete_id`. Retourne le bilan (dict) ;
    bilan['deja'] vaut True si ce paquet avait déjà été importé."""
    if athlete_id is None:
        raise R.ErreurConnecteurs("Choisis d'abord le coureur à qui appartiennent ces données.")
    brut = paquet
    if isinstance(paquet, (bytes, str)):
        brut = json.loads(paquet) if paquet else {}
    p = R.lire_paquet(brut)
    emp = R.empreinte(brut)
    bilan = {k: 0 for k in ("activites_nouvelles", "activites_completees", "sante_jours", "records", "materiel",
                            "courses", "agenda", "parcours", "securite", "playlists", "analyses", "demandes")}
    bilan.update(deja=False, charge=None, cree_le=p["cree_le"])
    if not forcer and deja_importe(emp):
        bilan["deja"] = True
        return bilan

    ids = {}
    with base.transaction() as cur:
        _importer_activites(cur, athlete_id, p["activites"], bilan, ids)
        _importer_materiel(cur, athlete_id, p["materiel"], bilan)
        _importer_records(cur, athlete_id, p["records"], bilan)
        _importer_agenda(cur, athlete_id, p["agenda"], bilan)
        _importer_courses(cur, athlete_id, p["courses_mail"], bilan)
        _importer_parcours(cur, athlete_id, p["parcours"], bilan)
        _importer_securite(cur, athlete_id, p["securite"], bilan)
        _importer_playlists(cur, athlete_id, p["playlists"], bilan)
        _importer_analyses(cur, athlete_id, p["analyses"], ids, bilan)
        _importer_demandes_traitees(cur, p["demandes_traitees"], bilan)
        if p["charge"]:
            c = p["charge"]
            cur.execute("INSERT INTO connecteurs_charge (athlete_id, date, aigue, chronique, acwr, source) "
                        "VALUES (?,?,?,?,?,?) ON CONFLICT(athlete_id, date, source) DO UPDATE SET aigue=excluded.aigue, "
                        "chronique=excluded.chronique, acwr=excluded.acwr",
                        (athlete_id, c["date"], c["aigue"], c["chronique"], c["acwr"], c["source"]))
            bilan["charge"] = c["acwr"]

    if p["sante"]:
        from noyau.imports.import_sante_garmin import enregistrer_sante
        jours = {s["date"]: s["mesures"] for s in p["sante"] if s["mesures"]}
        if jours:
            enregistrer_sante(athlete_id, jours)
            bilan["sante_jours"] = len(jours)
        pas = [(s["date"], s["pas"]) for s in p["sante"] if s.get("pas")]
        if pas:
            with base.transaction() as cur:
                for d, n in pas:
                    cur.execute("INSERT INTO garmin_quotidien (athlete_id, date, pas) VALUES (?,?,?) "
                                "ON CONFLICT(athlete_id, date) DO UPDATE SET pas=coalesce(garmin_quotidien.pas, excluded.pas)",
                                (athlete_id, d, n))

    if p.get("bilan_semaine"):
        from data.database import definir_parametre
        definir_parametre("connecteurs_bilan_semaine", p["bilan_semaine"])
        definir_parametre("connecteurs_bilan_semaine_date", p["cree_le"] or _maintenant())

    base.ecrire("INSERT OR IGNORE INTO connecteurs_paquets (empreinte, fichier, cree_le, importe_le, athlete_id, "
                  "bilan_json) VALUES (?,?,?,?,?,?)",
                  (emp, fichier, p["cree_le"], _maintenant(), athlete_id, json.dumps(bilan, ensure_ascii=False)))
    emettre(DONNEES_MODIFIEES, athlete_id=athlete_id)
    return bilan


def journal(limite=50):
    """Derniers paquets importés : [{fichier, cree_le, importe_le, bilan}]."""
    res = []
    for f, c, i, b in base.lire_tous("SELECT fichier, cree_le, importe_le, bilan_json FROM connecteurs_paquets "
                                     "ORDER BY importe_le DESC, id DESC LIMIT ?", (limite,)):
        try:
            bil = json.loads(b or "{}")
        except ValueError:
            bil = {}
        res.append({"fichier": f, "cree_le": c, "importe_le": i, "bilan": bil, "resume": R.resume_paquet(bil)})
    return res
