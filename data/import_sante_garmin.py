"""Ancien emplacement de import_sante_garmin, gardé pour compatibilité.

Le code est maintenant dans noyau/imports/import_sante_garmin.py (noyau de
Trail Hub Center). Importer « data.import_sante_garmin » donne exactement le même module.
"""
import sys

from noyau.imports import import_sante_garmin as _module

sys.modules[__name__] = _module
