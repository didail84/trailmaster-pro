"""Ancien emplacement de evolution_performance, gardé pour compatibilité.

Le code est maintenant dans noyau/entrainement/evolution_performance.py (noyau de
Trail Hub Center). Importer « interface.evolution_performance » donne exactement le même module.
"""
import sys

from noyau.entrainement import evolution_performance as _module

sys.modules[__name__] = _module
