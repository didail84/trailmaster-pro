"""
Envoi des photos par e-mail (étape 7), sans Qt ni SQL : un message par
coureur, par le serveur d'envoi (SMTP) de ta messagerie ou de celle du club.
Le mot de passe est gardé dans le trousseau de l'ordinateur, jamais dans la
base.
"""

import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr, make_msgid

TAILLE_MAX_PIECES = 15 * 1024 * 1024          # au-delà, beaucoup de messageries refusent le message
SERVICE_TROUSSEAU = "TrailHubCenter-smtp"


class ErreurCourriel(Exception):
    """Message lisible."""


def message(expediteur, nom_expediteur, destinataire, objet, texte, pieces=()):
    m = EmailMessage()
    m["From"] = formataddr((nom_expediteur or "", expediteur))
    m["To"] = destinataire
    m["Subject"] = objet
    m["Message-ID"] = make_msgid(domain=expediteur.split("@")[-1] if "@" in expediteur else None)
    m.set_content(texte)
    total = 0
    for nom, octets in pieces:
        total += len(octets)
        if total > TAILLE_MAX_PIECES:
            break
        m.add_attachment(octets, maintype="image", subtype="jpeg", filename=nom)
    return m


def connexion(config, mot_de_passe, delai=30):
    """config {hote, port, securite: 'ssl'|'starttls'|'aucune', identifiant}."""
    hote, port = config.get("hote"), int(config.get("port") or 587)
    if not hote:
        raise ErreurCourriel("Indique le serveur d'envoi (SMTP) de ta messagerie dans les réglages d'envoi.")
    ctx = ssl.create_default_context()
    try:
        if config.get("securite") == "ssl":
            s = smtplib.SMTP_SSL(hote, port, timeout=delai, context=ctx)
        else:
            s = smtplib.SMTP(hote, port, timeout=delai)
            if config.get("securite", "starttls") == "starttls":
                s.starttls(context=ctx)
        if config.get("identifiant"):
            s.login(config["identifiant"], mot_de_passe or "")
        return s
    except smtplib.SMTPAuthenticationError:
        raise ErreurCourriel("Identifiant ou mot de passe d'envoi refusé (pour Gmail, il faut un « mot de passe "
                             "d'application »).")
    except (OSError, smtplib.SMTPException) as e:
        raise ErreurCourriel(f"Connexion au serveur d'envoi impossible : {e}")


def mot_de_passe(identifiant):
    try:
        import keyring
        return keyring.get_password(SERVICE_TROUSSEAU, identifiant or "")
    except Exception:
        return None


def garder_mot_de_passe(identifiant, mdp):
    import keyring
    keyring.set_password(SERVICE_TROUSSEAU, identifiant or "", mdp)
