"""Ancien emplacement de records, gardé pour compatibilité.

Le code est maintenant dans noyau/entrainement/records.py (noyau de
Trail Hub Center). Importer « interface.records » donne exactement le même module.
"""
import sys

from noyau.entrainement import records as _module

sys.modules[__name__] = _module
