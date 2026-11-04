"""Ancien emplacement de import_garmin_json, gardé pour compatibilité.

Le code est maintenant dans noyau/imports/import_garmin_json.py (noyau de
Trail Hub Center). Importer « interface.import_garmin_json » donne exactement le même module.
"""
import sys

from noyau.imports import import_garmin_json as _module

sys.modules[__name__] = _module
