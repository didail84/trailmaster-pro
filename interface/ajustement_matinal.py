"""Ancien emplacement de ajustement_matinal, gardé pour compatibilité.

Le code est maintenant dans noyau/entrainement/ajustement_matinal.py (noyau de
Trail Hub Center). Importer « interface.ajustement_matinal » donne exactement le même module.
"""
import sys

from noyau.entrainement import ajustement_matinal as _module

sys.modules[__name__] = _module
