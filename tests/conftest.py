"""Outils communs aux tests de TrailMaster / Trail Hub Center.

Chaque test travaille sur une base SQLite temporaire, jamais sur la
vraie base de l'utilisateur."""
import math
import os
import sqlite3

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("TRAILHUB_SANS_ANALYSE_AUTO", "1")   # pas d'analyses en arrière-plan pendant les tests

import data.database as db

# 1 degré de latitude ≈ 111,195 km (même rayon terrestre que gpx_utils)
DEG_LAT_PAR_M = 1 / 111195.0


def ligne_droite(lat0, lon0, nb_points, pas_m, alt0=300.0, pente_m=0.0, pas_s=None):
    """Points (lat, lon, alt[, temps_s]) sur une ligne nord-sud,
    espacés de pas_m mètres, l'altitude montant de pente_m par point."""
    pts = []
    for i in range(nb_points):
        p = [lat0 + i * pas_m * DEG_LAT_PAR_M, lon0, alt0 + i * pente_m]
        if pas_s is not None:
            p.append(i * pas_s)
        pts.append(p)
    return pts


@pytest.fixture
def base_vide(tmp_path, monkeypatch):
    """Base neuve avec un athlète (id 1), sans aucune activité."""
    chemin = tmp_path / "test.db"
    monkeypatch.setattr(db, "CHEMIN_BDD", chemin)
    db.creer_base_de_donnees()
    c = sqlite3.connect(chemin)
    c.execute("INSERT INTO athletes (id, nom, prenom, age, fc_max, fc_repos) "
              "VALUES (1, 'Test', 'Coureur', 40, 185, 50)")
    c.commit()
    c.close()
    return chemin


def connecter(chemin):
    return sqlite3.connect(chemin)


def distance_m(lat1, lon1, lat2, lon2):
    from interface.gpx_utils import _distance_haversine_km
    return _distance_haversine_km(lat1, lon1, lat2, lon2) * 1000


__all__ = ["ligne_droite", "connecter", "distance_m", "DEG_LAT_PAR_M", "math"]


def pytest_sessionfinish(session, exitstatus):
    """Ferme proprement les fenêtres Qt créées par les tests d'écran avant
    que Python ne quitte : sinon Qt détruit parfois ses objets dans le
    désordre et le processus plante APRÈS des tests tous réussis (déjà le
    cas en v108), ce qui ferait échouer la fabrication sur GitHub."""
    import gc
    try:
        from PySide6.QtWidgets import QApplication
    except ImportError:
        return
    app = QApplication.instance()
    if app is None:
        return
    for fenetre in app.topLevelWidgets():
        fenetre.close()
        fenetre.deleteLater()
    app.processEvents()
    gc.collect()
    app.processEvents()
