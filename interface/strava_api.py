"""Ancien emplacement de strava_api, gardé pour compatibilité.

Le code est maintenant dans noyau/imports/strava_api.py (noyau de
Trail Hub Center). Importer « interface.strava_api » donne exactement le même module.
"""
import sys

from noyau.imports import strava_api as _module

sys.modules[__name__] = _module
