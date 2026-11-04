"""Analyses automatiques des sorties (hors ligne et IA) — Trail Hub Center."""
import sqlite3
from datetime import datetime, timedelta

import pytest

import data.database as db
from noyau.ia import analyse_auto as aa
from noyau.ia import analyse_locale as al
from noyau.ia import ia_coach


@pytest.fixture
def base(tmp_path, monkeypatch):
    chemin = tmp_path / "t.db"
    monkeypatch.setattr(db, "CHEMIN_BDD", chemin)
    db.creer_base_de_donnees()
    c = sqlite3.connect(chemin)
    c.execute("INSERT INTO athletes (id, nom, prenom, fc_repos, fc_max) VALUES (1, 'T', 'C', 50, 185)")
    maintenant = datetime.now()
    for i, jours in enumerate((0, 2, 5, 40)):
        d = (maintenant - timedelta(days=jours)).strftime("%Y-%m-%d 07:00:00")
        c.execute("INSERT INTO activites (id, athlete_id, date, nom, type, distance, denivele, duree, "
                  "frequence_cardiaque_moyenne, temps_zone_1, temps_zone_2, temps_zone_3, temps_zone_4, temps_zone_5) "
                  "VALUES (?,1,?,?,'Trail',12,600,5400,140,600,2400,1800,500,100)", (i + 1, d, f"Sortie {i + 1}"))
    c.commit()
    c.close()
    monkeypatch.setattr(ia_coach, "cle_api_configuree", lambda: False)
    monkeypatch.setattr(ia_coach, "cle_api_groq_configuree", lambda: False)
    return chemin


def test_seules_les_sorties_recentes_sans_analyse_sont_choisies(base):
    assert aa.sorties_a_analyser() == [(1, 1), (2, 1), (3, 1)]        # la plus récente d'abord ; 40 jours : trop vieille
    assert aa.sorties_a_analyser(limite=2) == [(1, 1), (2, 1), (3, 1)]   # hors ligne : pas de limite utile


def test_passage_hors_ligne_sans_cle(base):
    vus = []
    faits = aa.passage(rappel=lambda i, s: vus.append((i, s)))
    assert faits == [(1, "local"), (2, "local"), (3, "local")] and vus == faits
    textes = aa.analyses_des_sorties([1, 2, 3, 4])
    assert set(textes) == {1, 2, 3}
    t = textes[1]
    assert al.MARQUEUR_ANALYSE_LOCALE in t and "12,0 km" in t and "600 m de D+" in t
    assert ia_coach.MARQUEUR_ANALYSE_TECHNIQUE not in t           # une IA pourra la remplacer plus tard
    assert aa.source_du_texte(t) == "local"
    assert aa.sorties_a_analyser() == []                          # rien à refaire sans clé


def test_avec_une_cle_l_ia_remplace_l_analyse_hors_ligne(base, monkeypatch):
    aa.passage()
    monkeypatch.setattr(ia_coach, "cle_api_configuree", lambda: True)
    assert aa.sorties_a_analyser() == [(1, 1), (2, 1), (3, 1)]   # analyses hors ligne à remplacer
    assert aa.sorties_a_analyser(limite=2) == [(1, 1), (2, 1)]   # avec l'IA : quota protégé
    appels = []
    monkeypatch.setattr(ia_coach, "_appeler_ia", lambda prompt: appels.append(prompt) or "### Lecture technique de la séance\n- ok")
    faits = aa.passage()
    assert [s for _, s in faits] == ["ia", "ia", "ia"] and len(appels) == 3
    assert aa.source_du_texte(aa.analyses_des_sorties([1])[1]) == "ia"
    assert aa.sorties_a_analyser() == []


def test_si_l_ia_echoue_le_reste_du_passage_se_fait_hors_ligne(base, monkeypatch):
    monkeypatch.setattr(ia_coach, "cle_api_configuree", lambda: True)
    appels = []

    def panne(prompt):
        appels.append(1)
        raise ia_coach.ErreurAnalyseIA("quota atteint")
    monkeypatch.setattr(ia_coach, "_appeler_ia", panne)
    faits = aa.passage()
    assert [s for _, s in faits] == ["local", "local", "local"]
    assert len(appels) == 1                                       # une seule tentative d'IA par passage


def test_reglage_desactive(base):
    aa.definir_actif(False)
    assert aa.passage() == [] and aa.analyses_des_sorties([1]) == {}
    aa.definir_actif(True)
    assert aa.actif()


def test_redaction_signale_blessure_et_surcharge():
    texte = al.rediger({
        "activite": {"distance_km": 20, "denivele_positif_m": 1000, "duree_min": 150, "fc_moyenne": 150},
        "acwr": {"acwr": 1.7},
        "blessures_actives": [{"zone": "Genou", "type": "Tendinite"}],
        "sommeil_moyen_recent_h": 5.8,
        "dossier_technique": {
            "nature_probable_de_la_seance": "sortie longue d'endurance",
            "zones_FC": {"pct_facile_Z1_Z2": 40, "pct_intense_Z4_Z5": 35},
            "trace": {"decouplage_cardiaque_Pa_Hr": {"pct": 9.5},
                      "allure_ajustee_pente": {"regularite": {"profil": "split positif (2e moitié plus lente)", "ecart_moitiés_s_km": 25}}},
            "charge_et_fraicheur_au_jour_J": {"fraicheur_TSB": -34, "variation_hebdo_pct": 40},
        }})
    lignes = texte.splitlines()
    pour_la_suite = lignes[lignes.index("### Pour la suite") + 1]
    assert "Blessure en cours (Genou Tendinite)" in pour_la_suite      # la blessure passe en premier
    for attendu in ("1,70", "−34", "40 %", "5,8 h", "9,5 %", "25 s/km", "35 % du temps en Z4-Z5", "estimation"):
        assert attendu in texte, attendu


def test_redaction_sans_chiffres():
    texte = al.rediger({"activite": {}})
    assert "Pas assez de chiffres" in texte and "Rien de particulier" in texte
