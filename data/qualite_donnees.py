"""Ancien emplacement de qualite_donnees, gardé pour compatibilité.

Le code est maintenant dans noyau/entrainement/qualite_donnees.py (noyau de
Trail Hub Center). Importer « data.qualite_donnees » donne exactement le même module.
"""
import sys

from noyau.entrainement import qualite_donnees as _module

sys.modules[__name__] = _module
