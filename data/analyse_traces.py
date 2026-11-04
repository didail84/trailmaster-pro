"""Ancien emplacement de analyse_traces, gardé pour compatibilité.

Le code est maintenant dans noyau/traces/analyse_traces.py (noyau de
Trail Hub Center). Importer « data.analyse_traces » donne exactement le même module.
"""
import sys

from noyau.traces import analyse_traces as _module

sys.modules[__name__] = _module
