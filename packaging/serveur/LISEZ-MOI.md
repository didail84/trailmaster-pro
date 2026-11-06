# Serveur Trail Hub Center sur le NAS

Le serveur garde la base du club et des courses ; le bureau, les entraîneurs et les bénévoles s'y
connectent depuis le logiciel de bureau ou depuis leur téléphone (pages `/m/`). L'espace Coureur
de chacun reste sur son ordinateur.

## 1. Installer (PC Dell sous OpenMediaVault, ou tout Linux)

```bash
sudo apt install python3 python3-cryptography git
sudo useradd --system --home /opt/trailhub trailhub
sudo git clone -b trail-hub-center https://github.com/didail84/trailmaster-pro /opt/trailhub
sudo mkdir -p /srv/trailhub && sudo chown trailhub /srv/trailhub
```

Seule la bibliothèque `cryptography` est nécessaire (pour le certificat HTTPS) : pas de PySide6 sur le NAS.

## 2. Créer le compte administrateur

```bash
sudo -u trailhub python3 /opt/trailhub/trailhub_serveur.py --base /srv/trailhub/trail_hub.db --creer-admin didier
```

Pour reprendre la base actuelle du club, copie ton fichier `.db` dans `/srv/trailhub/trail_hub.db` avant
cette étape : il est mis à jour tout seul (version 14).

## 3. Démarrer tout seul au démarrage du NAS

```bash
sudo cp /opt/trailhub/packaging/serveur/trailhub-serveur.service /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now trailhub-serveur
journalctl -u trailhub-serveur -n 20        # affiche l'adresse et l'empreinte du certificat
```

## 4. Se connecter

- **Logiciel de bureau** : Outils > Serveur > « Se connecter à un serveur », adresse `https://IP-DU-NAS:8770`.
  Compare l'empreinte affichée avec celle du journal du NAS, puis redémarre le logiciel.
- **Téléphone** : `https://IP-DU-NAS:8770/m/`. Le navigateur prévient que le certificat est « non reconnu »
  (il est fabriqué par le NAS, pas par une autorité) : accepte-le une fois.

## Sécurité

- Mots de passe stockés en empreintes (PBKDF2, 310 000 tours) ; compte bloqué 15 min après 5 essais.
- Chaque écriture et chaque refus vont au journal des accès (gardé un an).
- Le serveur n'écoute que le réseau local. **N'ouvre pas de port sur la box** : l'accès depuis
  l'extérieur se fera par un tunnel sécurisé (Tailscale ou Cloudflare Tunnel), plus tard.
- Sauvegarde : copie `/srv/trailhub/` chaque nuit sur le NAS secondaire (fichiers `.db`, `.db-wal`, `.db-shm`).
