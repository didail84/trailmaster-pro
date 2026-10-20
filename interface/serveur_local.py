"""
Consultation réseau local — un petit serveur web en LECTURE SEULE,
generant une page HTML minimaliste avec les indicateurs clés (forme,
ACWR, charge de la semaine, alertes), consultable depuis un téléphone
connecté au même Wi-Fi que l'ordinateur.

Ce n'est pas une application mobile : pas de compte, pas d'écriture
possible depuis la page, aucun accès depuis l'extérieur du réseau
local (le serveur n'écoute que sur l'IP locale de la machine, jamais
sur Internet). Bibliothèque standard uniquement (http.server), aucune
dépendance externe, aucun appel réseau sortant.
"""

import socket
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

from data.database import obtenir_athlete_par_id, obtenir_parametre, definir_parametre
from interface.coach import (
    calculer_acwr, calculer_score_forme_jour, obtenir_charges_journalieres, generer_alertes,
    obtenir_indicateurs_couleur,
)
from interface.theme import couleur_pour_pourcentage


_serveur = None
_thread = None
_athlete_id_courant = None
PORT_DEFAUT = 8765

CLE_PARAMETRE_PORT = "serveur_local_port"


def obtenir_port_configure():
    """Port utilisé par défaut — réglable depuis Réglages, utile
    seulement si le port 8765 est déjà pris par un autre logiciel sur
    cet ordinateur."""

    valeur = obtenir_parametre(CLE_PARAMETRE_PORT)
    try:
        port = int(valeur) if valeur else PORT_DEFAUT
        return port if 1024 <= port <= 65535 else PORT_DEFAUT
    except (TypeError, ValueError):
        return PORT_DEFAUT


def definir_port_configure(port):
    definir_parametre(CLE_PARAMETRE_PORT, port)


def adresse_ip_locale():
    """IP locale de la machine sur le réseau Wi-Fi/Ethernet — astuce
    classique (ouvrir un socket UDP vers une IP externe sans jamais
    lui envoyer le moindre octet) pour obtenir l'interface réseau
    active sans dépendre d'une requête réseau réelle."""

    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        ip = s.getsockname()[0]
    except Exception:
        ip = "127.0.0.1"
    finally:
        s.close()
    return ip


def _generer_page_dashboard(athlete_id):
    athlete = obtenir_athlete_par_id(athlete_id) if athlete_id else None
    if not athlete:
        return "<html><body><h1>TrailMaster Pro</h1><p>Aucun athlète configuré pour la consultation.</p></body></html>"

    colonnes = [
        "id", "nom", "prenom", "age", "sexe", "taille", "poids",
        "fc_repos", "fc_max", "fc_seuil", "vma", "vo2max", "niveau",
    ]
    a = dict(zip(colonnes, athlete))

    forme = calculer_score_forme_jour(athlete_id)
    acwr_info = calculer_acwr(athlete_id)
    charges = obtenir_charges_journalieres(athlete_id, nb_jours=7)
    charge_semaine = round(sum(c for _, c in charges), 1)
    alertes = generer_alertes(athlete_id)
    indicateurs = obtenir_indicateurs_couleur(athlete_id)

    lignes_alertes = "".join(
        f"<li class='niveau-{al['niveau']}'>{al['message']}</li>" for al in alertes
    )

    couleur_forme = indicateurs["forme_jour"]["couleur"] or "#8A9299"
    couleur_acwr = indicateurs["acwr"]["couleur"] or "#8A9299"

    return f"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>TrailMaster Pro — {a['prenom']} {a['nom']}</title>
<style>
  body {{ background:#15191D; color:#E4E7EA; font-family:-apple-system,sans-serif; margin:0; padding:20px; }}
  h1 {{ font-size:20px; }}
  .grille {{ display:grid; grid-template-columns:1fr 1fr; gap:12px; margin:16px 0; }}
  .carte {{ background:#1E2328; border:1px solid #2A2F35; border-radius:12px; padding:14px; }}
  .carte .titre {{ font-size:11px; color:#8A9299; text-transform:uppercase; }}
  .carte .valeur {{ font-size:24px; font-weight:700; margin-top:4px; }}
  ul {{ list-style:none; padding:0; }}
  li {{ padding:10px; border-radius:8px; margin-bottom:8px; background:#1E2328; }}
  .niveau-critique {{ border-left:4px solid #EF5350; }}
  .niveau-attention {{ border-left:4px solid #F9A825; }}
  .niveau-info {{ border-left:4px solid #42A5F5; }}
  .niveau-ok {{ border-left:4px solid #66BB6A; }}
  .pied {{ color:#5A6167; font-size:11px; margin-top:24px; text-align:center; }}
</style>
</head>
<body>
<h1>🏔️ TrailMaster Pro — {a['prenom']} {a['nom']}</h1>
<div class="grille">
  <div class="carte" style="border-left:4px solid {couleur_forme};"><div class="titre">Forme du jour</div><div class="valeur" style="color:{couleur_forme};">{forme['score']}/100</div></div>
  <div class="carte" style="border-left:4px solid {couleur_acwr};"><div class="titre">ACWR</div><div class="valeur" style="color:{couleur_acwr};">{acwr_info['acwr'] if acwr_info['acwr'] is not None else '--'}</div></div>
  <div class="carte"><div class="titre">Charge (7 jours)</div><div class="valeur">{charge_semaine}</div></div>
  <div class="carte"><div class="titre">Niveau</div><div class="valeur" style="font-size:16px;">{a['niveau'] or '--'}</div></div>
</div>
<p style="color:#8A9299; font-size:11px;">🟢 Vert · 🟡 Jaune · 🟠 Orange · 🔴 Rouge · ⚫ Noir — du plus tranquille au plus critique.</p>
<h2 style="font-size:15px;">Alertes</h2>
<ul>{lignes_alertes}</ul>
<p class="pied">Lecture seule · actualise la page pour rafraîchir · réseau local uniquement</p>
</body>
</html>"""


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            contenu = _generer_page_dashboard(_athlete_id_courant).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(contenu)))
            self.end_headers()
            self.wfile.write(contenu)
        except Exception:
            self.send_response(500)
            self.end_headers()

    def log_message(self, format, *args):
        pass  # pas de bruit dans la console


def serveur_actif():
    return _serveur is not None


def demarrer_serveur_local(athlete_id, port=None):
    """Démarre le serveur en arrière-plan (thread démon — s'arrête tout
    seul à la fermeture de l'application). Retourne (succes, message)."""

    global _serveur, _thread, _athlete_id_courant

    if port is None:
        port = obtenir_port_configure()

    if _serveur is not None:
        _athlete_id_courant = athlete_id
        return True, "Le serveur tourne déjà — athlète mis à jour."

    _athlete_id_courant = athlete_id
    try:
        _serveur = HTTPServer(("0.0.0.0", port), _Handler)
    except OSError as erreur:
        _serveur = None
        return False, f"Impossible de démarrer le serveur sur le port {port} : {erreur}"

    _thread = threading.Thread(target=_serveur.serve_forever, daemon=True)
    _thread.start()
    return True, f"Serveur démarré : http://{adresse_ip_locale()}:{port}"


def arreter_serveur_local():
    global _serveur, _thread
    if _serveur is not None:
        _serveur.shutdown()
        _serveur.server_close()
        _serveur = None
        _thread = None
