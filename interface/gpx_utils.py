"""Ancien emplacement de gpx_utils, gardé pour compatibilité.

Le code est maintenant dans noyau/traces/gpx_utils.py (noyau de
Trail Hub Center). Importer « interface.gpx_utils » donne exactement le même module.
"""
import sys

from noyau.traces import gpx_utils as _module

sys.modules[__name__] = _module
