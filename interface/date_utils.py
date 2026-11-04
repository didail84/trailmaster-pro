"""Ancien emplacement de date_utils, gardé pour compatibilité.

Le code est maintenant dans noyau/outils/date_utils.py (noyau de
Trail Hub Center). Importer « interface.date_utils » donne exactement le même module.
"""
import sys

from noyau.outils import date_utils as _module

sys.modules[__name__] = _module
