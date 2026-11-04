"""Ancien emplacement de reference_materiel_course, gardé pour compatibilité.

Le code est maintenant dans noyau/course/reference_materiel_course.py (noyau de
Trail Hub Center). Importer « data.reference_materiel_course » donne exactement le même module.
"""
import sys

from noyau.course import reference_materiel_course as _module

sys.modules[__name__] = _module
