"""
Lecture automatique des dossards (étape 7), sans Qt ni SQL.

La reconnaissance de caractères tourne sur l'ordinateur, sans Internet
(RapidOCR et ONNX Runtime : modèles livrés avec le module, aucune photo
n'est envoyée nulle part). Si le module n'est pas installé, Trail Hub reste
utilisable : tu saisis les dossards à la main.
"""

_moteur = None
_erreur = None


def disponible():
    """True si la lecture automatique peut tourner sur cet ordinateur."""
    try:
        import rapidocr_onnxruntime  # noqa: F401
        import numpy  # noqa: F401
        return True
    except Exception:              # module absent ou incompatible avec ce système
        return False


def moteur():
    global _moteur, _erreur
    if _moteur is None and _erreur is None:
        try:
            from rapidocr_onnxruntime import RapidOCR
            _moteur = RapidOCR()
        except Exception as e:
            _erreur = str(e)
    return _moteur


def lire(chemin):
    """[(texte, score)] lus sur la photo, ou None si la lecture automatique n'est pas disponible."""
    from noyau.photos import images
    m = moteur()
    if m is None:
        return None
    resultat, _temps = m(images.pour_lecture(chemin))
    return [(str(r[1]), float(r[2])) for r in (resultat or [])]
