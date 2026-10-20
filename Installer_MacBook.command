#!/bin/bash
# ============================================================
# TrailMaster Pro — installation complète sur macOS (MacBook)
# ============================================================
# Double-clique sur ce fichier UNE SEULE FOIS : il construit une vraie
# application "TrailMaster Pro.app" (icône, se lance depuis le Dock/
# Launchpad ou le dossier Applications, sans Terminal ni ligne de
# commande au quotidien).
#
# Ce script doit être exécuté directement sur le Mac où tu veux
# installer l'appli (il ne peut pas être fabriqué à distance : une
# vraie appli Mac doit être construite sur un Mac).
#
# Ta base de données existante (data/trailmaster.db, à côté de ce
# script) est automatiquement reprise au premier lancement de l'appli
# installée — rien à copier à la main.
# ------------------------------------------------------------

set -e
cd "$(dirname "$0")"

echo "=============================================="
echo " TrailMaster Pro — construction de l'application"
echo "=============================================="
echo

if ! command -v python3 &> /dev/null; then
    echo "⚠️  Python 3 n'est pas installé sur ce Mac."
    echo "    Installe-le d'abord depuis https://www.python.org/downloads/macos/"
    echo "    (choisis la version 3.11 ou plus récente), puis relance ce fichier."
    read -p "Appuie sur Entrée pour fermer..."
    exit 1
fi

# Marqueur de version — un numéro basé sur la date/heure de CETTE
# construction, affiché dans le logiciel (bas de l'écran Réglages) :
# ça permet de vérifier en un coup d'œil, après une mise à jour, que
# l'appli installée est bien la toute dernière (et pas une ancienne
# copie relancée par erreur).
BUILD_ID="$(date +%Y%m%d-%H%M)"
echo "$BUILD_ID" > interface/assets/version_build.txt 2>/dev/null || {
    mkdir -p interface/assets
    echo "$BUILD_ID" > interface/assets/version_build.txt
}

echo "0/6 — Fermeture d'une éventuelle instance déjà ouverte..."
osascript -e 'tell application "TrailMaster Pro" to quit' 2>/dev/null || true
pkill -f "TrailMaster Pro" 2>/dev/null || true
sleep 1

echo "1/6 — Préparation d'un environnement Python dédié (.venv)..."
if [ ! -d ".venv" ]; then
    python3 -m venv .venv
fi
source .venv/bin/activate

echo "2/6 — Installation des dépendances (peut prendre quelques minutes la première fois)..."
pip install --upgrade pip --quiet
pip install -r requirements.txt --quiet
pip install pyinstaller --quiet

echo "3/6 — Construction de TrailMaster Pro.app (version $BUILD_ID)..."
rm -rf build dist
pyinstaller \
    --windowed \
    --name "TrailMaster Pro" \
    --add-data "interface/assets:interface/assets" \
    --add-data "ressources:ressources" \
    --add-data "VERSION:." \
    --hidden-import "PySide6.QtWebEngineWidgets" \
    --hidden-import "PySide6.QtWebEngineCore" \
    --hidden-import "PySide6.QtWebChannel" \
    --collect-all "PySide6" \
    --collect-all "garminconnect" \
    --collect-all "curl_cffi" \
    --collect-all "ua_generator" \
    --hidden-import "keyring.backends.macOS" \
    --noconfirm \
    --log-level WARN \
    main.py

deactivate

echo "4/6 — Suppression de toute ancienne copie de l'appli..."
# Une ancienne copie qui traîne ailleurs (Bureau, Téléchargements,
# dossier Applications personnel) peut être relancée par erreur à la
# place de la toute dernière version — on les retire toutes avant de
# poser la nouvelle, pour ne garder qu'un seul exemplaire, au bon
# endroit.
for EMPLACEMENT in \
    "/Applications/TrailMaster Pro.app" \
    "$HOME/Applications/TrailMaster Pro.app" \
    "$HOME/Desktop/TrailMaster Pro.app" \
    "$HOME/Downloads/TrailMaster Pro.app"
do
    if [ -e "$EMPLACEMENT" ]; then
        rm -rf "$EMPLACEMENT"
        echo "    Ancienne copie supprimée : $EMPLACEMENT"
    fi
done

echo "5/6 — Installation dans le dossier Applications..."
cp -R "dist/TrailMaster Pro.app" "/Applications/"
touch "/Applications/TrailMaster Pro.app"
# Force macOS à oublier les informations mises en cache (icône,
# métadonnées) pour cette appli, afin qu'il ne confonde jamais la
# nouvelle version avec une ancienne déjà indexée.
/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister \
    -f "/Applications/TrailMaster Pro.app" 2>/dev/null || true
killall Dock 2>/dev/null || true

echo "6/6 — Reprise de tes données existantes..."
DOSSIER_DONNEES="$HOME/Library/Application Support/TrailMaster Pro"
mkdir -p "$DOSSIER_DONNEES"
if [ -f "data/trailmaster.db" ] && [ ! -f "$DOSSIER_DONNEES/trailmaster.db" ]; then
    cp "data/trailmaster.db" "$DOSSIER_DONNEES/trailmaster.db"
    echo "    Base de données reprise."
fi
if [ -d "data/photos" ] && [ ! -d "$DOSSIER_DONNEES/photos" ]; then
    cp -R "data/photos" "$DOSSIER_DONNEES/photos"
    echo "    Photos des athlètes reprises."
fi

echo
echo "=============================================="
echo " ✅ Installation terminée ! (version $BUILD_ID)"
echo "=============================================="
echo
echo "TrailMaster Pro est maintenant dans ton dossier Applications — et"
echo "c'est désormais la SEULE copie sur cet ordinateur (les anciennes"
echo "copies éventuelles, ailleurs, ont été supprimées automatiquement)."
echo
echo "Pour vérifier que tu as bien la dernière version : ouvre l'appli >"
echo "Réglages > le numéro de version en bas de l'écran doit être"
echo "$BUILD_ID."
echo
echo "⚠️  Au tout premier lancement, macOS affichera un avertissement"
echo "    (l'appli n'est pas signée par un développeur identifié) :"
echo "    fais un clic droit (ou Ctrl-clic) sur l'icône de l'appli >"
echo "    « Ouvrir » > confirme « Ouvrir ». Les fois suivantes, un"
echo "    double-clic normal suffira."
echo
echo "Tes données existantes ont été reprises automatiquement dans :"
echo "    ~/Library/Application Support/TrailMaster Pro/"
echo
echo "(Relancer ce script plus tard, pour une future mise à jour, ne"
echo " touchera plus à tes données : il ne copie que si rien n'existe"
echo " encore à cet emplacement.)"
echo
read -p "Appuie sur Entrée pour fermer cette fenêtre..."
