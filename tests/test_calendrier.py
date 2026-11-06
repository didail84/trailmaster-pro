"""Calendrier des courses : disciplines FFA, lecture .ics, tableau collé, fusion des doublons, envois."""
from datetime import date

import pytest

from noyau.calendrier import regles as R

ICS = ("BEGIN:VCALENDAR\r\nVERSION:2.0\r\nBEGIN:VEVENT\r\nUID:a1@ex\r\nDTSTART;VALUE=DATE:20270417\r\n"
       "DTEND;VALUE=DATE:20270419\r\nSUMMARY:Ultra Trail du Ventoux 105 km 4500 D+\r\nLOCATION:Bédoin (84)\r\n"
       "URL:https://exemple.org\r\nDESCRIPTION:Départ place de la mairie\\, Bédoin\r\nEND:VEVENT\r\n"
       "BEGIN:VEVENT\r\nUID:a2@ex\r\nDTSTART:20270321T090000\r\nSUMMARY:KV de Gigondas\r\nLOCATION:84190 Gigondas\r\n"
       "STATUS:CANCELLED\r\nEND:VEVENT\r\nBEGIN:VEVENT\r\nSUMMARY:sans date\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n")
COLLE = ("Date\tLibellé\tLieu\tType\tNiveau\n"
         "15/11/2026\tTrail des Collines de Mazan 12 km / 25 km\tMazan (84)\tTrail\tDépartemental\n"
         "22/11/2026\tCross départemental\tCarpentras (84)\tCross\tDépartemental\n"
         "29/11/2026\tCorrida de Noël 10 km\tAvignon (84)\tHors Stade\tRégional\n"
         "pas une course\n")


def test_disciplines():
    assert R.km_effort(23, 300) == 26.0                            # exemple de la réglementation FFA
    assert R.classer("Trail des Dentelles", 23, 1100) == "trail_court"
    assert R.classer("Trail découverte", 12, 400) == "trail_decouverte"
    assert R.classer("Grand trail", 55, 2500) == "trail_long"
    assert R.classer("Ultra Trail du Ventoux", 105, 4500) == "ultra_trail"
    assert R.classer("10 km de Carpentras") == "route" and R.classer("Semi-marathon") == "route"
    assert R.classer("Cross départemental") == "cross" and R.classer("Meeting en salle") == "stade"
    assert R.classer("KV de Bédoin") == "kv" and R.classer("Marche nordique du Luberon") == "marche_nordique"
    assert R.classer("Course en montagne du Ventoux") == "montagne"
    assert R.niveau_depuis("Championnats de France de trail") == "championnat_france"
    assert R.FAMILLE["ultra_trail"] == "Trail" and set(R.REGIONS) == {"Provence-Alpes-Côte d'Azur", "Occitanie",
                                                                       "Auvergne-Rhône-Alpes"}


def test_dates_lieux_distances():
    assert R.lire_date("dim. 15 nov. 2026") == date(2026, 11, 15) and R.lire_date("15/11/26") == date(2026, 11, 15)
    assert R.lire_dates("du 13 au 15 novembre 2026") == (date(2026, 11, 13), date(2026, 11, 15))
    assert R.lire_dates("13-15/11/2026") == (date(2026, 11, 13), date(2026, 11, 15))
    assert R.lire_lieu("Bédoin (84)") == ("Bédoin", None, "84") and R.lire_lieu("84410 Bédoin") == ("Bédoin", "84410", "84")
    assert R.lire_distances("12 km / 600 D+, 25 km 1200m D+, 42k") == [(12, 600), (25, 1200), (42, None)]
    assert R.nom_sans_distances("Trail du Ventoux 23 km 1100 D+") == "Trail du Ventoux"
    assert R.nom_sans_distances("Les 10 km de Carpentras") == "Les 10 km de Carpentras"


def test_ics_et_collage():
    c, e = R.lire_ics(ICS)
    assert len(c) == 2 and len(e) == 1
    ultra = c[0]
    assert ultra["nom"] == "Ultra Trail du Ventoux" and ultra["date_debut"] == "2027-04-17"
    assert ultra["date_fin"] == "2027-04-18" and ultra["departement"] == "84" and ultra["discipline"] == "ultra_trail"
    assert ultra["epreuves"][0]["distance_km"] == 105 and "mairie, Bédoin" in ultra["notes"]
    assert c[1]["statut"] == "annulee" and c[1]["code_postal"] == "84190" and c[1]["discipline"] == "kv"
    c, e = R.lire_tableau(COLLE)
    assert [x["nom"] for x in c] == ["Trail des Collines de Mazan", "Cross départemental", "Corrida de Noël"]
    assert [x["discipline"] for x in c] == ["trail_decouverte", "cross", "route"]
    assert c[0]["niveau"] == "departemental" and len(c[0]["epreuves"]) == 2 and e == []
    # sans en-tête, colonnes séparées par des espaces
    c, _e = R.lire_tableau("dim. 29 nov. 2026   Trail du Ventoux   Bédoin (84)   23 km 1100 D+\n")
    assert c[0]["nom"] == "Trail du Ventoux" and c[0]["epreuves"][0]["denivele_m"] == 1100
    assert R.meme_course({"nom": "Trail du Ventoux 2026", "date_debut": "2026-11-29", "departement": "84"},
                         {"nom": "Trail du Ventoux", "date_debut": "2026-11-29", "departement": "84"})
    assert not R.meme_course({"nom": "Trail du Ventoux", "date_debut": "2026-11-29"},
                             {"nom": "Cross de Mazan", "date_debut": "2026-11-29"})
    texte = R.vers_ics(c)
    assert "SUMMARY:Trail du Ventoux" in texte


def test_filtres_et_liens():
    cs = [R.normaliser({"nom": "A trail", "date_debut": "2026-12-01", "departement": "84", "discipline": "trail_court"}),
          R.normaliser({"nom": "B cross", "date_debut": "2027-01-10", "departement": "34", "discipline": "cross"})]
    assert [x["nom"] for x in R.filtrer(cs, departements=R.REGIONS["Occitanie"])] == ["B cross"]
    assert [x["nom"] for x in R.filtrer(cs, familles=("Trail",))] == ["A trail"]
    assert [x["nom"] for x in R.filtrer(cs, fin="2026-12-31")] == ["A trail"]
    liens = dict(R.liens_calendriers("Trail", "Occitanie", 2027))
    assert "frmsaison=2027" in liens["Calendrier officiel FFA"] and liens["Betrail"].endswith("/occitanie")
    assert "Betrail" not in dict(R.liens_calendriers("Stade"))


def test_base(base_vide):
    from noyau.donnees import calendrier as dc
    r = dc.importer_texte(COLLE, "Calendrier FFA")
    assert r["ajoutees"] == 3 and r["erreurs"] == []
    r = dc.importer_texte(COLLE.replace("Corrida de Noël", "Corrida de Noël 2026"), "Calendrier FFA")
    assert r["ajoutees"] == 0 and r["mises_a_jour"] == 3                 # pas de doublon
    sid = dc.enregistrer_source({"nom": "Comité 84", "type": "ics", "url": "webcal://exemple.org/a.ics"})
    assert dc.source(sid)["url"] == "https://exemple.org/a.ics"
    with pytest.raises(dc.ErreurCalendrier):
        dc.enregistrer_source({"nom": "x", "type": "ics", "url": "ftp://x"})
    assert [s["id"] for s in dc.a_relire()] == [sid]
    assert dc.appliquer_flux(sid, ICS)["ajoutees"] == 2
    assert dc.appliquer_flux(sid, ICS)["ajoutees"] == 0 and not dc.a_relire()
    dc.appliquer_flux(sid, erreur="lecture impossible : réseau")
    assert dc.source(sid)["erreur"].startswith("lecture impossible")
    tous = dc.courses()
    assert len(tous) == 5 and dc.courses(fin="2026-12-31") and len(dc.courses("2027-01-01")) == 2
    # une course corrigée n'est plus modifiée par sa source
    ultra = next(c for c in tous if c["discipline"] == "ultra_trail")
    dc.enregistrer_course({**ultra, "nom": "Ultra du Ventoux (corrigé)", "mes_notes": "objectif 2027"}, ultra["id"])
    assert dc.appliquer_flux(sid, ICS)["ignorees"] >= 1
    assert dc.course(ultra["id"])["nom"] == "Ultra du Ventoux (corrigé)"
    # vers « Courses à venir » et l'agenda du club
    mid = dc.envoyer_vers_mes_courses(ultra["id"], 1)
    assert dc.envoyer_vers_mes_courses(ultra["id"], 1) == mid
    from noyau.donnees import courses as dcourses
    assert dcourses.course(mid, "nom", "distance_km", "denivele_m", "type_terrain", "region") == \
        ("Ultra du Ventoux (corrigé)", 105, 4500, "Trail", "Provence-Alpes-Côte d'Azur")
    from noyau.donnees import club as dclub, agenda_club as dag
    seance = dc.proposer_au_club(ultra["id"], dclub.club_id_ou_creer())
    assert dag.seance(seance)["type"] == "competition" and "105 km" in dag.seance(seance)["contenu"]
    dc.definir_favori(ultra["id"])
    dc.masquer(tous[0]["id"])
    assert len(dc.courses()) == 4 and dc.chiffres("2026-01-01")["favoris"] == 1
    dc.supprimer_source(sid, avec_courses=True)                       # garde la favorite corrigée
    assert dc.course(ultra["id"]) is not None


def test_ecrans(base_vide):
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    from noyau.donnees import calendrier as dc
    dc.importer_texte(COLLE.replace("2026", str(date.today().year + 1)), "Calendrier FFA")
    from interface.calendrier_competitions import CalendrierFenetre
    f = CalendrierFenetre(1)
    c = f.courses
    c.periode.setCurrentIndex(4)                                       # tout le calendrier à venir
    assert c.table.rowCount() == 3
    c.famille.setCurrentIndex(c.famille.findData("Trail"))
    assert c.table.rowCount() == 1
    c.table.selectRow(0)
    assert "Mazan" in c.detail.text()
    s = f.sources
    s.collage.setPlainText("Date;Libellé;Lieu\n12/12/2030;Trail de test 15 km;Apt (84)\n")
    s._apercu()
    assert "1 course(s) reconnue(s)" in s.label_apercu.text()
    assert s.lancer_relectures() == 0
    f.close()
