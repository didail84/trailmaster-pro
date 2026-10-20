# TrailMaster Pro

Logiciel gratuit et open source de **suivi d'entraînement trail running** pour Mac et Windows.
Tes données restent **sur ton ordinateur** : pas de compte, pas de serveur, pas d'abonnement.

> Interface en français · Python 3 + PySide6 · licence MIT

## Ce que fait le logiciel

- **Tableau de bord** : forme du jour, charge d'entraînement, fatigue, dernière sortie.
- **Sorties** : liste mois par mois, jours de repos automatiques, saisie manuelle, détail de chaque sortie (carte, profil, allure, FC).
- **Calendrier** à la semaine, au mois ou à l'année, avec le détail d'une sortie au clic.
- **Analyses** : forme et fatigue, records et prédictions de temps, VO2max, évolution des performances sur 2 ans.
- **VMA & circuits** : VMA estimée à partir de tes sorties, allures conseillées, évolution de ton chrono, de ton allure et de ta vitesse sur chaque circuit.
- **Suivi** : poids, état des jambes, fatigue, blessures, soins, matériel, nutrition, objectifs.
- **Plans d'entraînement** et séances structurées, parcours GPX, cartes, secteurs d'entraînement.
- **Import** : Strava (synchronisation), export Garmin Connect, fichiers .FIT / .GPX, copie depuis la montre en USB.
- **Mode « Affichage simplifié »** pour ne voir que l'essentiel.

## Installation

Va dans **[Releases](https://github.com/didail84/trailmaster-pro/releases/latest)** et télécharge le fichier qui correspond à ton ordinateur (rubrique *Assets*) :

| Ordinateur | Fichier |
|---|---|
| Windows 10 ou 11 | `TrailMasterPro-xx-windows-x64.exe` |
| Mac Intel (jusqu'à 2020, macOS 12 Monterey ou plus récent) | `TrailMasterPro-xx-mac-x64.dmg` |
| Mac Apple Silicon (M1, M2, M3, M4…) | `TrailMasterPro-xx-mac-arm64.dmg` |

Pas besoin d'installer Python.

### Windows
1. Double-clique sur le fichier `.exe`.
2. Si Windows affiche « Windows a protégé votre ordinateur » : **Informations complémentaires** → **Exécuter quand même** (l'appli n'est pas signée par un certificat payant).
3. Suis l'installation : TrailMaster Pro apparaît dans le menu Démarrer (et sur le Bureau si tu as coché la case).

### Mac
1. Ouvre le `.dmg` et fais glisser **TrailMaster Pro** dans **Applications** (remplace l'ancienne version s'il y en a une).
2. La première fois : dans Applications, **clic droit (ou Ctrl-clic) → Ouvrir** → **Ouvrir**.
3. Si macOS dit que l'app est « endommagée » : ouvre le Terminal et tape
   `xattr -cr "/Applications/TrailMaster Pro.app"`, puis relance.

### Depuis le code source (développeurs)
Python 3.11 ou plus récent :

```bash
pip install -r requirements.txt
python3 main.py
```

Les scripts `Installer_MacBook.command` et `Installer_Windows.bat` fabriquent aussi l'application directement sur ton ordinateur.

## Premiers pas

1. Crée ton profil d'athlète depuis l'écran Athlètes du menu.
2. Importe tes sorties : Strava (écran Strava du logiciel), un export Garmin Connect, ou des fichiers .FIT/.GPX.
3. Ouvre *Analyses & Forme* pour voir ta forme, ta VMA estimée et tes circuits.

### Connecter Strava

Strava demande à chaque utilisateur sa propre « application » (gratuit) :
crée-la sur <https://www.strava.com/settings/api>, puis recopie l'identifiant client et le code secret dans l'écran Strava du logiciel.
Ils sont enregistrés uniquement dans ta base locale.

## Où sont mes données ?

Dans un seul fichier, `trailmaster.db` :

| Façon de lancer | Emplacement |
|---|---|
| Application installée | Mac : `~/Library/Application Support/TrailMaster Pro/` · Windows : `%APPDATA%\TrailMaster Pro\` |
| `python3 main.py` | `data/trailmaster.db` (ou le dossier ci-dessus si le dossier `data/` n'en contient pas) |

Fais des sauvegardes de ce fichier. **Il contient tes données de santé et tes clés : ne le publie jamais.**
Si le logiciel s'ouvre vide après une mise à jour, lance `Retrouver_ma_base.command` : il retrouve tes bases sur l'ordinateur et remet la bonne en service.

## Mises à jour

Au démarrage, le logiciel regarde s'il existe une version plus récente dans les *Releases* de ce dépôt. Un clic sur « Mettre à jour » télécharge le bon installateur pour ton ordinateur et l'ouvre. Ta base n'est pas touchée.

## Pour les développeurs

- Code : `interface/` (écrans PySide6), `data/` (base SQLite et références), `packaging/` (fabrication des installateurs).
- Chaque écran de liste repose sur `interface/ecran_liste.py`.
- Lancer en test : `python3 main.py`. Vérifier la syntaxe : `python3 -m compileall interface data`.
- Voir `CONTRIBUTING.md`. Les nouveautés sont notées dans `CHANGELOG.md`.

## Publier une version (mainteneur)

1. Augmente le nombre dans `VERSION` et ajoute une ligne dans `CHANGELOG.md`.
2. Sur GitHub : *Releases → Draft a new release*, étiquette `V100` (le même nombre que `VERSION`), puis **Publish release**.
3. GitHub fabrique tout seul les installateurs Windows et Mac (`.github/workflows/installateurs.yml`, environ 15 minutes) et les ajoute à la release.

Ne joins jamais ta base (`trailmaster.db`) ni tes exports : le fichier `.gitignore` les exclut déjà.

## Licence

MIT, voir `LICENSE`. Composants tiers : `THIRD_PARTY_NOTICES.md`.
