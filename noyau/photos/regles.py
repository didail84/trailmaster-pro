"""
Photos par dossard (étape 7), sans Qt ni SQL.

1. Lecture : le texte lu sur une photo (par la reconnaissance de caractères,
   sur l'ordinateur, sans Internet) donne des nombres ; on ne garde que ceux
   qui sont des dossards attribués de la course. Une photo est « à vérifier »
   si la lecture hésite ; tu corriges, et ta correction a toujours le
   dernier mot.
2. Droit à l'image : une photo n'est rendue à un coureur que si TOUS les
   coureurs reconnus dessus l'ont accepté ; pour un mineur, il faut en plus
   l'autorisation parentale. Aucune reconnaissance des visages : seuls les
   numéros de dossard servent.
3. Accès : chaque coureur a un code personnel ; avec son dossard, il ne voit
   que ses photos (pas de galerie à parcourir).
"""

import re
import secrets
import unicodedata
from datetime import date

SEUIL_SUR = 0.5              # en dessous : la photo est à vérifier (le filtre des dossards attribués protège déjà)
STATUTS = (("a_lire", "À lire"), ("a_verifier", "À vérifier"), ("lue", "Lue"), ("verifiee", "Vérifiée"),
           ("sans_dossard", "Sans dossard"))
LIBELLE_STATUT = dict(STATUTS)
ALPHABET_CODE = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"     # sans 0/O ni 1/I/L : se dicte et se tape sans erreur
LONGUEUR_CODE = 6
EXTENSIONS = (".jpg", ".jpeg", ".png", ".heic", ".heif", ".webp", ".tif", ".tiff")


def est_photo(nom):
    return str(nom).lower().endswith(EXTENSIONS) and not str(nom).split("/")[-1].startswith(("._", "."))


def numeros(texte):
    """Groupes de 1 à 5 chiffres d'un texte lu (« N°312 », « 57. » → 312, 57)."""
    return [int(x) for x in re.findall(r"(?<!\d)\d{1,5}(?!\d)", str(texte or ""))]


def analyser_lecture(lectures, dossards_connus, seuil=SEUIL_SUR):
    """lectures [(texte, score)], dossards_connus {int} → {dossards: {n: confiance}, statut, doutes: [textes]}.
    Un nombre qui n'est pas un dossard attribué est ignoré, mais rend la photo douteuse s'il ressemble à un dossard
    (même nombre de chiffres qu'un dossard connu) ; un nombre lu qui n'est qu'un morceau d'un dossard plus long
    déjà lu est ignoré."""
    trouves, doutes = {}, []
    longueurs = {len(str(d)) for d in dossards_connus}
    lus = [(n, float(s or 0), t) for t, s in lectures for n in numeros(t)]
    tous = {str(n) for n, _s, _t in lus}
    for n, s, t in lus:
        if any(len(o) > len(str(n)) and str(n) in o and int(o) in dossards_connus for o in tous):
            continue                                     # « 31 » alors que « 312 » est lu aussi
        if n in dossards_connus:
            trouves[n] = max(trouves.get(n, 0), s)
        elif len(str(n)) in longueurs and len(str(n)) >= 2:
            doutes.append(t)
    if not trouves:
        statut = "a_verifier" if doutes else "sans_dossard"
    elif doutes or min(trouves.values()) < seuil:
        statut = "a_verifier"
    else:
        statut = "lue"
    return {"dossards": {n: round(c, 3) for n, c in sorted(trouves.items())}, "statut": statut, "doutes": doutes}


def lire_dossards_saisis(texte):
    """« 57, 312 ; 8 » → [8, 57, 312]."""
    return sorted(set(numeros(texte)))


def nouveau_code():
    return "".join(secrets.choice(ALPHABET_CODE) for _ in range(LONGUEUR_CODE))


def normaliser_code(t):
    """Code tapé par le coureur : majuscules, sans espace ; 0 et O, 1 et I se confondent (jamais générés)."""
    t = unicodedata.normalize("NFKD", str(t or "")).upper().replace("0", "O").replace("1", "I")
    return re.sub(r"[^A-Z0-9]", "", t)


def age_le(date_naissance, jour):
    if not date_naissance:
        return None
    try:
        n = date.fromisoformat(str(date_naissance)[:10])
        j = date.fromisoformat(str(jour)[:10])
    except ValueError:
        return None
    return j.year - n.year - ((j.month, j.day) < (n.month, n.day))


def peut_diffuser(inscription, jour_course, image_personne=None, parental_personne=None):
    """(oui ou non, raison) pour un coureur : accord pour l'image ; mineur → autorisation parentale aussi.
    image_personne / parental_personne : consentements enregistrés sur sa fiche (None = pas de fiche)."""
    accord = bool(inscription.get("droit_image")) or bool(image_personne)
    if not accord:
        return False, "pas d'accord pour l'image"
    a = age_le(inscription.get("date_naissance"), jour_course)
    if a is None and not inscription.get("date_naissance"):
        pass                                             # date inconnue : l'accord du coureur suffit
    elif a is not None and a < 18 and not (inscription.get("autorisation_parentale") or parental_personne):
        return False, "mineur sans autorisation parentale"
    return True, ""


def photo_diffusable(dossards_de_la_photo, diffusion_par_dossard):
    """Une photo n'est diffusée que si chaque coureur reconnu dessus est d'accord (un dossard inconnu bloque aussi)."""
    return bool(dossards_de_la_photo) and all(diffusion_par_dossard.get(d, (False, ""))[0] for d in dossards_de_la_photo)


def nom_zip(dossard, nom, prenom):
    t = unicodedata.normalize("NFKD", f"{dossard}_{nom or ''}_{prenom or ''}").encode("ascii", "ignore").decode()
    return re.sub(r"[^A-Za-z0-9_-]+", "-", t).strip("-_") + ".zip"


def texte_courriel(ev, inscription, code, nb, lien=None, piece_jointe=False):
    """(objet, texte) du message au coureur."""
    nom = f"{inscription.get('prenom') or ''} {inscription.get('nom') or ''}".strip()
    objet = f"Tes photos de {ev['nom']}"
    corps = [f"Bonjour {nom},", "",
             f"Merci d'avoir couru {ev['nom']} ! Nos photographes bénévoles t'ont pris en photo : {nb} photo(s) "
             f"où l'on voit ton dossard {inscription.get('dossard')}.", ""]
    if lien:
        corps += [f"Pour les voir et les télécharger : {lien}", f"Ton dossard : {inscription.get('dossard')}",
                  f"Ton code personnel : {code}", "", "Garde ce code pour toi : il ouvre tes photos seulement."]
    elif piece_jointe:
        corps += ["Tes photos sont jointes à ce message."]
    corps += ["", "Si une photo ne te convient pas, réponds à ce message : nous la retirerons.", "",
              "Sportivement,", ev.get("photos_message") or "L'organisation"]
    return objet, "\n".join(corps)


def lien_direct(url):
    """Lien de partage → adresse de téléchargement direct quand c'est possible (Dropbox, Google Drive pour un
    fichier), sinon l'adresse telle quelle. Renvoie (adresse, conseil)."""
    u = str(url or "").strip()
    if not u.startswith(("http://", "https://")):
        return None, "L'adresse doit commencer par https://"
    m = re.match(r"https://(www\.)?dropbox\.com/(.+?)(\?.*)?$", u)
    if m:
        q = (m.group(3) or "").lstrip("?")
        q = "&".join(x for x in q.split("&") if x and not x.startswith("dl=")) if q else ""
        return f"https://www.dropbox.com/{m.group(2)}?" + (q + "&" if q else "") + "dl=1", ""
    m = re.match(r"https://drive\.google\.com/(file/d/|open\?id=|uc\?id=)([\w-]+)", u)
    if m:
        return f"https://drive.google.com/uc?export=download&id={m.group(2)}", ""
    if "drive.google.com/drive/folders" in u:
        return None, ("Un dossier Google Drive ne se télécharge pas automatiquement : ouvre-le, choisis "
                      "« Tout télécharger » (un zip), puis importe le zip.")
    if "wetransfer.com" in u or "we.tl" in u:
        return None, ("WeTransfer ne permet pas le téléchargement automatique : ouvre le lien, télécharge le zip, "
                      "puis importe-le.")
    return u, ""
