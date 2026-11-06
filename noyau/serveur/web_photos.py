"""
Pages Photos du serveur (étape 7).

- /photos/<événement> : page publique. Le coureur tape son dossard et son
  code personnel ; il voit et télécharge SES photos seulement (aucune
  galerie à parcourir). Trop d'essais ratés depuis une même adresse :
  pause de 10 minutes. Les liens des images sont signés et expirent.
- /m/photos?ev= : un bénévole ou un photographe envoie ses photos depuis son
  téléphone ; les dossards sont lus ensuite (sur le serveur si la lecture
  automatique y est installée, sinon par le logiciel de bureau).
"""

import base64
import hashlib
import hmac
import html
import time
from email import policy
from email.parser import BytesParser

from noyau.serveur import web

DUREE_LIEN_S = 6 * 3600
TAILLE_MAX_ENVOI = 200 * 1024 * 1024


def _e(v):
    return html.escape("" if v is None else str(v))


def _signer(photo_id, inscription_id, expire=None):
    from noyau.serveur.serveur import secret_serveur
    expire = expire or int(time.time()) + DUREE_LIEN_S
    m = f"{photo_id}.{inscription_id}.{expire}"
    s = hmac.new(secret_serveur().encode(), ("photo|" + m).encode(), hashlib.sha256).digest()[:18]
    return base64.urlsafe_b64encode(m.encode()).decode().rstrip("=") + "." + base64.urlsafe_b64encode(s).decode()


def _verifier(jeton):
    from noyau.serveur.serveur import secret_serveur
    try:
        a, sig = jeton.split(".", 1)
        m = base64.urlsafe_b64decode(a + "=" * (-len(a) % 4)).decode()
        attendu = base64.urlsafe_b64encode(hmac.new(secret_serveur().encode(), ("photo|" + m).encode(),
                                                    hashlib.sha256).digest()[:18]).decode()
        if not hmac.compare_digest(sig, attendu):
            return None
        pid, iid, exp = (int(x) for x in m.split("."))
    except (ValueError, UnicodeDecodeError):
        return None
    return (pid, iid) if exp >= time.time() else None


def _formulaire_public(ev, message="", dossard=""):
    m = f"<div class='carte err'>{_e(message)}</div>" if message else ""
    return web.page(f"Mes photos · {ev['nom']}", m + f"""<form method='post' class='carte'>
<label for='d'>Mon numéro de dossard</label><input id='d' name='dossard' class='dossard' inputmode='numeric' value='{_e(dossard)}' required>
<label for='c'>Mon code personnel</label><input id='c' name='code' autocapitalize='characters' autocomplete='off' required>
<button type='submit'>Voir mes photos</button></form>
<p class='petit'>Ton code est dans le message de l'organisation. Tu ne vois que les photos où ton dossard a été reconnu,
et seulement si tous les coureurs visibles ont accepté la diffusion de leur image.</p>""")


def page_publique(handler, reste, verbe, q):
    from noyau.donnees import photos as dph
    from noyau.serveur import serveur as S
    morceaux = reste.strip("/").split("/")
    uuid = morceaux[0] if morceaux else ""
    if len(morceaux) == 3 and morceaux[1] == "i":
        return _image(handler, morceaux[2], q)
    ev = dph.evenement_public(uuid) if uuid else None
    if not ev:
        return handler._envoyer(404, web.page("Photos", "<div class='carte err'>Ces photos ne sont pas (ou plus) en ligne."
                                                        "</div>"))
    if verbe == "GET":
        return handler._envoyer(200, _formulaire_public(ev))
    f = handler._formulaire()
    if S._trop_d_echecs(handler._ip()):
        return handler._envoyer(429, _formulaire_public(ev, "Trop d'essais : réessaie dans 10 minutes.", f.get("dossard", "")))
    acc = dph.acces_public(uuid, f.get("dossard", ""), f.get("code", ""))
    if not acc:
        S._noter_echec(handler._ip())
        return handler._envoyer(200, _formulaire_public(ev, "Dossard ou code incorrect.", f.get("dossard", "")))
    if not acc["photos"]:
        corps = ("<div class='carte att'>Pas encore de photo pour ton dossard. Les photos arrivent au fil des jours après "
                 "la course : reviens plus tard.</div>")
    else:
        corps = (f"<p>{len(acc['photos'])} photo(s) · touche une photo pour l'ouvrir en grand, puis enregistre-la.</p>"
                 + "".join(f"<div class='carte' style='padding:6px'><a href='/photos/{_e(uuid)}/i/{_signer(p['id'], acc['inscription_id'])}"
                           f"?t=grande'><img src='/photos/{_e(uuid)}/i/{_signer(p['id'], acc['inscription_id'])}?t=web' "
                           f"alt='Photo {k}' style='width:100%;height:auto;border-radius:8px;display:block'></a>"
                           f"<a class='petit' href='/photos/{_e(uuid)}/i/{_signer(p['id'], acc['inscription_id'])}?t=grande&amp;dl=1'>"
                           f"⬇️ Télécharger</a></div>" for k, p in enumerate(acc["photos"], 1))
                 + "<p class='petit'>Les liens expirent dans quelques heures : reviens avec ton code pour les rouvrir.</p>")
    return handler._envoyer(200, web.page(f"Mes photos · dossard {acc['dossard']}", corps))


def _image(handler, jeton, q):
    from noyau.donnees import photos as dph
    v = _verifier(jeton)
    if not v:
        return handler._envoyer(403, web.page("Photos", "<div class='carte err'>Lien expiré : reviens avec ton code.</div>"))
    pid, iid = v
    if pid not in {p["id"] for p in dph.photos_du_coureur(iid)}:       # masquée ou retirée depuis
        return handler._envoyer(404, web.page("Photos", "<div class='carte err'>Cette photo n'est plus disponible.</div>"))
    taille = "grande" if q.get("t") == "grande" else "web"
    ent = {}
    if q.get("dl"):
        ent["Content-Disposition"] = f"attachment; filename=photo_{pid}.jpg"
    return handler._envoyer(200, dph.image(pid, taille), "image/jpeg", ent)


# ------------------------------------------------------------------ envoi depuis le téléphone

def lire_multipart(handler):
    """Champs (texte) et fichiers [(nom, octets)] d'un formulaire envoyé avec des fichiers."""
    n = int(handler.headers.get("Content-Length") or 0)
    if n > TAILLE_MAX_ENVOI:
        raise ValueError("Envoi trop gros : envoie tes photos en plusieurs fois (200 Mo au plus).")
    corps = handler.rfile.read(n) if n else b""
    msg = BytesParser(policy=policy.HTTP).parsebytes(
        b"Content-Type: " + (handler.headers.get("Content-Type") or "").encode() + b"\r\n\r\n" + corps)
    champs, fichiers = {}, []
    if not msg.is_multipart():
        return champs, fichiers
    for part in msg.iter_parts():
        nom = part.get_param("name", header="content-disposition")
        fn = part.get_filename()
        data = part.get_payload(decode=True) or b""
        if fn:
            if data:
                fichiers.append((fn, data))
        elif nom:
            champs[nom] = data.decode("utf-8", "replace")
    return champs, fichiers


def gerer_photos(handler, compte, csrf, verbe, chemin, q, f):
    from noyau.donnees import photos as dph, organisation as dor, comptes as dco
    ev_id = int(q.get("ev") or 0)
    if not web.peut_evenement(compte, "photos", ev_id):
        return handler._refus(compte)
    ev = dor.evenement(ev_id)
    msg = ""
    if verbe == "POST":
        fichiers = f.get("_fichiers") or []
        ok = deja = 0
        erreurs = []
        for nom, octets in fichiers:
            try:
                r = dph.importer_contenu(ev_id, nom, octets, "telephone", f.get("photographe") or compte.get("nom_affiche"))
                ok += r["nouvelle"]
                deja += not r["nouvelle"]
            except dph.ErreurPhotos as e:
                erreurs.append(str(e))
        dco.journaliser(compte["id"], compte["identifiant"], "photos", f"evenement {ev_id}", detail=f"{ok} photo(s)",
                        adresse=handler._ip())
        msg = (f"<div class='carte ok'>{ok} photo(s) reçue(s)" + (f", {deja} déjà là" if deja else "") + ". Merci !</div>"
               + (f"<div class='carte err'>{_e('; '.join(erreurs[:5]))}</div>" if erreurs else ""))
    nb = len(dph.photos(ev_id, avec_masquees=True))
    corps = msg + f"""<form method='post' enctype='multipart/form-data' class='carte'>{web._champ_csrf(csrf)}
<label>Photographe</label><input name='photographe' value='{_e(compte.get('nom_affiche') or '')}'>
<label>Photos (tu peux en choisir plusieurs)</label><input type='file' name='photos' accept='image/*' multiple required>
<button type='submit'>Envoyer</button></form>
<p class='petit'>{nb} photo(s) déjà reçues pour cette course. Envoie-les par paquets d'une vingtaine si le réseau est
faible. Les numéros de dossard sont lus ensuite ; aucune photo n'est publiée sans l'accord des coureurs.</p>"""
    return handler._envoyer(200, web.page(f"Photos · {ev['nom']}", corps, compte))


PAGES = {"/m/photos": gerer_photos}
