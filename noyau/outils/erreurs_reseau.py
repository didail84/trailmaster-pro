"""
Message d'erreur clair pour les échecs de requête réseau.

Sur Mac, l'erreur la plus fréquente n'est PAS un vrai problème de
connexion internet mais l'absence des certificats SSL racine — ça
arrive systématiquement avec Python installé depuis python.org tant
qu'on n'a pas lancé "Install Certificates.command" une fois. Sans ce
diagnostic, l'erreur remontée par Python (URLError) est la même dans
les deux cas et induit en erreur.
"""


def message_erreur_reseau(erreur):
    texte_erreur = str(getattr(erreur, "reason", erreur)).lower()

    if "certificate" in texte_erreur or "ssl" in texte_erreur:
        return (
            "Problème de certificats SSL (pas vraiment un problème d'internet). "
            "Ferme complètement TrailMaster puis relance-le ; si ça persiste, dans le "
            "Terminal tape : launchctl setenv SSL_CERT_FILE /etc/ssl/cert.pem — puis "
            "rouvre TrailMaster et réessaie."
        )

    return f"Pas de connexion internet ou service indisponible ({getattr(erreur, 'reason', erreur)})"
