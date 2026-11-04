"""
Analyses automatiques des sorties (Trail Hub Center).

Dès qu'une sortie arrive (import FIT/GPX, Garmin, Strava, montre USB,
saisie à la main, suivi en direct…), elle reçoit son analyse sans que
l'on ait à cliquer sur un bouton :
  - avec une clé Gemini ou Groq : analyse de l'IA (même texte que le
    bouton « Générer l'analyse » de la fiche sortie) ;
  - sans clé, ou si l'IA ne répond pas (quota, pas d'Internet) :
    analyse hors ligne par les règles du logiciel (analyse_locale.py).
Quand une clé est réglée plus tard, les analyses hors ligne récentes
sont remplacées par celles de l'IA, au fil des passages.

Pour ne pas épuiser le quota gratuit de l'IA, un passage ne traite que
les sorties des `JOURS_RECENTS` derniers jours, `PAR_PASSAGE` au plus,
les plus récentes d'abord. Aucun widget ici : l'interface lance les
passages en arrière-plan (interface/analyse_auto.py).
"""

from datetime import datetime, timedelta

from data.database import connexion, obtenir_parametre, definir_parametre
from noyau.outils.date_utils import parser_date_flexible
from noyau.ia.analyse_locale import MARQUEUR_ANALYSE_LOCALE, analyser_sortie_hors_ligne

CLE_REGLAGE = "ia_analyses_automatiques"
JOURS_RECENTS = 21
PAR_PASSAGE = 5


def actif():
    """Réglage « Analyses automatiques » (activé par défaut)."""
    return obtenir_parametre(CLE_REGLAGE, "1") == "1"


def definir_actif(oui):
    definir_parametre(CLE_REGLAGE, "1" if oui else "0")


def _ia_disponible():
    try:
        from noyau.ia.ia_coach import cle_api_configuree, cle_api_groq_configuree
        return bool(cle_api_configuree() or cle_api_groq_configuree())
    except Exception:
        return False


def _derniere_analyse_par_sortie():
    conn = connexion()
    try:
        lignes = conn.execute(
            "SELECT activite_id, contenu FROM analyses_ia WHERE activite_id IS NOT NULL "
            "ORDER BY date_generation, id").fetchall()
    finally:
        conn.close()
    return {aid: contenu for aid, contenu in lignes}    # la plus récente l'emporte


def sorties_a_analyser(athlete_id=None, jours=JOURS_RECENTS, limite=PAR_PASSAGE, maintenant=None):
    """[(activite_id, athlete_id)] des sorties récentes sans analyse — ou,
    si l'IA est disponible, avec seulement une analyse hors ligne."""
    maintenant = maintenant or datetime.now()
    limite_basse = maintenant - timedelta(days=jours)
    conn = connexion()
    try:
        sql = "SELECT id, athlete_id, date FROM activites"
        params = ()
        if athlete_id is not None:
            sql += " WHERE athlete_id=?"
            params = (athlete_id,)
        lignes = conn.execute(sql, params).fetchall()
    finally:
        conn.close()
    analyses = _derniere_analyse_par_sortie()
    ia = _ia_disponible()
    candidates = []
    for aid, ath, texte_date in lignes:
        d = parser_date_flexible(texte_date)
        if d is None or d < limite_basse or d > maintenant + timedelta(days=1) or ath is None:
            continue
        existante = analyses.get(aid)
        if existante is None or (ia and MARQUEUR_ANALYSE_LOCALE in existante):
            candidates.append((d, aid, ath))
    candidates.sort(reverse=True)
    if not ia:
        limite = max(limite, 60)        # hors ligne : gratuit et rapide, pas besoin d'économiser
    return [(aid, ath) for _, aid, ath in candidates[:limite]]


def analyser(activite_id, athlete_id, essayer_ia=True):
    """Analyse une sortie et l'enregistre. Renvoie (texte, source) avec
    source = 'ia' | 'cache' | 'local' ; (None, 'absente') si la sortie n'existe pas."""
    from noyau.ia.ia_coach import analyser_sortie, ErreurAnalyseIA, _enregistrer_analyse, _analyse_en_cache
    if essayer_ia and _ia_disponible():
        try:
            texte, depuis_cache = analyser_sortie(activite_id, athlete_id)
            return texte, "cache" if depuis_cache else "ia"
        except ErreurAnalyseIA:
            if _analyse_en_cache(activite_id):        # garde l'analyse hors ligne déjà faite
                return _analyse_en_cache(activite_id)[0], "local"
    texte = analyser_sortie_hors_ligne(activite_id, athlete_id)
    if texte is None:
        return None, "absente"
    _enregistrer_analyse(athlete_id, activite_id, texte)
    return texte, "local"


def passage(athlete_id=None, limite=PAR_PASSAGE, rappel=None):
    """Analyse les sorties en attente. `rappel(activite_id, source)` est
    appelé après chacune. Dès que l'IA échoue une fois (quota, réseau),
    le reste du passage se fait hors ligne. Renvoie [(activite_id, source)]."""
    if not actif():
        return []
    faits, essayer_ia = [], True
    for activite_id, ath in sorties_a_analyser(athlete_id, limite=limite):
        try:
            _texte, source = analyser(activite_id, ath, essayer_ia)
        except Exception:
            continue                                   # une sortie illisible ne bloque pas les autres
        if source == "local" and essayer_ia and _ia_disponible():
            essayer_ia = False
        if source == "absente":
            continue
        faits.append((activite_id, source))
        if rappel:
            rappel(activite_id, source)
    return faits


def analyses_des_sorties(activite_ids):
    """{activite_id: texte de la dernière analyse} pour les sorties données."""
    ids = [int(i) for i in activite_ids]
    if not ids:
        return {}
    conn = connexion()
    try:
        lignes = conn.execute(
            f"SELECT activite_id, contenu FROM analyses_ia WHERE activite_id IN ({','.join('?' * len(ids))}) "
            "ORDER BY date_generation, id", ids).fetchall()
    finally:
        conn.close()
    return {aid: contenu for aid, contenu in lignes}


def source_du_texte(texte):
    """'local' pour une analyse hors ligne, 'ia' sinon (None si pas de texte)."""
    if not texte:
        return None
    return "local" if MARQUEUR_ANALYSE_LOCALE in texte else "ia"
