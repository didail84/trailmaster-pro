"""
Suivi en direct d'une sortie — le coureur ouvre une page sur son
téléphone (aucune appli à installer), le téléphone envoie sa position
GPS (et sa fréquence cardiaque si une ceinture Bluetooth est couplée)
toutes les quelques secondes, et cet ordinateur affiche en direct la
carte qui se trace, la distance, l'allure, la vitesse, le D+, la FC et
le chrono. À la fin, la sortie est enregistrée comme une activité
normale (visible dans l'Historique), avec sa trace GPS.

Fonctionnement réseau : un petit serveur HTTPS tourne sur cet
ordinateur, joignable uniquement depuis les appareils du même réseau
Wi-Fi (comme "Consultation réseau local", mais ici le téléphone ENVOIE
des données au lieu de seulement les consulter). Le HTTPS est
nécessaire ici — contrairement au reste de l'appli — car les
navigateurs mobiles (Chrome, Safari) refusent d'donner accès à la
géolocalisation et aux capteurs de mouvement sur une page chargée en
simple HTTP dès qu'elle n'est pas strictement locale à l'appareil. Le
certificat utilisé est auto-signé (généré une fois, conservé à côté de
la base de données) : le navigateur du téléphone affichera donc un
avertissement de sécurité la première fois ("Connexion non privée") —
c'est normal pour un certificat local, il suffit de valider
("Avancé" → "Continuer vers...").

Reconciliation avec Garmin/Strava : une sortie enregistrée ainsi
utilise le GPS du téléphone (moins précis qu'une montre trail dédiée).
Si la même sortie est resynchronisée plus tard depuis Garmin/Strava,
l'écran "Nettoyage des doublons" (interface/nettoyage_doublons.py) la
détecte comme doublon et propose de fusionner les deux — en gardant
les chiffres de la source la plus précise. Voir interface/doublons.py.
"""

import json
import math
import secrets
import tempfile
import threading
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from PySide6.QtCore import Qt, QUrl, QTimer
from PySide6.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QLabel,
    QComboBox,
    QPushButton,
    QFrame,
    QScrollArea,
    QMessageBox,
    QLineEdit,
)
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebEngineCore import QWebEngineSettings

from data.database import connexion, CHEMIN_BDD, obtenir_parametre, definir_parametre, obtenir_athletes
from interface.ecran_liste import obtenir_style_ecran


# ------------------------------------------------------------------
# RÉGLAGES
# ------------------------------------------------------------------

PORT_DEFAUT_SUIVI = 8766
CLE_PARAMETRE_PORT_SUIVI = "suivi_direct_port"

# Filtres anti-bruit GPS/baromètre : un point impliquant une vitesse
# instantanée irréaliste (mauvaise réception GPS, rebond satellite) est
# ignoré pour la distance ; une variation d'altitude inférieure à ce
# seuil est considérée comme du bruit de mesure plutôt qu'un vrai
# dénivelé, et n'est pas comptée — approximation raisonnable, pas une
# mesure barométrique de précision.
VITESSE_MAX_PLAUSIBLE_KMH = 45
SEUIL_BRUIT_ALTITUDE_M = 1.5


def obtenir_port_suivi_configure():
    valeur = obtenir_parametre(CLE_PARAMETRE_PORT_SUIVI)
    try:
        port = int(valeur) if valeur else PORT_DEFAUT_SUIVI
        return port if 1024 <= port <= 65535 else PORT_DEFAUT_SUIVI
    except (TypeError, ValueError):
        return PORT_DEFAUT_SUIVI


def definir_port_suivi_configure(port):
    definir_parametre(CLE_PARAMETRE_PORT_SUIVI, port)


# ------------------------------------------------------------------
# CERTIFICAT HTTPS AUTO-SIGNÉ (généré une fois, réutilisé ensuite)
# ------------------------------------------------------------------

DOSSIER_CERTS = Path(CHEMIN_BDD).parent / "certs_suivi_direct"
CHEMIN_CERT = DOSSIER_CERTS / "suivi_direct_cert.pem"
CHEMIN_CLE = DOSSIER_CERTS / "suivi_direct_cle.pem"


def _generer_certificat_si_absent():
    """Crée un certificat HTTPS auto-signé local s'il n'existe pas
    encore. Valable 10 ans, propre à cette installation — jamais
    transmis nulle part, il sert uniquement à chiffrer la liaison
    téléphone → ordinateur sur le réseau Wi-Fi local."""

    if CHEMIN_CERT.exists() and CHEMIN_CLE.exists():
        return

    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID
    import datetime as _dt

    DOSSIER_CERTS.mkdir(parents=True, exist_ok=True)

    cle = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    sujet = emetteur = x509.Name(
        [x509.NameAttribute(NameOID.COMMON_NAME, "trailmaster.local")]
    )
    certificat = (
        x509.CertificateBuilder()
        .subject_name(sujet)
        .issuer_name(emetteur)
        .public_key(cle.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(_dt.datetime.utcnow() - _dt.timedelta(days=1))
        .not_valid_after(_dt.datetime.utcnow() + _dt.timedelta(days=3650))
        .add_extension(
            x509.SubjectAlternativeName([x509.DNSName("trailmaster.local")]),
            critical=False,
        )
        .sign(cle, hashes.SHA256())
    )

    CHEMIN_CLE.write_bytes(
        cle.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    CHEMIN_CERT.write_bytes(certificat.public_bytes(serialization.Encoding.PEM))


# ------------------------------------------------------------------
# ÉTAT DE LA SESSION EN COURS (mémoire uniquement — écrit en base
# seulement à la clôture de la sortie, voir terminer_session())
# ------------------------------------------------------------------

_verrou = threading.Lock()
_session = None  # dict ou None si aucun suivi en cours
_serveur = None
_thread = None


def session_active():
    with _verrou:
        return _session is not None


def _distance_haversine_km(lat1, lon1, lat2, lon2):
    rayon_terre_km = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * rayon_terre_km * math.asin(min(1, math.sqrt(a)))


def demarrer_session(athlete_id, port=None):
    """Démarre une nouvelle session de suivi en direct (arrête et
    remplace toute session déjà en cours pour cet athlète). Retourne
    (succes, message, url_pour_le_telephone)."""

    global _session, _serveur, _thread

    with _verrou:
        if _serveur is not None:
            _arreter_serveur_interne()

        try:
            _generer_certificat_si_absent()
        except Exception as erreur:
            return False, f"Impossible de préparer le certificat HTTPS local : {erreur}", None

        port = port or obtenir_port_suivi_configure()
        token = secrets.token_hex(4)

        import ssl

        contexte_ssl = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        try:
            contexte_ssl.load_cert_chain(certfile=str(CHEMIN_CERT), keyfile=str(CHEMIN_CLE))
        except Exception as erreur:
            return False, f"Certificat HTTPS invalide : {erreur}", None

        try:
            httpd = ThreadingHTTPServer(("0.0.0.0", port), _HandlerSuivi)
        except OSError as erreur:
            return False, f"Impossible de démarrer le serveur sur le port {port} : {erreur}", None

        httpd.socket = contexte_ssl.wrap_socket(httpd.socket, server_side=True)

        _session = {
            "token": token,
            "athlete_id": athlete_id,
            "debut_epoch": time.time(),
            "points": [],
            "distance_km": 0.0,
            "denivele_positif": 0,
            "denivele_negatif": 0,
            "derniere_position": None,
            "fc_liste": [],
            "cadence_liste": [],
            "terminee": False,
        }
        _serveur = httpd
        _thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        _thread.start()

        ip = _adresse_ip_locale()
        url = f"https://{ip}:{port}/suivi/{token}"
        return True, "Suivi démarré.", url


def _adresse_ip_locale():
    import socket

    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        ip = s.getsockname()[0]
    except Exception:
        ip = "127.0.0.1"
    finally:
        s.close()
    return ip


def _arreter_serveur_interne():
    """Doit être appelée avec _verrou déjà tenu."""
    global _serveur, _thread
    if _serveur is not None:
        _serveur.shutdown()
        _serveur.server_close()
        _serveur = None
        _thread = None


def annuler_session():
    """Arrête le suivi en cours sans rien enregistrer en base."""
    global _session
    with _verrou:
        _arreter_serveur_interne()
        _session = None


def etat_session():
    """Statistiques en direct de la session en cours, ou None si aucune
    session active — lecture directe en mémoire (même processus que
    l'écran Qt, pas besoin de passer par le réseau)."""

    with _verrou:
        if _session is None:
            return None
        s = _session
        duree_s = time.time() - s["debut_epoch"]
        distance_km = s["distance_km"]
        allure_min_km = (duree_s / 60 / distance_km) if distance_km > 0.05 else None
        vitesse_kmh = (distance_km / (duree_s / 3600)) if duree_s > 0 else 0
        fc_liste = s["fc_liste"]
        cadence_liste = s["cadence_liste"]
        return {
            "token": s["token"],
            "duree_s": duree_s,
            "distance_km": round(distance_km, 3),
            "denivele_positif": s["denivele_positif"],
            "denivele_negatif": s["denivele_negatif"],
            "allure_min_km": allure_min_km,
            "vitesse_kmh": round(vitesse_kmh, 1),
            "fc_instantanee": fc_liste[-1] if fc_liste else None,
            "fc_moyenne": round(sum(fc_liste) / len(fc_liste)) if fc_liste else None,
            "cadence_moyenne": round(sum(cadence_liste) / len(cadence_liste)) if cadence_liste else None,
            "nb_points": len(s["points"]),
            "trace": [[p["lat"], p["lon"]] for p in s["points"]],
        }


def _enregistrer_point(token, lat, lon, alt, hr, cadence):
    with _verrou:
        if _session is None or _session["token"] != token or _session["terminee"]:
            return False

        s = _session
        maintenant = time.time()
        alt = alt if alt is not None else 0.0

        derniere = s["derniere_position"]
        if derniere is not None:
            distance_pas_km = _distance_haversine_km(derniere[0], derniere[1], lat, lon)
            dt_s = max(1, maintenant - derniere[3])
            vitesse_instantanee_kmh = distance_pas_km / (dt_s / 3600)
            if vitesse_instantanee_kmh <= VITESSE_MAX_PLAUSIBLE_KMH:
                s["distance_km"] += distance_pas_km
                delta_alt = alt - derniere[2]
                if delta_alt > SEUIL_BRUIT_ALTITUDE_M:
                    s["denivele_positif"] += round(delta_alt)
                elif delta_alt < -SEUIL_BRUIT_ALTITUDE_M:
                    s["denivele_negatif"] += round(-delta_alt)
            # Un point jugé aberrant n'est pas compté dans la distance/D+,
            # mais reste conservé dans la trace pour ne rien perdre.

        s["points"].append({"lat": lat, "lon": lon, "alt": alt, "t": maintenant, "hr": hr, "cad": cadence})
        s["derniere_position"] = (lat, lon, alt, maintenant)
        if hr:
            s["fc_liste"].append(hr)
        if cadence:
            s["cadence_liste"].append(cadence)

        return True


def terminer_session(nom_sortie=None):
    """Clôture la session en cours, l'enregistre comme une activité
    normale (+ trace GPS liée), arrête le serveur, et retourne
    (succes, message, activite_id_ou_None)."""

    global _session

    with _verrou:
        if _session is None:
            return False, "Aucun suivi en cours.", None
        s = dict(_session)
        _session["terminee"] = True
        _arreter_serveur_interne()
        _session = None

    if len(s["points"]) < 2:
        return False, "Trop peu de positions reçues — rien n'a été enregistré.", None

    athlete_id = s["athlete_id"]
    duree_s = int(time.time() - s["debut_epoch"])
    distance_km = round(s["distance_km"], 3)
    vitesse_moyenne = round(distance_km / (duree_s / 3600), 2) if duree_s > 0 else None
    allure_moyenne = round((duree_s / 60) / distance_km, 2) if distance_km > 0.05 else None
    fc_moyenne = round(sum(s["fc_liste"]) / len(s["fc_liste"])) if s["fc_liste"] else None
    fc_max = max(s["fc_liste"]) if s["fc_liste"] else None
    cadence_moyenne = round(sum(s["cadence_liste"]) / len(s["cadence_liste"])) if s["cadence_liste"] else None
    date_debut = datetime.fromtimestamp(s["debut_epoch"]).strftime("%Y-%m-%d %H:%M:%S")
    nom = nom_sortie or f"Sortie du {datetime.fromtimestamp(s['debut_epoch']).strftime('%d/%m/%Y')} (suivi en direct)"

    conn = connexion()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO activites (
            athlete_id, date, nom, type, distance, denivele, duree,
            vitesse_moyenne, allure_moyenne, frequence_cardiaque_moyenne,
            frequence_cardiaque_max, source, cadence_moyenne, notes
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            athlete_id, date_debut, nom, "Trail", distance_km,
            s["denivele_positif"], duree_s, vitesse_moyenne, allure_moyenne,
            fc_moyenne, fc_max, "Suivi en direct (téléphone)", cadence_moyenne,
            "Sortie enregistrée en direct depuis le téléphone — GPS de téléphone, "
            "moins précis qu'une montre dédiée. Une synchro Garmin/Strava ultérieure "
            "de la même sortie peut être fusionnée depuis Nettoyage des doublons.",
        ),
    )
    activite_id = cur.lastrowid

    points_json = [[p["lat"], p["lon"], p["alt"], p["t"], p["hr"], p["cad"]] for p in s["points"]]
    cur.execute(
        """
        INSERT INTO parcours_gpx (
            athlete_id, nom, distance_km, denivele_positif, denivele_negatif,
            trace_json, activite_id
        ) VALUES (?,?,?,?,?,?,?)
        """,
        (athlete_id, nom, distance_km, s["denivele_positif"], s["denivele_negatif"],
         json.dumps(points_json), activite_id),
    )

    conn.commit()
    conn.close()

    try:
        from interface.coach import invalider_cache_coach
        invalider_cache_coach()
    except ImportError:
        pass

    return True, "Sortie enregistrée.", activite_id


# ------------------------------------------------------------------
# PAGE MOBILE (servie au téléphone du coureur)
# ------------------------------------------------------------------

def _page_mobile(token):
    return """<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1">
<title>TrailMaster Pro — Suivi en direct</title>
<style>
  body { background:#15191D; color:#E4E7EA; font-family:-apple-system,sans-serif; margin:0; padding:18px; }
  h1 { font-size:18px; margin-bottom:4px; }
  #etat { color:#8A9299; font-size:13px; margin-bottom:16px; }
  .grille { display:grid; grid-template-columns:1fr 1fr; gap:10px; }
  .carte { background:#1E2328; border:1px solid #2A2F35; border-radius:12px; padding:12px; text-align:center; }
  .carte .titre { font-size:10px; color:#8A9299; text-transform:uppercase; }
  .carte .valeur { font-size:22px; font-weight:700; margin-top:4px; }
  button { width:100%%; padding:16px; font-size:16px; font-weight:700; border:none; border-radius:12px;
           margin-top:14px; cursor:pointer; }
  #boutonDemarrer { background:#FF7828; color:white; }
  #boutonBluetooth { background:#2A2F35; color:#E4E7EA; font-size:14px; padding:12px; }
  #boutonBluetooth.connecte { background:#2E7D32; }
</style>
</head>
<body>
<h1>TrailMaster Pro — Suivi en direct</h1>
<div id="etat">Prêt à démarrer.</div>

<div class="grille">
  <div class="carte"><div class="titre">Chrono</div><div class="valeur" id="valChrono">--:--</div></div>
  <div class="carte"><div class="titre">Distance</div><div class="valeur" id="valDistance">0.00 km</div></div>
  <div class="carte"><div class="titre">Allure</div><div class="valeur" id="valAllure">--</div></div>
  <div class="carte"><div class="titre">Vitesse</div><div class="valeur" id="valVitesse">0.0 km/h</div></div>
  <div class="carte"><div class="titre">D+</div><div class="valeur" id="valDPlus">0 m</div></div>
  <div class="carte"><div class="titre">FC</div><div class="valeur" id="valFC">--</div></div>
</div>

<button id="boutonDemarrer">Démarrer le suivi</button>
<button id="boutonBluetooth">🔗 Connecter une ceinture FC (Bluetooth, optionnel)</button>

<script>
var TOKEN = "%s";
var enCours = false;
var watchId = null;
var derniereFC = null;
var compteurPas = 0;
var derniereAccelMagnitude = null;
var picDetecte = false;
var cadenceInstantanee = 0;

function formaterChrono(secondes) {
  var h = Math.floor(secondes / 3600);
  var m = Math.floor((secondes %% 3600) / 60);
  var s = Math.floor(secondes %% 60);
  var pad = function(n) { return n < 10 ? "0" + n : "" + n; };
  return h > 0 ? (h + ":" + pad(m) + ":" + pad(s)) : (pad(m) + ":" + pad(s));
}

function envoyerPosition(lat, lon, alt) {
  fetch("/position", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({
      token: TOKEN, lat: lat, lon: lon, alt: alt,
      hr: derniereFC, cadence: Math.round(cadenceInstantanee)
    })
  }).then(function(reponse) { return reponse.json(); })
    .then(function(donnees) {
      if (!donnees.ok) { return; }
      var e = donnees.etat;
      document.getElementById("valChrono").textContent = formaterChrono(e.duree_s);
      document.getElementById("valDistance").textContent = e.distance_km.toFixed(2) + " km";
      document.getElementById("valAllure").textContent = e.allure_min_km
          ? (Math.floor(e.allure_min_km) + ":" + String(Math.round((e.allure_min_km %% 1) * 60)).padStart(2, "0") + " /km")
          : "--";
      document.getElementById("valVitesse").textContent = e.vitesse_kmh.toFixed(1) + " km/h";
      document.getElementById("valDPlus").textContent = e.denivele_positif + " m";
      document.getElementById("valFC").textContent = e.fc_instantanee ? (e.fc_instantanee + " bpm") : "--";
    }).catch(function() {
      document.getElementById("etat").textContent = "Connexion à l'ordinateur perdue — nouvel essai...";
    });
}

document.getElementById("boutonDemarrer").addEventListener("click", function() {
  if (enCours) return;
  enCours = true;
  document.getElementById("boutonDemarrer").textContent = "Suivi en cours…";
  document.getElementById("boutonDemarrer").disabled = true;
  document.getElementById("etat").textContent = "Recherche du signal GPS…";

  if (!navigator.geolocation) {
    document.getElementById("etat").textContent = "Ce navigateur ne fournit pas la géolocalisation.";
    return;
  }

  watchId = navigator.geolocation.watchPosition(function(position) {
    document.getElementById("etat").textContent = "Suivi actif — laisse cette page ouverte.";
    envoyerPosition(
      position.coords.latitude, position.coords.longitude,
      position.coords.altitude
    );
  }, function(erreur) {
    document.getElementById("etat").textContent = "GPS indisponible : " + erreur.message;
  }, {enableHighAccuracy: true, maximumAge: 2000, timeout: 15000});

  // Cadence approximative : comptage de pics d'accélération verticale
  // (approximation simple, pas un vrai capteur de cadence dédié).
  var demarrerAccelerometre = function() {
    window.addEventListener("devicemotion", function(evenement) {
      var acc = evenement.accelerationIncludingGravity;
      if (!acc) return;
      var magnitude = Math.sqrt(acc.x * acc.x + acc.y * acc.y + acc.z * acc.z);
      if (derniereAccelMagnitude !== null) {
        var delta = magnitude - derniereAccelMagnitude;
        if (delta > 2.2 && !picDetecte) {
          compteurPas += 1;
          picDetecte = true;
        } else if (delta < 0.5) {
          picDetecte = false;
        }
      }
      derniereAccelMagnitude = magnitude;
    });
    setInterval(function() {
      cadenceInstantanee = compteurPas * 2; // pas/min (fenêtre de 30s), 2 pieds
      compteurPas = 0;
    }, 30000);
  };

  if (typeof DeviceMotionEvent !== "undefined" && typeof DeviceMotionEvent.requestPermission === "function") {
    DeviceMotionEvent.requestPermission().then(function(reponse) {
      if (reponse === "granted") demarrerAccelerometre();
    }).catch(function() {});
  } else if (typeof DeviceMotionEvent !== "undefined") {
    demarrerAccelerometre();
  }
});

document.getElementById("boutonBluetooth").addEventListener("click", function() {
  if (!navigator.bluetooth) {
    alert("Le Bluetooth Web n'est pas disponible sur ce navigateur (essaie Chrome sur Android).");
    return;
  }
  navigator.bluetooth.requestDevice({filters: [{services: ["heart_rate"]}]})
    .then(function(appareil) { return appareil.gatt.connect(); })
    .then(function(serveur) { return serveur.getPrimaryService("heart_rate"); })
    .then(function(service) { return service.getCharacteristic("heart_rate_measurement"); })
    .then(function(caracteristique) { return caracteristique.startNotifications(); })
    .then(function(caracteristique) {
      document.getElementById("boutonBluetooth").textContent = "✅ Ceinture FC connectée";
      document.getElementById("boutonBluetooth").classList.add("connecte");
      caracteristique.addEventListener("characteristicvaluechanged", function(evenement) {
        var valeur = evenement.target.value;
        var drapeaux = valeur.getUint8(0);
        derniereFC = (drapeaux & 0x1) ? valeur.getUint16(1, true) : valeur.getUint8(1);
      });
    }).catch(function(erreur) {
      alert("Connexion Bluetooth impossible : " + erreur);
    });
});
</script>
</body>
</html>""" % token


def _page_aucun_suivi():
    return (
        "<html><body style='background:#15191D;color:#E4E7EA;"
        "font-family:sans-serif;text-align:center;padding-top:80px;'>"
        "<h2>Aucun suivi en cours</h2>"
        "<p>Démarre le suivi depuis l'écran « Suivi en direct » sur l'ordinateur.</p>"
        "</body></html>"
    )


# ------------------------------------------------------------------
# SERVEUR HTTP(S)
# ------------------------------------------------------------------

class _HandlerSuivi(BaseHTTPRequestHandler):

    def log_message(self, format, *args):
        pass

    def _repondre_json(self, code, donnees):
        contenu = json.dumps(donnees).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(contenu)))
        self.end_headers()
        self.wfile.write(contenu)

    def _repondre_html(self, code, html):
        contenu = html.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(contenu)))
        self.end_headers()
        self.wfile.write(contenu)

    def do_GET(self):
        chemin = urlparse(self.path).path
        if chemin.startswith("/suivi/"):
            token_recu = chemin.split("/suivi/", 1)[1].strip("/")
            with _verrou:
                token_valide = _session is not None and _session["token"] == token_recu
            if token_valide:
                self._repondre_html(200, _page_mobile(token_recu))
            else:
                self._repondre_html(404, _page_aucun_suivi())
        else:
            self._repondre_html(200, _page_aucun_suivi())

    def do_POST(self):
        chemin = urlparse(self.path).path
        if chemin != "/position":
            self._repondre_json(404, {"ok": False, "erreur": "route inconnue"})
            return

        try:
            longueur = int(self.headers.get("Content-Length", 0))
            corps = self.rfile.read(longueur)
            donnees = json.loads(corps)
        except (ValueError, TypeError):
            self._repondre_json(400, {"ok": False, "erreur": "requête invalide"})
            return

        token = donnees.get("token")
        lat, lon = donnees.get("lat"), donnees.get("lon")
        if token is None or lat is None or lon is None:
            self._repondre_json(400, {"ok": False, "erreur": "champs manquants"})
            return

        accepte = _enregistrer_point(
            token, float(lat), float(lon), donnees.get("alt"),
            donnees.get("hr"), donnees.get("cadence"),
        )
        if not accepte:
            self._repondre_json(403, {"ok": False, "erreur": "session invalide ou terminée"})
            return

        self._repondre_json(200, {"ok": True, "etat": etat_session()})


# ------------------------------------------------------------------
# ÉCRAN "SUIVI EN DIRECT" (côté ordinateur)
# ------------------------------------------------------------------

DOSSIER_LEAFLET = Path(__file__).parent / "assets" / "leaflet"
CHEMIN_TEMP_HTML_SUIVI = Path(tempfile.gettempdir()) / "trailmaster_suivi_direct.html"

GABARIT_HTML_CARTE_DIRECT = """
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8" />
<link rel="stylesheet" href="%s" />
<script src="%s"></script>
<style>
  html, body, #carte { height: 100%%; margin: 0; padding: 0; background: #15191D; }
</style>
</head>
<body>
<div id="carte"></div>
<script>
  var carte = L.map('carte');
  L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', {
      attribution: 'Imagerie &copy; Esri, Maxar, Earthstar Geographics', maxZoom: 19
  }).addTo(carte);
  carte.setView([46.6, 2.4], 6);

  var ligne = L.polyline([], {color: '#FF7828', weight: 4, opacity: 0.95}).addTo(carte);
  var marqueur = null;

  window.mettreAJourTrace = function(points) {
    if (!points || points.length === 0) return;
    ligne.setLatLngs(points);
    var dernier = points[points.length - 1];
    if (marqueur === null) {
      marqueur = L.circleMarker(dernier, {radius: 7, color: '#fff', weight: 2, fillColor: '#FF7828', fillOpacity: 1}).addTo(carte);
    } else {
      marqueur.setLatLng(dernier);
    }
    if (points.length === 1) {
      carte.setView(dernier, 16);
    } else {
      carte.fitBounds(L.latLngBounds(points), {padding: [30, 30], maxZoom: 17});
    }
  };
</script>
</body>
</html>"""


def _formater_chrono(secondes):
    secondes = int(secondes)
    h, reste = divmod(secondes, 3600)
    m, s = divmod(reste, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def _formater_allure(allure_min_km):
    if allure_min_km is None:
        return "--"
    minutes = int(allure_min_km)
    secondes = round((allure_min_km - minutes) * 60)
    if secondes == 60:
        minutes += 1
        secondes = 0
    return f"{minutes}:{secondes:02d} /km"


class SuiviDirect(QMainWindow):
    """Démarre, affiche et clôture un suivi en direct depuis le
    téléphone du coureur. Voir le docstring en tête de ce fichier pour
    le fonctionnement réseau (serveur HTTPS local, certificat
    auto-signé)."""

    def __init__(self, athlete_id_initial=None):
        super().__init__()

        self.setWindowTitle("TrailMaster Pro – Suivi en direct")
        self.resize(1000, 800)
        self.setMinimumSize(800, 600)

        self._url_suivi = None
        self._minuteur = QTimer(self)
        self._minuteur.setInterval(2000)
        self._minuteur.timeout.connect(self._actualiser_etat)
        self._carte_prete = False

        conteneur_scroll = QScrollArea()
        conteneur_scroll.setWidgetResizable(True)
        conteneur_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        conteneur_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        conteneur_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.setCentralWidget(conteneur_scroll)

        central = QWidget()
        conteneur_scroll.setWidget(central)

        principal = QVBoxLayout(central)
        principal.setContentsMargins(25, 20, 25, 20)
        principal.setSpacing(15)

        titre = QLabel("📡 Suivi en direct")
        titre.setObjectName("titrePage")
        sous_titre = QLabel(
            "Le coureur ouvre une page sur son téléphone (aucune appli à installer) — la "
            "carte, la distance, l'allure, la vitesse, le D+, la FC (si une ceinture Bluetooth "
            "est couplée) et le chrono s'affichent ici en direct pendant la sortie."
        )
        sous_titre.setObjectName("sousTitrePage")
        principal.addWidget(titre)
        principal.addWidget(sous_titre)

        # --- Zone de démarrage ---
        cadre_demarrage = QFrame()
        cadre_demarrage.setObjectName("carteForm")
        demarrage_layout = QVBoxLayout(cadre_demarrage)

        barre_demarrage = QHBoxLayout()
        label_athlete = QLabel("Athlète :")
        label_athlete.setObjectName("labelChamp")
        self.combo_athlete = QComboBox()
        for a in obtenir_athletes():
            self.combo_athlete.addItem(f"{a[2]} {a[1]}", a[0])
        if athlete_id_initial is not None:
            for i in range(self.combo_athlete.count()):
                if self.combo_athlete.itemData(i) == athlete_id_initial:
                    self.combo_athlete.setCurrentIndex(i)
                    break

        self.bouton_demarrer = QPushButton("📡 Démarrer un suivi en direct")
        self.bouton_demarrer.setObjectName("boutonPrincipal")
        self.bouton_demarrer.clicked.connect(self.demarrer)

        barre_demarrage.addWidget(label_athlete)
        barre_demarrage.addWidget(self.combo_athlete)
        barre_demarrage.addStretch()
        barre_demarrage.addWidget(self.bouton_demarrer)
        demarrage_layout.addLayout(barre_demarrage)

        self.label_url = QLineEdit("")
        self.label_url.setReadOnly(True)
        self.label_url.setVisible(False)
        self.label_url.setStyleSheet("font-size: 14px; padding: 8px;")
        demarrage_layout.addWidget(self.label_url)

        self.label_instructions = QLabel("")
        self.label_instructions.setObjectName("texteSecondaire")
        self.label_instructions.setWordWrap(True)
        demarrage_layout.addWidget(self.label_instructions)

        principal.addWidget(cadre_demarrage)

        # --- Statistiques en direct ---
        cadre_stats = QFrame()
        cadre_stats.setObjectName("carteForm")
        stats_layout = QGridLayout(cadre_stats)
        stats_layout.setHorizontalSpacing(20)
        stats_layout.setVerticalSpacing(10)

        self.labels_valeurs = {}
        stats_definies = [
            ("chrono", "Chrono"), ("distance", "Distance"), ("allure", "Allure"),
            ("vitesse", "Vitesse"), ("denivele", "D+"), ("fc", "FC"),
            ("fc_moyenne", "FC moyenne"), ("cadence", "Cadence"),
        ]
        for i, (cle, titre_stat) in enumerate(stats_definies):
            colonne, ligne = i % 4, i // 4
            bloc = QVBoxLayout()
            label_titre = QLabel(titre_stat)
            label_titre.setObjectName("texteSecondaire")
            label_valeur = QLabel("--")
            label_valeur.setStyleSheet("font-size: 22px; font-weight: 700;")
            bloc.addWidget(label_titre)
            bloc.addWidget(label_valeur)
            conteneur = QWidget()
            conteneur.setLayout(bloc)
            stats_layout.addWidget(conteneur, ligne, colonne)
            self.labels_valeurs[cle] = label_valeur

        principal.addWidget(cadre_stats)

        # --- Carte en direct ---
        cadre_carte = QFrame()
        cadre_carte.setObjectName("carteForm")
        carte_layout = QVBoxLayout(cadre_carte)
        self.vue_web = QWebEngineView()
        self.vue_web.setMinimumHeight(420)
        # Page locale (file://) devant charger les tuiles satellite
        # distantes — sans ça QtWebEngine bloque l'accès réseau distant
        # par défaut (voir la même remarque dans carte_reelle.py).
        self.vue_web.settings().setAttribute(
            QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True
        )
        self.vue_web.loadFinished.connect(self._carte_chargee)
        carte_layout.addWidget(self.vue_web)
        principal.addWidget(cadre_carte, 1)

        self.bouton_terminer = QPushButton("⏹ Terminer la sortie")
        self.bouton_terminer.setObjectName("boutonSecondaire")
        self.bouton_terminer.setEnabled(False)
        self.bouton_terminer.clicked.connect(self.terminer)
        principal.addWidget(self.bouton_terminer)

        self.setStyleSheet(obtenir_style_ecran())

        self._charger_carte_vide()

    def _charger_carte_vide(self):
        chemin_css = (DOSSIER_LEAFLET / "leaflet.css").as_uri()
        chemin_js = (DOSSIER_LEAFLET / "leaflet.js").as_uri()
        html = GABARIT_HTML_CARTE_DIRECT % (chemin_css, chemin_js)
        CHEMIN_TEMP_HTML_SUIVI.write_text(html, encoding="utf-8")
        self.vue_web.load(QUrl.fromLocalFile(str(CHEMIN_TEMP_HTML_SUIVI)))

    def _carte_chargee(self, succes):
        self._carte_prete = succes

    def demarrer(self):
        athlete_id = self.combo_athlete.currentData()
        if athlete_id is None:
            QMessageBox.warning(self, "Athlète requis", "Sélectionne un athlète.")
            return

        succes, message, url = demarrer_session(athlete_id)
        if not succes:
            QMessageBox.critical(self, "Impossible de démarrer", message)
            return

        self._url_suivi = url
        self.label_url.setText(url)
        self.label_url.setVisible(True)
        self.label_instructions.setText(
            "Ouvre cette adresse dans le navigateur du téléphone (même réseau Wi-Fi), puis "
            "appuie sur « Démarrer le suivi ». Le navigateur affichera un avertissement de "
            "sécurité (« Connexion non privée ») car le certificat est auto-signé, propre à "
            "cet ordinateur — c'est normal, appuie sur « Avancé » puis « Continuer »."
        )
        self.bouton_demarrer.setEnabled(False)
        self.combo_athlete.setEnabled(False)
        self.bouton_terminer.setEnabled(True)
        self._minuteur.start()

    def _actualiser_etat(self):
        etat = etat_session()
        if etat is None:
            self._minuteur.stop()
            return

        self.labels_valeurs["chrono"].setText(_formater_chrono(etat["duree_s"]))
        self.labels_valeurs["distance"].setText(f"{etat['distance_km']:.2f} km")
        self.labels_valeurs["allure"].setText(_formater_allure(etat["allure_min_km"]))
        self.labels_valeurs["vitesse"].setText(f"{etat['vitesse_kmh']:.1f} km/h")
        self.labels_valeurs["denivele"].setText(f"{etat['denivele_positif']} m")
        self.labels_valeurs["fc"].setText(f"{etat['fc_instantanee']} bpm" if etat["fc_instantanee"] else "--")
        self.labels_valeurs["fc_moyenne"].setText(f"{etat['fc_moyenne']} bpm" if etat["fc_moyenne"] else "--")
        self.labels_valeurs["cadence"].setText(f"{etat['cadence_moyenne']} spm" if etat["cadence_moyenne"] else "--")

        if self._carte_prete and etat["trace"]:
            self.vue_web.page().runJavaScript(f"window.mettreAJourTrace({json.dumps(etat['trace'])});")

    def terminer(self):
        if not session_active():
            return

        confirmation = QMessageBox.question(
            self, "Terminer la sortie",
            "Arrêter le suivi et enregistrer la sortie dans l'historique des activités ?"
        )
        if confirmation != QMessageBox.StandardButton.Yes:
            return

        self._minuteur.stop()
        succes, message, activite_id = terminer_session()
        self.bouton_terminer.setEnabled(False)

        if not succes:
            QMessageBox.warning(self, "Sortie non enregistrée", message)
            return

        reponse = QMessageBox.information(
            self, "Sortie enregistrée",
            "La sortie a été ajoutée à l'historique des activités. Si tu synchronises plus "
            "tard la même sortie depuis Garmin ou Strava, va dans « Nettoyage des doublons » "
            "pour fusionner les deux et garder les chiffres les plus précis.",
        )

        self.bouton_demarrer.setEnabled(True)
        self.combo_athlete.setEnabled(True)
        self.label_url.setVisible(False)
        self.label_instructions.setText("")
