"""IMC (indice de masse corporelle) — repère OMS."""
import sqlite3
from datetime import date, timedelta

from noyau.sante import imc as I


def test_calcul_et_unites():
    assert I.calculer_imc(72, 175) == 23.5
    assert I.calculer_imc(72, 1.75) == 23.5           # taille en mètres acceptée
    assert I.calculer_imc("88", "1,80") == 27.2
    for poids, taille in ((None, 175), (72, None), (72, 0), (0, 175), (72, 400), (72, "abc")):
        assert I.calculer_imc(poids, taille) is None


def test_classes_oms_aux_bornes():
    attendu = [(18.4, "Insuffisance pondérale"), (18.5, "Corpulence normale"), (24.9, "Corpulence normale"),
               (25.0, "Surpoids"), (29.9, "Surpoids"), (30.0, "Obésité modérée"), (35.0, "Obésité sévère"),
               (40.0, "Obésité massive")]
    for valeur, libelle in attendu:
        assert I.classe_imc(valeur)[0] == libelle, valeur
    assert I.classe_imc(None) == (None, None)


def test_plage_de_poids_normal():
    assert I.plage_poids_normal(175) == (56.7, 76.5)
    r = I.resume_imc(80.04, 180)
    assert r["imc"] == 24.7 and r["classe"] == "Corpulence normale" and r["plage_poids_normal_kg"] == (59.9, 80.9)
    assert I.resume_imc(80, None) is None


def test_imc_dans_le_dossier_envoye_a_l_ia(base_vide):
    c = sqlite3.connect(base_vide)
    c.execute("UPDATE athletes SET taille=180 WHERE id=1")
    for j in range(1, 8):
        c.execute("INSERT INTO suivi_corporel (athlete_id, date, poids_kg, moment) VALUES (1, ?, 81, 'matin')",
                  ((date.today() - timedelta(days=j)).isoformat(),))
    c.commit()
    c.close()
    from data import analyse_ecran as ae
    d = ae.dossier_poids(1)
    assert d["IMC"]["valeur"] == 25.0 and d["IMC"]["classe_OMS"] == "Surpoids"
