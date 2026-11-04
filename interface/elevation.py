"""Ancien emplacement de elevation, gardé pour compatibilité.

Le code est maintenant dans noyau/traces/elevation.py (noyau de
Trail Hub Center). Importer « interface.elevation » donne exactement le même module.
"""
import sys

from noyau.traces import elevation as _module

sys.modules[__name__] = _module
