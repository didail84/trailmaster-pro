"""Ancien emplacement de generateur_plan, gardé pour compatibilité.

Le code est maintenant dans noyau/entrainement/generateur_plan.py (noyau de
Trail Hub Center). Importer « interface.generateur_plan » donne exactement le même module.
"""
import sys

from noyau.entrainement import generateur_plan as _module

sys.modules[__name__] = _module
