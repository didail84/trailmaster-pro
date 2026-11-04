"""
Historique de poids / état des jambes / fatigue relevé à la main début
septembre → 5 octobre 2026, importé une seule fois à la première
ouverture de l'écran « Poids & récupération » (sans effet si l'athlète n'a pas
ce numéro, ou s'il a déjà des relevés, ou si l'import a déjà eu lieu).

Les relevés dont la date n'était pas connue (4 poids entre le 3 et le
11 septembre, un poids « début octobre ») ne sont pas inclus : à saisir
directement dans l'écran une fois la date retrouvée.
"""

from data.database import connexion, obtenir_parametre, definir_parametre

ATHLETE_ID = 18
CLE_FLAG = "suivi_corporel_historique_initial_importe"

# (date, poids_kg, etat_jambes, fatigue_jambes, fatigue_generale, notes)
LIGNES = [
    ("2026-09-03", 90.0, None, None, None, "Date approximative (« vers le 3 septembre »), poids ≈ 90 kg."),
    ("2026-09-11", None, "Normales", None, None, None),
    ("2026-09-14", 88.6, "Fatiguées", None, 7, "Jambes fatiguées et douloureuses après le trail du dimanche ; fatigue 7/10 après la sortie."),
    ("2026-09-15", None, "Normales", None, None, "Aucune douleur ; poids non mesuré."),
    ("2026-09-19", 87.3, "Normales", None, None, "Sans douleur, pas fatigué."),
    ("2026-09-20", 88.6, None, None, None, None),
    ("2026-09-21", 88.6, "Normales", None, 4, None),
    ("2026-09-22", 88.1, None, None, None, None),
    ("2026-09-24", 86.8, None, None, None, "Date approximative (« vers le 24–25 septembre »)."),
    ("2026-09-25", 86.6, None, None, None, "Date approximative (« vers le 24–25 septembre »)."),
    ("2026-10-04", 87.8, "Normales", None, 4, "Normales au réveil, puis courbatures après le trail."),
    ("2026-10-05", 87.7, "Courbatures", None, 5, "Quadriceps et mollets sensibles, davantage que la veille."),
]


def importer_historique_initial():
    if obtenir_parametre(CLE_FLAG) == "1":
        return 0

    conn = connexion()
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM athletes WHERE id=?", (ATHLETE_ID,))
    if cur.fetchone() is None:
        conn.close()
        return 0
    cur.execute("SELECT COUNT(*) FROM suivi_corporel WHERE athlete_id=?", (ATHLETE_ID,))
    deja = cur.fetchone()[0]
    if not deja:
        for ligne in LIGNES:
            cur.execute(
                "INSERT INTO suivi_corporel (athlete_id, date, poids_kg, etat_jambes, "
                "fatigue_jambes, fatigue_generale, notes) VALUES (?,?,?,?,?,?,?)",
                (ATHLETE_ID,) + ligne,
            )
        conn.commit()
    conn.close()
    definir_parametre(CLE_FLAG, "1")
    return 0 if deja else len(LIGNES)
