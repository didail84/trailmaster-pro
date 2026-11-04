"""Ancien emplacement de mensurations, gardé pour compatibilité.

Le code est maintenant dans noyau/sante/mensurations.py (noyau de
Trail Hub Center). Importer « data.mensurations » donne exactement le même module.
"""
import sys

from noyau.sante import mensurations as _module

sys.modules[__name__] = _module
