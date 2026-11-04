"""Ancien emplacement de strava_sync, gardé pour compatibilité.

Le code est maintenant dans noyau/imports/strava_sync.py (noyau de
Trail Hub Center). Importer « interface.strava_sync » donne exactement le même module.
"""
import sys

from noyau.imports import strava_sync as _module

sys.modules[__name__] = _module
