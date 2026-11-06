"""Étape 3.4 : matériel obligatoire d'une course comparé à ton équipement."""
import sqlite3

import pytest

from noyau.materiel import equipements as eq, comparaison as cmp

REGLEMENT = """MATÉRIEL OBLIGATOIRE :
- Téléphone portable chargé avec les numéros de l'organisation
- Gobelet personnel de 15 cl minimum
- Réserve d'eau de 1,5 litre minimum
- Deux lampes frontales en état de marche avec piles de rechange (200 lumens conseillés)
- Couverture de survie 1,40 m x 2 m ; sifflet
- Réserve alimentaire de 800 kcal
- Veste imperméable avec capuche, 10 000 mm Schmerber minimum, coutures étanches
- Trousse de premiers secours avec bande élastique adhésive 100 x 6 cm
Selon la météo :
- Lunettes de soleil
- 2 litres d'eau par temps chaud
Matériel conseillé :
- Bâtons
- Batterie externe"""


def _par_code(lignes):
    return {(l["equipement"], l["niveau"]): l for l in lignes}


def test_reconnaissance_des_equipements():
    assert eq.reconnaitre("Couverture de survie") == "couverture_survie"
    assert eq.reconnaitre("Veste imperméable Gore-Tex") == "veste_impermeable"
    assert eq.reconnaitre("Lampes frontales") == "frontale"
    assert eq.reconnaitre("Bâtons de marche") == "batons"
    assert eq.reconnaitre("Sachet de bonbons") is None            # « sac » ne doit pas être trouvé dans « sachet »
    assert eq.reconnaitre("Bateau") is None                         # ni « eau » dans « bateau »
    assert eq.codes_dans("Lampe frontale + piles de rechange") == ["frontale", "piles"]
    assert eq.codes_dans("2 frontales") == ["frontale", "frontale_secours"]


def test_valeurs_chiffrees():
    assert eq.valeur_chiffree("Réserve d'eau de 1,5 L", "volume_l") == 1.5
    assert eq.valeur_chiffree("150 cl d'eau", "volume_l") == 1.5
    assert eq.valeur_chiffree("500 ml", "volume_l") == 0.5
    assert eq.valeur_chiffree("gobelet 15 cl", "volume_cl") == 15
    assert eq.valeur_chiffree("membrane 10 000 mm", "colonne_eau_mm") == 10000
    assert eq.valeur_chiffree("20000 Schmerber", "colonne_eau_mm") == 20000
    assert eq.valeur_chiffree("800 kcal", "kcal") == 800
    assert eq.valeur_chiffree("200 lumens", "lumens") == 200
    assert eq.valeur_chiffree("sans chiffre", "kcal") is None
    assert eq.libelle_valeur("veste_impermeable", 10000) == "10 000 mm"


def test_lecture_d_un_reglement():
    lignes = eq.analyser_reglement(REGLEMENT)
    d = _par_code(lignes)
    assert d[("reserve_eau", "obligatoire")]["valeur_min"] == 1.5
    assert d[("gobelet", "obligatoire")]["valeur_min"] == 15
    assert d[("frontale", "obligatoire")]["valeur_min"] == 200
    assert ("frontale_secours", "obligatoire") in d and ("piles", "obligatoire") in d
    assert d[("frontale_secours", "obligatoire")]["libelle"] == "Seconde lampe"
    assert ("sifflet", "obligatoire") in d and ("couverture_survie", "obligatoire") in d
    assert d[("veste_impermeable", "obligatoire")]["valeur_min"] == 10000
    assert d[("reserve_alimentaire", "obligatoire")]["valeur_min"] == 800
    assert ("trousse_secours", "obligatoire") in d and ("bande_elastique", "obligatoire") in d
    assert ("lunettes", "meteo") in d
    assert d[("reserve_eau", "meteo")]["valeur_min"] == 2 and d[("reserve_eau", "meteo")]["quantite"] == 1
    assert ("batons", "conseille") in d and ("batterie_externe", "conseille") in d
    assert all(not l["libelle"][0].isalpha() or l["libelle"][0].isupper() for l in lignes)
    # ligne inconnue gardée telle quelle, à cocher soi-même
    inconnu = eq.analyser_reglement("Matériel obligatoire :\n- Gilet de flottaison homologué")
    assert len(inconnu) == 1 and inconnu[0]["equipement"] is None
    assert eq.analyser_reglement("") == []


def test_repere_standard_reconnu():
    l = eq.repere_standard(85, 4000, nocturne=True, altitude=True, saison="Hiver")
    codes = {x["equipement"] for x in l if x["niveau"] == "obligatoire"}
    assert {"telephone", "frontale", "piles", "couverture_survie", "veste_impermeable", "gants", "bonnet",
            "pantalon_long", "reserve_eau"} <= codes
    eau = [x for x in l if x["equipement"] == "reserve_eau" and x["niveau"] == "obligatoire"]
    assert len(eau) == 1 and eau[0]["valeur_min"] == 1.0
    court = {x["equipement"] for x in eq.repere_standard(10) if x["niveau"] == "obligatoire"}
    assert court == {"telephone"}


def _objet(code, nom=None, **k):
    return {"id": k.pop("id", hash(nom or code) % 10000), "equipement": code, "nom": nom or eq.EQUIPEMENTS[code]["nom"],
            "statut": k.pop("statut", "Actif"), "quantite": k.pop("quantite", 1), "poids_g": k.pop("poids_g", None),
            "caracteristiques": k.pop("car", {}), "controle_le": k.pop("controle_le", None)}


def test_comparaison_ligne_par_ligne():
    liste = eq.analyser_reglement(REGLEMENT)
    inventaire = [
        _objet("telephone", poids_g=190), _objet("gobelet", car={"volume_cl": 15}, poids_g=15),
        _objet("reserve_eau", "Flasque 500 ml", quantite=2, car={"volume_l": 0.5}, poids_g=30),
        _objet("frontale", "Frontale 450", car={"lumens": 450}, poids_g=85, controle_le="2026-10-01"),
        _objet("frontale", "Petite frontale", car={"lumens": 100}, poids_g=40, id=77),
        _objet("couverture_survie", poids_g=55),
        _objet("veste_impermeable", "Veste 5000", car={"colonne_eau_mm": 5000, "coutures_etanches": True,
                                                      "capuche": True}, poids_g=200),
        _objet("sifflet", statut="Retiré"),
    ]
    r = cmp.comparer(liste, inventaire, "2026-11-20")
    d = {(l["equipement"], l["niveau"]): l for l in r["lignes"]}
    assert d[("telephone", "obligatoire")]["statut"] == "ok"
    assert d[("gobelet", "obligatoire")]["statut"] == "ok"
    eau = d[("reserve_eau", "obligatoire")]
    assert eau["statut"] == "manque" and "1 L seulement" in eau["detail"]
    assert d[("frontale", "obligatoire")]["statut"] == "ok"                    # la meilleure fait 450 lm
    assert d[("frontale_secours", "obligatoire")]["statut"] == "ok"            # la deuxième frontale sert de secours
    veste = d[("veste_impermeable", "obligatoire")]
    assert veste["statut"] == "manque" and "5 000 mm" in veste["detail"]
    assert d[("sifflet", "obligatoire")]["statut"] == "manque"                 # retiré = plus dans le sac
    assert d[("piles", "obligatoire")]["statut"] == "manque"
    assert r["pret_pct"] < 100 and r["manquants"]
    assert r["poids_g"] >= 190 + 15 + 60 + 85 + 40 + 55
    texte = cmp.texte_liste_de_courses(r, "Ultra test")
    assert "Ultra test" in texte and "Réserve d'eau" in texte and "1,5 L minimum" in texte


def test_verifications():
    liste = [{"libelle": "Veste imperméable à capuche, coutures étanches", "equipement": "veste_impermeable",
              "niveau": "obligatoire", "quantite": 1, "valeur_min": None},
             {"libelle": "Frontale", "equipement": "frontale", "niveau": "obligatoire", "quantite": 1,
              "valeur_min": None},
             {"libelle": "Réserve d'eau 1 L", "equipement": "reserve_eau", "niveau": "obligatoire", "quantite": 1,
              "valeur_min": 1.0},
             {"libelle": "Gilet de flottaison", "equipement": None, "niveau": "obligatoire", "quantite": 1,
              "valeur_min": None, "dans_le_sac": 0},
             {"libelle": "Collant", "equipement": "pantalon_long", "niveau": "obligatoire", "quantite": 1}]
    inv = [_objet("veste_impermeable", car={}), _objet("frontale", controle_le="2025-01-01"),
           _objet("reserve_eau", "Poche à eau"), _objet("pantalon_long", statut="À surveiller")]
    r = cmp.comparer(liste, inv, "2026-11-20")
    st = [l["statut"] for l in r["lignes"]]
    assert st == ["verifier", "verifier", "verifier", "manuel", "verifier"]
    assert "plus de 6 mois" in r["lignes"][1]["detail"]
    liste[3]["dans_le_sac"] = 1
    assert cmp.comparer(liste, inv)["lignes"][3]["statut"] == "ok"
    sans_capuche = cmp.comparer(liste[:1], [_objet("veste_impermeable", car={"coutures_etanches": False})])
    assert sans_capuche["lignes"][0]["statut"] == "manque"
    # quantité
    deux = cmp.comparer([{"libelle": "2 gobelets", "equipement": "gobelet", "niveau": "obligatoire", "quantite": 2}],
                        [_objet("gobelet")])
    assert deux["lignes"][0]["statut"] == "manque" and "Il en faut 2" in deux["lignes"][0]["detail"]


def test_reserve_alimentaire_avec_mes_produits():
    from noyau.nutrition import catalogue as cat
    gel = {**cat.generique("g:gel"), "id": 1, "favori": 1}
    req = [{"libelle": "Réserve alimentaire 800 kcal", "equipement": "reserve_alimentaire", "niveau": "obligatoire",
            "quantite": 1, "valeur_min": 800}]
    r = cmp.comparer(req, [], produits_nutrition=[gel])
    l = r["lignes"][0]
    assert l["statut"] == "ok" and "Gel énergétique classique" in l["detail"] and "kcal" in l["detail"]
    assert cmp.comparer(req, [])["lignes"][0]["statut"] == "manque"


def test_base_equipement_et_liste(base_vide):
    import data.database as db
    from noyau.donnees import equipement as deq
    c = sqlite3.connect(db.CHEMIN_BDD)
    c.execute("INSERT INTO courses_calendrier (id, athlete_id, nom, date, distance_km, denivele_m) "
              "VALUES (5, 1, 'Course test', '2027-06-01', 60, 3000)")
    c.execute("INSERT INTO materiel (athlete_id, nom, type, statut) VALUES (1, 'Frontale Petzl', 'Autre', 'Actif')")
    c.execute("INSERT INTO materiel (athlete_id, nom, type, statut) VALUES (1, 'Speedgoat', 'Chaussures', 'Actif')")
    c.commit()
    c.close()
    assert deq.relier_automatiquement(1) == 1
    objets = deq.equipements(1)
    assert {o["nom"]: o["equipement"] for o in objets} == {"Frontale Petzl": "frontale", "Speedgoat": None}
    fid = next(o["id"] for o in objets if o["nom"] == "Frontale Petzl")
    deq.modifier_equipement(fid, {"poids_g": 85, "caracteristiques": {"lumens": 450, "vide": None}})
    o = deq.equipement(fid)
    assert o["poids_g"] == 85 and o["caracteristiques"] == {"lumens": 450}
    deq.batteries_controlees([fid], "2026-11-06")
    assert deq.equipement(fid)["controle_le"] == "2026-11-06"
    vid = deq.creer_equipement(1, {"nom": "Veste", "equipement": "veste_impermeable",
                                   "caracteristiques": {"colonne_eau_mm": 20000}})
    assert deq.equipement(vid)["type"] == "Vêtement"
    with pytest.raises(deq.ErreurEquipement):
        deq.creer_equipement(1, {"nom": " "})
    with pytest.raises(deq.ErreurEquipement):
        deq.creer_equipement(1, {"nom": "X", "equipement": "fusee"})

    deq.enregistrer_liste(1, 5, eq.analyser_reglement(REGLEMENT))
    liste = deq.liste_de_la_course(5)
    assert len(liste) >= 14 and liste[0]["ordre"] == 0
    assert deq.infos_reglement(5)[0] is not None
    deq.cocher_sac(liste[0]["id"])
    assert deq.liste_de_la_course(5)[0]["dans_le_sac"] == 1
    deq.vider_sac(5)
    assert not any(l["dans_le_sac"] for l in deq.liste_de_la_course(5))
    assert deq.courses(1)[0]["nb_lignes"] == len(liste)
    with pytest.raises(deq.ErreurEquipement):
        deq.enregistrer_liste(1, 5, [{"libelle": "X", "niveau": "peut-être"}])
    assert len(deq.liste_de_la_course(5)) == len(liste)          # rien n'a changé
    # la liste disparaît avec la course
    from noyau.donnees import base
    base.ecrire("DELETE FROM courses_calendrier WHERE id=5")
    assert deq.liste_de_la_course(5) == []


def test_checklist_du_roadbook_utilise_le_reglement():
    from noyau.course import roadbook as rbk
    officielle = [{"libelle": "Réserve d'eau 1,5 L", "equipement": "reserve_eau", "niveau": "obligatoire",
                   "valeur_min": 1.5},
                  {"libelle": "Lunettes", "equipement": "lunettes", "niveau": "meteo", "valeur_min": None},
                  {"libelle": "Bâtons", "equipement": "batons", "niveau": "conseille", "valeur_min": None}]
    cl = rbk.construire_checklist(50, 2500, liste_officielle=officielle)
    oblig = [c for c in cl if c["section"] == "Obligatoire"]
    assert [c["texte"] for c in oblig] == ["Réserve d'eau 1,5 L", "Lunettes"]
    assert "1,5 L minimum" in oblig[0]["raison"] and "météo" in oblig[1]["raison"]
    assert [c["texte"] for c in cl if c["section"] == "Conseillé"] == ["Bâtons"]
    assert any(c["section"] == "Obligatoire" for c in rbk.construire_checklist(50, 2500))


def test_ecran_et_pdf(base_vide, tmp_path):
    import shiboken6
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    import data.database as db
    from noyau.donnees import equipement as deq
    c = sqlite3.connect(db.CHEMIN_BDD)
    c.execute("INSERT INTO courses_calendrier (id, athlete_id, nom, date, distance_km, denivele_m) "
              "VALUES (3, 1, 'Ultra', '2099-06-01', 90, 5000)")
    c.commit()
    c.close()
    deq.creer_equipement(1, {"nom": "Frontale", "equipement": "frontale"})
    from interface.materiel_course import MaterielCourse
    f = MaterielCourse(1, {"id": 3})
    pc = f.pour_course
    assert pc.combo_course.currentData() == 3
    assert pc.table.rowCount() > 8 and not pc._officielle                 # repère standard
    deq.enregistrer_liste(1, 3, eq.analyser_reglement(REGLEMENT))
    pc.actualiser()
    assert pc._officielle and pc.table.rowCount() == len(deq.liste_de_la_course(3))
    f.mon_equipement.actualiser()
    assert f.mon_equipement.table.rowCount() == 1
    from interface.roadbook_fiche import rendre_checklist_materiel_pdf
    chemin = tmp_path / "check.pdf"
    assert rendre_checklist_materiel_pdf(str(chemin), "Ultra", "2099-06-01", pc._resultat, "Liste") >= 1
    assert chemin.stat().st_size > 2000
    app.processEvents()
    shiboken6.delete(f)
