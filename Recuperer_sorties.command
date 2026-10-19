#!/bin/bash
# Double-clique sur ce fichier pour récupérer les sorties disparues.
# Ferme TrailMaster Pro avant.
cd "$(dirname "$0")"
python3 -m data.restaurer_sorties
echo
read -p "Appuie sur Entrée pour fermer."
