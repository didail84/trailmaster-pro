"""
Indice de masse corporelle (IMC) : poids (kg) / taille (m)².

Classes de l'Organisation mondiale de la santé (adultes). L'IMC est un
repère, pas un diagnostic : chez un sportif musclé il surestime la masse
grasse, et il ne s'applique pas tel quel aux enfants (courbes par âge).
Aucun widget ici : utilisé par les écrans Poids, le dossier envoyé à l'IA
et la page Claude.
"""

# (borne haute exclue, libellé, niveau) — niveau : "bas", "normal", "attention", "alerte"
CLASSES_OMS = (
    (18.5, "Insuffisance pondérale", "attention"),
    (25.0, "Corpulence normale", "normal"),
    (30.0, "Surpoids", "attention"),
    (35.0, "Obésité modérée", "alerte"),
    (40.0, "Obésité sévère", "alerte"),
    (float("inf"), "Obésité massive", "alerte"),
)
IMC_NORMAL = (18.5, 25.0)

NOTE_IMC = ("Repère de l'OMS pour les adultes, pas un diagnostic : chez un sportif musclé, "
            "l'IMC surestime la masse grasse.")


def taille_en_metres(taille):
    """Accepte la taille en cm (175) ou en m (1,75) ; None si absente ou impossible."""
    if taille is None or taille == "":
        return None
    try:
        t = float(str(taille).replace(",", "."))
    except ValueError:
        return None
    if 0.5 <= t <= 2.6:
        return t
    if 50 <= t <= 260:
        return t / 100
    return None


def calculer_imc(poids_kg, taille):
    """IMC arrondi à 0,1, ou None si le poids ou la taille manquent."""
    m = taille_en_metres(taille)
    try:
        p = float(poids_kg) if poids_kg is not None else None
    except (TypeError, ValueError):
        p = None
    if not m or not p or p <= 0:
        return None
    return round(p / (m * m), 1)


def classe_imc(imc):
    """(libellé OMS, niveau) ou (None, None)."""
    if imc is None:
        return None, None
    for borne, libelle, niveau in CLASSES_OMS:
        if imc < borne:
            return libelle, niveau
    return CLASSES_OMS[-1][1], CLASSES_OMS[-1][2]


def poids_pour_imc(imc, taille):
    m = taille_en_metres(taille)
    return round(imc * m * m, 1) if m else None


def plage_poids_normal(taille):
    """(poids mini, poids maxi) d'une corpulence normale pour cette taille, ou None."""
    if not taille_en_metres(taille):
        return None
    return poids_pour_imc(IMC_NORMAL[0], taille), round(poids_pour_imc(IMC_NORMAL[1], taille) - 0.1, 1)


def resume_imc(poids_kg, taille):
    """Tout ce qu'il faut afficher : dict ou None si l'IMC ne peut pas être calculé."""
    imc = calculer_imc(poids_kg, taille)
    if imc is None:
        return None
    libelle, niveau = classe_imc(imc)
    plage = plage_poids_normal(taille)
    return {"imc": imc, "classe": libelle, "niveau": niveau, "poids_kg": round(float(poids_kg), 1),
            "taille_m": round(taille_en_metres(taille), 2), "plage_poids_normal_kg": plage}
