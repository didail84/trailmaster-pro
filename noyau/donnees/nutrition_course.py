"""
Accès aux données de la nutrition de course (étape 3.3) : tes produits,
tes essais de tolérance et tes recettes fait maison. Seul ce module écrit
dans produits_nutrition, tolerances_nutrition et recettes_nutrition.
"""

import json
from datetime import datetime

from noyau.donnees import base
from noyau.nutrition.catalogue import CHAMPS_PRODUIT, generique

COLONNES_PRODUIT = ("id", "uuid") + CHAMPS_PRODUIT + ("date_ajout",)
CHAMPS_TOLERANCE = ("produit_id", "date", "contexte", "activite_id", "quantite", "duree_min", "glucides_g_h",
                    "temperature_c", "ressenti", "symptomes", "notes")


class ErreurNutrition(Exception):
    """Message lisible ; rien n'a été modifié."""


def _maintenant():
    return datetime.now().isoformat(timespec="seconds")


# ------------------------------------------------------------------
# Produits
# ------------------------------------------------------------------

def _produit(ligne):
    return dict(zip(COLONNES_PRODUIT, ligne)) if ligne else None


def produits(athlete_id):
    """Tes produits, favoris d'abord, puis par catégorie et nom."""
    if athlete_id is None:
        return []
    lignes = base.lire_tous(
        f"SELECT {', '.join(COLONNES_PRODUIT)} FROM produits_nutrition WHERE athlete_id=? "
        "ORDER BY favori DESC, categorie, nom COLLATE NOCASE", (athlete_id,))
    return [_produit(l) for l in lignes]


def produit(produit_id):
    return _produit(base.lire_un(f"SELECT {', '.join(COLONNES_PRODUIT)} FROM produits_nutrition WHERE id=?",
                                 (produit_id,)))


def _verifier(champs):
    if not (champs.get("nom") or "").strip():
        raise ErreurNutrition("Donne un nom au produit.")
    for cle in ("portion", "energie_kcal", "glucides_g", "sucres_g", "fibres_g", "proteines_g", "lipides_g",
                "ags_g", "sel_g", "prix_portion", "cafeine_mg"):
        v = champs.get(cle)
        if v is not None and v < 0:
            raise ErreurNutrition("Les valeurs nutritionnelles et le prix ne peuvent pas être négatifs.")
    for a, b, lib in (("sucres_g", "glucides_g", "sucres"), ("ags_g", "lipides_g", "acides gras saturés")):
        if champs.get(a) is not None and champs.get(b) is not None and champs[a] > champs[b] + 0.05:
            raise ErreurNutrition(f"Les {lib} ne peuvent pas dépasser les "
                                  f"{'glucides' if b == 'glucides_g' else 'lipides'}.")
    if (champs.get("glucides_g") or 0) + (champs.get("proteines_g") or 0) + (champs.get("lipides_g") or 0) > 100.5:
        raise ErreurNutrition("Glucides + protéines + lipides dépassent 100 g pour 100 g : vérifie l'étiquette.")


def creer_produit(athlete_id, champs, cur=None):
    champs = {k: champs.get(k) for k in CHAMPS_PRODUIT if k in champs}
    champs["nom"] = (champs.get("nom") or "").strip()
    _verifier(champs)
    champs = {"athlete_id": athlete_id, **champs, "date_ajout": _maintenant()}
    return base.inserer("produits_nutrition", champs, cur)


def modifier_produit(produit_id, champs, cur=None):
    champs = {k: champs[k] for k in CHAMPS_PRODUIT if k in champs}
    if "nom" in champs:
        champs["nom"] = (champs["nom"] or "").strip()
    actuel = produit(produit_id) if cur is None else None
    _verifier({**(actuel or {}), **champs})
    if not champs:
        return
    base.verifier_colonnes(list(champs))
    base.ecrire(f"UPDATE produits_nutrition SET {', '.join(c + '=?' for c in champs)} WHERE id=?",
                tuple(champs.values()) + (produit_id,), cur)


def supprimer_produit(produit_id):
    """Supprime le produit et ses essais ; une recette liée garde sa recette."""
    with base.transaction() as cur:
        base.ecrire("UPDATE recettes_nutrition SET produit_id=NULL WHERE produit_id=?", (produit_id,), cur)
        base.ecrire("DELETE FROM tolerances_nutrition WHERE produit_id=?", (produit_id,), cur)
        base.ecrire("DELETE FROM produits_nutrition WHERE id=?", (produit_id,), cur)


def definir_favori(produit_id, favori=True):
    base.ecrire("UPDATE produits_nutrition SET favori=? WHERE id=?", (1 if favori else 0, produit_id))


def ajouter_generique(athlete_id, id_generique):
    """Copie un produit générique dans tes produits (pour noter un essai, un prix…) ; renvoie son id.
    Si tu l'as déjà copié, renvoie l'existant."""
    g = generique(id_generique)
    if g is None:
        raise ErreurNutrition("Produit générique inconnu.")
    deja = base.lire_un("SELECT id FROM produits_nutrition WHERE athlete_id=? AND nom=? AND source='Générique'",
                        (athlete_id, g["nom"]))
    if deja:
        return deja[0]
    return creer_produit(athlete_id, g)


def par_code_barre(athlete_id, code):
    l = base.lire_un("SELECT id FROM produits_nutrition WHERE athlete_id=? AND code_barre=?", (athlete_id, code))
    return l[0] if l else None


# ------------------------------------------------------------------
# Essais de tolérance
# ------------------------------------------------------------------

RESSENTIS = (
    ("bien", "Bien toléré"),
    ("leger", "Petite gêne"),
    ("gene", "Gêne digestive"),
    ("arret", "M'a fait ralentir ou arrêter"),
)
LIBELLE_RESSENTI = dict(RESSENTIS)
SYMPTOMES = ("Nausée", "Ballonnements", "Crampes d'estomac", "Besoin pressant", "Brûlures, reflux",
             "Écœurement du goût", "Trop sucré", "Difficile à avaler", "Coup de barre après")
CONTEXTES = ("Entraînement", "Sortie longue", "Course")


def ajouter_essai(athlete_id, champs):
    champs = {k: champs.get(k) for k in CHAMPS_TOLERANCE if k in champs}
    if not champs.get("produit_id"):
        raise ErreurNutrition("Choisis le produit essayé.")
    if champs.get("ressenti") not in LIBELLE_RESSENTI:
        raise ErreurNutrition("Indique comment tu l'as toléré.")
    if not champs.get("date"):
        champs["date"] = datetime.now().date().isoformat()
    if champs.get("glucides_g_h") is not None and not 0 <= champs["glucides_g_h"] <= 150:
        raise ErreurNutrition("Les glucides par heure doivent être entre 0 et 150 g.")
    if isinstance(champs.get("symptomes"), (list, tuple)):
        champs["symptomes"] = ", ".join(champs["symptomes"])
    return base.inserer("tolerances_nutrition", {"athlete_id": athlete_id, **champs})


def supprimer_essai(essai_id):
    base.ecrire("DELETE FROM tolerances_nutrition WHERE id=?", (essai_id,))


def essais(athlete_id, produit_id=None):
    """[{id, produit_id, produit, date, contexte, …}] du plus récent au plus ancien."""
    if athlete_id is None:
        return []
    sql = ("SELECT t.id, t.produit_id, p.nom, t.date, t.contexte, t.activite_id, t.quantite, t.duree_min, "
           "t.glucides_g_h, t.temperature_c, t.ressenti, t.symptomes, t.notes "
           "FROM tolerances_nutrition t JOIN produits_nutrition p ON p.id = t.produit_id WHERE t.athlete_id=?")
    params = [athlete_id]
    if produit_id is not None:
        sql += " AND t.produit_id=?"
        params.append(produit_id)
    sql += " ORDER BY t.date DESC, t.id DESC"
    cles = ("id", "produit_id", "produit", "date", "contexte", "activite_id", "quantite", "duree_min",
            "glucides_g_h", "temperature_c", "ressenti", "symptomes", "notes")
    return [dict(zip(cles, l)) for l in base.lire_tous(sql, tuple(params))]


# ------------------------------------------------------------------
# Recettes fait maison
# ------------------------------------------------------------------

COLONNES_RECETTE = ("id", "uuid", "nom", "categorie", "nb_portions", "ingredients_json", "preparation",
                    "conservation", "notes", "produit_id", "date_modification")


def _recette(l):
    if not l:
        return None
    r = dict(zip(COLONNES_RECETTE, l))
    try:
        r["ingredients"] = json.loads(r.pop("ingredients_json") or "[]")
    except ValueError:
        r["ingredients"] = []
    return r


def recettes(athlete_id):
    if athlete_id is None:
        return []
    return [_recette(l) for l in base.lire_tous(
        f"SELECT {', '.join(COLONNES_RECETTE)} FROM recettes_nutrition WHERE athlete_id=? ORDER BY nom COLLATE NOCASE",
        (athlete_id,))]


def recette(recette_id):
    return _recette(base.lire_un(f"SELECT {', '.join(COLONNES_RECETTE)} FROM recettes_nutrition WHERE id=?",
                                 (recette_id,)))


def enregistrer_recette(athlete_id, recette_id, nom, categorie, nb_portions, ingredients,
                        preparation="", conservation="", notes=""):
    """Crée ou met à jour la recette ET son produit dans « Mes produits » (marque « Fait maison »),
    pour la comparer et noter tes essais comme n'importe quel produit. Renvoie (recette_id, produit_id)."""
    from noyau.nutrition import recettes as calc
    nom = (nom or "").strip()
    if not nom:
        raise ErreurNutrition("Donne un nom à la recette.")
    lignes = [i for i in ingredients if (i.get("g") or 0) > 0]
    if not lignes:
        raise ErreurNutrition("Ajoute au moins un ingrédient avec une quantité.")
    if not nb_portions or nb_portions < 1:
        raise ErreurNutrition("Le nombre de portions doit être d'au moins 1.")
    resultat = calc.calculer(lignes, nb_portions, categorie)
    champs_produit = calc.produit_depuis_recette(nom, categorie, resultat)
    texte = json.dumps(lignes, ensure_ascii=False)
    with base.transaction() as cur:
        if recette_id is None:
            recette_id = base.inserer("recettes_nutrition", {
                "athlete_id": athlete_id, "nom": nom, "categorie": categorie, "nb_portions": nb_portions,
                "ingredients_json": texte, "preparation": preparation, "conservation": conservation,
                "notes": notes, "date_modification": _maintenant()}, cur)
            produit_id = None
        else:
            base.ecrire("UPDATE recettes_nutrition SET nom=?, categorie=?, nb_portions=?, ingredients_json=?, "
                        "preparation=?, conservation=?, notes=?, date_modification=? WHERE id=?",
                        (nom, categorie, nb_portions, texte, preparation, conservation, notes, _maintenant(),
                         recette_id), cur)
            l = base.lire_un("SELECT produit_id FROM recettes_nutrition WHERE id=?", (recette_id,), cur)
            produit_id = l[0] if l else None
            if produit_id is not None and not base.lire_un("SELECT 1 FROM produits_nutrition WHERE id=?",
                                                           (produit_id,), cur):
                produit_id = None
        champs_produit["recette_id"] = recette_id
        if produit_id is None:
            produit_id = creer_produit(athlete_id, champs_produit, cur)
            base.ecrire("UPDATE recettes_nutrition SET produit_id=? WHERE id=?", (produit_id, recette_id), cur)
        else:
            # le prix ou le favori saisis à la main sur le produit sont gardés si la recette n'en donne pas
            if champs_produit.get("prix_portion") is None:
                champs_produit.pop("prix_portion")
            modifier_produit(produit_id, champs_produit, cur)
    return recette_id, produit_id


def supprimer_recette(recette_id, avec_produit=False):
    r = recette(recette_id)
    if not r:
        return
    with base.transaction() as cur:
        if avec_produit and r.get("produit_id"):
            base.ecrire("DELETE FROM tolerances_nutrition WHERE produit_id=?", (r["produit_id"],), cur)
            base.ecrire("DELETE FROM produits_nutrition WHERE id=?", (r["produit_id"],), cur)
        elif r.get("produit_id"):
            base.ecrire("UPDATE produits_nutrition SET recette_id=NULL WHERE id=?", (r["produit_id"],), cur)
        base.ecrire("DELETE FROM recettes_nutrition WHERE id=?", (recette_id,), cur)
