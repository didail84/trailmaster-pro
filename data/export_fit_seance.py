"""Ancien emplacement de export_fit_seance, gardé pour compatibilité.

Le code est maintenant dans noyau/entrainement/export_fit_seance.py (noyau de
Trail Hub Center). Importer « data.export_fit_seance » donne exactement le même module.
"""
import sys

from noyau.entrainement import export_fit_seance as _module

sys.modules[__name__] = _module
