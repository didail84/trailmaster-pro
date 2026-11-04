"""
Couleur d'un niveau de risque (0-100 %), sans aucune dépendance à
l'interface : utilisée par le coach (pastilles du tableau de bord),
la consultation réseau local et le thème de l'application.
"""

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
