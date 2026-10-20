"""
Replanification automatique d'un plan d'entraînement — TrailMaster Pro.

Principe : à la demande (bouton dans l'écran "Plans d'entraînement"),
on regarde ce qui s'est réellement passé récemment — séances ratées,
charge d'entraînement (ACWR), forme du jour, dérive de fréquence
cardiaque — et on ajuste les séances À VENIR du plan (jamais celles
déjà passées) en conséquence : volume réduit, séance de qualité
transformée en sortie facile, séance manquée récupérée le lendemain si
la forme le permet.

100% local et déterministe par défaut (aucune dépendance réseau) :
chaque séance modifiée reçoit un commentaire clair expliquant pourquoi.
Un commentaire supplémentaire, rédigé par l'IA (Gemini/Groq, la même
que pour l'analyse de sortie), peut être ajouté en option pour
reformuler le diagnostic dans un ton "coach" plus naturel — mais le
plan est réajusté et expliqué de façon fiable même sans IA/internet.

Limites à connaître (comme le reste du moteur de coaching) :
  - La détection de dérive de FC compare la FC moyenne des dernières
    sorties à celle des précédentes, sans normaliser par l'allure ni
    le dénivelé — un signal utile mais approximatif, pas un diagnostic
    médical.
  - Les séances déjà "Réalisée" ne sont jamais modifiées ; seules les
    séances futures encore "Prévue" du plan choisi sont concernées.
"""

import json
from datetime import datetime, timedelta

from data.database import connexion
from interface.date_utils import parser_date_flexible
from interface.conformite import distance_totale_prevue_km
from interface.coach import (
    calculer_acwr, calculer_score_forme_jour, _blessures_actives, obtenir_seuils_alertes,
)


# ------------------------------------------------------------------
# DÉTECTION — séances manquées
# ------------------------------------------------------------------

def _seances_du_plan(plan_id):
    conn = connexion()
    cur = conn.cursor()
    cur.execute(
        "SELECT id, nom, type_seance, date_prevue, statut, etapes_json, "
        "commentaire_replanification "
        "FROM seances_structurees WHERE plan_id=? ORDER BY date_prevue",
        (plan_id,),
    )
    lignes = cur.fetchall()
    conn.close()

    resultat = []
    for id_, nom, type_seance, date_prevue, statut, etapes_json, commentaire in lignes:
        date_obj = parser_date_flexible(date_prevue)
        resultat.append({
            "id": id_, "nom": nom, "type_seance": type_seance,
            "date_prevue": date_obj.date() if date_obj else None,
            "date_prevue_texte": date_prevue,
            "statut": statut,
            "etapes": json.loads(etapes_json) if etapes_json else [],
            "commentaire_replanification": commentaire,
        })
    return resultat


def detecter_seances_manquees(plan_id, aujourdhui=None):
    """Séances du plan dont la date prévue est passée mais qui ne sont
    toujours pas marquées 'Réalisée' — jamais modifié en base ici,
    seulement détecté."""

    aujourdhui = aujourdhui or datetime.now().date()
    seances = _seances_du_plan(plan_id)
    return [
        s for s in seances
        if s["date_prevue"] and s["date_prevue"] < aujourdhui and s["statut"] != "Réalisée"
    ]


def detecter_anomalie_fc(athlete_id, nb_recentes=3, nb_baseline=15, seuil_pct=6.0):
    """Compare la FC moyenne des nb_recentes dernières sorties à celle
    des nb_baseline précédentes. Un écart positif marqué peut indiquer
    fatigue, chaleur, début de maladie... — un signal à croiser avec le
    reste, pas un diagnostic en soi."""

    conn = connexion()
    cur = conn.cursor()
    cur.execute(
        "SELECT date, frequence_cardiaque_moyenne FROM activites "
        "WHERE athlete_id=? AND frequence_cardiaque_moyenne IS NOT NULL AND duree > 600",
        (athlete_id,),
    )
    lignes = cur.fetchall()
    conn.close()

    datees = []
    for date_texte, fc in lignes:
        date_obj = parser_date_flexible(date_texte)
        if date_obj is not None:
            datees.append((date_obj, fc))
    datees.sort(key=lambda t: t[0], reverse=True)

    recentes = [fc for _, fc in datees[:nb_recentes]]
    baseline = [fc for _, fc in datees[nb_recentes:nb_recentes + nb_baseline]]

    if len(recentes) < nb_recentes or len(baseline) < 5:
        return {
            "anomalie": False, "ecart_pct": None,
            "fc_recente": None, "fc_baseline": None,
            "message": "Pas assez d'historique de FC pour comparer.",
        }

    fc_recente = sum(recentes) / len(recentes)
    fc_baseline = sum(baseline) / len(baseline)
    ecart_pct = round((fc_recente - fc_baseline) / fc_baseline * 100, 1)
    anomalie = ecart_pct >= seuil_pct

    if anomalie:
        message = (
            f"FC moyenne des {nb_recentes} dernières sorties en hausse de {ecart_pct}% "
            f"par rapport à tes {nb_baseline} sorties précédentes ({round(fc_recente)} vs "
            f"{round(fc_baseline)} bpm) — signe possible de fatigue, chaleur ou récupération "
            "incomplète."
        )
    else:
        message = "FC récente cohérente avec ton historique."

    return {
        "anomalie": anomalie, "ecart_pct": ecart_pct,
        "fc_recente": round(fc_recente), "fc_baseline": round(fc_baseline),
        "message": message,
    }


# ------------------------------------------------------------------
# DIAGNOSTIC GLOBAL
# ------------------------------------------------------------------

def construire_diagnostic(plan_id, athlete_id, aujourdhui=None):
    aujourdhui = aujourdhui or datetime.now().date()

    manquees = detecter_seances_manquees(plan_id, aujourdhui)
    manquees_7j = [s for s in manquees if (aujourdhui - s["date_prevue"]).days <= 7]
    manquees_14j = [s for s in manquees if (aujourdhui - s["date_prevue"]).days <= 14]

    acwr_info = calculer_acwr(athlete_id)
    forme_info = calculer_score_forme_jour(athlete_id)
    fc_info = detecter_anomalie_fc(athlete_id)
    blessure_active = bool(_blessures_actives(athlete_id))

    return {
        "aujourdhui": aujourdhui,
        "manquees": manquees,
        "nb_manquees_7j": len(manquees_7j),
        "nb_manquees_14j": len(manquees_14j),
        "acwr": acwr_info,
        "forme": forme_info,
        "fc": fc_info,
        "blessure_active": blessure_active,
    }


# ------------------------------------------------------------------
# DÉCISION — quel niveau d'ajustement appliquer
# ------------------------------------------------------------------

def decider_niveau(diagnostic):
    """Retourne (niveau, raisons: list[str]).
    niveau ∈ {'alleger_fort', 'alleger_leger', 'reprise_progressive', 'stable'}."""

    raisons = []
    acwr = diagnostic["acwr"]["acwr"]
    forme = diagnostic["forme"]
    fc = diagnostic["fc"]
    seuils = obtenir_seuils_alertes()

    signal_fort = False
    signal_leger = False

    if diagnostic["blessure_active"]:
        signal_fort = True
        raisons.append("Blessure active en cours.")

    if acwr is not None and acwr > seuils["acwr_risque"]:
        signal_fort = True
        raisons.append(f"ACWR très élevé ({acwr}) — risque de blessure important.")
    elif acwr is not None and acwr > seuils["acwr_attention"]:
        signal_leger = True
        raisons.append(f"ACWR en hausse ({acwr}).")

    if fc["anomalie"] and fc["ecart_pct"] is not None and fc["ecart_pct"] >= 12:
        signal_fort = True
        raisons.append(fc["message"])
    elif fc["anomalie"]:
        signal_leger = True
        raisons.append(fc["message"])

    if forme["score"] < 30:
        signal_fort = True
        raisons.append(f"Score de forme du jour bas ({forme['score']}/100) — {forme['interpretation']}")
    elif forme["score"] < 50:
        signal_leger = True
        raisons.append(f"Score de forme du jour moyen ({forme['score']}/100).")
    elif forme.get("fatigue_vie", {}).get("actif"):
        # Le score de forme reste correct, mais le rythme de vie du jour
        # (lever tôt, longue journée — Réglages) mérite d'être mentionné
        # même sans déclencher d'allègement à lui seul.
        raisons.append(
            "Rythme de vie de semaine chargé aujourd'hui (déjà intégré au score de forme "
            "ci-dessus), à garder en tête sans que ça justifie seul un allègement."
        )

    if diagnostic["nb_manquees_7j"] >= seuils["manquees_7j"]:
        signal_leger = True
        raisons.append(f"{diagnostic['nb_manquees_7j']} séances manquées cette semaine.")

    if signal_fort:
        return "alleger_fort", raisons
    if signal_leger:
        return "alleger_leger", raisons

    if diagnostic["nb_manquees_14j"] >= seuils["manquees_14j"] and (acwr is None or acwr < 0.9):
        raisons.append(
            f"{diagnostic['nb_manquees_14j']} séances manquées sur 14 jours mais charge "
            "actuelle faible (aucun signe de fatigue) — reprise en douceur plutôt qu'un "
            "retour brutal au volume prévu."
        )
        return "reprise_progressive", raisons

    raisons.append("Aucun signal de fatigue ou de retard significatif détecté.")
    return "stable", raisons


FACTEUR_VOLUME = {
    "alleger_fort": 0.70,
    "alleger_leger": 0.85,
    "reprise_progressive": 0.80,
    "stable": 1.0,
}

TYPES_QUALITE = {"Fractionné", "Côtes"}

FENETRE_JOURS = {
    "alleger_fort": 7,
    "alleger_leger": 7,
    "reprise_progressive": 7,
    "stable": 0,
}


# ------------------------------------------------------------------
# PROPOSITIONS DE CHANGEMENT
# ------------------------------------------------------------------

def _ajuster_etapes(etapes, facteur_volume, retirer_intensite):
    nouvelles = []
    for etape in etapes:
        nouvelle = dict(etape)
        nouvelle["valeur"] = round(nouvelle["valeur"] * facteur_volume, 2)
        if retirer_intensite:
            nouvelle["allure_cible"] = None
            nouvelle["fc_cible"] = None
        nouvelles.append(nouvelle)
    return nouvelles


def proposer_replanification(plan_id, athlete_id, aujourdhui=None):
    """Retourne (diagnostic, niveau, raisons, propositions).
    propositions : liste de dicts {seance_id, avant, apres, commentaire}
    pour chaque séance future qui serait modifiée — n'écrit rien en
    base (voir appliquer_replanification)."""

    aujourdhui = aujourdhui or datetime.now().date()
    diagnostic = construire_diagnostic(plan_id, athlete_id, aujourdhui)
    niveau, raisons = decider_niveau(diagnostic)

    propositions = []
    seances = _seances_du_plan(plan_id)
    futures = [s for s in seances if s["date_prevue"] and s["date_prevue"] >= aujourdhui
               and s["statut"] == "Prévue"]

    fenetre = FENETRE_JOURS[niveau]
    facteur = FACTEUR_VOLUME[niveau]

    # 1) Rattrapage d'une séance manquée récente, seulement si tout va
    #    bien par ailleurs (niveau stable) — sinon on laisse tomber la
    #    séance plutôt que de surcharger un athlète déjà fatigué.
    TYPES_NON_RATTRAPABLES = {"Sortie longue", "Course de préparation"}
    if niveau == "stable":
        manquees_recentes = [
            s for s in diagnostic["manquees"]
            if (aujourdhui - s["date_prevue"]).days <= 3
            and s["type_seance"] not in TYPES_NON_RATTRAPABLES
        ]
        if len(diagnostic["manquees"]) == 1 and manquees_recentes and futures:
            manquee = manquees_recentes[0]
            dates_occupees = {s["date_prevue"] for s in futures}
            nouvelle_date = aujourdhui + timedelta(days=1)
            for _ in range(5):
                if nouvelle_date not in dates_occupees:
                    break
                nouvelle_date += timedelta(days=1)
            commentaire = (
                f"Séance manquée du {manquee['date_prevue'].strftime('%d/%m')} déplacée "
                f"au {nouvelle_date.strftime('%d/%m')} — charge stable, aucun signal de "
                "fatigue détecté, tu peux la rattraper."
            )
            propositions.append({
                "seance_id": manquee["id"],
                "avant": {"date": manquee["date_prevue_texte"], "nom": manquee["nom"]},
                "apres": {"date": nouvelle_date.strftime("%Y-%m-%d"), "nom": manquee["nom"]},
                "commentaire": commentaire,
                "type_changement": "deplacement",
            })

    # 2) Allègement des séances à venir dans la fenêtre concernée.
    if fenetre > 0:
        limite = aujourdhui + timedelta(days=fenetre)
        for s in futures:
            if s["date_prevue"] > limite:
                continue
            retirer_intensite = niveau == "alleger_fort" and s["type_seance"] in TYPES_QUALITE
            if facteur == 1.0 and not retirer_intensite:
                continue

            nouvelles_etapes = _ajuster_etapes(s["etapes"], facteur, retirer_intensite)
            distance_avant = distance_totale_prevue_km(s["etapes"])
            distance_apres = distance_totale_prevue_km(nouvelles_etapes)

            morceaux_commentaire = []
            if facteur < 1.0:
                morceaux_commentaire.append(f"volume réduit de {round((1 - facteur) * 100)}%")
            if retirer_intensite:
                morceaux_commentaire.append("intensité retirée (séance transformée en sortie facile)")
            commentaire = (
                f"Allégée ({', '.join(morceaux_commentaire)}) — " + " ; ".join(raisons)
            )

            propositions.append({
                "seance_id": s["id"],
                "avant": {
                    "nom": s["nom"],
                    "distance_km": distance_avant,
                },
                "apres": {
                    "nom": s["nom"] + (" (allégée)" if " (allégée)" not in s["nom"] else ""),
                    "distance_km": distance_apres,
                    "etapes": nouvelles_etapes,
                },
                "commentaire": commentaire,
                "type_changement": "allegement",
            })

    return diagnostic, niveau, raisons, propositions


# ------------------------------------------------------------------
# APPLICATION EN BASE
# ------------------------------------------------------------------

def appliquer_replanification(plan_id, athlete_id, niveau, raisons, propositions, resume_ia=None):
    """Écrit les propositions en base (séances futures uniquement) et
    journalise le passage dans la table 'replanifications'."""

    conn = connexion()
    cur = conn.cursor()

    for prop in propositions:
        if prop["type_changement"] == "deplacement":
            cur.execute(
                "UPDATE seances_structurees SET date_prevue=?, commentaire_replanification=? "
                "WHERE id=?",
                (prop["apres"]["date"], prop["commentaire"], prop["seance_id"]),
            )
        else:  # allegement
            cur.execute(
                "UPDATE seances_structurees SET nom=?, etapes_json=?, commentaire_replanification=? "
                "WHERE id=?",
                (
                    prop["apres"]["nom"],
                    json.dumps(prop["apres"]["etapes"]),
                    prop["commentaire"],
                    prop["seance_id"],
                ),
            )

    resume = " ; ".join(raisons)
    cur.execute(
        "INSERT INTO replanifications "
        "(plan_id, athlete_id, date_generation, niveau_ajustement, resume, resume_ia, "
        "nb_seances_modifiees) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            plan_id, athlete_id, datetime.now().isoformat(timespec="seconds"),
            niveau, resume, resume_ia, len(propositions),
        ),
    )

    conn.commit()
    conn.close()


def historique_replanifications(plan_id):
    conn = connexion()
    cur = conn.cursor()
    cur.execute(
        "SELECT date_generation, niveau_ajustement, resume, resume_ia, nb_seances_modifiees "
        "FROM replanifications WHERE plan_id=? ORDER BY date_generation DESC",
        (plan_id,),
    )
    lignes = cur.fetchall()
    conn.close()
    return lignes
