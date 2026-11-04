"""Étape 1.2 — filet de sécurité : estimation du temps de course apprise
sur les sorties de l'athlète (régression distance + dénivelé)."""
from datetime import date, timedelta

import pytest

from data import estimation_temps_course as etc
from conftest import connecter


def duree_modele(d_km, d_plus):
    """Coureur « parfait » : 300 s/km + 0,6 s/m de D+ + 120 s fixes."""
    return 300 * d_km + 0.6 * d_plus + 120


def inserer_sorties(chemin, sorties):
    c = connecter(chemin)
    for jour, d_km, d_plus, duree, type_ in sorties:
        c.execute("INSERT INTO activites (athlete_id, date, nom, type, distance, denivele, duree) "
                  "VALUES (1, ?, 'S', ?, ?, ?, ?)", (jour, type_, d_km, d_plus, duree))
    c.commit()
    c.close()


def test_systeme_3x3():
    # 2x + y + z = 7 ; x + 3y + 2z = 13 ; x + y + 4z = 15 → x = 1, y = 2, z = 3
    sol = etc._resoudre_systeme_3x3([[2, 1, 1], [1, 3, 2], [1, 1, 4]], [7, 13, 15])
    assert [round(v, 9) for v in sol] == [1, 2, 3]
    # système dégénéré (deux lignes identiques) → None
    assert etc._resoudre_systeme_3x3([[1, 1, 1], [1, 1, 1], [0, 0, 1]], [1, 1, 1]) is None


def test_regression_retrouve_les_coefficients():
    lignes = [(d, n, duree_modele(d, n)) for d, n in
              [(8, 200), (10, 450), (12, 300), (15, 900), (21, 600), (6, 100)]]
    a, b, c = etc._regression_duree(lignes)
    assert a == pytest.approx(300, abs=1e-6)
    assert b == pytest.approx(0.6, abs=1e-6)
    assert c == pytest.approx(120, abs=1e-4)


def test_regression_pas_assez_de_sorties():
    assert etc._regression_duree([(10, 100, 3200)] * 4) is None


def test_formater_duree():
    assert etc._formater_duree(None) == "—"
    assert etc._formater_duree(0) == "—"
    assert etc._formater_duree(45 * 60) == "45 min"
    assert etc._formater_duree(2 * 3600 + 5 * 60 + 40) == "2 h 05 min"


def test_estimation_sans_historique(base_vide):
    assert etc.estimer_temps_course(1, 20, 1000) is None
    assert etc.estimer_temps_course(1, 0, 1000) is None
    assert etc.estimer_temps_course(None, 20, 1000) is None


def test_estimation_depuis_les_sorties(base_vide):
    aujourdhui = date.today()
    profils = [(8, 200), (10, 450), (12, 300), (15, 900), (21, 600), (6, 100)]
    inserer_sorties(base_vide, [
        ((aujourdhui - timedelta(days=10 * i)).isoformat(), d, n, duree_modele(d, n), "Trail")
        for i, (d, n) in enumerate(profils)
    ])
    r = etc.estimer_temps_course(1, 20, 1000)
    assert r["secondes"] == pytest.approx(duree_modele(20, 1000), abs=0.5)  # 6 720 s
    assert r["duree_formatee"] == "1 h 52 min"
    assert r["nb_sorties"] == 6
    assert r["extrapolation"] is False and r["ajustement_saison"] is False
    # au-delà de 2,5 × la plus longue sortie connue (21 km) → extrapolation signalée
    assert etc.estimer_temps_course(1, 60, 3000)["extrapolation"] is True


def test_estimation_ignore_le_velo_et_les_vieilles_sorties(base_vide):
    vieux = (date.today() - timedelta(days=365 * 3)).isoformat()
    recent = date.today().isoformat()
    inserer_sorties(base_vide, [(vieux, d, 100, duree_modele(d, 100), "Trail") for d in (5, 8, 10, 12, 15)]
                    + [(recent, d, 100, 100 * d, "Vélo") for d in (20, 30, 40, 50, 60)])
    assert etc.estimer_temps_course(1, 20, 1000) is None


def test_estimation_ajustement_de_saison(base_vide):
    # 6 sorties « d'hiver » 10 % plus lentes que le modèle + 6 autres
    hiver = []
    for i, (d, n) in enumerate([(8, 200), (10, 450), (12, 300), (15, 900), (21, 600), (6, 100)]):
        hiver.append((f"{date.today().year - 1}-12-{10 + i:02d}", d, n, duree_modele(d, n) * 1.10, "Trail"))
    ete = []
    for i, (d, n) in enumerate([(9, 250), (11, 500), (13, 350), (16, 800), (18, 700), (7, 150)]):
        ete.append((f"{date.today().year - 1}-07-{10 + i:02d}", d, n, duree_modele(d, n) * 0.95, "Trail"))
    inserer_sorties(base_vide, hiver + ete)
    sans = etc.estimer_temps_course(1, 20, 1000)
    avec = etc.estimer_temps_course(1, 20, 1000, date_course=f"{date.today().year}-01-15")
    assert avec["ajustement_saison"] is True
    assert avec["secondes"] > sans["secondes"]  # course en hiver → plus lente
    # l'ajustement reste borné entre 0,85 et 1,20
    assert 0.85 <= avec["secondes"] / sans["secondes"] <= 1.20
