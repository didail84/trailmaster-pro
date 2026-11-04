"""Ancien emplacement de estimation_temps_course, gardé pour compatibilité.

Le code est maintenant dans noyau/course/estimation_temps_course.py (noyau de
Trail Hub Center). Importer « data.estimation_temps_course » donne exactement le même module.
"""
import sys

from noyau.course import estimation_temps_course as _module

sys.modules[__name__] = _module
