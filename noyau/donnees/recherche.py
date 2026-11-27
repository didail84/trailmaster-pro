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

    # v109 — recherche partout : courses à venir, matériel, personnes et coureurs
    cur.execute(
        f"SELECT id, nom, date FROM courses_calendrier WHERE (nom LIKE ? OR lieu LIKE ?) "
        f"{'AND (athlete_id = ? OR athlete_id IS NULL)' if athlete_id else ''} ORDER BY date LIMIT ?",
        (motif, motif, *parametres_base, nb_max_par_categorie),
    )
    for id_, nom, date in cur.fetchall():
        resultats.append(("Course", nom, date or "", id_))

    cur.execute(
        f"SELECT id, nom, date_achat FROM materiel WHERE nom LIKE ? {condition_athlete} LIMIT ?",
        (motif, *parametres_base, nb_max_par_categorie),
    )
    for id_, nom, date in cur.fetchall():
        resultats.append(("Matériel", nom, date or "", id_))

    try:
        cur.execute(
            "SELECT id, trim(prenom || ' ' || nom), '' FROM personnes WHERE nom LIKE ? OR prenom LIKE ? "
            "OR (prenom || ' ' || nom) LIKE ? LIMIT ?", (motif, motif, motif, nb_max_par_categorie))
        for id_, nom, date in cur.fetchall():
            resultats.append(("Personne", nom, date, id_))
    except Exception:                      # base ancienne sans la table personnes
        pass
    conn.close()

    try:
        from noyau.bibliotheque import regles as biblio
        for i, livre in enumerate(biblio.livres(recherche=texte.strip())[:nb_max_par_categorie]):
            resultats.append(("Livre", biblio.titre_affiche(livre), str(livre.get("annee") or ""), livre.get("id", i)))
    except Exception:
        pass

    t = _sans_accents(texte.strip().lower())
    n = 0
    for section, mots in SECTIONS_REGLAGES:
        if n < nb_max_par_categorie and (t in _sans_accents(section.lower()) or any(t in m for m in mots)):
            resultats.append(("Réglage", section, "", section))
            n += 1
    return resultats


SECTIONS_REGLAGES = [
    ("Coach et IA", ["ia", "analyse", "gemini", "claude", "ton", "coach", "moteur", "groq"]),
    ("Montre et connecteurs", ["garmin", "strava", "montre", "connecteur", "pont", "drive", "agenda", "spotify"]),
    ("Apparence", ["theme", "couleur", "sombre", "clair", "nuit", "soleil", "accent", "icone"]),
    ("Rythme de vie", ["travail", "trajet", "lever", "fatigue", "rythme"]),
    ("Notifications", ["alerte", "rappel", "notification", "barre des menus", "materiel", "chaussure"]),
    ("Données et sauvegarde", ["sauvegarde", "export", "import", "restaurer", "synchro"]),
    ("Modules", ["module", "club", "organisation", "kids"]),
    ("Mises à jour", ["version", "mise a jour", "relais", "github"]),
]


def _sans_accents(t):
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFD", t) if unicodedata.category(c) != "Mn")
