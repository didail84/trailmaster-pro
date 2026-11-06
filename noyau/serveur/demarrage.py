"""
Au démarrage du logiciel de bureau : branche les espaces Club et Organisation sur le serveur si une
connexion est enregistrée (Outils > Serveur), sinon tout reste local. Le jeton de session est rangé dans le
trousseau du système (keyring) quand il est disponible, jamais le mot de passe.
"""

from data.database import obtenir_parametre, definir_parametre

etat = {"mode": "local", "message": "", "client": None, "compte": None}
SERVICE = "Trail Hub Center serveur"


def _jeton_lire(url):
    try:
        import keyring
        j = keyring.get_password(SERVICE, url)
        if j:
            return j
    except Exception:
        pass
    return obtenir_parametre("serveur_jeton") or None


def _jeton_ecrire(url, jeton):
    try:
        import keyring
        if jeton:
            keyring.set_password(SERVICE, url, jeton)
        else:
            try:
                keyring.delete_password(SERVICE, url)
            except Exception:
                pass
        definir_parametre("serveur_jeton", "")
        return
    except Exception:
        definir_parametre("serveur_jeton", jeton or "")


def configuration():
    return {"url": obtenir_parametre("serveur_url") or "", "empreinte": obtenir_parametre("serveur_empreinte") or "",
            "identifiant": obtenir_parametre("serveur_identifiant") or ""}


def enregistrer(url, empreinte, identifiant, jeton):
    definir_parametre("serveur_url", url)
    definir_parametre("serveur_empreinte", empreinte or "")
    definir_parametre("serveur_identifiant", identifiant)
    _jeton_ecrire(url, jeton)


def oublier():
    c = configuration()
    if c["url"]:
        _jeton_ecrire(c["url"], None)
    for k in ("serveur_url", "serveur_empreinte", "serveur_identifiant"):
        definir_parametre(k, "")


def brancher_si_configure():
    """Renvoie l'état : {mode: local | serveur | erreur, message}."""
    c = configuration()
    if not c["url"]:
        etat.update(mode="local", message="")
        return etat
    from noyau.serveur import client as C
    jeton = _jeton_lire(c["url"])
    if not jeton:
        etat.update(mode="erreur", message="Connexion au serveur à refaire (Outils > Serveur) : tu travailles en local.")
        return etat
    cl = C.Client(c["url"], c["empreinte"] or None, jeton, delai=8)
    try:
        compte = cl.moi()
        if not compte:
            raise C.ErreurServeur("Session expirée.")
        C.installer(cl)
    except (C.ErreurConnexion, C.ErreurServeur) as e:
        etat.update(mode="erreur", message=f"Serveur injoignable ou session expirée ({e}). Tu travailles en local "
                                           "jusqu'au prochain démarrage.")
        return etat
    etat.update(mode="serveur", client=cl, compte=compte,
                message=f"Club et Organisation sur le serveur {c['url']} ({compte['identifiant']}).")
    return etat
