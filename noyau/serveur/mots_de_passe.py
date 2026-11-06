"""
Mots de passe des comptes du serveur : jamais stockés en clair. PBKDF2-SHA256
(bibliothèque standard), sel aléatoire, 310 000 itérations ; format
« pbkdf2_sha256$itérations$sel$empreinte ». Comparaison en temps constant.
"""

import base64
import hashlib
import hmac
import secrets

ITERATIONS = 310_000
LONGUEUR_MIN = 10


class ErreurMotDePasse(Exception):
    """Message lisible."""


def verifier_solidite(mdp, identifiant=""):
    """Au moins 10 caractères, pas l'identifiant, au moins deux sortes de caractères (lettres, chiffres,
    autres). Lève ErreurMotDePasse sinon."""
    mdp = mdp or ""
    if len(mdp) < LONGUEUR_MIN:
        raise ErreurMotDePasse(f"Le mot de passe doit faire au moins {LONGUEUR_MIN} caractères.")
    if identifiant and identifiant.lower() in mdp.lower():
        raise ErreurMotDePasse("Le mot de passe ne doit pas contenir l'identifiant.")
    sortes = sum((any(c.isalpha() for c in mdp), any(c.isdigit() for c in mdp), any(not c.isalnum() for c in mdp)))
    if sortes < 2:
        raise ErreurMotDePasse("Mélange au moins des lettres et des chiffres (ou d'autres caractères).")


def hacher(mdp, iterations=ITERATIONS):
    sel = secrets.token_bytes(16)
    h = hashlib.pbkdf2_hmac("sha256", mdp.encode("utf-8"), sel, iterations)
    return f"pbkdf2_sha256${iterations}${base64.b64encode(sel).decode()}${base64.b64encode(h).decode()}"


def verifier(mdp, stocke):
    try:
        algo, it, sel, h = stocke.split("$")
        if algo != "pbkdf2_sha256":
            return False
        calc = hashlib.pbkdf2_hmac("sha256", (mdp or "").encode("utf-8"), base64.b64decode(sel), int(it))
        return hmac.compare_digest(calc, base64.b64decode(h))
    except (ValueError, AttributeError):
        return False


def mot_de_passe_provisoire():
    """12 caractères lisibles (sans 0/O, 1/l) à donner à la personne, qui le change à la première connexion."""
    alphabet = "abcdefghjkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    while True:
        m = "".join(secrets.choice(alphabet) for _ in range(12))
        if any(c.isdigit() for c in m) and any(c.isalpha() for c in m):
            return m


def jeton():
    """Jeton de session (le serveur n'en garde que l'empreinte)."""
    return secrets.token_urlsafe(32)


def empreinte_jeton(j):
    return hashlib.sha256((j or "").encode()).hexdigest()
