"""Ancien emplacement de ia_coach, gardé pour compatibilité.

Le code est maintenant dans noyau/ia/ia_coach.py (noyau de
Trail Hub Center). Importer « interface.ia_coach » donne exactement le même module.
"""
import sys

from noyau.ia import ia_coach as _module

sys.modules[__name__] = _module
