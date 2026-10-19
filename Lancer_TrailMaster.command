#!/bin/bash
# Double-clique sur ce fichier pour lancer TrailMaster Pro.
# La première fois, ça installe les dépendances nécessaires (un peu plus
# long) ; les fois suivantes, ça se lance directement.

cd "$(dirname "$0")"

echo "Vérification des dépendances..."
pip3 install -r requirements.txt --quiet 2>/dev/null || pip3 install -r requirements.txt --quiet --break-system-packages

echo "Lancement de TrailMaster Pro..."
python3 main.py
