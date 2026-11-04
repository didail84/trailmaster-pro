"""
Accès aux profils des coureurs (table `athletes`).

Requêtes reprises telles qu'elles étaient dans les écrans (étape 1.4a).
Les fonctions déjà présentes dans data.database (ajouter_athlete,
obtenir_athletes…) restent utilisables : elles seront regroupées ici à
l'étape 2.
"""

from noyau.donnees import base

COLONNES_PROFIL = ("nom", "prenom", "age", "sexe", "taille", "poids",
                   "fc_repos", "fc_max", "fc_seuil", "vma", "vo2max", "niveau")


def valeurs(athlete_id, *colonnes):
    """Colonnes choisies d'un athlète (tuple) ou None."""
    return base.valeurs("athletes", athlete_id, colonnes)


def valeur(athlete_id, colonne):
    """Une seule valeur du profil, ou None (athlète inconnu ou champ vide)."""
    ligne = valeurs(athlete_id, colonne)
    return ligne[0] if ligne else None


def lister_pour_tableau():
    """(id, nom, prenom, age, sexe, taille, poids, fc_repos, vma, niveau), le plus récent d'abord."""
    return base.lire_tous("""
        SELECT id, nom, prenom, age, sexe, taille, poids,
               fc_repos, vma, niveau
        FROM athletes
        ORDER BY id DESC
    """)


def fiche(athlete_id):
    """Profil complet (14 colonnes, photo comprise) ou None."""
    return base.lire_un("""
        SELECT id, nom, prenom, age, sexe, taille, poids,
               fc_repos, fc_max, fc_seuil, vma, vo2max, niveau, photo_path
        FROM athletes
        WHERE id=?
    """, (athlete_id,))


def modifier_profil(athlete_id, nom, prenom, age, sexe, taille, poids,
                    fc_repos, fc_max, fc_seuil, vma, vo2max, niveau):
    base.ecrire("""
        UPDATE athletes
        SET nom=?, prenom=?, age=?, sexe=?, taille=?, poids=?,
            fc_repos=?, fc_max=?, fc_seuil=?, vma=?, vo2max=?, niveau=?
        WHERE id=?
    """, (nom, prenom, age, sexe, taille, poids, fc_repos, fc_max, fc_seuil,
          vma, vo2max, niveau, athlete_id))


def definir_vma(athlete_id, vma):
    base.ecrire("UPDATE athletes SET vma=? WHERE id=?", (vma, athlete_id))


def supprimer(athlete_id):
    base.ecrire("DELETE FROM athletes WHERE id=?", (athlete_id,))
