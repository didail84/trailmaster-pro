"""Ancien emplacement de roadbook, gardé pour compatibilité.

Le code est maintenant dans noyau/course/roadbook.py (noyau de
Trail Hub Center). Importer « data.roadbook » donne exactement le même module.
"""
import sys

from noyau.course import roadbook as _module

sys.modules[__name__] = _module
