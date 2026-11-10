"""LiveTrack coach : liens Garmin, états, rattachement de la sortie, tests de configuration, export/import."""
import json
import sqlite3
from datetime import datetime, timedelta

import pytest

from noyau.donnees import livetrack as D
from noyau.livetrack import regles as R

LIEN = "https://livetrack.garmin.com/session/8a1f0c2e-1b3d-4c5e-9f00-aaaaaaaaaaaa/token/ABCDEF0123456789"


# ------------------------------------------------------------------ règles

def test_lien_valide_et_message_entier():
    assert R.valider_lien(LIEN) == LIEN
    assert R.valider_lien(LIEN.replace("https://", "http://")) == LIEN                  # http passé en https
    msg = f"Suis ma sortie en direct : {LIEN}. À tout à l'heure !"
    assert R.valider_lien(msg) == LIEN and R.extraire_lien(msg) == LIEN
    assert R.valider_lien(f"Mon lien\n{LIEN}") == LIEN


def test_liens_refuses():
    for mauvais in ("", "   ", "pas de lien ici", "https://exemple.com/session/x/token/y",
                    "https://livetrack.garmin.com.pirate.fr/session/x/token/y", "https://livetrack.garmin.com/",
                    "https://livetrack.garmin.com/session", "https://connect.garmin.com/modern/activities"):
        with pytest.raises(R.ErreurLiveTrack):
            R.valider_lien(mauvais)
    assert R.extraire_lien("rien ici https://exemple.com/a") is None
    assert R.valider_lien("https://connect.garmin.com/modern/livetrack/abc").startswith("https://connect.garmin.com/")


def test_lien_masque_court():
    assert R.lien_masque(LIEN).startswith("livetrack.garmin.com/session/") and len(R.lien_masque(LIEN)) < 60


def test_etat_affiche_expire_apres_delai():
    debut = datetime(2026, 11, 10, 9, 0)
    s = {"etat": "en_cours", "debut": debut.isoformat()}
    assert R.etat_affiche(s, debut + timedelta(hours=2))[0] == "en_cours"
    assert R.etat_affiche(s, debut + timedelta(hours=R.DELAI_EXPIRE_PROBABLE_H + 1)) == ("expire", "Expiré probable")
    assert R.etat_affiche({**s, "etat": "termine"}, debut + timedelta(days=9))[0] == "termine"
    assert R.duree_suivi({"debut": debut.isoformat(), "fin": (debut + timedelta(minutes=95)).isoformat()}) == 5700
    assert R.duree_texte(5700) == "1 h 35" and R.duree_texte(1500) == "25 min" and R.duree_texte(None) == ""


def test_activites_candidates_proches_du_suivi():
    s = {"debut": "2026-11-10T09:00:00", "fin": "2026-11-10T11:00:00"}
    acts = [{"id": 1, "date": "2026-11-10T08:55:00"}, {"id": 2, "date": "2026-11-10T09:40:00"},
            {"id": 3, "date": "2026-11-05T09:00:00"}, {"id": 4, "date": "2026-11-10"},
            {"id": 5, "date": "2026-11-13T09:00:00"}, {"id": 6, "date": "n'importe quoi"}]
    ids = [a["id"] for a in R.activites_candidates(s, acts)]
    assert ids[0] == 4 and set(ids) == {1, 2, 4}                    # date seule : comparée au jour ; trop tôt/tard exclus
    assert R.activites_candidates({}, acts) == []


def test_message_au_coureur():
    m = R.modele_message("Léa", "Didier", "Fenix 6 Pro", "sortie longue")
    assert m.startswith("Bonjour Léa,") and "Fenix 6 Pro" in m and "sortie longue" in m and m.endswith("Didier")
    assert all(f"{i}." in m for i in range(1, len(R.ETAPES_COUREUR) + 1))
    assert "Sécurité et suivi" in m and R.modele_message().startswith("Bonjour,")


def test_bilan_du_test_de_configuration():
    tout = {c: True for c in R.CODES_TEST}
    assert "bonne" in R.bilan_test(tout)
    assert "fréquence cardiaque n'apparaît pas" in R.bilan_test({**tout, "fc": False})
    assert "ne s'ouvre pas" in R.bilan_test({**tout, "page_ouvre": False})
    assert "carte" in R.bilan_test({**tout, "carte": False})
    assert R.bilan_test({}) == "Test pas encore fait."
    assert "incomplet" in R.bilan_test({"lien_recu": True, "page_ouvre": True})
    assert R.fc_vue_par_le_test({"fc": True}) == 1 and R.fc_vue_par_le_test({"fc": False}) == 0 and R.fc_vue_par_le_test({}) is None


def test_ligne_du_fil():
    s = {"etat": "termine", "debut": "2026-11-10T09:00:00", "fin": "2026-11-10T10:30:00"}
    assert R.ligne_fil(s, "Léa") == "📡 Léa suivi en direct — terminé (1 h 30)"
    assert "annulé" in R.ligne_fil({**s, "etat": "annule"}, "Léa")


# ------------------------------------------------------------------ données

def ajouter_activite(chemin, date, athlete_id=1, nom="Sortie", empreinte=None):
    c = sqlite3.connect(chemin)
    cur = c.execute("INSERT INTO activites (athlete_id, date, nom, type, distance, duree, empreinte) VALUES (?,?,?,?,?,?,?)",
                    (athlete_id, date, nom, "Trail", 12.3, 4200, empreinte or f"e-{date}-{nom}"))
    c.commit()
    c.close()
    return cur.lastrowid


def test_coureur_creation_modification_suppression(base_vide):
    with pytest.raises(D.ErreurLiveTrack):
        D.creer_coureur({"nom": "  "})
    cid = D.creer_coureur({"nom": "Léa Martin", "montre": "Fenix 6 Pro", "athlete_id": 1})
    D.modifier_coureur(cid, {"nom": "Léa Martin", "montre": "Forerunner 945", "objectif": "UTMB", "athlete_id": 1})
    c = D.coureur(cid)
    assert c["montre"] == "Forerunner 945" and c["objectif"] == "UTMB" and c["athlete_id"] == 1
    assert [x["nom"] for x in D.coureurs()] == ["Léa Martin"]
    D.archiver_coureur(cid)
    assert D.coureurs() == [] and len(D.coureurs(actifs=False)) == 1
    D.archiver_coureur(cid, True)
    D.supprimer_coureur(cid)
    assert D.coureur(cid) is None and D.coureurs(actifs=False) == []
    assert D.athletes_disponibles() == [(1, "Coureur Test")]


def test_suivi_lien_etats_et_remplacement(base_vide):
    cid = D.creer_coureur({"nom": "Léa"})
    with pytest.raises(D.ErreurLiveTrack):
        D.ajouter_suivi(cid, "https://exemple.com/x")
    with pytest.raises(D.ErreurLiveTrack):
        D.ajouter_suivi(999, LIEN)
    s1 = D.ajouter_suivi(cid, f"Voici mon lien {LIEN}", debut="2026-11-10T09:00:00")
    assert D.ajouter_suivi(cid, LIEN) == s1                                              # même lien : pas de doublon
    assert [s["id"] for s in D.suivis_en_cours()] == [s1]
    lien2 = LIEN.replace("ABCDEF", "UVWXYZ")
    s2 = D.ajouter_suivi(cid, lien2, debut="2026-11-10T14:00:00")
    assert D.suivi(s1)["etat"] == "termine" and D.suivi(s1)["fin"] == "2026-11-10T14:00:00"     # le précédent est fermé
    assert D.suivi(s2)["etat"] == "en_cours" and D.coureurs()[0]["nb_suivis"] == 2
    D.terminer_suivi(s2, "2026-11-10T15:30:00")
    assert D.suivi(s2)["duree"] == 5400 and D.suivi(s2)["etat_libelle"] == "Terminé"
    D.reprendre_suivi(s2)
    assert D.suivi(s2)["etat"] == "en_cours" and D.suivi(s2)["fin"] is None
    D.annuler_suivi(s2)
    assert D.suivi(s2)["etat"] == "annule"
    D.noter_suivi(s1, " bien parti ")
    assert D.suivi(s1)["notes"] == "bien parti"
    D.supprimer_suivi(s1)
    assert D.suivi(s1) is None


def test_expire_probable_et_filtre_des_etats(base_vide):
    cid = D.creer_coureur({"nom": "Léa"})
    vieux = (datetime.now() - timedelta(hours=30)).isoformat(timespec="seconds")
    sid = D.ajouter_suivi(cid, LIEN, debut=vieux)
    assert D.suivi(sid)["etat_code"] == "expire" and D.suivis_en_cours() == []
    assert [s["id"] for s in D.suivis(etats=("expire",))] == [sid]


def test_purge_des_liens_apres_la_fin(base_vide):
    cid = D.creer_coureur({"nom": "Léa"})
    ancien = D.ajouter_suivi(cid, LIEN, debut="2026-09-01T09:00:00")
    D.terminer_suivi(ancien, "2026-09-01T10:00:00")
    recent = D.ajouter_suivi(cid, LIEN.replace("ABCDEF", "GHIJKL"), debut="2026-11-09T09:00:00")
    D.terminer_suivi(recent, "2026-11-09T10:00:00")
    now = datetime(2026, 11, 10, 12, 0)
    assert D.nb_liens_a_purger(maintenant=now) == 1
    assert D.purger_liens(maintenant=now) == 1 and D.purger_liens(maintenant=now) == 0
    assert D.suivi(ancien)["lien"] == "" and D.suivi(ancien)["lien_court"] == "(lien effacé)"
    assert D.suivi(recent)["lien"].startswith("https://")                                # l'historique reste, le lien récent aussi
    with pytest.raises(D.ErreurLiveTrack):
        D.reprendre_suivi(ancien)


def test_rattachement_de_la_sortie_et_analyse(base_vide, monkeypatch):
    emis = []
    monkeypatch.setattr(D, "emettre", lambda nom, **kw: emis.append((nom, kw)))
    cid = D.creer_coureur({"nom": "Léa", "athlete_id": 1})
    sid = D.ajouter_suivi(cid, LIEN, debut="2026-11-10T09:00:00")
    bonne = ajouter_activite(base_vide, "2026-11-10T09:05:00", nom="Sortie du matin")
    ajouter_activite(base_vide, "2026-10-01T09:05:00", nom="Trop ancienne")
    autre_ath = ajouter_activite(base_vide, "2026-11-10T09:05:00", athlete_id=None, nom="Autre", empreinte="x")
    cand = D.activites_candidates(sid)
    assert [a["id"] for a in cand] == [bonne] and autre_ath not in [a["id"] for a in cand]
    D.rattacher_activite(sid, bonne)
    s = D.suivi(sid)
    assert s["activite_id"] == bonne and s["etat"] == "termine" and s["fin"]
    assert emis and emis[0][0] == "donnees_modifiees" and emis[0][1] == {"athlete_id": 1}   # analyses automatiques réveillées
    assert D.suivi_de_activite(bonne)["coureur_nom"] == "Léa" and D.suivi_de_activite(999) is None
    assert D.analyse_de_la_sortie(sid) is None
    c = sqlite3.connect(base_vide)
    c.execute("INSERT INTO analyses_ia (athlete_id, activite_id, contenu) VALUES (1, ?, 'Belle sortie régulière.')", (bonne,))
    c.commit()
    c.close()
    assert D.analyse_de_la_sortie(sid) == "Belle sortie régulière."
    assert D.suivis()[0]["sortie_nom"] == "Sortie du matin"
    # une sortie ne peut servir qu'à un suivi
    sid2 = D.ajouter_suivi(cid, LIEN.replace("ABCDEF", "ZZZ"), debut="2026-11-10T09:30:00")
    with pytest.raises(D.ErreurLiveTrack):
        D.rattacher_activite(sid2, bonne)
    assert bonne not in [a["id"] for a in D.activites_candidates(sid2)]
    D.detacher_activite(sid)
    assert D.suivi(sid)["activite_id"] is None
    with pytest.raises(D.ErreurLiveTrack):
        D.rattacher_activite(sid, 12345)


def test_sans_profil_lie_pas_de_candidats(base_vide):
    cid = D.creer_coureur({"nom": "Externe"})
    sid = D.ajouter_suivi(cid, LIEN)
    assert D.activites_candidates(sid) == [] and D.seances_prevues(None) == []


def test_seance_prevue_et_choix(base_vide):
    c = sqlite3.connect(base_vide)
    cur = c.execute("INSERT INTO seances_structurees (athlete_id, nom, date_prevue) VALUES (1, 'Sortie longue', '2026-11-10')")
    sid_seance = cur.lastrowid
    c.execute("INSERT INTO seances_structurees (athlete_id, nom, date_prevue) VALUES (1, 'Plus tard', '2026-12-25')")
    c.commit()
    c.close()
    cid = D.creer_coureur({"nom": "Léa", "athlete_id": 1})
    sv = D.ajouter_suivi(cid, LIEN, debut="2026-11-10T09:00:00")
    prevues = D.seances_prevues(1, datetime(2026, 11, 10, 9))
    assert [p["nom"] for p in prevues] == ["Sortie longue"]
    D.choisir_seance(sv, sid_seance)
    assert D.suivi(sv)["seance_id"] == sid_seance
    D.choisir_seance(sv, None)
    assert D.suivi(sv)["seance_id"] is None


def test_test_de_configuration_et_fc(base_vide):
    cid = D.creer_coureur({"nom": "Léa"})
    sid = D.ajouter_suivi(cid, LIEN)
    assert D.dernier_test(cid) is None
    complet = {c: True for c in R.CODES_TEST}
    tid, bilan = D.enregistrer_test(cid, {**complet, "fc": False}, "FC absente de la page")
    assert "fréquence cardiaque n'apparaît pas" in bilan
    assert D.suivi(sid)["fc_visible"] == 0                                    # retenu sur le suivi en cours
    D.enregistrer_test(cid, complet)
    assert D.suivi(sid)["fc_visible"] == 1
    t = D.tests(cid)
    assert len(t) == 2 and t[0]["resultats"]["fc"] is True and "bonne" in t[0]["bilan"]
    assert D.dernier_test(cid)["id"] == t[0]["id"]
    D.definir_fc_visible(sid, None)
    assert D.suivi(sid)["fc_visible"] is None
    with pytest.raises(D.ErreurLiveTrack):
        D.enregistrer_test(999, complet)


def test_lignes_du_fil(base_vide):
    cid = D.creer_coureur({"nom": "Léa"})
    s1 = D.ajouter_suivi(cid, LIEN, debut="2026-11-09T09:00:00")
    D.terminer_suivi(s1, "2026-11-09T10:00:00")
    s2 = D.ajouter_suivi(cid, LIEN.replace("ABCDEF", "Q"), debut="2026-11-10T09:00:00")
    D.annuler_suivi(s2)
    assert [t for _d, t in D.lignes_fil()] == ["📡 Léa suivi en direct — terminé (1 h 00)"]


def test_export_import_sans_doublon(base_vide, tmp_path, monkeypatch):
    cid = D.creer_coureur({"nom": "Léa", "montre": "Fenix 6 Pro", "athlete_id": 1})
    sid = D.ajouter_suivi(cid, LIEN, debut="2026-11-10T09:00:00")
    D.terminer_suivi(sid, "2026-11-10T10:00:00")
    D.enregistrer_test(cid, {c: True for c in R.CODES_TEST})
    texte = D.exporter_json()
    export = json.loads(texte)
    assert export["module"] == "livetrack_coach" and export["coureurs"][0]["profil"] == "Coureur Test"
    assert "athlete_id" not in export["coureurs"][0] and "activite_id" not in export["suivis"][0]
    assert D.importer(texte) == {"coureurs": 0, "suivis": 0, "tests": 0}               # rien n'est doublé
    # sur une autre base : tout arrive, les profils sont retrouvés par leur nom
    import data.database as db
    autre = tmp_path / "autre.db"
    monkeypatch.setattr(db, "CHEMIN_BDD", autre)
    db.creer_base_de_donnees()
    c = sqlite3.connect(autre)
    c.execute("INSERT INTO athletes (id, nom, prenom) VALUES (7, 'Test', 'Coureur')")
    c.commit()
    c.close()
    assert D.importer(texte) == {"coureurs": 1, "suivis": 1, "tests": 1}
    assert D.coureurs()[0]["athlete_id"] == 7 and D.suivis()[0]["etat"] == "termine"
    assert D.importer(export) == {"coureurs": 0, "suivis": 0, "tests": 0}
    for faux in ("pas du json", json.dumps({"module": "autre"}), "[]"):
        with pytest.raises(D.ErreurLiveTrack):
            D.importer(faux)


def test_la_page_claude_connait_les_memes_adresses_garmin():
    from pathlib import Path
    page = (Path(__file__).resolve().parent.parent / "page_claude" / "trail_hub_center.html").read_text(encoding="utf-8")
    assert "htmlLiveTrack" in page and "livetrack_suivis" in page
    motifs = {"livetrack.garmin.com": r"livetrack\.garmin\.com", "connect.garmin.com": r"connect\.garmin\.(com|cn)",
              "connect.garmin.cn": r"connect\.garmin\.(com|cn)"}
    assert set(motifs) == set(R.HOTES_GARMIN), "une adresse Garmin a changé : mets la page Claude à jour aussi"
    for hote in R.HOTES_GARMIN:
        assert motifs[hote] in page, hote
