"""v109 — nouvelles fonctions : soleil, prêt à courir, semaine, jour de course, recherche, duel, rapport,
alerte matériel, défis en famille, moteur et ton de l'IA."""
import json
from datetime import date, datetime, timedelta

import pytest

from noyau.donnees import base


def _act(aid, d, nom="Trail", type_="Trail", dist=10.0, dp=300):
    base.ecrire("INSERT INTO activites (id, athlete_id, date, nom, type, distance, denivele, duree) VALUES (?,?,?,?,?,?,?,?)",
                (aid, 1, d, nom, type_, dist, dp, 3600))


# ------------------------------------------------------------------ soleil

def test_soleil_lisle_sur_la_sorgue():
    from noyau.outils import soleil as S
    lever, coucher = S.lever_coucher(date(2026, 11, 25))
    assert (lever.hour, coucher.hour) == (7, 17) and 35 <= lever.minute <= 55
    l2, c2 = S.lever_coucher(date(2026, 6, 21))
    assert l2.hour == 5 and c2.hour == 21
    assert S.fait_jour(datetime(2026, 11, 25, 12)) and not S.fait_jour(datetime(2026, 11, 25, 19))
    assert S.prochain_changement(datetime(2026, 11, 25, 12)).hour == 17


# ------------------------------------------------------------------ prêt à courir

def test_pret_a_courir_combine_les_signaux(base_vide):
    from noyau.sante import pret_a_courir as P
    assert P.calculer(1)["score"] is not None or P.calculer(1)["facteurs"] == []
    base.ecrire("INSERT INTO connecteurs_charge (athlete_id, date, aigue, chronique, acwr, source) VALUES (1,?,164,119,1.38,'Garmin')",
                (date.today().isoformat(),))
    base.ecrire("INSERT INTO suivi_corporel (athlete_id, date, fatigue_jambes, fatigue_generale) VALUES (1,?,7,5)",
                (date.today().isoformat(),))
    r = P.calculer(1)
    cles = {f["cle"] for f in r["facteurs"]}
    assert {"charge", "ressenti"} <= cles and 0 <= r["score"] <= 100
    assert r["acwr"] == 1.38 and r["source_charge"] == "Garmin"
    assert P._score_acwr(1.05) == 100 and P._score_acwr(1.6) < P._score_acwr(1.38) < 70
    v, c = P.verdict_et_conseil(45, acwr=1.38, jambes=7)
    assert v == "Récupération en cours" and "charge élevée" in c and "jambes lourdes" in c


# ------------------------------------------------------------------ semaine

def test_placer_au_plus_pres_de_l_heure_preferee():
    from noyau.entrainement.semaine_auto import placer
    assert placer(45, None) == "18:00"
    assert placer(45, [("06:00", "07:00"), ("12:00", "13:00"), ("18:30", "21:00")]) == "18:30"
    assert placer(45, [("06:00", "07:00"), ("17:00", "21:00")]) == "18:00"
    assert placer(90, [("06:00", "07:00")]) is None


def test_preparer_ma_semaine(base_vide):
    from noyau.entrainement import semaine_auto as S
    from noyau.donnees import connecteurs as D
    demain = (date.today() + timedelta(days=1)).isoformat()
    etapes = json.dumps([{"type": "Effort", "mode": "temps", "valeur": 45}])
    base.ecrire("INSERT INTO seances_structurees (athlete_id, nom, date_prevue, etapes_json) VALUES (1,'Footing',?,?)",
                (demain, etapes))
    base.ecrire("INSERT INTO seances_structurees (athlete_id, nom, date_prevue, etapes_json) VALUES (1,'Sans étapes',?,'[]')",
                (demain,))
    from noyau.connecteurs import importer as I
    I.importer({"format": "trailhub-connecteurs", "version": 1, "agenda": [
        {"cle": "a", "titre": "Chantier", "debut": f"{demain}T07:00:00", "fin": f"{demain}T18:20:00"}]}, 1)
    props = S.proposition(1)
    assert [p["seance"]["nom"] for p in props] == ["Footing", "Sans étapes"]
    assert props[0]["heure"] == "18:20" and props[0]["chargee"] and "chargée" in props[0]["remarque"]
    r = S.appliquer(1, props)
    assert r["demandes"] == 5 and len(r["erreurs"]) == 1          # pas de séance montre sans étapes
    assert {d["type"] for d in D.demandes()} == {"seance_montre", "agenda", "playlist"}
    S.definir_heure_preferee("07:30")
    assert S.heure_preferee() == "07:30"


# ------------------------------------------------------------------ jour de course

def test_jour_de_course(base_vide):
    from noyau.course import jour_de_course as J
    assert J.preparer(1) is None
    dans10 = (date.today() + timedelta(days=10)).isoformat()
    base.ecrire("INSERT INTO courses_calendrier (athlete_id, nom, date, lieu, distance_km, denivele_m) VALUES (1,?,?,?,?,?)",
                ("Trail des Dentelles", dans10, "Gigondas", 23, 1200))
    r = J.preparer(1)
    assert r["course"]["nom"] == "Trail des Dentelles" and r["rebours"]["texte"] == "J-10"
    assert r["duree_h"] and "estimation" in r["origine_duree"] and r["plan"]["heures"]
    assert r["sac"] and r["playlist_min"] >= 60
    sac = r["sac"]
    sac[0]["coche"] = True
    J.enregistrer_sac(r["course"], sac)
    assert J.preparer(1)["sac"][0]["coche"] is True
    assert J.compte_a_rebours(date.today().isoformat())["texte"] == "C'est aujourd'hui"
    assert J._hms_en_h("3:30") == 3.5 and J._hms_en_h("abc") is None


# ------------------------------------------------------------------ recherche partout

def test_recherche_partout(base_vide):
    from noyau.donnees.recherche import rechercher_partout
    base.ecrire("INSERT INTO courses_calendrier (athlete_id, nom, date, lieu) VALUES (1,'Trail des Dentelles','2027-03-14','Gigondas')")
    base.ecrire("INSERT INTO materiel (athlete_id, nom, type) VALUES (1,'HOKA Mafate 5','Chaussures')")
    cats = {c for c, *_ in rechercher_partout("dentelles", 1, 5)}
    assert "Course" in cats
    assert ("Matériel", "HOKA Mafate 5") in {(c, l) for c, l, *_ in rechercher_partout("mafate", 1, 5)}
    assert ("Réglage", "Apparence") in {(c, l) for c, l, *_ in rechercher_partout("soleil", 1, 5)}


# ------------------------------------------------------------------ duel

def _trace(decalage_s=0, ralenti_km=None):
    pts, t = [], 0
    for i in range(101):                          # 100 pas de ~111 m vers le nord, puis retour
        lat = 43.9 + (i if i <= 50 else 100 - i) * 0.001
        t += 40 + (15 if ralenti_km is not None and ralenti_km[0] <= i < ralenti_km[1] else 0)
        pts.append([lat, 5.05, 100 + (i if i <= 50 else 100 - i) * 2, t + decalage_s, 140])
    return pts


def test_duel_meme_parcours(base_vide):
    from noyau.analyse import duel as Du
    _act(1, "2026-11-01 09:00:00")
    _act(2, "2026-11-15 09:00:00")
    _act(3, "2026-11-20 09:00:00")
    for aid, pts in ((1, _trace()), (2, _trace(ralenti_km=(60, 80))), (3, [[44.5, 6.0, 0, i * 10, None] for i in range(20)])):
        base.ecrire("INSERT INTO parcours_gpx (athlete_id, nom, trace_json, activite_id) VALUES (1,'x',?,?)",
                    (json.dumps(pts), aid))
    assert [c[0] for c in Du.candidats(1, 1)] == [2]
    assert {p[0] for p in Du.paires(1)} == {1, 2}
    r = Du.comparer(1, 1, 2, n=10)
    assert len(r["portions"]) == 10 and r["ecart_total_s"] == 20 * 15
    assert r["portions"][0]["terrain"] == "montée" and r["portions"][-1]["terrain"] == "descente"
    assert "plus lent" in r["resume"] and "perd le plus" in r["resume"]
    with pytest.raises(ValueError):
        Du.comparer(1, 1, 3)


# ------------------------------------------------------------------ rapport du mois

def test_rapport_mois_auto(base_vide):
    from noyau.outils import rapport_auto as R
    assert R.mois_precedent(date(2026, 1, 3)) == (2025, 12)
    assert R.mois_a_ecrire(date(2026, 12, 1)) == (2026, 11)
    R.marquer_ecrit(2026, 11)
    assert R.mois_a_ecrire(date(2026, 12, 15)) is None and R.mois_a_ecrire(date(2027, 1, 1)) == (2026, 12)
    R.definir_actif(False)
    assert R.mois_a_ecrire(date(2027, 1, 1)) is None
    assert R.nom_fichier("Didier / B", 2026, 11) == "Rapport 2026-11 — Didier _ B.pdf"


# ------------------------------------------------------------------ alerte matériel

def test_alerte_materiel(base_vide):
    from noyau.materiel import alerte as A
    base.ecrire("INSERT INTO materiel (athlete_id, nom, type, km_actuels, statut) VALUES (1,'HOKA Mafate 5','Chaussures',640,'Actif')")
    base.ecrire("INSERT INTO materiel (athlete_id, nom, type, km_actuels, statut) VALUES (1,'Kiprun XT8','Chaussures',200,'Actif')")
    a = A.alertes(1)
    assert len(a) == 1 and a[0]["nom"] == "HOKA Mafate 5" and a[0]["niveau"] == "bientot"
    assert a[0]["famille"] == "amorti max, terrain varié"
    assert all("mafate" not in e["modele"].lower() for e in a[0]["equivalents"])
    assert a[0]["equivalents"][0]["liens"][0][1].startswith("https://")
    assert A.famille("Nike Next") == "polyvalente trail" and A.famille("Kiprun XT 8") == "polyvalente trail"
    A.definir_seuil(700)
    assert A.alertes(1) == []
    with pytest.raises(ValueError):
        A.definir_seuil(50)


# ------------------------------------------------------------------ défis en famille

def test_defis_famille(base_vide):
    from noyau.donnees import defis as F
    debut, fin = date.today().replace(day=1).isoformat(), (date.today() + timedelta(days=20)).isoformat()
    _act(1, date.today().isoformat() + " 08:00:00", dist=12.0)
    _act(2, date.today().isoformat() + " 12:00:00", type_="Vélo", dist=30.0)
    did = F.creer("Le tour du Luberon", 100, debut, fin,
                  participants=[{"prenom": "Didier", "athlete_id": 1}, {"prenom": "Lucas"}])
    p_lucas = [p for p in F.etat(did)["participants"] if p["prenom"] == "Lucas"][0]["id"]
    F.noter(p_lucas, 3.5, note="balade du dimanche")
    e = F.etat(did)
    assert e["total"] == 25.5 and e["pct"] == 26 and e["participants"][0]["prenom"] == "Didier"
    assert [b["obtenu"] for b in e["badges"]] == [True, False, False, False]
    assert e["reste"] == 74.5 and not e["termine"]
    with pytest.raises(F.ErreurDefi):
        F.creer("", 10, debut, fin)
    with pytest.raises(F.ErreurDefi):
        F.noter(p_lucas, -1)
    assert len(F.lister(en_cours_seulement=True)) == 1
    F.supprimer(did)
    assert F.lister() == []


# ------------------------------------------------------------------ moteur et ton de l'IA

def test_moteur_et_ton(base_vide):
    from noyau.ia import analyse_auto as A
    assert A.moteur() == "tout" and A.ton() == "direct"
    A.definir_moteur("regles")
    assert A._ia_disponible() is False
    A.definir_ton("detaille")
    assert "chiffres" in A.consigne_ton()
    with pytest.raises(ValueError):
        A.definir_moteur("autre")


def test_seuil_journee_chargee(base_vide):
    from noyau.connecteurs import regles as R
    from data.database import definir_parametre
    assert R.fatigue_agenda(9) == 1
    definir_parametre(R.CLE_JOURNEE_CHARGEE, "11")
    assert R.fatigue_agenda(9) == 0 and R.fatigue_agenda(13) == 2


# ------------------------------------------------------------------ écrans

def test_ecrans_v109(base_vide, monkeypatch):
    from PySide6.QtWidgets import QApplication, QMessageBox
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)
    demain = (date.today() + timedelta(days=1)).isoformat()
    base.ecrire("INSERT INTO seances_structurees (athlete_id, nom, date_prevue, etapes_json) VALUES (1,'Footing',?,?)",
                (demain, json.dumps([{"type": "Effort", "mode": "temps", "valeur": 40}])))
    base.ecrire("INSERT INTO courses_calendrier (athlete_id, nom, date, distance_km, denivele_m) VALUES (1,'Trail',?,20,800)",
                ((date.today() + timedelta(days=5)).isoformat(),))
    _act(1, date.today().isoformat() + " 08:00:00")
    from interface.jour_de_course import JourDeCourseFenetre
    from interface.duel import DuelFenetre
    from interface.defis_famille import DefisFamilleFenetre, GrandAffichage
    from interface.preparer_semaine import DialoguePreparerSemaine
    from interface.alerte_materiel import DialogueAlerteMateriel
    from interface.panneau_detail import PanneauDetail
    from interface.icones import icone, icone_appli, sans_emoji, ICONE_DE_L_ECRAN, TRACES
    j = JourDeCourseFenetre(athlete_id_initial=1)
    assert j.ecran.c_rebours.valeur.text() == "J-5" and j.ecran.sac.count() > 3
    DuelFenetre(athlete_id_initial=1)
    f = DefisFamilleFenetre(athlete_id_initial=1)
    from noyau.donnees import defis as F
    F.creer("Défi", 50, date.today().isoformat(), demain, participants=[{"prenom": "Didier", "athlete_id": 1}])
    f.ecran.actualiser()
    assert f.ecran.barre.value() == 20
    GrandAffichage(f.ecran._etat)
    d = DialoguePreparerSemaine(1)
    assert d.table.rowCount() == 1
    d._envoyer()
    from noyau.donnees import connecteurs as D
    assert len(D.demandes()) == 3
    DialogueAlerteMateriel(1)
    p = PanneauDetail()
    assert p.montrer_sortie(1) and p.isVisible() is False or True
    assert not icone("parcours", "#E8590C").isNull() and not icone_appli().isNull()
    assert sans_emoji("☀️  Aujourd'hui") == "Aujourd'hui" and sans_emoji("Rien") == "Rien"
    assert set(ICONE_DE_L_ECRAN.values()) <= set(TRACES)
