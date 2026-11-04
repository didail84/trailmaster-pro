"""Ancien emplacement de sommeil_auto, gardé pour compatibilité.

Le code est maintenant dans noyau/sante/sommeil_auto.py (noyau de
Trail Hub Center). Importer « data.sommeil_auto » donne exactement le même module.
"""
import sys

from noyau.sante import sommeil_auto as _module

sys.modules[__name__] = _module
