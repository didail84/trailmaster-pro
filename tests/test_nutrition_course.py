"""Étape 3.3 : nutrition de course — Nutri-Score, fait maison, catalogue, tolérances, comparatif."""
import json

import pytest

from noyau.nutrition import nutriscore as ns, recettes as rc, catalogue as cat, comparatif as cmp
from noyau.nutrition import tolerances as tol, open_food_facts as off
from noyau.nutrition.ingredients import MODELES, INGREDIENTS
from noyau.course import ravitaillement as rav


# ---------------------------------------------------------------- Nutri-Score
@pytest.mark.parametrize("valeurs, type_, attendu", [
    ({"energie_kcal": 42, "sucres_g": 10.6, "ags_g": 0, "sel_g": 0}, "boisson", "E"),          # soda
    ({"energie_kcal": 44, "sucres_g": 8.7, "ags_g": 0, "sel_g": 0, "fruits_legumes_pct": 100,
      "proteines_g": 0.7}, "boisson", "C"),                                                    # jus 100 %
    ({"energie_kcal": 0, "sucres_g": 0, "ags_g": 0, "sel_g": 0}, "boisson", "B"),              # boisson zéro sans édulcorant
    ({"energie_kcal": 370, "sucres_g": 1, "ags_g": 1.3, "sel_g": 0.01, "fibres_g": 10,
      "proteines_g": 13.5}, "aliment", "A"),                                                   # flocons d'avoine
    ({"energie_kcal": 280, "sucres_g": 30, "ags_g": 0, "sel_g": 0.3}, "aliment", "D"),         # gel
    ({"energie_kcal": 540, "sucres_g": 0.5, "ags_g": 3, "sel_g": 1.3, "fibres_g": 4.5,
      "proteines_g": 6.5}, "aliment", "D"),                                                    # chips
])
def test_nutriscore_produits_connus(valeurs, type_, attendu):
    assert ns.calculer(valeurs, type_)["lettre"] == attendu


def test_nutriscore_regles():
    assert ns.calculer({}, "eau")["lettre"] == "A"
    assert ns.calculer({"energie_kcal": 0, "sucres_g": 0, "ags_g": 0, "sel_g": 0}, "boisson")["lettre"] != "A"
    # édulcorants : +4 points dans une boisson
    sans = ns.calculer({"energie_kcal": 1, "sucres_g": 0, "ags_g": 0, "sel_g": 0}, "boisson")
    avec = ns.calculer({"energie_kcal": 1, "sucres_g": 0, "ags_g": 0, "sel_g": 0, "edulcorants": 1}, "boisson")
    assert avec["score"] == sans["score"] + 4
    # N ≥ 11 : protéines non comptées (sauf fromage)
    base = {"energie_kcal": 450, "sucres_g": 30, "ags_g": 5, "sel_g": 0.5, "proteines_g": 20}
    r = ns.calculer(base, "aliment")
    assert r["negatif"] >= 11 and r["positif"] == 0
    assert ns.calculer(base, "fromage")["positif"] > 0
    # bornes strictes : 3,4 g de sucres = 0 point, 3,5 g = 1 point
    assert ns._points(3.4, ns.ALIMENT["sucres_g"]) == 0 and ns._points(3.5, ns.ALIMENT["sucres_g"]) == 1
    assert ns.calculer({"energie_kcal": 100}, "aliment")["lettre"] is None
    assert ns.calculer({}, "non_applicable")["lettre"] is None
    gel = ns.calculer({"energie_kcal": 280, "sucres_g": 30, "ags_g": 0, "sel_g": 0.3}, "aliment")
    assert gel["note"] and "effort" in gel["note"]


# ---------------------------------------------------------------- Fait maison
def _modele(nom):
    m = next(x for x in MODELES if x[0] == nom)
    return [{"code": c, "g": g} for c, g in m[3]], m[2], m[1]


def test_tous_les_modeles_se_calculent():
    for nom, categorie, n, ing, _p, _c in MODELES:
        assert all(c in INGREDIENTS for c, _g in ing), nom
        r = rc.calculer([{"code": c, "g": g} for c, g in ing], n, categorie)
        assert r and r["par_portion"]["glucides_g"] > 5, nom
        assert r["nutriscore"]["lettre"] in "ABCDE", nom


def test_gel_miel_citron():
    ing, n, c = _modele("Gel miel-citron salé")
    r = rc.calculer(ing, n, c)
    assert abs(r["par_portion"]["glucides_g"] - (81 + 0.48) / 4) < 0.6      # miel + citron
    assert abs(r["sodium_mg_portion"] - 0.6 * 393.4 / 4) < 2
    assert r["ratio_glucose_fructose"].startswith("1:1")                  # le miel est un peu plus riche en fructose
    assert r["concentration_g_l"] is None


def test_boisson_haute_dose_et_concentration():
    ing, n, c = _modele("Boisson haute dose 2:1 (90 g par bidon)")
    r = rc.calculer(ing, n, c)
    assert 85 <= r["par_portion"]["glucides_g"] <= 90
    assert r["ratio_glucose_fructose"] == "1:0,5"
    assert r["concentration_g_l"] > 80
    assert any("maltodextrine" in a for a in r["avertissements"])
    # sirop de fruits dilué très concentré : avertissement « hypertonique »
    r2 = rc.calculer([{"code": "eau", "g": 500}, {"code": "sirop_fruits", "g": 80}], 1, "Boisson")
    assert any("hypertonique" in a for a in r2["avertissements"])


def test_cout_et_valeurs_corrigees():
    ing = [{"code": "maltodextrine", "g": 100, "prix_kg": 8}, {"code": "eau", "g": 400, "prix_kg": 0}]
    r = rc.calculer(ing, 2, "Boisson")
    assert r["cout_total"] == 0.8 and r["cout_portion"] == 0.4
    assert rc.calculer([{"code": "eau", "g": 100}, {"code": "miel", "g": 10}], 1, "Gel")["cout_portion"] is None
    corrige = rc.calculer([{"code": "miel", "g": 100, "valeurs": {"glucides_g": 70}}], 1, "Gel")
    assert corrige["par_portion"]["glucides_g"] == 70
    libre = rc.calculer([{"nom": "Mon sirop", "g": 50, "valeurs": {"kcal": 300, "glucides_g": 75}}], 1, "Gel")
    assert libre["par_portion"]["glucides_g"] == 37.5


def test_viser_des_glucides():
    ing, n, c = _modele("Gel miel-citron salé")
    ajout = rc.ajuster_glucides(ing, n, 30, "maltodextrine", c)
    r = rc.calculer(ing + [{"code": "maltodextrine", "g": ajout}], n, c)
    assert abs(r["par_portion"]["glucides_g"] - 30) < 1.5
    assert rc.ajuster_glucides(ing, n, 5, "maltodextrine", c) == 0
    assert rc.calculer([], 1) is None


# ---------------------------------------------------------------- Catalogue et comparatif
def test_generiques_et_calculs_par_portion():
    gel = cat.generique("g:gel")
    assert round(cat.par_portion(gel, "glucides_g")) == 25
    gel["prix_portion"] = 2.0
    assert round(cat.prix_pour_60g(gel), 2) == round(2.0 / (0.71 * 35) * 60, 2)
    pastille = cat.generique("g:pastille")
    assert round(cat.sodium_mg_portion(pastille)) == 250
    assert cat.nutriscore_de(pastille)["lettre"] is None
    assert cat.nutriscore_de({**gel, "nutriscore_officiel": "c"})["officiel"] == "C"


def test_comparatif():
    a, b, c = (cat.generique(x) for x in ("g:gel", "g:gel_2_1", "g:compote"))
    a["prix_portion"], b["prix_portion"] = 2.0, 3.0
    r = cmp.comparer([a, b, c])
    assert r["colonnes"] == [a["nom"], b["nom"], c["nom"]]
    assert all(len(v) == 3 for _c, v in r["lignes"])
    assert r["nutriscores"] == ["D", "C", "A"]
    texte = " ".join(r["phrases"])
    assert "Gel haute dose" in texte and "le plus de glucides" in texte
    assert "moins cher" in texte
    assert "Compote" in texte and "Nutri-Score A" in texte
    caf = cmp.comparer([cat.generique("g:gel_cafeine"), a])
    assert any("caféine" in p for p in caf["phrases"])


# ---------------------------------------------------------------- Open Food Facts (sans réseau)
def test_lecture_fiche_open_food_facts():
    fiche = {"status": 1, "product": {
        "code": "3000000000017", "product_name_fr": "Gel coup de fouet", "brands": "Marque, Autre",
        "nutriscore_grade": "d", "serving_quantity": 32, "serving_size": "32 g",
        "categories_tags": ["en:energy-gels"],
        "nutriments": {"energy-kj_100g": 1170, "carbohydrates_100g": 68, "sugars_100g": 31, "fat_100g": 0,
                       "saturated-fat_100g": 0, "proteins_100g": 0, "sodium_100g": 0.2, "caffeine_100g": 0.25}}}
    p = off.produit_depuis_json(fiche)
    assert p["nom"] == "Gel coup de fouet" and p["marque"] == "Marque"
    assert p["categorie"] == "Gel" and p["nutriscore_officiel"] == "D"
    assert round(p["energie_kcal"]) == 280 and p["sel_g"] == 0.5
    assert p["cafeine_mg"] == 80 and p["portion"] == 32
    assert off.produit_depuis_json({"product": {"product_name": ""}}) is None
    assert off.code_valide("3017620422003") and not off.code_valide("12ab")
    with pytest.raises(off.ErreurOpenFoodFacts):
        off.chercher_code("123")


# ---------------------------------------------------------------- Tolérances
def _e(pid, ressenti, contexte="Entraînement", duree=60, gh=None):
    return {"produit_id": pid, "ressenti": ressenti, "contexte": contexte, "duree_min": duree, "glucides_g_h": gh}


def test_verdicts():
    assert tol.verdict([])["code"] == "jamais"
    assert tol.verdict([_e(1, "bien")])["code"] == "a_confirmer"
    assert tol.verdict([_e(1, "bien", "Sortie longue", 150), _e(1, "bien")])["code"] == "valide"
    assert tol.verdict([_e(1, "gene"), _e(1, "bien")])["code"] == "prudence"
    assert tol.verdict([_e(1, "arret"), _e(1, "bien"), _e(1, "bien", "Course")])["code"] == "eviter"
    assert tol.verdict([_e(1, "gene")])["code"] == "eviter"
    b = tol.bilan([{"id": 1}, {"id": 2}], [_e(1, "bien", gh=70), _e(1, "bien", gh=60), _e(2, "gene", gh=90)])
    assert b["max_g_h_tolere"] == 70 and b["min_g_h_gene"] == 90
    assert "10 g/h par semaine" in tol.entrainement_du_ventre(60, 80)
    assert "à ta portée" in tol.entrainement_du_ventre(90, 80)


def test_menu_et_composition_avec_mes_produits():
    gel = {**cat.generique("g:gel"), "id": 1, "favori": 1}
    barre = {**cat.generique("g:barre"), "id": 2, "favori": 1}
    a_eviter = {**cat.generique("g:pate_fruits"), "id": 3, "favori": 1}
    boisson = {**cat.generique("g:boisson"), "id": 4, "favori": 1}
    verdicts = {3: {"code": "eviter"}}
    plan = rav.plan_ravitaillement(3, 20)
    menu = tol.menu_avec_mes_produits(plan, [gel, barre, a_eviter, boisson], verdicts)
    assert len(menu) == 3
    noms = {p["nom"] for l in menu for p, _n in l["items"]}
    assert a_eviter["nom"] not in noms and boisson["nom"] in noms
    for l in menu:
        assert abs(l["glucides_g"] - l["cible_g"]) <= 15
    assert "×" in tol.texte_ligne_menu(menu[0])
    assert tol.menu_avec_mes_produits(plan, [], {}) == []
    compo = tol.composer(100, [gel, barre])
    total = sum(cat.par_portion(p, "glucides_g") * n for p, n in compo)
    assert 85 <= total <= 125
    assert tol.produits_pour_la_course([gel, a_eviter, boisson], verdicts) == [gel]


# ---------------------------------------------------------------- Base de données
def test_produits_essais_recettes_en_base(base_vide):
    from noyau.donnees import nutrition_course as dnut
    pid = dnut.ajouter_generique(1, "g:gel")
    assert dnut.ajouter_generique(1, "g:gel") == pid                    # pas de doublon
    dnut.modifier_produit(pid, {"prix_portion": 2.5})
    assert dnut.produit(pid)["prix_portion"] == 2.5
    with pytest.raises(dnut.ErreurNutrition):
        dnut.creer_produit(1, {"nom": "Faux", "glucides_g": 20, "sucres_g": 30})
    with pytest.raises(dnut.ErreurNutrition):
        dnut.creer_produit(1, {"nom": " "})
    dnut.ajouter_essai(1, {"produit_id": pid, "ressenti": "bien", "glucides_g_h": 60, "symptomes": []})
    dnut.ajouter_essai(1, {"produit_id": pid, "ressenti": "bien", "contexte": "Sortie longue", "duree_min": 160})
    with pytest.raises(dnut.ErreurNutrition):
        dnut.ajouter_essai(1, {"produit_id": pid, "ressenti": "super"})
    assert len(dnut.essais(1)) == 2
    assert [p["nom"] for p in tol.produits_course_de(1)] == ["Gel énergétique classique"]

    ing, n, c = _modele("Barres avoine-dattes")
    rid, prod = dnut.enregistrer_recette(1, None, "Mes barres", c, n, ing, "mixer", "frigo")
    p = dnut.produit(prod)
    assert p["marque"] == "Fait maison" and p["recette_id"] == rid and p["categorie"] == "Barre"
    assert round(cat.par_portion(p, "glucides_g")) == round(rc.calculer(ing, n, c)["par_portion"]["glucides_g"])
    dnut.modifier_produit(prod, {"prix_portion": 0.6, "favori": 1})
    dnut.enregistrer_recette(1, rid, "Mes barres v2", c, 10, ing)       # mise à jour : même produit, prix gardé
    p2 = dnut.produit(prod)
    assert p2["nom"] == "Mes barres v2" and p2["prix_portion"] == 0.6 and p2["portion"] < p["portion"]
    assert len([x for x in dnut.produits(1) if x["recette_id"] == rid]) == 1
    assert dnut.recette(rid)["ingredients"] == [i for i in ing if i["g"] > 0]
    dnut.supprimer_recette(rid, avec_produit=True)
    assert dnut.produit(prod) is None and dnut.recettes(1) == []
    dnut.supprimer_produit(pid)
    assert dnut.essais(1) == [] and dnut.produits(1) == []


def test_sacs_d_assistance_avec_mes_produits():
    from noyau.course import strategie as strat
    gel = {**cat.generique("g:gel"), "id": 1, "favori": 1}
    from datetime import datetime, timedelta
    t0 = datetime(2026, 6, 1, 6, 0)
    def pas(nom, km, typ, s):
        return {"nom": nom, "km": km, "type": typ, "troncon_s": s, "passage": t0 + timedelta(seconds=s)}
    passages = [pas("Départ", 0, "Départ", 0), pas("Col", 10, "Assistance", 7200), pas("Arrivée", 20, "Arrivée", 7200)]
    scen = {"realiste": {"passages": passages}}
    nutri = [{"nom": "Arrivée", "km": 20, "glucides_g": 120, "eau_ml": 1000}]
    sacs = strat.sacs_assistance(scen, nutri, 15, [gel])
    assert sacs and sacs[0]["produits"] and "Gel énergétique classique" in sacs[0]["lignes"][0]
    assert "tes produits" in strat.sacs_assistance(scen, nutri, 15)[0]["lignes"][0]


def test_ecrans_nutrition(base_vide):
    import shiboken6
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    from noyau.donnees import nutrition_course as dnut
    pid = dnut.ajouter_generique(1, "g:gel")
    dnut.definir_favori(pid)
    from interface.alimentation import AlimentationFenetre
    f = AlimentationFenetre(1)
    on = f.onglets
    assert on.produits.table.rowCount() >= len(cat.GENERIQUES)
    fm = on.fait_maison
    assert fm.table.rowCount() > 0 and fm._resultat
    fm.nom.setText("Test gel")
    fm._recette_id, _ = dnut.enregistrer_recette(1, None, "Test gel", fm.categorie.currentText(),
                                                 fm.portions.value(), fm._ingredients())
    fm.actualiser()
    assert fm.liste.count() == 2
    on.comparatif.preselectionner([pid, "g:compote"])
    assert on.comparatif.table.rowCount() > 5
    on.tolerances.actualiser()
    assert on.tolerances.table_menu.rowCount() >= 1
    app.processEvents()
    shiboken6.delete(f)
