"""
Fabrique le manifeste Relais d'une version : python packaging/relais_manifeste.py <dossier des installateurs>
<étiquette> [--canal test]. Signé si la clé privée est donnée (variable RELAIS_CLE_PRIVEE, ou fichier
~/.relais/trail-hub-center.pem). Écrit <dossier>/relais.json.

Créer les clés, une seule fois, sur ton ordinateur :  python packaging/relais_manifeste.py --creer-cles
  - la clé privée va dans ~/.relais/trail-hub-center.pem (à garder pour toi, et à copier dans le secret
    GitHub RELAIS_CLE_PRIVEE du dépôt) ;
  - la clé publique va dans noyau/relais/cle_publique.pem (à publier avec le code).
"""

import json
import os
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

from noyau.relais import manifeste as M  # noqa: E402

CLE_PRIVEE = Path.home() / ".relais" / "trail-hub-center.pem"


def creer_cles():
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    if CLE_PRIVEE.exists():
        print("Une clé privée existe déjà :", CLE_PRIVEE)
        return
    k = Ed25519PrivateKey.generate()
    CLE_PRIVEE.parent.mkdir(mode=0o700, exist_ok=True)
    CLE_PRIVEE.write_bytes(k.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                           serialization.NoEncryption()))
    os.chmod(CLE_PRIVEE, 0o600)
    M.FICHIER_CLE_PUBLIQUE.write_bytes(k.public_key().public_bytes(serialization.Encoding.PEM,
                                                                   serialization.PublicFormat.SubjectPublicKeyInfo))
    print("Clé privée :", CLE_PRIVEE, "(ne la donne à personne ; copie-la dans le secret GitHub RELAIS_CLE_PRIVEE)")
    print("Clé publique :", M.FICHIER_CLE_PUBLIQUE, "(à envoyer sur GitHub avec le code)")


def main(argv):
    if "--creer-cles" in argv:
        return creer_cles()
    dossier, etiquette = Path(argv[0]), argv[1]
    canal = argv[argv.index("--canal") + 1] if "--canal" in argv else "stable"
    url = f"https://github.com/didail84/trailmaster-pro/releases/download/{etiquette}"
    fichiers = [M.decrire_fichier(p, url) for p in sorted(dossier.iterdir()) if p.is_file() and p.name != "relais.json"]
    notes = os.environ.get("RELAIS_NOTES", "")
    m = M.construire(etiquette.lstrip("vV"), fichiers, canal, notes)
    cle = os.environ.get("RELAIS_CLE_PRIVEE") or (CLE_PRIVEE.read_text() if CLE_PRIVEE.exists() else None)
    if cle:
        m = M.signer(m, cle)
    (dossier / "relais.json").write_text(json.dumps(m, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"relais.json : {len(m['fichiers'])} fichier(s), {'signé' if cle else 'NON signé'}")


if __name__ == "__main__":
    main(sys.argv[1:])
