"""Ancien emplacement de impact_conditions, gardé pour compatibilité.

Le code est maintenant dans noyau/entrainement/impact_conditions.py (noyau de
Trail Hub Center). Importer « data.impact_conditions » donne exactement le même module.
"""
import sys

from noyau.entrainement import impact_conditions as _module

sys.modules[__name__] = _module
