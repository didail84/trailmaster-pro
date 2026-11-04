"""Ancien emplacement de meteo, gardé pour compatibilité.

Le code est maintenant dans noyau/outils/meteo.py (noyau de
Trail Hub Center). Importer « interface.meteo » donne exactement le même module.
"""
import sys

from noyau.outils import meteo as _module

sys.modules[__name__] = _module
