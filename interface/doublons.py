"""Ancien emplacement de doublons, gardé pour compatibilité.

Le code est maintenant dans noyau/traces/doublons.py (noyau de
Trail Hub Center). Importer « interface.doublons » donne exactement le même module.
"""
import sys

from noyau.traces import doublons as _module

sys.modules[__name__] = _module
