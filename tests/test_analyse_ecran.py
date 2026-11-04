"""Tests v106 : analyses IA des écrans (IA simulée — aucun appel réseau)."""
import json
import os
import sqlite3
from datetime import date, timedelta

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import data.database as db


@pytest.fixture
def base(tmp_path, monkeypatch):
    chemin = tmp_path / "t.db"
    monkeypatch.setattr(db, "CHEMIN_BDD", chemin)
    db.creer_base_de_donnees()
    c = sqlite3.connect(chemin)
    c.execute("INSERT INTO athletes (id, nom, prenom, age, fc_max, fc_repos, vma) VALUES (1,'T','C',40,185,50,16)")
    for k in range(30):
        j = date.today() - timedelta(days=3 * (30 - k))
        c.execute("INSERT INTO activites (athlete_id,date,nom,type,distance,denivele,duree,frequence_cardiaque_moyenne,"
                  "frequence_cardiaque_max,temperature_moyenne,temps_zone_1,temps_zone_2,temps_zone_3,temps_zone_4,temps_zone_5) "
                  "VALUES (1,?,?,?,10,300,?,150,175,?,2400,900,200,80,20)",
                  (j.isoformat() + " 07:00:00", f"S{k}", "Trail", 4800 - k * 15, [8, 14, 21, 27][k % 4]))
    for k in range(20):
        j = date.today() - timedelta(days=20 - k)
        c.execute("INSERT INTO suivi_corporel (athlete_id,date,poids_kg,fatigue_jambes,fatigue_generale,moment) "
                  "VALUES (1,?,?,?,?,'matin')", (j.isoformat(), 86 - k * 0.1, 3 + k % 3, 3))
    c.commit()
    c.close()


class IAFausse:
    def __init__(self):
        self.prompts = []

    def __call__(self, prompt):
        self.prompts.append(prompt)
        return "**Lecture** : poids en baisse de 0,1 kg/jour."


def test_dossiers_contiennent_des_chiffres(base):
    from data import analyse_ecran as ae
    p = ae.dossier_poids(1)
    assert p["poids"]["nb_points"] == 20 and p["poids"]["variation_pct"] < 0 and p["moyenne_7j_kg"] < p["moyenne_7j_precedents_kg"]
    v = ae.dossier_vma(1)
    assert v["vma_estimee_kmh"] > 0 and "serie_vo2max" in v and v["vma_du_profil_kmh"] == 16
    a = ae.dossier_aujourdhui(1)
    assert a["coach_du_jour"]["niveau"] in ("vert", "orange", "rouge") and a["forme"]
    assert ae.dossier_conditions(1)["polarisation_6_semaines"]
    assert ae.dossier_sommeil(1)["forme"]


def test_analyse_cache_et_regeneration(base):
    from data import analyse_ecran as ae
    ia = IAFausse()
    d = ae.dossier_poids(1)
    t1, s1 = ae.analyser(1, "poids", d, appeler=ia)
    assert s1 == "ia" and "Lecture" in t1 and len(ia.prompts) == 1
    assert "RÈGLES ABSOLUES" in ia.prompts[0] and '"poids"' in ia.prompts[0]
    t2, s2 = ae.analyser(1, "poids", d, appeler=ia)
    assert s2 == "cache" and len(ia.prompts) == 1                      # aucun nouvel appel
    t3, s3 = ae.analyser(1, "poids", d, forcer=True, appeler=ia)
    assert s3 == "ia" and len(ia.prompts) == 2
    d2 = dict(d, moyenne_7j_kg=80.0)                                    # chiffres changés -> nouvelle analyse
    assert ae.analyser(1, "poids", d2, appeler=ia)[1] == "ia"


def test_repli_local_sans_cle(base, monkeypatch):
    from data import analyse_ecran as ae
    monkeypatch.setattr(ae, "cle_ia_disponible", lambda: False)
    t, s = ae.analyser(1, "poids", ae.dossier_poids(1))
    assert s == "local" and "Chiffres clés" in t and "moyenne 7j kg" in t
    assert ae.analyser(1, "poids", {})[1] == "local"


def test_ecrans_ont_une_carte_ia(base):
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    from interface.analyse_ia_widget import CarteAnalyseIA
    from interface.forme_evolution import FormeFatigue, EvolutionPerformances
    from interface.sante_charge import SommeilRecuperation
    from interface.vma import VMACircuits
    from interface.poids_fatigue import PoidsFatigue
    from interface.analyses_avancees import MeilleursEfforts, ConditionsIntensite
    from interface.recuperation_tendances import RecuperationTendances
    from data import analyse_ecran as ae
    for cls in (FormeFatigue, EvolutionPerformances, SommeilRecuperation, VMACircuits, PoidsFatigue,
                MeilleursEfforts, ConditionsIntensite, RecuperationTendances):
        e = cls(athlete_id_initial=1)
        assert e.findChildren(CarteAnalyseIA), cls.__name__
    # dossier générique d'un écran à courbes : les courbes affichées sont résumées
    f = FormeFatigue(athlete_id_initial=1)
    d = f._dossier_ia()
    assert d["affiche_a_l_ecran"]["courbes"] and "forme" in d


def test_carte_affiche_le_resultat(base, monkeypatch):
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    from interface.analyse_ia_widget import CarteAnalyseIA
    from data import analyse_ecran as ae
    monkeypatch.setattr(ae, "cle_ia_disponible", lambda: False)
    carte = CarteAnalyseIA("poids", "poids", lambda: 1, lambda: ae.dossier_poids(1))
    carte.lancer()
    carte._tache.wait()
    app.processEvents()
    assert "Chiffres clés" in carte.texte.text() and "local" in carte.note.text().lower()
    sans = CarteAnalyseIA("poids", "poids", lambda: None, lambda: {})
    sans.lancer()
    assert "athlète" in sans.texte.text()


def test_tableau_de_bord_aujourdhui_a_la_carte(base):
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    import data.metriques as met
    from interface.aujourdhui import EcranAujourdhui
    from interface.analyse_ia_widget import CarteAnalyseIA
    nav = {k: (lambda: None) for k in ("nouvelle", "palette", "sante", "charge", "alertes", "plan", "coach",
                                       "bilans", "courses", "sortie", "ressenti")}
    nav["athlete_change"] = lambda i: None
    e = EcranAujourdhui(nav, [(1, "C T")], 1)
    e._recu(met.donnees_aujourdhui(1), None)
    assert e.findChildren(CarteAnalyseIA)
