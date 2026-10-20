"""
Registre des cartes du tableau de bord : quelles cartes existent, si
elles occupent une place "carte" (petite, plusieurs par ligne) ou
"grand" (pleine largeur), et dans quel ordre elles s'affichent.

La configuration choisie par l'utilisateur (quelles cartes activées,
dans quel ordre) est stockée en base sous forme de liste d'identifiants
dans parametres_app — une carte absente de la liste est simplement
masquée.
"""

import json

from data.database import obtenir_parametre, definir_parametre


WIDGETS_DISPONIBLES = {
    "alertes_proactives": {"nom": "Alertes proactives (surcharge/fatigue)", "type": "grand"},
    "apercu_cartes": {"nom": "Aperçu : forme du moment (6 cartes)", "type": "grand"},
    "apercu_courbe": {"nom": "Aperçu : forme et fatigue sur 6 mois", "type": "grand"},
    "dernieres_sorties": {"nom": "Aperçu : dernières sorties", "type": "grand"},
    "fiche_coureur": {"nom": "Fiche du coureur (photo + stats)", "type": "carte"},
    "charge_semaine": {"nom": "Charge de la semaine", "type": "carte"},
    "entrainements_semaine": {"nom": "Jours actifs cette semaine", "type": "carte"},
    "forme": {"nom": "Forme (interprétation ACWR)", "type": "carte"},
    "acwr": {"nom": "ACWR", "type": "carte"},
    "indice_forme": {"nom": "Indice de forme (score/100)", "type": "carte"},
    "distance_cumulee": {"nom": "Distance cumulée (période au choix)", "type": "carte"},
    "denivele_cumule": {"nom": "Dénivelé D+ cumulé (période au choix)", "type": "carte"},
    "duree_cumulee": {"nom": "Temps d'entraînement cumulé (période au choix)", "type": "carte"},
    "graphique_charge": {"nom": "Graphique d'évolution de la charge", "type": "grand"},
    "graphique_sur_mesure": {"nom": "Graphique polyvalent (mesure + période au choix)", "type": "grand"},
    "mini_forme_fatigue": {"nom": "Mini graphique Fitness/Fatigue/Forme (30 jours)", "type": "grand"},
    "tableau_croise": {"nom": "Tableau croisé (forme, charge, rythme de vie, courses)", "type": "grand"},
}

ORDRE_PAR_DEFAUT = [
    "alertes_proactives",
    "apercu_cartes",
    "apercu_courbe",
    "dernieres_sorties",
    "fiche_coureur",
    "charge_semaine",
    "entrainements_semaine",
    "indice_forme",
    "forme",
    "acwr",
    "distance_cumulee",
    "denivele_cumule",
    "duree_cumulee",
    "graphique_charge",
    "graphique_sur_mesure",
    "mini_forme_fatigue",
    "tableau_croise",
]


BLOCS_APERCU = ["apercu_cartes", "apercu_courbe", "dernieres_sorties"]


def obtenir_configuration_dashboard():
    """Retourne la liste ordonnée des identifiants de cartes à
    afficher (les cartes non listées sont masquées).

    Une configuration déjà enregistrée (avant l'ajout de nouvelles
    cartes à une mise à jour) ne les contient pas encore : on les
    ajoute automatiquement à la suite, pour qu'une personne qui a déjà
    personnalisé son tableau de bord voie quand même les nouveautés
    sans avoir à aller les cocher elle-même dans Réglages."""

    brut = obtenir_parametre("dashboard_widgets")
    if brut:
        try:
            liste = json.loads(brut)
            liste_valide = [w for w in liste if w in WIDGETS_DISPONIBLES]
            if liste_valide:
                # Une nouveauté se place juste après la carte qui la précède
                # dans l'ordre par défaut (et à la fin si aucune n'est présente),
                # pour qu'un tableau de bord déjà personnalisé la voie à sa place.
                resultat = list(liste_valide)
                # Les blocs « Aperçu » (forme du moment, courbe, dernières sorties)
                # se placent tout en haut d'un tableau de bord déjà personnalisé.
                manquants_en_tete = [w for w in BLOCS_APERCU if w not in resultat]
                resultat = manquants_en_tete + resultat
                for i, w in enumerate(ORDRE_PAR_DEFAUT):
                    if w in resultat:
                        continue
                    position = len(resultat)
                    for precedent in reversed(ORDRE_PAR_DEFAUT[:i]):
                        if precedent in resultat:
                            position = resultat.index(precedent) + 1
                            break
                    resultat.insert(position, w)
                return resultat
        except (ValueError, TypeError):
            pass

    return list(ORDRE_PAR_DEFAUT)


def definir_configuration_dashboard(liste_ids):
    definir_parametre("dashboard_widgets", json.dumps(liste_ids))
