"""
Mode « jour de course » : tout ce qu'il faut pour la prochaine course, sur
un seul écran.

  - la course : prochaine course du calendrier ou prochain roadbook daté ;
  - compte à rebours (jours, ou heures le jour J) ;
  - durée visée : temps visé du roadbook, sinon prédiction (VO₂max), sinon
    repère simple (6 min par km-effort) — toujours signalée comme estimation ;
  - sac à préparer : la liste du roadbook (cases cochées gardées), sinon le
    repère de matériel selon distance, dénivelé, nuit et saison ;
  - plan de ravitaillement heure par heure ;
  - météo : la prévision AllTrails reçue par les connecteurs si un parcours
    proche est connu (sinon, l'écran Météo) ;
  - une playlist de la bonne durée, demandée à Claude.
"""

import json
from datetime import date, datetime

from data.database import connexion


def _saison(d):
    return {12: "hiver", 1: "hiver", 2: "hiver", 6: "ete", 7: "ete", 8: "ete"}.get(d.month, "mi-saison")


def prochaine_course(athlete_id, aujourdhui=None):
    """{nom, date, distance_km, denivele_m, lieu, roadbook_id} ou None."""
    aujourdhui = (aujourdhui or date.today()).isoformat()
    conn = connexion()
    try:
        c = conn.execute("SELECT nom, date, distance_km, denivele_m, lieu FROM courses_calendrier "
                         "WHERE (athlete_id=? OR athlete_id IS NULL) AND date>=? ORDER BY date LIMIT 1",
                         (athlete_id, aujourdhui)).fetchone()
        try:
            rb = conn.execute("SELECT id, nom, date_course, distance_km, denivele_m FROM roadbooks "
                              "WHERE athlete_id=? AND date_course>=? ORDER BY date_course LIMIT 1",
                              (athlete_id, aujourdhui)).fetchone()
        except Exception:                       # table créée au premier roadbook
            rb = None
    finally:
        conn.close()
    course = dict(zip(("nom", "date", "distance_km", "denivele_m", "lieu"), c)) if c else None
    if rb and (course is None or (rb[2] or "")[:10] <= (course["date"] or "")[:10]):
        meme = course and (course["date"] or "")[:10] == (rb[2] or "")[:10]
        course = {"nom": rb[1], "date": rb[2], "distance_km": rb[3] or (course or {}).get("distance_km"),
                  "denivele_m": rb[4] or (course or {}).get("denivele_m"), "lieu": (course or {}).get("lieu") if meme else None}
    if course is None:
        return None
    course["roadbook_id"] = rb[0] if rb and (rb[2] or "")[:10] == (course["date"] or "")[:10] else None
    return course


def compte_a_rebours(date_course, maintenant=None):
    maintenant = maintenant or datetime.now()
    try:
        d = datetime.fromisoformat(str(date_course)[:19].replace(" ", "T")) if len(str(date_course)) > 10 \
            else datetime.fromisoformat(str(date_course)[:10])
    except ValueError:
        return {"jours": None, "texte": "Date à préciser"}
    jours = (d.date() - maintenant.date()).days
    if jours > 1:
        return {"jours": jours, "texte": f"J-{jours}"}
    if jours == 1:
        return {"jours": 1, "texte": "Demain"}
    if jours == 0:
        return {"jours": 0, "texte": "C'est aujourd'hui"}
    return {"jours": jours, "texte": "Course passée"}


def _hms_en_h(texte):
    try:
        morceaux = [int(x) for x in str(texte).replace("h", ":").replace("H", ":").split(":") if x.strip()]
    except ValueError:
        return None
    if not morceaux:
        return None
    h = morceaux[0] + (morceaux[1] / 60 if len(morceaux) > 1 else 0) + (morceaux[2] / 3600 if len(morceaux) > 2 else 0)
    return h if 0 < h < 72 else None


def duree_visee(athlete_id, course, roadbook=None):
    """(heures, origine)."""
    if roadbook and roadbook.get("temps_vise"):
        h = _hms_en_h(roadbook["temps_vise"])
        if h:
            return h, "temps visé du roadbook"
    dist, dp = course.get("distance_km") or 0, course.get("denivele_m") or 0
    if dist:
        try:
            from noyau.course.roadbook import duree_depuis_vo2max
            s = duree_depuis_vo2max(athlete_id, dist, dp)
            if s:
                return s / 3600, "estimation d'après ton VO₂max"
        except Exception:
            pass
        return (dist + dp / 100) * 6 / 60, "estimation simple (6 min par km-effort)"
    return None, None


def preparer(athlete_id, aujourdhui=None):
    """Tout l'écran jour de course, ou None s'il n'y a aucune course à venir."""
    course = prochaine_course(athlete_id, aujourdhui)
    if not course:
        return None
    from noyau.course import roadbook as RB
    from noyau.course.ravitaillement import plan_ravitaillement
    rb = RB.charger(course["roadbook_id"]) if course.get("roadbook_id") else None
    jour_course = None
    try:
        jour_course = date.fromisoformat(str(course["date"])[:10])
    except (TypeError, ValueError):
        pass
    heures, origine = duree_visee(athlete_id, course, rb)
    temp = (rb or {}).get("temperature_c")
    plan = plan_ravitaillement(heures, temp, (rb or {}).get("poids_kg") or 70) if heures else None
    if rb and rb.get("checklist"):
        sac = rb["checklist"]
    else:
        sac = RB.construire_checklist(course.get("distance_km") or 10, course.get("denivele_m") or 0,
                                      nocturne=bool((rb or {}).get("nocturne")), altitude=bool((rb or {}).get("altitude")),
                                      saison=_saison(jour_course) if jour_course else None, plan=plan,
                                      existante=_sac_memorise(course))
    return {"course": course, "rebours": compte_a_rebours(course["date"]), "roadbook": rb,
            "duree_h": heures, "origine_duree": origine, "plan": plan, "sac": sac,
            "meteo": meteo_connue(athlete_id, course), "playlist_min": int(round((heures or 1) * 60))}


def meteo_connue(athlete_id, course):
    """Prévision AllTrails d'un parcours reçu dont le lieu ressemble à celui de la course (texte), sinon None."""
    lieu = (course.get("lieu") or "").strip().lower()
    if not lieu:
        return None
    conn = connexion()
    try:
        for nom, l, meteo in conn.execute("SELECT nom, lieu, meteo FROM connecteurs_parcours WHERE athlete_id=? "
                                          "AND meteo IS NOT NULL ORDER BY recu_le DESC", (athlete_id,)):
            if lieu.split(",")[0] in f"{nom} {l}".lower():
                return {"parcours": nom, "texte": meteo}
    except Exception:
        return None
    finally:
        conn.close()
    return None


def _cle_sac(course):
    return f"sac_course:{str(course.get('date') or '')[:10]}:{course.get('nom') or ''}"


def _sac_memorise(course):
    from data.database import obtenir_parametre
    try:
        return json.loads(obtenir_parametre(_cle_sac(course), "[]") or "[]")
    except ValueError:
        return []


def enregistrer_sac(course, sac):
    """Mémorise les cases cochées : dans le roadbook s'il y en a un, sinon dans les réglages."""
    roadbook_id = course.get("roadbook_id")
    if not roadbook_id:
        from data.database import definir_parametre
        definir_parametre(_cle_sac(course), json.dumps(sac, ensure_ascii=False))
        return True
    conn = connexion()
    try:
        conn.execute("UPDATE roadbooks SET checklist_json=? WHERE id=?", (json.dumps(sac, ensure_ascii=False), roadbook_id))
        conn.commit()
    finally:
        conn.close()
    return True
