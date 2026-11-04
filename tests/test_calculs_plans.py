"""Étape 1.2 — filet de sécurité : générateur de plan classique et
programme Ultra. Ces tests figent le comportement actuel (v108) pour
qu'aucun déplacement de code vers le noyau ne le change sans qu'on le voie."""
from datetime import date

import pytest

from interface import generateur_plan as gp
from interface import generateur_ultra as gu


# ------------------------------------------------------------------
# Générateur de plan classique
# ------------------------------------------------------------------

@pytest.fixture
def plan_10km():
    return gp.generer_plan("10 km", 10, "Intermédiaire", 4, "5:00")


def test_plan_nombre_de_semaines_et_phases(plan_10km):
    assert [s["indice"] for s in plan_10km] == list(range(1, 11))
    phases = [s["phase"] for s in plan_10km]
    # 40 % de base (4 semaines), affûtage = max(2, 15 % de 10) = 2 semaines
    assert phases == ["base"] * 4 + ["developpement"] * 4 + ["affutage"] * 2


def test_plan_volumes_calcules(plan_10km):
    volumes = {s["indice"]: s["volume_km"] for s in plan_10km}
    # semaine 1 : 20 + (35 - 20) × 1/8 = 21,9 → 22 km
    assert volumes[1] == 22
    # semaine 4 = récupération : (20 + 15 × 4/8) × 0,7 = 19,25 → 19 km
    assert volumes[4] == 19
    # semaine 8 = semaine de récupération au pic : 35 × 0,7 = 24,5 → 24 km (arrondi Python)
    assert volumes[8] == 24
    # affûtage : 85 % puis 50 % du pic
    assert volumes[9] == round(35 * 0.7)
    assert volumes[10] == round(35 * 0.5)


def test_plan_semaines_de_recuperation(plan_10km):
    recup = [s["indice"] for s in plan_10km if s["recuperation"]]
    assert recup == [4, 8]  # toutes les 4 semaines, jamais en affûtage


def test_plan_seances_de_la_semaine(plan_10km):
    for semaine in plan_10km:
        jours = sorted(s["jour_offset"] for s in semaine["seances"])
        assert jours == [1, 3, 5, 6]  # 4 jours : mardi, jeudi, samedi, dimanche
        longue = next(s for s in semaine["seances"] if s["type_seance"] == "Sortie longue")
        assert longue["jour_offset"] == 6  # toujours le dimanche


def test_plan_sortie_longue_et_allures(plan_10km):
    s1 = plan_10km[0]
    longue = next(s for s in s1["seances"] if s["type_seance"] == "Sortie longue")
    assert longue["etapes"][0]["valeur"] == 8.8          # 8 + 6 × 1/8 = 8,75 → 8,8 km
    assert longue["etapes"][0]["allure_cible"] == "6:00"  # endurance = objectif × 1,20
    # dernière semaine d'affûtage : 40 % de la sortie longue pic
    derniere = plan_10km[-1]
    longue_fin = next(s for s in derniere["seances"] if s["type_seance"] == "Sortie longue")
    assert longue_fin["etapes"][0]["valeur"] == 5.6


def test_plan_qualite_en_developpement(plan_10km):
    types = {}
    for semaine in plan_10km:
        for s in semaine["seances"]:
            if s["type_seance"] in ("Fractionné", "Côtes"):
                types[semaine["indice"]] = s["type_seance"]
    # qualité hors base et hors récupération : développement (5, 6, 7) et
    # affûtage (9, 10 — « on garde un peu d'intensité »), alternée par semaine
    assert types == {5: "Fractionné", 6: "Côtes", 7: "Fractionné", 9: "Fractionné", 10: "Côtes"}
    fractionne = next(s for s in plan_10km[4]["seances"] if s["type_seance"] == "Fractionné")
    efforts = [e for e in fractionne["etapes"] if e["type"] == "Effort"]
    assert len(efforts) == 6 and all(e["valeur"] == 0.8 for e in efforts)
    assert efforts[0]["allure_cible"] == "4:30"  # fractionné = objectif × 0,90


def test_plan_facteur_niveau_et_sans_allure():
    debutant = gp.generer_plan("Marathon", 16, "Débutant", 3, "")
    confirme = gp.generer_plan("Marathon", 16, "Confirmé", 3, "")
    assert debutant[0]["volume_km"] < confirme[0]["volume_km"]
    assert len(debutant[0]["seances"]) == 3
    for semaine in debutant:
        for s in semaine["seances"]:
            for e in s["etapes"]:
                assert e["allure_cible"] is None  # pas d'allure objectif → pas d'allure cible


def test_plan_nombre_de_jours_inconnu_retombe_sur_4():
    plan = gp.generer_plan("10 km", 8, "Intermédiaire", 7, "5:00")
    assert len(plan[0]["seances"]) == 4


def test_formater_allure_et_date_seance():
    assert gp._formater_allure(5.5) == "5:30"
    assert gp._formater_allure(4.999) == "5:00"  # 59,9 s arrondi → minute suivante
    assert gp._formater_allure(None) is None
    lundi = date(2026, 11, 2)
    assert gp.date_seance(lundi, 1, 0) == lundi
    assert gp.date_seance(lundi, 3, 6) == date(2026, 11, 22)


# ------------------------------------------------------------------
# Programme Ultra
# ------------------------------------------------------------------

def test_ultra_repartition_des_semaines():
    assert gu._repartir_semaines(104) == [17, 17, 17, 17, 18, 18]
    assert gu._repartir_semaines(24) == [4] * 6
    assert sum(gu._repartir_semaines(31)) == 31


def test_ultra_penalite_zone_fc_et_duree():
    assert gu._facteur_penalite_ultra(42.2) == 1.0
    assert gu._facteur_penalite_ultra(50) == 1.12
    assert gu._facteur_penalite_ultra(70) == 1.32
    assert gu._facteur_penalite_ultra(120) == 1.32
    assert gu._zone_fc(10, 185) == (152, 166)
    assert gu._zone_fc(42, 185) == (144, 157)
    assert gu._zone_fc(80, 185) == (130, 144)
    assert gu._zone_fc(10, None) == (None, None)
    assert gu._formater_duree_h(3 * 3600 + 25 * 60) == "3h25"
    assert gu._formater_duree_h(40 * 60) == "40min"


def test_ultra_baseline_sans_sortie(base_vide):
    b = gu.estimer_baseline_actuelle(1)
    assert b["volume_hebdo_moyen_km"] is None and b["plus_longue_recente_km"] is None


def test_ultra_cibles_sans_record(base_vide):
    c = gu.cibles_course(1, 60)
    assert c["duree_s"] is None and c["allure_texte"] is None
    assert (c["fc_min"], c["fc_max"]) == (130, 144)


def test_ultra_programme_complet(base_vide):
    semaines, baseline, blocs = gu.generer_programme_ultra(
        1, distance_finale_km=60.0, nb_semaines=24, date_debut=date(2026, 11, 2))
    assert len(semaines) == 24
    assert [b["nom"] for b in blocs] == gu.NOMS_BLOCS
    assert [b["distance_repere_km"] for b in blocs] == [15.0, 24.0, 33.0, 42.0, 51.0, 60.0]
    # la toute dernière semaine porte l'objectif final
    noms_derniere = [s["nom"] for s in semaines[-1]["seances"]]
    assert any(n.startswith("🏁 OBJECTIF — Ultra 60 km") for n in noms_derniere)
    # garde-fou de volume : jamais plus de 130 km par semaine
    assert max(s["volume_km"] for s in semaines) <= 130
    # au plus 3 séances de musculation par semaine (réglage par défaut)
    for s in semaines:
        nb_muscu = sum(1 for x in s["seances"] if x["type_seance"] == "Musculation")
        assert nb_muscu <= 3


def test_ultra_volume_part_de_la_baseline(base_vide):
    semaines, _, _ = gu.generer_programme_ultra(1, distance_finale_km=60.0, nb_semaines=24)
    # sans historique : volume de départ 20 km × facteur 1,0, jamais sous 12 km
    assert semaines[0]["volume_km"] >= 12
