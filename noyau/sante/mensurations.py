"""
Mensurations saisies avec le poids (v107) : tour de taille, hanches,
poitrine, cuisse, bras et masse grasse. Toutes facultatives.

Contrairement au poids, une mensuration ne dépend pas du moment de la journée :
on prend tous les relevés, du plus ancien au plus récent.
"""

from data.database import connexion

# colonne SQL -> (libellé, unité, mots reconnus dans l'en-tête d'un fichier importé)
MESURES = {
    "tour_taille_cm": ("Tour de taille", "cm", ("taille",)),
    "tour_hanches_cm": ("Tour de hanches", "cm", ("hanche",)),
    "tour_poitrine_cm": ("Tour de poitrine", "cm", ("poitrine", "torse")),
    "tour_cuisse_cm": ("Tour de cuisse", "cm", ("cuisse",)),
    "tour_bras_cm": ("Tour de bras", "cm", ("bras",)),
    "masse_grasse_pct": ("Masse grasse", "%", ("masse grasse", "graisse")),
}


def serie_mesure(athlete_id, colonne):
    """[(date_iso, valeur)] du plus ancien au plus récent (dernier relevé du jour)."""
    if colonne not in MESURES:
        raise ValueError(colonne)
    conn = connexion()
    cur = conn.cursor()
    cur.execute(
        f"SELECT date, {colonne} FROM suivi_corporel WHERE athlete_id=? AND {colonne} IS NOT NULL "
        f"AND {colonne} > 0 ORDER BY date, id", (athlete_id,))
    par_jour = {}
    for d, v in cur.fetchall():
        par_jour[str(d)[:10]] = float(v)
    conn.close()
    return sorted(par_jour.items())


def resume_mesures(athlete_id):
    """{colonne: {"libelle","unite","derniere","date","premiere","date_premiere","ecart","nb"}}
    pour les mesures qui ont au moins un relevé."""
    out = {}
    for col, (lib, unite, _) in MESURES.items():
        s = serie_mesure(athlete_id, col)
        if not s:
            continue
        out[col] = {
            "libelle": lib, "unite": unite, "nb": len(s),
            "derniere": s[-1][1], "date": s[-1][0],
            "premiere": s[0][1], "date_premiere": s[0][0],
            "ecart": round(s[-1][1] - s[0][1], 1) if len(s) >= 2 else None,
        }
    return out
