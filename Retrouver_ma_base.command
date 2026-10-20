#!/bin/bash
# Double-clique sur ce fichier si TrailMaster n'affiche plus tes sorties.
# Ferme TrailMaster Pro avant.
cd "$(dirname "$0")"
python3 -m data.retrouver_base
echo
read -p "Appuie sur Entrée pour fermer."
