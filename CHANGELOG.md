# Historique des versions

## Trail Hub Center — étape 8 (mise en service, Linux, volet commercial, mises à jour par Relais)
- **Mise en service et données** (nouveau menu) :
  - **contrôles de cet ordinateur** : base à jour, dernière sauvegarde, modules, club, prochaine course (plages de dossards, accords pour l'image), lecture des dossards, trousseau, e-mails, Relais ; avec le réseau : serveur du club et Relais joignables ;
  - **23 essais pour de vrai**, étape par étape (« fini quand » du Master Plan), à cocher avec une note : Mac, Windows, Linux, NAS, téléphones, vraie course, Kids, photos, RGPD…
  - **répétition générale** : une course fictive de 40 coureurs (2 épreuves, dossards, points de contrôle, postes) pour s'entraîner au chrono, au PC course et aux téléphones avec les bénévoles, supprimée d'un clic ;
  - **rapport de mise en service** en PDF.
- **Données personnelles (RGPD)** :
  - **registre des traitements** écrit d'après les modules allumés (finalité, personnes, données, base légale, destinataires, durée, sécurité), en PDF ;
  - **durées de conservation** réglables et **nettoyage** de ce qui les dépasse : positions GPS, photos, coordonnées des inscrits des courses passées (les résultats restent) ; anciens adhérents listés pour être revus ;
  - **demandes des personnes** : copie complète de leurs données en JSON, effacement (inscriptions rendues anonymes), délai d'un mois suivi ;
  - **violations de données** : registre, conduite à tenir, rappel des 72 heures pour la CNIL.
- **Licences** : écran avec la licence MIT et celles des composants ; `THIRD_PARTY_NOTICES.md` complété (Pillow, RapidOCR, ONNX Runtime, OpenCV, NumPy…).
- **Linux** :
  - fabrication d'une **AppImage** (toutes distributions), d'un **.deb** (Ubuntu, Debian, Mint, entrée dans le menu) et d'une archive `.tar.gz` ; GitHub les fabrique avec Windows et Mac ;
  - `Installer_Linux.sh` pour installer depuis les sources (commande `trailhub-center` et entrée de menu) ;
  - données dans `~/.local/share/TrailMaster Pro` (respecte `XDG_DATA_HOME`), mots de passe dans le trousseau GNOME ou KDE.
- **Mises à jour par Relais** :
  - **manifeste** `relais.json` publié avec chaque version : numéro, canal (stable ou test), notes, et pour chaque plateforme le fichier avec son empreinte SHA-256 ; **signé** (Ed25519) dès que la clé est créée ;
  - le logiciel cherche d'abord sur le **NAS du club**, puis sur GitHub ; il prend le bon fichier pour l'ordinateur (installateur Windows, version portable, .dmg, AppImage, .deb), **vérifie l'empreinte**, puis installe : l'AppImage se remplace toute seule et l'ancienne est gardée (**retour arrière** dans Réglages) ;
  - réglages dans Réglages > Mises à jour (canal, adresse du Relais, vérifier maintenant) ;
  - le serveur du club sert aussi de Relais (`/relais/`) : `trailhub_serveur.py --relais-miroir V109` y copie une version de GitHub, et les postes du club se mettent à jour sur le réseau local.
- **Base de données version 19** : recette, demandes et violations de données.
- **Page Claude**, rubrique Analyse : carte Mise en service (essais réussis, problèmes notés).
- **Document « Trail Hub Center — volet commercial »** (Claude Docs) : offre possible, guide d'entretien pour fixer les prix, démarches avant de facturer, données personnelles, options de licence.

## Trail Hub Center — étape 7 (photos par dossard)
- **Organisation, nouvel onglet Photos** (13 onglets au total) :
  - **import** d'un dossier, d'un zip ou d'un lien de partage (Dropbox, Google Drive pour un fichier, lien direct) ; une photo importée deux fois n'apparaît qu'une fois ; date de prise de vue et photographe gardés ;
  - **téléphones des bénévoles** : page « 📷 Envoyer mes photos » sur le serveur du club ;
  - **lecture automatique des dossards** sur l'ordinateur, sans Internet (RapidOCR). Seuls les dossards attribués sur la course sont retenus ; une lecture hésitante passe « à vérifier » ;
  - **correction rapide** : galerie, grande photo, dossards à taper, Entrée pour passer à la suivante ; ta correction a toujours le dernier mot ; masquer ou supprimer une photo.
- **Droit à l'image** :
  - case sur chaque inscription, et colonne « droit à l'image » reconnue à l'import des inscrits ;
  - l'accord donné sur la fiche d'un licencié compte aussi ;
  - pour un mineur, il faut en plus l'autorisation parentale ;
  - une photo n'est rendue que si **tous** les coureurs reconnus dessus sont d'accord ;
  - aucune reconnaissance des visages : seul le numéro de dossard sert.
- **Rendre les photos aux coureurs** :
  - **page publique** sur le serveur : dossard + code personnel, chacun ne voit que SES photos ; trop d'essais ratés = pause de 10 minutes ; liens signés qui expirent ;
  - **codes en PDF** à remettre avec le dossard ;
  - **un zip par coureur** ;
  - **e-mail** par la messagerie du club : lien et code, ou photos jointes s'il n'y a pas d'adresse publique ; mot de passe gardé dans le trousseau ;
  - les photos rendues n'ont plus de données EXIF (ni position GPS, ni appareil).
- **Club, Licenciés** : les photos de course du licencié sur son profil (bouton « Photos »).
- **Page Claude**, rubrique Organisation : carte Photos (photos, à vérifier, dossards reconnus, inscrits sans accord). Les photos elles-mêmes restent sur l'ordinateur du club.
- **Base de données version 18** : photos, dossards lus, codes d'accès, envois ; droit à l'image des inscrits.
- **À installer** : `Pillow` et `rapidocr_onnxruntime` (dans requirements.txt). Sur un Mac Intel sous macOS 12, versions limitées dans `packaging/contraintes-mac-intel.txt`.

## Trail Hub Center — étapes 5 et 6, Kids, Analyse, Actualités, plusieurs associations
- **Club : plusieurs associations et leurs sections, sans mélange** :
  - un club FFA et une association de trail (ou plus) dans le même logiciel, chacun avec ses adhésions, groupes, tarifs, reçus numérotés et agenda ;
  - des **sections** dans une association (trail, école d'athlé…) ;
  - une personne inscrite dans deux associations garde **une seule fiche** ;
  - choix de l'association et de la section en haut des écrans du Club (et dans la page Claude).
- **Étape 5, mode serveur** (module « Serveur et comptes », éteint par défaut) :
  - une seule base sur le NAS pour le bureau, les entraîneurs et les bénévoles. Chaque poste du bureau se branche dessus ; le reste du logiciel reste local ;
  - **comptes et rôles** par association ou par événement (président, secrétaire, trésorier, entraîneur, bénévole, chronométreur, parent…). Le serveur vérifie chaque lecture et chaque écriture ;
  - **connexion chiffrée** (HTTPS) : certificat propre au serveur, empreinte vérifiée par chaque poste. Mots de passe protégés (PBKDF2) ;
  - **pages téléphone** : chrono, appel des présences, mon poste de bénévole, résultats ;
  - **journal des accès** gardé un an, et **consentements** : accord parental, droit à l'image, géolocalisation ;
  - **modifications simultanées** : si deux personnes modifient la même fiche en même temps, la seconde est prévenue, rien n'est écrasé ;
  - installation sur le NAS (OpenMediaVault) : `packaging/serveur/LISEZ-MOI.md`.
- **Étape 6, jour de course** (Organisation, onglet Jour de course) :
  - **tableau de commandement du PC course** : carte du parcours, coureurs en course, retards, alertes ;
  - **points de contrôle** créés depuis les ravitaillements, pointage des dossards ;
  - **incidents** signalés depuis un téléphone, même sans réseau (envoi au retour du réseau, sans doublon) ; prise en charge, suivi, clôture ;
  - présence des bénévoles à leur poste ;
  - **Trail Live** : positions importées d'un traceur, et une page publique de suivi pour les proches. La position n'apparaît qu'avec l'accord de géolocalisation.
- **Kids, l'école d'athlé** (Club, onglet Kids) :
  - **carnet de progression** en 4 niveaux (Découverte, Explorateur, Montagnard, Jeune traileur) et 6 domaines (28 compétences validées par l'encadrant) ;
  - **badges** (niveau terminé, domaine maîtrisé, assiduité, première course) ;
  - repères de distance de la FFA, équipement de l'enfant, carnet en PDF ;
  - **espace parents** sur le téléphone ;
  - aucun classement : chaque enfant ne se compare qu'à lui-même.
- **Analyse** (nouveau menu) :
  - **prévu ou réel** : tes courses avec un roadbook et un résultat le même jour. Tu vois le temps prévu, le réel, l'écart et le scénario atteint ;
    - l'écart médian donne un **facteur de correction**, que tu peux appliquer aux temps « appris » de la Stratégie (borné entre 0,85 et 1,2) ;
  - **bilans du club** saison par saison : effectif, nouveaux, fidélisation, femmes et hommes, jeunes, cotisations, séances, présence moyenne, résultats, podiums ;
  - **bilans des événements** : inscrits, partants, finishers, abandons, incidents, bénévoles, solde, et **comparaison des éditions** d'une même course ;
  - PDF. Vraiment utile après une saison de données.
- **Actualités du trail** (nouveau menu, Outils) :
  - **fil d'actualités France et monde** lu dans les flux RSS des sites : u-Trail, Distances+, Esprit Trail, U Run, RunMotion, Trail Run Magazine, Canadian Running, Ian Corless ;
    - seuls le titre, la date, un court extrait et le lien sont gardés ; l'article s'ouvre sur le site ;
    - le **robots.txt** de chaque site est respecté ;
    - tu peux ajouter tes propres flux ;
  - **coureurs connus** français et étrangers (19 au départ), avec un **palmarès vérifié** et ses sources, sans photo ;
    - suis un coureur : les articles qui le citent sont retrouvés tout seuls ;
    - tu peux corriger une fiche ou en ajouter une.
- **Stratégie** : le temps appris affiche la correction appliquée.
- **Correction** : la référence de l'annuaire n'était pas copiée dans l'application installée. Elle l'est maintenant, ainsi que celle des actualités.
- **Base de données version 17** : associations et sections, comptes et rôles, sessions, journal, consentements, points de contrôle, incidents, positions, carnet Kids, actualités et coureurs connus.
- **Page Claude** :
  - rubrique Club : choix de l'association et de la section, et carnet de l'école d'athlé ;
  - rubrique Organisation : nouvelle carte Jour de course (points, passages, incidents) ;
  - nouvelle rubrique **Analyse** ;
  - nouvelle rubrique **Actualités du trail** (articles lus par le logiciel, coureurs connus).

## Trail Hub Center — étape 4.6 (logistique d'une course : démarches, bénévoles, ravitaillements, matériel, partenaires et budget)
- **Fenêtre Organisation, cinq nouveaux onglets** (onze au total) :
  - **Démarches et rétroplanning** :
    - « Ta course » : voie publique, communes et départements, chronométrage, calendrier FFA, coureurs et public attendus, carrefours, Natura 2000, forêt ONF, terrains privés, Parc naturel régional ou national, site protégé, nuit, buvette, restauration, musique, tombola, prix, subventions, gobelets ;
    - le logiciel en tire **la liste des démarches avec leur date limite** calculée depuis la date de la course, de J-180 à J+30. On y trouve notamment :
      - déclaration au maire ou au préfet (Cerfa 15824, 2 mois avant, 3 mois sur plusieurs départements), ou Cerfa 15825 pour une randonnée sans classement ;
      - avis et calendrier FFA, assurance responsabilité civile, poste de secours et médecin, plan de secours, SDIS et gendarmerie ;
      - arrêtés de circulation et liste des signaleurs ;
      - Natura 2000, ONF, propriétaires, Parc, site protégé ;
      - **Vaucluse et départements du Sud-Est** : accès aux massifs réglementé de juin à septembre (parcours de repli, carte du danger la veille) ; Parcs du Mont-Ventoux et du Luberon nommés ;
      - buvette (10 autorisations par an pour une association sportive), Sacem, tombola (Cerfa 11823), subventions (Cerfa 12156) ;
      - jalons des bénévoles, de la logistique et de l'après-course ;
    - statut de chaque démarche (à faire, en cours, envoyée, accordée, refusée, sans objet), pièces à fournir, conseil, alertes de retard ; si le contexte change, les démarches se mettent à jour sans perdre le suivi ;
    - **secours du public** dimensionnés avec la grille nationale (RIS, PAPS, DPS) ; les secours des coureurs restent à analyser avec l'association agréée ;
    - **rétroplanning en PDF**, **échéances en .ics** pour l'agenda, **courriers types** (mairie, propriétaire avec coupon d'accord, ONF, Parc, SDIS, entreprise, collectivité, remerciements) à copier ou mettre en PDF.
  - **Bénévoles** :
    - adhérents du club en un clic (ils reçoivent le rôle Bénévole), **import** d'un formulaire HelloAsso, Google Forms ou CSV sans doublon, saisie à la main ;
    - **postes types créés tout seuls** (retrait des dossards, départ et arrivée, chrono, PC course, ravitaillements, serre-files, balisage la veille, débalisage, signaleurs, parking, buvette) avec horaires et besoins ;
    - affectations ; le logiciel signale les postes à compléter, les **conflits d'horaires** et les **signaleurs mineurs ou sans permis** ;
    - **planning PDF**, **convocations PDF** (une page par bénévole), **liste des signaleurs PDF** pour la préfecture (numéro de permis à remplir à la main), e-mails à copier.
  - **Ravitaillements** : kilomètre, type (eau, complet, chaud, arrivée), épreuves, ouverture, barrière horaire, accès. **Quantités calculées** d'après les coureurs attendus (plus d'eau l'été, 15 % de marge, gobelet personnel par défaut). **Liste de courses** en PDF et en CSV.
  - **Matériel** : **liste type** avec quantités suggérées (arche, barrières, rubalise, flèches, gilets, talkies, trousses, barnums, jerricans, toilettes, chrono…), qui prête ou loue, où ça va, statut jusqu'au retour, coût, **check-list PDF**.
  - **Partenaires et budget** :
    - mécénat (don, en argent ou en nature), parrainage, subventions, partenaires médias ; contacts, relances, contreparties ;
    - **reçu de don numéroté en PDF**, avec la réduction d'impôt du donateur (60 % pour une entreprise, 66 % pour un particulier) et une alerte si les contreparties dépassent 25 % du don ;
    - **budget prévisionnel et réalisé** : les inscriptions (coureurs attendus × tarif moyen ; encaissé en réalisé) et les accords des partenaires sont repris tout seuls ; dépenses fixes ou par coureur ;
    - **seuil de rentabilité** ; budget en PDF.
- **Tableau de bord** : nouveau cadre Logistique (démarches en retard et prochaines, bénévoles, matériel, partenaires, budget, secours).
- **Base de données version 12** : contexte de la course, démarches, bénévoles, postes et affectations, ravitaillements, matériel, partenaires, budget.
- **Page Claude**, rubrique Organisation :
  - nouvelles cartes : démarches faites et en retard, places de bénévoles pourvues, partenaires, solde prévu ;
  - **démarches à suivre** et **postes à compléter** ;
  - une **lecture de Claude** qui donne les 3 actions prioritaires de la semaine. Claude ne reçoit aucun nom de bénévole ni de partenaire.
- Les règles sont des rappels à jour de novembre 2026 : vérifie toujours auprès de la mairie, de la préfecture et du comité FFA.

## Trail Hub Center — étapes 4.3 (profils des licenciés, entraîneurs, séances partagées) et 4.5 (chrono et classements)
- **Club, trois nouveaux onglets** (la fenêtre Club en compte maintenant 11) :
  - **Licenciés** : fiche de chaque licencié avec catégorie, groupes, **bilan de la saison** (courses, km, D+, podiums), **records** sur route (5 km, 10 km, semi, marathon…) et en trail (par km-effort), **index ITRA, UTMB et Betrail** saisis à la main, liste des résultats.
    - On ajoute un résultat à la main, ou on **importe le classement d'une course** (colonnes reconnues : clt, nom, prénom, temps, catégorie, clt cat., club). Les adhérents sont retrouvés par nom et prénom (et année de naissance si deux personnes portent le même nom) ; ceux qui ne sont pas reconnus sont listés.
    - **Pas de doublon** : une même course du même licencié est mise à jour, jamais ajoutée deux fois. Si le licencié a un profil coureur, le résultat va aussi dans ses « Résultats de courses ».
    - Résultats du club des 90 derniers jours.
  - **Séances partagées** : bibliothèque de séances du club (contenu, objectif, public, durée, fractionné de la bibliothèque), **programmée** dans l'agenda d'un groupe (ou ajoutée à une séance déjà prévue), puis **envoyée aux coureurs** qui ont un profil : elle arrive dans leurs séances structurées avec les allures calculées sur **leur** VMA, une seule fois.
  - **Entraîneurs** : désigner un entraîneur, ses **diplômes** (date de validité, alerte 90 jours avant l'échéance), ses groupes et ses prochaines séances.
- **Organisation, deux nouveaux onglets** (6 au total) :
  - **Chrono** : top départ de chaque épreuve (ou heure saisie), arrivées au **dossard + Entrée** avec l'heure de l'ordinateur ou une heure saisie, horloge, retour immédiat (nom, épreuve, temps). Un **double top** de moins de 5 secondes est ignoré tout seul, un second passage est gardé de côté ; dossards inconnus et passages sans dossard signalés. Correction et annulation d'un passage, **import du fichier du chronométreur** (heures de passage ou temps de course, sans doublon).
  - **Classements** : scratch, par sexe, par catégorie FFA (M1H, SEF…), écart, vitesse, allure ; ex æquo au même rang ; abandons, disqualifiés et non-partants à la fin. Statuts et temps corrigés, **export CSV**, **PDF**, podiums à copier, et **publication sur les profils des licenciés** sans doublon (publier à nouveau met à jour).
- **Base de données version 11** : résultats des licenciés, diplômes, séances modèles, passages du chrono ; départ réel des épreuves, statut et temps corrigé des inscriptions.
- **Page Claude** : rubrique Club, carte **Résultats récents des licenciés** (12 mois) ; rubrique Organisation, **classement et podiums** de chaque épreuve, calculés comme dans le logiciel. Claude ne reçoit que des chiffres, aucun nom.

## Trail Hub Center — étape 4.4 (organisation d'un événement) et Calendrier des courses
- **Nouveau module « Calendrier des courses »** (espace Coureur, allumé par défaut, menu Analyse). Il couvre les compétitions de stade, hors stade (route), cross, trail (découverte, court, long, ultra), course en montagne, kilomètre vertical, marche nordique et relais, en Provence-Alpes-Côte d'Azur, Occitanie et Auvergne-Rhône-Alpes.
  - **Courses** : filtres (période, région, département, discipline, niveau, favorites), fiche de la course avec épreuves et km-effort.
  - **Envois** : vers **« Courses à venir »** (en choisissant l'épreuve) ou vers **l'agenda du club**. Export .ics.
  - **Sources** :
    - les **flux .ics** donnés par l'utilisateur (organisateurs, comités, ligues, Google Agenda) sont **relus tout seuls** à l'ouverture, toutes les 12 heures, en tâche de fond ;
    - les **calendriers en ligne** (FFA, Betrail, Sas Départ, GoTrail, Sport-Nature, Trace de Trail) s'ouvrent dans le navigateur avec la discipline et la saison choisies. On **colle** le tableau des courses et le logiciel reconnaît les colonnes ;
    - on peut aussi **importer** un fichier .ics ou .csv.
  - **Fusion sans doublon** : même date, noms proches, même département. Une course corrigée par toi n'est plus modifiée par ses sources.
  - Le logiciel ne lit pas tout seul les sites qui interdisent la lecture automatique (FFA, Betrail) : il les ouvre dans ton navigateur.
- **Module « Organisation de courses »** (espace Organisation, à allumer dans Réglages > Modules). Il ouvre la fenêtre **🏁 Organisation**, en quatre onglets :
  - **Événement et épreuves** : date, lieu, ouverture et clôture des inscriptions, tarif tardif, validité du Pass Prévention Santé, autorisation parentale. Chaque épreuve a sa distance, son D+, son km-effort, son horaire, son quota, ses tarifs (normal, licencié FFA, tardif), sa plage de dossards et un âge minimum. On publie l'événement dans le calendrier des courses.
  - **Inscriptions** : saisie, **import Njuko, HelloAsso ou CSV** (l'épreuve est reconnue par son nom ou sa distance, les commandes remboursées sont écartées, sans doublon), **inscription des adhérents du club** avec leur licence, liste d'attente quand le quota est atteint, paiements, validation des dossiers complets, export, e-mails des dossiers incomplets.
  - **Contrôle des dossiers** d'après la réglementation FFA des manifestations running 2025-2026 :
    - distances maximales par catégorie, sur route et en trail (km-effort, plus de 950 m de D+ réservé aux juniors et plus) ;
    - licences acceptées (Athlé Compétition, Running, Entreprise) ;
    - Pass Prévention Santé pour les majeurs, fait au plus 3 mois avant la course ;
    - mineurs : questionnaire de santé avec attestation parentale, ou certificat de moins de six mois, et autorisation parentale ;
    - paiement et téléphone à prévenir.

    Chaque contrôle s'affiche en manque ou en avertissement : l'organisateur garde la décision.
  - **Dossards** : attribution aux inscriptions validées (ordre alphabétique ou d'inscription), contrôle des plages qui se chevauchent, retrait des dossards le jour J, **liste de départ CSV** et **feuille de retrait PDF**.
  - **Tableau de bord** : inscrits, validés, dossiers incomplets, encaissé et reste, dossards ; par épreuve (places restantes), par catégorie et par club.
- **Base de données version 10** : sources et courses du calendrier, événements, épreuves, inscriptions.
- **Page Claude** : rubrique **Calendrier des courses**, avec une lecture de Claude qui propose 2 ou 3 courses adaptées à ta forme et à tes objectifs. Rubrique **Organisation** : remplissage des épreuves, dossiers à traiter, encaissé, dossards.

## Trail Hub Center — Annuaire trail (nouveau module)
- **Nouveau module « Annuaire trail »** (espace Coureur, allumé par défaut). Il ouvre la fenêtre **📒 Annuaire trail** (menu Outils), en trois onglets :
  - **Clubs et écoles** : clubs d'athlétisme, de running et de trail, sections trail, écoles de trail, organisateurs de courses ;
  - **Magasins** : spécialistes running et trail, magasins outdoor, grandes surfaces de sport avec un rayon running ;
  - **Marques** : chaussures, textile, sacs, bâtons, frontales, montres, nutrition, accessoires. L'onglet montre aussi combien d'objets de ton matériel sont de chaque marque.
- **Base de référence livrée**, région PACA (04, 05, 06, 13, 83, 84) :
  - 78 clubs, écoles, sections et organisateurs ;
  - 56 magasins ;
  - 111 marques.

  Cette première base est **incomplète** : elle vient d'annuaires publics (PagesJaunes, sites i-Run, Terre de Running, running-var.fr, réseau École de Trail). Chaque fiche indique sa source. Les clubs sont indiqués **par commune seulement**, car l'adresse d'une association est souvent le domicile d'un bénévole.
- **Actions sur les fiches** :
  - recherche et filtres (département, type, catégorie, favoris) ;
  - ajouter, corriger, mettre en favori, noter, marquer « vérifiée aujourd'hui » ;
  - ouvrir le site, ou une recherche sur le web s'il n'y a pas de site ;
  - importer un tableau CSV (sans doublon, en complétant les cases vides) et exporter.
- **Mises à jour de la base de référence** : une fiche que tu as corrigée n'est jamais écrasée. Une fiche retirée reste masquée. Tes notes et favoris sont gardés.
- **Matériel** : chaque objet a maintenant une **marque** et un **magasin d'achat**. Ils sont proposés pendant la saisie, et la marque suit le type d'objet (frontales pour une lampe, sacs pour un sac…). Même chose dans l'écran Matériel (usure) et pour la marque des produits de nutrition.
- **Base de données version 9** : table annuaire ; marque et magasin du matériel.
- **Page Claude** : nouvelle rubrique **Annuaire trail**, avec recherche et filtres. Elle affiche la base livrée, ou celle de ta base avec tes ajouts, favoris et notes.

## Trail Hub Center — étape 4.2 : Agenda du club et appel des présences (blocs 17 à 19)
- Deux nouveaux onglets dans la fenêtre **🏟️ Club** :
  - **📅 Agenda**
  - **✅ Présences**
- **Agenda**
  - **Séances** une par une ou **en série chaque semaine** : groupe, jour, horaire, lieu, entraîneur.
  - **Dates retirées toutes seules** : les jours fériés sont calculés (Pâques, Ascension, Pentecôte…). Les vacances scolaires officielles 2025-2026 et 2026-2027 (zones A, B, C) et le pont de l'Ascension sont retirés au choix.
  - **Aperçu** du nombre de séances et des dates sautées avant de créer la série.
  - **Modifier une série** refait ses séances à venir sans appel. Les séances passées ou déjà appelées sont gardées.
  - Sur une séance : **annuler** (avec motif, la séance reste barrée), rétablir, dupliquer, supprimer.
  - Périodes affichées : semaine, 4 semaines, mois, saison, ou les séances passées dont l'appel reste à faire.
  - **Feuille d'appel PDF** à imprimer : cases P, R, E, A, téléphone de la personne à prévenir, lignes libres.
  - **Export de l'agenda (.ics)** : en ouvrant le fichier, les adhérents ajoutent les séances à leur téléphone ou à Google Agenda. Les séances annulées y apparaissent comme annulées.
- **Présences**
  - **L'appel** : par défaut, la séance du jour. Chaque personne est notée présente, en retard, excusée ou absente, avec une remarque.
  - Boutons « Tout le monde présent » et « Les non pointés : absents ».
  - **Ajout d'une personne venue en plus**, notée comme invitée.
  - La colonne Urgence affiche le téléphone de la personne à prévenir. Il est signalé quand il manque pour un mineur.
  - **Assiduité** sur 30 jours, 3 mois ou la saison :
    - par groupe : présents en moyenne, taux ;
    - par personne : taux, absences de suite, dernière présence.
  - **Export tableur** des présences : une colonne par séance.
  - **Alertes** : un adhérent absent 3 fois de suite sans excuse est signalé, ainsi que les séances passées sans appel. Elles apparaissent aussi dans le « À faire » du tableau de bord.
- **Tableau de bord** du club : nouvelle liste des prochaines séances.
- **Onglet Le club** : choix de la zone de vacances scolaires selon l'académie (zone B par défaut).
- **Reçus PDF** : le texte s'imprimait trop petit, il est maintenant à la bonne taille.
- **Base de données version 8** : séries, séances, présences ; zone de vacances du club.
- **Page Claude**, rubrique Club : agenda des 4 prochaines semaines avec les prochaines vacances, présences des 60 derniers jours par groupe et par adhérent, décrochages et appels oubliés. Les calculs sont les mêmes que dans le logiciel. La lecture de Claude reçoit les chiffres des présences, toujours sans aucun nom.

## Trail Hub Center — étape 4.1 : Espace Club, adhérents et licences FFA (blocs 17 à 19)
- Nouveau module **Gestion du club** (éteint par défaut : Réglages > Modules). Il ajoute la fenêtre **🏟️ Club** (menu Club), en six onglets.
- **📊 Tableau de bord** de la saison : adhérents, taux de renouvellement, dossiers incomplets, cotisations encaissées et restantes, jeunes. Liste « À faire », répartition par catégorie FFA (années de naissance de la saison) et par licence. Liste des adhérents pas encore renouvelés, à renouveler en un clic.
- **👥 Adhérents** : recherche et filtres (groupe, dossiers incomplets, cotisation à payer, moins de 18 ans, annulées). Chaque adhérent a une fiche complète :
  - la personne, avec la personne à prévenir ;
  - sa licence et son numéro FFA ;
  - sa pièce de santé, l'autorisation parentale et le droit à l'image ;
  - son tarif, sa cotisation et son paiement ;
  - ses groupes.
  Chaque adhérent est une fiche Personne (rôle licencié) : pas de double saisie avec les coureurs, parents ou bénévoles. Un doublon possible est signalé à la création.
  Depuis la liste : paiement en plusieurs fois, **reçu PDF** numéroté (attribué tout seul quand la cotisation est soldée), export tableur, copie des e-mails.
- **Catégories FFA** calculées pour chaque saison (1er septembre au 31 août), de Baby athlé à Masters 10. Un type de licence qui ne correspond pas à l'âge est signalé.
- **🧑‍🤝‍🧑 Groupes** d'entraînement, avec leur entraîneur et leurs membres.
- **💶 Cotisations** : les tarifs de la saison, liés ou non à un type de licence, se reprennent d'une saison à l'autre. L'onglet donne aussi le reste à encaisser, un message de relance à copier et les paiements par mode.
- **📥 Import** d'un export HelloAsso, de la liste du SI-FFA ou de tout tableau (CSV ou Excel), avec un aperçu avant d'importer. Les colonnes sont reconnues toutes seules. Les commandes remboursées ou annulées sont écartées. Les personnes déjà connues (même n° de licence, ou même nom, prénom et naissance) sont complétées sans doublon.
- **⚙️ Le club** : identité, affiliation FFA et président(e), repris sur les reçus.
- Base de données version 7 : clubs, groupes, adhésions par saison, tarifs ; contact d'urgence sur la fiche Personne.
- Le module **Fractionné** est maintenant un module à part entière (activable).
- Page Claude : nouvelle rubrique **Club**, visible sur l'exemple et quand le module est allumé dans la base. Elle reprend les chiffres de la saison, les catégories, les groupes, les adhérents et leur dossier, et les non-renouvelés, avec les mêmes règles que le logiciel. La lecture de Claude ne reçoit que des chiffres, aucun nom d'adhérent.

## Trail Hub Center — étape 3.5 : Fractionné court ou long, à plat ou en côte (bloc 14)
- Nouvelle fenêtre **⏱️ Fractionné** (menu Entraînement), en quatre onglets.
- **📚 Bibliothèque** : 20 séances types, filtrables court ou long et à plat ou en côte.
  - Court à plat : 30/30, 15/15, 10 × 200 m, 8 × 300 m, 10 × 400 m, pyramide.
  - Long à plat : 6 × 1000 m, 5 × 1000 m vite, 4 × 2000 m, 3 × 3000 m au seuil, 3 × 10 min, 2 × 15 min.
  - Court en côte : 10 × 30 s, 12 × 100 m en côte raide, 8 × 45 s, 2 × 6 × 1 min.
  - Long en côte : 5 × 3 min, 4 × 5 min, 3 × 8 min, 4 × 1000 m.
  - Cibles calculées depuis ta VMA (celle de ta fiche, sinon celle estimée sur tes sorties, modifiable) : temps de chaque répétition, allure, distance attendue sur une répétition en durée.
  - En côte, la vitesse attendue et le D+ tiennent compte de la pente (coût énergétique de Minetti).
  - Tableau des temps au 100, 200, 300, 400 et 1000 m, de 80 à 110 % de VMA.
  - Chaque séance peut être envoyée à la montre (fichier FIT, allure cible à plat), ajoutée aux séances prévues ou copiée en séance perso (blocs, séries, récupération, pente).
- **⏲ Minuteur** : la séance déroulée phase par phase, en gros chiffres, avec la couleur de la phase.
  - Un bip long à chaque changement, trois bips courts avant la fin de chaque phase.
  - Sur piste, le bouton « Fin de répétition » relève ton temps en passant la ligne ; les temps relevés vont directement à la saisie.
- **Dans le suivi** (ta demande) : le détail d'une sortie a une section « Fractionnés de cette séance ».
  - Un **menu déroulant** (filtrable court ou long, à plat ou en côte) choisit le fractionné fait ; on peut en ajouter plusieurs pour une même sortie.
  - La saisie d'une nouvelle sortie a aussi son menu « Fractionné fait ».
- **Saisie des temps** :
  - temps des répétitions en distance (1:32 ou 92), distance des répétitions en durée, D+ en côte, FC ;
  - ou bien « Retrouver les répétitions dans la trace » : le logiciel cherche dans la trace GPS de la sortie les passages les plus rapides de la bonne longueur (en pente corrigée en côte, pour ne pas prendre les descentes). Les répétitions identiques restent dans le bon ordre, par exemple les deux 400 m d'une pyramide.
- **Analyse** : % de VMA tenu (corrigé de la pente en côte), écart à la cible, régularité, baisse en fin de séance, verdict (dans la cible, plus vite, plus lent), conseils, et VMA suggérée quand les répétitions courtes sont tenues plus vite que prévu.
- **📝 Mes fractionnés** et **📈 Progression** : historique avec le détail répétition par répétition, et l'évolution de la vitesse moyenne de chaque séance refaite.
- Migration n° 6 de la base : séances perso et fractionnés faits. Un fractionné fait garde une copie de sa séance (si tu supprimes ta séance perso, rien n'est perdu) et survit à la suppression de la sortie. La v108 fonctionne toujours sur la base convertie.
- Page Claude : nouvelle rubrique **Fractionné** (séances types avec les cibles selon ta VMA, temps de passage, tes fractionnés avec leur analyse, progression, lecture de Claude), et les fractionnés d'une sortie dans son détail. Les calculs sont les mêmes que dans le logiciel (vérifié séance par séance).
- Étape 3 du Master Plan construite (3.1 à 3.5), reste à la valider sur une vraie course. Tests : 309.

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
