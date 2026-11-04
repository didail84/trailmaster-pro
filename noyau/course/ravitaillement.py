"""
Plan de ravitaillement chiffré (v103) : glucides, eau et sodium par heure
selon la durée, l'intensité, la température et le poids. Repères de
nutrition sportive généralement admis (glucides 30–60 g/h de 1 h à 2 h 30,
60–90 g/h au-delà ; eau selon la chaleur ; sodium 300–800 mg/h). Ce sont des
POINTS DE DÉPART à tester à l'entraînement, jamais le jour de la course
pour la première fois. Ce n'est pas un avis médical.
"""

GEL_G = 25            # glucides d'un gel standard
BARRE_G = 30          # d'une barre
BOISSON_G_PAR_500 = 30  # d'une boisson d'effort à ~6 %


def glucides_g_par_heure(duree_h, intensite="modere"):
    if duree_h < 1.0:
        return 0
    if duree_h < 2.5:
        base = 45
    elif duree_h < 5:
        base = 65
    else:
        base = 75
    base += {"facile": -10, "modere": 0, "soutenu": 10}.get(intensite, 0)
    return max(30, min(base, 90))


def eau_ml_par_heure(temperature_c, poids_kg=70):
    if temperature_c is None:
        temperature_c = 15
    ml = 400 if temperature_c < 10 else 500 if temperature_c < 18 else 600 if temperature_c < 25 else 750
    ml += max(0, (poids_kg - 70)) * 4          # + un peu pour les gabarits plus lourds
    return int(round(ml / 50.0) * 50)


def sodium_mg_par_heure(temperature_c, grand_transpirateur=False):
    t = 15 if temperature_c is None else temperature_c
    mg = 300 if t < 12 else 450 if t < 22 else 600 if t < 28 else 750
    if grand_transpirateur:
        mg += 150
    return mg


def plan_ravitaillement(duree_h, temperature_c=None, poids_kg=70, intensite="modere",
                        grand_transpirateur=False):
    """Plan heure par heure + totaux + repères pratiques (nombre de gels...)."""
    if not duree_h or duree_h <= 0:
        return None
    g_h = glucides_g_par_heure(duree_h, intensite)
    eau = eau_ml_par_heure(temperature_c, poids_kg)
    na = sodium_mg_par_heure(temperature_c, grand_transpirateur)
    heures = []
    restant = duree_h
    h = 1
    while restant > 1e-9:
        part = min(1.0, restant)
        heures.append({
            "heure": h, "duree_h": round(part, 2),
            "glucides_g": int(round(g_h * part)), "eau_ml": int(round(eau * part / 50.0) * 50),
            "sodium_mg": int(round(na * part / 50.0) * 50),
        })
        restant -= part
        h += 1
    tot_g = sum(x["glucides_g"] for x in heures)
    # Les glucides viennent d'abord de la boisson d'effort, le reste de gels / barres.
    boisson_g = int(sum(x["eau_ml"] for x in heures) / 500 * BOISSON_G_PAR_500 * 0.5)
    solide_g = max(0, tot_g - boisson_g)
    nb_gels = int(round(solide_g * 0.7 / GEL_G))
    nb_barres = int(round(solide_g * 0.3 / BARRE_G))
    notes = []
    if g_h == 0:
        notes.append("Sortie de moins d'une heure : eau seulement si besoin, pas de glucides indispensables.")
    else:
        notes.append("Commence à manger dès 20–30 min, puis toutes les 20–30 min : petites quantités régulières.")
    if g_h >= 75:
        notes.append("Au-delà de 60 g/h, entraîne ton ventre en sortie longue avant la course.")
    if (temperature_c or 15) >= 25:
        notes.append("Chaleur : bois avant d'avoir soif, ajoute des sels, mouille la nuque.")
    notes.append("Teste tout à l'entraînement, jamais un produit nouveau le jour de la course.")
    return {"glucides_g_h": g_h, "eau_ml_h": eau, "sodium_mg_h": na, "heures": heures,
            "totaux": {"glucides_g": tot_g, "eau_l": round(sum(x["eau_ml"] for x in heures) / 1000, 1),
                       "sodium_mg": sum(x["sodium_mg"] for x in heures)},
            "repere_pratique": {"gels": nb_gels, "barres": nb_barres,
                                "boisson_effort_ml": int(sum(x["eau_ml"] for x in heures) * 0.5)},
            "notes": notes}


# ----------------------------------------------------------------------
# v105 — Exemples concrets (aliments génériques, valeurs indicatives)
# ----------------------------------------------------------------------
# Glucides par portion d'un produit courant : à vérifier sur l'étiquette du produit
# réellement choisi (les marques varient beaucoup).
CATALOGUE = [
    ("gel", "1 gel énergétique", 25),
    ("compote", "1 gourde de compote de fruits (~90 g)", 16),
    ("barre", "1 barre de céréales ou de fruits", 25),
    ("banane", "1 banane", 23),
    ("pate", "3 pâtes de fruits", 20),
    ("datte", "2 dattes", 32),
    ("raisin", "1 poignée de raisins secs (30 g)", 22),
    ("gateau", "1 petit gâteau de riz ou pain d'épices", 28),
    ("sandwich", "½ sandwich pain-confiture ou miel", 30),
]
ORDRE_COURT = ["gel", "compote", "barre", "pate", "banane"]            # sorties < 2 h 30
ORDRE_LONG = ["compote", "barre", "gel", "banane", "gateau", "pate", "sandwich", "datte", "raisin"]
GOUT_BOISSON_G_PAR_500 = BOISSON_G_PAR_500
SODIUM_BOISSON_MG_PAR_500 = 200       # boisson d'effort salée standard (~400 mg/L)
PASTILLE_SEL_MG = 250                 # 1 pastille d'électrolytes
SALE = "quelques chips, du fromage ou une tasse de bouillon salé"


def menu_exemple(plan):
    """Propose, heure par heure, une combinaison d'aliments qui atteint les glucides visés.
    plan : résultat de plan_ravitaillement. Retourne [{heure, items:[texte], glucides_g,
    boisson_ml, eau_ml, sodium_mg, pastilles}]."""
    if not plan:
        return []
    par_cle = {c[0]: c for c in CATALOGUE}
    ordre = ORDRE_LONG if sum(h["duree_h"] for h in plan["heures"]) >= 2.5 else ORDRE_COURT
    i = 0
    menu = []
    for h in plan["heures"]:
        cible = h["glucides_g"]
        boisson_ml = int(round(h["eau_ml"] * 0.5 / 50.0) * 50) if cible else 0
        g_boisson = boisson_ml / 500.0 * GOUT_BOISSON_G_PAR_500
        reste = max(0.0, cible - g_boisson)
        items, total_solide, essais = [], 0, 0
        while reste >= 10 and essais < 12 and len(items) < 3:
            cle, texte, g = par_cle[ordre[i % len(ordre)]]
            i += 1
            essais += 1
            if g <= reste * 1.35 or not items:
                items.append(texte)
                total_solide += g
                reste -= g
        eau_ml = max(0, h["eau_ml"] - boisson_ml)
        na_boisson = boisson_ml / 500.0 * SODIUM_BOISSON_MG_PAR_500
        pastilles = max(0, int(round((h["sodium_mg"] - na_boisson) / PASTILLE_SEL_MG)))
        if h["duree_h"] < 0.5:
            pastilles = 0
        menu.append({"heure": h["heure"], "items": items,
                     "glucides_g": int(round(g_boisson + total_solide)),
                     "boisson_ml": boisson_ml, "eau_ml": eau_ml,
                     "sodium_mg": h["sodium_mg"], "pastilles": pastilles})
    return menu


def texte_menu(ligne):
    """Une ligne lisible pour une heure du menu."""
    parts = []
    if ligne["boisson_ml"]:
        parts.append(f"{ligne['boisson_ml']} ml de boisson d'effort")
    parts += ligne["items"]
    if ligne["eau_ml"]:
        parts.append(f"{ligne['eau_ml']} ml d'eau")
    if ligne["pastilles"]:
        parts.append(f"{ligne['pastilles']} pastille{'s' if ligne['pastilles'] > 1 else ''} d'électrolytes")
    return " + ".join(parts) if parts else "eau à volonté"
