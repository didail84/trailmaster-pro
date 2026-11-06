"""
Manifeste Relais (étape 8), sans Qt ni réseau.

Un manifeste décrit une version publiée d'un logiciel : numéro, canal
(stable ou test), notes, et pour chaque plateforme le fichier à installer
avec son empreinte SHA-256 et sa taille. Il est signé (Ed25519) avec la clé
privée de Didier ; le logiciel ne connaît que la clé publique : un
manifeste modifié, ou un fichier qui ne correspond pas à son empreinte,
est refusé.

    {"format": "relais/1", "logiciel": "trail-hub-center", "version": "109", "canal": "stable",
     "publie_le": "2026-11-06T12:00:00", "notes": "…", "minimum": "100",
     "fichiers": [{"plateforme": "linux-x64", "type": "appimage", "nom": "…", "url": "…",
                   "sha256": "…", "taille": 123}],
     "signature": "base64…"}
"""

import base64
import hashlib
import json
import re
from pathlib import Path

FORMAT = "relais/1"
LOGICIEL = "trail-hub-center"
CANAUX = (("stable", "Stable"), ("test", "Test (versions d'essai)"))
FICHIER_CLE_PUBLIQUE = Path(__file__).resolve().parent / "cle_publique.pem"


class ErreurRelais(Exception):
    """Message lisible."""


def canonique(m):
    """Octets signés : le manifeste sans sa signature, clés triées, sans espaces."""
    return json.dumps({k: v for k, v in m.items() if k != "signature"}, sort_keys=True, ensure_ascii=False,
                      separators=(",", ":")).encode("utf-8")


def signer(m, cle_privee_pem):
    from cryptography.hazmat.primitives.serialization import load_pem_private_key
    cle = load_pem_private_key(cle_privee_pem if isinstance(cle_privee_pem, bytes) else cle_privee_pem.encode(), None)
    return {**m, "signature": base64.b64encode(cle.sign(canonique(m))).decode()}


def cle_publique():
    """Clé publique livrée avec le logiciel, ou None tant qu'elle n'est pas créée."""
    try:
        return FICHIER_CLE_PUBLIQUE.read_bytes()
    except OSError:
        return None


def verifier_signature(m, cle_publique_pem=None):
    """True si signé par la clé ; False si signature fausse ; None si pas de clé connue ou pas de signature."""
    pem = cle_publique_pem if cle_publique_pem is not None else cle_publique()
    if not pem or not m.get("signature"):
        return None
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives.serialization import load_pem_public_key
    try:
        load_pem_public_key(pem).verify(base64.b64decode(m["signature"]), canonique(m))
        return True
    except (InvalidSignature, ValueError):
        return False


def numero(v):
    """« V109 », « 109 », « 1.2.3 » → tuple comparable."""
    t = [int(x) for x in re.findall(r"\d+", str(v or ""))]
    return tuple(t) or (0,)


def valider(m, cle_publique_pem=None, exiger_signature=None):
    """Contrôle un manifeste reçu. Renvoie {manifeste, signe} ou lève ErreurRelais.
    exiger_signature : par défaut, oui dès qu'une clé publique est livrée avec le logiciel."""
    if not isinstance(m, dict) or m.get("format") != FORMAT:
        raise ErreurRelais("Ce n'est pas un manifeste Relais.")
    if m.get("logiciel") != LOGICIEL:
        raise ErreurRelais("Ce manifeste est celui d'un autre logiciel.")
    for f in m.get("fichiers") or []:
        if not re.fullmatch(r"[0-9a-f]{64}", str(f.get("sha256", ""))) or not str(f.get("url", "")).startswith("https://"):
            raise ErreurRelais("Fichier mal décrit dans le manifeste (empreinte ou adresse).")
    pem = cle_publique_pem if cle_publique_pem is not None else cle_publique()
    sig = verifier_signature(m, pem)
    if sig is False:
        raise ErreurRelais("Signature du manifeste invalide : mise à jour refusée.")
    if (exiger_signature if exiger_signature is not None else bool(pem)) and sig is not True:
        raise ErreurRelais("Manifeste non signé : mise à jour refusée.")
    return {"manifeste": m, "signe": bool(sig)}


def fichier_pour(m, plateforme, types_preferes):
    """Le fichier du manifeste pour cette plateforme, dans l'ordre de préférence des types."""
    l = [f for f in m.get("fichiers") or [] if f.get("plateforme") == plateforme]
    for t in types_preferes:
        for f in l:
            if f.get("type") == t:
                return f
    return None


def empreinte(chemin):
    h = hashlib.sha256()
    with open(chemin, "rb") as f:
        for bloc in iter(lambda: f.read(1 << 20), b""):
            h.update(bloc)
    return h.hexdigest()


TYPES_PAR_EXTENSION = ((".AppImage", "appimage"), (".deb", "deb"), (".dmg", "dmg"), ("-portable.zip", "portable"),
                       (".exe", "installateur"), (".tar.gz", "archive"))


def decrire_fichier(chemin, url_base):
    """Entrée « fichiers » d'un installateur fabriqué (nom de la forme TrailMasterPro-<v>-<os>-<arch>.<ext>)."""
    p = Path(chemin)
    m = re.match(r"TrailMasterPro-[^-]+-(windows|mac|linux)-(x64|arm64|amd64|portable)", p.name)
    if not m:
        return None
    os_, arch = m.group(1), m.group(2)
    if arch == "amd64":
        arch = "x64"
    if arch == "portable":
        arch = "x64"
    type_ = next((t for ext, t in TYPES_PAR_EXTENSION if p.name.endswith(ext)), None)
    if not type_:
        return None
    return {"plateforme": f"{os_}-{arch}", "type": type_, "nom": p.name, "url": f"{url_base.rstrip('/')}/{p.name}",
            "sha256": empreinte(p), "taille": p.stat().st_size}


def construire(version, fichiers, canal="stable", notes="", publie_le=None, minimum=None):
    from datetime import datetime
    return {"format": FORMAT, "logiciel": LOGICIEL, "version": str(version), "canal": canal, "notes": notes or "",
            "publie_le": publie_le or datetime.now().isoformat(timespec="seconds"), "minimum": minimum,
            "fichiers": [f for f in fichiers if f]}
