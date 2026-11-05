"""VMA, VO2max et évolutions calculées par jour, par semaine ou par mois."""
import sqlite3
from datetime import date, timedelta

import pytest

from noyau.outils.periodes import periodes, remplir_trous
from noyau.entrainement.vma import calculer_vma, vma_depuis_effort
from noyau.entrainement.estimations_basses import serie_estimations
from noyau.entrainement.evolution_performance import serie_evolution, serie_evolution_mensuelle


def test_decoupage():
    fin = date(2026, 11, 5)                      # un jeudi
    j = periodes(fin, "jour", 3)
    assert [(l, d.isoformat(), f.isoformat()) for l, d, f in j] == [
        ("03/11", "2026-11-03", "2026-11-03"), ("04/11", "2026-11-04", "2026-11-04"), ("05/11", "2026-11-05", "2026-11-05")]
    s = periodes(fin, "semaine", 2)
    assert [(l, d.isoformat(), f.isoformat()) for l, d, f in s] == [
        ("26/10", "2026-10-26", "2026-11-01"), ("02/11", "2026-11-02", "2026-11-05")]   # la semaine en cours s'arrête à aujourd'hui
    m = periodes(fin, "mois", 3)
    assert [(l, d.isoformat(), f.isoformat()) for l, d, f in m] == [
        ("09/26", "2026-09-01", "2026-09-30"), ("10/26", "2026-10-01", "2026-10-31"), ("11/26", "2026-11-01", "2026-11-05")]
    assert len(periodes(fin, "mois")) == 24 and len(periodes(fin, "semaine")) == 52 and len(periodes(fin, "jour")) == 90
    assert periodes(date(2026, 1, 15), "mois", 2)[0][0] == "12/25"
    with pytest.raises(ValueError):
        periodes(fin, "heure")
    assert remplir_trous([("a", None), ("b", 1), ("c", None), ("d", 2)]) == [("b", 1), ("c", 1), ("d", 2)]


@pytest.fixture
def sorties(base_vide):
    c = sqlite3.connect(base_vide)
    auj = date.today()
    # 10 km : 50 min il y a 20 jours, 45 min il y a 10 jours, 60 min il y a 3 jours (tranquille)
    for jours, minutes in ((20, 50), (10, 45), (3, 60)):
        c.execute("INSERT INTO activites (athlete_id, date, type, distance, denivele, duree, nom) VALUES (1,?,?,?,?,?,?)",
                  ((auj - timedelta(days=jours)).isoformat() + " 08:00:00", "Course", 10, 0, minutes * 60, f"S{jours}"))
    c.commit()
    c.close()
    return auj


def test_vma_par_jour_semaine_mois(sorties):
    auj = sorties
    v50, v45, v60 = (vma_depuis_effort(10, 0, m * 60) for m in (50, 45, 60))
    mois = calculer_vma(1)
    assert mois == calculer_vma(1, "mois")
    jour = calculer_vma(1, "jour", 30)
    lib = {l: v for l, v in jour["serie"]}
    # la série commence le jour de la première sortie ; la VMA du moment monte le jour de la meilleure sortie
    assert jour["serie"][0] == ((auj - timedelta(days=20)).strftime("%d/%m"), round(v50, 1))
    assert lib[(auj - timedelta(days=10)).strftime("%d/%m")] == round((v45 + v50) / 2, 1)
    assert lib[(auj - timedelta(days=3)).strftime("%d/%m")] == round((v45 + v50 + v60) / 3, 1)
    meilleure = dict(jour["serie_meilleure_sortie"])
    assert meilleure[(auj - timedelta(days=10)).strftime("%d/%m")] == round(v45, 1)
    assert meilleure[(auj - timedelta(days=11)).strftime("%d/%m")] is None      # pas de sortie ce jour-là
    assert len(jour["serie_meilleure_sortie"]) == len(jour["serie"])
    semaine = calculer_vma(1, "semaine", 8)
    assert semaine["pas"] == "semaine" and semaine["serie"][-1][1] == jour["serie"][-1][1]
    assert jour["actuelle"] == mois["actuelle"] == semaine["actuelle"]   # la VMA du moment ne dépend pas du pas


def test_estimations_et_evolution_par_semaine(sorties):
    est = serie_estimations(1, pas="semaine", nb=8)
    assert est["pas"] == "semaine" and est["vma"][-1][1] is not None and est["vo2max"][-1][1] is not None
    assert sum(v for _, v in serie_evolution(1, "distance", "semaine", 8)) == 30
    par_jour = serie_evolution(1, "distance", "jour", 30)
    assert sum(v for _, v in par_jour) == 30 and sum(1 for _, v in par_jour if v == 10) == 3   # jours sans sortie : 0
    fc = serie_evolution(1, "fc_moyenne", "jour", 30)
    assert all(v is None for _, v in fc)                       # pas de FC : aucune valeur inventée
    assert serie_evolution_mensuelle(1, "vo2max", 12) == serie_evolution(1, "vo2max", "mois", 12)
