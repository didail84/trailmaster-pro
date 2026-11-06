"""Étape 4.2 : agenda du club (séries, vacances, fériés) et appel des présences."""
from datetime import date

import pytest

from noyau.club import agenda as ag


# ----------------------------------------------------------------- calendrier

def test_paques_et_feries():
    assert ag.paques(2026) == date(2026, 4, 5) and ag.paques(2027) == date(2027, 3, 28)
    f = ag.jours_feries(2027)
    assert f[date(2027, 3, 29)] == "Lundi de Pâques" and f[date(2027, 5, 6)] == "Ascension"
    assert f[date(2027, 5, 17)] == "Lundi de Pentecôte" and len(f) == 11
    assert ag.ferie("2026-11-11") == "Armistice 1918" and ag.ferie("2026-11-12") is None


def test_vacances_officielles():
    # zone B (Aix-Marseille) 2026-2027 : hiver du 20 février au 7 mars, reprise le lundi 8 mars
    assert ag.en_vacances("2027-02-20", "B") == "vacances d'hiver"
    assert ag.en_vacances("2027-03-07", "B") == "vacances d'hiver"
    assert ag.en_vacances("2027-03-08", "B") is None
    assert ag.en_vacances("2027-02-08", "C") == "vacances d'hiver" and ag.en_vacances("2027-02-08", "B") is None
    assert ag.en_vacances("2026-10-17", "A") == "vacances de la Toussaint"
    assert ag.en_vacances("2026-11-02", "A") is None
    assert ag.en_vacances("2026-04-20", "B") == "vacances de printemps"          # 2025-2026
    assert ag.en_vacances("2027-05-07", "B") == "pont de l'ascension"
    assert ag.calendrier_connu("2026-2027") and not ag.calendrier_connu("2030-2031")
    v = ag.vacances_de("2026-2027", "B")
    assert [x[0] for x in v] == ["Toussaint", "Noël", "Hiver", "Printemps", "Été"] and v[-1][3]   # été 2027 estimé


def test_dates_serie():
    # les mardis de novembre 2026 : le 3, 10, 17, 24
    d, e = ag.dates_serie(1, "2026-11-01", "2026-11-30")
    assert [x.day for x in d] == [3, 10, 17, 24] and e == []
    # mercredis : le 11 novembre est férié
    d, e = ag.dates_serie(2, "2026-11-01", "2026-11-30")
    assert [x.day for x in d] == [4, 18, 25] and e == [(date(2026, 11, 11), "férié : Armistice 1918")]
    d, _e = ag.dates_serie(2, "2026-11-01", "2026-11-30", sauf_feries=False)
    assert len(d) == 4
    # samedis d'octobre hors vacances (zone B : Toussaint à partir du samedi 17)
    d, e = ag.dates_serie(5, "2026-10-01", "2026-10-31", "B", sauf_vacances=True)
    assert [x.day for x in d] == [3, 10] and [x[0].day for x in e] == [17, 24, 31]
    with pytest.raises(ag.ErreurAgenda):
        ag.dates_serie(1, "2026-11-30", "2026-11-01")


def test_heures():
    assert ag.verifier_heure("18h30") == "18:30" and ag.verifier_heure("9h") == "09:00"
    assert ag.verifier_heure("18.45") == "18:45" and ag.verifier_heure("") is None
    with pytest.raises(ag.ErreurAgenda):
        ag.verifier_heure("25:00")


def test_bilan_et_assiduite():
    b = ag.bilan_appel({1: "present", 2: "retard", 3: "excuse", 4: "absent"}, [1, 2, 3, 4, 5])
    assert b["effectif"] == 2 and b["non_pointes"] == 1 and b["taux"] == 50
    lignes = [(1, "2026-10-06", "present"), (1, "2026-10-13", "absent"), (1, "2026-10-20", "absent"),
              (1, "2026-10-27", "absent"), (2, "2026-10-06", "excuse"), (2, "2026-10-13", "present"),
              (3, "2026-10-06", None)]
    a = ag.assiduite(lignes)
    assert a[1]["taux"] == 25 and a[1]["absences_de_suite"] == 3 and a[1]["derniere_presence"] == "2026-10-06"
    assert a[2]["taux"] == 100                      # l'excuse ne compte pas contre lui
    assert a[3]["taux"] is None
    al = ag.alertes_presences(a, {1: "Chloé Roux"}, 2)
    assert "Chloé Roux" in al[0] and "2 séances" in al[1]


def test_ics():
    texte = ag.ics([{"id": 1, "uuid": "abc", "titre": "Fractionné piste", "date": "2026-11-10", "heure_debut": "18:30",
                     "heure_fin": None, "lieu": "Stade, Carpentras", "type": "entrainement", "groupe": "Adultes",
                     "entraineur": "Marc", "contenu": "10 × 400 m", "annulee": 0},
                    {"id": 2, "titre": "Cross", "date": "2026-11-29", "type": "competition", "annulee": 1,
                     "motif_annulation": "alerte orage"}], "Ventoux Trail Athlé")
    assert texte.startswith("BEGIN:VCALENDAR\r\n") and texte.endswith("END:VCALENDAR\r\n")
    assert "DTSTART;TZID=Europe/Paris:20261110T183000" in texte and "DTEND;TZID=Europe/Paris:20261110T193000" in texte
    assert "LOCATION:Stade\\, Carpentras" in texte and "SUMMARY:Fractionné piste (Adultes)" in texte
    assert "DTSTART;VALUE=DATE:20261129" in texte and "STATUS:CANCELLED" in texte and "ANNULÉ" in texte
    assert all(len(l.encode()) <= 75 for l in texte.split("\r\n"))


# ----------------------------------------------------------------- base de données

def _club():
    from noyau.donnees import club as dclub
    from noyau.club import imports as imp
    cid = dclub.club_id_ou_creer()
    csv = ("Nom;Prénom;Date de naissance;Formule;Montant tarif\nMARTIN;Lucas;12/03/1985;competition;95\n"
           "DURAND;Emma;05/07/2014;decouverte;70\nROUX;Chloé;22/11/1978;running;75\n")
    dclub.importer(cid, "2026-2027", imp.analyser(imp.lire_tableau(csv))["lignes"])
    g = dclub.enregistrer_groupe(cid, {"nom": "Adultes"})
    ids = {a["nom"]: a["personne_id"] for a in dclub.adhesions(cid, "2026-2027")}
    for n in ("MARTIN", "ROUX"):
        dclub.definir_groupes(ids[n], [g], cid)
    return cid, g, ids


def test_series_seances_appel(base_vide):
    from noyau.donnees import agenda_club as dag, club as dclub
    cid, g, ids = _club()
    dclub.enregistrer_club({"zone_vacances": "B"}, cid)
    serie = {"groupe_id": g, "titre": "Piste", "jour_semaine": 1, "heure_debut": "18h30", "heure_fin": "20h",
             "date_debut": "2026-09-01", "date_fin": "2027-06-30", "sauf_vacances": True}
    dates, ecartees = dag.apercu_serie(cid, serie)
    r = dag.enregistrer_serie(cid, serie, aujourdhui="2026-11-06")
    assert r["creees"] == len(dates) == 36 and len(r["ecartees"]) == len(ecartees) == 8
    assert dag.series(cid)[0]["nb_seances"] == 36
    with pytest.raises(dag.ErreurAgenda):
        dag.enregistrer_serie(cid, {**serie, "heure_fin": "17:00"})
    ss = dag.seances(cid, "2026-10-01", "2026-11-30")
    assert [s["date"][5:] for s in ss] == ["10-06", "10-13", "11-03", "11-10", "11-17", "11-24"]
    # l'appel : les membres du groupe sont attendus, Emma vient en plus
    feuille = dag.appel(ss[0]["id"])
    assert [l["nom"] for l in feuille] == ["MARTIN", "ROUX"] and all(l["attendu"] for l in feuille)
    b = dag.enregistrer_appel(ss[0]["id"], {ids["MARTIN"]: "present", ids["ROUX"]: ("excuse", "malade"),
                                            ids["DURAND"]: "present"})
    assert b == {"present": 2, "retard": 0, "excuse": 1, "absent": 0, "non_pointes": 0, "effectif": 2, "taux": 67}
    feuille = dag.appel(ss[0]["id"])
    assert [l["nom"] for l in feuille] == ["DURAND", "MARTIN", "ROUX"] and not feuille[0]["attendu"]
    assert feuille[2]["note"] == "malade" and dag.seance(ss[0]["id"])["appel_fait"]
    with pytest.raises(dag.ErreurAgenda):
        dag.enregistrer_appel(ss[1]["id"], {ids["MARTIN"]: "là"})
    for s in ss[1:4]:
        dag.enregistrer_appel(s["id"], {ids["MARTIN"]: "present", ids["ROUX"]: "absent"})
    a = dag.assiduite(cid, "2026-09-01", "2026-11-30")
    assert a[ids["ROUX"]]["absences_de_suite"] == 3 and a[ids["ROUX"]]["taux"] == 0
    assert a[ids["MARTIN"]]["taux"] == 100 and a[ids["MARTIN"]]["nom"] == "MARTIN"
    pg = dag.par_groupe(cid, "2026-09-01", "2026-11-30", aujourdhui=date(2026, 11, 10))
    assert pg[0]["groupe"] == "Adultes" and pg[0]["appelees"] == 4
    # enlever une personne de l'appel
    dag.enregistrer_appel(ss[0]["id"], {ids["DURAND"]: None})
    assert len(dag.appel(ss[0]["id"])) == 2
    # annuler, rétablir, dupliquer, ponctuelle
    dag.annuler_seance(ss[4]["id"], "piste fermée")
    assert dag.seance(ss[4]["id"])["annulee"] and len(dag.seances(cid, "2026-11-17", "2026-11-17", avec_annulees=False)) == 0
    dag.retablir_seance(ss[4]["id"])
    nid = dag.dupliquer_seance(ss[4]["id"], "2026-11-19")
    assert dag.seance(nid)["titre"] == "Piste" and dag.seance(nid)["serie_id"] is None
    cross = dag.enregistrer_seance(cid, {"titre": "Cross", "type": "competition", "date": "2026-11-29"})
    assert dag.attendus(cross) and len(dag.attendus(cross)) == 3          # sans groupe : tout le club
    with pytest.raises(dag.ErreurAgenda):
        dag.enregistrer_seance(cid, {"titre": " ", "date": "2026-11-29"})
    # séances passées sans appel
    assert [s["date"] for s in dag.sans_appel(cid, aujourdhui=date(2026, 11, 25))
            if s["date"] >= "2026-11-01"] == ["2026-11-17", "2026-11-19", "2026-11-24"]
    assert len(dag.sans_appel(cid, aujourdhui=date(2026, 11, 25), depuis_jours=10)) == 3
    # modifier la série : les séances à venir sans appel sont refaites, les autres restent
    r2 = dag.enregistrer_serie(cid, {**serie, "jour_semaine": 3}, r["serie_id"], aujourdhui="2026-11-06")
    apres = dag.seances(cid, "2026-11-01", "2026-11-30")
    jours = sorted({s["date"] for s in apres if s["serie_id"] == r["serie_id"]})
    assert "2026-11-10" in jours and "2026-11-12" in jours and "2026-11-17" not in jours      # le 10 a un appel
    assert r2["gardees"] >= 4
    # supprimer la série garde les séances appelées
    n = dag.supprimer_serie(r["serie_id"], aujourdhui="2026-11-06")
    assert n > 20 and dag.seance(ss[3]["id"]) and dag.seance(ss[3]["id"])["serie_id"] is None
    # exports
    csv = dag.export_presences_csv(cid, "2026-09-01", "2026-11-30")
    assert "MARTIN;Lucas;P;P;P;P;100 %" in csv
    texte = dag.export_ics(cid, "2026-11-01", "2026-11-30")
    assert texte.count("BEGIN:VEVENT") == len(dag.seances(cid, "2026-11-01", "2026-11-30"))


def test_ecrans(base_vide, tmp_path):
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    from noyau.donnees import agenda_club as dag
    cid, g, ids = _club()
    from datetime import timedelta
    auj = date.today()
    dag.enregistrer_serie(cid, {"groupe_id": g, "titre": "Piste", "jour_semaine": auj.weekday(), "heure_debut": "18:30",
                                "date_debut": (auj - timedelta(days=21)).isoformat(),
                                "date_fin": (auj + timedelta(days=35)).isoformat(), "sauf_feries": False})
    from interface.club import ClubFenetre
    f = ClubFenetre(1)
    assert f.tabs.count() == 8
    a, p = f.agenda, f.presences
    a.periode.setCurrentIndex(4)                                  # toute la saison
    assert a.table.rowCount() >= 8 and a.table_series.rowCount() == 1
    a.periode.setCurrentIndex(5)                                  # passées sans appel
    assert a.table.rowCount() == 3
    p.actualiser()
    seance_id = p.combo_seance.currentData()
    assert dag.seance(seance_id)["date"] == auj.isoformat()         # par défaut : la séance du jour
    assert p.table.rowCount() == 2
    p._tous_presents()
    p._combos[1].setCurrentIndex(p._combos[1].findData("absent"))
    assert p._sauver(p.statuts())
    assert dag.bilan(seance_id)["present"] == 1 and dag.seance(seance_id)["appel_fait"]
    a.periode.setCurrentIndex(5)
    a._remplir()
    assert a.table.rowCount() == 3                                  # aujourd'hui n'est pas « passée »
    f.tableau.actualiser()
    assert f.tableau.table_proch.rowCount() >= 1
    from interface.club_pdf import rendre_feuille_appel
    pdf = tmp_path / "appel.pdf"
    rendre_feuille_appel(pdf, None, dag.seance(seance_id), dag.appel(seance_id))
    assert pdf.read_bytes()[:4] == b"%PDF"
    f.close()
