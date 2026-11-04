"""Ancien emplacement de orchestrateur, gardé pour compatibilité.

Le code est maintenant dans noyau/services/orchestrateur.py (noyau de
Trail Hub Center). Importer « data.orchestrateur » donne exactement le même module.
"""
import sys

from noyau.services import orchestrateur as _module

sys.modules[__name__] = _module
