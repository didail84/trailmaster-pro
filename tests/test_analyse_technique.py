"""
Tests du dossier technique envoyé à l'IA (v101) : chiffres de performance
calculés en local, repli propre sans trace, consignes du prompt.
Lancer :  python3 -m pytest tests
"""

import json
import os
import sqlite3
from datetime import date, timedelta

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import data.database as db


def _trace(n=900):
    pts, lat, lon, alt = [], 44.0, 5.0, 300.0
    for i in range(n):
        pente = 0.08 if (i // 150) % 2 == 0 else -0.06
        alt += pente * 10
        lat += 0.00018
        lon += 0.00005
        pts.append([lat, lon, alt, i * 10, 140 + (i * 12) // n + (8 if pente > 0 else -4), 80])
    return pts


@pytest.fixture
def base(tmp_path, monkeypatch):
    chemin = tmp_path / "t.db"
    monkeypatch.setattr(db, "CHEMIN_BDD", chemin)
    db.creer_base_de_donnees()
    c = sqlite3.connect(chemin)
    c.execute("INSERT INTO athletes (id, nom, prenom, age, fc_max, fc_repos) VALUES (1,'T','C',40,185,50)")
    ids = []
    for k in range(6):
        j = date.today() - timedelta(days=2 + k * 4)
        cur = c.execute(
            "INSERT INTO activites (athlete_id,date,nom,type,distance,denivele,duree,frequence_cardiaque_moyenne,"
            "frequence_cardiaque_max) VALUES (1,?,?,?,?,?,?,?,?)",
            (j.isoformat() + " 07:30:00", f"S{k}", "Trail", 14.0, 520, 9000, 148, 172))
        ids.append(cur.lastrowid)
    c.execute("INSERT INTO parcours_gpx (athlete_id,nom,distance_km,denivele_positif,denivele_negatif,trace_json,activite_id)"
              " VALUES (1,'t',14,520,520,?,?)", (json.dumps(_trace()), ids[0]))
    c.commit()
    c.close()
    return ids


def test_dossier_sortie_avec_trace(base):
    from interface.analyse_technique import dossier_sortie
    d = dossier_sortie(base[0], 1)
    assert d["effort"]["km_effort"] == 19.2
    assert "decouplage_cardiaque_Pa_Hr" in d["trace"]
    gap = d["trace"]["allure_ajustee_pente"]
    assert gap["allure_ajustee_GAP"] and gap["detail"]
    assert d["zones_FC"]["zones"][2]["bpm"] == "130-148"
    assert d["comparaison_sorties_similaires"]["nb_sorties_comparees"] >= 2
    assert "fraicheur_TSB" in d["charge_et_fraicheur_au_jour_J"]
    assert d["nature_probable_de_la_seance"]


def test_dossier_sortie_sans_trace_ni_donnees(base):
    from interface.analyse_technique import dossier_sortie
    d = dossier_sortie(base[3], 1)         # sortie sans trace
    assert "trace_absente" in d and "trace" not in d
    assert dossier_sortie(99999, 1) == {}  # sortie inconnue : jamais d'exception


def test_prompts_techniques(base):
    from interface import ia_coach as ia
    p = ia._construire_prompt(ia.construire_resume_sortie(base[0], 1))
    for titre in ("### Lecture technique de la séance", "### Limiteurs de performance",
                  "### Prescription pour la prochaine séance"):
        assert titre in p
    assert "non mesuré" in p and "DÉFINITIONS" in p
    aujourd = date.today()
    r = ia.construire_resume_periode(1, "mois")
    pp = ia._construire_prompt_periode("mois", aujourd - timedelta(days=27), aujourd, r)
    assert "### Bilan technique de la période" in pp and "volume" in json.dumps(r["dossier_technique"])


def test_ancienne_analyse_est_regeneree(base, monkeypatch):
    from interface import ia_coach as ia
    ia._enregistrer_analyse(1, base[0], "### Ce qui est positif\nancien format")
    monkeypatch.setattr(ia, "_appeler_ia", lambda prompt: "### Lecture technique de la séance\nnouveau")
    texte, depuis_cache = ia.analyser_sortie(base[0], 1)
    assert not depuis_cache and "Lecture technique" in texte
    _, depuis_cache = ia.analyser_sortie(base[0], 1)     # la nouvelle est réutilisée
    assert depuis_cache
