"""
Outils communs de l'accès aux données : lecture, écriture et
transaction, au-dessus de data.database.connexion().

Avec `cur=None`, chaque appel ouvre sa connexion, valide (écritures)
et la referme — exactement ce que faisaient les écrans. Avec un curseur
fourni, la requête s'exécute dessus et c'est l'appelant qui valide.
"""

import re
from contextlib import contextmanager

import data.database as _base

_IDENTIFIANT = re.compile(r"^[a-z_][a-z0-9_]*$")


def connexion():
    return _base.connexion()


def verifier_colonnes(colonnes):
    """Refuse tout nom de colonne qui ne serait pas un identifiant simple
    (les noms viennent du code, jamais d'une saisie, mais on reste strict)."""
    for c in colonnes:
        if not _IDENTIFIANT.match(c):
            raise ValueError(f"Nom de colonne refusé : {c!r}")
    return colonnes


@contextmanager
def transaction():
    """Plusieurs requêtes validées ensemble, ou aucune en cas d'erreur."""
    conn = connexion()
    try:
        cur = conn.cursor()
        yield cur
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def lire_un(sql, parametres=(), cur=None):
    if cur is not None:
        cur.execute(sql, parametres)
        return cur.fetchone()
    conn = connexion()
    try:
        return conn.execute(sql, parametres).fetchone()
    finally:
        conn.close()


def lire_tous(sql, parametres=(), cur=None):
    if cur is not None:
        cur.execute(sql, parametres)
        return cur.fetchall()
    conn = connexion()
    try:
        return conn.execute(sql, parametres).fetchall()
    finally:
        conn.close()


def ecrire(sql, parametres=(), cur=None):
    """Exécute une écriture ; renvoie l'identifiant de la ligne créée
    (INSERT) ou None."""
    if cur is not None:
        cur.execute(sql, parametres)
        return cur.lastrowid
    conn = connexion()
    try:
        c = conn.execute(sql, parametres)
        conn.commit()
        return c.lastrowid
    finally:
        conn.close()


def inserer(table, champs, cur=None):
    """INSERT des colonnes de `champs` (dict, ordre conservé) ; renvoie l'id."""
    colonnes = verifier_colonnes(list(champs))
    sql = (f"INSERT INTO {verifier_colonnes([table])[0]} ({', '.join(colonnes)}) "
           f"VALUES ({', '.join('?' * len(colonnes))})")
    return ecrire(sql, tuple(champs.values()), cur)


def valeurs(table, id_, colonnes, cur=None, filtre_athlete=None):
    """Une ligne de `table` (colonnes choisies) par son id, ou None."""
    colonnes = verifier_colonnes(list(colonnes))
    sql = f"SELECT {', '.join(colonnes)} FROM {verifier_colonnes([table])[0]} WHERE id=?"
    parametres = [id_]
    if filtre_athlete is not None:
        sql += " AND athlete_id=?"
        parametres.append(filtre_athlete)
    return lire_un(sql, tuple(parametres), cur)
