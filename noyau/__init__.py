"""
Noyau de Trail Hub Center — tous les calculs et services, sans aucune
interface graphique.

Règle d'architecture (vérifiée par tests/test_architecture.py) :
  - rien dans noyau/ n'importe PySide6 ni le dossier interface/ ;
  - noyau/ peut lire et écrire la base via data.database ;
  - data.database ne dépend que de noyau.outils.evenements.

Sous-dossiers :
  outils/        dates, couleurs de risque, réseau, événements internes
  traces/        GPX, FIT, segments, secteurs, montées, analyses de trace
  entrainement/  coach, charge, plans, replanification, VMA, VO2max, métriques
  sante/         rythme de vie, mensurations, sommeil
  course/        roadbook, ravitaillement, estimations et tactique de course
  imports/       Strava, Garmin Connect, montre USB, Excel
  ia/            analyses IA (Gemini / Groq)
  services/      petits serveurs locaux (consultation depuis le téléphone)
"""
