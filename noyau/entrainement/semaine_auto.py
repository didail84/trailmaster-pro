"""
« Préparer ma semaine » : les séances prévues des 7 prochains jours sont
placées dans les créneaux libres de Google Agenda (reçu par les
connecteurs Claude), puis envoyées d'un coup sur la montre, dans l'agenda
et sur Spotify (demandes déposées pour Claude).

Règles de placement, par séance :
  - le jour prévu ; l'heure préférée (Réglages, 18:00 par défaut) si elle
    est libre, sinon le créneau libre assez long le plus proche ;
  - sans agenda reçu, l'heure préférée ;
  - jamais avant 6 h ni après 21 h ; une journée chargée est signalée.
"""

from datetime import date, datetime, timedelta

from data.database import obtenir_parametre, definir_parametre

CLE_HEURE = "semaine_heure_preferee"
HEURE_DEFAUT = "18:00"


def heure_preferee():
    h = obtenir_parametre(CLE_HEURE, HEURE_DEFAUT) or HEURE_DEFAUT
    try:
        datetime.strptime(h, "%H:%M")
        return h
    except ValueError:
        return HEURE_DEFAUT


def definir_heure_preferee(h):
    datetime.strptime(h, "%H:%M")
    definir_parametre(CLE_HEURE, h)


def _minutes(hhmm):
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def _hhmm(minutes):
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def placer(duree_min, creneaux, preferee=HEURE_DEFAUT):
    """Heure de départ « HH:MM » pour une séance de `duree_min` dans les créneaux libres [(debut, fin)].
    None si aucun créneau ne convient. Sans créneau connu (liste None) : l'heure préférée."""
    if creneaux is None:
        return preferee
    p = _minutes(preferee)
    meilleur = None
    for d, f in creneaux:
        a, b = _minutes(d), _minutes(f)
        if b - a < duree_min:
            continue
        depart = min(max(p, a), b - duree_min)       # au plus près de l'heure préférée
        ecart = abs(depart - p)
        if meilleur is None or ecart < meilleur[0]:
            meilleur = (ecart, depart)
    return _hhmm(meilleur[1]) if meilleur else None


def proposition(athlete_id, debut=None, jours=7):
    """[{seance, jour, heure, fin, duree_min, chargee, heures_agenda, remarque}] pour les séances prévues."""
    from noyau.donnees import connecteurs as D
    debut = debut or date.today()
    pref = heure_preferee()
    fatigue = {f["jour"]: f for f in D.fatigue_par_jour(athlete_id, debut.isoformat(), jours)}
    agenda_connu = bool(D.agenda(athlete_id, debut.isoformat(), jours)) or _agenda_deja_recu(athlete_id)
    res = []
    for s in D.seances_prevues(athlete_id):
        j = (s.get("date_prevue") or "")[:10]
        if not j or j < debut.isoformat() or j >= (debut + timedelta(days=jours)).isoformat():
            continue
        duree = max(20, s["duree_min"] or 45)
        f = fatigue.get(j, {"creneaux": None, "heures": 0, "chargee": False})
        heure = placer(duree, f["creneaux"] if agenda_connu else None, pref)
        remarque = ""
        if heure is None:
            heure, remarque = pref, "Aucun créneau libre assez long : à caser à la main."
        elif f.get("chargee"):
            remarque = "Journée chargée : garde la séance facile."
        fin = _hhmm(_minutes(heure) + duree)
        res.append({"seance": s, "jour": j, "heure": heure, "fin": fin, "duree_min": duree,
                    "chargee": bool(f.get("chargee")), "heures_agenda": f.get("heures", 0), "remarque": remarque})
    res.sort(key=lambda x: (x["jour"], x["heure"]))
    return res


def _agenda_deja_recu(athlete_id):
    from noyau.donnees import base
    try:
        return base.lire_un("SELECT 1 FROM connecteurs_paquets WHERE athlete_id=? LIMIT 1", (athlete_id,)) is not None
    except Exception:
        return False


def appliquer(athlete_id, propositions, montre=True, agenda=True, playlist=True):
    """Crée les demandes pour Claude. Retourne {"demandes": n, "erreurs": [texte]}."""
    from noyau.donnees import connecteurs as D
    n, erreurs = 0, []
    for p in propositions:
        s = p["seance"]
        actions = []
        if montre:
            actions.append(("montre", lambda: D.demander_seance_montre(athlete_id, s)))
        if agenda:
            actions.append(("agenda", lambda: D.demander_agenda(
                athlete_id, f"🏃 {s['nom']}", f"{p['jour']}T{p['heure']}", f"{p['jour']}T{p['fin']}",
                description=f"Séance prévue dans Trail Master Hub Pro ({s.get('type_seance') or 'course'}).")))
        if playlist:
            actions.append(("playlist", lambda: D.demander_playlist(athlete_id, s["nom"], p["duree_min"])))
        for quoi, faire in actions:
            try:
                faire()
                n += 1
            except Exception as e:                # une séance sans étapes ne bloque pas le reste
                erreurs.append(f"{s['nom']} ({quoi}) : {e}")
    return {"demandes": n, "erreurs": erreurs}
