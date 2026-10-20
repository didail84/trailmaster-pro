"""
Historique de poids / état des jambes / fatigue relevé à la main début
septembre → 5 octobre 2026, importé une seule fois à la première
ouverture de l'écran « Poids & fatigue » (sans effet si l'athlète n'a pas
ce numéro, ou s'il a déjà des relevés, ou si l'import a déjà eu lieu).

Les relevés dont la date n'était pas connue (4 poids entre le 3 et le
11 septembre, un poids « début octobre ») ne sont pas inclus : à saisir
directement dans l'écran une fois la date retrouvée.
"""

from data.database import connexion, obtenir_parametre, definir_parametre

ATHLETE_ID = 18
CLE_FLAG = "suivi_corporel_historique_initial_importe"

# (date, poids_kg, etat_jambes, fatigue_jambes, fatigue_generale, notes)
LIGNES = []   # vide dans la version publique : chacun saisit ses relevés dans l'écran « Poids & fatigue »


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
