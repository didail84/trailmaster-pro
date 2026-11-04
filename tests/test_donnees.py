"""Étape 1.4a — couche d'accès aux données (noyau/donnees).

Chaque fonction est comparée à la requête d'origine, telle qu'elle était
écrite dans les écrans de la v108, sur une base remplie pour l'occasion.
Les derniers tests surveillent qu'aucune nouvelle requête SQL ne
réapparaît dans les écrans.
"""
import ast
import json
import re
import sqlite3
from datetime import date, timedelta
from pathlib import Path

import pytest

import data.database as db
from noyau.donnees import activites as dact, parcours as dparc, athletes as dath, base
from noyau.donnees.recherche import rechercher_partout
from noyau.outils import evenements as ev

AUJ = date.today()


@pytest.fixture
def remplie(tmp_path, monkeypatch):
    chemin = tmp_path / "t.db"
    monkeypatch.setattr(db, "CHEMIN_BDD", chemin)
    db.creer_base_de_donnees()
    c = sqlite3.connect(chemin)
    c.execute("INSERT INTO athletes (id, nom, prenom, age, sexe, taille, poids, fc_repos, fc_max, vma, niveau) "
              "VALUES (1,'Beltran','Test',50,'H',178,88.5,55,180,12.5,'Intermédiaire')")
    c.execute("INSERT INTO athletes (id, nom, prenom, poids) VALUES (2,'Autre','Coureur',70)")
    types = ["Trail", "Course", "Randonnée", "Vélo", "Trail"]
    for i in range(30):
        jour = (AUJ - timedelta(days=3 * i)).isoformat() + f" 0{7 + i % 3}:00:00"
        athlete = 1 if i % 6 else 2
        cur = c.execute(
            "INSERT INTO activites (athlete_id, date, nom, type, distance, denivele, duree, "
            "frequence_cardiaque_moyenne, frequence_cardiaque_max, vo2max, allure_moyenne, empreinte, "
            "te_aerobie, temps_zone_2) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (athlete, jour, f"Sortie {i} col", types[i % 5], 4 + i % 9, 100 * (i % 7), 1500 + 120 * i,
             140 + i % 10, 170, 40 + i % 5 if i % 2 else None, 6.1, f"emp{i}", 2.5, 600))
        if i % 3 == 0:
            trace = [[44 + k * 1e-4, 5.0, 300 + k, k * 10] for k in range(12)]
            c.execute("INSERT INTO parcours_gpx (athlete_id, nom, distance_km, denivele_positif, "
                      "denivele_negatif, altitude_min, altitude_max, trace_json, activite_id, date_ajout) "
                      "VALUES (?,?,?,?,?,?,?,?,?,?)",
                      (athlete, f"Trace {i}", 4 + i % 9, 120, 110, 300, 420, json.dumps(trace),
                       cur.lastrowid, f"2026-0{1 + i % 9}-1{i % 10} 10:00:00"))
    c.execute("INSERT INTO parcours_gpx (athlete_id, nom, distance_km, trace_json, date_ajout) "
              "VALUES (1, 'Dessiné sans trace', 12, NULL, '2026-10-01 09:00:00')")
    c.commit()
    c.close()
    return chemin


def brut(chemin, sql, params=()):
    c = sqlite3.connect(chemin)
    try:
        return c.execute(sql, params).fetchall()
    finally:
        c.close()


# ------------------------------------------------------------------
# Sorties : chaque fonction rend exactement la requête d'origine
# ------------------------------------------------------------------

def test_valeurs_d_une_sortie(remplie):
    assert dact.valeurs(2, "nom", "date", "type", "distance", "denivele", "duree") == brut(
        remplie, "SELECT nom, date, type, distance, denivele, duree FROM activites WHERE id=?", (2,))[0]
    assert dact.valeurs(9999, "nom") is None
    # filtre athlète : la sortie 1 appartient à l'athlète 2
    assert dact.valeurs(1, "nom", athlete_id=1) is None
    assert dact.valeurs(1, "nom", athlete_id=2) == ("Sortie 0 col",)


@pytest.mark.parametrize("fonction, args, sql, params", [
    (dact.recentes, (1, 5),
     "SELECT id, date, nom, type, distance, denivele, duree, frequence_cardiaque_moyenne "
     "FROM activites WHERE athlete_id=? ORDER BY date DESC LIMIT ?", (1, 5)),
    (dact.pour_liaison, (1, 50),
     "SELECT id, date, type, distance, duree FROM activites WHERE athlete_id=? ORDER BY date DESC LIMIT ?", (1, 50)),
    (dact.pour_choix_photo, (1,),
     "SELECT id, date, nom, type FROM activites WHERE athlete_id=? ORDER BY date DESC", (1,)),
    (dact.pour_record_vo2max, (1,),
     "SELECT date, distance, duree, vo2max FROM activites WHERE athlete_id=? "
     "AND type IN ('Trail','Course') AND distance >= 3 AND duree > 0", (1,)),
    (dact.pour_page_telephone, (1,),
     "SELECT date, nom, type, distance, denivele, duree, frequence_cardiaque_moyenne, allure_moyenne, vo2max "
     "FROM activites WHERE athlete_id=? ORDER BY date", (1,)),
])
def test_listes_de_sorties(remplie, fonction, args, sql, params):
    attendu = brut(remplie, sql, params)
    assert attendu, "la base de test doit contenir des lignes"
    assert fonction(*args) == attendu


def test_sorties_par_jour_et_par_periode(remplie):
    debut, fin = (AUJ - timedelta(days=20)).isoformat(), AUJ.isoformat()
    assert dact.par_jour_entre(1, debut, fin) == brut(
        remplie, "SELECT id, date, nom, type, distance, denivele, duree, frequence_cardiaque_moyenne "
        "FROM activites WHERE athlete_id=? AND substr(date,1,10) BETWEEN ? AND ? ORDER BY date", (1, debut, fin))
    cols = ["id", "date", "nom", "type"]
    assert dact.colonnes_de_l_athlete(1, cols) == brut(remplie, "SELECT id, date, nom, type FROM activites WHERE athlete_id=?", (1,))
    assert dact.colonnes_de_l_athlete(1, cols, type_="Trail") == brut(
        remplie, "SELECT id, date, nom, type FROM activites WHERE athlete_id=? AND type=?", (1, "Trail"))
    assert dact.colonnes_de_l_athlete(1, cols, debut=debut, fin=fin + "T23:59:59") == brut(
        remplie, "SELECT id, date, nom, type FROM activites WHERE athlete_id=? AND date >= ? AND date <= ?",
        (1, debut, fin + "T23:59:59"))


def test_sommes_maxima_et_details(remplie):
    depuis = (AUJ - timedelta(days=60)).isoformat()
    assert dact.maxima_depuis(1, depuis) == brut(
        remplie, "SELECT MAX(distance), MAX(denivele) FROM activites "
        "WHERE athlete_id=? AND date >= ? AND type IN ('Trail','Course','Randonnée')", (1, depuis))[0]
    assert dact.somme_distance_depuis(1, depuis) == brut(
        remplie, "SELECT SUM(distance) FROM activites WHERE athlete_id=? AND date >= ?", (1, depuis))[0][0]
    assert dact.somme_distance_depuis(1, depuis, ["Trail", "Course"]) == brut(
        remplie, "SELECT SUM(distance) FROM activites WHERE athlete_id=? AND date >= ? AND type IN (?,?)",
        (1, depuis, "Trail", "Course"))[0][0]
    assert dact.somme_distance_depuis(1, "2099-01-01") is None
    assert len(dact.detaillees_depuis(1, depuis)[0]) == 16
    assert dact.ids_chronologiques(1) == [r[0] for r in brut(
        remplie, "SELECT id FROM activites WHERE athlete_id=? ORDER BY date, id", (1,))]


def test_sorties_avec_trace(remplie):
    tout = dact.avec_trace_entre(1, "2000-01-01", "2100-01-01")
    assert tout and all(len(l) == 5 and l[4] for l in tout)
    assert [l[1] for l in tout] == sorted(l[1] for l in tout)
    recentes = dact.avec_trace_recentes(1, "2000-01-01", 3)
    assert len(recentes) == 3 and recentes[0][0] >= recentes[-1][0]


# ------------------------------------------------------------------
# Sorties : écritures
# ------------------------------------------------------------------

def test_inserer_et_empreinte(remplie):
    vus = []

    def noter(**_):
        vus.append(1)

    ev.abonner(ev.DONNEES_MODIFIEES, noter)
    try:
        nouvel = dact.inserer({"athlete_id": 1, "date": "2026-11-01 08:00:00", "nom": "Nouvelle",
                               "type": "Trail", "distance": 12.5, "empreinte": "neuve"})
    finally:
        ev.desabonner(ev.DONNEES_MODIFIEES, noter)
    assert dact.id_par_empreinte("neuve") == nouvel
    assert dact.id_par_empreinte("absente") is None
    assert dact.valeurs(nouvel, "nom", "distance") == ("Nouvelle", 12.5)
    assert vus, "une création hors transaction annonce DONNEES_MODIFIEES"


def test_modifier_une_sortie(remplie):
    dact.modifier(2, 1, [("nom", "Renommée"), ("distance", 21.1)])
    assert dact.valeurs(2, "nom", "distance") == ("Renommée", 21.1)
    dact.modifier(1, 1, [("nom", "Pas à moi")])  # la sortie 1 est à l'athlète 2 : rien ne change
    assert dact.valeurs(1, "nom") == ("Sortie 0 col",)


def test_transaction_tout_ou_rien(remplie):
    avant = len(brut(remplie, "SELECT id FROM activites"))
    with pytest.raises(RuntimeError):
        with base.transaction() as cur:
            dact.inserer({"athlete_id": 1, "date": "2026-11-02", "nom": "A"}, cur=cur)
            dparc.inserer({"athlete_id": 1, "nom": "B"}, cur=cur)
            raise RuntimeError("coupure")
    assert len(brut(remplie, "SELECT id FROM activites")) == avant
    with base.transaction() as cur:
        a = dact.inserer({"athlete_id": 1, "date": "2026-11-02", "nom": "A"}, cur=cur)
        dparc.inserer({"athlete_id": 1, "nom": "B", "activite_id": a}, cur=cur)
    assert dparc.lie_a_l_activite(a) is None  # parcours sans trace
    assert brut(remplie, "SELECT activite_id FROM parcours_gpx WHERE nom='B'") == [(a,)]


def test_noms_de_colonnes_refuses():
    for mauvais in ("nom; DROP TABLE activites", "1=1 --", "Nom", "a b"):
        with pytest.raises(ValueError):
            base.verifier_colonnes([mauvais])


# ------------------------------------------------------------------
# Parcours
# ------------------------------------------------------------------

def test_parcours(remplie):
    pid = brut(remplie, "SELECT id FROM parcours_gpx WHERE nom='Trace 3'")[0][0]
    assert dparc.trace(pid) == brut(remplie, "SELECT trace_json FROM parcours_gpx WHERE id=?", (pid,))[0][0]
    assert dparc.valeurs(pid, "nom", "distance_km", "trace_json")[0] == "Trace 3"
    act = brut(remplie, "SELECT activite_id FROM parcours_gpx WHERE id=?", (pid,))[0][0]
    assert dparc.trace_de_l_activite(act) == dparc.trace(pid)
    assert dparc.lie_a_l_activite(act) == (pid, dparc.trace(pid))
    assert dparc.trace_de_l_activite(99999) is None
    assert dparc.avec_son_activite(pid)[1:] == brut(
        remplie, "SELECT p.athlete_id, a.distance, a.duree FROM parcours_gpx p "
        "LEFT JOIN activites a ON p.activite_id = a.id WHERE p.id=?", (pid,))[0]


def test_listes_de_parcours(remplie):
    assert dparc.liste_courte(1, 300) == brut(
        remplie, "SELECT id, nom, distance_km FROM parcours_gpx WHERE athlete_id=? "
        "ORDER BY date_ajout DESC LIMIT 300", (1,))
    assert len(dparc.liste_courte(1, 2)) == 2
    assert dparc.liste_courte(1, par_id=True) == brut(
        remplie, "SELECT id, nom, distance_km FROM parcours_gpx WHERE athlete_id=? ORDER BY id DESC", (1,))
    assert dparc.traces_de_l_athlete(1) == brut(remplie, "SELECT id, trace_json FROM parcours_gpx WHERE athlete_id=?", (1,))
    trails = dparc.traces_de_l_athlete(1, "Trail")
    assert trails and len(trails) < len(dparc.traces_de_l_athlete(1))
    assert len(dparc.traces_et_activites(1)[0]) == 3
    assert dparc.liste_pour_tableau(None) == brut(
        remplie, "SELECT id, nom, distance_km, denivele_positif, denivele_negatif, date_ajout, activite_id "
        "FROM parcours_gpx ORDER BY date_ajout DESC LIMIT 500")
    assert all(len(l) == 7 for l in dparc.liste_pour_tableau(1))
    assert [l[0] for l in dparc.liste_complete()] == [r[0] for r in brut(
        remplie, "SELECT id FROM parcours_gpx ORDER BY date_ajout DESC")]


def test_parcours_creer_et_supprimer(remplie):
    pid = dparc.inserer({"athlete_id": 1, "nom": "Boucle", "distance_km": 8.2, "trace_json": "[]"})
    assert dparc.valeurs(pid, "nom", "distance_km") == ("Boucle", 8.2)
    dparc.supprimer(pid)
    assert dparc.valeurs(pid, "nom") is None


# ------------------------------------------------------------------
# Athlètes
# ------------------------------------------------------------------

def test_athletes(remplie):
    assert dath.lister_pour_tableau() == brut(
        remplie, "SELECT id, nom, prenom, age, sexe, taille, poids, fc_repos, vma, niveau FROM athletes ORDER BY id DESC")
    assert len(dath.fiche(1)) == 14 and dath.fiche(99) is None
    assert dath.valeurs(1, "prenom", "nom") == ("Test", "Beltran")
    assert dath.valeur(1, "poids") == 88.5 and dath.valeur(99, "poids") is None
    dath.definir_vma(1, 13.1)
    assert dath.valeur(1, "vma") == 13.1
    dath.modifier_profil(2, "Autre", "Coureuse", 33, "F", 165, 58, 50, 190, 170, 15, 55, "Confirmé")
    assert dath.fiche(2)[1:13] == ("Autre", "Coureuse", 33, "F", 165, 58, 50, 190, 170, 15, 55, "Confirmé")


def test_supprimer_un_athlete_sans_sortie(remplie):
    c = sqlite3.connect(remplie)
    c.execute("INSERT INTO athletes (id, nom, prenom) VALUES (3, 'Sans', 'Sortie')")
    c.commit()
    c.close()
    dath.supprimer(3)
    assert dath.fiche(3) is None


# ------------------------------------------------------------------
# Recherche globale
# ------------------------------------------------------------------

def test_recherche_globale(remplie):
    assert rechercher_partout("", 1, 10) == []
    tous = rechercher_partout("col", None, 100)
    seulement_1 = rechercher_partout("col", 1, 100)
    assert {r[0] for r in tous} == {"Activité"}
    assert 0 < len(seulement_1) < len(tous)
    assert len(rechercher_partout("Trace", 1, 2)) == 2  # limite par catégorie


# ------------------------------------------------------------------
# Garde-fou : plus de nouvelles requêtes SQL dans les écrans
# ------------------------------------------------------------------

RACINE = Path(__file__).resolve().parent.parent
TABLES_FAITES = {"activites", "parcours_gpx", "athletes"}
_TABLE = re.compile(r"\b(?:FROM|INTO|UPDATE)\s+([a-z_]+)", re.I)


def requetes_des_ecrans():
    trouvees = []
    for chemin in sorted((RACINE / "interface").glob("*.py")):
        src = chemin.read_text(encoding="utf-8")
        for n in ast.walk(ast.parse(src)):
            if isinstance(n, ast.Call) and getattr(n.func, "attr", "") in ("execute", "executemany") and n.args:
                texte = ast.get_source_segment(src, n.args[0]) or ""
                trouvees.append((chemin.name, n.lineno, texte))
    return trouvees


def test_plus_aucune_requete_principale_sur_les_tables_faites():
    """Les écrans ne lisent plus activites, parcours_gpx ni athletes en
    table principale (seules restent des jointures depuis d'autres tables,
    traitées aux étapes 1.4b et 1.4c)."""
    fautes = []
    for fichier, ligne, texte in requetes_des_ecrans():
        principales = _TABLE.findall(texte)
        if principales and principales[0].lower() in TABLES_FAITES:
            fautes.append(f"{fichier}:{ligne}")
    assert not fautes, "Requête à déplacer dans noyau/donnees : " + ", ".join(fautes)


def test_le_nombre_de_requetes_des_ecrans_ne_remonte_pas():
    # 157 requêtes en v108 → 88 après l'étape 1.4a ; ce plafond baissera à chaque étape.
    assert len(requetes_des_ecrans()) <= 88
