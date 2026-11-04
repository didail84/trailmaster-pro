"""Ancien emplacement de tactique_course, gardé pour compatibilité.

Le code est maintenant dans noyau/course/tactique_course.py (noyau de
Trail Hub Center). Importer « interface.tactique_course » donne exactement le même module.
"""
import sys

from noyau.course import tactique_course as _module

sys.modules[__name__] = _module
