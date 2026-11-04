"""Étape 1.2 — filet de sécurité : segments, secteurs d'entraînement et
lecture des fichiers FIT."""
import json
from datetime import datetime, timedelta

import pytest

from interface import segments_utils as su
from interface import secteurs_utils as secu
from interface import fit_utils as fu
from conftest import ligne_droite, connecter, distance_m


# ------------------------------------------------------------------
# Segments
# ------------------------------------------------------------------

def test_segment_reference_sous_echantillonnee():
    pts = ligne_droite(44.0, 5.0, 41, 10, pente_m=2.0)  # 400 m, +80 m
    ref = su.extraire_reference_segment(pts, 0, 40)
    assert ref["distance_km"] == pytest.approx(0.4, abs=0.002)
    assert ref["denivele_positif"] == 80
    # un point dès qu'on a parcouru au moins 50 m, plus le point d'arrivée
    gaps = [distance_m(*a, *b) for a, b in zip(ref["points_reference"], ref["points_reference"][1:])]
    assert all(g >= 49.9 for g in gaps[:-1]) and all(g <= 61 for g in gaps)
    assert ref["points_reference"][0] == (pts[0][0], pts[0][1])
    assert ref["points_reference"][-1] == (pts[40][0], pts[40][1])


def test_segment_trop_court():
    pts = ligne_droite(44.0, 5.0, 9, 10)  # 80 m
    assert su.extraire_reference_segment(pts, 0, 8) is None
    assert su.extraire_reference_segment(pts, 3, 3) is None


def test_segment_detecte_dans_une_autre_sortie():
    ref = su.extraire_reference_segment(ligne_droite(44.0, 5.0, 41, 10), 0, 40)["points_reference"]
    # la sortie démarre 300 m plus au sud et passe sur le segment, 1 point/s
    sortie = ligne_droite(44.0 - 300 / 111195.0, 5.0, 101, 10, pas_s=3)
    debut, fin = su.detecter_occurrence(ref, sortie)
    assert distance_m(sortie[debut][0], sortie[debut][1], *ref[0]) <= su.RAYON_TOLERANCE_M
    assert distance_m(sortie[fin][0], sortie[fin][1], *ref[-1]) <= su.RAYON_TOLERANCE_M
    assert su.duree_occurrence_s(sortie, debut, fin) == (fin - debut) * 3


def test_segment_absent_et_duree_inconnue():
    ref = su.extraire_reference_segment(ligne_droite(44.0, 5.0, 41, 10), 0, 40)["points_reference"]
    ailleurs = ligne_droite(45.0, 6.0, 50, 10)
    assert su.detecter_occurrence(ref, ailleurs) is None
    sans_temps = ligne_droite(44.0, 5.0, 41, 10)
    assert su.duree_occurrence_s(sans_temps, 0, 40) is None


# ------------------------------------------------------------------
# Secteurs d'entraînement
# ------------------------------------------------------------------

def trace(nom, lat, lon, distance=10, d_plus=300, date=None, type_="Trail"):
    return {"nom": nom, "point_depart": (lat, lon), "distance_km": distance,
            "denivele_positif": d_plus, "date": date, "type": type_, "points": []}


def test_regroupement_par_proximite():
    traces = [
        trace("Piste du stade", 44.000, 5.000),
        trace("Colline", 44.010, 5.010),     # ~1,4 km : même secteur
        trace("Ventoux", 44.170, 5.280),     # ~29 km : nouveau secteur
    ]
    secteurs = secu.regrouper_en_secteurs(traces)
    assert [len(s["traces"]) for s in secteurs] == [2, 1]
    assert secteurs[0]["centre"] == pytest.approx((44.005, 5.005))


def test_nom_du_secteur():
    repetee = {"traces": [trace("A", 0, 0), trace("B", 0, 0), trace("B", 0, 0)]}
    assert secu._nom_secteur(repetee) == "B"
    unique = {"traces": [trace("Le plus ancien", 0, 0), trace("Autre", 0, 0)]}
    assert secu._nom_secteur(unique) == "Le plus ancien"


def test_stats_et_recommandation_des_secteurs(base_vide):
    c = connecter(base_vide)
    maintenant = datetime.now()
    sorties = [
        # secteur proche : visité hier, profil 10 km / 300 m
        ("Stade", 44.000, 5.000, 10, 300, maintenant - timedelta(days=1)),
        ("Stade", 44.002, 5.001, 10, 300, maintenant - timedelta(days=2)),
        # secteur montagne : pas visité depuis 90 jours, profil 20 km / 1 200 m
        ("Ventoux", 44.170, 5.280, 20, 1200, maintenant - timedelta(days=90)),
    ]
    for nom, lat, lon, dist, dplus, jour in sorties:
        cur = c.execute("INSERT INTO activites (athlete_id, date, nom, type, distance, denivele, duree) "
                        "VALUES (1, ?, ?, 'Trail', ?, ?, 3600)",
                        (jour.strftime("%Y-%m-%d %H:%M:%S"), nom, dist, dplus))
        c.execute("INSERT INTO parcours_gpx (athlete_id, nom, distance_km, denivele_positif, "
                  "denivele_negatif, trace_json, activite_id) VALUES (1, ?, ?, ?, 0, ?, ?)",
                  (nom, dist, dplus, json.dumps([[lat, lon, 300]]), cur.lastrowid))
    c.commit()
    c.close()

    sans_objectif = secu.calculer_stats_secteurs(1)
    assert [s["nom"] for s in sans_objectif] == ["Ventoux", "Stade"]  # le plus « frais » d'abord
    ventoux = sans_objectif[0]
    assert ventoux["score_fraicheur"] == 100 and ventoux["score_profil"] == 100
    stade = sans_objectif[1]
    assert stade["nb_sorties"] == 2 and stade["jours_depuis_visite"] == 1
    assert stade["score_fraicheur"] == 2  # 1 jour / 60 × 100

    # objectif d'une sortie courte et plate : le stade reprend des points de profil
    court = {s["nom"]: s for s in secu.calculer_stats_secteurs(1, distance_visee_km=10, denivele_vise_m=300)}
    assert court["Stade"]["score_profil"] == 100
    assert court["Ventoux"]["score_profil"] == 0  # écart moyen > 100 %


# ------------------------------------------------------------------
# Fichiers FIT (lecture simulée : aucun vrai fichier nécessaire)
# ------------------------------------------------------------------

class FauxMessage:
    def __init__(self, valeurs):
        self.valeurs = valeurs

    def get_value(self, champ):
        if champ not in self.valeurs and getattr(self, "strict", False):
            raise KeyError(champ)
        return self.valeurs.get(champ)


class FauxFit:
    messages = {}

    def __init__(self, chemin):
        if chemin == "illisible.fit":
            raise ValueError("fichier abîmé")

    def get_messages(self, nom):
        return [FauxMessage(v) for v in self.messages.get(nom, [])]


@pytest.fixture
def faux_fit(monkeypatch):
    monkeypatch.setattr(fu, "FitFile", FauxFit)
    FauxFit.messages = {}
    return FauxFit


def semicercles(degres):
    return round(degres / fu.SEMICERCLES_VERS_DEGRES)


def test_fit_points_distance_et_denivele(faux_fit):
    t0 = datetime(2026, 11, 1, 8, 0, 0)
    records = []
    for i in range(11):  # 10 × 100 m vers le nord, +5 m par point puis -2 m
        lat = 44.0 + i * 100 / 111195.0
        alt = 300 + (5 * i if i <= 6 else 30 - 2 * (i - 6))
        records.append({"position_lat": semicercles(lat), "position_long": semicercles(5.0),
                        "enhanced_altitude": alt, "heart_rate": 140 + i, "cadence": 85,
                        "timestamp": t0 + timedelta(seconds=30 * i)})
    records.insert(3, {"position_lat": None, "position_long": None})  # point sans GPS ignoré
    faux_fit.messages = {"record": records}

    r = fu.parser_fit("sortie.fit")
    assert len(r["points"]) == 11
    assert r["distance_km"] == pytest.approx(1.0, abs=0.01)
    assert r["denivele_positif"] == 30 and r["denivele_negatif"] == 8
    assert (r["altitude_min"], r["altitude_max"]) == (300, 330)
    assert r["points"][10][3] == 300.0 and r["points"][10][4] == 150
    assert r["date_debut"] == t0 and r["date_fin"] == t0 + timedelta(seconds=300)


def test_fit_altitude_de_repli_et_fichier_vide(faux_fit):
    faux_fit.messages = {"record": [
        {"position_lat": semicercles(44.0), "position_long": semicercles(5.0), "altitude": 250},
        {"position_lat": semicercles(44.001), "position_long": semicercles(5.0), "altitude": None},
    ]}
    r = fu.parser_fit("x.fit")
    assert [p[2] for p in r["points"]] == [250, 0.0]
    faux_fit.messages = {}
    vide = fu.parser_fit("x.fit")
    assert vide["points"] == [] and vide["distance_km"] == 0.0 and vide["date_debut"] is None


def test_fit_type_de_sport():
    assert fu._type_depuis_sport_fit("running", "trail") == "Trail"
    assert fu._type_depuis_sport_fit("running", "generic") == "Course"
    assert fu._type_depuis_sport_fit("cycling", "mountain") == "VTT"
    assert fu._type_depuis_sport_fit("running", "treadmill") == "Cardio machine"
    assert fu._type_depuis_sport_fit("swimming", None) == "Autre"
    assert fu._type_depuis_sport_fit(None, None) == "Autre"


def test_fit_resume_de_session(faux_fit):
    faux_fit.messages = {"session": [{
        "sport": "running", "sub_sport": "trail", "total_distance": 21097.5,
        "total_timer_time": 7384.6, "total_ascent": 1203.4, "total_descent": 1198.6,
        "avg_heart_rate": 151.4, "max_heart_rate": 178, "total_calories": 1650,
        "avg_cadence": 82, "avg_speed": 2.857, "max_speed": 4.5,
        "start_time": datetime(2026, 10, 4, 7, 30), "timestamp": datetime(2026, 10, 4, 9, 33),
    }]}
    r = fu.parser_resume_session_fit("course.fit")
    assert r["type"] == "Trail"
    assert r["distance_km"] == 21.098 and r["duree_s"] == 7385
    assert (r["denivele_positif"], r["denivele_negatif"]) == (1203, 1199)
    assert (r["fc_moyenne"], r["fc_max"]) == (151, 178)
    assert r["cadence_moyenne"] == 164           # un pied × 2
    assert r["vitesse_moyenne_kmh"] == 10.29 and r["vitesse_max_kmh"] == 16.2


def test_fit_resume_absent_ou_illisible(faux_fit):
    faux_fit.messages = {}
    assert fu.parser_resume_session_fit("suivi_quotidien.fit") == {}
    assert fu.parser_resume_session_fit("illisible.fit") == {}


def test_fit_signaux_de_recuperation_jamais_d_erreur(faux_fit):
    r = fu.extraire_signaux_recuperation("illisible.fit")
    assert r == {"hrv_ms": None, "stress_moyen": None, "date": None}
