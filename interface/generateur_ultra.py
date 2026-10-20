"""
Programme Ultra long terme (TrailMaster Pro) — génère un programme
progressif de plusieurs mois à plusieurs années vers un objectif long
(par défaut : un ultra-trail de 60 km dans 2 ans), construit par blocs
successifs plutôt qu'une seule montée en charge continue :

  - chaque bloc vise une "course repère" à une distance intermédiaire,
    progressivement plus longue (ex. 15 km -> 24 km -> 33 km -> 42 km ->
    51 km -> 60 km), avec sa propre périodisation base/développement/
    affûtage (réutilise le moteur d'interface/generateur_plan.py) ;
  - le volume de départ du tout premier bloc est estimé à partir de
    l'entraînement RÉELLEMENT effectué récemment (pas une valeur
    générique), pour ne pas partir sur une base irréaliste ;
  - chaque semaine combine : une sortie longue le week-end, une séance
    spécifique (fractionné/côtes) de semaine plafonnée à ~45-60 min,
    des séances de musculation (2 à 4/semaine, configurable), et — une
    semaine sur deux — une sortie détente/groupe plus longue (1h-1h15) ;
  - environ une fois par mois, la sortie longue est remplacée par une
    "course de préparation" avec allure, FC cible et temps visé calculés
    à partir des records/prédictions de l'athlète.

Comme le reste du moteur de coaching : 100% local, aucune dépendance
réseau, et le résultat n'est qu'une proposition — le plan enregistré
reste ensuite modifiable séance par séance, et ajustable semaine après
semaine par la replanification automatique (interface/replanification.py)
qui regarde ce qui a réellement été fait, la forme, la FC et le rythme
de vie.

Limites à connaître :
  - La prédiction de temps (formule de Riegel) est fiable jusqu'au
    marathon ; au-delà, une dégradation d'allure supplémentaire est
    appliquée pour approcher la réalité de l'ultra (terrain, ravito,
    marche en côte...), mais reste une estimation grossière, pas une
    prescription individualisée par un vrai coach.
  - Les jours de terrain n'étant pas fixes dans la semaine, ils ne
    sont pas modélisés ici — seuls lever/trajets/horaires fixes du
    rythme de vie (Réglages) sont pris en compte, via le score de
    forme du jour une fois le plan en cours.
"""

import json
from datetime import date, timedelta

from data.database import connexion
from interface.conformite import parser_allure
from interface.records import calculer_records, DISTANCES_REFERENCE, EXPOSANT_RIEGEL
from interface.generateur_plan import (
    FACTEUR_NIVEAU,
    _phase_semaine,
    _est_semaine_recuperation,
    _volume_semaine,
    _distance_longue_semaine,
    _formater_allure,
)


# ------------------------------------------------------------------
# BASELINE — estimation du niveau actuel à partir de l'entraînement
# réellement effectué (pas une valeur générique de table).
# ------------------------------------------------------------------

def estimer_baseline_actuelle(athlete_id, depuis_date=None):
    """Regarde les sorties Trail/Course/Route réellement enregistrées
    depuis depuis_date (par défaut le 25 août de l'année en cours, ou
    de l'année précédente si on est encore avant cette date) et en
    tire un volume hebdomadaire moyen et la plus longue sortie — sert
    de point de départ réaliste au premier bloc du programme plutôt
    qu'une valeur générique."""

    aujourdhui = date.today()
    if depuis_date is None:
        depuis_date = date(aujourdhui.year, 8, 25)
        if depuis_date > aujourdhui:
            depuis_date = date(aujourdhui.year - 1, 8, 25)

    conn = connexion()
    cur = conn.cursor()
    cur.execute(
        "SELECT date, distance FROM activites WHERE athlete_id=? "
        "AND type IN ('Trail','Course','Route') AND distance IS NOT NULL",
        (athlete_id,),
    )
    lignes = cur.fetchall()
    conn.close()

    from interface.date_utils import parser_date_flexible

    distances = []
    for date_texte, distance in lignes:
        date_obj = parser_date_flexible(date_texte)
        if date_obj is not None and date_obj.date() >= depuis_date:
            distances.append((date_obj.date(), distance))

    if not distances:
        return {
            "nb_semaines_donnees": 0,
            "volume_hebdo_moyen_km": None,
            "plus_longue_recente_km": None,
        }

    nb_jours = max((aujourdhui - depuis_date).days, 1)
    nb_semaines = max(nb_jours / 7, 1)
    volume_total = sum(d for _, d in distances)

    return {
        "nb_semaines_donnees": round(nb_semaines, 1),
        "volume_hebdo_moyen_km": round(volume_total / nb_semaines, 1),
        "plus_longue_recente_km": round(max(d for _, d in distances), 1),
    }


# ------------------------------------------------------------------
# CIBLES DE COURSE — allure / FC / temps visé pour une distance donnée
# ------------------------------------------------------------------

# Au-delà du marathon, Riegel sous-estime la dégradation d'allure réelle
# en ultra-trail (terrain, dénivelé, marche, ravitaillement...) — cette
# table ajoute une pénalité progressive, très approximative mais plus
# réaliste qu'une simple extrapolation linéaire.
PENALITE_ULTRA = [
    (42.2, 1.00),
    (50.0, 1.12),
    (60.0, 1.20),
    (80.0, 1.32),
]


def _facteur_penalite_ultra(distance_km):
    if distance_km <= 42.2:
        return 1.0
    for (borne, facteur) in PENALITE_ULTRA:
        if distance_km <= borne:
            return facteur
    return PENALITE_ULTRA[-1][1]


def _predire_temps_distance(records, distance_km):
    """Généralise calculer_predictions() (interface/records.py) à une
    distance quelconque (pas seulement 5/10/semi/marathon), avec la
    pénalité ultra ci-dessus pour tout ce qui dépasse le marathon."""

    connues = [
        (distance_reference, records[label]["duree_s"])
        for label, distance_reference in DISTANCES_REFERENCE
        if records.get(label)
    ]
    if not connues:
        return None

    estimations = [
        duree_connue * (distance_km / distance_connue) ** EXPOSANT_RIEGEL
        for distance_connue, duree_connue in connues
    ]
    duree_s = (sum(estimations) / len(estimations)) * _facteur_penalite_ultra(distance_km)
    return duree_s


def _zone_fc(distance_km, fc_max):
    if fc_max is None:
        return None, None
    if distance_km <= 21.1:
        bas, haut = 0.82, 0.90
    elif distance_km <= 42.2:
        bas, haut = 0.78, 0.85
    else:
        bas, haut = 0.70, 0.78
    return round(fc_max * bas), round(fc_max * haut)


def _formater_duree_h(secondes):
    secondes = int(round(secondes))
    h, reste = divmod(secondes, 3600)
    m = reste // 60
    if h > 0:
        return f"{h}h{m:02d}"
    return f"{m}min"


def cibles_course(athlete_id, distance_km):
    """Retourne {allure_min_km, allure_texte, duree_s, duree_texte,
    fc_min, fc_max, texte} pour une distance donnée, à partir des
    records/prédictions de l'athlète — None si aucun record connu
    pour extrapoler."""

    conn = connexion()
    cur = conn.cursor()
    cur.execute("SELECT fc_max FROM athletes WHERE id=?", (athlete_id,))
    ligne = cur.fetchone()
    conn.close()
    fc_max = ligne[0] if ligne else None

    records = calculer_records(athlete_id)
    duree_s = _predire_temps_distance(records, distance_km)
    fc_min, fc_haut = _zone_fc(distance_km, fc_max)

    if duree_s is None:
        return {
            "allure_min_km": None, "allure_texte": None,
            "duree_s": None, "duree_texte": None,
            "fc_min": fc_min, "fc_max": fc_haut,
            "texte": "Pas encore assez de courses enregistrées pour estimer une allure cible.",
        }

    allure = (duree_s / 60) / distance_km
    allure_texte = _formater_allure(allure)
    duree_texte = _formater_duree_h(duree_s)

    morceaux = [f"~{duree_texte} visé"]
    if allure_texte:
        morceaux.append(f"allure {allure_texte}/km")
    if fc_min and fc_haut:
        morceaux.append(f"FC {fc_min}-{fc_haut} bpm")
    texte = ", ".join(morceaux)
    if distance_km > 42.2:
        texte += " (estimation prudente au-delà du marathon, à ajuster à l'usage)"

    return {
        "allure_min_km": round(allure, 2), "allure_texte": allure_texte,
        "duree_s": round(duree_s), "duree_texte": duree_texte,
        "fc_min": fc_min, "fc_max": fc_haut,
        "texte": texte,
    }


# ------------------------------------------------------------------
# BLOCS — progression par courses repères jusqu'à l'objectif final
# ------------------------------------------------------------------

NOMS_BLOCS = [
    "Bloc 1 — Fondation",
    "Bloc 2 — Développement I",
    "Bloc 3 — Développement II",
    "Bloc 4 — Spécifique long I",
    "Bloc 5 — Spécifique long II",
    "Bloc 6 — Finalisation ultra",
]

# Proportions de la distance finale utilisées comme "course repère" de
# fin de bloc (le dernier bloc se termine sur l'objectif lui-même).
PROPORTIONS_REPERE = [0.25, 0.40, 0.55, 0.70, 0.85, 1.00]


def _repartir_semaines(nb_semaines, nb_blocs=6):
    base = nb_semaines // nb_blocs
    reste = nb_semaines - base * nb_blocs
    repartition = [base] * nb_blocs
    for i in range(reste):
        repartition[nb_blocs - 1 - i] += 1  # le reste va aux derniers blocs (plus longs, réalistes)
    return repartition


# ------------------------------------------------------------------
# CONSTRUCTION D'UNE SEMAINE (structure spécifique au programme Ultra)
# ------------------------------------------------------------------

TYPES_QUALITE_ULTRA = {"Fractionné", "Côtes"}


def _plafonner_duree_qualite(etapes, allures, duree_max_min=58):
    """Réduit proportionnellement le volume d'une séance de qualité
    pour rester dans la fenêtre ~45-60 min demandée, sans changer le
    nombre de répétitions (juste leur longueur)."""

    from interface.conformite import duree_totale_prevue_min

    duree = duree_totale_prevue_min(etapes)
    if not duree or duree <= duree_max_min:
        return etapes
    facteur = duree_max_min / duree
    for e in etapes:
        e["valeur"] = round(e["valeur"] * facteur, 2)
    return etapes


def _etape_fc(type_, mode, valeur, allure_min_km=None, fc_cible=None):
    return {
        "type": type_, "mode": mode, "valeur": round(valeur, 2),
        "allure_cible": _formater_allure(allure_min_km) if allure_min_km else None,
        "fc_cible": fc_cible,
    }


def _construire_semaine_ultra(
    indice_global, phase, recuperation, volume, longue, allures, fc_max,
    jour_specifique, jour_longue, jours_musculation, nb_musculation,
    sortie_detente, semaine_speciale=None, nom_course=None, type_course=None,
    distance_course=None, etape_course=None,
):
    """semaine_speciale : None (semaine normale), "repere" (course de
    préparation mensuelle — la séance spécifique de qualité est
    supprimée cette semaine-là, la course faisant déjà office de
    stimulus intense) ou "objectif" (semaine de la course finale —
    taper complet : pas de séance de qualité, pas de musculation,
    juste la course et de courts décrassages)."""

    seances = []

    # --- Sortie longue (week-end), ou course si semaine spéciale ---
    if semaine_speciale:
        seances.append({
            "jour_offset": jour_longue,
            "nom": nom_course,
            "type_seance": type_course,
            "etapes": [etape_course],
        })
        longue = distance_course
    else:
        seances.append({
            "jour_offset": jour_longue,
            "nom": "Sortie longue",
            "type_seance": "Sortie longue",
            "etapes": [_etape_fc(
                "Effort", "distance", longue, allures.get("endurance"),
                round(fc_max * 0.75) if fc_max else None,
            )],
        })

    reste_volume = max(volume - longue, 0)

    # --- Séance spécifique de semaine (fractionné/côtes), plafonnée ---
    # Jamais la même semaine qu'une course (repère ou objectif) : la
    # course fournit déjà le stimulus intense, empiler un fractionné/
    # côtes en plus serait justement le genre de surcharge à éviter.
    if semaine_speciale == "objectif":
        pass  # rien d'autre cette semaine-là : repos/décrassage seulement, voir plus bas
    elif semaine_speciale == "repere" or phase == "base" or recuperation:
        # Course de préparation, phase base, ou semaine de récupération :
        # pas de séance de qualité, juste une endurance légère à la place.
        seances.append({
            "jour_offset": jour_specifique,
            "nom": "Endurance fondamentale",
            "type_seance": "Endurance fondamentale",
            "etapes": [_etape_fc(
                "Effort", "distance", min(reste_volume * 0.4, 10), allures.get("endurance"),
            )],
        })
        reste_volume = max(reste_volume * 0.6, 0)
    else:
        # Phase développement/affûtage, semaine normale : séance de
        # qualité (fractionné/côtes), plafonnée à ~45-60 min.
        type_qualite = "Fractionné" if indice_global % 2 == 1 else "Côtes"
        allure_qualite = allures.get("fractionne") if type_qualite == "Fractionné" else allures.get("seuil")
        fc_qualite = round(fc_max * 0.90) if fc_max else None

        etapes_qualite = [_etape_fc("Échauffement", "distance", 2, allures.get("endurance"))]
        n_repets = 6 if type_qualite == "Fractionné" and phase == "developpement" else (
            4 if type_qualite == "Fractionné" else 5
        )
        distance_effort = 0.8 if type_qualite == "Fractionné" else 0.6
        for _ in range(n_repets):
            etapes_qualite.append(_etape_fc("Effort", "distance", distance_effort, allure_qualite, fc_qualite))
            etapes_qualite.append(_etape_fc("Récupération", "distance", 0.4, allures.get("recuperation")))
        etapes_qualite.append(_etape_fc("Retour au calme", "distance", 2, allures.get("endurance")))
        etapes_qualite = _plafonner_duree_qualite(etapes_qualite, allures)

        volume_qualite = sum(e["valeur"] for e in etapes_qualite if e["mode"] == "distance")
        seances.append({
            "jour_offset": jour_specifique,
            "nom": type_qualite,
            "type_seance": type_qualite,
            "etapes": etapes_qualite,
        })
        reste_volume = max(reste_volume - volume_qualite, 0)

    # --- Sorties d'endurance restantes / sortie détente ---
    jours_deja_pris = {jour_longue, jour_specifique}
    jours_endurance = [j for j in range(7) if j not in jours_deja_pris][:2]

    if semaine_speciale == "objectif":
        # Semaine de la course finale : uniquement de très courts
        # décrassages, pas de volume — le travail est déjà fait.
        for j in jours_endurance[:1]:
            seances.append({
                "jour_offset": j,
                "nom": "Décrassage",
                "type_seance": "Récupération",
                "etapes": [_etape_fc("Effort", "duree", 20, allures.get("recuperation"))],
            })
    elif jours_endurance:
        volume_par_jour = reste_volume / len(jours_endurance)
        for i, j in enumerate(jours_endurance):
            if sortie_detente and i == len(jours_endurance) - 1:
                # Une semaine sur deux : sortie détente/groupe, plat et
                # tranquille, plafonnée à 1h-1h15 plutôt qu'en distance stricte.
                seances.append({
                    "jour_offset": j,
                    "nom": "Sortie détente / groupe",
                    "type_seance": "Récupération",
                    "etapes": [_etape_fc(
                        "Effort", "duree", 70, allures.get("endurance"),
                        round(fc_max * 0.72) if fc_max else None,
                    )],
                })
            else:
                seances.append({
                    "jour_offset": j,
                    "nom": "Endurance fondamentale",
                    "type_seance": "Endurance fondamentale",
                    "etapes": [_etape_fc("Effort", "distance", volume_par_jour, allures.get("endurance"))],
                })

    # --- Musculation (2 à 4x/semaine — sur les jours déjà courus le midi
    #     en priorité, comme dans le rythme de vie réel de l'athlète,
    #     puis sur des jours dédiés si besoin). Coupée entièrement la
    #     semaine de la course finale (taper complet avant l'objectif).
    if semaine_speciale != "objectif":
        jours_course = {s["jour_offset"] for s in seances}
        jours_muscu_prioritaires = [j for j in jours_musculation if j in jours_course]
        jours_muscu_autres = [j for j in jours_musculation if j not in jours_course]
        ordre_muscu = (jours_muscu_prioritaires + jours_muscu_autres)[:nb_musculation]

        for j in ordre_muscu:
            seances.append({
                "jour_offset": j,
                "nom": "Musculation",
                "type_seance": "Musculation",
                "etapes": [_etape_fc("Effort", "duree", 60)],
            })

    return seances


def generer_programme_ultra(
    athlete_id,
    distance_finale_km=60.0,
    nb_semaines=104,
    date_debut=None,
    jour_sortie_longue=6,       # dimanche
    jour_seance_specifique=3,   # jeudi
    jours_musculation=(0, 2, 4),  # lundi, mercredi, vendredi par défaut
    nb_musculation_semaine=3,
    allure_objectif_finale_texte=None,
    niveau="Intermédiaire",
):
    """Retourne (semaines, baseline, blocs_info).

    semaines : liste de dicts {indice, bloc, phase, recuperation,
    volume_km, seances: [...]}, compatible avec l'aperçu existant de
    l'écran Plans d'entraînement.

    blocs_info : détail de chaque bloc (nom, semaines, distance repère,
    cibles de course) pour affichage résumé."""

    date_debut = date_debut or date.today()
    nb_musculation_semaine = max(0, min(4, nb_musculation_semaine))

    baseline = estimer_baseline_actuelle(athlete_id)
    facteur_niveau = FACTEUR_NIVEAU.get(niveau, 1.0)

    volume_debut_bloc1 = baseline["volume_hebdo_moyen_km"] or (20 * facteur_niveau)
    long_debut_bloc1 = baseline["plus_longue_recente_km"] or (10 * facteur_niveau)
    # Garde-fou : jamais un volume de départ ridiculement bas (données
    # quasi inexistantes) ni au contraire une sortie longue de départ
    # déjà proche du premier repère (le bloc doit encore progresser).
    volume_debut_bloc1 = max(volume_debut_bloc1, 12.0)
    long_debut_bloc1 = max(min(long_debut_bloc1, distance_finale_km * PROPORTIONS_REPERE[0] * 0.8), 8.0)

    # Volume hebdomadaire au pic du DERNIER bloc — plafonné à une valeur
    # réaliste et sûre pour un amateur préparant un ultra de cette
    # distance (des coureurs d'élite dépassent rarement 160-180 km/semaine
    # même en pic spécifique ; on reste nettement en dessous). Les blocs
    # intermédiaires interpolent linéairement entre le volume de départ
    # réel et ce plafond, plutôt que d'être déduits mécaniquement de la
    # distance de la sortie longue (ce qui avait fait exploser le volume
    # à 200 km/semaine dans une première version — corrigé ici).
    volume_pic_final = min(round(70 * facteur_niveau + distance_finale_km * 0.5), 130)
    volume_pic_final = max(volume_pic_final, round(volume_debut_bloc1 * 1.4))

    repartition_semaines = _repartir_semaines(nb_semaines, len(NOMS_BLOCS))

    allure_objectif_finale = parser_allure(allure_objectif_finale_texte) if allure_objectif_finale_texte else None

    conn = connexion()
    cur = conn.cursor()
    cur.execute("SELECT fc_max FROM athletes WHERE id=?", (athlete_id,))
    ligne = cur.fetchone()
    conn.close()
    fc_max = ligne[0] if ligne else None

    semaines = []
    blocs_info = []
    indice_global = 0
    volume_debut_bloc = volume_debut_bloc1
    long_debut_bloc = long_debut_bloc1

    for i_bloc, (nom_bloc, nb_semaines_bloc, proportion) in enumerate(
        zip(NOMS_BLOCS, repartition_semaines, PROPORTIONS_REPERE)
    ):
        if nb_semaines_bloc <= 0:
            continue

        distance_repere = round(distance_finale_km * proportion, 1)
        dernier_bloc = i_bloc == len(NOMS_BLOCS) - 1

        # Sortie longue pic du bloc : ~85% de la distance repère (marge
        # de sécurité sous la distance réelle de l'épreuve), sauf le
        # dernier bloc où le "pic" EST l'objectif final. Volume hebdo pic
        # interpolé linéairement entre le volume de départ réel et le
        # plafond du dernier bloc (calculé plus haut) — progression
        # régulière et bornée sur les 6 blocs plutôt qu'une explosion.
        long_pic = distance_repere if dernier_bloc else round(distance_repere * 0.85, 1)
        progression_bloc = i_bloc / (len(NOMS_BLOCS) - 1)
        volume_pic = round(
            volume_debut_bloc1 + (volume_pic_final - volume_debut_bloc1) * progression_bloc
        )
        volume_pic = max(volume_pic, round(volume_debut_bloc * 1.10))

        semaines_affutage_bloc = max(2, round(nb_semaines_bloc * 0.15))

        allure_objectif_bloc = allure_objectif_finale
        if allure_objectif_bloc is None:
            cibles = cibles_course(athlete_id, distance_repere)
            allure_objectif_bloc = cibles.get("allure_min_km")
        allures = _allures_semaine(allure_objectif_bloc) if allure_objectif_bloc else {
            "endurance": None, "seuil": None, "fractionne": None, "recuperation": None,
        }

        cibles_repere = cibles_course(athlete_id, distance_repere)

        for indice_bloc in range(1, nb_semaines_bloc + 1):
            indice_global += 1
            phase = _phase_semaine(indice_bloc, nb_semaines_bloc, semaines_affutage_bloc)
            recuperation = _est_semaine_recuperation(indice_bloc, phase)
            volume = _volume_semaine(
                indice_bloc, nb_semaines_bloc, volume_debut_bloc, volume_pic, phase, semaines_affutage_bloc
            )
            longue = _distance_longue_semaine(
                indice_bloc, nb_semaines_bloc, long_debut_bloc, long_pic, phase, semaines_affutage_bloc
            )

            derniere_semaine_bloc = indice_bloc == nb_semaines_bloc
            objectif_final = dernier_bloc and derniere_semaine_bloc
            # Course de préparation environ une fois par mois : décalée
            # d'un cran (%4==2) par rapport aux semaines de récupération
            # (%4==0) pour ne jamais tomber la même semaine que celles-ci
            # — sinon la condition "not recuperation" ne se déclenche
            # jamais puisque les deux tombent alors sur les mêmes semaines.
            est_semaine_repere = (
                objectif_final
                or (phase != "base" and not recuperation and not derniere_semaine_bloc
                    and indice_bloc % 4 == 2)
            )

            sortie_detente = (not est_semaine_repere) and (indice_global % 2 == 0) and phase != "base"

            semaine_speciale = None
            nom_course = type_course = etape_course = None
            distance_course = None
            if est_semaine_repere:
                semaine_speciale = "objectif" if objectif_final else "repere"
                distance_course = distance_finale_km if objectif_final else min(longue, distance_repere)
                cibles_semaine = cibles_course(athlete_id, distance_course)
                fc_cible_course = (
                    round((cibles_semaine["fc_min"] + cibles_semaine["fc_max"]) / 2)
                    if cibles_semaine.get("fc_min") and cibles_semaine.get("fc_max") else None
                )
                nom_course = (
                    f"🏁 OBJECTIF — Ultra {distance_finale_km:g} km" if objectif_final
                    else f"🏆 Course de préparation — {distance_course:g} km"
                )
                if cibles_semaine["allure_texte"]:
                    nom_course += f" ({cibles_semaine['texte']})"
                type_course = "Course de préparation"
                etape_course = _etape_fc(
                    "Effort", "distance", distance_course,
                    cibles_semaine.get("allure_min_km"), fc_cible_course,
                )

            seances_semaine = _construire_semaine_ultra(
                indice_global, phase, recuperation, volume, longue, allures, fc_max,
                jour_seance_specifique, jour_sortie_longue, list(jours_musculation),
                nb_musculation_semaine, sortie_detente,
                semaine_speciale=semaine_speciale, nom_course=nom_course,
                type_course=type_course, distance_course=distance_course,
                etape_course=etape_course,
            )

            semaines.append({
                "indice": indice_global,
                "bloc": nom_bloc,
                "phase": phase,
                "recuperation": recuperation,
                "volume_km": volume,
                "seances": seances_semaine,
            })

        blocs_info.append({
            "nom": nom_bloc,
            "nb_semaines": nb_semaines_bloc,
            "distance_repere_km": distance_repere,
            "volume_pic_km": volume_pic,
            "cibles": cibles_repere,
        })

        # Le bloc suivant redémarre depuis une base réduite (deload)
        # plutôt qu'en repartant du pic précédent — évite d'enchaîner
        # une montée en charge continue de 2 ans sans respiration.
        volume_debut_bloc = round(volume_pic * 0.65)
        long_debut_bloc = round(long_pic * 0.60, 1)

    return semaines, baseline, blocs_info


# ------------------------------------------------------------------
# RAPPORT DE FIN DE BLOC — résumé prévu vs réalisé (volume, D+, forme)
# pour un bloc donné, généré à la transition vers le bloc suivant.
# ------------------------------------------------------------------

import re


def obtenir_blocs_plan(plan_id):
    """Retourne la liste ordonnée des noms de blocs détectés dans les
    séances d'un plan (format "S12 [Bloc 2 — Développement I] — Fractionné"
    généré par dialogue_programme_ultra.py) — liste vide pour un plan
    classique (generateur_plan.py) qui ne structure pas ses séances par bloc."""

    conn = connexion()
    cur = conn.cursor()
    cur.execute("SELECT nom FROM seances_structurees WHERE plan_id=? ORDER BY date_prevue", (plan_id,))
    noms = [n for (n,) in cur.fetchall()]
    conn.close()

    blocs = []
    for nom in noms:
        m = re.search(r"\[(.+?)\]", nom or "")
        if m and m.group(1) not in blocs:
            blocs.append(m.group(1))
    return blocs


def generer_rapport_bloc(plan_id, athlete_id, nom_bloc):
    """Compare volume/D+ prévus vs réalisés, et forme moyenne, sur les
    semaines d'un bloc donné du programme Ultra — texte prêt à afficher/
    enregistrer (interface/plans_entrainement.py), aucun appel IA."""

    from interface.conformite import distance_totale_prevue_km
    from interface.coach import calculer_serie_forme
    from interface.date_utils import parser_date_flexible

    conn = connexion()
    cur = conn.cursor()
    cur.execute(
        "SELECT nom, type_seance, date_prevue, etapes_json, activite_id "
        "FROM seances_structurees WHERE plan_id=? AND nom LIKE ? ORDER BY date_prevue",
        (plan_id, f"%[{nom_bloc}]%"),
    )
    lignes = cur.fetchall()
    conn.close()

    if not lignes:
        return f"Aucune séance trouvée pour « {nom_bloc} »."

    dates = [parser_date_flexible(d) for (_, _, d, _, _) in lignes if d]
    dates = [d.date() for d in dates if d is not None]
    if not dates:
        return f"Dates introuvables pour « {nom_bloc} »."
    date_min, date_max = min(dates), max(dates)

    volume_prevu = 0.0
    for _, _, _, etapes_json, _ in lignes:
        if not etapes_json:
            continue
        try:
            etapes = json.loads(etapes_json)
        except (ValueError, TypeError):
            continue
        volume_prevu += distance_totale_prevue_km(etapes) or 0.0

    conn = connexion()
    cur = conn.cursor()
    cur.execute(
        "SELECT distance, denivele FROM activites WHERE athlete_id=? AND date>=? AND date<=?",
        (athlete_id, date_min.isoformat(), (date_max + timedelta(days=1)).isoformat()),
    )
    activites = cur.fetchall()
    conn.close()

    distance_reelle = sum(d or 0 for d, _ in activites)
    denivele_reel = sum(dp or 0 for _, dp in activites)

    serie_forme = calculer_serie_forme(athlete_id, nb_jours=(date.today() - date_min).days + 5)
    formes_periode = [j["forme"] for j in serie_forme if date_min <= j["date"] <= date_max]
    forme_moyenne = round(sum(formes_periode) / len(formes_periode), 1) if formes_periode else None

    nb_semaines = max(round((date_max - date_min).days / 7), 1)
    ecart_volume_pct = (
        round((distance_reelle - volume_prevu) / volume_prevu * 100) if volume_prevu > 0 else None
    )

    lignes_texte = [
        f"Rapport de bloc — {nom_bloc}",
        f"Période : {date_min.strftime('%d/%m/%Y')} → {date_max.strftime('%d/%m/%Y')} (~{nb_semaines} semaines)",
        f"Volume prévu : {round(volume_prevu)} km — réalisé : {round(distance_reelle)} km"
        + (f" ({'+' if ecart_volume_pct >= 0 else ''}{ecart_volume_pct} %)" if ecart_volume_pct is not None else ""),
        f"Dénivelé D+ cumulé réalisé : {round(denivele_reel)} m",
    ]
    if forme_moyenne is not None:
        lignes_texte.append(f"Forme moyenne sur la période : {forme_moyenne}")
    if ecart_volume_pct is not None:
        if ecart_volume_pct <= -20:
            lignes_texte.append("→ Volume nettement en retrait par rapport au plan : le bloc suivant "
                                 "part d'une base réelle plus prudente que prévu.")
        elif ecart_volume_pct >= 20:
            lignes_texte.append("→ Volume nettement dépassé par rapport au plan : reste vigilant sur "
                                 "la progression du bloc suivant (risque de surcharge).")
        else:
            lignes_texte.append("→ Volume globalement conforme au plan.")

    return "\n".join(lignes_texte)


def _allures_semaine(allure_objectif_min_km):
    if not allure_objectif_min_km:
        return {}
    return {
        "endurance": allure_objectif_min_km * 1.20,
        "seuil": allure_objectif_min_km * 1.03,
        "fractionne": allure_objectif_min_km * 0.90,
        "recuperation": allure_objectif_min_km * 1.35,
    }
