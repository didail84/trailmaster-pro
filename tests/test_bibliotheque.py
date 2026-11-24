"""Bibliothèque trail : liste de référence, filtres, statuts et écran."""
import pytest

from noyau import modules as M
from noyau.bibliotheque import regles as R


def test_reference_coherente():
    ref = R.lire_reference()
    ls = ref["livres"]
    themes = dict(R.themes(ref))
    assert len(ls) >= 40 and len({l["id"] for l in ls}) == len(ls)
    for l in ls:
        assert l["titre"] and l["auteurs"] and l["pourquoi"], l["id"]
        assert l["theme"] in themes, l["id"]
        assert l["langue"] in R.NOM_LANGUE, l["id"]
        assert l["modules"] and all(c in M.PAR_CODE for c in l["modules"]), l["id"]
        assert l["ecrans"], l["id"]
        assert l["annee"] is None or 1980 <= l["annee"] <= 2026, l["id"]
        assert not l["lien"] or l["lien"].startswith("https://"), l["id"]
    assert {l["theme"] for l in ls} == set(themes)                  # chaque thème a au moins un livre
    assert sum(R.lisible_en_francais(l) for l in ls) >= 20


def test_les_ecrans_cites_existent_dans_le_menu():
    from pathlib import Path
    import re
    src = (Path(__file__).resolve().parent.parent / "interface" / "tableau_bord.py").read_text(encoding="utf-8")
    menu = {re.sub(r"\s+", " ", t.replace("&&", "&")).strip()
            for t in re.findall(r'\("\S+\s+([^"]+)", self\.ouvrir_\w+, (?:True|False)\)', src)}
    onglets = {"Poids & récupération", "Blessures", "Carte du corps", "Soins", "Matériel", "Zones d'entraînement",
               "Renforcement & Mobilité"}
    for l in R.lire_reference()["livres"]:
        for e in l["ecrans"]:
            assert e in menu or e in onglets, (l["id"], e)


def test_filtres_et_recherche():
    tous = R.livres()
    assert R.livres(theme="nutrition") and all(l["theme"] == "nutrition" for l in R.livres(theme="nutrition"))
    assert all("fractionne" in l["modules"] for l in R.livres(module="fractionne"))
    assert {l["id"] for l in R.livres(recherche="billat")} == {"billat"}
    assert "walker" in {l["id"] for l in R.livres(recherche="pourquoi nous DORMONS")}   # titre français, sans casse
    assert "lanthier" in {l["id"] for l in R.livres(recherche="cles performer")}         # sans accents
    assert all(R.lisible_en_francais(l) for l in R.livres(en_francais=True))
    assert all(l["langue"] == "en" for l in R.livres(langue="en"))
    st = {"billat": "lu", "uphill": "a_lire"}
    assert [l["id"] for l in R.livres(statut="lu", statuts=st)] == ["billat"]
    assert len(R.livres(statut="aucun", statuts=st)) == len(tous) - 2
    assert {l["id"] for l in R.livres_pour_ecran("fractionné")} >= {"billat", "daniels", "uphill"}


def test_affichage():
    ref = {l["id"]: l for l in R.lire_reference()["livres"]}
    assert R.auteurs(ref["uphill"]) == "Steve House, Scott Johnston et Kilian Jornet"
    assert R.auteurs(ref["billat"]) == "Véronique Billat"
    assert R.titre_affiche(ref["uphill"]).startswith("Up !")
    assert R.reference_courte(ref["uphill"]) == "Patagonia, 2019 · traduit en français (Guérin, 2020)"
    assert R.lien(ref["ffa_regl"]).startswith("https://www.athle.fr/")
    assert R.lien(ref["daniels"]).startswith("https://openlibrary.org/search?q=Daniels")


def test_statuts(base_vide):
    assert R.lire_statuts() == {}
    R.definir_statut("billat", "a_lire")
    R.definir_statut("uphill", "lu")
    assert R.lire_statuts() == {"billat": "a_lire", "uphill": "lu"}
    R.definir_statut("billat", None)
    assert R.lire_statuts() == {"uphill": "lu"}
    assert R.resume()["lus"] == 1
    with pytest.raises(ValueError):
        R.definir_statut("uphill", "peut-etre")


def test_ecran(base_vide):
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    from interface.bibliotheque import BibliothequeFenetre, html_livre
    f = BibliothequeFenetre()
    try:
        e = f.livres
        assert e.table.rowCount() == len(R.livres())
        e.recherche.setText("uphill")
        assert e.table.rowCount() == 1
        e.table.selectRow(0)
        assert "Up !" in e.lecteur.toHtml()
        e._basculer("a_lire")
        assert R.lire_statuts() == {"uphill": "a_lire"} and e.b_a_lire.text().startswith("Retirer")
        e.recherche.setText("")
        e.statut.setCurrentIndex(e.statut.findData("a_lire"))
        assert e.table.rowCount() == 1
        p = f.par_ecran
        i = p.ecran.findData("Alimentation")
        p.ecran.setCurrentIndex(i)
        assert "Sport Nutrition" in p.lecteur.toPlainText()
        assert "Choisis un livre" in html_livre(None)
    finally:
        f.close()
