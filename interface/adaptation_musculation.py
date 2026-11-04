"""Ancien emplacement de adaptation_musculation, gardé pour compatibilité.

Le code est maintenant dans noyau/entrainement/adaptation_musculation.py (noyau de
Trail Hub Center). Importer « interface.adaptation_musculation » donne exactement le même module.
"""
import sys

from noyau.entrainement import adaptation_musculation as _module

sys.modules[__name__] = _module
