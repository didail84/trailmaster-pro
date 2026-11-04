"""Ancien emplacement de reference_alimentation, gardé pour compatibilité.

Le code est maintenant dans noyau/course/reference_alimentation.py (noyau de
Trail Hub Center). Importer « data.reference_alimentation » donne exactement le même module.
"""
import sys

from noyau.course import reference_alimentation as _module

sys.modules[__name__] = _module
