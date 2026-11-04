"""Ancien emplacement de puissance, gardé pour compatibilité.

Le code est maintenant dans noyau/traces/puissance.py (noyau de
Trail Hub Center). Importer « interface.puissance » donne exactement le même module.
"""
import sys

from noyau.traces import puissance as _module

sys.modules[__name__] = _module
