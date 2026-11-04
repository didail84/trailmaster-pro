"""
Analyse IA des sorties — TrailMaster Pro.

Utilise l'API Google Gemini (gratuite, quota généreux, aucune carte
bancaire requise — clé personnelle à récupérer une fois sur
https://aistudio.google.com/apikey) pour produire, à la demande, un
compte rendu en français sur une sortie précise : points positifs,
points à travailler, et recommandation pour la séance suivante
(repos / renforcement / endurance / sortie spécifique...).

Comme Météo, Carte réelle, Synchro Strava ou Créer un parcours,
c'est la seule partie de cette fonctionnalité qui dépend d'internet :
le résumé envoyé à l'IA est construit uniquement à partir des calculs
déjà faits localement par interface/coach.py (charge, ACWR, alertes,
sommeil, blessures...) — aucune donnée personnelle (nom, coordonnées)
n'est transmise, seulement des chiffres de performance et de forme.

Chaque analyse générée est enregistrée en base (table analyses_ia) et
réutilisée telle quelle à la prochaine consultation, pour éviter de
consommer à nouveau le quota gratuit à chaque simple réaffichage.
"""

import json
import time
import urllib.request
import urllib.error
import socket
from datetime import datetime, timedelta

from data.database import connexion, obtenir_parametre, definir_parametre
from noyau.outils.date_utils import parser_date_flexible
from noyau.entrainement.coach import (
    charge_activite_pour_athlete,
    calculer_acwr,
    generer_alertes,
    calculer_score_forme_jour,
    calculer_serie_forme,
)
from noyau.sante.rythme_vie import contexte_fatigue_vie


CLE_PARAMETRE_API_KEY = "cle_api_gemini"

# Google renomme régulièrement ses modèles (l'ancien "gemini-2.0-flash"
# a par exemple fini par répondre 404 "no longer available"). On essaie
# d'abord le modèle daté le plus courant connu, puis un alias "-latest"
# que Google fait pointer automatiquement vers le dernier modèle Flash
# disponible — pour rester résilient sans nécessiter de mise à jour du
# logiciel à chaque renommage côté Google.
MODELES_GEMINI_CANDIDATS = ["gemini-3.6-flash", "gemini-flash-latest"]
URL_GEMINI_MODELE = "https://generativelanguage.googleapis.com/v1beta/models/{modele}:generateContent"
DELAI_TIMEOUT_SECONDES = 30

# En cas de surcharge temporaire côté Google (503 "UNAVAILABLE" — le
# modèle reçoit un pic de demande, rien à voir avec la clé ou le
# réseau de l'utilisateur), on retente automatiquement quelques fois
# avant de basculer sur le modèle candidat suivant, plutôt que
# d'afficher tout de suite le message technique brut à l'utilisateur.
NB_TENTATIVES_SURCHARGE = 3
DELAI_ENTRE_TENTATIVES_SECONDES = 3

# ------------------------------------------------------------------
# GROQ — second fournisseur gratuit, utilisé automatiquement en
# secours si Gemini est indisponible (clé optionnelle, sans carte
# bancaire, à récupérer sur console.groq.com/keys). Contrairement à
# Gemini, dont le palier gratuit est explicitement "déprioritisé en
# cas de forte demande" côté Google (d'où les erreurs 503 récurrentes),
# l'infrastructure de Groq est connue pour rester disponible même sur
# son palier gratuit — un bon filet de sécurité plutôt qu'un simple
# remplaçant.
CLE_PARAMETRE_API_KEY_GROQ = "cle_api_groq"
MODELES_GROQ_CANDIDATS = ["llama-3.3-70b-versatile", "llama-3.1-8b-instant"]
URL_GROQ = "https://api.groq.com/openai/v1/chat/completions"
NB_TENTATIVES_SURCHARGE_GROQ = 2


# ------------------------------------------------------------------
# CLÉS API (Réglages)
# ------------------------------------------------------------------

def obtenir_cle_api():
    return obtenir_parametre(CLE_PARAMETRE_API_KEY)


def definir_cle_api(cle):
    definir_parametre(CLE_PARAMETRE_API_KEY, (cle or "").strip())


def cle_api_configuree():
    """Vrai si au moins un fournisseur (Gemini et/ou Groq) a une clé
    renseignée — c'est cette condition qui active le bouton « Analyse
    IA » dans les écrans, plus large que la seule présence d'une clé
    Gemini depuis l'ajout du secours Groq."""
    return bool((obtenir_cle_api() or "").strip()) or cle_api_groq_configuree()


def obtenir_cle_api_groq():
    return obtenir_parametre(CLE_PARAMETRE_API_KEY_GROQ)


def definir_cle_api_groq(cle):
    definir_parametre(CLE_PARAMETRE_API_KEY_GROQ, (cle or "").strip())


def cle_api_groq_configuree():
    cle = obtenir_cle_api_groq()
    return bool(cle and cle.strip())


# ------------------------------------------------------------------
# CONSTRUCTION DU RÉSUMÉ (tout est calculé localement, hors ligne)
# ------------------------------------------------------------------

def _activites_similaires_recentes(athlete_id, type_activite, avant_date, limite=5):
    """5 dernières sorties du même type avant celle analysée, pour donner
    un point de comparaison à l'IA (progression / régularité)."""

    conn = connexion()
    cur = conn.cursor()
    cur.execute(
        "SELECT date, distance, duree, allure_moyenne, frequence_cardiaque_moyenne "
        "FROM activites WHERE athlete_id=? AND type=? ORDER BY date DESC",
        (athlete_id, type_activite),
    )
    lignes = cur.fetchall()
    conn.close()

    resultat = []
    for date_texte, distance, duree, allure, fc_moy in lignes:
        date_obj = parser_date_flexible(date_texte)
        if date_obj is None or date_obj >= avant_date:
            continue
        resultat.append({
            "date": date_obj.strftime("%d/%m/%Y"),
            "distance": distance, "duree_min": round((duree or 0) / 60, 1),
            "allure": allure, "fc_moyenne": fc_moy,
        })
        if len(resultat) >= limite:
            break
    return resultat


def _musculation_recente(athlete_id, jour_activite, nb_jours=2):
    conn = connexion()
    cur = conn.cursor()
    cur.execute(
        "SELECT date, type_seance, groupe_musculaire, rpe, douleur "
        "FROM musculation_suivi WHERE athlete_id=?",
        (athlete_id,),
    )
    lignes = cur.fetchall()
    conn.close()

    resultat = []
    for date_texte, type_seance, groupe, rpe, douleur in lignes:
        date_obj = parser_date_flexible(date_texte)
        if date_obj is None:
            continue
        ecart = (jour_activite - date_obj.date()).days
        if 0 <= ecart <= nb_jours:
            resultat.append({
                "jours_avant": ecart, "type_seance": type_seance,
                "groupe_musculaire": groupe, "rpe": rpe, "douleur": douleur,
            })
    return resultat


def _blessures_actives(athlete_id):
    conn = connexion()
    cur = conn.cursor()
    cur.execute(
        "SELECT zone_corporelle, type_blessure, gravite FROM blessures "
        "WHERE athlete_id=? AND statut != 'Guérie'",
        (athlete_id,),
    )
    lignes = cur.fetchall()
    conn.close()
    return lignes


def _sommeil_moyen_recent(athlete_id, nb_entrees=5):
    conn = connexion()
    cur = conn.cursor()
    cur.execute(
        "SELECT duree_heures FROM sommeil WHERE athlete_id=? ORDER BY date DESC LIMIT ?",
        (athlete_id, nb_entrees),
    )
    valeurs = [d for (d,) in cur.fetchall() if d is not None]
    conn.close()
    if not valeurs:
        return None
    return round(sum(valeurs) / len(valeurs), 1)


def construire_resume_sortie(activite_id, athlete_id):
    """Rassemble en un dict tout ce qui est utile pour juger la sortie
    (rien n'est envoyé tel quel : sert à construire le prompt texte)."""

    conn = connexion()
    cur = conn.cursor()
    cur.execute(
        "SELECT date, nom, type, distance, denivele, denivele_negatif, duree, "
        "vitesse_moyenne, allure_moyenne, frequence_cardiaque_moyenne, "
        "frequence_cardiaque_max, calories, notes "
        "FROM activites WHERE id=? AND athlete_id=?",
        (activite_id, athlete_id),
    )
    ligne = cur.fetchone()
    conn.close()

    if not ligne:
        return None

    (date_texte, nom, type_, distance, denivele, denivele_neg, duree,
     vitesse_moy, allure_moy, fc_moy, fc_max, calories, notes) = ligne

    date_obj = parser_date_flexible(date_texte)
    activite_dict = {
        "type": type_, "distance": distance, "duree": duree,
        "frequence_cardiaque_moyenne": fc_moy,
    }
    charge, methode_charge = charge_activite_pour_athlete(activite_dict, athlete_id)

    return {
        "activite": {
            "date": date_obj.strftime("%d/%m/%Y") if date_obj else date_texte,
            "nom": nom, "type": type_, "distance_km": distance,
            "denivele_positif_m": denivele, "denivele_negatif_m": denivele_neg,
            "duree_min": round((duree or 0) / 60, 1),
            "vitesse_moyenne_kmh": vitesse_moy, "allure_moyenne_min_km": allure_moy,
            "fc_moyenne": fc_moy, "fc_max": fc_max, "calories": calories,
            "notes_athlete": notes,
        },
        "charge_sortie": {"valeur": charge, "methode": methode_charge},
        "acwr": calculer_acwr(athlete_id),
        "score_forme_du_jour": calculer_score_forme_jour(athlete_id),
        "rythme_de_vie": contexte_fatigue_vie(date_obj.date() if date_obj else None).get("texte"),
        "alertes_actives": generer_alertes(athlete_id),
        "sommeil_moyen_recent_h": _sommeil_moyen_recent(athlete_id),
        "blessures_actives": [
            {"zone": z, "type": t, "gravite": g} for z, t, g in _blessures_actives(athlete_id)
        ],
        "musculation_jours_proches": _musculation_recente(
            athlete_id, date_obj.date() if date_obj else datetime.now().date()
        ),
        "sorties_similaires_recentes": _activites_similaires_recentes(
            athlete_id, type_, date_obj or datetime.now()
        ),
        "dossier_technique": _dossier_technique_sortie(activite_id, athlete_id),
    }


def _dossier_technique_sortie(activite_id, athlete_id):
    """Chiffres de performance calculés en local (interface/analyse_technique.py).
    Un échec ici ne doit jamais empêcher l'analyse : on envoie alors sans."""
    try:
        from noyau.ia.analyse_technique import dossier_sortie
        return dossier_sortie(activite_id, athlete_id)
    except Exception:
        return {}


MARQUEUR_ANALYSE_TECHNIQUE = "Lecture technique"   # présent dans toute analyse générée par la v101+

CONSIGNES_COMMUNES = (
    "RÈGLES ABSOLUES :\n"
    "- Tu t'appuies UNIQUEMENT sur les données fournies. Chaque affirmation cite au moins un chiffre "
    "exact avec son unité (min/km, bpm, m/h, %, km-effort...). Si une donnée manque (clé absente ou "
    "null), écris « non mesuré » et n'en déduis rien.\n"
    "- Tu n'inventes aucune valeur, aucune comparaison, aucun record. Les zones en % FCmax, la VMA, le "
    "VO2max, les allures de référence, l'allure ajustée (GAP) et la nature probable de la séance sont "
    "des ESTIMATIONS : dis-le en une fois, brièvement.\n"
    "- Vocabulaire d'entraîneur : allure ajustée à la pente (GAP), découplage aérobie (Pa:Hr), VAM, "
    "zones de FC, CTL/ATL/TSB, ACWR, monotonie, polarisation 80/20, durabilité. Explique en quelques "
    "mots un terme technique la première fois qu'il apparaît.\n"
    "- Priorise : un point fort ou un limiteur n'est cité que s'il est étayé par un chiffre. Pas de "
    "compliments génériques, pas de phrases vagues (« continue comme ça »).\n"
    "- Si une alerte, une blessure active, une HRV sous la bande ou une FC de repos en hausse figure dans "
    "les données, elle prime sur l'envie de charger : dis-le clairement.\n"
    "- Aucun diagnostic médical. Tutoie l'athlète. Réponds uniquement en français, en Markdown.\n"
)


def _construire_prompt(resume):
    from noyau.ia.analyse_technique import LEGENDE
    return (
        "Tu es un entraîneur de trail et de course à pied de haut niveau, spécialiste de la "
        "physiologie de l'effort et de l'analyse de données d'entraînement. Tu rédiges l'analyse "
        "technique d'UNE séance pour un athlète qui veut progresser en performance. Le ton est "
        "direct, précis, professionnel.\n\n"
        + CONSIGNES_COMMUNES + "\n"
        "STRUCTURE OBLIGATOIRE (ces titres exacts, dans cet ordre) :\n\n"
        "### Lecture technique de la séance\n"
        "Nature de la séance (déduite de nature_probable_de_la_seance, des zones et de la régularité), "
        "puis lecture chiffrée : allure réelle vs allure ajustée à la pente, régularité (split), "
        "FC et zones (% de temps), découplage Pa:Hr, VAM dans les montées principales, cadence, "
        "durabilité si disponible. 6 à 10 lignes, en puces courtes.\n\n"
        "### Points forts (performance)\n"
        "2 à 4 puces, chacune avec son chiffre. Compare à comparaison_sorties_similaires "
        "(efficacité, vitesse, FC) quand elle existe.\n\n"
        "### Limiteurs de performance\n"
        "2 à 4 puces : ce qui a freiné ou coûté de l'énergie (dérive cardiaque, allure irrégulière, "
        "trop de temps en zone 3, VAM qui chute, descente subie...), chacune avec son chiffre et "
        "l'hypothèse physiologique la plus probable. Distingue clairement un fait mesuré d'une hypothèse.\n\n"
        "### Charge, fatigue et récupération\n"
        "CTL/ATL/TSB au jour J, charge des 7 derniers jours et variation, monotonie, HRV vs base, FC "
        "de repos, sommeil, poids si pertinent. Conclus par un niveau de risque (faible / modéré / "
        "élevé) justifié en une phrase. 4 à 6 lignes.\n\n"
        "### Prescription pour la prochaine séance\n"
        "Une séance précise et exécutable : type, durée, structure (échauffement / blocs / retour au "
        "calme), intensité en bpm ET en allure (min/km, allure ajustée si en côte), D+ cible, critère "
        "d'arrêt ou d'ajustement (ex. « si la FC dépasse X bpm à allure Y, ralentis »). Justifie en une "
        "phrase par les données. Donne une alternative plus légère si la fraîcheur, la HRV ou le "
        "sommeil sont défavorables. Termine par UN axe de travail prioritaire pour les 2 prochaines "
        "semaines.\n\n"
        "Longueur totale : 350 à 550 mots. Pas d'introduction, pas de conclusion en dehors des "
        "sections.\n\n"
        + LEGENDE + "\n"
        "DONNÉES DE LA SORTIE ET DU CONTEXTE (JSON, calculées localement, sans donnée personnelle) :\n"
        f"{json.dumps(resume, ensure_ascii=False, separators=(',', ':'), default=str)}"
    )


# ------------------------------------------------------------------
# APPEL API + CACHE EN BASE
# ------------------------------------------------------------------

class ErreurAnalyseIA(Exception):
    pass


class _ErreurModeleSurcharge(Exception):
    """Signal interne (pas montré tel quel à l'utilisateur) : le modèle
    Gemini a répondu 503 "UNAVAILABLE" — surcharge temporaire côté
    Google. Distinct de ValueError (modèle introuvable, 404) pour que
    l'appelant sache qu'il vaut la peine de retenter le même modèle
    avant de passer au suivant."""
    pass


def _appeler_gemini_avec_modele(prompt, cle, modele):
    """Un seul essai avec un nom de modèle donné. Retourne le texte, ou
    lève ErreurAnalyseIA — sauf pour un 404 "modèle introuvable" (lève
    ValueError, pour que l'appelant essaie le modèle candidat suivant)
    ou un 503 "surcharge temporaire" (lève _ErreurModeleSurcharge, pour
    que l'appelant retente ce même modèle avant d'abandonner)."""

    corps = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.3, "maxOutputTokens": 4096},
    }).encode("utf-8")

    requete = urllib.request.Request(
        URL_GEMINI_MODELE.format(modele=modele),
        data=corps,
        headers={
            "Content-Type": "application/json",
            "x-goog-api-key": cle,
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(requete, timeout=DELAI_TIMEOUT_SECONDES) as reponse:
            donnees = json.loads(reponse.read().decode("utf-8"))
    except urllib.error.HTTPError as erreur:
        corps_erreur = ""
        try:
            corps_erreur = erreur.read().decode("utf-8")
        except Exception:
            pass
        if erreur.code == 404:
            # Modèle renommé/retiré côté Google : on laisse une chance
            # au(x) modèle(s) candidat(s) suivant(s).
            raise ValueError(f"modèle {modele} introuvable") from erreur
        if erreur.code in (401, 403):
            raise ErreurAnalyseIA(
                "Clé API Gemini refusée (401/403). Vérifie qu'elle est correctement "
                "copiée dans Réglages > Analyse IA."
            ) from erreur
        if erreur.code == 429:
            raise ErreurAnalyseIA(
                "Quota gratuit Gemini atteint pour le moment (429). Réessaie plus tard."
            ) from erreur
        if erreur.code == 503:
            raise _ErreurModeleSurcharge(corps_erreur) from erreur
        raise ErreurAnalyseIA(
            f"Erreur de l'API Gemini ({erreur.code}) : {corps_erreur[:300]}"
        ) from erreur
    except (urllib.error.URLError, socket.timeout) as erreur:
        raise ErreurAnalyseIA(
            "Impossible de joindre l'API Gemini — vérifie ta connexion internet."
        ) from erreur

    try:
        return donnees["candidates"][0]["content"]["parts"][0]["text"].strip()
    except (KeyError, IndexError, TypeError) as erreur:
        raise ErreurAnalyseIA(
            "Réponse inattendue de l'API Gemini (pas de texte renvoyé)."
        ) from erreur


def _appeler_gemini(prompt):
    cle = obtenir_cle_api()
    if not cle:
        raise ErreurAnalyseIA(
            "Aucune clé API Gemini configurée. Renseigne-la dans Réglages > Analyse IA "
            "(clé gratuite à récupérer sur https://aistudio.google.com/apikey)."
        )

    derniere_erreur_modele = None
    au_moins_une_surcharge = False

    for modele in MODELES_GEMINI_CANDIDATS:
        for tentative in range(1, NB_TENTATIVES_SURCHARGE + 1):
            try:
                return _appeler_gemini_avec_modele(prompt, cle, modele)
            except ValueError as erreur:
                # Modèle introuvable (404) : inutile de retenter, on
                # passe directement au modèle candidat suivant.
                derniere_erreur_modele = erreur
                break
            except _ErreurModeleSurcharge as erreur:
                au_moins_une_surcharge = True
                derniere_erreur_modele = erreur
                if tentative < NB_TENTATIVES_SURCHARGE:
                    time.sleep(DELAI_ENTRE_TENTATIVES_SECONDES)
                    continue
                # Tentatives épuisées pour ce modèle : on passe au
                # modèle candidat suivant (s'il y en a un).
                break

    if au_moins_une_surcharge:
        raise ErreurAnalyseIA(
            "Gemini est momentanément surchargé (forte demande côté Google)."
        ) from derniere_erreur_modele

    raise ErreurAnalyseIA(
        "Aucun des modèles Gemini connus par l'application n'est disponible pour le "
        "moment (ils ont peut-être été renommés côté Google)."
    ) from derniere_erreur_modele


# ------------------------------------------------------------------
# APPEL GROQ (secours) — API compatible OpenAI, même principe de
# retour que Gemini : texte renvoyé, ou ErreurAnalyseIA / ValueError
# (modèle introuvable, on tente le suivant) / _ErreurModeleSurcharge
# (surcharge temporaire, on retente le même modèle).
# ------------------------------------------------------------------

def _appeler_groq_avec_modele(prompt, cle, modele):
    corps = json.dumps({
        "model": modele,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.3,
        "max_tokens": 2500,
    }).encode("utf-8")

    requete = urllib.request.Request(
        URL_GROQ,
        data=corps,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {cle}",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(requete, timeout=DELAI_TIMEOUT_SECONDES) as reponse:
            donnees = json.loads(reponse.read().decode("utf-8"))
    except urllib.error.HTTPError as erreur:
        corps_erreur = ""
        try:
            corps_erreur = erreur.read().decode("utf-8")
        except Exception:
            pass
        if erreur.code in (400, 404):
            # Modèle renommé/retiré/décommissionné côté Groq : on
            # laisse une chance au(x) modèle(s) candidat(s) suivant(s).
            raise ValueError(f"modèle {modele} introuvable") from erreur
        if erreur.code in (401, 403):
            raise ErreurAnalyseIA(
                "Clé API Groq refusée (401/403). Vérifie qu'elle est correctement "
                "copiée dans Réglages > Analyse IA."
            ) from erreur
        if erreur.code == 429:
            raise ErreurAnalyseIA(
                "Quota gratuit Groq atteint pour le moment (429). Réessaie plus tard."
            ) from erreur
        if erreur.code == 503:
            raise _ErreurModeleSurcharge(corps_erreur) from erreur
        raise ErreurAnalyseIA(
            f"Erreur de l'API Groq ({erreur.code}) : {corps_erreur[:300]}"
        ) from erreur
    except (urllib.error.URLError, socket.timeout) as erreur:
        raise ErreurAnalyseIA(
            "Impossible de joindre l'API Groq — vérifie ta connexion internet."
        ) from erreur

    try:
        return donnees["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError, TypeError) as erreur:
        raise ErreurAnalyseIA(
            "Réponse inattendue de l'API Groq (pas de texte renvoyé)."
        ) from erreur


def _appeler_groq(prompt):
    cle = obtenir_cle_api_groq()
    if not cle:
        raise ErreurAnalyseIA("Aucune clé API Groq configurée.")

    derniere_erreur_modele = None
    au_moins_une_surcharge = False

    for modele in MODELES_GROQ_CANDIDATS:
        for tentative in range(1, NB_TENTATIVES_SURCHARGE_GROQ + 1):
            try:
                return _appeler_groq_avec_modele(prompt, cle, modele)
            except ValueError as erreur:
                derniere_erreur_modele = erreur
                break
            except _ErreurModeleSurcharge as erreur:
                au_moins_une_surcharge = True
                derniere_erreur_modele = erreur
                if tentative < NB_TENTATIVES_SURCHARGE_GROQ:
                    time.sleep(DELAI_ENTRE_TENTATIVES_SECONDES)
                    continue
                break

    if au_moins_une_surcharge:
        raise ErreurAnalyseIA("Groq est momentanément surchargé.") from derniere_erreur_modele

    raise ErreurAnalyseIA(
        "Aucun des modèles Groq connus par l'application n'est disponible pour le moment."
    ) from derniere_erreur_modele


# ------------------------------------------------------------------
# ORCHESTRATION — Gemini en priorité (déjà configuré chez la plupart
# des utilisateurs), Groq automatiquement en secours si une clé est
# renseignée et que Gemini échoue. Complètement transparent : la
# personne ne voit qu'un seul bouton « Analyse IA », jamais le nom du
# fournisseur qui a fini par répondre.
# ------------------------------------------------------------------

def _appeler_ia(prompt):
    cle_gemini = obtenir_cle_api()
    cle_groq = obtenir_cle_api_groq()

    if not cle_gemini and not cle_groq:
        raise ErreurAnalyseIA(
            "Aucune clé API configurée. Renseigne au moins une clé gratuite dans "
            "Réglages > Analyse IA des sorties (Gemini sur aistudio.google.com/apikey, "
            "et/ou Groq — recommandé en secours — sur console.groq.com/keys)."
        )

    erreur_gemini = None
    if cle_gemini:
        try:
            return _appeler_gemini(prompt)
        except ErreurAnalyseIA as erreur:
            erreur_gemini = erreur
            if not cle_groq:
                raise

    try:
        return _appeler_groq(prompt)
    except ErreurAnalyseIA as erreur_groq:
        if erreur_gemini is not None:
            raise ErreurAnalyseIA(
                "Ni Gemini ni Groq n'ont pu répondre pour le moment :\n"
                f"• Gemini : {erreur_gemini}\n"
                f"• Groq : {erreur_groq}\n"
                "Ce n'est ni ta clé ni ta connexion qui sont en cause — réessaie dans "
                "quelques minutes avec « Régénérer l'analyse »."
            ) from erreur_groq
        raise


def _analyse_en_cache(activite_id):
    conn = connexion()
    cur = conn.cursor()
    cur.execute(
        "SELECT contenu, date_generation FROM analyses_ia "
        "WHERE activite_id=? ORDER BY date_generation DESC, id DESC LIMIT 1",
        (activite_id,),
    )
    resultat = cur.fetchone()
    conn.close()
    return resultat


def _enregistrer_analyse(athlete_id, activite_id, contenu):
    conn = connexion()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO analyses_ia (athlete_id, activite_id, date_generation, contenu) "
        "VALUES (?, ?, ?, ?)",
        (athlete_id, activite_id, datetime.now().isoformat(timespec="seconds"), contenu),
    )
    conn.commit()
    conn.close()


def analyser_sortie(activite_id, athlete_id, forcer_regeneration=False):
    """Retourne (contenu_texte, depuis_cache: bool). Lève ErreurAnalyseIA
    si la génération échoue (pas de clé, pas d'internet, quota...)."""

    if not forcer_regeneration:
        en_cache = _analyse_en_cache(activite_id)
        if en_cache and MARQUEUR_ANALYSE_TECHNIQUE in en_cache[0]:
            return en_cache[0], True
        # Analyse d'avant la v101 (format simple) : on la régénère en version technique.

    resume = construire_resume_sortie(activite_id, athlete_id)
    if resume is None:
        raise ErreurAnalyseIA("Sortie introuvable.")

    prompt = _construire_prompt(resume)
    contenu = _appeler_ia(prompt)
    _enregistrer_analyse(athlete_id, activite_id, contenu)
    return contenu, False


# ==================================================================
# BILANS PÉRIODIQUES (semaine / mois / année)
# ==================================================================
# Même principe que le compte rendu par sortie (mêmes garde-fous, même
# cache en base, même API Gemini) mais agrégé sur une période entière :
# volume/charge de la période comparés à la période précédente, objectifs
# à échéance sur la période, séances de renforcement, sommeil, blessures,
# et progression de la courbe Fitness/Fatigue/Forme déjà calculée par
# interface/coach.py.

LIBELLES_PERIODE = {"semaine": "cette semaine", "mois": "ce mois-ci", "annee": "cette année"}


def _bornes_periode(type_periode, date_ref):
    if type_periode == "semaine":
        debut = date_ref - timedelta(days=date_ref.weekday())
        fin = debut + timedelta(days=6)
    elif type_periode == "mois":
        debut = date_ref.replace(day=1)
        mois_suivant = debut.replace(year=debut.year + 1, month=1) if debut.month == 12 \
            else debut.replace(month=debut.month + 1)
        fin = mois_suivant - timedelta(days=1)
    elif type_periode == "annee":
        debut = date_ref.replace(month=1, day=1)
        fin = date_ref.replace(month=12, day=31)
    else:
        raise ValueError(f"Type de période inconnu : {type_periode}")
    return debut, fin


def _periode_precedente(type_periode, debut):
    if type_periode == "semaine":
        return _bornes_periode("semaine", debut - timedelta(days=7))
    if type_periode == "mois":
        dernier_jour_mois_precedent = debut - timedelta(days=1)
        return _bornes_periode("mois", dernier_jour_mois_precedent)
    return _bornes_periode("annee", debut.replace(year=debut.year - 1))


def _cle_periode(type_periode, date_ref):
    if type_periode == "semaine":
        annee_iso, semaine_iso, _ = date_ref.isocalendar()
        return f"{annee_iso}-S{semaine_iso:02d}"
    if type_periode == "mois":
        return f"{date_ref.year}-{date_ref.month:02d}"
    return f"{date_ref.year}"


def _activites_periode(athlete_id, debut, fin):
    conn = connexion()
    cur = conn.cursor()
    cur.execute(
        "SELECT date, type, distance, denivele, duree, frequence_cardiaque_moyenne "
        "FROM activites WHERE athlete_id=?",
        (athlete_id,),
    )
    lignes = cur.fetchall()
    conn.close()

    resultat = []
    for date_texte, type_, distance, denivele, duree, fc_moy in lignes:
        date_obj = parser_date_flexible(date_texte)
        if date_obj is None or not (debut <= date_obj.date() <= fin):
            continue
        resultat.append({
            "type": type_, "distance": distance, "denivele": denivele,
            "duree": duree, "fc_moyenne": fc_moy,
        })
    return resultat


def _agreger_activites(activites, athlete_id):
    nb = len(activites)
    distance_totale = sum(a["distance"] or 0 for a in activites)
    denivele_total = sum(a["denivele"] or 0 for a in activites)
    duree_totale_min = sum((a["duree"] or 0) / 60 for a in activites)

    charge_totale = 0.0
    repartition_types = {}
    for a in activites:
        charge, _methode = charge_activite_pour_athlete(
            {"type": a["type"], "distance": a["distance"], "duree": a["duree"],
             "frequence_cardiaque_moyenne": a["fc_moyenne"]},
            athlete_id,
        )
        charge_totale += charge
        cle_type = a["type"] or "Autre"
        repartition_types[cle_type] = repartition_types.get(cle_type, 0) + 1

    return {
        "nb_sorties": nb,
        "distance_totale_km": round(distance_totale, 1),
        "denivele_total_m": denivele_total,
        "duree_totale_h": round(duree_totale_min / 60, 1),
        "charge_totale": round(charge_totale, 1),
        "repartition_par_type": repartition_types,
    }


def _objectifs_periode(athlete_id, debut, fin):
    conn = connexion()
    cur = conn.cursor()
    cur.execute(
        "SELECT titre, date_cible, statut, type_objectif FROM objectifs WHERE athlete_id=?",
        (athlete_id,),
    )
    lignes = cur.fetchall()
    conn.close()

    resultat = []
    for titre, date_cible_texte, statut, type_objectif in lignes:
        date_obj = parser_date_flexible(date_cible_texte)
        if date_obj is None or not (debut <= date_obj.date() <= fin):
            continue
        resultat.append({
            "titre": titre, "date_cible": date_obj.strftime("%d/%m/%Y"),
            "statut": statut, "type": type_objectif,
        })
    return resultat


def _musculation_periode(athlete_id, debut, fin):
    conn = connexion()
    cur = conn.cursor()
    cur.execute(
        "SELECT date, type_seance, groupe_musculaire FROM musculation_suivi WHERE athlete_id=?",
        (athlete_id,),
    )
    lignes = cur.fetchall()
    conn.close()

    nb_renforcement, nb_cardio_machine = 0, 0
    groupes_travailles = {}
    for date_texte, type_seance, groupe in lignes:
        date_obj = parser_date_flexible(date_texte)
        if date_obj is None or not (debut <= date_obj.date() <= fin):
            continue
        if type_seance == "Cardio machine":
            nb_cardio_machine += 1
        else:
            nb_renforcement += 1
            if groupe:
                groupes_travailles[groupe] = groupes_travailles.get(groupe, 0) + 1

    return {
        "seances_renforcement": nb_renforcement,
        "seances_cardio_machine": nb_cardio_machine,
        "groupes_travailles": groupes_travailles,
    }


def _sommeil_moyen_periode(athlete_id, debut, fin):
    conn = connexion()
    cur = conn.cursor()
    cur.execute("SELECT date, duree_heures FROM sommeil WHERE athlete_id=?", (athlete_id,))
    lignes = cur.fetchall()
    conn.close()

    valeurs = []
    for date_texte, duree in lignes:
        date_obj = parser_date_flexible(date_texte)
        if date_obj and debut <= date_obj.date() <= fin and duree is not None:
            valeurs.append(duree)
    return round(sum(valeurs) / len(valeurs), 1) if valeurs else None


def _blessures_declarees_periode(athlete_id, debut, fin):
    conn = connexion()
    cur = conn.cursor()
    cur.execute(
        "SELECT date_debut, zone_corporelle, type_blessure, statut FROM blessures WHERE athlete_id=?",
        (athlete_id,),
    )
    lignes = cur.fetchall()
    conn.close()

    resultat = []
    for date_texte, zone, type_blessure, statut in lignes:
        date_obj = parser_date_flexible(date_texte)
        if date_obj and debut <= date_obj.date() <= fin:
            resultat.append({
                "date_debut": date_obj.strftime("%d/%m/%Y"), "zone": zone,
                "type": type_blessure, "statut": statut,
            })
    return resultat


def _progression_forme(athlete_id, debut, fin):
    """Compare la Forme (TSB) au début et à la fin de la période, à
    partir de la courbe déjà calculée par interface/coach.py."""

    aujourdhui = datetime.now().date()
    nb_jours = max((aujourdhui - debut).days + 10, 35)
    serie = calculer_serie_forme(athlete_id, nb_jours=nb_jours)
    if not serie:
        return {"forme_debut_periode": None, "forme_fin_periode": None, "fitness_fin_periode": None}

    def _plus_proche(date_cible):
        candidats = [e for e in serie if e["date"] <= date_cible]
        return candidats[-1] if candidats else serie[0]

    entree_debut = _plus_proche(debut)
    entree_fin = _plus_proche(min(fin, aujourdhui))

    return {
        "forme_debut_periode": entree_debut["forme"],
        "forme_fin_periode": entree_fin["forme"],
        "fitness_fin_periode": entree_fin["fitness"],
    }


def construire_resume_periode(athlete_id, type_periode, date_ref=None):
    date_ref = date_ref or datetime.now().date()
    debut, fin = _bornes_periode(type_periode, date_ref)
    debut_prec, fin_prec = _periode_precedente(type_periode, debut)

    activites = _activites_periode(athlete_id, debut, fin)
    activites_precedentes = _activites_periode(athlete_id, debut_prec, fin_prec)

    return {
        "periode": {
            "type": type_periode,
            "du": debut.strftime("%d/%m/%Y"), "au": fin.strftime("%d/%m/%Y"),
        },
        "bilan_periode": _agreger_activites(activites, athlete_id),
        "bilan_periode_precedente": _agreger_activites(activites_precedentes, athlete_id),
        "objectifs_a_echeance": _objectifs_periode(athlete_id, debut, fin),
        "musculation": _musculation_periode(athlete_id, debut, fin),
        "sommeil_moyen_periode_h": _sommeil_moyen_periode(athlete_id, debut, fin),
        "blessures_declarees_periode": _blessures_declarees_periode(athlete_id, debut, fin),
        "progression_forme": _progression_forme(athlete_id, debut, fin),
        "acwr_actuel": calculer_acwr(athlete_id),
        "score_forme_actuel": calculer_score_forme_jour(athlete_id),
        "rythme_de_vie": contexte_fatigue_vie().get("texte"),
        "alertes_actives": generer_alertes(athlete_id),
        "dossier_technique": _dossier_technique_periode(athlete_id, debut, fin),
    }


def _dossier_technique_periode(athlete_id, debut, fin):
    try:
        from noyau.ia.analyse_technique import dossier_periode
        return dossier_periode(athlete_id, debut, fin)
    except Exception:
        return {}


def _construire_prompt_periode(type_periode, debut, fin, resume):
    from noyau.ia.analyse_technique import LEGENDE
    libelle = LIBELLES_PERIODE.get(type_periode, type_periode)
    return (
        "Tu es un entraîneur de trail et de course à pied de haut niveau, spécialiste de la "
        "planification et de l'analyse de charge. Tu rédiges le bilan technique d'un athlète sur "
        f"{libelle} (du {debut.strftime('%d/%m/%Y')} au {fin.strftime('%d/%m/%Y')}), comparé à la "
        "période précédente de même durée. Le ton est direct, précis, professionnel.\n\n"
        + CONSIGNES_COMMUNES + "\n"
        "STRUCTURE OBLIGATOIRE (ces titres exacts, dans cet ordre) :\n\n"
        "### Bilan technique de la période\n"
        "Volume en km, D+, heures et km-effort vs période précédente (variations en %), sorties "
        "longues, vitesse équivalente-plat, répartition d'intensité (% de temps facile vs 80 % visé, "
        "zones cumulées si disponibles). 6 à 9 puces chiffrées.\n\n"
        "### Objectifs\n"
        "Objectifs à échéance sur la période (atteints ou non, avec l'écart chiffré) et courses à venir "
        "avec ce que la forme actuelle permet d'en attendre ; sinon une phrase.\n\n"
        "### Progression et efficacité\n"
        "Évolution de l'indice d'efficacité (tendance_efficacite), du CTL (fitness), de la VMA et du "
        "VO2max estimés. Dis clairement si la forme progresse, stagne ou régresse, avec les chiffres, "
        "et à quoi tu l'attribues (volume, intensité, récupération). Distingue fait mesuré et "
        "hypothèse.\n\n"
        "### Charge et récupération\n"
        "Charge hebdomadaire et variations (règle des +10 %), monotonie, TSB, ACWR, HRV vs base, FC "
        "de repos, sommeil, blessures. Conclus par un niveau de risque (faible / modéré / élevé) "
        "justifié.\n\n"
        "### Plan des 7 à 14 prochains jours\n"
        "Cible chiffrée : volume (km, D+, heures), nombre et nature des séances clés (avec intensité en "
        "bpm et allure), répartition facile/dur visée, et un point de contrôle mesurable pour juger "
        "si ça se passe bien. Priorise UN levier de performance. Adapte si le rythme de vie "
        "(champ rythme_de_vie) ou la récupération l'imposent.\n\n"
        "Longueur totale : 400 à 600 mots. Pas d'introduction ni de conclusion hors sections.\n\n"
        + LEGENDE + "\n"
        "DONNÉES (JSON, calculées localement, sans donnée personnelle) :\n"
        f"{json.dumps(resume, ensure_ascii=False, separators=(',', ':'), default=str)}"
    )


def _analyse_periode_en_cache(athlete_id, type_periode, cle_periode):
    conn = connexion()
    cur = conn.cursor()
    cur.execute(
        "SELECT contenu FROM analyses_ia WHERE athlete_id=? AND type=? AND periode_cle=? "
        "ORDER BY date_generation DESC, id DESC LIMIT 1",
        (athlete_id, type_periode, cle_periode),
    )
    resultat = cur.fetchone()
    conn.close()
    return resultat


def _enregistrer_analyse_periode(athlete_id, type_periode, cle_periode, contenu):
    conn = connexion()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO analyses_ia (athlete_id, activite_id, type, periode_cle, date_generation, contenu) "
        "VALUES (?, NULL, ?, ?, ?, ?)",
        (athlete_id, type_periode, cle_periode, datetime.now().isoformat(timespec="seconds"), contenu),
    )
    conn.commit()
    conn.close()


def analyser_periode(athlete_id, type_periode, date_ref=None, forcer_regeneration=False):
    """Retourne (contenu_texte, depuis_cache, date_debut, date_fin).
    Lève ErreurAnalyseIA si la génération échoue."""

    date_ref = date_ref or datetime.now().date()
    debut, fin = _bornes_periode(type_periode, date_ref)
    cle = _cle_periode(type_periode, date_ref)

    if not forcer_regeneration:
        en_cache = _analyse_periode_en_cache(athlete_id, type_periode, cle)
        if en_cache and "Bilan technique" in en_cache[0]:
            return en_cache[0], True, debut, fin

    resume = construire_resume_periode(athlete_id, type_periode, date_ref)
    prompt = _construire_prompt_periode(type_periode, debut, fin, resume)
    contenu = _appeler_ia(prompt)
    _enregistrer_analyse_periode(athlete_id, type_periode, cle, contenu)
    return contenu, False, debut, fin


# ==================================================================
# COMMENTAIRE IA SUR UNE REPLANIFICATION DE PLAN (optionnel)
# ==================================================================
# La replanification automatique (interface/replanification.py) est
# toujours expliquée par un texte local, sans IA — cette fonction
# ajoute juste, à la demande, une reformulation plus "coach" du même
# diagnostic. Pas de mise en cache : chaque passage de replanification
# est un événement ponctuel, pas quelque chose qu'on réaffiche tel
# quel plus tard.

def _construire_prompt_replanification(resume_diagnostic, resume_changements):
    return (
        "Tu es un entraîneur de trail de haut niveau. Le plan d'entraînement d'un athlète vient d'être "
        "réajusté automatiquement par des règles simples (pas par toi) à partir de son état de forme. "
        "Voici le diagnostic et les changements appliqués. En français, en 6 à 9 lignes, tutoiement, ton "
        "technique et direct : (1) quels indicateurs ont déclenché l'ajustement et ce qu'ils signifient "
        "physiologiquement (charge/ACWR, fraîcheur TSB, récupération), (2) l'effet attendu de chaque "
        "changement sur la charge et sur la performance à moyen terme, (3) le point à surveiller dans "
        "les prochains jours avec un seuil chiffré (FC de repos, HRV, sensations, FC à allure donnée). "
        "N'invente aucun chiffre absent des données ; cite ceux qui y figurent.\n\n"
        f"Diagnostic :\n{resume_diagnostic}\n\nChangements appliqués :\n{resume_changements}"
    )


def commenter_replanification(resume_diagnostic, resume_changements):
    """Retourne un texte court (str). Lève ErreurAnalyseIA en cas
    d'échec — à l'appelant de décider si l'absence de commentaire IA
    doit bloquer l'affichage (normalement non : le résumé local suffit
    toujours)."""

    prompt = _construire_prompt_replanification(resume_diagnostic, resume_changements)
    return _appeler_ia(prompt)
