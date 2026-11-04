"""
Accès aux données de Trail Hub Center — le seul endroit où s'écrivent
les requêtes SQL.

Les écrans n'écrivent plus de SQL : ils appellent ces fonctions. Quand
la structure de la base évoluera (identifiants universels, migrations
numérotées, mode serveur), seul ce dossier changera.

  base          lire / écrire, transaction partagée par plusieurs requêtes
  activites     sorties
  parcours      traces GPX et parcours dessinés
  athletes      profils des coureurs
  seances       séances structurées
  plans         plans d'entraînement et rapports de bloc
  segments      segments précis et passages
  musculation   renforcement, cardio machine et mobilité
  sante         poids, jambes, fatigue, sommeil, récupération, santé Garmin
  blessures     blessures et soins
  courses       courses à venir, résultats, objectifs
  listes        accès générique de l'écran de liste commun
  recherche     recherche globale (toutes les tables)

Chaque fonction peut recevoir `cur=` (un curseur déjà ouvert) pour
s'insérer dans une opération en cours — un import en lot par exemple —
sans valider à sa place.
"""
