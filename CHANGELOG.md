# Historique des versions

## 99
- Vrais installateurs prêts à l'emploi, fabriqués automatiquement par GitHub : `.exe` pour Windows, `.dmg` pour Mac Intel (compatible macOS 12 Monterey) et pour Mac Apple Silicon. Plus besoin d'installer Python.
- Mise à jour en un clic depuis l'application installée : le bon installateur est téléchargé puis ouvert ; les données restent en place.
- Synchronisation Garmin Connect (sorties et santé) ; le code publié ne contient plus aucune donnée personnelle.

## 98
Grande version « fluidité, performance et santé » : 42 nouvelles fonctions.

**Navigation et confort**
- Une seule fenêtre : tous les écrans du menu s'ouvrent dans la fenêtre principale (plus de fenêtres qui s'empilent) ; la touche Échap ramène à l'écran Aujourd'hui. Réversible depuis la palette de commandes (« Fenêtre unique / fenêtres séparées »).
- Nouvel écran « Aujourd'hui » au lancement (style Cockpit) : disponibilité du matin en anneau, séance du jour, charge de la semaine, ACWR, prochaine course, points d'attention, dernière sortie et ressenti à saisir. Chaque bloc est cliquable.
- Tableau de bord restylé (cartes Cockpit), fiche de sortie « carte d'abord » en sombre avec chiffres flottants, nouveau Journal en sombre (fil des sorties, ressentis, photos, pesées, blessures).
- Palette de commandes (Ctrl/Cmd+K), raccourcis clavier (Ctrl+N, Ctrl+F, Ctrl+1…9, Alt+← / → entre les sorties), confirmations discrètes, interrupteur d'affichage Simple / Complet, numéro de version réel et mise à jour en un clic.
- Calculs lourds en arrière-plan avec message « Chargement… » : l'interface ne se fige plus.

**Performance**
- Performance trail : VAM et classement des montées, allure ajustée à la pente, résistance à la fatigue, efficacité de course dans le temps, vitesse par type de terrain, météo et performance, forme pour la distance visée.
- Bilans & objectifs : totaux par semaine / mois / année, comparaison de deux périodes, objectifs annuels avec jauge, simulateur de charge, rapport PDF hebdomadaire ou mensuel, affiche annuelle, page de suivi pour le téléphone.

**Santé et récupération**
- Sommeil : dette de sommeil ; HRV avec bande normale ; FC de repos avec alerte ; monotonie et contrainte ; hausse de charge par semaine ; poids lissé avec objectif ; ressenti en 3 clics ; carte du corps pour les blessures ; acclimatation à la chaleur.

**Entraînement**
- Calendrier du plan par glisser-déposer ; plan qui s'ajuste chaque matin (une fois par jour, sans alléger en boucle) ; répartition facile/dur (80/20) ; volume cible de la semaine ; séances fractionnées envoyées à la montre (fichier FIT, à copier dans GARMIN/NewFiles) ; questions libres au coach IA.

**Souvenirs**
- Album et diaporama par sortie (avec export en PDF), fiche de sortie à partager en image, affiche de l'année.

**Corrections**
- Fiche d'une sortie : le style et le chargement de l'analyse IA étaient mal placés dans le code ; l'analyse déjà générée s'affiche maintenant à l'ouverture, et la génération ne part que sur clic (pour ne pas consommer le quota gratuit).

## 97
- Photos des sorties : nouvelle section « 📷 Photos » dans la fiche d'une sortie (ajout de photos, vignettes, agrandissement avec flèches, légende, suppression, rattachement à une autre sortie).
- Nouvel écran « 📷 Photos » dans le menu (section Entraînement) : galerie de toutes les photos avec filtres (année, type de sortie, sans sortie rattachée, recherche), ajout de photos, import d'un dossier entier.
- Les photos sont réduites à 800 ou 1600 pixels (réglable dans l'écran Photos, 1600 par défaut) et copiées à côté de la base, dans photos/sorties ; les fichiers d'origine ne sont jamais modifiés. Les doublons sont ignorés.
- Rattachement automatique à la bonne sortie grâce à la date de prise de vue (heure exacte, sinon même jour) ; pour les photos enregistrées depuis WhatsApp, qui n'ont plus de date EXIF, la date est lue dans le nom du fichier.
- Sur le tracé de la sortie, les photos sont placées par des pastilles numérotées cliquables : position GPS de la photo, ou position du tracé à l'heure de la photo quand la trace est horodatée.

## 96
- Analyses & Forme : deux nouveaux onglets, « 📈 Forme & fatigue » et « 📉 Évolution ». Forme & fatigue : cartes forme / fatigue / fraîcheur avec son état, courbe forme + fatigue, courbe de fraîcheur en aire, période de 3 mois à 2 ans, blessures de la période. Évolution : une mesure au choix (VO2max, FC, allure, D+, durée, distance), 12 ou 24 mois, avec dernière valeur, meilleure valeur et variation sur la période. Lecture des valeurs au survol.
- Évolution : nouvelle mesure « Distance cumulée (km) ».

## 95
- Tableau de bord : trois nouveaux blocs « Aperçu » en haut — la forme du moment en 6 cartes (forme, fatigue, fraîcheur, VO2max récent et record, dernier poids), la courbe forme / fatigue sur 6 mois (lecture au survol) et les 10 dernières sorties (un clic ouvre la fiche). Ils apparaissent aussi sur un tableau de bord déjà personnalisé, et se masquent depuis Réglages comme les autres cartes.
- VMA & circuits : courbe de VMA avec aire colorée, tableaux sans texte coupé, évolutions en vert (plus rapide) / ambre (plus lent), dates et décimales à la française.
- Poids & fatigue : cartes de résumé, courbes poids et fatigue directement dans la page, tableau « Tous les relevés » complet ; le formulaire d'ajout passe sous le tableau.
- Calendrier : colonnes de largeur égale, durées au format 0h24, distances à virgule.
- Historique des activités : type de sortie en pastille colorée, durées et décimales à la française.

## 94
- Fiche d'une sortie : nouveau bouton « 🏅 Meilleures portions et secteurs » (pour les sorties avec une trace GPS horodatée, fichier FIT/GPX de la montre). Il calcule le plus rapide 400 m, 1 km, 2 km, 5 km, 10 km…, la meilleure allure tenue sur 5, 10, 20, 30 et 60 minutes, un tableau km par km (allure, pente, D+, FC) et la répartition montée / plat / descente.
- Le tracé est coloré selon l'allure locale (vert = rapide, rouge = lent), la portion choisie est surlignée avec son début et sa fin, et une info-bulle donne allure, altitude et FC en chaque point. Les pauses ne sont pas comptées.

## 93
- Alimentation : la liste des fruits et légumes passe de 20 à 111 fiches — petits fruits, fruits d'été et d'hiver, agrumes, fruits exotiques, fruits secs et oléagineux, légumes de printemps, d'été, d'automne et d'hiver, aromates et légumineuses — chacune avec ses calories, sa ou ses saisons et un conseil pour le coureur.
- La liste est triée par ordre alphabétique (accents pris en compte).

## 92
- Tous les graphiques affichent une info-bulle au survol de la souris : le jour (ou la période) et la valeur de chaque mesure avec son unité — VMA (km/h), VO₂max, allure (mm:ss /km), chrono (h:mm:ss), poids, charge, FC, HRV, etc.
- Courbes : repère vertical + points sur chaque courbe ; barres : la barre survolée est mise en évidence.
- Profil d'altitude des traces : altitude, distance et pente locale au survol.
- Mini-courbes des cartes du tableau de bord : date et valeur au survol.

## 91
- Nouvel écran « 🩺 Récupération & tendances » (Analyses & Forme) : lecture du jour (FC de repos, HRV, sommeil, Body Battery comparés à ta valeur habituelle), courbes, efficience, répartition de l'intensité, dérive cardiaque, effet d'entraînement.
- Import « 🩺 santé Garmin » (dossier ou .zip de l'export) : FC de repos, HRV de nuit, sommeil détaillé, Body Battery, stress, SpO₂. Les jours sans montre n'ont pas de mesure.
- Fiche de sortie : bloc « Détail avancé » (effet d'entraînement, charge Garmin, zones de FC, puissance, dynamique de course, température, effort perçu Strava, efficience, dérive cardiaque).
- L'indice de forme tient compte de la FC de repos et du Body Battery quand ils sont récents.

## 90
- Imports Garmin et Strava : récupèrent maintenant aussi le dénivelé négatif, la vitesse et l'allure max, la cadence et la VO₂max (Garmin), ainsi que la vitesse/allure moyennes et la FC max (Strava). Une sortie déjà importée est complétée sans doublon ni écrasement.
- Strava : nouveau bouton « Compléter mes anciennes sorties depuis Strava ».
- Vitesse et allure moyennes calculées automatiquement quand elles manquent (distance / durée).

## 89
- Poids & fatigue : bouton « 📥 Importer un Excel » (.xlsx ou .csv : Date, Poids, État des jambes, RPE, Commentaires). Les lignes sans date précise sont ignorées, aucun doublon en cas de réimport.

## 88
- Tableau de bord : un clic sur une carte ouvre une fenêtre de détail (explication en mots simples, graphique d'évolution, choix de la période) avec un bouton vers la page complète correspondante. Fonctionne sur les cartes de chiffres, les graphiques et les alertes.

## 87
- Première version publique (open source, licence MIT).
- Calendrier des sorties à la semaine, au mois ou à l'année, avec détail au clic.
- Estimation de la VMA à partir des sorties, allures conseillées et évolution par circuit.
- Suivi du poids et de la fatigue (jambes et générale).
- Affichage simplifié, jours de repos automatiques, sorties manuelles.
- Synchronisation Strava (certificats SSL corrigés pour macOS).
- Outil `Retrouver_ma_base.command` : retrouve la base si le logiciel s'ouvre vide.
