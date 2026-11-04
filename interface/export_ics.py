"""Ancien emplacement de export_ics, gardé pour compatibilité.

Le code est maintenant dans noyau/entrainement/export_ics.py (noyau de
Trail Hub Center). Importer « interface.export_ics » donne exactement le même module.
"""
import sys

from noyau.entrainement import export_ics as _module

sys.modules[__name__] = _module
