"""Chantier F : actualités du trail (flux RSS) et coureurs connus."""
import pytest

from noyau.actualites import regles as R

RSS = """<?xml version="1.0" encoding="UTF-8"?><rss version="2.0" xmlns:content="http://purl.org/rss/1.0/modules/content/">
<channel><title>u-Trail</title><language>fr-FR</language>
<item><title>Blandine L&#8217;Hirondel remporte l&#039;UTMB</title><link>https://u-trail.com/utmb-2026</link>
<pubDate>Sun, 30 Aug 2026 08:00:00 +0200</pubDate><guid isPermaLink="false">https://u-trail.com/?p=1</guid>
<description><![CDATA[<p><img src="https://u-trail.com/photo.jpg"/>Victoire de la Française sur le trail le plus couru.</p>
<p>L’article X est apparu en premier sur u-Trail.</p>]]></description></item>
<item><title>Nouvelle chaussure de route</title><link>https://u-trail.com/route</link>
<pubDate>Mon, 02 Nov 2026 10:00:00 +0000</pubDate><guid>https://u-trail.com/?p=2</guid>
<description>Test sur bitume, pour le marathon.</description></item>
<item><title>Sans lien</title></item>
</channel></rss>"""

ATOM = """<?xml version="1.0" encoding="utf-8"?><feed xmlns="http://www.w3.org/2005/Atom"><title>Blog</title>
<entry><title>Kilian Jornet back at Hardrock</title><link rel="alternate" href="https://ex.org/k"/><id>tag:ex.org,1</id>
<updated>2026-11-01T12:00:00Z</updated><summary type="html">&lt;b&gt;Ultra&lt;/b&gt; news</summary></entry></feed>"""


def test_regles():
    titre, a = R.lire_flux(RSS)
    assert titre == "u-Trail" and len(a) == 2                          # l'article sans lien est ignoré
    assert a[0]["titre"] == "Blandine L’Hirondel remporte l'UTMB" and a[0]["date"] == "2026-08-30T06:00:00"
    assert a[0]["extrait"] == "Victoire de la Française sur le trail le plus couru." and "img" not in a[0]["extrait"]
    assert a[0]["guid"] == "https://u-trail.com/?p=1"
    assert R.parle_de_trail(a[0]) and not R.parle_de_trail(a[1])
    t2, b = R.lire_flux(ATOM.encode())
    assert t2 == "Blog" and b[0]["lien"] == "https://ex.org/k" and b[0]["date"] == "2026-11-01T12:00:00"
    assert b[0]["extrait"] == "Ultra news"
    with pytest.raises(R.ErreurActualites):
        R.lire_flux('<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "b">]><rss><channel/></rss>')
    with pytest.raises(R.ErreurActualites):
        R.lire_flux("<html><body>pas un flux</body></html>")
    with pytest.raises(R.ErreurActualites):
        R.lire_flux("pas du xml")
    assert len(R.texte_simple("mot " * 200)) <= R.LONGUEUR_EXTRAIT + 1
    lh = {"prenom": "Blandine", "nom": "L'Hirondel", "alias": ["Lhirondel"]}
    assert R.cite(lh, a[0]["titre"]) and R.cite(lh, "Lhirondel en tête") and not R.cite(lh, "Blandine seule")
    assert not R.cite({"prenom": "Tom", "nom": "Evans"}, "Tom Evansville gagne") and R.cite({"prenom": "Tom", "nom": "Evans"}, "EVANS Tom, 1er")
    ref = R.lire_reference()
    assert len(ref["coureurs"]) >= 15 and any(c["pays"] != "FRA" for c in ref["coureurs"])
    assert all(c["palmares"] and c["sources"] and all(s.startswith("https://") for s in c["sources"]) for c in ref["coureurs"])
    assert {s["zone"] for s in ref["sources"]} == {"france", "monde"}
    assert not any("irunfar" in s["url"] for s in ref["sources"])     # site qui refuse les robots


def test_base(base_vide, monkeypatch):
    from noyau.donnees import actualites as dac
    ss = dac.sources()
    assert len(ss) >= 8 and dac.version_reference()
    utrail = next(s for s in ss if s["cle_reference"] == "utrail")
    cs = dac.coureurs()
    lh = next(c for c in cs if c["cle_reference"] == "lhirondel")
    assert lh["pays_nom"] == "France" and lh["palmares"] and dac.coureurs(pays="etranger")
    dac.suivre(lh["id"])
    r = dac.appliquer_flux(utrail["id"], RSS.encode(), maintenant=__import__("datetime").datetime(2026, 11, 6, 9))
    assert r == {"nouveaux": 2, "erreur": None}
    assert dac.appliquer_flux(utrail["id"], RSS.encode())["nouveaux"] == 0           # déjà reçus
    arts = dac.articles()
    assert [x["titre"][:8] for x in arts] == ["Nouvelle", "Blandine"] and arts[1]["coureurs"] == ["Blandine L'Hirondel"]
    assert len(dac.articles(trail_seulement=True)) == 1 and len(dac.articles(coureur_id=lh["id"])) == 1
    assert len(dac.articles(suivis=True)) == 1 and len(dac.articles(zone="monde")) == 0
    assert len(dac.articles(recherche="bitume")) == 1
    dac.marquer_lu([arts[0]["id"]])
    assert len(dac.articles(non_lus=True)) == 1
    dac.definir_favori(arts[1]["id"])
    dac.masquer(arts[0]["id"])
    assert len(dac.articles()) == 1 and len(dac.articles(favoris=True)) == 1
    assert next(c for c in dac.coureurs() if c["id"] == lh["id"])["nb_articles"] == 1
    t = dac.tableau()
    assert t["non_lus"] == 1 and t["coureurs_suivis"] == ["Blandine L'Hirondel"]
    # un nouveau coureur retrouve les articles déjà reçus
    with pytest.raises(dac.ErreurActualites):
        dac.enregistrer_coureur({"nom": "Doe", "sources": "pas une adresse"})
    nid = dac.enregistrer_coureur({"prenom": "Chaussure", "nom": "Nouvelle", "pays": "fra", "palmares": "a\nb",
                                   "sources": "https://ex.org"})
    assert dac.coureur(nid)["palmares"] == ["a", "b"] and dac.coureur(nid)["pays"] == "FRA"
    assert dac.relier(nid) == 1
    # une fiche livrée que tu corriges n'est plus écrasée ; une fiche supprimée ne revient pas
    dac.enregistrer_coureur({**lh, "palmares": "\n".join(lh["palmares"] + ["ma note"]), "sources": "\n".join(lh["sources"])}, lh["id"])
    dac.synchroniser(forcer=True)
    assert dac.coureur(lh["id"])["palmares"][-1] == "ma note"
    j = next(c for c in dac.coureurs() if c["cle_reference"] == "jornet")
    dac.supprimer_coureur(j["id"])
    dac.supprimer_source(utrail["id"])
    dac.synchroniser(forcer=True)
    assert not any(c["cle_reference"] == "jornet" for c in dac.coureurs())
    assert not any(s["cle_reference"] == "utrail" for s in dac.sources())
    assert len(dac.articles(favoris=True)) == 1                       # le favori reste, sans source
    # flux invalide, robots.txt, purge
    s2 = dac.enregistrer_source({"nom": "Mon flux", "url": "https://ex.org/feed", "zone": "monde"})
    assert dac.appliquer_flux(s2, b"<html/>")["erreur"]
    assert dac.appliquer_flux(s2, erreur="le site interdit ... (robots.txt)")["erreur"] and not dac.source(s2)["actif"]
    assert s2 not in [s["id"] for s in dac.a_relire()]
    with pytest.raises(dac.ErreurActualites):
        dac.enregistrer_source({"nom": "x", "url": "ftp://x"})
    monkeypatch.setattr(dac, "autorise_par_robots", lambda url, delai=10: False)
    with pytest.raises(dac.ErreurActualites):
        dac.telecharger("https://ex.org/feed")
    assert dac.purger(aujourdhui=__import__("datetime").datetime(2027, 6, 1)) == 0   # il ne reste que le favori


def test_robots(monkeypatch):
    import io
    import urllib.request
    from noyau.donnees import actualites as dac

    class Rep(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False
    monkeypatch.setattr(urllib.request, "urlopen", lambda req, timeout=10: Rep(b"User-agent: *\nDisallow: /feed\n"))
    assert not dac.autorise_par_robots("https://ex.org/feed/")
    assert dac.autorise_par_robots("https://ex.org/autre")


def test_fenetre(base_vide):
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    from noyau.donnees import actualites as dac
    dac.appliquer_flux(dac.sources()[0]["id"], RSS.encode())
    from interface.actualites import ActualitesFenetre
    f = ActualitesFenetre(athlete_id_initial=1, lecture_auto=False)
    assert f.tabs.count() == 3
    for ec in f.ecrans:
        ec.rafraichir()
    assert f.fil.table.rowCount() == 1                               # « Trail seulement » coché par défaut
    f.fil.trail.setChecked(False)
    assert f.fil.table.rowCount() == 2
    f.coureurs.table.selectRow(0)
    assert "Palmarès" in f.coureurs.fiche.toHtml()
