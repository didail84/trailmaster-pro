"""Ancien emplacement de meilleurs_efforts, gardé pour compatibilité.

Le code est maintenant dans noyau/traces/meilleurs_efforts.py (noyau de
Trail Hub Center). Importer « data.meilleurs_efforts » donne exactement le même module.
"""
import sys

from noyau.traces import meilleurs_efforts as _module

sys.modules[__name__] = _module
