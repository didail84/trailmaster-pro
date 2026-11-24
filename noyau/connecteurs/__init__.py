"""
Connecteurs Claude : le pont entre Trail Hub Center et les connecteurs de Claude
(Strava, Garmin via Running Workout, AllTrails, TrailSync, Google Agenda, Gmail,
Spotify, Google Drive).

Le logiciel de bureau ne parle pas directement aux connecteurs : c'est Claude
qui les interroge (tâche programmée chaque matin, ou la page Claude), puis
dépose un « paquet » JSON dans un dossier partagé (Google Drive). Le logiciel
lit ce dossier, importe le paquet sans doublon, et y écrit ses « demandes »
(séance à envoyer sur la montre, événement d'agenda, playlist…) que Claude
exécute au passage suivant.

  - regles.py  : format du paquet et des demandes, conversions, calculs purs ;
  - importer.py : écriture d'un paquet dans la base ;
  - pont.py    : le dossier partagé (lecture des paquets, écriture des demandes).
"""
