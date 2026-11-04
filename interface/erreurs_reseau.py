"""Ancien emplacement de erreurs_reseau, gardé pour compatibilité.

Le code est maintenant dans noyau/outils/erreurs_reseau.py (noyau de
Trail Hub Center). Importer « interface.erreurs_reseau » donne exactement le même module.
"""
import sys

from noyau.outils import erreurs_reseau as _module

sys.modules[__name__] = _module
