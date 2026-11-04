"""Ancien emplacement de dynamique_course, gardé pour compatibilité.

Le code est maintenant dans noyau/traces/dynamique_course.py (noyau de
Trail Hub Center). Importer « interface.dynamique_course » donne exactement le même module.
"""
import sys

from noyau.traces import dynamique_course as _module

sys.modules[__name__] = _module
