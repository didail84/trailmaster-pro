"""Ancien emplacement de estimations_basses, gardé pour compatibilité.

Le code est maintenant dans noyau/entrainement/estimations_basses.py (noyau de
Trail Hub Center). Importer « interface.estimations_basses » donne exactement le même module.
"""
import sys

from noyau.entrainement import estimations_basses as _module

sys.modules[__name__] = _module
