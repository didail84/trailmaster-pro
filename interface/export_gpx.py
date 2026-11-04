"""Ancien emplacement de export_gpx, gardé pour compatibilité.

Le code est maintenant dans noyau/traces/export_gpx.py (noyau de
Trail Hub Center). Importer « interface.export_gpx » donne exactement le même module.
"""
import sys

from noyau.traces import export_gpx as _module

sys.modules[__name__] = _module
