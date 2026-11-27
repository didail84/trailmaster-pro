"""
Alerte matériel : quand une paire de chaussures approche de sa fin de vie
(600 km par défaut, réglable), le logiciel le signale et propose des
modèles équivalents à comparer, avec des liens de recherche de prix.

Les modèles équivalents viennent d'une petite table de familles de
chaussures de trail (amorti, accroche, drop) : ce sont des pistes à
essayer, pas une recommandation d'achat. Les prix ne sont pas lus
automatiquement (pas de site marchand interrogé) : les liens ouvrent une
recherche sur des comparateurs français.
"""

from urllib.parse import quote_plus

from data.database import connexion, obtenir_parametre, definir_parametre

CLE_SEUIL = "alerte_chaussures_km"
SEUIL_DEFAUT = 600

FAMILLES = {
    "amorti max, terrain varié": ["HOKA Mafate Speed", "HOKA Speedgoat", "Saucony Xodus Ultra", "Brooks Caldera",
                                  "Kiprun MT Cushion", "Altra Olympus"],
    "polyvalente trail": ["Salomon Speedcross", "Salomon Sense Ride", "Kiprun XT", "Brooks Cascadia",
                          "La Sportiva Bushido", "Saucony Peregrine"],
    "chemin et route": ["Kiprun KD900", "HOKA Challenger", "Kiprun Kipride Gravel", "Brooks Divide", "Saucony Ride TR"],
    "légère et rapide": ["Salomon S/Lab Pulsar", "HOKA Tecton X", "La Sportiva Prodigio", "Kiprun Race Light"],
}

MOTS_FAMILLE = [("mafate", "amorti max, terrain varié"), ("speedgoat", "amorti max, terrain varié"),
                ("xodus", "amorti max, terrain varié"), ("caldera", "amorti max, terrain varié"),
                ("olympus", "amorti max, terrain varié"), ("cushion", "amorti max, terrain varié"),
                ("speedcross", "polyvalente trail"), ("sense", "polyvalente trail"), ("cascadia", "polyvalente trail"),
                ("peregrine", "polyvalente trail"), ("bushido", "polyvalente trail"), ("xt", "polyvalente trail"),
                ("gravel", "chemin et route"), ("challenger", "chemin et route"), ("kd", "chemin et route"),
                ("divide", "chemin et route"), ("pulsar", "légère et rapide"), ("tecton", "légère et rapide"),
                ("prodigio", "légère et rapide")]


def seuil():
    try:
        return int(obtenir_parametre(CLE_SEUIL, str(SEUIL_DEFAUT)))
    except (TypeError, ValueError):
        return SEUIL_DEFAUT


def definir_seuil(km):
    km = int(km)
    if not 200 <= km <= 2000:
        raise ValueError("Le seuil doit être entre 200 et 2000 km.")
    definir_parametre(CLE_SEUIL, str(km))


def famille(nom):
    n = (nom or "").lower()
    mots = n.replace("-", " ").split()
    for mot, fam in MOTS_FAMILLE:
        if (mot in mots) if len(mot) <= 3 else (mot in n):
            return fam
    return "polyvalente trail"


def equivalents(nom, nb=4):
    fam = famille(nom)
    n = (nom or "").lower()
    mots = set(n.replace("-", " ").split())

    def meme_modele(m):
        return any(w in mots for w in m.lower().split()[1:] if len(w) > 2)
    return fam, [m for m in FAMILLES[fam] if not meme_modele(m)][:nb]


def liens_prix(modele):
    q = quote_plus(modele)
    return [("idealo", f"https://www.idealo.fr/prechcat.html?q={q}"),
            ("i-run", f"https://www.i-run.fr/recherche/?q={q}"),
            ("Alltricks", f"https://www.alltricks.fr/Acheter/{q}")]


def alertes(athlete_id):
    """Chaussures actives au-delà du seuil : [{id, nom, km, seuil, niveau, famille, equivalents}]."""
    s = seuil()
    conn = connexion()
    try:
        lignes = conn.execute("SELECT id, nom, km_actuels, km_max_recommande FROM materiel WHERE athlete_id=? "
                              "AND type='Chaussures' AND ifnull(statut,'Actif')='Actif'", (athlete_id,)).fetchall()
    finally:
        conn.close()
    res = []
    for i, nom, km, kmax in lignes:
        km = km or 0
        limite = min(s, kmax) if kmax else s
        if km < limite:
            continue
        fam, eq = equivalents(nom)
        res.append({"id": i, "nom": nom, "km": round(km), "seuil": limite,
                    "niveau": "changer" if km >= limite + 100 else "bientot",
                    "famille": fam, "equivalents": [{"modele": m, "liens": liens_prix(m)} for m in eq]})
    return sorted(res, key=lambda r: -r["km"])
