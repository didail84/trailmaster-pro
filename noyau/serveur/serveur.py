"""
Serveur Trail Hub Center (étape 5) : une seule base pour plusieurs personnes, sur le NAS ou un ordinateur
allumé. Bibliothèque standard (ThreadingHTTPServer) ; HTTPS avec un certificat créé sur place.

- /api/…  pour le logiciel de bureau (jeton dans l'en-tête Authorization) ;
- /m/…    pages web pour le téléphone (cookie de session, jeton anti-falsification dans chaque formulaire).

Écoute par défaut sur le réseau local (port 8770). L'accès depuis Internet se fera plus tard par un tunnel
sécurisé (Tailscale ou Cloudflare), jamais en ouvrant un port de la box.
"""

import hashlib
import hmac
import json
import secrets
import socket
import ssl
import threading
import time
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from noyau.donnees import comptes as dco
from noyau.serveur import rpc, web

PORT_DEFAUT = 8770
TAILLE_MAX = 25 * 1024 * 1024
NOM_COOKIE = "thc_session"
VERSION_API = 1

_etat = {"serveur": None, "thread": None, "https": False, "port": None, "secret": None}
_echecs_ip = {}
_verrou_ip = threading.Lock()


# ------------------------------------------------------------------ préparation

def preparer_base():
    """Mode WAL : lectures et écritures simultanées sans se bloquer. Base migrée à la dernière version."""
    import data.database as db
    db.creer_base_de_donnees()
    c = db.connexion()
    try:
        c.execute("PRAGMA journal_mode=WAL")
        c.execute("PRAGMA busy_timeout=8000")
    finally:
        c.close()


def secret_serveur():
    """Clé propre à ce serveur, pour signer les jetons anti-falsification des formulaires."""
    if _etat["secret"]:
        return _etat["secret"]
    from data.database import obtenir_parametre, definir_parametre
    s = obtenir_parametre("serveur_secret")
    if not s:
        s = secrets.token_hex(32)
        definir_parametre("serveur_secret", s)
    _etat["secret"] = s
    return s


def csrf_pour(jeton):
    return hmac.new(secret_serveur().encode(), (jeton or "").encode(), hashlib.sha256).hexdigest()[:40]


def adresses_locales():
    ips = set()
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.255.255.255", 1))
        ips.add(s.getsockname()[0])
        s.close()
    except OSError:
        pass
    try:
        for i in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ips.add(i[4][0])
    except OSError:
        pass
    ips.discard("127.0.0.1")
    return sorted(ips) or ["127.0.0.1"]


def certificat(dossier):
    """(chemin du certificat, de la clé, empreinte SHA-256) ; créés au premier lancement, valables 10 ans."""
    dossier = Path(dossier)
    cert, cle = dossier / "serveur_cert.pem", dossier / "serveur_cle.pem"
    if not (cert.exists() and cle.exists()):
        from cryptography import x509
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import ec
        from cryptography.x509.oid import NameOID
        import datetime as dt
        import ipaddress
        dossier.mkdir(parents=True, exist_ok=True)
        k = ec.generate_private_key(ec.SECP256R1())
        nom = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "trailhub.local")])
        noms = [x509.DNSName("trailhub.local"), x509.DNSName("localhost")]
        for ip in adresses_locales() + ["127.0.0.1"]:
            try:
                noms.append(x509.IPAddress(ipaddress.ip_address(ip)))
            except ValueError:
                pass
        maintenant = dt.datetime.now(dt.timezone.utc)
        c = (x509.CertificateBuilder().subject_name(nom).issuer_name(nom).public_key(k.public_key())
             .serial_number(x509.random_serial_number()).not_valid_before(maintenant - dt.timedelta(days=1))
             .not_valid_after(maintenant + dt.timedelta(days=3650))
             .add_extension(x509.SubjectAlternativeName(noms), critical=False).sign(k, hashes.SHA256()))
        cle.write_bytes(k.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                        serialization.NoEncryption()))
        try:
            cle.chmod(0o600)
        except OSError:
            pass
        cert.write_bytes(c.public_bytes(serialization.Encoding.PEM))
    der = ssl.PEM_cert_to_DER_cert(cert.read_text())
    return str(cert), str(cle), empreinte(der)


def empreinte(der):
    h = hashlib.sha256(der).hexdigest().upper()
    return ":".join(h[i:i + 2] for i in range(0, len(h), 2))


def _trop_d_echecs(ip):
    with _verrou_ip:
        t = time.time()
        l = [x for x in _echecs_ip.get(ip, []) if t - x < 600]
        _echecs_ip[ip] = l
        return len(l) >= 20


def _noter_echec(ip):
    with _verrou_ip:
        _echecs_ip.setdefault(ip, []).append(time.time())


# ------------------------------------------------------------------ requêtes

class Gestionnaire(BaseHTTPRequestHandler):
    server_version = "TrailHubCenter"
    sys_version = ""
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):                  # pas de bruit dans la console du NAS
        pass

    # -- outils
    def _ip(self):
        return self.client_address[0]

    def _envoyer(self, code, corps, type_="text/html; charset=utf-8", entetes=None):
        b = corps.encode("utf-8") if isinstance(corps, str) else corps
        self.send_response(code)
        self.send_header("Content-Type", type_)
        self.send_header("Content-Length", str(len(b)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", "default-src 'none'; style-src 'unsafe-inline'; img-src 'self' data:; "
                                                    "script-src 'self'; connect-src 'self'; "
                                                    "form-action 'self'; frame-ancestors 'none'; base-uri 'none'")
        if _etat["https"]:
            self.send_header("Strict-Transport-Security", "max-age=31536000")
        for k, v in (entetes or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(b)

    def _json(self, code, donnees):
        self._envoyer(code, rpc.vers_json(donnees), "application/json; charset=utf-8")

    def _rediriger(self, ou, cookie=None):
        e = {"Location": ou}
        if cookie is not None:
            e["Set-Cookie"] = cookie
        self._envoyer(303, "", entetes=e)

    def _corps(self):
        n = int(self.headers.get("Content-Length") or 0)
        if n > TAILLE_MAX:
            raise ValueError("Envoi trop gros.")
        return self.rfile.read(n) if n else b""

    def _formulaire(self):
        return {k: v[0] for k, v in parse_qs(self._corps().decode("utf-8"), keep_blank_values=True).items()}

    def _cookie_session(self):
        c = SimpleCookie(self.headers.get("Cookie") or "")
        return c[NOM_COOKIE].value if NOM_COOKIE in c else None

    def _cookie(self, jeton, effacer=False):
        attrs = f"{NOM_COOKIE}={'' if effacer else jeton}; Path=/; HttpOnly; SameSite=Strict"
        if _etat["https"]:
            attrs += "; Secure"
        if effacer:
            attrs += "; Max-Age=0"
        return attrs

    # -- verbes
    def do_GET(self):
        self._traiter("GET")

    def do_POST(self):
        self._traiter("POST")

    def _traiter(self, verbe):
        try:
            u = urlparse(self.path)
            q = {k: v[0] for k, v in parse_qs(u.query).items()}
            if u.path.startswith("/api/"):
                return self._api(verbe, u.path, q)
            if u.path in ("/", ""):
                return self._rediriger("/m/")
            if u.path.startswith("/m"):
                return self._web(verbe, u.path, q)
            if u.path.startswith("/live/"):
                from noyau.serveur import web_course
                return web_course.page_publique(self, u.path[6:].strip("/"), q)
            self._envoyer(404, web.erreur(None, "Page introuvable.", 404))
        except ValueError as e:
            self._envoyer(400, web.erreur(None, str(e), 400))
        except Exception as e:                           # jamais de trace d'erreur vers le réseau : au journal
            import traceback
            try:
                dco.journaliser(None, None, "erreur", self.path[:200], detail=traceback.format_exc()[-480:],
                                adresse=self._ip(), reussi=False)
            except Exception:
                pass
            self._envoyer(500, web.erreur(None, "Erreur sur le serveur.", 500))

    # -- API du logiciel de bureau
    def _compte_api(self):
        a = self.headers.get("Authorization") or ""
        return dco.session(a[7:].strip()) if a.startswith("Bearer ") else None

    def _api(self, verbe, chemin, q):
        if chemin == "/api/info":
            import data.migrations as mig
            return self._json(200, {"application": "Trail Hub Center", "api": VERSION_API, "https": _etat["https"],
                                    "base": mig.VERSION_LOGICIEL})
        if verbe != "POST":
            return self._json(405, {"erreur": {"type": "Methode", "message": "POST attendu."}})
        try:
            donnees = json.loads(self._corps() or b"{}")
        except ValueError:
            return self._json(400, {"erreur": {"type": "Requete", "message": "JSON illisible."}})
        if chemin == "/api/connexion":
            if _trop_d_echecs(self._ip()):
                return self._json(429, {"erreur": {"type": "ErreurCompte", "message": "Trop d'essais : réessaie dans 10 minutes."}})
            try:
                j, c = dco.authentifier(donnees.get("identifiant"), donnees.get("mot_de_passe"), self._ip(), "bureau",
                                        donnees.get("appareil"))
            except dco.ErreurCompte as e:
                _noter_echec(self._ip())
                return self._json(401, {"erreur": {"type": "ErreurCompte", "message": str(e)}})
            return self._json(200, {"jeton": j, "compte": c})
        c = self._compte_api()
        if not c:
            return self._json(401, {"erreur": {"type": "Session", "message": "Connexion expirée : reconnecte-toi."}})
        if chemin == "/api/moi":
            return self._json(200, {"compte": c})
        if chemin == "/api/deconnexion":
            dco.deconnecter((self.headers.get("Authorization") or "")[7:].strip())
            return self._json(200, {"ok": True})
        if chemin == "/api/mot_de_passe":
            try:
                dco.changer_mot_de_passe(c["id"], donnees.get("nouveau"), donnees.get("ancien"))
            except dco.ErreurCompte as e:
                return self._json(400, {"erreur": {"type": "ErreurCompte", "message": str(e)}})
            dco.journaliser(c["id"], c["identifiant"], "mot_de_passe", adresse=self._ip())
            return self._json(200, {"ok": True})
        if chemin == "/api/copie":
            if not any(r["role"] == "admin" for r in c["roles"]):
                return self._json(403, {"erreur": {"type": "Refus", "message": "Réservé à l'administrateur."}})
            return self._envoyer(200, copie_base(), "application/octet-stream")
        if chemin == "/api/rpc":
            if c.get("doit_changer"):
                return self._json(403, {"erreur": {"type": "Refus", "message": "Change d'abord ton mot de passe provisoire."}})
            r = rpc.executer(c, donnees.get("module"), donnees.get("fonction"), donnees.get("args"),
                             donnees.get("kwargs"), self._ip(), donnees.get("contexte"))
            return self._json(200, r)
        return self._json(404, {"erreur": {"type": "Requete", "message": "Adresse inconnue."}})

    # -- pages web
    def _web(self, verbe, chemin, q):
        if chemin == "/m/connexion":
            if verbe == "GET":
                return self._envoyer(200, web.connexion())
            f = self._formulaire()
            if _trop_d_echecs(self._ip()):
                return self._envoyer(429, web.connexion("Trop d'essais : réessaie dans 10 minutes.", f.get("identifiant", "")))
            try:
                j, _c = dco.authentifier(f.get("identifiant"), f.get("mot_de_passe"), self._ip(), "web",
                                         self.headers.get("User-Agent"))
            except dco.ErreurCompte as e:
                _noter_echec(self._ip())
                return self._envoyer(401, web.connexion(str(e), f.get("identifiant", "")))
            return self._rediriger("/m/", self._cookie(j))
        jeton = self._cookie_session()
        c = dco.session(jeton)
        if not c:
            return self._rediriger("/m/connexion")
        csrf = csrf_pour(jeton)
        f = {}
        if verbe == "POST":
            f = self._formulaire()
            if not hmac.compare_digest(f.get("csrf", ""), csrf):
                return self._envoyer(403, web.erreur(c, "Formulaire expiré : recharge la page."))
        if chemin == "/m/deconnexion":
            dco.deconnecter(jeton)
            dco.journaliser(c["id"], c["identifiant"], "deconnexion", adresse=self._ip())
            return self._rediriger("/m/connexion", self._cookie("", effacer=True))
        if chemin == "/m/mot-de-passe" or c.get("doit_changer"):
            if verbe == "POST" and chemin == "/m/mot-de-passe":
                if f.get("nouveau") != f.get("nouveau2"):
                    return self._envoyer(200, web.changer_mot_de_passe(c, csrf, "Les deux mots de passe sont différents.",
                                                                       bool(c.get("doit_changer"))))
                try:
                    dco.changer_mot_de_passe(c["id"], f.get("nouveau"), f.get("ancien"))
                except dco.ErreurCompte as e:
                    return self._envoyer(200, web.changer_mot_de_passe(c, csrf, str(e), bool(c.get("doit_changer"))))
                dco.journaliser(c["id"], c["identifiant"], "mot_de_passe", adresse=self._ip())
                return self._rediriger("/m/")
            return self._envoyer(200, web.changer_mot_de_passe(c, csrf, impose=bool(c.get("doit_changer"))))
        if chemin in ("/m", "/m/"):
            return self._envoyer(200, web.accueil(c))
        if chemin in ("/m/chrono", "/m/chrono-annuler"):
            ev = int(q.get("ev") or 0)
            pc = int(q["pc"]) if str(q.get("pc") or "").isdigit() else None
            if not web.peut_evenement(c, "chrono", ev):
                return self._refus(c)
            if verbe == "POST":
                msg, cl = (web.top_chrono(c, ev, f.get("dossard"), self._ip(), pc) if chemin == "/m/chrono"
                           else web.annuler_dernier_top(c, ev, self._ip(), pc))
                return self._envoyer(200, web.chrono(c, csrf, ev, msg, cl, pc))
            return self._envoyer(200, web.chrono(c, csrf, ev, point_id=pc))
        if chemin == "/m/appel":
            s = int(q.get("seance") or 0)
            if not web.peut_seance(c, s):
                return self._refus(c)
            msg = web.enregistrer_appel(c, s, f, self._ip()) if verbe == "POST" else None
            return self._envoyer(200, web.appel(c, csrf, s, msg))
        if chemin == "/m/poste":
            ev = int(q.get("ev") or 0)
            if not web.peut_evenement(c, "poste", ev):
                return self._refus(c)
            return self._envoyer(200, web.poste(c, ev, csrf))
        if chemin == "/m/resultats":
            if "resultats" not in web.D.pages_autorisees(c["roles"]):
                return self._refus(c)
            return self._envoyer(200, web.resultats(c))
        for prefixe, gestion in PAGES_EN_PLUS.items():               # incidents, commandement, Kids (étapes suivantes)
            if chemin.startswith(prefixe):
                return gestion(self, c, csrf, verbe, chemin, q, f)
        self._envoyer(404, web.erreur(c, "Page introuvable.", 404))

    def _refus(self, c):
        dco.journaliser(c["id"], c["identifiant"], "refus", self.path, adresse=self._ip(), reussi=False)
        self._envoyer(403, web.erreur(c, "Ton compte n'a pas accès à cette page."))


PAGES_EN_PLUS = {}          # préfixe -> gestion(handler, compte, csrf, verbe, chemin, q, formulaire)


def _brancher_pages():
    from noyau.serveur import web_course                      # étape 6 : incidents, commandement, présence
    PAGES_EN_PLUS.update(web_course.PAGES)


_brancher_pages()


def copie_base():
    """Copie cohérente de la base (même pendant des écritures), sans les comptes ni les sessions ni le journal :
    pour la page Claude ou une sauvegarde."""
    import sqlite3
    import tempfile
    import data.database as db
    with tempfile.TemporaryDirectory() as d:
        dest = Path(d) / "copie.db"
        src = sqlite3.connect(db.CHEMIN_BDD)
        cible = sqlite3.connect(dest)
        try:
            src.backup(cible)
            for t in ("sessions_serveur", "comptes_roles", "comptes", "journal_acces"):
                cible.execute(f"DELETE FROM {t}")
            cible.execute("DELETE FROM parametres_app WHERE cle LIKE 'serveur_%'")
            cible.commit()
            cible.execute("VACUUM")
        finally:
            src.close()
            cible.close()
        return dest.read_bytes()


# ------------------------------------------------------------------ démarrage

def demarrer(port=PORT_DEFAUT, https=True, hote="0.0.0.0", dossier_certificat=None, en_fond=True):
    """Démarre le serveur ; renvoie {adresses, port, https, empreinte}."""
    if _etat["serveur"]:
        return infos()
    preparer_base()
    secret_serveur()
    dco.purger_sessions()
    srv = ThreadingHTTPServer((hote, port), Gestionnaire)
    srv.daemon_threads = True
    emp = None
    if https:
        import data.database as db
        cert, cle, emp = certificat(dossier_certificat or Path(db.CHEMIN_BDD).parent / "certificats_serveur")
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.minimum_version = ssl.TLSVersion.TLSv1_2
        ctx.load_cert_chain(cert, cle)
        srv.socket = ctx.wrap_socket(srv.socket, server_side=True)
    _etat.update(serveur=srv, https=https, port=srv.server_address[1], empreinte=emp)
    if en_fond:
        t = threading.Thread(target=srv.serve_forever, name="serveur-trailhub", daemon=True)
        t.start()
        _etat["thread"] = t
    else:
        srv.serve_forever()
    return infos()


def infos():
    if not _etat["serveur"]:
        return None
    sch = "https" if _etat["https"] else "http"
    return {"adresses": [f"{sch}://{ip}:{_etat['port']}" for ip in adresses_locales()], "port": _etat["port"],
            "https": _etat["https"], "empreinte": _etat.get("empreinte")}


def actif():
    return _etat["serveur"] is not None


def arreter():
    s = _etat["serveur"]
    if s:
        s.shutdown()
        s.server_close()
    _etat.update(serveur=None, thread=None, port=None)
