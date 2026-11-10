"""
LiveTrack coach — règles, sans Qt ni SQL.

Le coureur lance LiveTrack depuis Garmin Connect sur son téléphone ; Garmin
lui donne un lien qu'il envoie à son coach (SMS, e-mail, messagerie…). Ce lien
ouvre une page web (carte, allure, distance…) : le logiciel le garde, le
rattache au coureur et l'affiche. Il ne lit PAS les données de la page : il n'y
a pas d'accès officiel de Garmin pour ça, et la fréquence cardiaque n'y apparaît
que si Garmin l'affiche sur la page (à vérifier avec le test de configuration).

Un lien LiveTrack ne marche que pendant et peu après la sortie ; le logiciel ne
peut pas le savoir, donc l'état « en cours » ou « terminé » se règle à la main,
avec une indication « expiré probable » passé un certain délai.
"""

import re
from datetime import datetime, timedelta
from urllib.parse import urlsplit, urlunsplit

# Adresses acceptées : seules les pages de Garmin (jamais un site quelconque collé par erreur).
HOTES_GARMIN = ("livetrack.garmin.com", "connect.garmin.com", "connect.garmin.cn")
DELAI_EXPIRE_PROBABLE_H = 24          # au-delà, le lien est probablement mort (indication, pas une certitude)
FENETRE_RATTACHEMENT_H = 36           # une sortie reçue plus tard que ça après le suivi n'est plus proposée

ETATS = (("en_cours", "En cours"), ("termine", "Terminé"), ("annule", "Annulé"))
LIBELLE_ETAT = dict(ETATS)
LIBELLE_FC = {None: "pas encore vérifié", 1: "visible sur la page", 0: "non visible sur la page"}

_RE_URL = re.compile(r"https?://[^\s<>\"'«»]+", re.IGNORECASE)
_PONCTUATION_FINALE = ".,;:!?)]}»"


class ErreurLiveTrack(Exception):
    """Message lisible ; rien n'a été modifié."""


def extraire_lien(texte):
    """Premier lien Garmin trouvé dans un texte collé (message complet du coureur, e-mail…), ou None."""
    for brut in _RE_URL.findall(texte or ""):
        brut = brut.rstrip(_PONCTUATION_FINALE)
        try:
            return valider_lien(brut)
        except ErreurLiveTrack:
            continue
    return None


def valider_lien(texte):
    """Lien LiveTrack propre (https, adresse Garmin) ; lève ErreurLiveTrack sinon.

    Accepte un message entier : on y cherche le lien. Un lien en http est passé en https."""
    t = (texte or "").strip()
    if not t:
        raise ErreurLiveTrack("Colle le lien reçu du coureur (il commence par https://livetrack.garmin.com/…).")
    if not t.lower().startswith(("http://", "https://")):
        trouve = _RE_URL.search(t)
        if not trouve:
            raise ErreurLiveTrack("Je ne trouve pas de lien dans ce texte. Colle le lien LiveTrack envoyé par le coureur.")
        t = trouve.group(0)
    t = t.split()[0].rstrip(_PONCTUATION_FINALE)
    p = urlsplit(t)
    hote = (p.hostname or "").lower()
    if hote not in HOTES_GARMIN:
        raise ErreurLiveTrack("Ce lien n'est pas un lien Garmin LiveTrack (il doit venir de livetrack.garmin.com). "
                              "Vérifie le lien envoyé par le coureur.")
    if hote == "connect.garmin.com" and "livetrack" not in (p.path or "").lower():
        raise ErreurLiveTrack("Ce lien Garmin Connect n'est pas un lien LiveTrack. "
                              "Demande au coureur de t'envoyer le lien de son suivi en direct.")
    if hote == "livetrack.garmin.com" and len([s for s in p.path.split("/") if s]) < 2:
        raise ErreurLiveTrack("Le lien LiveTrack paraît incomplet (il manque la fin). Colle-le en entier.")
    return urlunsplit(("https", p.netloc, p.path, p.query, ""))


def lien_masque(lien):
    """Lien raccourci pour l'affichage (le jeton de fin n'a pas à s'étaler à l'écran)."""
    p = urlsplit(lien or "")
    chemin = p.path or ""
    return f"{p.netloc}{chemin[:18]}…" if len(chemin) > 18 else f"{p.netloc}{chemin}"


def _dt(v):
    if isinstance(v, datetime):
        return v
    try:
        return datetime.fromisoformat(str(v)[:19])
    except (TypeError, ValueError):
        return None


def etat_affiche(suivi, maintenant=None):
    """(code, libellé) de ce qu'on montre au coach : « en cours », « terminé », « annulé » ou « expiré probable »."""
    etat = suivi.get("etat") or "en_cours"
    if etat == "en_cours":
        debut = _dt(suivi.get("debut"))
        maintenant = maintenant or datetime.now()
        if debut and maintenant - debut > timedelta(hours=DELAI_EXPIRE_PROBABLE_H):
            return "expire", "Expiré probable"
    return etat, LIBELLE_ETAT.get(etat, etat)


def duree_suivi(suivi, maintenant=None):
    """Durée du suivi en secondes (début → fin, ou → maintenant s'il n'est pas fini), ou None."""
    debut = _dt(suivi.get("debut"))
    if not debut:
        return None
    fin = _dt(suivi.get("fin")) or (maintenant or datetime.now())
    return max(0, int((fin - debut).total_seconds()))


def duree_texte(secondes):
    if secondes is None:
        return ""
    m = int(round(secondes / 60))
    return f"{m // 60} h {m % 60:02d}" if m >= 60 else f"{m} min"


def activites_candidates(suivi, activites):
    """Sorties qui peuvent correspondre à ce suivi : même coureur, démarrées autour du suivi.

    `activites` : liste de dicts {id, athlete_id, date, nom, type, distance, duree}. Les plus proches du début du
    suivi d'abord. Une sortie déjà rattachée à un autre suivi doit être retirée avant (c'est le rôle de l'accès aux
    données)."""
    debut = _dt(suivi.get("debut"))
    if debut is None:
        return []
    fin = _dt(suivi.get("fin")) or debut
    bas = debut - timedelta(hours=3)                      # le coureur colle parfois le lien après être parti
    haut = max(fin, debut) + timedelta(hours=FENETRE_RATTACHEMENT_H)
    res = []
    for a in activites:
        d = _dt(a.get("date"))
        if d is None:
            continue
        if len(str(a.get("date") or "")) <= 10:           # date seule : on compare au jour
            d = datetime.combine(d.date(), debut.time())
        if bas <= d <= haut:
            res.append((abs((d - debut).total_seconds()), a))
    return [a for _e, a in sorted(res, key=lambda x: x[0])]


# ------------------------------------------------------------------ message au coureur

ETAPES_COUREUR = (
    "Sur ton téléphone, ouvre l'appli Garmin Connect (la montre doit être jumelée en Bluetooth, et le téléphone "
    "doit avoir du réseau pendant la sortie).",
    "Ouvre le menu Plus, puis Sécurité et suivi, puis LiveTrack.",
    "Choisis de partager avec ton coach (par e-mail ou SMS) et démarre LiveTrack.",
    "Sur la montre, lance ton activité (course à pied, trail) : le suivi commence au départ de l'activité.",
    "Envoie-moi le lien que Garmin te donne (ou vérifie que je l'ai bien reçu) avant de partir.",
)


def modele_message(prenom_coureur="", nom_coach="", montre="", objectif=""):
    """Texte à envoyer au coureur : les étapes pour lancer LiveTrack et envoyer le lien."""
    bonjour = f"Bonjour {prenom_coureur}," if prenom_coureur else "Bonjour,"
    cible = f" Pour ta sortie ({objectif}), " if objectif else " Pour ta prochaine sortie, "
    lignes = [bonjour, "",
              f"je voudrais te suivre en direct.{cible}peux-tu lancer Garmin LiveTrack"
              + (f" avec ta {montre}" if montre else "") + " ? Voici comment :", ""]
    lignes += [f"{i}. {e}" for i, e in enumerate(ETAPES_COUREUR, 1)]
    lignes += ["", "Merci ! Je te suis depuis le lien dès que tu es parti."]
    if nom_coach:
        lignes += ["", nom_coach]
    return "\n".join(lignes)


# ------------------------------------------------------------------ test de configuration

# (code, ce que le coach vérifie) — résultat : « oui » / « non » / None (pas encore fait)
POINTS_TEST = (
    ("lien_recu", "Le coach a reçu le lien LiveTrack du coureur"),
    ("page_ouvre", "Le lien s'ouvre (sans compte Garmin à créer)"),
    ("carte", "La carte avec la position du coureur s'affiche et bouge"),
    ("allure", "L'allure et la distance s'affichent"),
    ("fc", "La fréquence cardiaque s'affiche sur la page"),
)
CODES_TEST = tuple(c for c, _l in POINTS_TEST)


def bilan_test(resultats):
    """Résumé en une phrase d'un test (dict code → True/False/None) : ce que le coach peut compter voir."""
    r = {c: resultats.get(c) for c in CODES_TEST}
    if all(v is None for v in r.values()):
        return "Test pas encore fait."
    if r["lien_recu"] is False or r["page_ouvre"] is False:
        return "Le lien ne s'ouvre pas : demande au coureur de relancer LiveTrack et de renvoyer le lien."
    if r["carte"] is False:
        return "La carte ne s'affiche pas : le coureur doit avoir du réseau et lancer l'activité sur la montre."
    manque = [c for c in CODES_TEST if r[c] is None]
    if manque:
        return "Test incomplet : il reste des points à vérifier."
    if r["fc"] is False:
        return ("Position, allure et distance sont suivies ; la fréquence cardiaque n'apparaît pas sur la page. "
                "Pour la voir en direct, il faudra la diffuser depuis la montre vers une appli de suivi.")
    return "Tout est visible, y compris la fréquence cardiaque : la configuration est bonne."


def fc_vue_par_le_test(resultats):
    """1 / 0 / None : la fréquence cardiaque s'est-elle vue sur la page pendant le test ?"""
    v = resultats.get("fc")
    return None if v is None else (1 if v else 0)


# ------------------------------------------------------------------ fil de suivi

def ligne_fil(suivi, coureur_nom):
    """Phrase du fil d'activité pour un suivi en direct."""
    etat, lib = etat_affiche(suivi)
    d = duree_texte(duree_suivi(suivi))
    base = f"📡 {coureur_nom} suivi en direct"
    if etat == "termine":
        return f"{base} — terminé" + (f" ({d})" if d else "")
    if etat == "annule":
        return f"{base} — annulé"
    if etat == "expire":
        return f"{base} — lien probablement expiré"
    return f"{base} — en cours" + (f" depuis {d}" if d else "")
