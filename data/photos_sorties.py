"""
Photos des sorties : copie réduite (800 ou 1600 pixels sur le grand côté,
au choix) dans le dossier géré par l'appli, à côté de la base
(photos/sorties/), avec lecture de la date de prise de vue et de la
position GPS quand le fichier les contient (EXIF).

Le rattachement automatique à une sortie se fait par la date : d'abord
l'heure exacte (photo prise pendant la sortie, à 20 minutes près), sinon
le même jour. Les photos enregistrées par WhatsApp n'ont plus d'EXIF :
la date est alors lue dans le nom du fichier (IMG-20261019-WA0003.jpg,
« WhatsApp Image 2026-10-19 at 07.55.12 ») puis, à défaut, dans la date
du fichier.

Le fichier d'origine n'est jamais modifié ni déplacé.
"""

import hashlib
import re
import struct
from datetime import datetime, timedelta
from pathlib import Path

from data import database as bdd
from data.database import connexion, obtenir_parametre, definir_parametre

EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif", ".tif", ".tiff")
TAILLES_DISPONIBLES = (800, 1600)
TAILLE_PAR_DEFAUT = 1600
TOLERANCE_MIN = 20


# ------------------------------------------------------------------
# Dossier et réglage
# ------------------------------------------------------------------

def dossier_photos():
    dossier = Path(bdd.CHEMIN_BDD).parent / "photos" / "sorties"
    dossier.mkdir(parents=True, exist_ok=True)
    return dossier


def chemin_photo(fichier):
    return dossier_photos() / fichier


def taille_max():
    try:
        valeur = int(obtenir_parametre("photos_taille_max", TAILLE_PAR_DEFAUT))
    except (TypeError, ValueError):
        valeur = TAILLE_PAR_DEFAUT
    return valeur if valeur in TAILLES_DISPONIBLES else TAILLE_PAR_DEFAUT


def definir_taille_max(valeur):
    if int(valeur) in TAILLES_DISPONIBLES:
        definir_parametre("photos_taille_max", int(valeur))


# ------------------------------------------------------------------
# Lecture EXIF minimale (JPEG) — sans dépendance externe
# ------------------------------------------------------------------

def _lire_exif(chemin):
    """Retourne {'date': datetime|None, 'lat': float|None, 'lon': float|None}."""
    resultat = {"date": None, "lat": None, "lon": None}
    try:
        with open(chemin, "rb") as f:
            en_tete = f.read(2)
            if en_tete != b"\xff\xd8":
                return resultat
            while True:
                marqueur = f.read(2)
                if len(marqueur) < 2 or marqueur[0] != 0xFF:
                    return resultat
                if marqueur[1] == 0xDA:     # début des données image
                    return resultat
                taille = struct.unpack(">H", f.read(2))[0]
                bloc = f.read(taille - 2)
                if marqueur[1] == 0xE1 and bloc[:6] == b"Exif\x00\x00":
                    return _analyser_tiff(bloc[6:], resultat)
    except Exception:
        return resultat


def _analyser_tiff(t, resultat):
    ordre = "<" if t[:2] == b"II" else ">"

    def u16(o): return struct.unpack(ordre + "H", t[o:o + 2])[0]
    def u32(o): return struct.unpack(ordre + "I", t[o:o + 4])[0]

    TAILLES = {1: 1, 2: 1, 3: 2, 4: 4, 5: 8, 7: 1, 9: 4, 10: 8}

    def lire_ifd(offset):
        entrees = {}
        n = u16(offset)
        for i in range(n):
            e = offset + 2 + 12 * i
            tag, typ, nb = u16(e), u16(e + 2), u32(e + 4)
            taille = TAILLES.get(typ, 1) * nb
            pos = e + 8 if taille <= 4 else u32(e + 8)
            entrees[tag] = (typ, nb, pos)
        return entrees

    def texte(entree):
        _, nb, pos = entree
        return t[pos:pos + nb].split(b"\x00")[0].decode("ascii", "ignore")

    def rationnels(entree):
        _, nb, pos = entree
        return [u32(pos + 8 * i) / max(u32(pos + 8 * i + 4), 1) for i in range(nb)]

    try:
        ifd0 = lire_ifd(u32(4))
        def pointeur(entrees, tag):
            # LONG unique stocké en ligne : « pos » est l'adresse de la valeur
            return u32(entrees[tag][2]) if tag in entrees else None

        date_txt = None
        p_exif = pointeur(ifd0, 0x8769)
        if p_exif:
            ifd_exif = lire_ifd(p_exif)
            if 0x9003 in ifd_exif:
                date_txt = texte(ifd_exif[0x9003])
        if not date_txt and 0x0132 in ifd0:
            date_txt = texte(ifd0[0x0132])
        if date_txt:
            try:
                resultat["date"] = datetime.strptime(date_txt.strip(), "%Y:%m:%d %H:%M:%S")
            except ValueError:
                pass

        p_gps = pointeur(ifd0, 0x8825)
        if p_gps:
            gps = lire_ifd(p_gps)
            if 2 in gps and 4 in gps:
                def degres(v):
                    return v[0] + v[1] / 60 + v[2] / 3600
                lat = degres(rationnels(gps[2]))
                lon = degres(rationnels(gps[4]))
                if 1 in gps and texte(gps[1]).upper().startswith("S"):
                    lat = -lat
                if 3 in gps and texte(gps[3]).upper().startswith("W"):
                    lon = -lon
                if (lat or lon) and abs(lat) <= 90 and abs(lon) <= 180:
                    resultat["lat"], resultat["lon"] = round(lat, 6), round(lon, 6)
    except Exception:
        pass
    return resultat


_MOTIFS_NOM = [
    re.compile(r"(?:IMG|VID|PXL|PHOTO)[-_](\d{4})(\d{2})(\d{2})"),
    re.compile(r"(\d{4})-(\d{2})-(\d{2}) at (\d{2})\.(\d{2})\.(\d{2})"),
    re.compile(r"(\d{4})(\d{2})(\d{2})[_-](\d{2})(\d{2})(\d{2})"),
    re.compile(r"(\d{4})-(\d{2})-(\d{2})"),
]


def _date_depuis_nom(nom):
    """(datetime, avec_heure) lu dans le nom du fichier, ou (None, False)."""
    for motif in _MOTIFS_NOM:
        m = motif.search(nom)
        if not m:
            continue
        g = [int(x) for x in m.groups()]
        try:
            if len(g) >= 6:
                return datetime(g[0], g[1], g[2], g[3], g[4], g[5]), True
            return datetime(g[0], g[1], g[2], 12, 0, 0), False
        except ValueError:
            continue
    return None, False


def date_de_la_photo(chemin, exif=None):
    """(datetime, avec_heure, origine) : EXIF, sinon nom du fichier, sinon date du fichier."""
    exif = exif if exif is not None else _lire_exif(chemin)
    if exif["date"]:
        return exif["date"], True, "exif"
    d, avec_heure = _date_depuis_nom(Path(chemin).name)
    if d:
        return d, avec_heure, "nom"
    try:
        return datetime.fromtimestamp(Path(chemin).stat().st_mtime), False, "fichier"
    except OSError:
        return None, False, None


# ------------------------------------------------------------------
# Rattachement à une sortie
# ------------------------------------------------------------------

def _debut_et_fin(date_txt, duree_s):
    try:
        debut = datetime.fromisoformat(str(date_txt)[:19])
    except ValueError:
        return None, None
    return debut, debut + timedelta(seconds=duree_s or 0)


def trouver_activite(athlete_id, date_photo, avec_heure=True):
    """Id de la sortie qui correspond à la date de la photo, ou None."""
    if date_photo is None:
        return None
    jour = date_photo.strftime("%Y-%m-%d")
    conn = connexion()
    cur = conn.cursor()
    cur.execute(
        "SELECT id, date, duree FROM activites WHERE athlete_id=? AND substr(date,1,10)=? ORDER BY date",
        (athlete_id, jour),
    )
    lignes = cur.fetchall()
    conn.close()
    if not lignes:
        return None
    if avec_heure:
        tol = timedelta(minutes=TOLERANCE_MIN)
        for id_, d, duree in lignes:
            debut, fin = _debut_et_fin(d, duree)
            if debut and debut - tol <= date_photo <= fin + tol:
                return id_
    # Même jour : la sortie la plus proche de l'heure de la photo (ou la plus longue)
    if avec_heure:
        def ecart(l):
            debut, _ = _debut_et_fin(l[1], l[2])
            return abs((debut - date_photo).total_seconds()) if debut else 1e12
        return min(lignes, key=ecart)[0]
    return max(lignes, key=lambda l: l[2] or 0)[0]


# ------------------------------------------------------------------
# Ajout, lecture, suppression
# ------------------------------------------------------------------

def _empreinte(chemin):
    h = hashlib.sha1()
    with open(chemin, "rb") as f:
        for bloc in iter(lambda: f.read(1 << 20), b""):
            h.update(bloc)
    return h.hexdigest()


def _reduire_et_enregistrer(chemin_source, destination, cote_max):
    """Redimensionne (orientation EXIF respectée) et enregistre en JPEG.
    Retourne (largeur, hauteur) ou None si l'image est illisible."""
    from PySide6.QtGui import QImageReader, QImage
    from PySide6.QtCore import Qt
    lecteur = QImageReader(str(chemin_source))
    lecteur.setAutoTransform(True)
    image = lecteur.read()
    if image.isNull():
        return None
    if max(image.width(), image.height()) > cote_max:
        image = image.scaled(cote_max, cote_max, Qt.AspectRatioMode.KeepAspectRatio,
                             Qt.TransformationMode.SmoothTransformation)
    if image.hasAlphaChannel():
        fond = QImage(image.size(), QImage.Format.Format_RGB32)
        fond.fill(0xFFFFFFFF)
        from PySide6.QtGui import QPainter
        p = QPainter(fond)
        p.drawImage(0, 0, image)
        p.end()
        image = fond
    if not image.save(str(destination), "JPEG", 85):
        return None
    return image.width(), image.height()


def ajouter_photo(chemin_source, athlete_id, activite_id=None, legende="",
                  rattacher_auto=True, source="manuel"):
    """Ajoute une photo. Retourne {'id', 'activite_id', 'doublon', 'erreur'}."""
    chemin_source = Path(chemin_source)
    if chemin_source.suffix.lower() not in EXTENSIONS or not chemin_source.exists():
        return {"id": None, "activite_id": None, "doublon": False, "erreur": "format non pris en charge"}

    empreinte = _empreinte(chemin_source)
    conn = connexion()
    cur = conn.cursor()
    cur.execute("SELECT id, activite_id FROM photos_sorties WHERE athlete_id=? AND empreinte=?",
                (athlete_id, empreinte))
    existante = cur.fetchone()
    if existante:
        conn.close()
        return {"id": existante[0], "activite_id": existante[1], "doublon": True, "erreur": None}

    exif = _lire_exif(chemin_source)
    date_photo, avec_heure, _ = date_de_la_photo(chemin_source, exif)

    nom = f"p{athlete_id}_{empreinte[:12]}.jpg"
    dimensions = _reduire_et_enregistrer(chemin_source, chemin_photo(nom), taille_max())
    if dimensions is None:
        conn.close()
        return {"id": None, "activite_id": None, "doublon": False, "erreur": "image illisible"}

    if activite_id is None and rattacher_auto:
        activite_id = trouver_activite(athlete_id, date_photo, avec_heure)

    cur.execute(
        "INSERT INTO photos_sorties (athlete_id, activite_id, fichier, legende, date_prise, "
        "latitude, longitude, largeur, hauteur, empreinte, source) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (athlete_id, activite_id, nom, legende or None,
         date_photo.strftime("%Y-%m-%d %H:%M:%S") if date_photo else None,
         exif["lat"], exif["lon"], dimensions[0], dimensions[1], empreinte, source),
    )
    id_ = cur.lastrowid
    conn.commit()
    conn.close()
    return {"id": id_, "activite_id": activite_id, "doublon": False, "erreur": None}


def importer_dossier(dossier, athlete_id, progression=None, recursif=True):
    """Ajoute toutes les photos d'un dossier. Retourne un compte rendu."""
    dossier = Path(dossier)
    fichiers = sorted(p for p in (dossier.rglob("*") if recursif else dossier.glob("*"))
                      if p.is_file() and p.suffix.lower() in EXTENSIONS)
    bilan = {"total": len(fichiers), "ajoutees": 0, "rattachees": 0, "sans_sortie": 0,
             "doublons": 0, "erreurs": 0}
    for i, fichier in enumerate(fichiers):
        r = ajouter_photo(fichier, athlete_id, source="dossier")
        if r["erreur"]:
            bilan["erreurs"] += 1
        elif r["doublon"]:
            bilan["doublons"] += 1
        else:
            bilan["ajoutees"] += 1
            if r["activite_id"]:
                bilan["rattachees"] += 1
            else:
                bilan["sans_sortie"] += 1
        if progression:
            progression(i + 1, len(fichiers))
    return bilan


_COLONNES = ("id, athlete_id, activite_id, fichier, legende, date_prise, latitude, longitude, "
             "largeur, hauteur")


def _en_dict(ligne):
    cles = [c.strip() for c in _COLONNES.split(",")]
    return dict(zip(cles, ligne))


def photos_de_sortie(activite_id):
    conn = connexion()
    cur = conn.cursor()
    cur.execute(f"SELECT {_COLONNES} FROM photos_sorties WHERE activite_id=? "
                "ORDER BY date_prise, id", (activite_id,))
    lignes = [_en_dict(l) for l in cur.fetchall()]
    conn.close()
    return lignes


def photos_galerie(athlete_id, annee=None, type_sortie=None, sans_sortie=False, texte=None):
    """Photos de l'athlète, les plus récentes d'abord, avec filtres optionnels.
    Chaque dict contient aussi 'sortie_nom', 'sortie_type', 'sortie_date'."""
    requete = ("SELECT p.id, p.athlete_id, p.activite_id, p.fichier, p.legende, p.date_prise, "
               "p.latitude, p.longitude, p.largeur, p.hauteur, a.nom, a.type, a.date "
               "FROM photos_sorties p LEFT JOIN activites a ON a.id = p.activite_id "
               "WHERE p.athlete_id=?")
    params = [athlete_id]
    if annee:
        requete += " AND substr(COALESCE(p.date_prise, a.date, p.date_ajout),1,4)=?"
        params.append(str(annee))
    if type_sortie:
        requete += " AND a.type=?"
        params.append(type_sortie)
    if sans_sortie:
        requete += " AND p.activite_id IS NULL"
    if texte:
        requete += " AND (p.legende LIKE ? OR a.nom LIKE ?)"
        params += [f"%{texte}%", f"%{texte}%"]
    requete += " ORDER BY COALESCE(p.date_prise, a.date, p.date_ajout) DESC, p.id DESC"
    conn = connexion()
    cur = conn.cursor()
    cur.execute(requete, params)
    cles = [c.strip() for c in _COLONNES.split(",")] + ["sortie_nom", "sortie_type", "sortie_date"]
    lignes = [dict(zip(cles, l)) for l in cur.fetchall()]
    conn.close()
    return lignes


def options_filtres(athlete_id):
    """(annees, types) présents dans la galerie, pour remplir les filtres."""
    conn = connexion()
    cur = conn.cursor()
    cur.execute("SELECT DISTINCT substr(COALESCE(p.date_prise, a.date, p.date_ajout),1,4) "
                "FROM photos_sorties p LEFT JOIN activites a ON a.id=p.activite_id "
                "WHERE p.athlete_id=? ORDER BY 1 DESC", (athlete_id,))
    annees = [r[0] for r in cur.fetchall() if r[0]]
    cur.execute("SELECT DISTINCT a.type FROM photos_sorties p JOIN activites a ON a.id=p.activite_id "
                "WHERE p.athlete_id=? AND a.type IS NOT NULL ORDER BY 1", (athlete_id,))
    types = [r[0] for r in cur.fetchall()]
    conn.close()
    return annees, types


def modifier_photo(photo_id, **champs):
    permis = {k: v for k, v in champs.items() if k in ("legende", "activite_id")}
    if not permis:
        return
    conn = connexion()
    cur = conn.cursor()
    cur.execute(f"UPDATE photos_sorties SET {', '.join(k + '=?' for k in permis)} WHERE id=?",
                (*permis.values(), photo_id))
    conn.commit()
    conn.close()


def supprimer_photo(photo_id):
    """Retire la photo de la base et supprime sa copie réduite (jamais l'original)."""
    conn = connexion()
    cur = conn.cursor()
    cur.execute("SELECT fichier FROM photos_sorties WHERE id=?", (photo_id,))
    ligne = cur.fetchone()
    cur.execute("DELETE FROM photos_sorties WHERE id=?", (photo_id,))
    conn.commit()
    conn.close()
    if ligne:
        try:
            chemin_photo(ligne[0]).unlink()
        except OSError:
            pass


def position_sur_trace(photo, points, debut_activite=None):
    """(lat, lon) où placer la photo sur la carte : sa position GPS si elle
    en a une, sinon la position du tracé à l'heure de la photo (trace avec
    temps seulement). None si on ne peut pas la situer."""
    if photo.get("latitude") is not None and photo.get("longitude") is not None:
        return photo["latitude"], photo["longitude"]
    if not (points and debut_activite and photo.get("date_prise")):
        return None
    try:
        t = (datetime.fromisoformat(photo["date_prise"]) - datetime.fromisoformat(str(debut_activite)[:19])
             ).total_seconds()
    except ValueError:
        return None
    temps = [(p[3], p) for p in points if len(p) > 3 and p[3] is not None]
    if len(temps) < 2 or t < -TOLERANCE_MIN * 60 or t > temps[-1][0] + TOLERANCE_MIN * 60:
        return None
    meilleur = min(temps, key=lambda tp: abs(tp[0] - t))[1]
    return meilleur[0], meilleur[1]
