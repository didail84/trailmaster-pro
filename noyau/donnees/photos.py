"""
Accès aux données des Photos par dossard (étape 7).

Les photos sont rangées dans le dossier des données (photos/courses/<événement>/,
jamais dans la base ni sur GitHub) ; la base garde leur empreinte (une photo
importée deux fois n'apparaît qu'une fois), les dossards lus ou corrigés,
les codes d'accès des coureurs et l'historique des envois.

Toutes les fonctions passent les photos en octets : elles marchent pareil en
local et quand le logiciel est branché sur le serveur du club.
"""

import io
import json
import shutil
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path

from noyau.donnees import base
from noyau.photos import regles as R, images as IM


class ErreurPhotos(Exception):
    """Message lisible ; rien n'a été modifié."""


COL = ("id", "evenement_id", "fichier", "nom_origine", "empreinte", "prise_le", "photographe", "source", "largeur",
       "hauteur", "statut", "lecture_json", "lue_le", "masquee", "importee_le", "uuid")
TAILLE_MAX_PHOTO = 60 * 1024 * 1024


def _maintenant():
    return datetime.now().isoformat(timespec="seconds")


def racine():
    import data.database as db
    return Path(db.CHEMIN_BDD).parent / "photos" / "courses"


def _ev(evenement_id):
    l = base.lire_un("SELECT id, nom, date_debut, uuid, photos_ouvertes, photos_message, commune FROM evenements WHERE id=?",
                     (evenement_id,))
    if not l:
        raise ErreurPhotos("Événement introuvable.")
    return dict(zip(("id", "nom", "date_debut", "uuid", "photos_ouvertes", "photos_message", "commune"), l))


def evenement_photos(evenement_id):
    """{id, nom, date_debut, uuid, photos_ouvertes, photos_message, commune} de l'événement."""
    return _ev(evenement_id)


def dossier(evenement_id):
    d = racine() / _ev(evenement_id)["uuid"]
    d.mkdir(parents=True, exist_ok=True)
    return d


def _photo(l):
    p = dict(zip(COL, l))
    p["lecture"] = json.loads(p.pop("lecture_json") or "null")
    return p


def photo(photo_id):
    l = base.lire_un(f"SELECT {', '.join(COL)} FROM photos_course WHERE id=?", (photo_id,))
    if not l:
        return None
    p = _photo(l)
    p["dossards"] = [d for d, in base.lire_tous("SELECT dossard FROM photos_dossards WHERE photo_id=? ORDER BY dossard",
                                                (photo_id,))]
    return p


def _chemin(p):
    return racine() / p["fichier"]


def dossards_attribues(evenement_id):
    return {r[0] for r in base.lire_tous(
        "SELECT i.dossard FROM inscriptions i JOIN epreuves p ON p.id = i.epreuve_id WHERE p.evenement_id=? "
        "AND i.dossard IS NOT NULL AND i.statut NOT IN ('annulee', 'liste_attente')", (evenement_id,))}


# ------------------------------------------------------------------ import

def importer_contenu(evenement_id, nom, contenu, source="dossier", photographe=None, lectures=None):
    """Range une photo (octets) dans le dossier de l'événement. lectures [(texte, score)] : la lecture déjà faite
    sur l'ordinateur qui importe. Renvoie {id, nouvelle}."""
    if not R.est_photo(nom):
        raise ErreurPhotos(f"{nom} : ce n'est pas une photo (JPEG, PNG, HEIC…).")
    if len(contenu) > TAILLE_MAX_PHOTO:
        raise ErreurPhotos(f"{nom} : photo trop grosse (plus de 60 Mo).")
    ev = _ev(evenement_id)
    d = dossier(evenement_id)
    tmp = Path(tempfile.mkstemp(dir=d, suffix=".tmp")[1])
    try:
        tmp.write_bytes(contenu)
        emp = IM.empreinte(tmp)
        deja = base.lire_un("SELECT id FROM photos_course WHERE evenement_id=? AND empreinte=?", (evenement_id, emp))
        if deja:
            return {"id": deja[0], "nouvelle": False}
        try:
            inf = IM.infos(tmp)
        except Exception:
            raise ErreurPhotos(f"{nom} : photo illisible.")
        ext = Path(nom).suffix.lower() or ".jpg"
        final = d / f"{emp[:20]}{ext}"
        shutil.move(str(tmp), final)
    finally:
        if tmp.exists():
            tmp.unlink()
    pid = base.inserer("photos_course", {"evenement_id": evenement_id, "fichier": f"{ev['uuid']}/{final.name}",
                                         "nom_origine": Path(nom).name[:200], "empreinte": emp, "prise_le": inf["prise_le"],
                                         "photographe": (photographe or "")[:120] or None, "source": source,
                                         "largeur": inf["largeur"], "hauteur": inf["hauteur"], "statut": "a_lire",
                                         "importee_le": _maintenant()})
    if lectures is not None:
        enregistrer_lecture(pid, lectures)
    return {"id": pid, "nouvelle": True}


def importer_zip(evenement_id, contenu, source="zip", photographe=None, lire=None):
    """Toutes les photos d'un zip (octets). lire(chemin) → lectures, ou None. Renvoie {importees, deja, erreurs}."""
    res = {"importees": 0, "deja": 0, "erreurs": []}
    try:
        z = zipfile.ZipFile(io.BytesIO(contenu))
    except zipfile.BadZipFile:
        raise ErreurPhotos("Ce fichier n'est pas un zip lisible.")
    with tempfile.TemporaryDirectory() as tmpd:
        for info in z.infolist():
            if info.is_dir() or not R.est_photo(info.filename) or "__MACOSX" in info.filename:
                continue
            if info.file_size > TAILLE_MAX_PHOTO:
                res["erreurs"].append(f"{info.filename} : trop grosse")
                continue
            octets = z.read(info)
            lect = None
            if lire:
                f = Path(tmpd) / Path(info.filename).name
                f.write_bytes(octets)
                try:
                    lect = lire(f)
                except Exception:
                    lect = None
            try:
                r = importer_contenu(evenement_id, Path(info.filename).name, octets, source, photographe, lect)
                res["importees" if r["nouvelle"] else "deja"] += 1
            except ErreurPhotos as e:
                res["erreurs"].append(str(e))
    return res


def telecharger_lien(url, delai=60, maxi=4 * 1024 ** 3):
    """Télécharge un lien de partage direct (zip ou photo) dans un fichier temporaire. Renvoie le chemin.
    Réseau : à appeler hors de l'écran."""
    import urllib.request
    direct, conseil = R.lien_direct(url)
    if not direct:
        raise ErreurPhotos(conseil)
    req = urllib.request.Request(direct, headers={"User-Agent": "TrailHubCenter/1.0 (photos de course)"})
    fd, chemin = tempfile.mkstemp(suffix=".zip")
    n = 0
    with urllib.request.urlopen(req, timeout=delai) as r, open(fd, "wb") as out:
        if "text/html" in (r.headers.get("Content-Type") or ""):
            raise ErreurPhotos("Ce lien ouvre une page, pas un fichier : télécharge le zip depuis la page, puis importe-le.")
        while True:
            b = r.read(1 << 20)
            if not b:
                break
            n += len(b)
            if n > maxi:
                raise ErreurPhotos("Fichier trop gros (plus de 4 Go).")
            out.write(b)
    return chemin


# ------------------------------------------------------------------ lecture des dossards

def a_lire(evenement_id=None, n=50):
    sql = "SELECT id FROM photos_course WHERE statut='a_lire' AND masquee=0"
    par = ()
    if evenement_id:
        sql += " AND evenement_id=?"
        par = (evenement_id,)
    return [r[0] for r in base.lire_tous(sql + " ORDER BY id LIMIT ?", par + (int(n),))]


def enregistrer_lecture(photo_id, lectures):
    """Lecture automatique d'une photo. Ne touche pas une photo déjà vérifiée par toi."""
    p = photo(photo_id)
    if not p or p["statut"] == "verifiee":
        return None
    a = R.analyser_lecture(lectures or [], dossards_attribues(p["evenement_id"]))
    with base.transaction() as cur:
        cur.execute("DELETE FROM photos_dossards WHERE photo_id=? AND origine='auto'", (photo_id,))
        for d, conf in a["dossards"].items():
            cur.execute("INSERT OR IGNORE INTO photos_dossards (photo_id, dossard, origine, confiance) VALUES (?, ?, 'auto', ?)",
                        (photo_id, d, conf))
        cur.execute("UPDATE photos_course SET statut=?, lecture_json=?, lue_le=? WHERE id=?",
                    (a["statut"], json.dumps({"textes": [[t, round(float(sc), 3)] for t, sc in lectures or []][:40], "doutes": a["doutes"]},
                                             ensure_ascii=False), _maintenant(), photo_id))
    return a


def lire_sur_place(photo_id):
    """Lecture faite par la machine qui garde les photos (serveur du club, ou ce poste en local)."""
    from noyau.photos import lecture
    p = photo(photo_id)
    if not p:
        return None
    l = lecture.lire(_chemin(p))
    return None if l is None else enregistrer_lecture(photo_id, l)


def definir_dossards(photo_id, dossards):
    """Ta correction : la liste exacte des dossards de la photo (vide = personne de reconnaissable)."""
    p = photo(photo_id)
    if not p:
        raise ErreurPhotos("Photo introuvable.")
    ds = sorted(set(int(d) for d in (R.lire_dossards_saisis(dossards) if isinstance(dossards, str) else dossards)))
    inconnus = [d for d in ds if d not in dossards_attribues(p["evenement_id"])]
    if inconnus:
        raise ErreurPhotos(f"Dossard(s) non attribué(s) sur cette course : {', '.join(map(str, inconnus))}.")
    with base.transaction() as cur:
        cur.execute("DELETE FROM photos_dossards WHERE photo_id=?", (photo_id,))
        for d in ds:
            cur.execute("INSERT INTO photos_dossards (photo_id, dossard, origine, confiance) VALUES (?, ?, 'manuel', 1)",
                        (photo_id, d))
        cur.execute("UPDATE photos_course SET statut='verifiee' WHERE id=?", (photo_id,))
    return ds


def valider(photo_ids):
    """La lecture automatique est juste : les photos passent à « vérifiée »."""
    for i in ([photo_ids] if isinstance(photo_ids, int) else photo_ids):
        base.ecrire("UPDATE photos_course SET statut='verifiee' WHERE id=? AND statut != 'a_lire'", (i,))


def masquer(photo_id, masquee=True):
    """Une photo masquée (floue, ratée, à la demande du coureur) n'est plus jamais diffusée."""
    base.ecrire("UPDATE photos_course SET masquee=? WHERE id=?", (1 if masquee else 0, photo_id))


def supprimer_photo(photo_id):
    p = photo(photo_id)
    if not p:
        return
    base.ecrire("DELETE FROM photos_course WHERE id=?", (photo_id,))
    c = _chemin(p)
    for f in (c, c.parent / ".vignette" / f"{p['empreinte'][:20]}.jpg", c.parent / ".web" / f"{p['empreinte'][:20]}.jpg"):
        try:
            f.unlink()
        except OSError:
            pass


def photos(evenement_id, statut=None, dossard=None, avec_masquees=False, limite=5000):
    sql = f"SELECT {', '.join('p.' + c for c in COL)} FROM photos_course p WHERE p.evenement_id=?"
    par = [evenement_id]
    if not avec_masquees:
        sql += " AND p.masquee=0"
    if statut == "masquees":
        sql = sql.replace(" AND p.masquee=0", "") + " AND p.masquee=1"
    elif statut:
        sql += " AND p.statut=?"
        par.append(statut)
    if dossard is not None:
        sql += " AND p.id IN (SELECT photo_id FROM photos_dossards WHERE dossard=?)"
        par.append(int(dossard))
    res = [_photo(l) for l in base.lire_tous(sql + " ORDER BY COALESCE(p.prise_le, p.importee_le), p.id LIMIT ?",
                                              tuple(par) + (int(limite),))]
    ds = {}
    if res:
        for pid, d in base.lire_tous("SELECT x.photo_id, x.dossard FROM photos_dossards x JOIN photos_course p ON p.id = "
                                     "x.photo_id WHERE p.evenement_id=? ORDER BY x.dossard", (evenement_id,)):
            ds.setdefault(pid, []).append(d)
    for p in res:
        p["dossards"] = ds.get(p["id"], [])
    return res


def image(photo_id, taille="vignette"):
    """Octets JPEG de la photo réduite (« vignette », « web », « lecture », « grande »), sans EXIF."""
    p = photo(photo_id)
    if not p:
        raise ErreurPhotos("Photo introuvable.")
    cote = {"vignette": IM.TAILLE_VIGNETTE, "web": IM.TAILLE_WEB, "lecture": IM.TAILLE_LECTURE, "grande": 4000}[taille]
    if taille in ("vignette", "web"):                    # gardées à côté des photos : la galerie s'ouvre vite
        cache = _chemin(p).parent / f".{taille}" / f"{p['empreinte'][:20]}.jpg"
        try:
            return cache.read_bytes()
        except OSError:
            pass
        octets = IM.reduite(_chemin(p), cote, 78 if taille == "vignette" else 86)
        try:
            cache.parent.mkdir(exist_ok=True)
            cache.write_bytes(octets)
        except OSError:
            pass
        return octets
    return IM.reduite(_chemin(p), cote, 88)


# ------------------------------------------------------------------ diffusion

def _inscrits(evenement_id):
    cles = ("id", "personne_id", "nom", "prenom", "sexe", "date_naissance", "email", "dossard", "autorisation_parentale",
            "droit_image", "epreuve")
    return [dict(zip(cles, l)) for l in base.lire_tous(
        "SELECT i.id, i.personne_id, i.nom, i.prenom, i.sexe, i.date_naissance, i.email, i.dossard, i.autorisation_parentale, "
        "i.droit_image, p.nom FROM inscriptions i JOIN epreuves p ON p.id = i.epreuve_id WHERE p.evenement_id=? AND "
        "i.dossard IS NOT NULL AND i.statut NOT IN ('annulee', 'liste_attente') ORDER BY i.dossard", (evenement_id,))]


def _consentement(personne_id, type_):
    if not personne_id:
        return None
    try:
        from noyau.donnees import comptes as dco
        return dco.a_consenti(personne_id, type_)
    except Exception:
        return None


def diffusion(evenement_id):
    """Pour chaque coureur : ses photos, celles qu'on peut lui rendre, la raison sinon, son code. Et les photos
    retenues (un coureur dessus n'a pas donné son accord)."""
    ev = _ev(evenement_id)
    ins = _inscrits(evenement_id)
    droit = {}
    for i in ins:
        droit[i["dossard"]] = R.peut_diffuser(i, ev["date_debut"], _consentement(i["personne_id"], "image"),
                                              _consentement(i["personne_id"], "parental"))
    codes = dict(base.lire_tous("SELECT a.inscription_id, a.code FROM photos_acces a JOIN inscriptions i ON i.id = "
                                "a.inscription_id JOIN epreuves p ON p.id = i.epreuve_id WHERE p.evenement_id=?",
                                (evenement_id,)))
    envois = {r[0]: r[1] for r in base.lire_tous(
        "SELECT e.inscription_id, MAX(e.envoye_le) FROM photos_envois e JOIN inscriptions i ON i.id = e.inscription_id "
        "JOIN epreuves p ON p.id = i.epreuve_id WHERE p.evenement_id=? AND e.reussi=1 GROUP BY e.inscription_id", (evenement_id,))}
    ph = photos(evenement_id)
    retenues = [p for p in ph if p["dossards"] and not R.photo_diffusable(p["dossards"], droit)]
    par_dossard = {}
    for p in ph:
        for d in p["dossards"]:
            par_dossard.setdefault(d, []).append(p)
    res = []
    for i in ins:
        lp = par_dossard.get(i["dossard"], [])
        ok = [p for p in lp if R.photo_diffusable(p["dossards"], droit) and p["statut"] in ("lue", "verifiee")]
        res.append({**i, "inscription_id": i["id"], "nb_photos": len(lp), "nb_diffusables": len(ok),
                    "diffusable": droit[i["dossard"]][0], "raison": droit[i["dossard"]][1],
                    "code": codes.get(i["id"]), "envoye_le": envois.get(i["id"])})
    st = {s: 0 for s, _l in R.STATUTS}
    for p in ph:
        st[p["statut"]] = st.get(p["statut"], 0) + 1
    return {"evenement": ev, "coureurs": res, "retenues": len(retenues), "photos": len(ph), "statuts": st,
            "avec_photos": sum(1 for c in res if c["nb_diffusables"])}


def generer_codes(evenement_id):
    """Un code personnel pour chaque coureur qui n'en a pas. Renvoie le nombre de codes créés."""
    n = 0
    with base.transaction() as cur:
        for i in _inscrits(evenement_id):
            if not cur.execute("SELECT 1 FROM photos_acces WHERE inscription_id=?", (i["id"],)).fetchone():
                cur.execute("INSERT INTO photos_acces (inscription_id, code, cree_le) VALUES (?, ?, ?)",
                            (i["id"], R.nouveau_code(), _maintenant()))
                n += 1
    return n


def ouvrir_photos(evenement_id, ouvertes=True, message=None):
    """Ouvre (ou ferme) la page publique des photos de l'événement sur le serveur."""
    base.ecrire("UPDATE evenements SET photos_ouvertes=?, photos_message=? WHERE id=?",
                (1 if ouvertes else 0, (message or "").strip() or None, evenement_id))
    if ouvertes:
        generer_codes(evenement_id)


def photos_du_coureur(inscription_id):
    """Les photos qu'on peut rendre à ce coureur (lues ou vérifiées, non masquées, tous les coureurs dessus d'accord)."""
    l = base.lire_un("SELECT p.evenement_id, i.dossard FROM inscriptions i JOIN epreuves p ON p.id = i.epreuve_id WHERE i.id=?",
                     (inscription_id,))
    if not l or l[1] is None:
        return []
    d = diffusion(l[0])
    droit = {c["dossard"]: (c["diffusable"], c["raison"]) for c in d["coureurs"]}
    return [p for p in photos(l[0], dossard=l[1]) if p["statut"] in ("lue", "verifiee")
            and R.photo_diffusable(p["dossards"], droit)]


def acces_public(evenement_uuid, dossard, code):
    """Page publique : (événement, inscription, photos) si le dossard et le code vont ensemble, sinon None."""
    l = base.lire_un("SELECT id FROM evenements WHERE uuid=? AND photos_ouvertes=1", (str(evenement_uuid),))
    if not l:
        return None
    try:
        dossard = int(str(dossard).strip())
    except ValueError:
        return None
    r = base.lire_un("SELECT i.id, a.code FROM inscriptions i JOIN epreuves p ON p.id = i.epreuve_id JOIN photos_acces a ON "
                     "a.inscription_id = i.id WHERE p.evenement_id=? AND i.dossard=? AND i.statut NOT IN ('annulee', "
                     "'liste_attente')", (l[0], dossard))
    import hmac
    if not r or not hmac.compare_digest(R.normaliser_code(code), R.normaliser_code(r[1])):
        return None
    base.ecrire("UPDATE photos_acces SET vues = vues + 1, derniere_vue=? WHERE inscription_id=?", (_maintenant(), r[0]))
    return {"evenement": _ev(l[0]), "inscription_id": r[0], "dossard": dossard, "photos": photos_du_coureur(r[0])}


def evenement_public(evenement_uuid):
    l = base.lire_un("SELECT id FROM evenements WHERE uuid=? AND photos_ouvertes=1", (str(evenement_uuid),))
    return _ev(l[0]) if l else None


def zip_coureur(inscription_id):
    """Octets d'un zip avec les photos du coureur (grande taille, sans EXIF)."""
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_STORED) as z:
        for k, p in enumerate(photos_du_coureur(inscription_id), 1):
            z.writestr(f"photo_{k:03d}.jpg", image(p["id"], "grande"))
    return out.getvalue()


def noter_envoi(inscription_id, canal, reussi=True, detail=None):
    base.inserer("photos_envois", {"inscription_id": inscription_id, "canal": canal, "envoye_le": _maintenant(),
                                   "reussi": 1 if reussi else 0, "detail": (detail or "")[:300] or None})


def photos_de_la_personne(personne_id):
    """Pour le profil du licencié : [{evenement, date, photo_id}] des photos qu'on peut lui rendre."""
    res = []
    for iid, ev, jour in base.lire_tous(
            "SELECT i.id, e.nom, e.date_debut FROM inscriptions i JOIN epreuves p ON p.id = i.epreuve_id JOIN evenements e "
            "ON e.id = p.evenement_id WHERE i.personne_id=? AND i.dossard IS NOT NULL ORDER BY e.date_debut DESC", (personne_id,)):
        res += [{"evenement": ev, "date": jour, "photo_id": p["id"], "inscription_id": iid} for p in photos_du_coureur(iid)]
    return res


def codes(evenement_id):
    """[(dossard, nom, prénom, épreuve, code)] pour la liste à remettre au retrait des dossards."""
    generer_codes(evenement_id)
    return base.lire_tous("SELECT i.dossard, i.nom, i.prenom, p.nom, a.code FROM inscriptions i JOIN epreuves p ON p.id = "
                          "i.epreuve_id JOIN photos_acces a ON a.inscription_id = i.id WHERE p.evenement_id=? AND i.dossard "
                          "IS NOT NULL AND i.statut NOT IN ('annulee', 'liste_attente') ORDER BY i.dossard", (evenement_id,))


def tableau(evenement_id):
    d = diffusion(evenement_id)
    return {"photos": d["photos"], "statuts": d["statuts"], "retenues": d["retenues"], "coureurs_avec_photos": d["avec_photos"],
            "ouvertes": bool(d["evenement"]["photos_ouvertes"]),
            "sans_accord": sum(1 for c in d["coureurs"] if not c["diffusable"])}
