"""Ancien emplacement de certificats_ssl, gardé pour compatibilité.

Le code est maintenant dans noyau/outils/certificats_ssl.py (noyau de
Trail Hub Center). Importer « interface.certificats_ssl » donne exactement le même module.
"""
import sys

from noyau.outils import certificats_ssl as _module

sys.modules[__name__] = _module
