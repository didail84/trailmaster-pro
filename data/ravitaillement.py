"""Ancien emplacement de ravitaillement, gardé pour compatibilité.

Le code est maintenant dans noyau/course/ravitaillement.py (noyau de
Trail Hub Center). Importer « data.ravitaillement » donne exactement le même module.
"""
import sys

from noyau.course import ravitaillement as _module

sys.modules[__name__] = _module
