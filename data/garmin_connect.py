"""Ancien emplacement de garmin_connect, gardé pour compatibilité.

Le code est maintenant dans noyau/imports/garmin_connect.py (noyau de
Trail Hub Center). Importer « data.garmin_connect » donne exactement le même module.
"""
import sys

from noyau.imports import garmin_connect as _module

sys.modules[__name__] = _module
