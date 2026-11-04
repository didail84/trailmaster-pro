"""Ancien emplacement de serveur_local, gardé pour compatibilité.

Le code est maintenant dans noyau/services/serveur_local.py (noyau de
Trail Hub Center). Importer « interface.serveur_local » donne exactement le même module.
"""
import sys

from noyau.services import serveur_local as _module

sys.modules[__name__] = _module
