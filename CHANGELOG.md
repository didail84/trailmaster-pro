# Historique des versions

## Trail Hub Center — étape 3.4 : Matériel obligatoire comparé à ton équipement (bloc 13)
- « Matériel pour une course » est refait en deux onglets : **Pour une course** et **Mon équipement**.
- **Liste du règlement** :
  - tu colles la liste du matériel copiée depuis le règlement ou la page officielle de la course, et elle est **lue automatiquement** : 31 équipements reconnus (téléphone, gobelet, réserve d'eau, couverture de survie, sifflet, frontale et seconde lampe, piles, veste imperméable, collant long, couche chaude, bonnet, gants, réserve alimentaire, bande élastique, trousse de secours…) ;
  - les exigences chiffrées sont relevées : litres d'eau, centilitres du gobelet, colonne d'eau de la veste en mm, lumens, kcal, grammes de la couche chaude ;
  - les quantités sont reconnues (« deux lampes frontales » donne une frontale et une seconde lampe), ainsi que les rubriques « conseillé » et « selon la météo » ;
  - tu corriges chaque ligne si besoin avant d'enregistrer, et la date d'enregistrement est notée ;
  - sans règlement enregistré, le repère standard (distance, D+, nuit, altitude, saison) est reconnu de la même façon.
- **Comparaison ligne par ligne** avec ton équipement :
  - ✅ je l'ai, ⚠️ à vérifier (caractéristique non renseignée, matériel « à surveiller », piles contrôlées il y a plus de 6 mois), ❌ il me manque (absent, pas en nombre suffisant, pas assez d'eau au total, veste pas assez imperméable, sans capuche ou sans coutures étanches) ;
  - une deuxième frontale compte comme lampe de secours ;
  - la réserve alimentaire est composée avec tes **produits de course favoris ou validés** (Nutrition) quand ton équipement n'en a pas.
- **Pour une course**, en plus du tableau :
  - pourcentage du matériel obligatoire prêt et poids du sac obligatoire ;
  - cases « dans le sac » pour la veille de la course ;
  - liste de ce qui manque, copiée dans le presse-papiers ;
  - checklist PDF à imprimer ;
  - lien vers la page de la course ;
  - un double-clic sur une ligne manquante ajoute le matériel à ton équipement.
- **Mon équipement** :
  - ton matériel avec quantité, poids, caractéristique contrôlée, coutures étanches, capuche, date de contrôle des batteries et état ;
  - « Reconnaître d'après les noms » relie en un clic les objets déjà saisis (« Frontale Petzl » devient une lampe frontale) ;
  - c'est la même table que l'écran Matériel (usure des chaussures), donc rien n'est saisi en double.
- Roadbook : la checklist du sac reprend la liste du règlement de la course choisie quand elle est enregistrée.
- Migration n° 5 de la base : caractéristiques de ton matériel et liste du règlement par course. La v108 fonctionne toujours sur la base convertie.
- Page Claude : la rubrique Matériel affiche le matériel obligatoire de tes prochaines courses comparé à ton équipement, avec le même calcul que le logiciel (vérifié ligne par ligne), et la lecture de Claude en tient compte.
- Tests : 300.

## Trail Hub Center — étape 3.3 : Nutrition de course (bloc 12)
- Alimentation : quatre nouveaux onglets en tête, **Produits de course**, **Fait maison**, **Comparatif** et **Tolérances et besoins**. Le journal des repas et les fiches aliments sont inchangés.
- **Produits de course** :
  - tes gels, barres, boissons, pâtes de fruits et produits salés, avec par portion les glucides, l'énergie, le sodium, la caféine et le prix ;
  - 14 produits génériques sans marque donnent des valeurs typiques ;
  - ajout à la main avec l'étiquette, ou par code-barres et par nom depuis **Open Food Facts** (connexion Internet ; les valeurs sont proposées à vérifier avant d'enregistrer) ;
  - produits favoris (★), et détail des points du Nutri-Score de chaque produit.
- **Nutri-Score (lettres A à E)** calculé avec l'algorithme révisé appliqué depuis 2024, avec les tableaux des aliments et des boissons :
  - l'eau est classée A, les édulcorants comptent dans les boissons, et les protéines ne comptent plus quand le score négatif atteint 11 (sauf pour les fromages) ;
  - le Nutri-Score imprimé sur l'emballage, quand il est connu, s'affiche à côté du calcul ;
  - un rappel explique qu'un produit d'effort sucré est normalement classé D ou E.
- **Fait maison** :
  - 8 recettes de départ : gel miel-citron salé, gel 2:1 maltodextrine-fructose, barres avoine-dattes, riz cakes, boules abricot-amande, boisson isotonique, boisson haute dose (90 g par bidon) et boisson de récupération au chocolat ;
  - 34 ingrédients aux valeurs moyennes du type de la table Ciqual, plus un « ingrédient libre » pour recopier ton étiquette ;
  - calcul en direct des glucides, de l'énergie et du sodium par portion, du rapport glucose:fructose, de la concentration d'une boisson en g/L, du Nutri-Score et du coût par portion (prix en €/kg facultatif) ;
  - avertissements : gel trop liquide, boisson trop concentrée, trop de fructose, pas assez de sel, fibres, caféine ;
  - bouton « Viser » : il ajoute ce qu'il faut de maltodextrine, de dextrose, de sucre, de miel ou de fructose pour atteindre le nombre de glucides voulu par portion ;
  - une recette enregistrée rejoint tes produits (marque « Fait maison ») pour être comparée et testée.
- **Comparatif** de 2 à 4 produits : glucides par portion et pour 100 g, sodium, caféine, glucose:fructose, fibres, prix, prix pour 60 g de glucides (environ 1 h d'effort), ta tolérance et le Nutri-Score, plus des phrases de synthèse (le plus de glucides, le moins cher, le plus salé, la caféine avec les repères de l'EFSA, les fibres, ce qui t'a déjà gêné).
- **Tolérances** :
  - pour chaque essai : contexte, durée, quantité, glucides par heure, température, ressenti et symptômes ;
  - verdict par produit : Validé (au moins 2 essais sans souci, dont un long), À confirmer, Avec prudence, À éviter ou Jamais testé ;
  - ton apport de glucides le plus haut bien toléré, et un conseil d'entraînement du ventre (+10 g/h par semaine).
- **Besoins par heure** : glucides, eau et sodium selon la durée, la température, l'intensité et ton poids, avec le menu heure par heure composé de tes produits favoris ou validés (les produits à éviter sont écartés, des pastilles d'électrolytes complètent le sodium).
- Roadbook : les **sacs d'assistance** sont composés avec tes produits favoris ou validés (« 3 × Gel… + 1 × Barres avoine-dattes ») au lieu de gels et barres « standard ».
- Migration n° 4 de la base : produits, essais de tolérance et recettes. La v108 fonctionne toujours sur la base convertie.
- Page Claude : nouvelle rubrique **Nutrition de course**, avec tes produits et leur Nutri-Score, ta tolérance, un comparatif (touche les lignes pour les choisir), le calculateur fait maison en direct et la lecture de Claude. Les calculs sont les mêmes que dans le logiciel (vérifié recette par recette).
- Tests : 290.

## Trail Hub Center — étape 3.2 : Diagnostic et comparaison de parcours (bloc 16)
- Cartes & Traces : nouvel onglet **« 📐 Diagnostic de parcours »**. Tu choisis un parcours de ta bibliothèque ou tu charges un GPX (une course à venir, par exemple). L'écran donne le km-effort (km + D+/100), la catégorie ITRA (XXS à XXL) et le type de terrain (D+ par km). Il affiche aussi **ton temps estimé**, appris sur tes sorties comme dans le Roadbook.
- **Pentes** : une barre de couleur montre la part de la distance dans chaque classe de pente, de la descente raide (< −15 %) au très raide (> 25 %). Sont indiquées aussi la pente la plus raide tenue sur 200 m et sur 1 km, et la descente la plus raide.
- **Répartition du D+** : le D+ et le D− de chaque quart du parcours, et la part du D+ placée dans la seconde moitié, avec le conseil qui va avec (« garde des forces » ou « ne pars pas trop vite »).
- **Montées et descentes principales**, avec le km de départ, la longueur, le dénivelé et la pente moyenne et maximale. Elles sont bornées sur la partie qui monte vraiment : le plat avant le pied de la montée n'est pas compté. Les montées portent une catégorie façon cyclisme (Cat. 4 à HC).
- **Technicité estimée** sur 5. Elle est lue sur le tracé : passages au-dessus de 25 %, descentes raides, sinuosité (lacets) et distance au-dessus de 2 000 m. C'est un repère, pas une cotation du terrain : un GPS ne voit ni les cailloux ni les racines.
- **Comparaison de deux tracés** : profils superposés, tableau mesure par mesure avec l'écart, et phrases de synthèse (par exemple « demande environ 89 % d'effort de plus », « nettement plus raide en montée : bâtons utiles », « dénivelé plus tardif »).
- Page Claude : dans le détail d'une sortie qui a un tracé, nouveau bloc « Difficulté du tracé » (km-effort, catégorie ITRA, terrain, pente maximale sur 1 km, barre des pentes, D+ par quart, plus grosse montée). Le calcul est le même que dans le logiciel.
- Correction : la vérification automatique des mises à jour ne plante plus si la fenêtre principale est fermée avant le délai de 2,5 s.
- Tests : 269.

## Trail Hub Center — étape 3.1 : Stratégie de course (bloc 15)
- Roadbook : nouvelle méthode « Appris sur tes sorties (conseillé) » — le temps de course vient de la régression distance + D+ de tes sorties Trail/Course des 2 dernières années, ajustée à la saison (avertissement si la course est bien plus longue que tes sorties).
- **Trois scénarios** prudent, réaliste et ambitieux : temps total, heure d'arrivée, allure plat et marge la plus faible pour chacun ; dans le tableau, les heures de passage des trois scénarios et la marge sur les barrières en scénario prudent. L'écart entre scénarios vient de la dispersion réelle de tes sorties autour du modèle (bornée à −15 %/−3 % et +4 %/+25 %), sinon −6 % / +10 %. Verdict clair : barrières sûres même en prudent, serrées, ou en danger.
- **Sacs d'assistance** : nouveau type de point « Assistance » (là où tes proches t'attendent). Pour chacun : la fourchette d'heures à laquelle ils doivent être là, et le contenu du sac jusqu'à l'assistance suivante — glucides (en gels et barres), eau et ravitaillements où remplir, frontale si le tronçon passe de nuit en scénario prudent, couche chaude, rechanges au-delà de 3 h.
- **Bracelet d'allures** (PDF A4, 4 bandes de 32 mm à découper) : km, point, heure réaliste en gros, heure prudente, barrière en rouge, D+/D− jusqu'au point suivant.
- Mini-fiche A5 : temps des trois scénarios en tête, page « Sacs d'assistance », repère « A » pour les points d'assistance.
- Tests : 261.

## Trail Hub Center — VMA et VO2max par jour, par semaine ou par mois
- Écran **VMA & circuits** : les courbes de VMA, VO2max et efficacité se lisent désormais jour par jour (30 jours, 90 jours ou 6 mois), semaine par semaine (12, 26 ou 52 semaines, du lundi au dimanche) ou mois par mois (12 ou 24 mois). À chaque point, la VMA du moment garde la même règle : moyenne des 3 meilleures sorties des 90 jours d'avant. Nouveau : des points orange montrent la meilleure sortie de chaque jour, semaine ou mois.
- Écrans **Évolution des performances** (VO2max, FC, allure, D+, distance, durée) : même choix jour, semaine ou mois.
- Correction : sur ces courbes, une période sans sortie comptait la distance, le D+ ou la durée de la période d'avant ; elle compte maintenant 0. Par jour ou par semaine, une moyenne sans mesure laisse un trou au lieu de répéter une valeur.
- Page Claude : carte « VMA et VO2max » dans Forme et charge, avec les boutons Jour / Semaine / Mois (mêmes valeurs que le logiciel, vérifié point par point).
- Tests : 256.

## Trail Hub Center — étape 2.4 (passeport coureur) : fin de l'étape 2
- **Passeport coureur** : un fichier `.json` lisible qui transporte une personne d'un ordinateur à l'autre, ou d'un club à un coureur — sa fiche, ses rôles, son profil sportif, ses résultats de courses, ses index et, au choix, ses courses à venir, ses objectifs et ses coordonnées (non incluses par défaut). Les sorties et traces n'y sont pas : elles voyagent avec la sauvegarde complète.
- Écran Personnes : « Exporter le passeport… » (choix du contenu) et « Importer un passeport coureur… » avec un aperçu avant import. Zéro doublon : chaque élément est reconnu par son identifiant universel, ou par la même course à la même date, le même index à la même date ; une personne inconnue par son identifiant est rapprochée par nom, prénom et date de naissance, et en cas d'homonymes le logiciel demande quelle fiche compléter. Le profil existant n'est complété que dans ses cases vides, sauf si l'on coche « Remplacer ». Tout l'import se fait d'un bloc : en cas d'erreur, rien n'est modifié. Un passeport d'une version plus récente est refusé avec un message clair.
- Migration n° 3 : **index de performance** (ITRA, UTMB Index, Betrail…) par personne et par date, saisis dans l'écran Personnes ; ils voyagent dans le passeport et seront tenus à jour par le Club (étape 4).
- Page Claude : carte « Index de performance » dans Courses et objectifs (avec l'évolution depuis le relevé précédent), index transmis à la lecture de Claude.
- Étape 2 du Master Plan terminée : noyau (personnes, identifiants universels, migrations numérotées, modules activables, passeport) ; la base se convertit sans perte et la v108 fonctionne toujours sur une base convertie.
- Tests : 253.

## Trail Hub Center — étape 2.3 (modules activables) et IMC
- **Modules activables** : Réglages > Modules (en haut des réglages) allume ou éteint chaque module de l'espace Coureur : Récupération, santé et matériel ; Courses et stratégie ; Cartes, traces et photos ; Suivi en direct ; Alimentation ; Météo. Le Noyau et l'Entraînement restent toujours actifs. Un module éteint disparaît aussitôt du menu, de la palette de commandes (Ctrl+K) et des raccourcis Ctrl+1…9 ; rien n'est supprimé.
- Les modules à venir (Fractionné piste, Gestion du club, Kids, Organisation de courses, Trail Live, Photos par dossard, Analyse transversale) sont déjà listés avec l'étape où ils arrivent. Un seul registre (`noyau/modules.py`) décrit tous les modules : menu, palette, Réglages et page Claude le lisent.
- **IMC** : carte « IMC » et carte « Poids pour un IMC normal » dans Poids & récupération (calculés sur la moyenne des 7 derniers jours de pesée et la taille du profil Athlète), carte IMC dans Poids lissé, IMC transmis à l'analyse IA du poids. Classes de l'OMS pour les adultes, présentées comme un repère et non un diagnostic (un sportif musclé est souvent au-dessus).
- Page Claude : IMC dans Aujourd'hui et dans Poids et sommeil (même calcul que le logiciel) ; les rubriques d'un module éteint dans le logiciel ne s'affichent plus.
- Démarrage : si le logiciel ne se lance pas, la raison s'affiche et s'enregistre dans `TrailHubCenter_erreur_demarrage.txt` (dossier personnel).
- Tests : 246.

## Trail Hub Center — étape 2.2 (fiche Personne et rôles) et analyses automatiques
- Migration n° 2 : chaque personne a désormais une fiche unique (table `personnes`, avec identifiant universel), lue par tous les modules, et un ou plusieurs rôles : coureur, licencié, enfant, parent, entraîneur, bénévole, organisateur. Les liens parent/enfant sont enregistrés (pour l'accord parental et l'espace parents à venir).
- Chaque athlète existant reçoit sa fiche et le rôle Coureur à la conversion (copie de sécurité faite avant). Tout athlète créé ensuite, par n'importe quel écran ou import, reçoit sa fiche automatiquement ; nom, sexe et photo restent identiques des deux côtés.
- Nouvel écran **Personnes** (menu Compte, et onglet de Compte) : recherche, filtre par rôle, fiche complète, rôles, liens familiaux, alerte avant de créer un doublon (accents et majuscules ignorés). Le rôle Coureur, qui porte les sorties, ne se retire que depuis l'écran Athlètes.
- Nouveau **Fil d'activité** (menu Entraînement) : les sorties en cartes, comme sur Strava (chiffres, tracé, photos, ressenti), chacune avec son analyse.
- **Analyses automatiques** : chaque sortie reçue (import, Garmin, Strava, montre, saisie) est analysée sans clic, en arrière-plan ; les cartes « Analyse IA » des écrans se lancent toutes seules à l'ouverture et au changement d'athlète, une fois les chiffres chargés, sans rappeler l'IA tant qu'ils ne changent pas ; la fiche d'une sortie sans analyse la fait aussitôt. Avec une clé Gemini ou Groq : analyse de l'IA (au plus 5 sorties par passage, 15 minutes de pause après une erreur de quota) ; sans clé : nouvelle analyse hors ligne par les règles du logiciel, chiffrée, qui sera remplacée par celle de l'IA dès qu'une clé est réglée. Réglage dans Réglages > Analyse IA.
- Page Claude : rubrique Fil d'activité (analyses de la base reprises, Claude écrit celles qui manquent quand une carte arrive à l'écran, analyse hors ligne sinon) et « Lecture de Claude » écrite automatiquement en haut de chaque rubrique.
- Tests : 237.

## Trail Hub Center — page Claude (consultation sans installation)
- Nouveau fichier `page_claude/trail_hub_center.html` : la page Claude du logiciel, en mode réduit. Elle ouvre la sauvegarde `.db` faite par « Sauvegarder maintenant » (Réglages) directement dans le navigateur, en lecture seule : le fichier n'est ni envoyé ni enregistré.
- Rubriques : Aujourd'hui, Sorties (calendrier sur un an, liste, tracé et profil d'altitude), Forme et charge, Poids et sommeil, Courses et objectifs, Blessures et soins, Matériel, Demander à Claude.
- Forme, fatigue, fraîcheur et charge par sortie : même calcul que le logiciel, au jour près (vérifié sur 180 jours).
- Ouvre les bases d'avant (version 0) et d'après (version 1) l'étape 2.1. Sans base ouverte, la page montre des données d'exemple signalées comme telles.

## Trail Hub Center — étape 2.1 (migrations numérotées et identifiants universels)
- La base a désormais un numéro de version (table `schema_version`) et évolue par migrations numérotées (`data/migrations.py`), appliquées une seule fois, dans l'ordre, au démarrage.
- Avant toute conversion d'une base qui contient des données, une copie complète est faite automatiquement dans le dossier `sauvegardes` à côté de la base. Chaque migration est « tout ou rien » : en cas d'erreur, la base reste dans sa version précédente. Une base plus récente que le logiciel n'est jamais touchée.
- Migration n° 1 : chaque donnée (athlètes, sorties, traces, photos, séances, plans, roadbooks, courses, résultats, objectifs, blessures, soins, matériel, segments et passages, poids, sommeil, nutrition, musculation, zones) reçoit un identifiant universel (UUID), indispensable pour échanger avec un club, un serveur ou un autre ordinateur sans doublon. Les nouvelles lignes le reçoivent automatiquement, quel que soit l'écran ou l'import qui les crée.
- Compatibilité : la v108 fonctionne normalement sur une base convertie (vérifié sur tous les écrans de la série 1.4).
- Tests : 221 ; correction d'un plantage de Qt à la fermeture des tests (déjà présent en v108), qui pouvait faire échouer la fabrication des installateurs.

## Trail Hub Center — étape 1.4c (dernières requêtes : plus aucun SQL dans les écrans)
- `noyau/donnees/` s'enrichit de `sante` (poids, jambes, fatigue, sommeil, récupération, santé Garmin), `blessures` (blessures et soins), `courses` (courses à venir, résultats, objectifs) et `listes` (écran de liste commun). 45 requêtes ont quitté 21 écrans.
- Étape 1.4 terminée : 157 requêtes dans les écrans en v108, 0 aujourd'hui. Un test interdit désormais toute requête dans un écran.
- Le nettoyage des cases vides de « Poids & récupération » se fait en une seule opération.
- Tests : 210.

## Trail Hub Center — étape 1.4b (accès aux données : plans, séances, segments, musculation)
- `noyau/donnees/` s'enrichit de `seances`, `plans`, `segments` et `musculation` : 39 requêtes ont quitté 9 écrans (88 → 50 requêtes restantes dans les écrans).
- Un plan d'entraînement (classique ou Programme Ultra) est enregistré avec toutes ses séances en une seule opération : rien n'est écrit à moitié en cas d'erreur.
- Correction : un plan ayant un rapport de fin de bloc, un historique de replanification ou une séance déjà comparée à une sortie ne pouvait pas être supprimé (la base refusait et l'écran affichait une erreur). Sa suppression efface maintenant aussi ces éléments liés.
- Correction : même chose pour une séance seule déjà comparée à une sortie réalisée.
- Tests : 202, dont 9 sur les nouvelles fonctions de données.

## Trail Hub Center — étape 1.4a (accès aux données : sorties, parcours, athlètes)
- Nouveau dossier `noyau/donnees/` : c'est désormais le seul endroit où s'écrivent les requêtes sur les sorties, les parcours GPX et les athlètes. 70 requêtes ont quitté 28 écrans (157 → 88 requêtes restantes dans les écrans).
- La recherche globale est rangée dans le noyau.
- Correction : l'écran « Import » (CSV Strava, JSON Garmin) écrivait dans `data/trailmaster.db` à côté du programme et non dans la vraie base du logiciel ; dans l'application installée, les sorties importées depuis cet écran n'arrivaient donc pas dans la base utilisée.
- Correction : une sortie modifiée dans sa fiche met aussitôt à jour la forme et l'ACWR (le cache du coach était conservé jusqu'à 90 secondes).
- Le suivi en direct enregistre la sortie et sa trace ensemble, ou rien en cas d'erreur.
- Tests : 194 (dont 21 qui comparent chaque fonction de données à la requête d'origine, et un garde-fou qui interdit le retour de requêtes dans les écrans).

## Trail Hub Center — confidentialité
- Retrait du fichier `data/suivi_corporel_initial.py`, qui contenait en clair des relevés personnels de poids et de fatigue (septembre-octobre 2026). Ces relevés avaient déjà été importés une fois pour toutes dans la base de l'utilisateur : rien n'est perdu, l'écran « Poids & récupération » les affiche toujours.

## Trail Hub Center — étape 1.3 (réorganisation interne, aucune nouveauté visible)
- Tous les calculs (coach, plans, replanification, traces GPX/FIT, roadbook, ravitaillement, imports Strava/Garmin, IA…) sont rangés dans un nouveau dossier `noyau/`, indépendant de l'interface : 63 fichiers, en 8 familles (outils, traces, entraînement, santé, course, imports, IA, services).
- Les calculs de « VMA & circuits » et de l'import montre USB sont séparés de leur écran.
- Les anciens chemins (`interface.coach`, `data.metriques`…) continuent de fonctionner à l'identique.
- La base de données ne dépend plus de l'interface : elle annonce ses modifications par un événement interne, que le coach et les écrans écoutent pour vider leurs caches.
- Tests : 173 (dont 65 qui vérifient ces règles d'architecture) ; les installateurs embarquent le dossier `noyau`.

## 108
- Nouveau : **Roadbook course** (Analyses > Performance > 🗺️ Roadbook, et bouton « 🗺️ Roadbook de cette course » dans Courses à venir) pour préparer une course précise, en complément de l'entraînement.
- Import du GPX (ou d'un parcours déjà importé) : profil altimétrique, points nommés du GPX repris, temps de passage estimés selon ton niveau (VO₂max « estimation basse », allure sur le plat, ou temps visé) avec le même calcul de pente que le pacing existant.
- Points de passage éditables : ravitaillements, barrières horaires, repères ; barrière saisie en heure (« 14:30 », passage minuit géré) ; marge en minutes à chaque barrière (vert / orange sous 30 min / rouge si dépassée) et alerte globale ; ravitaillements réguliers en un clic.
- Nutrition par tronçon : glucides, eau, sodium et menu d'exemple entre chaque point, avec les débits du plan de ravitaillement du Coach du jour (aucun nouveau calcul).
- Checklist du sac cochable : matériel obligatoire / conseillé de « Matériel course » (nuit, altitude, saison), nutrition à emporter, éléments perso ; les cases cochées sont conservées quand la liste est recalculée.
- Roadbooks enregistrés dans la base (plusieurs courses possibles), rechargeables et supprimables.
- Mini-fiche A5 en PDF à imprimer / plastifier : profil, points de passage avec heures, barrières et marges, quoi manger entre les points, checklist.
- Tests automatiques ajoutés (GPX synthétique, barrières, nutrition, enregistrement, PDF, écran).

## 107
- Poids & récupération : saisie manuelle des mensurations avec le poids — tour de taille, hanches, poitrine, cuisse, bras et masse grasse (cases facultatives du formulaire sous le tableau, colonnes visibles dans la table). Nouvelles cartes « Tour de taille » (dernière valeur et écart depuis le premier relevé) et « Autres mesures », courbe « Mensurations ».
- L'import Excel / CSV reconnaît les colonnes « Tour de taille (cm) », « hanches », « poitrine », « cuisse », « bras », « masse grasse » (sans doublon, complète un relevé existant).
- L'analyse IA du poids reçoit aussi les mensurations. Base mise à jour automatiquement (colonnes ajoutées), tes données ne sont pas touchées.
- Tests automatiques ajoutés.

## 106
- Analyse IA sur les écrans de résultats : une carte « 🤖 Analyser » en bas du tableau de bord (synthèse du jour), du sommeil / HRV / FC de repos, de la récupération & tendances, du poids (deux écrans), de la VMA et du VO₂max, des meilleurs efforts, de conditions & intensité, des courbes (forme, évolution, charge, efficacité, montées…) et de la préparation aux courses. Format : Lecture, Cause probable, À faire (chiffré).
- L'IA ne lit que des chiffres calculés par le logiciel (dossier par écran) et ne peut pas en inventer ; la VMA et le VO₂max restent signalés « estimation basse ».
- Mémorisation : tant que les chiffres ne changent pas, l'analyse est relue sans nouvel appel (aucun quota consommé) ; « Régénérer » force un nouvel appel.
- Sans clé IA (Réglages > Analyse IA), la carte affiche un résumé local des chiffres clés. Consentement demandé une seule fois avant le premier envoi à Gemini ou Groq.
- Tests automatiques ajoutés (IA simulée, aucun appel réseau).

## 105
- Plan de ravitaillement : une colonne « Exemple concret » propose, heure par heure, une combinaison d'aliments qui atteint les glucides visés (boisson d'effort, gel, compote, barre, banane, pâtes de fruits, dattes, raisins secs, gâteau de riz, sandwich…), l'eau restante et les pastilles d'électrolytes ; du salé est suggéré au-delà de 4 h. Aliments génériques, glucides indicatifs : à vérifier sur l'étiquette.
- Tests automatiques ajoutés.

## 104
- Écran Aujourd'hui relié au Coach du jour : la carte « Séance du jour » affiche la décision du coach (feu vert / prudence / repos) et prévient quand la séance prévue est intense alors que le coach conseille d'alléger. Le matin, ce conseil est aussi écrit dans le commentaire de la séance (sans la modifier : tu décides).
- Nouvel onglet « 🧪 Données » (Analyses & Forme) : contrôle de la qualité des données (sorties sans FC, valeurs aberrantes, doublons probables, trous de santé, note sur 100) et bouton qui recalcule les FC manquantes depuis les traces.
- Nouvel onglet « ⚡ Meilleurs efforts » : meilleure vitesse (à plat équivalent) de 1 min à 1 h, vitesse critique et réserve D′ — estimation basse.
- Nouvel écran « 🌡️ Conditions & intensité » : efficacité selon la température et selon le sommeil de la nuit, et répartition de l'intensité (profil polarisé / pyramidal / zone grise) sur 6 semaines.
- Onglets regroupés : Analyses & Forme passe de 10 à 6 onglets (Forme & récupération, Performance, IA & bilans regroupent les écrans proches, sans les modifier) ; Bilans & objectifs range Rapport PDF, Page téléphone et Affiche sous « Partager ». Les raccourcis du tableau de bord ont été mis à jour.
- Les « & » des titres d'onglets s'affichent correctement.
- Tests automatiques ajoutés.

## 103
- Nouvel onglet « 🎯 Coach du jour » (Analyses & Forme) : décide la séance du jour d'après tes jambes, ta RPE, ta fraîcheur (TSB), ta HRV, ta FC de repos, ton sommeil et une éventuelle blessure. Feu vert / prudence / repos, séance structurée aux allures de ta VMA (qualité, endurance ou récupération), routine de renfort et de mobilité adaptée, explication chiffrée de la décision.
- Envoi de la séance directement sur Garmin Connect, sans câble (elle arrive sur la montre à la prochaine synchronisation). Non testé avec un vrai compte Garmin : à vérifier à la première utilisation. L'export .fit par câble reste disponible dans Séances.
- Prédiction de chrono 5 km, 10 km, semi, marathon et sur un parcours avec D+, à partir du VO₂max estimé, avec la mention « estimation basse ».
- Allure par segment sur un GPX : nouvelle méthode par défaut basée sur le coût énergétique réel de la pente (Minetti), la même que l'analyse des sorties ; l'ancienne règle simple reste au choix.
- Plan de ravitaillement chiffré (glucides, eau, sodium par heure selon durée, intensité, température et poids). Repères généraux à tester à l'entraînement.
- Tests automatiques ajoutés.

## 102
- Écran « VMA & circuits » : nouvelle carte « Évolution des estimations — estimation basse » avec trois courbes sur 24 mois (VMA en km/h, VO₂max en ml/kg/min, indice d'efficacité cardiaque), chacune portant la mention « estimation basse » et la variation en % sur la période. Ces valeurs sont calculées sur des sorties réelles (rarement des efforts maximaux) : elles sous-estiment la valeur vraie, seule la tendance est fiable. Un graphique par grandeur (pas de double axe).
- Tests automatiques ajoutés.

## 101
- Analyses de l'IA plus orientées performance et plus techniques. Avant chaque analyse, TrailMaster calcule en local un dossier de chiffres (rien n'est inventé par l'IA) : allure réelle vs allure ajustée à la pente (GAP), régularité et split, découplage cardiaque Pa:Hr, VAM des montées, durabilité par blocs de 30 min, efficacité (m par battement, indice km-effort/FC), temps par zone de FC avec bornes en bpm, comparaison avec des sorties similaires, fitness/fatigue/fraîcheur (CTL/ATL/TSB) et monotonie au jour J, HRV, FC de repos, sommeil, VMA et VO2max estimés.
- Nouvelle structure d'une analyse de sortie : Lecture technique, Points forts, Limiteurs de performance, Charge/fatigue/récupération (avec niveau de risque), Prescription de la prochaine séance (durée, structure, bpm, allure, D+, critère d'ajustement). Bilans semaine/mois/année : volume en km-effort, répartition d'intensité 80/20, tendance d'efficacité, charge, plan chiffré des 7 à 14 jours.
- Questions au coach et commentaire de replanification : même niveau technique. Réponses plus factuelles (température basse). Les anciennes analyses (format simple) sont régénérées à la prochaine demande.
- Tests automatiques ajoutés.

## 100
- Nouvel écran « Poids & récupération » (onglet Suivi) : fusion de « Poids & fatigue » et « Poids lissé et objectif ». Six cartes (dernier poids du matin, moyenne 7 jours et écart avec la semaine d'avant, perte depuis le poids de départ, reste jusqu'à l'objectif avec estimation, fatigue et jambes au réveil), poids brut + courbe lissée, fatigue au réveil, et la séance de la veille à côté de chaque relevé (tirée des sorties et séances de salle déjà enregistrées).
- Moment du relevé (matin, soir, après séance) : seules les pesées du matin servent aux moyennes et à la courbe lissée. Les anciens relevés reçoivent leur moment automatiquement.
- Poids de départ réglable ; les cases laissées vides ne sont plus enregistrées à 0.
- Import Excel/CSV : colonnes « Moment » et « Fatigue jambes (/10) » reconnues ; réimporter un fichier ne crée toujours aucun doublon (même date + même moment = même relevé, seules les cases vides sont complétées).
- Tests automatiques (`python3 -m pytest tests`).

## 99
- Synchronisation automatique avec Garmin Connect (sans USB) : sorties avec trace GPS, sommeil, VFC, FC de repos, Body Battery, stress, SpO2, pas, disponibilité d'entraînement, VO2max, poids.
- Option de synchro automatique une fois par jour au démarrage.

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
