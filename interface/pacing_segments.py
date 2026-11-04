"""Ancien emplacement de pacing_segments, gardé pour compatibilité.

Le code est maintenant dans noyau/course/pacing_segments.py (noyau de
Trail Hub Center). Importer « interface.pacing_segments » donne exactement le même module.
"""
import sys

from noyau.course import pacing_segments as _module

sys.modules[__name__] = _module
