"""Ancien emplacement de coach_du_jour, gardé pour compatibilité.

Le code est maintenant dans noyau/entrainement/coach_du_jour.py (noyau de
Trail Hub Center). Importer « data.coach_du_jour » donne exactement le même module.
"""
import sys

from noyau.entrainement import coach_du_jour as _module

sys.modules[__name__] = _module
