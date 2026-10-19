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

Il faut **Python 3.11 ou plus récent** ([python.org](https://www.python.org/downloads/)).
Sous Windows, coche « Add python.exe to PATH » pendant l'installation de Python.

1. Télécharge la dernière version dans l'onglet **Releases** de ce dépôt, ou clique sur *Code → Download ZIP*.
2. Dézippe le dossier où tu veux.
3. Lance l'installateur, **une seule fois** :
   - **Mac** : double-clique sur `Installer_MacBook.command` (clic droit → Ouvrir la première fois).
   - **Windows** : double-clique sur `Installer_Windows.bat`.
4. Le logiciel est ensuite disponible comme une application normale (Dock/Launchpad sur Mac, menu Démarrer sous Windows).

Pour essayer sans installer : `Lancer_TrailMaster.command` (Mac), ou en ligne de commande :

```bash
pip install -r requirements.txt
python3 main.py
```

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

Au démarrage, le logiciel regarde s'il existe une version plus récente dans les *Releases* de ce dépôt et te propose de la télécharger. Pour installer : dézippe, puis relance l'installateur. Ta base n'est pas touchée.

## Pour les développeurs

- Code : `interface/` (écrans PySide6), `data/` (base SQLite et références).
- Chaque écran de liste repose sur `interface/ecran_liste.py`.
- Lancer en test : `python3 main.py`. Vérifier la syntaxe : `python3 -m compileall interface data`.
- Voir `CONTRIBUTING.md`. Les nouveautés sont notées dans `CHANGELOG.md`.

## Publier une version (mainteneur)

1. Augmente le nombre dans `VERSION` et ajoute une ligne dans `CHANGELOG.md`.
2. Sur GitHub : *Releases → Draft a new release*, étiquette `V88` (le même nombre que `VERSION`).
3. Joins le zip du projet (sans ta base !) ou laisse GitHub générer l'archive du code source.

## Licence

MIT, voir `LICENSE`. Composants tiers : `THIRD_PARTY_NOTICES.md`.
