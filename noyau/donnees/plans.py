"""
Accès aux plans d'entraînement (tables `plans_entrainement` et
`rapports_bloc`) et à leurs séances.

Requêtes reprises telles qu'elles étaient dans les écrans (étape 1.4b).
Un plan et toutes ses séances sont enregistrés ensemble, ou pas du tout.
"""

from noyau.donnees import base, seances


def creer_avec_seances(champs_plan, liste_seances):
    """champs_plan : dict {colonne: valeur} du plan ; liste_seances : dicts
    {athlete_id, nom, type_seance, date_prevue, etapes_json}. Le plan et
    ses séances sont écrits dans une seule transaction. Renvoie l'id du plan."""
    with base.transaction() as cur:
        plan_id = base.inserer("plans_entrainement", champs_plan, cur)
        for s in liste_seances:
            seances.creer({**s, "plan_id": plan_id}, cur=cur)
    return plan_id


def lister(athlete_id=None):
    """(id, nom, distance_cible, niveau, nb_semaines, date_debut), le plus récent d'abord."""
    if athlete_id is None:
        return base.lire_tous(
            "SELECT id, nom, distance_cible, niveau, nb_semaines, date_debut "
            "FROM plans_entrainement ORDER BY date_creation DESC"
        )
    return base.lire_tous(
        "SELECT id, nom, distance_cible, niveau, nb_semaines, date_debut "
        "FROM plans_entrainement WHERE athlete_id=? ORDER BY date_creation DESC",
        (athlete_id,),
    )


def avancement(plan_id):
    """(nombre de séances, nombre réalisées — None s'il n'y a aucune séance)."""
    return base.lire_un(
        "SELECT COUNT(*), SUM(CASE WHEN statut='Réalisée' THEN 1 ELSE 0 END) "
        "FROM seances_structurees WHERE plan_id=?",
        (plan_id,),
    )


def supprimer(plan_id):
    """Supprime le plan, TOUTES ses séances et ce qui en dépend (comparaisons
    prévu/réalisé des séances, historique de replanification, rapports de
    bloc), ensemble. Avant l'étape 1.4b, un plan ayant un rapport de bloc ou
    une replanification ne pouvait pas être supprimé : la base refusait."""
    with base.transaction() as cur:
        cur.execute("DELETE FROM comparaisons_courses WHERE seance_id IN "
                    "(SELECT id FROM seances_structurees WHERE plan_id=?)", (plan_id,))
        cur.execute("DELETE FROM replanifications WHERE plan_id=?", (plan_id,))
        cur.execute("DELETE FROM rapports_bloc WHERE plan_id=?", (plan_id,))
        cur.execute("DELETE FROM seances_structurees WHERE plan_id=?", (plan_id,))
        cur.execute("DELETE FROM plans_entrainement WHERE id=?", (plan_id,))


def enregistrer_rapport_bloc(plan_id, athlete_id, nom_bloc, contenu):
    return base.ecrire(
        "INSERT INTO rapports_bloc (plan_id, athlete_id, nom_bloc, contenu) VALUES (?, ?, ?, ?)",
        (plan_id, athlete_id, nom_bloc, contenu),
    )
