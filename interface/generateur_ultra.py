"""Ancien emplacement de generateur_ultra, gardé pour compatibilité.

Le code est maintenant dans noyau/entrainement/generateur_ultra.py (noyau de
Trail Hub Center). Importer « interface.generateur_ultra » donne exactement le même module.
"""
import sys

from noyau.entrainement import generateur_ultra as _module

sys.modules[__name__] = _module
