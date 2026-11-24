"""Connecteurs Claude : format du paquet, import sans doublon, demandes, pont (dossier partagé)."""
import json
from datetime import date, datetime, timedelta

import pytest

from noyau.connecteurs import regles as R
from noyau.connecteurs import importer as I
from noyau.connecteurs import pont as P
from noyau.donnees import connecteurs as D
from noyau.donnees import base


def paquet(**sections):
    p = {"format": "trailhub-connecteurs", "version": 1, "cree_le": "2026-11-24T05:50:00"}
    p.update(sections)
    return p


TRAIL = {"source": "strava", "id_externe": "21074893881", "date": "2026-11-21T18:32:06",
         "nom": "Trail nocturne de Bonnieux", "sport": "TrailRun", "distance_m": 12143.8, "duree_s": 5117,
         "denivele_m": 490, "vitesse_moy_ms": 2.3475, "vitesse_max_ms": 4.9, "fc_moy": 167, "fc_max": 188,
         "calories": 1124, "cadence": 77.6, "effort_relatif": 288, "materiel_id": "30735136", "lieu": "Bonnieux, France"}


# ------------------------------------------------------------------ règles

def test_paquet_refuse_si_mauvais_format():
    for mauvais in ("pas du json", json.dumps({"format": "autre"}), {"format": "trailhub-connecteurs", "version": 9}):
        with pytest.raises(R.ErreurConnecteurs):
            R.lire_paquet(mauvais)


def test_activite_normalisee():
    a = R.normaliser_activite(TRAIL)
    assert a["type"] == "Trail" and a["distance"] == 12.144 and a["denivele"] == 490 and a["duree"] == 5117
    assert a["date"] == "2026-11-21 18:32:06" and a["cadence_moyenne"] == 155.2        # cadence doublée en course
    assert abs(a["allure_moyenne"] - 7.1) < 0.01 and a["vitesse_moyenne"] == 8.45
    assert R.normaliser_activite({"source": "inconnue", "id_externe": "1", "date": "2026-11-21"}) is None
    assert R.normaliser_activite({"source": "garmin", "id_externe": "1", "date": "pas une date"}) is None
    assert R.type_sport("TRACK_RUNNING") == "Course" and R.type_sport("MountainBikeRide") == "VTT"


def test_sante_filtre_les_valeurs_absurdes():
    s = R.normaliser_sante({"date": "2026-11-23", "sommeil_duree_h": 7.25, "hrv_nuit_ms": 900, "fc_repos": 52})
    assert s["mesures"] == {"sommeil_duree_h": 7.25, "fc_repos": 52}
    assert R.normaliser_sante({"date": "2026-11-23"}) is None


def test_zone_acwr():
    assert R.zone_acwr(1.0)[0] == "optimal" and R.zone_acwr(1.38)[0] == "eleve"
    assert R.zone_acwr(1.7)[0] == "danger" and R.zone_acwr(0.5)[0] == "bas" and R.zone_acwr(None)[0] == "inconnu"
    assert R.normaliser_charge({"aigue": 164, "chronique": 119})["acwr"] == 1.38


def test_usure_chaussure():
    assert R.usure_chaussure(264789)["km"] == 264.8 and R.usure_chaussure(264789)["etat"] == "Bon état"
    assert R.usure_chaussure(650000)["etat"] == "Bientôt à changer" and R.usure_chaussure(750000)["etat"] == "À changer"


def test_agenda_fatigue_et_creneaux():
    evts = [{"debut": "2026-11-25T07:00:00", "fin": "2026-11-25T12:00:00"},
            {"debut": "2026-11-25T13:00:00", "fin": "2026-11-25T18:30:00"},
            {"debut": "2026-11-25T00:00:00", "fin": "2026-11-26T00:00:00", "journee": True},
            {"debut": "2026-11-26T09:00:00", "fin": "2026-11-26T10:00:00"}]
    h = R.charge_agenda_par_jour(evts)
    assert h == {"2026-11-25": 10.5, "2026-11-26": 1.0}
    assert R.fatigue_agenda(10.5) == 1 and R.fatigue_agenda(11) == 2 and R.fatigue_agenda(1) == 0
    assert R.creneaux_libres(evts, "2026-11-25") == [("06:00", "07:00"), ("12:00", "13:00"), ("18:30", "21:00")]


def test_seance_vers_running_workout_avec_repetitions():
    etapes = [{"type": "Échauffement", "mode": "temps", "valeur": 15},
              {"type": "Effort", "mode": "distance", "valeur": 0.4, "allure_cible": "4:30"},
              {"type": "Récupération", "mode": "temps", "valeur": 1.5},
              {"type": "Effort", "mode": "distance", "valeur": 0.4, "allure_cible": "4:30"},
              {"type": "Récupération", "mode": "temps", "valeur": 1.5},
              {"type": "Effort", "mode": "distance", "valeur": 0.4, "allure_cible": "4:30"},
              {"type": "Récupération", "mode": "temps", "valeur": 1.5},
              {"type": "Retour au calme", "mode": "temps", "valeur": 10, "fc_cible": 130}]
    w = R.seance_vers_running_workout("3 x 400 m", etapes)
    pas = w["segments"][0]["steps"]
    assert w["sport"] == "RUNNING" and [p["type"] for p in pas] == ["WorkoutStep", "WorkoutRepeatStep", "WorkoutStep"]
    assert pas[0] == {"type": "WorkoutStep", "intensity": "WARMUP", "durationType": "TIME", "durationValue": 900,
                      "targetType": "OPEN"}
    rep = pas[1]
    assert rep["repeatValue"] == 3 and rep["steps"][0]["durationType"] == "DISTANCE" and rep["steps"][0]["durationValue"] == 400
    assert rep["steps"][0]["targetType"] == "PACE" and rep["steps"][0]["targetValueLow"] < 1000 / 270 < rep["steps"][0]["targetValueHigh"]
    assert rep["steps"][1]["intensity"] == "RECOVERY" and pas[2]["targetType"] == "HEART_RATE"
    assert R.duree_seance_min(etapes) == 35          # 15 + 3 × (1,8 + 1,5) + 10
    with pytest.raises(R.ErreurConnecteurs):
        R.seance_vers_running_workout("vide", [])


def test_prompt_playlist():
    p = R.prompt_playlist("Sortie longue", 95)
    assert p.startswith("Crée une playlist de 95 minutes") and "funk" in p and "Sortie longue" in p


# ------------------------------------------------------------------ import

def test_import_complet_et_sans_doublon(base_vide):
    p = paquet(activites=[TRAIL], sante=[{"date": "2026-11-23", "sommeil_duree_h": 7.2, "sommeil_score": 80,
                                         "hrv_nuit_ms": 45, "fc_repos": 52, "pas": 9000}],
               records=[{"sport": "Run", "type": "Fastest5k", "valeur": 1610, "unite": "seconds", "date": "2026-11-23"}],
               materiel=[{"id": "30735136", "type": "Shoe", "marque": "HOKA", "modele": "mafate 5", "distance_m": 264789}],
               charge={"date": "2026-11-24", "aigue": 164, "chronique": 119, "acwr": 1.38},
               agenda=[{"cle": "e1", "titre": "Réunion chantier", "debut": "2026-11-25T08:00:00",
                        "fin": "2026-11-25T18:00:00"}],
               courses_mail=[{"nom": "Trail des Dentelles", "date": "2027-03-14", "lieu": "Gigondas", "distance_km": 23,
                              "lien": "javascript:alert(1)"}],
               parcours=[{"source": "AllTrails", "id": "123", "nom": "Boucle du Luberon", "distance_m": 14000,
                          "denivele_m": 600, "lien": "https://www.alltrails.com/fr/x"}],
               securite=[{"trajet": "Isle-sur-la-Sorgue → Mont Ventoux", "date": "2026-11-24", "niveau": "vigilance",
                          "resume": "Neige au sommet"}],
               playlists=[{"nom": "Fractionné funk", "lien": "https://open.spotify.com/playlist/x", "duree_min": 45}],
               analyses=[{"id_externe": "21074893881", "texte": "Belle course de nuit."}],
               bilan_semaine="Semaine chargée : 3 sorties.")
    b = I.importer(p, 1, fichier="trailhub-connecteurs-test.json")
    assert b["activites_nouvelles"] == 1 and b["sante_jours"] == 1 and b["records"] == 1 and b["materiel"] == 1
    assert b["courses"] == 1 and b["agenda"] == 1 and b["parcours"] == 1 and b["securite"] == 1
    assert b["playlists"] == 1 and b["analyses"] == 1 and b["charge"] == 1.38

    act = base.lire_un("SELECT type, distance, source, identifiant_externe, cadence_moyenne FROM activites")
    assert act == ("Trail", 12.144, "Strava (connecteur)", "21074893881", 155.2)
    assert base.lire_un("SELECT fc_repos, hrv_nuit_ms FROM recuperation_quotidienne WHERE date='2026-11-23'") == (52, 45.0)
    assert base.lire_un("SELECT pas FROM garmin_quotidien WHERE date='2026-11-23'") == (9000,)
    assert base.lire_un("SELECT lien, source FROM courses_calendrier") == (None, "Gmail (connecteur)")   # lien non https refusé
    assert base.lire_un("SELECT contenu FROM analyses_ia")[0].startswith(I.PREFIXE_ANALYSE)
    m = D.materiel_strava(1)
    assert m[0]["nom"] == "HOKA mafate 5" and m[0]["km"] == 264.8 and m[0]["usure"]["etat"] == "Bon état"
    assert D.derniere_charge(1)["zone"] == "eleve" and D.records(1)[0]["texte"] == "26 min 50 s"
    assert D.bilan_semaine()["texte"].startswith("Semaine chargée")

    # même paquet : ignoré ; autre paquet avec la même sortie : complétée, pas dupliquée
    assert I.importer(p, 1)["deja"] is True
    p2 = paquet(cree_le="2026-11-25T05:50:00", activites=[{**TRAIL, "fc_moy": 167},
                                                          {**TRAIL, "id_externe": "autre", "source": "garmin",
                                                           "date": "2026-11-21T18:35:00"}],
                materiel=[{"id": "30735136", "type": "Shoe", "marque": "HOKA", "modele": "mafate 5", "distance_m": 300000}])
    b2 = I.importer(p2, 1)
    assert b2["activites_nouvelles"] == 0 and base.lire_un("SELECT COUNT(*) FROM activites")[0] == 1
    assert D.materiel_strava(1)[0]["km"] == 300.0 and base.lire_un("SELECT COUNT(*) FROM materiel")[0] == 1
    assert len(I.journal()) == 2


def test_import_sans_coureur_refuse(base_vide):
    with pytest.raises(R.ErreurConnecteurs):
        I.importer(paquet(), None)


def test_fatigue_agenda_depuis_la_base(base_vide):
    demain = (date.today() + timedelta(days=1)).isoformat()
    I.importer(paquet(agenda=[{"cle": "a", "titre": "Chantier", "debut": f"{demain}T07:00:00", "fin": f"{demain}T18:00:00"}]), 1)
    f = D.fatigue_par_jour(1, jours=3)
    assert f[1]["jour"] == demain and f[1]["heures"] == 11 and f[1]["bonus"] == 2 and f[0]["bonus"] == 0


# ------------------------------------------------------------------ demandes et pont

def test_demandes_cycle_complet(base_vide, tmp_path):
    base.ecrire("INSERT INTO seances_structurees (athlete_id, nom, type_seance, date_prevue, etapes_json) VALUES (?,?,?,?,?)",
                (1, "Footing", "Endurance", date.today().isoformat(),
                 json.dumps([{"type": "Effort", "mode": "temps", "valeur": 40}])))
    s = D.seances_prevues(1)[0]
    assert s["duree_min"] == 40
    c1 = D.demander_seance_montre(1, s)
    c2 = D.demander_playlist(1, "Footing", 40)
    c3 = D.demander_agenda(1, "Footing", f"{date.today()}T18:00", f"{date.today()}T18:45")
    D.demander_parcours(1, "L'Isle-sur-la-Sorgue", 43.919, 5.051, distance_km=15, denivele_m=500)
    D.demander_securite(1, "L'Isle-sur-la-Sorgue", "Mont Ventoux")
    with pytest.raises(R.ErreurConnecteurs):
        D.demander_agenda(1, "x", "2026-11-25T10:00", "2026-11-25T09:00")
    D.annuler_demande(c3)

    P.definir_dossier(str(tmp_path))
    P.definir_athlete(1)
    res = P.passage()
    assert res["demandes"] == 4 and not res["erreurs"]
    f = json.loads((tmp_path / R.FICHIER_DEMANDES).read_text(encoding="utf-8"))
    assert f["format"] == "trailhub-demandes" and [d["type"] for d in f["demandes"]][:2] == ["seance_montre", "playlist"]
    assert f["demandes"][0]["parametres"]["workout"]["sport"] == "RUNNING"
    assert {d["statut"] for d in D.demandes(("envoyee",))} == {"envoyee"}

    # Claude répond dans le paquet suivant, déposé dans le dossier
    (tmp_path / "trailhub-connecteurs-2026-11-25-0550.json").write_text(json.dumps(paquet(
        demandes_traitees=[{"cle": c1, "statut": "fait", "message": "Séance envoyée sur la Fenix"},
                           {"cle": c2, "statut": "fait", "lien": "https://open.spotify.com/playlist/y"}])), encoding="utf-8")
    (tmp_path / "trailhub-connecteurs-abime.json").write_text("{", encoding="utf-8")
    res = P.passage()
    assert len(res["importes"]) == 1 and len(res["erreurs"]) == 1 and res["demandes"] == 2
    faits = {d["cle"]: d for d in D.demandes(("fait",))}
    assert set(faits) == {c1, c2} and faits[c2]["lien"].startswith("https://open.spotify.com")
    assert "Aucun nouveau paquet" in P.texte_passage(P.passage())


def test_pont_sans_dossier(base_vide):
    P.definir_dossier("")
    assert P.passage()["dossier"] is None and P.texte_passage(P.passage()).startswith("Aucun dossier")
    with pytest.raises(R.ErreurConnecteurs):
        P.definir_dossier("/chemin/qui/n/existe/pas")


# ------------------------------------------------------------------ écran

def test_ecran_connecteurs(base_vide, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QApplication, QMessageBox
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: None)
    from interface import connecteurs as E
    from noyau import modules as M
    assert M.module_de_l_ecran("ouvrir_connecteurs") == "connecteurs" and M.est_actif("connecteurs")
    I.importer(paquet(activites=[TRAIL], charge={"aigue": 164, "chronique": 119},
                      materiel=[{"id": "1", "type": "Shoe", "nom": "HOKA mafate 5", "distance_m": 264789}],
                      records=[{"sport": "Run", "type": "Fastest5k", "valeur": 1610, "unite": "seconds"}],
                      parcours=[{"id": "9", "nom": "Boucle", "distance_m": 9000, "lien": "https://www.alltrails.com/x"}]), 1)
    base.ecrire("INSERT INTO seances_structurees (athlete_id, nom, date_prevue, etapes_json) VALUES (1,'Footing',?,?)",
                (date.today().isoformat(), json.dumps([{"type": "Effort", "mode": "temps", "valeur": 45}])))
    P.definir_dossier(str(tmp_path))
    f = E.ConnecteursFenetre(athlete_id_initial=1)
    assert f.recu.t_records.rowCount() == 1 and f.recu.t_mat.rowCount() == 1 and f.recu.t_sorties.rowCount() == 1
    assert f.recu.c_charge.valeur.text() == "1,38" and f.recu.t_agenda.rowCount() == 14
    assert f.parcours.t_parcours.rowCount() == 1
    f.parcours.t_parcours.selectRow(0)
    f.parcours._favori()
    assert D.parcours(1)[0]["favori"] == 1
    d = f.demandes
    assert d.t_seances.rowCount() == 1
    d.t_seances.selectRow(0)
    assert d._montre() and d._playlist()
    assert d.t_dem.rowCount() == 2 and (tmp_path / R.FICHIER_DEMANDES).exists()
    f.pont.rafraichir()
    assert f.pont.table.rowCount() == 1 and f.pont.chemin.text() == str(tmp_path)
    f.close()
