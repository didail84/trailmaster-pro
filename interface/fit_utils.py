"""Ancien emplacement de fit_utils, gardé pour compatibilité.

Le code est maintenant dans noyau/traces/fit_utils.py (noyau de
Trail Hub Center). Importer « interface.fit_utils » donne exactement le même module.
"""
import sys

from noyau.traces import fit_utils as _module

sys.modules[__name__] = _module
