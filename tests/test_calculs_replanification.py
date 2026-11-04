"""Étape 1.2 — filet de sécurité : replanification du matin (détection,
décision du niveau d'ajustement, propositions, écriture en base)."""
import json
from datetime import date, timedelta

import pytest

from interface import replanification as rp
from conftest import connecter

AUJOURDHUI = date(2026, 11, 4)


def diag(**changements):
    """Diagnostic « tout va bien », à modifier champ par champ."""
    d = {
        "aujourdhui": AUJOURDHUI, "manquees": [], "nb_manquees_7j": 0, "nb_manquees_14j": 0,
        "acwr": {"acwr": 1.0}, "forme": {"score": 70, "interpretation": "Bonne forme"},
        "fc": {"anomalie": False, "ecart_pct": None, "message": "FC cohérente"},
        "blessure_active": False,
    }
    d.update(changements)
    return d


# ------------------------------------------------------------------
# Décision (seuils « Standard » : attention 1,3 / risque 1,5, 2 et 3 séances manquées)
# ------------------------------------------------------------------

@pytest.mark.parametrize("changement, attendu", [
    ({}, "stable"),
    ({"blessure_active": True}, "alleger_fort"),
    ({"acwr": {"acwr": 1.6}}, "alleger_fort"),
    ({"acwr": {"acwr": 1.4}}, "alleger_leger"),
    ({"forme": {"score": 25, "interpretation": "Fatigue"}}, "alleger_fort"),
    ({"forme": {"score": 45, "interpretation": "Moyen"}}, "alleger_leger"),
    ({"fc": {"anomalie": True, "ecart_pct": 13.0, "message": "FC +13 %"}}, "alleger_fort"),
    ({"fc": {"anomalie": True, "ecart_pct": 7.0, "message": "FC +7 %"}}, "alleger_leger"),
    ({"nb_manquees_7j": 2, "nb_manquees_14j": 2}, "alleger_leger"),
    ({"nb_manquees_14j": 3, "acwr": {"acwr": 0.7}}, "reprise_progressive"),
    ({"nb_manquees_14j": 3, "acwr": {"acwr": 1.0}}, "stable"),
])
def test_decider_niveau(base_vide, changement, attendu):
    niveau, raisons = rp.decider_niveau(diag(**changement))
    assert niveau == attendu
    assert raisons  # toujours au moins une explication


def test_sensibilite_prudente_plus_stricte(base_vide):
    from interface.coach import definir_sensibilite_alertes
    definir_sensibilite_alertes("Prudent")
    assert rp.decider_niveau(diag(acwr={"acwr": 1.45}))[0] == "alleger_fort"


def test_ajuster_etapes():
    etapes = [{"type": "Effort", "mode": "distance", "valeur": 10.0, "allure_cible": "4:30", "fc_cible": 170}]
    reduites = rp._ajuster_etapes(etapes, 0.85, retirer_intensite=False)
    assert reduites[0]["valeur"] == 8.5 and reduites[0]["allure_cible"] == "4:30"
    faciles = rp._ajuster_etapes(etapes, 0.7, retirer_intensite=True)
    assert faciles[0]["valeur"] == 7.0 and faciles[0]["allure_cible"] is None and faciles[0]["fc_cible"] is None
    assert etapes[0]["valeur"] == 10.0  # l'original n'est jamais modifié


# ------------------------------------------------------------------
# Détection en base
# ------------------------------------------------------------------

def etape(km, allure="5:30"):
    return {"type": "Effort", "mode": "distance", "valeur": km, "allure_cible": allure, "fc_cible": None}


@pytest.fixture
def plan(base_vide):
    c = connecter(base_vide)
    plan_id = c.execute("INSERT INTO plans_entrainement (athlete_id, nom) VALUES (1, 'Plan test')").lastrowid
    seances = [
        ("Endurance", "Endurance fondamentale", -2, "Prévue", [etape(8)]),
        ("Longue", "Sortie longue", -5, "Réalisée", [etape(18)]),
        ("Fractionné", "Fractionné", 1, "Prévue", [etape(2), etape(0.8, "4:10"), etape(2)]),
        ("Endurance J+3", "Endurance fondamentale", 3, "Prévue", [etape(10)]),
        ("Longue J+12", "Sortie longue", 12, "Prévue", [etape(22)]),
    ]
    ids = {}
    for nom, type_, decalage, statut, etapes in seances:
        jour = (AUJOURDHUI + timedelta(days=decalage)).isoformat()
        ids[nom] = c.execute(
            "INSERT INTO seances_structurees (athlete_id, nom, type_seance, date_prevue, statut, "
            "etapes_json, plan_id) VALUES (1, ?, ?, ?, ?, ?, ?)",
            (nom, type_, jour, statut, json.dumps(etapes), plan_id)).lastrowid
    c.commit()
    c.close()
    return plan_id, ids


def test_seances_manquees(plan):
    plan_id, ids = plan
    manquees = rp.detecter_seances_manquees(plan_id, AUJOURDHUI)
    assert [s["id"] for s in manquees] == [ids["Endurance"]]  # la sortie longue est réalisée


def test_anomalie_fc(base_vide):
    c = connecter(base_vide)
    for i in range(18):
        fc = 152 if i < 3 else 140  # les 3 plus récentes en hausse
        jour = (AUJOURDHUI - timedelta(days=i)).isoformat()
        c.execute("INSERT INTO activites (athlete_id, date, type, distance, duree, "
                  "frequence_cardiaque_moyenne) VALUES (1, ?, 'Trail', 10, 3600, ?)", (jour, fc))
    c.commit()
    c.close()
    r = rp.detecter_anomalie_fc(1)
    assert r["anomalie"] is True and r["ecart_pct"] == 8.6
    assert (r["fc_recente"], r["fc_baseline"]) == (152, 140)


def test_anomalie_fc_sans_historique(base_vide):
    r = rp.detecter_anomalie_fc(1)
    assert r["anomalie"] is False and r["ecart_pct"] is None


# ------------------------------------------------------------------
# Propositions et application
# ------------------------------------------------------------------

def test_allegement_fort(plan, monkeypatch):
    plan_id, ids = plan
    monkeypatch.setattr(rp, "construire_diagnostic", lambda *a, **k: diag(blessure_active=True))
    _, niveau, _, props = rp.proposer_replanification(plan_id, 1, AUJOURDHUI)
    assert niveau == "alleger_fort"
    par_id = {p["seance_id"]: p for p in props}
    # seules les séances des 7 prochains jours sont allégées (pas celle à J+12)
    assert set(par_id) == {ids["Fractionné"], ids["Endurance J+3"]}
    fractionne = par_id[ids["Fractionné"]]["apres"]
    assert fractionne["nom"] == "Fractionné (allégée)"
    assert all(e["allure_cible"] is None for e in fractionne["etapes"])  # intensité retirée
    assert par_id[ids["Endurance J+3"]]["apres"]["distance_km"] == pytest.approx(7.0)  # -30 %


def test_rattrapage_si_tout_va_bien(plan, monkeypatch):
    plan_id, ids = plan
    manquee = rp.detecter_seances_manquees(plan_id, AUJOURDHUI)
    monkeypatch.setattr(rp, "construire_diagnostic",
                        lambda *a, **k: diag(manquees=manquee, nb_manquees_7j=1, nb_manquees_14j=1))
    _, niveau, _, props = rp.proposer_replanification(plan_id, 1, AUJOURDHUI)
    assert niveau == "stable"
    assert len(props) == 1 and props[0]["type_changement"] == "deplacement"
    # demain (J+1) est déjà pris par le fractionné → déplacée à J+2
    assert props[0]["apres"]["date"] == (AUJOURDHUI + timedelta(days=2)).isoformat()


def test_application_en_base(plan, monkeypatch, base_vide):
    plan_id, ids = plan
    monkeypatch.setattr(rp, "construire_diagnostic", lambda *a, **k: diag(blessure_active=True))
    _, niveau, raisons, props = rp.proposer_replanification(plan_id, 1, AUJOURDHUI)
    rp.appliquer_replanification(plan_id, 1, niveau, raisons, props)
    c = connecter(base_vide)
    nom, etapes_json = c.execute("SELECT nom, etapes_json FROM seances_structurees WHERE id=?",
                                 (ids["Endurance J+3"],)).fetchone()
    c.close()
    assert nom == "Endurance J+3 (allégée)" and json.loads(etapes_json)[0]["valeur"] == 7.0
    histo = rp.historique_replanifications(plan_id)
    assert len(histo) == 1 and histo[0][1] == "alleger_fort" and histo[0][4] == 2


def test_diagnostic_reel_sans_donnees(plan):
    """Le diagnostic complet (ACWR, forme, FC, blessures) tourne sans planter sur une base presque vide."""
    plan_id, _ = plan
    diagnostic, niveau, raisons, _ = rp.proposer_replanification(plan_id, 1, AUJOURDHUI)
    assert niveau in rp.FACTEUR_VOLUME and raisons
    assert diagnostic["nb_manquees_7j"] == 1
