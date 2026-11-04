"""Ancien emplacement de rythme_vie, gardé pour compatibilité.

Le code est maintenant dans noyau/sante/rythme_vie.py (noyau de
Trail Hub Center). Importer « interface.rythme_vie » donne exactement le même module.
"""
import sys

from noyau.sante import rythme_vie as _module

sys.modules[__name__] = _module
