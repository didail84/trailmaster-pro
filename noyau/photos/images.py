"""
Fichiers des photos (étape 7), sans Qt ni SQL : empreinte, date de prise de
vue, tailles, vignette et version allégée pour le web. Pillow sert à lire
les photos ; la photo d'origine n'est jamais modifiée.
"""

import hashlib
import io
from datetime import datetime

TAILLE_VIGNETTE = 360
TAILLE_WEB = 1600
TAILLE_LECTURE = 2400        # la reconnaissance des dossards travaille sur une image de cette taille au plus


def empreinte(chemin):
    h = hashlib.sha256()
    with open(chemin, "rb") as f:
        for bloc in iter(lambda: f.read(1 << 20), b""):
            h.update(bloc)
    return h.hexdigest()


def _ouvrir(chemin):
    from PIL import Image, ImageOps
    try:                                            # photos HEIC des iPhone, si le module est installé
        import pillow_heif
        pillow_heif.register_heif_opener()
    except ImportError:
        pass
    im = Image.open(chemin)
    im = ImageOps.exif_transpose(im)               # photo prise en hauteur : remise droite
    return im.convert("RGB")


def infos(chemin):
    """{largeur, hauteur, prise_le} ; la date vient de l'EXIF (DateTimeOriginal) quand elle existe."""
    from PIL import Image
    with Image.open(chemin) as im:
        l, h = im.size
        prise = None
        try:
            ex = im.getexif()
            brut = ex.get_ifd(0x8769).get(36867) or ex.get(306)
            if brut:
                prise = datetime.strptime(str(brut).strip()[:19], "%Y:%m:%d %H:%M:%S").isoformat()
            o = ex.get(274)
            if o in (5, 6, 7, 8):
                l, h = h, l
        except (ValueError, AttributeError, KeyError, TypeError):
            pass
    return {"largeur": l, "hauteur": h, "prise_le": prise}


def reduite(chemin, cote, qualite=82):
    """JPEG (octets) de la photo réduite à `cote` pixels au plus sur le grand côté, sans les données EXIF
    (ni position GPS, ni appareil)."""
    im = _ouvrir(chemin)
    im.thumbnail((cote, cote))
    out = io.BytesIO()
    im.save(out, "JPEG", quality=qualite, optimize=True)
    return out.getvalue()


def pour_lecture(chemin):
    """Tableau d'image (numpy, BGR) pour la reconnaissance des dossards."""
    import numpy as np
    im = _ouvrir(chemin)
    im.thumbnail((TAILLE_LECTURE, TAILLE_LECTURE))
    return np.array(im)[:, :, ::-1].copy()
