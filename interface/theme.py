"""
Couleur d'accent de l'application (boutons principaux, sélections,
survols) — choisie dans Réglages, stockée en base, appliquée à chaque
nouvelle fenêtre ouverte.

Les fenêtres déjà ouvertes au moment du changement gardent leur
ancienne couleur (il faudrait les reconstruire pour la mettre à jour
en direct) ; les nouvelles fenêtres ouvertes après le changement
utilisent la nouvelle couleur.

Ce module porte aussi la charte graphique commune à tout le logiciel
(fond, cartes, texte, polices) : les couleurs "neutres" ci-dessous
(PALETTE) ne changent pas avec l'athlète — seul l'accent est
personnalisable.
"""

import sys
from pathlib import Path

from data.database import obtenir_parametre, definir_parametre


def dossier_racine_ressources():
    """Dossier à partir duquel remonter vers 'ressources/', que le
    logiciel tourne depuis les sources (python3 main.py) ou depuis une
    vraie appli construite avec PyInstaller.

    En exécution normale, __file__ pointe vers le vrai fichier source
    et la racine du projet est son grand-parent. Une fois empaqueté,
    PyInstaller extrait (ou place à côté de l'exécutable) tous les
    fichiers ajoutés via --add-data dans un dossier donné par
    sys._MEIPASS — un chemin totalement différent de celui du projet
    d'origine, qu'il faut utiliser à la place sous peine de chercher
    au mauvais endroit (et donc de ne jamais trouver les polices ou
    images embarquées une fois l'appli installée)."""

    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
    return Path(__file__).resolve().parent.parent


COULEURS_ACCENT = {
    "Vert": "#2E7D32",
    "Bleu": "#1976D2",
    "Violet": "#6A1B9A",
    "Orange": "#E65100",
    "Rouge": "#C62828",
    "Turquoise": "#00838F",
}

COULEUR_PAR_DEFAUT = COULEURS_ACCENT["Vert"]


# ==================================================================
# CHARTE GRAPHIQUE COMMUNE — fond sombre, cartes, typographie
# ==================================================================
# Palette neutre partagée par tout le logiciel (identique quel que
# soit l'accent choisi) : fond général, fond des cartes/panneaux,
# bordures et niveaux de gris pour le texte.

PALETTE_SOMBRE = {
    "fond": "#12151A",
    "fond_secondaire": "#14181D",
    "carte": "#1B2126",
    "carte_haute": "#171C21",
    "bordure": "#262E34",
    "bordure_douce": "#232A30",
    "texte": "#F3F6F7",
    "texte_att": "#C9D2D6",
    "texte_secondaire": "#9AA7AE",
    "texte_discret": "#6B767D",
    "bleu": "#4C8DFF",
    "orange": "#FF8A3D",
}

# Mode clair optionnel (Réglages > Apparence) — mêmes clés, valeurs
# inversées en luminosité, pensées pour rester lisibles en plein
# soleil/en extérieur. Les couleurs d'accent (choisies séparément par
# l'utilisateur) restent inchangées entre les deux modes.
PALETTE_CLAIRE = {
    "fond": "#F4F6F7",
    "fond_secondaire": "#ECEFF1",
    "carte": "#FFFFFF",
    "carte_haute": "#F8F9FA",
    "bordure": "#D7DCE0",
    "bordure_douce": "#E2E6E9",
    "texte": "#161A1E",
    "texte_att": "#2B3238",
    "texte_secondaire": "#5B656C",
    "texte_discret": "#8A939A",
    "bleu": "#1976D2",
    "orange": "#E65100",
}

# PALETTE reste l'objet importé partout ailleurs (`from interface.theme
# import PALETTE`) — un dict MUTABLE dont le contenu est remplacé en
# place par definir_mode_couleur() plutôt que réassigné, pour que tous
# les modules qui l'ont déjà importé voient le changement sans avoir à
# être modifiés un par un (même principe que la couleur d'accent,
# relue à chaque construction d'écran).
PALETTE = dict(PALETTE_SOMBRE)

# Polices — Sora pour les titres (repères visuels, chiffres clés),
# IBM Plex Sans pour le texte courant : combinaison distinctive
# embarquée avec le logiciel (ressources/polices), donc identique
# sur toutes les installations, sans dépendre des polices déjà
# présentes sur l'ordinateur.
POLICE_TITRE = "Sora"
POLICE_TITRE_DEMI = "Sora SemiBold"
POLICE_TITRE_EXTRA = "Sora ExtraBold"
POLICE_TEXTE = "IBM Plex Sans"
POLICE_TEXTE_MOYENNE = "IBM Plex Sans Medium"
POLICE_TEXTE_DEMI = "IBM Plex Sans SemiBold"

_POLICES_CHARGEES = False


def charger_polices():
    """Enregistre les polices maison (Sora / IBM Plex Sans) auprès de
    Qt, une seule fois par lancement du logiciel. À appeler après la
    création de QApplication (donc jamais au tout premier import de
    ce module) — sans effet si déjà fait, donc sans risque à rappeler
    depuis chaque écran."""

    global _POLICES_CHARGEES
    if _POLICES_CHARGEES:
        return

    from PySide6.QtGui import QFontDatabase

    dossier = dossier_racine_ressources() / "ressources" / "polices"
    if dossier.is_dir():
        for fichier in sorted(dossier.glob("*.ttf")):
            QFontDatabase.addApplicationFont(str(fichier))

    _POLICES_CHARGEES = True


def obtenir_version_installee():
    """Identifiant de la construction actuelle (date-heure), inscrit
    par Installer_MacBook.command à chaque reconstruction de l'appli —
    permet de vérifier après une mise à jour qu'on utilise bien la
    toute dernière version, et pas une ancienne copie relancée par
    erreur. Absent en exécution depuis les sources (python3 main.py) :
    dans ce cas, le code est de toute façon toujours à jour."""

    chemin = dossier_racine_ressources() / "interface" / "assets" / "version_build.txt"
    if chemin.is_file():
        try:
            return chemin.read_text(encoding="utf-8").strip() or "inconnue"
        except OSError:
            return "inconnue"
    return "développement (sources)"


def obtenir_couleur_accent_douce(opacite=0.14):
    """Version 'teinte douce' de l'accent choisi (fond de pastille,
    surbrillance de ligne active…) — en rgba, calculée depuis
    n'importe quelle couleur d'accent (les 6 couleurs proposées ou
    une couleur personnalisée)."""

    couleur_hex = obtenir_couleur_accent().lstrip("#")
    r, g, b = int(couleur_hex[0:2], 16), int(couleur_hex[2:4], 16), int(couleur_hex[4:6], 16)
    return f"rgba({r}, {g}, {b}, {opacite})"


def obtenir_mode_couleur():
    return obtenir_parametre("mode_couleur", "Sombre")


def definir_mode_couleur(mode):
    """Bascule PALETTE (en place — voir le commentaire plus haut) entre
    le jeu de couleurs sombre et clair, et mémorise le choix. Comme
    pour la couleur d'accent, les fenêtres déjà ouvertes gardent leur
    ancienne apparence ; seules les nouvelles fenêtres utilisent le
    nouveau mode."""

    source = PALETTE_CLAIRE if mode == "Clair" else PALETTE_SOMBRE
    PALETTE.clear()
    PALETTE.update(source)
    definir_parametre("mode_couleur", mode)


def appliquer_mode_couleur_enregistre():
    """À appeler une fois au démarrage de l'application (avant la
    création de la première fenêtre) pour que PALETTE reflète le choix
    mémorisé dans Réglages plutôt que de toujours démarrer en sombre."""

    definir_mode_couleur(obtenir_mode_couleur())


def obtenir_couleur_accent():
    return obtenir_parametre("couleur_accent", COULEUR_PAR_DEFAUT)


def obtenir_nom_couleur_accent():
    couleur = obtenir_couleur_accent()
    for nom, hex_ in COULEURS_ACCENT.items():
        if hex_ == couleur:
            return nom
    return "Personnalisée"


def definir_couleur_accent(nom_ou_hex):
    valeur = COULEURS_ACCENT.get(nom_ou_hex, nom_ou_hex)
    definir_parametre("couleur_accent", valeur)


def eclaircir(couleur_hex, facteur=0.18):
    """Éclaircit une couleur hexadécimale (#RRGGBB) — utilisé pour
    l'effet de survol des boutons."""

    couleur_hex = couleur_hex.lstrip("#")
    r, g, b = int(couleur_hex[0:2], 16), int(couleur_hex[2:4], 16), int(couleur_hex[4:6], 16)
    r = min(255, int(r + (255 - r) * facteur))
    g = min(255, int(g + (255 - g) * facteur))
    b = min(255, int(b + (255 - b) * facteur))
    return f"#{r:02X}{g:02X}{b:02X}"


# ==================================================================
# ÉCHELLE DE COULEUR PAR POURCENTAGE D'ALERTE
# ==================================================================
# Échelle commune à 5 niveaux (vert/jaune/orange/rouge/noir) utilisée
# pour colorer n'importe quel critère surveillé (ACWR, forme du jour,
# sommeil, jours à forte charge...) une fois ramené à un pourcentage de
# risque 0-100 (voir interface/coach.py — obtenir_indicateurs_couleur) :
# 0% = situation idéale, 100%+ = seuil critique largement dépassé.

BANDES_COULEUR_POURCENTAGE = [
    (20, "#43A047", "Vert"),
    (45, "#FDD835", "Jaune"),
    (70, "#FB8C00", "Orange"),
    (90, "#E53935", "Rouge"),
    (10_000, "#1B1B1F", "Noir"),
]


def couleur_pour_pourcentage(pourcentage):
    """Retourne (couleur_hex, label) pour un pourcentage de risque/alerte
    (0-100, peut dépasser 100 en cas de dépassement franc d'un seuil).
    Retourne (None, None) si `pourcentage` est None (donnée indisponible)."""

    if pourcentage is None:
        return None, None
    pourcentage = max(0, pourcentage)
    for seuil, couleur, label in BANDES_COULEUR_POURCENTAGE:
        if pourcentage < seuil:
            return couleur, label
    return BANDES_COULEUR_POURCENTAGE[-1][1], BANDES_COULEUR_POURCENTAGE[-1][2]
