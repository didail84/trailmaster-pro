"""Ancien emplacement de completer_activites, gardé pour compatibilité.

Le code est maintenant dans noyau/imports/completer_activites.py (noyau de
Trail Hub Center). Importer « data.completer_activites » donne exactement le même module.
"""
import sys

from noyau.imports import completer_activites as _module

sys.modules[__name__] = _module
