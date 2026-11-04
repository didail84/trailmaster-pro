"""Ancien emplacement de coach, gardé pour compatibilité.

Le code est maintenant dans noyau/entrainement/coach.py (noyau de
Trail Hub Center). Importer « interface.coach » donne exactement le même module.
"""
import sys

from noyau.entrainement import coach as _module

sys.modules[__name__] = _module
