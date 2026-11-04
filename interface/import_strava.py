"""Ancien emplacement de import_strava, gardé pour compatibilité.

Le code est maintenant dans noyau/imports/import_strava.py (noyau de
Trail Hub Center). Importer « interface.import_strava » donne exactement le même module.
"""
import sys

from noyau.imports import import_strava as _module

sys.modules[__name__] = _module
