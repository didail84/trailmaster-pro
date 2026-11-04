"""Ancien emplacement de comparaison_courses, gardé pour compatibilité.

Le code est maintenant dans noyau/entrainement/comparaison_courses.py (noyau de
Trail Hub Center). Importer « interface.comparaison_courses » donne exactement le même module.
"""
import sys

from noyau.entrainement import comparaison_courses as _module

sys.modules[__name__] = _module
