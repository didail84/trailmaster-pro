"""
Intégration avec l'API officielle de Strava (OAuth 2.0).

Fonctionnement : l'utilisateur crée gratuitement une "application" sur
https://www.strava.com/settings/api (domaine de rappel d'autorisation à
renseigner : "localhost"), ce qui donne un Client ID et un Client
Secret. TrailMaster Pro utilise ces identifiants pour ouvrir le
navigateur vers la page d'autorisation Strava ; une fois l'utilisateur
connecté et l'accès autorisé, Strava redirige vers un petit serveur
local temporaire qui récupère le code d'autorisation, puis l'échange
contre un jeton d'accès.

Nécessite une connexion internet à chaque appel — comme la météo et la
carte réelle.
"""

import json
import threading
import time
import urllib.request
import urllib.parse
import urllib.error
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer

from interface.erreurs_reseau import message_erreur_reseau


PORT_CALLBACK = 8765
REDIRECT_URI = f"http://localhost:{PORT_CALLBACK}/callback"
SCOPES = "read,activity:read_all"

URL_AUTORISATION = "https://www.strava.com/oauth/authorize"
URL_JETON = "https://www.strava.com/oauth/token"
URL_API = "https://www.strava.com/api/v3"


def construire_url_autorisation(client_id):
    parametres = {
        "client_id": client_id,
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "scope": SCOPES,
        "approval_prompt": "auto",
    }
    return f"{URL_AUTORISATION}?{urllib.parse.urlencode(parametres)}"


class _GestionnaireCallback(BaseHTTPRequestHandler):
    """Gère la seule requête qu'on attend : la redirection de Strava
    contenant le code d'autorisation."""

    code_recu = {"valeur": None, "erreur": None}

    def do_GET(self):
        parametres = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)

        if "code" in parametres:
            _GestionnaireCallback.code_recu["valeur"] = parametres["code"][0]
            message = "Autorisation reçue — tu peux fermer cet onglet et revenir à TrailMaster Pro."
        else:
            _GestionnaireCallback.code_recu["erreur"] = parametres.get("error", ["Erreur inconnue"])[0]
            message = "Autorisation refusée ou annulée — tu peux fermer cet onglet."

        self.send_response(200)
        self.send_header("Content-type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(
            f"<html><body style='font-family:sans-serif;padding:40px'><h2>{message}</h2></body></html>".encode("utf-8")
        )

    def log_message(self, format, *args):
        pass


def demarrer_flux_autorisation(client_id):
    """Ouvre le navigateur vers la page d'autorisation Strava et lance
    un serveur local temporaire pour récupérer le code. Retourne
    immédiatement ; utiliser attendre_code() pour connaître le résultat."""

    _GestionnaireCallback.code_recu = {"valeur": None, "erreur": None}

    serveur = HTTPServer(("localhost", PORT_CALLBACK), _GestionnaireCallback)
    serveur.timeout = 120

    def _attendre():
        serveur.handle_request()

    thread = threading.Thread(target=_attendre, daemon=True)
    thread.start()

    webbrowser.open(construire_url_autorisation(client_id))

    return thread


def verifier_code_recu():
    """Version non bloquante, à appeler depuis un QTimer côté interface
    pour ne pas geler l'appli en attendant la réponse du navigateur.
    Retourne (code, erreur, termine) — termine=False tant que rien
    n'est encore arrivé."""

    if _GestionnaireCallback.code_recu["valeur"]:
        return _GestionnaireCallback.code_recu["valeur"], None, True
    if _GestionnaireCallback.code_recu["erreur"]:
        return None, _GestionnaireCallback.code_recu["erreur"], True
    return None, None, False


def attendre_code(timeout_s=120):
    """À appeler après demarrer_flux_autorisation(). Bloque jusqu'à
    réception du code (ou du timeout). Retourne (code, erreur)."""

    debut = time.time()
    while time.time() - debut < timeout_s:
        if _GestionnaireCallback.code_recu["valeur"]:
            return _GestionnaireCallback.code_recu["valeur"], None
        if _GestionnaireCallback.code_recu["erreur"]:
            return None, _GestionnaireCallback.code_recu["erreur"]
        time.sleep(0.3)
    return None, "Délai dépassé — aucune réponse reçue de Strava."


def _requete_post(url, donnees):
    corps = urllib.parse.urlencode(donnees).encode("utf-8")
    requete = urllib.request.Request(url, data=corps, method="POST")
    try:
        with urllib.request.urlopen(requete, timeout=15) as reponse:
            return json.loads(reponse.read().decode("utf-8")), None
    except urllib.error.HTTPError as erreur:
        detail = erreur.read().decode("utf-8", errors="ignore")
        return None, f"Erreur HTTP {erreur.code} : {detail}"
    except urllib.error.URLError as erreur:
        return None, message_erreur_reseau(erreur)


def echanger_code_contre_jetons(client_id, client_secret, code):
    donnees, erreur = _requete_post(URL_JETON, {
        "client_id": client_id,
        "client_secret": client_secret,
        "code": code,
        "grant_type": "authorization_code",
    })
    if erreur:
        return None, erreur

    return {
        "access_token": donnees["access_token"],
        "refresh_token": donnees["refresh_token"],
        "expires_at": donnees["expires_at"],
    }, None


def rafraichir_jetons(client_id, client_secret, refresh_token):
    donnees, erreur = _requete_post(URL_JETON, {
        "client_id": client_id,
        "client_secret": client_secret,
        "refresh_token": refresh_token,
        "grant_type": "refresh_token",
    })
    if erreur:
        return None, erreur

    return {
        "access_token": donnees["access_token"],
        "refresh_token": donnees["refresh_token"],
        "expires_at": donnees["expires_at"],
    }, None


def _requete_get_api(url, access_token):
    requete = urllib.request.Request(url, headers={"Authorization": f"Bearer {access_token}"})
    try:
        with urllib.request.urlopen(requete, timeout=15) as reponse:
            return json.loads(reponse.read().decode("utf-8")), None
    except urllib.error.HTTPError as erreur:
        if erreur.code == 401:
            return None, "Jeton expiré ou invalide — reconnecte-toi à Strava."
        detail = erreur.read().decode("utf-8", errors="ignore")
        return None, f"Erreur HTTP {erreur.code} : {detail}"
    except urllib.error.URLError as erreur:
        return None, message_erreur_reseau(erreur)


def obtenir_activites(access_token, apres_timestamp=None, page=1, par_page=50):
    """Liste les activités de l'athlète connecté, les plus récentes
    d'abord. apres_timestamp (epoch) limite aux activités postérieures
    à cette date, pour ne récupérer que les nouvelles lors d'une
    resynchronisation."""

    parametres = {"page": page, "per_page": par_page}
    if apres_timestamp:
        parametres["after"] = apres_timestamp

    url = f"{URL_API}/athlete/activities?{urllib.parse.urlencode(parametres)}"
    return _requete_get_api(url, access_token)


def obtenir_flux_activite(access_token, activity_id):
    """Récupère les flux détaillés (position, altitude, FC, cadence,
    temps) d'une activité. Retourne (flux, erreur) où flux est un dict
    {latlng, altitude, heartrate, cadence, time} — chaque clé absente
    si l'appareil ne l'a pas enregistrée."""

    cles = "latlng,altitude,heartrate,cadence,time"
    url = f"{URL_API}/activities/{activity_id}/streams?keys={cles}&key_by_type=true"

    donnees, erreur = _requete_get_api(url, access_token)
    if erreur:
        return None, erreur

    resultat = {}
    for cle in ("latlng", "altitude", "heartrate", "cadence", "time"):
        if cle in donnees:
            resultat[cle] = donnees[cle]["data"]

    return resultat, None
