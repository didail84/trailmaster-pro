"""Ancien emplacement de analyse_technique, gardé pour compatibilité.

Le code est maintenant dans noyau/ia/analyse_technique.py (noyau de
Trail Hub Center). Importer « interface.analyse_technique » donne exactement le même module.
"""
import sys

from noyau.ia import analyse_technique as _module

sys.modules[__name__] = _module
