"""Ancien emplacement de replanification, gardé pour compatibilité.

Le code est maintenant dans noyau/entrainement/replanification.py (noyau de
Trail Hub Center). Importer « interface.replanification » donne exactement le même module.
"""
import sys

from noyau.entrainement import replanification as _module

sys.modules[__name__] = _module
