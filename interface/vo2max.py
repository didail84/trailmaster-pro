"""Ancien emplacement de vo2max, gardé pour compatibilité.

Le code est maintenant dans noyau/entrainement/vo2max.py (noyau de
Trail Hub Center). Importer « interface.vo2max » donne exactement le même module.
"""
import sys

from noyau.entrainement import vo2max as _module

sys.modules[__name__] = _module
