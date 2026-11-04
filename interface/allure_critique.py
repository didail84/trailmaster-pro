"""Ancien emplacement de allure_critique, gardé pour compatibilité.

Le code est maintenant dans noyau/entrainement/allure_critique.py (noyau de
Trail Hub Center). Importer « interface.allure_critique » donne exactement le même module.
"""
import sys

from noyau.entrainement import allure_critique as _module

sys.modules[__name__] = _module
