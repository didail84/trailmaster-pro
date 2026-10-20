"""
Certificats SSL pour les connexions internet de TrailMaster (Strava, mises
à jour, météo, IA...).

Sur Mac, un Python installé via Homebrew ou une appli empaquetée n'a pas
toujours accès aux certificats racine : toute connexion HTTPS échoue alors
avec « certificate verify failed », alors qu'internet fonctionne très bien.
Plutôt que de demander une manipulation à la main, on indique à Python où
trouver un jeu de certificats valide au démarrage : celui du paquet
« certifi » s'il est installé, sinon celui fourni par le système
(macOS : /etc/ssl/cert.pem).
"""

import os
import ssl
import sys


CHEMINS_SYSTEME = [
    "/etc/ssl/cert.pem",                                   # macOS
    "/opt/homebrew/etc/ca-certificates/cert.pem",          # Homebrew Apple Silicon
    "/usr/local/etc/ca-certificates/cert.pem",             # Homebrew Intel
    "/etc/ssl/certs/ca-certificates.crt",                  # Linux
]


def configurer_certificats_ssl():
    """Renvoie le chemin du fichier de certificats retenu (ou None si
    rien de mieux que le réglage par défaut n'a été trouvé)."""

    # Sous Windows, Python utilise déjà le magasin de certificats du
    # système — y compris le certificat de l'entreprise si un proxy
    # inspecte le trafic HTTPS. Le remplacer par certifi casserait ces
    # connexions : on n'y touche donc pas.
    if sys.platform.startswith("win"):
        return None

    candidats = []
    try:
        import certifi
        candidats.append(certifi.where())
    except ImportError:
        pass
    candidats.extend(CHEMINS_SYSTEME)

    for chemin in candidats:
        if chemin and os.path.isfile(chemin):
            os.environ["SSL_CERT_FILE"] = chemin
            ssl._create_default_https_context = (
                lambda *args, _chemin=chemin, **kwargs: ssl.create_default_context(cafile=_chemin)
            )
            return chemin
    return None
