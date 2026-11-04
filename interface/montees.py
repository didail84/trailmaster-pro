"""Ancien emplacement de montees, gardé pour compatibilité.

Le code est maintenant dans noyau/traces/montees.py (noyau de
Trail Hub Center). Importer « interface.montees » donne exactement le même module.
"""
import sys

from noyau.traces import montees as _module

sys.modules[__name__] = _module
