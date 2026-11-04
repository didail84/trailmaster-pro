"""Ancien emplacement de metriques, gardé pour compatibilité.

Le code est maintenant dans noyau/entrainement/metriques.py (noyau de
Trail Hub Center). Importer « data.metriques » donne exactement le même module.
"""
import sys

from noyau.entrainement import metriques as _module

sys.modules[__name__] = _module
