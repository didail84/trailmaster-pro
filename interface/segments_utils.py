"""Ancien emplacement de segments_utils, gardé pour compatibilité.

Le code est maintenant dans noyau/traces/segments_utils.py (noyau de
Trail Hub Center). Importer « interface.segments_utils » donne exactement le même module.
"""
import sys

from noyau.traces import segments_utils as _module

sys.modules[__name__] = _module
