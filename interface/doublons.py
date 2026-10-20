"""
Détection de doublons entre activités : deux activités du même
athlète, à quelques minutes d'écart et à distance proche, sont
considérées comme la même sortie enregistrée deux fois (typiquement :
une fois via un import manuel Garmin/Strava, une fois via la synchro
Strava directe).

Important : la fenêtre de temps doit rester courte (quelques minutes),
pas "le même jour" — sinon deux vraies sorties différentes le même
jour (fréquent : plusieurs relais d'une course, ou deux séances dans
la journée) seraient prises à tort pour des doublons.
"""

from data.database import connexion, supprimer_activite, fusionner_activites
from interface.date_utils import parser_date_flexible


FENETRE_TEMPS_MINUTES = 15

# Une sortie suivie en direct depuis le téléphone (GPS de téléphone,
# moins précis) ne doit jamais être choisie comme "version à garder"
# par défaut quand une autre source existe pour la même sortie — voir
# interface/suivi_direct.py.
SOURCE_SUIVI_DIRECT = "Suivi en direct (téléphone)"


def detecter_doublons(athlete_id):
    """Retourne une liste de groupes de doublons, chaque groupe étant
    une liste de dicts {id, date, nom, type, distance, denivele,
    duree, source} triée par qualité décroissante (la plus complète
    en premier, à garder de préférence)."""

    conn = connexion()
    cur = conn.cursor()
    cur.execute(
        "SELECT id, date, nom, type, distance, denivele, duree, "
        "frequence_cardiaque_moyenne, source FROM activites WHERE athlete_id=?",
        (athlete_id,),
    )
    lignes = cur.fetchall()
    conn.close()

    activites = []
    for id_, date, nom, type_, distance, denivele, duree, fc, source in lignes:
        date_obj = parser_date_flexible(date)
        if date_obj is None:
            continue
        activites.append({
            "id": id_, "date": date, "date_obj": date_obj, "nom": nom, "type": type_,
            "distance": distance or 0, "denivele": denivele or 0,
            "duree": duree or 0, "fc": fc, "source": source,
        })

    activites.sort(key=lambda a: a["date_obj"])

    groupes = []
    deja_groupees = set()

    for i, a in enumerate(activites):
        if a["id"] in deja_groupees:
            continue

        groupe = [a]
        for b in activites[i + 1:]:
            ecart_minutes = (b["date_obj"] - a["date_obj"]).total_seconds() / 60
            if ecart_minutes > FENETRE_TEMPS_MINUTES:
                break
            if b["id"] in deja_groupees:
                continue
            ecart_distance = abs(a["distance"] - b["distance"])
            if ecart_distance <= max(0.3, a["distance"] * 0.1):
                groupe.append(b)

        if len(groupe) > 1:
            for membre in groupe:
                deja_groupees.add(membre["id"])
            groupe.sort(
                key=lambda x: (
                    x["source"] != SOURCE_SUIVI_DIRECT,
                    x["duree"] > 0, x["denivele"] > 0, x["fc"] is not None,
                ),
                reverse=True,
            )
            groupes.append(groupe)

    return groupes


def supprimer_doublons(ids_a_supprimer):
    """Supprime les activités indiquées, avec la cascade complète
    (trace GPS, efforts sur segments, analyse IA, et détachement des
    séances/résultats/blessures liés) — voir data.database.supprimer_activite."""

    for id_ in ids_a_supprimer:
        supprimer_activite(id_)


def fusionner_groupe(groupe_trie, index_survivant=0):
    """Fusionne un groupe de doublons déjà trié (comme retourné par
    detecter_doublons) : garde `groupe_trie[index_survivant]` (par
    défaut le premier, la version jugée la plus fiable) et fusionne
    tous les autres membres dedans plutôt que de les supprimer à
    l'aveugle — voir data.database.fusionner_activites."""

    if len(groupe_trie) < 2:
        return None

    survivant = groupe_trie[index_survivant]
    for i, membre in enumerate(groupe_trie):
        if i != index_survivant:
            fusionner_activites(survivant["id"], membre["id"])

    return survivant["id"]
