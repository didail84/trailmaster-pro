#!/bin/bash
# ============================================================
# Trail Hub Center — installation sous Linux, depuis les sources
# ============================================================
# Plus simple encore : télécharge le fichier .AppImage de la dernière
# version sur GitHub, rends-le exécutable (clic droit > Propriétés >
# Autoriser l'exécution) et double-clique dessus. Ou installe le .deb
# (Ubuntu, Debian, Mint) d'un double-clic.
#
# Ce script-ci installe depuis les sources : un environnement Python à
# part (.venv), une commande « trailhub-center » et une entrée dans le
# menu des applications. Tes données restent dans ~/.local/share/TrailMaster Pro.
# ------------------------------------------------------------
set -e
cd "$(dirname "$0")"
ICI="$(pwd)"

echo "=============================================="
echo " Trail Hub Center — installation Linux"
echo "=============================================="

if ! command -v python3 >/dev/null 2>&1; then
    echo "⚠️  Python 3 n'est pas installé. Ubuntu / Debian / Mint : sudo apt install python3 python3-venv"
    echo "    Fedora : sudo dnf install python3     Arch : sudo pacman -S python"
    exit 1
fi
if ! python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)'; then
    echo "⚠️  Il faut Python 3.10 ou plus récent (tu as $(python3 --version))."
    exit 1
fi
if ! python3 -c 'import venv, ensurepip' >/dev/null 2>&1; then
    echo "⚠️  Le module venv manque. Ubuntu / Debian / Mint : sudo apt install python3-venv"
    exit 1
fi

if command -v apt-get >/dev/null 2>&1 && ! ldconfig -p 2>/dev/null | grep -q libxcb-cursor; then
    echo "ℹ️  Qt a besoin de quelques bibliothèques ; si l'appli ne s'ouvre pas, lance :"
    echo "    sudo apt install libxcb-cursor0 libxkbcommon-x11-0 libegl1"
fi

echo "1/3 — Environnement Python dédié (.venv)…"
[ -d .venv ] || python3 -m venv .venv
. .venv/bin/activate
echo "2/3 — Dépendances (quelques minutes la première fois)…"
python -m pip install --upgrade pip --quiet
pip install -r requirements.txt --quiet

echo "3/3 — Commande et entrée de menu…"
mkdir -p "$HOME/.local/bin" "$HOME/.local/share/applications" "$HOME/.local/share/icons/hicolor/256x256/apps"
cat > "$HOME/.local/bin/trailhub-center" <<LANCEUR
#!/bin/bash
cd "$ICI" && exec "$ICI/.venv/bin/python" main.py "\$@"
LANCEUR
chmod +x "$HOME/.local/bin/trailhub-center"
cp packaging/icone.png "$HOME/.local/share/icons/hicolor/256x256/apps/trailhub-center.png"
cat > "$HOME/.local/share/applications/trailhub-center.desktop" <<BUREAU
[Desktop Entry]
Type=Application
Name=Trail Hub Center
Comment=Entraînement trail, club, organisation de courses
Exec=$HOME/.local/bin/trailhub-center
Icon=trailhub-center
Terminal=false
Categories=Sports;Utility;
StartupWMClass=TrailMaster Pro
BUREAU
command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database "$HOME/.local/share/applications" || true

echo
echo "✅ Installé : cherche « Trail Hub Center » dans le menu des applications,"
echo "   ou tape trailhub-center dans un terminal."
