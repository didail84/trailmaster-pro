"""
Le logiciel de bureau branché sur un serveur Trail Hub (étape 5).

- Connexion HTTPS au certificat du serveur reconnu par son empreinte : la
  première fois, on note l'empreinte (montrée aussi sur le serveur) ;
  ensuite, un certificat différent est refusé.
- installer(client) remplace les fonctions des modules partagés
  (noyau/donnees : club, agenda, organisation, chrono, logistique…) par des
  appels au serveur. L'espace Coureur reste sur l'ordinateur.
- L'association et la section choisies restent propres à ce poste.
"""

import hashlib
import http.client
import importlib
import inspect
import json
import ssl
from urllib.parse import urlparse

from noyau.serveur import rpc

MODULES_PARTAGES = ("club", "agenda_club", "profils", "personnes", "organisation", "chrono", "logistique", "calendrier",
                    "annuaire", "kids", "analyse", "commandement", "comptes")


class ErreurConnexion(Exception):
    """Le serveur ne répond pas, ou pas comme prévu."""


class ErreurServeur(Exception):
    """Erreur renvoyée par le serveur."""


def _empreinte(der):
    h = hashlib.sha256(der).hexdigest().upper()
    return ":".join(h[i:i + 2] for i in range(0, len(h), 2))


class Client:

    def __init__(self, url, empreinte=None, jeton=None, delai=20):
        u = urlparse(url.strip().rstrip("/"))
        if u.scheme not in ("http", "https") or not u.hostname:
            raise ErreurConnexion("Adresse du serveur illisible (exemple : https://192.168.1.20:8770).")
        self.url, self.https, self.hote, self.port = url.strip().rstrip("/"), u.scheme == "https", u.hostname, u.port
        self.empreinte, self.jeton, self.delai = empreinte, jeton, delai
        self.contexte = {}                     # {"club_id": …, "sections": {…}} envoyé avec chaque appel

    # -- transport
    def _connexion(self):
        if not self.https:
            return http.client.HTTPConnection(self.hote, self.port or 80, timeout=self.delai)
        ctx = ssl.create_default_context()
        ctx.check_hostname = False            # certificat du serveur reconnu par son empreinte, pas par une autorité
        ctx.verify_mode = ssl.CERT_NONE
        return http.client.HTTPSConnection(self.hote, self.port or 443, timeout=self.delai, context=ctx)

    def _requete(self, verbe, chemin, donnees=None):
        c = self._connexion()
        try:
            c.connect()
            if self.https:
                vue = _empreinte(c.sock.getpeercert(binary_form=True))
                if self.empreinte is None:
                    self.empreinte = vue
                elif vue != self.empreinte:
                    raise ErreurConnexion("Le certificat du serveur a changé : ce n'est peut-être pas ton serveur. "
                                          f"Empreinte reçue : {vue}")
            corps = json.dumps(rpc.encoder(donnees or {}), ensure_ascii=False).encode() if verbe == "POST" else None
            e = {"Content-Type": "application/json"}
            if self.jeton:
                e["Authorization"] = f"Bearer {self.jeton}"
            c.request(verbe, chemin, body=corps, headers=e)
            r = c.getresponse()
            brut = r.read()
        except (OSError, http.client.HTTPException) as e:
            raise ErreurConnexion(f"Le serveur ne répond pas ({e.__class__.__name__}). Vérifie qu'il est allumé et que "
                                  "tu es sur le même réseau.")
        finally:
            c.close()
        try:
            rep = json.loads(brut or b"{}")
        except ValueError:
            raise ErreurConnexion("Réponse illisible du serveur.")
        if r.status == 401:
            raise ErreurServeur((rep.get("erreur") or {}).get("message") or "Connexion refusée.")
        return rep

    # -- compte
    def info(self):
        return self._requete("GET", "/api/info")

    def connecter(self, identifiant, mot_de_passe, appareil="Trail Hub Center (bureau)"):
        r = self._requete("POST", "/api/connexion", {"identifiant": identifiant, "mot_de_passe": mot_de_passe,
                                                     "appareil": appareil})
        if "jeton" not in r:
            raise ErreurServeur((r.get("erreur") or {}).get("message") or "Connexion refusée.")
        self.jeton = r["jeton"]
        return r["compte"]

    def moi(self):
        return self._requete("POST", "/api/moi").get("compte")

    def changer_mot_de_passe(self, ancien, nouveau):
        r = self._requete("POST", "/api/mot_de_passe", {"ancien": ancien, "nouveau": nouveau})
        if "erreur" in r:
            raise ErreurServeur(r["erreur"]["message"])

    def telecharger_copie(self, chemin):
        """Copie de la base du serveur (administrateur) : pour l'ouvrir dans la page Claude."""
        c = self._connexion()
        try:
            c.connect()
            if self.https and _empreinte(c.sock.getpeercert(binary_form=True)) != self.empreinte:
                raise ErreurConnexion("Le certificat du serveur a changé.")
            c.request("POST", "/api/copie", body=b"{}", headers={"Authorization": f"Bearer {self.jeton}",
                                                                  "Content-Type": "application/json"})
            r = c.getresponse()
            brut = r.read()
        except (OSError, http.client.HTTPException) as e:
            raise ErreurConnexion(f"Le serveur ne répond pas ({e.__class__.__name__}).")
        finally:
            c.close()
        if r.status != 200:
            try:
                raise ErreurServeur(json.loads(brut)["erreur"]["message"])
            except (ValueError, KeyError):
                raise ErreurServeur("Copie refusée.")
        with open(chemin, "wb") as f:
            f.write(brut)
        return len(brut)

    def deconnecter(self):
        try:
            self._requete("POST", "/api/deconnexion")
        finally:
            self.jeton = None

    # -- appels
    def appeler(self, module, fonction, *args, **kwargs):
        r = self._requete("POST", "/api/rpc", {"module": module, "fonction": fonction, "args": list(args),
                                               "kwargs": kwargs, "contexte": self.contexte})
        if "erreur" in r:
            e = r["erreur"]
            classe = _classe_erreur(module, e.get("type"))
            raise classe(e.get("message") or "Erreur du serveur.")
        return rpc.decoder(r.get("ok"))


def _classe_erreur(module, nom):
    """L'exception du module (ErreurClub…) pour que les écrans affichent le message comme d'habitude."""
    try:
        m = importlib.import_module(f"noyau.donnees.{module}")
        c = getattr(m, nom, None)
        if isinstance(c, type) and issubclass(c, Exception):
            return c
    except ImportError:
        pass
    return ErreurServeur


# ------------------------------------------------------------------ bascule des modules

_originaux = {}


def _mandataire(client, module, nom, f):
    sig = inspect.signature(f)

    def appel(*args, **kwargs):
        try:
            lies = sig.bind(*args, **kwargs)
        except TypeError:
            return client.appeler(module, nom, *args, **kwargs)
        return client.appeler(module, nom, **dict(lies.arguments))

    appel.__name__, appel.__doc__, appel.__wrapped__ = nom, f.__doc__, f
    appel._mandataire = True
    return appel


def installer(client, depot_local=None):
    """Branche les modules partagés sur le serveur. depot_local : objet avec obtenir(cle) / definir(cle, valeur)
    pour l'association et la section de ce poste (par défaut : les paramètres de la base locale).
    Renvoie la fonction qui débranche."""
    from noyau.serveur import serveur as S
    if S.actif():
        raise ErreurConnexion("Cet ordinateur est lui-même le serveur : il travaille déjà sur la base partagée.")
    if _originaux:
        desinstaller()
    if depot_local is None:
        from data.database import obtenir_parametre, definir_parametre

        class _D:
            obtenir = staticmethod(obtenir_parametre)
            definir = staticmethod(definir_parametre)
        depot_local = _D
    for module in MODULES_PARTAGES:
        try:
            m = importlib.import_module(f"noyau.donnees.{module}")
        except ImportError:
            continue
        locales = rpc.LOCALES.get(module, set())
        for nom, f in list(vars(m).items()):
            if not inspect.isfunction(f) or nom.startswith("_") or f.__module__ != m.__name__ or nom in locales:
                continue
            _originaux[(m, nom)] = f
            setattr(m, nom, _mandataire(client, module, nom, f))
    _brancher_club_local(client, depot_local)
    return desinstaller


def _brancher_club_local(client, depot):
    from noyau.donnees import club as m

    def club_courant_id():
        ids = [c["id"] for c in m.clubs()]
        v = depot.obtenir("serveur_club_courant")
        if v and str(v).isdigit() and int(v) in ids:
            return int(v)
        return ids[0] if ids else None

    def choisir_club(club_id):
        depot.definir("serveur_club_courant", club_id)
        client.contexte["club_id"] = club_id

    def club_principal():
        cid = club_courant_id()
        return m.club(cid) if cid else None

    def club_id_ou_creer():
        c = club_principal()
        return c["id"] if c else m.enregistrer_club({"nom": "Mon club"})

    def section_courante(club_id):
        v = depot.obtenir(f"serveur_section_{club_id}")
        return int(v) if v and str(v).isdigit() else None

    def choisir_section(club_id, section_id):
        depot.definir(f"serveur_section_{club_id}", section_id or "")
        client.contexte.setdefault("sections", {})[str(club_id)] = section_id

    for nom, f in (("club_courant_id", club_courant_id), ("choisir_club", choisir_club), ("club_principal", club_principal),
                   ("club_id_ou_creer", club_id_ou_creer), ("section_courante", section_courante),
                   ("choisir_section", choisir_section)):
        _originaux.setdefault((m, nom), getattr(m, nom))
        setattr(m, nom, f)
    cid = club_courant_id()
    client.contexte["club_id"] = cid
    if cid:
        client.contexte["sections"] = {str(cid): section_courante(cid)}


def desinstaller():
    for (m, nom), f in _originaux.items():
        setattr(m, nom, f)
    _originaux.clear()


def branche():
    return bool(_originaux)
