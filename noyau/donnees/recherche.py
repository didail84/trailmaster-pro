"""
Recherche globale (palette Ctrl/Cmd+F) : sorties, séances, résultats de
course, objectifs et parcours dont le nom contient le texte cherché.

Reprise telle quelle de interface/recherche_globale.py (étape 1.4a).
"""

from noyau.donnees import base


def rechercher_partout(texte, athlete_id, nb_max_par_categorie):
    """Liste de (catégorie, libellé, date, id) ; [] si le texte est vide."""
    if not texte or not texte.strip():
        return []

    motif = f"%{texte.strip()}%"
    resultats = []
    conn = base.connexion()
    cur = conn.cursor()

    condition_athlete = "AND athlete_id = ?" if athlete_id else ""
    parametres_base = (athlete_id,) if athlete_id else ()

    cur.execute(
        f"SELECT id, nom, date, type FROM activites "
        f"WHERE nom LIKE ? {condition_athlete} ORDER BY date DESC LIMIT ?",
        (motif, *parametres_base, nb_max_par_categorie),
    )
    for id_, nom, date, type_ in cur.fetchall():
        resultats.append(("Activité", nom or type_ or "(sans nom)", date or "", id_))

    cur.execute(
        f"SELECT id, nom, date_prevue FROM seances_structurees "
        f"WHERE nom LIKE ? {condition_athlete} ORDER BY date_prevue DESC LIMIT ?",
        (motif, *parametres_base, nb_max_par_categorie),
    )
    for id_, nom, date in cur.fetchall():
        resultats.append(("Séance", nom, date or "", id_))

    cur.execute(
        f"SELECT id, nom_course, date FROM resultats_courses "
        f"WHERE nom_course LIKE ? {condition_athlete} ORDER BY date DESC LIMIT ?",
        (motif, *parametres_base, nb_max_par_categorie),
    )
    for id_, nom, date in cur.fetchall():
        resultats.append(("Résultat de course", nom, date or "", id_))

    cur.execute(
        f"SELECT id, titre, date_cible FROM objectifs "
        f"WHERE (titre LIKE ? OR description LIKE ?) {condition_athlete} "
        f"ORDER BY date_cible DESC LIMIT ?",
        (motif, motif, *parametres_base, nb_max_par_categorie),
    )
    for id_, titre, date in cur.fetchall():
        resultats.append(("Objectif", titre, date or "", id_))

    cur.execute(
        f"SELECT id, nom, date_ajout FROM parcours_gpx "
        f"WHERE nom LIKE ? {condition_athlete} ORDER BY date_ajout DESC LIMIT ?",
        (motif, *parametres_base, nb_max_par_categorie),
    )
    for id_, nom, date in cur.fetchall():
        resultats.append(("Parcours", nom, date or "", id_))

    conn.close()
    return resultats
