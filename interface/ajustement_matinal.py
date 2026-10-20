"""
E3 — Plan qui s'ajuste chaque matin. Au premier lancement de la journée,
chaque plan en cours (course à venir ou séances futures prévues) passe par
la replanification existante (séances ratées, ACWR, forme, FC, blessure) ;
les changements éventuels sont appliqués aux seules séances futures, avec
un commentaire expliquant pourquoi, et consignés dans l'historique.
Désactivable (paramètre « ajustement_matinal »).
"""

from datetime import date

from data.database import connexion, obtenir_parametre, definir_parametre

CLE = "ajustement_matinal"
CLE_DERNIER = "ajustement_matinal_dernier_jour"


def actif():
    return obtenir_parametre(CLE, "1") == "1"


def definir_actif(oui):
    definir_parametre(CLE, "1" if oui else "0")


def _plans_en_cours(athlete_id):
    conn = connexion()
    cur = conn.cursor()
    cur.execute("SELECT DISTINCT p.id, p.nom FROM plans_entrainement p JOIN seances_structurees s ON s.plan_id=p.id "
                "WHERE p.athlete_id=? AND s.statut='Prévue' AND s.date_prevue>=?",
                (athlete_id, date.today().isoformat()))
    res = cur.fetchall()
    conn.close()
    return res


def _replanifie_recemment(plan_id, jours=3):
    """Évite d'alléger chaque matin de plus en plus : pas de nouvel
    ajustement automatique si le plan vient d'être modifié."""
    from datetime import datetime, timedelta
    conn = connexion()
    cur = conn.cursor()
    cur.execute("SELECT MAX(date_generation) FROM replanifications WHERE plan_id=? AND nb_seances_modifiees>0", (plan_id,))
    r = cur.fetchone()[0]
    conn.close()
    try:
        return bool(r) and datetime.fromisoformat(r) > datetime.now() - timedelta(days=jours)
    except ValueError:
        return False


def ajuster_athlete(athlete_id):
    """Renvoie une liste de {plan, niveau, nb_modifiees, raisons}."""
    from interface.replanification import proposer_replanification, appliquer_replanification
    sorties = []
    for plan_id, nom in _plans_en_cours(athlete_id):
        if _replanifie_recemment(plan_id):
            continue
        try:
            _diag, niveau, raisons, props = proposer_replanification(plan_id, athlete_id)
        except Exception:
            continue
        if props:
            appliquer_replanification(plan_id, athlete_id, niveau, raisons, props)
        sorties.append({"plan": nom, "niveau": niveau, "nb_modifiees": len(props), "raisons": raisons})
    return sorties


def ajustement_du_jour(force=False):
    """Fait l'ajustement une seule fois par jour pour tous les athlètes.
    Renvoie (liste_resultats, message) ou ([], None) s'il n'y a rien à faire."""
    if not actif() and not force:
        return [], None
    aujourd = date.today().isoformat()
    if not force and obtenir_parametre(CLE_DERNIER, "") == aujourd:
        return [], None
    conn = connexion()
    cur = conn.cursor()
    cur.execute("SELECT id FROM athletes")
    ids = [r[0] for r in cur.fetchall()]
    conn.close()
    res = []
    for a in ids:
        res += ajuster_athlete(a)
    definir_parametre(CLE_DERNIER, aujourd)
    n = sum(r["nb_modifiees"] for r in res)
    if n:
        return res, f"Ton plan a été ajusté ce matin : {n} séance{'s' if n > 1 else ''} modifiée{'s' if n > 1 else ''} (détail dans chaque séance)."
    return res, None
