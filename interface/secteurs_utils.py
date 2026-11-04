"""Ancien emplacement de secteurs_utils, gardé pour compatibilité.

Le code est maintenant dans noyau/traces/secteurs_utils.py (noyau de
Trail Hub Center). Importer « interface.secteurs_utils » donne exactement le même module.
"""
import sys

from noyau.traces import secteurs_utils as _module

sys.modules[__name__] = _module
