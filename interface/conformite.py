"""Ancien emplacement de conformite, gardé pour compatibilité.

Le code est maintenant dans noyau/entrainement/conformite.py (noyau de
Trail Hub Center). Importer « interface.conformite » donne exactement le même module.
"""
import sys

from noyau.entrainement import conformite as _module

sys.modules[__name__] = _module
