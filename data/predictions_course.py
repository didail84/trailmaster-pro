"""Ancien emplacement de predictions_course, gardé pour compatibilité.

Le code est maintenant dans noyau/course/predictions_course.py (noyau de
Trail Hub Center). Importer « data.predictions_course » donne exactement le même module.
"""
import sys

from noyau.course import predictions_course as _module

sys.modules[__name__] = _module
