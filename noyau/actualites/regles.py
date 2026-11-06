"""
Actualités du trail (chantier F), sans Qt ni SQL.

On lit les flux RSS ou Atom que les sites publient pour être repris. On ne
garde que le titre, la date, un court extrait en texte (300 caractères au
plus, sans image) et le lien vers l'article, qui s'ouvre sur le site.
Les coureurs connus sont retrouvés dans les titres et extraits par leur nom
complet ou leurs autres graphies.
"""

import html
import json
import re
import unicodedata
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

FICHIER_REFERENCE = Path(__file__).resolve().parents[2] / "data" / "actualites" / "reference.json"
LONGUEUR_EXTRAIT = 300
ZONES = (("france", "France"), ("monde", "Monde"))
LIBELLE_ZONE = dict(ZONES)
PAYS = {"FRA": "France", "ESP": "Espagne", "USA": "États-Unis", "GBR": "Royaume-Uni", "NZL": "Nouvelle-Zélande",
        "ITA": "Italie", "SUI": "Suisse", "CAN": "Canada", "NEP": "Népal", "AUS": "Australie", "BEL": "Belgique",
        "AUT": "Autriche", "GER": "Allemagne", "NOR": "Norvège", "SWE": "Suède", "CHN": "Chine", "JPN": "Japon",
        "RSA": "Afrique du Sud", "MEX": "Mexique", "POR": "Portugal"}
MOTS_TRAIL = ("trail", "ultra", "utmb", "skyrunning", "course en montagne", "kilomètre vertical", "km vertical",
              "diagonale", "western states", "hardrock", "d+", "dénivelé", "mountain running", "100 miles", "sentier")


class ErreurActualites(Exception):
    """Message lisible ; rien n'a été modifié."""


def lire_reference(chemin=None):
    return json.loads(Path(chemin or FICHIER_REFERENCE).read_text(encoding="utf-8"))


def _local(tag):
    return tag.rsplit("}", 1)[-1].lower()


def _enfant(el, *noms):
    for c in el:
        if _local(c.tag) in noms:
            return c
    return None


def _texte(el):
    return "".join(el.itertext()).strip() if el is not None else ""


def texte_simple(t, maxi=LONGUEUR_EXTRAIT):
    """HTML → texte court, sans balise ni image ; coupé au mot près."""
    t = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", t or "")
    t = re.sub(r"(?s)<[^>]+>", " ", t)
    t = html.unescape(t)
    t = re.sub(r"\s+", " ", t).strip()
    t = re.sub(r"\s*(The post|L’article|L'article) .{0,200} (appeared first on|est apparu en premier sur) .*$", "", t)
    if len(t) > maxi:
        t = t[:maxi].rsplit(" ", 1)[0].rstrip(",;:.") + "…"
    return t


def lire_date(t):
    """RFC 822 (RSS) ou ISO 8601 (Atom) → « AAAA-MM-JJTHH:MM:SS » en heure UTC, ou None."""
    if not t:
        return None
    t = t.strip()
    try:
        d = parsedate_to_datetime(t)
    except (TypeError, ValueError, IndexError):
        try:
            d = datetime.fromisoformat(t.replace("Z", "+00:00"))
        except ValueError:
            return None
    if d.tzinfo:
        d = d.astimezone(timezone.utc).replace(tzinfo=None)
    return d.isoformat(timespec="seconds")


def lire_flux(contenu):
    """Contenu d'un flux RSS 2.0, RSS 1.0 ou Atom → (titre du flux, [{guid, titre, lien, date, extrait}])."""
    if isinstance(contenu, bytes):
        brut = contenu
    else:
        brut = (contenu or "").encode("utf-8")
    debut = brut[:3000].lower()
    if b"<!doctype" in debut or b"<!entity" in brut[:20000].lower():
        raise ErreurActualites("Ce flux contient des déclarations non admises (DOCTYPE) : lecture refusée.")
    try:
        racine = ET.fromstring(brut)
    except ET.ParseError as e:
        raise ErreurActualites(f"Ce n'est pas un flux RSS lisible ({e}).")
    nom = _local(racine.tag)
    articles, titre = [], ""
    if nom == "feed":                                       # Atom
        titre = _texte(_enfant(racine, "title"))
        elements = [c for c in racine if _local(c.tag) == "entry"]
    else:                                                   # RSS 2.0 (rss/channel/item) ou RSS 1.0 (rdf:RDF/item)
        canal = _enfant(racine, "channel")
        titre = _texte(_enfant(canal, "title")) if canal is not None else ""
        elements = [c for c in (canal if canal is not None and _enfant(canal, "item") is not None else racine)
                    if _local(c.tag) == "item"]
    if nom not in ("feed", "rss", "rdf"):
        raise ErreurActualites("Ce n'est pas un flux RSS ou Atom.")
    for it in elements:
        t = texte_simple(_texte(_enfant(it, "title")), 250)
        lien = ""
        for c in it:
            if _local(c.tag) == "link":
                if c.get("href") and c.get("rel", "alternate") == "alternate":
                    lien = c.get("href")
                    break
                if (c.text or "").strip():
                    lien = c.text.strip()
                    break
        if not lien.startswith(("http://", "https://")):
            lien = ""
        guid = _texte(_enfant(it, "guid", "id")) or lien or t
        d = lire_date(_texte(_enfant(it, "pubdate", "published", "updated", "date")))
        resume = _enfant(it, "description", "summary")
        if resume is None or not _texte(resume):
            resume = _enfant(it, "encoded", "content")
        if not t or not lien:
            continue
        articles.append({"guid": guid[:500], "titre": t, "lien": lien[:1000], "date": d,
                         "extrait": texte_simple(_texte(resume))})
    return titre, articles


def _norm(t):
    t = unicodedata.normalize("NFKD", str(t or "")).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[’'`\-]", " ", t)


def formes_du_nom(coureur):
    """Graphies cherchées : « Prénom Nom », « Nom Prénom » et les autres graphies (alias)."""
    p, n = coureur.get("prenom") or "", coureur.get("nom") or ""
    formes = {f"{p} {n}".strip(), f"{n} {p}".strip()} | {a for a in (coureur.get("alias") or []) if a}
    return sorted({re.sub(r"\s+", " ", _norm(f)).strip() for f in formes if len(f.strip()) >= 4})


def cite(coureur, texte):
    """Le coureur est-il cité dans ce texte (mot entier) ?"""
    t = " " + re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", _norm(texte))) + " "
    return any(f" {re.sub(r'[^a-z0-9 ]', ' ', f)} " in t for f in formes_du_nom(coureur))


def coureurs_cites(coureurs, article):
    texte = f"{article.get('titre', '')} {article.get('extrait', '')}"
    return [c["id"] for c in coureurs if cite(c, texte)]


def parle_de_trail(article):
    t = _norm(f"{article.get('titre', '')} {article.get('extrait', '')}")
    return any(_norm(m) in t for m in MOTS_TRAIL)
