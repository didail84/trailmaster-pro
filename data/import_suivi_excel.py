"""Ancien emplacement de import_suivi_excel, gardé pour compatibilité.

Le code est maintenant dans noyau/imports/import_suivi_excel.py (noyau de
Trail Hub Center). Importer « data.import_suivi_excel » donne exactement le même module.
"""
import sys

from noyau.imports import import_suivi_excel as _module

sys.modules[__name__] = _module
