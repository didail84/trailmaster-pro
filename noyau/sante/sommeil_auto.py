"""
Poursuite automatique du remplissage du Sommeil, jour après jour, selon
le rythme habituel déclaré par l'athlète (coucher 22h30 tous les jours,
lever 4h30 en semaine, 8h00 le samedi, 7h00 le dimanche s'il y a eu une
sortie ce jour-là sinon 8h00) — exactement le même rythme que le
rattrapage ponctuel fait fin septembre 2026, mais appelé automatiquement
à chaque ouverture de l'écran Sommeil plutôt qu'à la demande, pour ne
jamais avoir à redemander un rattrapage plus tard.

Ne complète jamais le jour courant (pas encore terminé) ni les jours
déjà renseignés — n'insère que les jours manquants entre la dernière
entrée existante et hier inclus.
"""

from datetime import date, timedelta

from data.database import connexion


NOTE_REMPLISSAGE_AUTO = (
    "Rempli automatiquement à partir du rythme habituel déclaré (coucher 22h30, "
    "lever 4h30 en semaine / 8h00 le samedi / 7h00 ou 8h00 le dimanche selon sortie)."
)


def _a_couru_ce_jour(cur, athlete_id, jour_iso):
    cur.execute(
        "SELECT 1 FROM activites WHERE athlete_id=? AND date LIKE ? AND type IN ('Trail','Course') LIMIT 1",
        (athlete_id, f"{jour_iso}%"),
    )
    return cur.fetchone() is not None


def _valeurs_pour_jour(cur, athlete_id, jour):
    jour_semaine = jour.weekday()  # 0=lundi ... 5=samedi, 6=dimanche
    jour_iso = jour.isoformat()

    if jour_semaine == 5:  # samedi
        return "22:30", "08:00", 9.5
    if jour_semaine == 6:  # dimanche
        if _a_couru_ce_jour(cur, athlete_id, jour_iso):
            return "22:30", "07:00", 8.5
        return "22:30", "08:00", 9.5
    return "22:30", "04:30", 6.0  # semaine


def combler_sommeil_manquant():
    """Pour chaque athlète ayant déjà au moins une entrée Sommeil,
    insère les jours manquants entre sa dernière entrée et hier inclus.
    N'agit jamais sur un athlète sans aucune entrée existante (on ne
    décide pas d'un rythme à sa place sans base de départ connue), et
    jamais sur un jour déjà renseigné. Renvoie le nombre de lignes
    insérées (0 si rien à faire, y compris hors connexion/erreur)."""

    hier = date.today() - timedelta(days=1)

    conn = connexion()
    cur = conn.cursor()

    cur.execute("SELECT DISTINCT athlete_id FROM sommeil WHERE athlete_id IS NOT NULL")
    athletes = [ligne[0] for ligne in cur.fetchall()]

    total_insere = 0
    for athlete_id in athletes:
        cur.execute("SELECT MAX(date) FROM sommeil WHERE athlete_id=?", (athlete_id,))
        resultat = cur.fetchone()
        derniere_date_str = resultat[0] if resultat else None
        if not derniere_date_str:
            continue

        try:
            derniere_date = date.fromisoformat(str(derniere_date_str)[:10])
        except ValueError:
            continue

        jour = derniere_date + timedelta(days=1)
        while jour <= hier:
            jour_iso = jour.isoformat()
            cur.execute(
                "SELECT 1 FROM sommeil WHERE athlete_id=? AND date=?", (athlete_id, jour_iso)
            )
            if cur.fetchone() is None:
                coucher, lever, duree = _valeurs_pour_jour(cur, athlete_id, jour)
                cur.execute(
                    """
                    INSERT INTO sommeil
                        (athlete_id, date, heure_coucher, heure_lever, duree_heures, reveils_nombre, notes)
                    VALUES (?, ?, ?, ?, ?, 0, ?)
                    """,
                    (athlete_id, jour_iso, coucher, lever, duree, NOTE_REMPLISSAGE_AUTO),
                )
                total_insere += 1
            jour += timedelta(days=1)

    conn.commit()
    conn.close()
    return total_insere
